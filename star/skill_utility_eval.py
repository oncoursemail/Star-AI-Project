"""Offline paired evaluation of whether an injected skill actually helps.

The evaluator accepts redacted run metadata only. It does not select, enable,
rewrite, or promote skills. Compare skill-on and skill-off runs on the same
task, model, harness, dataset, base prompt, and replicate.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import ceil, isfinite
from statistics import median
import re
from typing import cast

MAX_TRIALS = 100_000
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SPLITS = frozenset(("train", "validation", "holdout"))
_ARMS = frozenset(("off", "on"))


@dataclass(frozen=True, slots=True)
class Trial:
    """One skill-on or skill-off attempt for one task and replicate.

    base_prompt_sha256 hashes the prompt/context before the optional skill is
    injected. model_revision, harness_revision, task_revision and
    dataset_revision pin the comparison. A skill is the only intended
    difference between the two arms.
    """

    skill_id: str
    case_id: str
    replicate: int
    split: str
    arm: str
    model_id: str
    model_revision: str
    harness_revision: str
    dataset_revision: str
    task_revision: str
    base_prompt_sha256: str
    success: bool
    input_tokens: int
    output_tokens: int
    latency_ms: float
    deadline_ms: float | None = None


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError(f"{field} must be a bounded identifier")
    return value


def _count(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


def _number(value: object, field: str, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if type(value) not in (int, float):
        raise ValueError(f"{field} must be a finite nonnegative number")
    number = cast(int | float, value)
    if not isfinite(number) or number < 0:
        raise ValueError(f"{field} must be a finite nonnegative number")
    return float(number)


def _rate(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 6)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if percentile == 0.50:
        return round(median(ordered), 3)
    return round(ordered[ceil(percentile * len(ordered)) - 1], 3)


def _distribution(values: list[float]) -> dict:
    return {
        "n": len(values),
        "mean": round(sum(values) / len(values), 3) if values else None,
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "p99": _percentile(values, 0.99),
        "max": round(max(values), 3) if values else None,
    }


def _pair_metadata(row: Trial) -> tuple:
    return (
        row.model_id,
        row.model_revision,
        row.harness_revision,
        row.dataset_revision,
        row.task_revision,
        row.base_prompt_sha256,
        row.deadline_ms,
    )


def _validate(row: Trial) -> None:
    if not isinstance(row, Trial):
        raise ValueError("Every item must be a Trial")
    for field in (
        "skill_id", "case_id", "model_id", "model_revision",
        "harness_revision", "dataset_revision", "task_revision",
    ):
        _identifier(getattr(row, field), field)
    if type(row.replicate) is not int or row.replicate < 0:
        raise ValueError("replicate must be a nonnegative integer")
    if not isinstance(row.split, str) or row.split not in _SPLITS:
        raise ValueError("split must be train, validation, or holdout")
    if not isinstance(row.arm, str) or row.arm not in _ARMS:
        raise ValueError("arm must be off or on")
    if type(row.success) is not bool:
        raise ValueError("success must be a boolean")
    if not isinstance(row.base_prompt_sha256, str) or _SHA256.fullmatch(row.base_prompt_sha256) is None:
        raise ValueError("base_prompt_sha256 must be a lowercase SHA-256 digest")
    _count(row.input_tokens, "input_tokens")
    _count(row.output_tokens, "output_tokens")
    latency = _number(row.latency_ms, "latency_ms")
    assert latency is not None
    deadline = _number(row.deadline_ms, "deadline_ms", optional=True)
    if deadline is not None and deadline <= 0:
        raise ValueError("deadline_ms must be greater than zero when supplied")


def _summarize(skill_id: str, split: str, rows: list[Trial]) -> dict:
    pairs: dict[tuple[str, int], dict[str, Trial]] = {}
    for row in rows:
        pairs.setdefault((row.case_id, row.replicate), {})[row.arm] = row

    matched: list[tuple[Trial, Trial]] = []
    unpaired_off = 0
    unpaired_on = 0
    for arms in pairs.values():
        off = arms.get("off")
        on = arms.get("on")
        if off is None:
            unpaired_on += 1
        elif on is None:
            unpaired_off += 1
        else:
            if _pair_metadata(off) != _pair_metadata(on):
                raise ValueError("paired arms must use identical model, harness, task, dataset, base prompt, and deadline")
            matched.append((off, on))

    off_success = sum(off.success for off, _ in matched)
    on_success = sum(on.success for _, on in matched)
    wins = sum(on.success and not off.success for off, on in matched)
    regressions = sum(off.success and not on.success for off, on in matched)
    ties = len(matched) - wins - regressions

    latency_delta = [on.latency_ms - off.latency_ms for off, on in matched]
    input_delta = [float(on.input_tokens - off.input_tokens) for off, on in matched]
    output_delta = [float(on.output_tokens - off.output_tokens) for off, on in matched]
    deadline_pairs = [
        (off, on) for off, on in matched
        if off.deadline_ms is not None and on.deadline_ms is not None
    ]
    off_deadline_pass = 0
    on_deadline_pass = 0
    for off, on in deadline_pairs:
        assert off.deadline_ms is not None and on.deadline_ms is not None
        off_deadline_pass += off.latency_ms <= off.deadline_ms
        on_deadline_pass += on.latency_ms <= on.deadline_ms
    off_tokens = sum(off.input_tokens for off, _ in matched)

    return {
        "skill_id": skill_id,
        "split": split,
        "pairs": len(matched),
        "unpaired_off": unpaired_off,
        "unpaired_on": unpaired_on,
        "coverage": _rate(len(matched), len(pairs)),
        "success": {
            "off": off_success,
            "on": on_success,
            "off_rate": _rate(off_success, len(matched)),
            "on_rate": _rate(on_success, len(matched)),
            "delta_on_minus_off": round((on_success - off_success) / len(matched), 6) if matched else None,
            "wins": wins,
            "regressions": regressions,
            "ties": ties,
            "net_wins": wins - regressions,
        },
        "latency_delta_ms_on_minus_off": _distribution(latency_delta),
        "input_token_delta_on_minus_off": _distribution(input_delta),
        "output_token_delta_on_minus_off": _distribution(output_delta),
        "input_token_overhead_rate": (
            round(sum(input_delta) / off_tokens, 6) if off_tokens else None
        ),
        "deadline": {
            "pairs": len(deadline_pairs),
            "off_passed": off_deadline_pass,
            "on_passed": on_deadline_pass,
            "off_rate": _rate(off_deadline_pass, len(deadline_pairs)),
            "on_rate": _rate(on_deadline_pass, len(deadline_pairs)),
        },
    }


def evaluate(trials: Iterable[Trial]) -> dict:
    """Return paired skill utility by skill and split.

    Unpaired rows are counted but excluded from outcome comparisons. A pair
    with mismatched provenance is rejected instead of being silently compared.
    The evaluator reports outcomes and costs separately and never recommends
    automatic enablement or promotion.
    """
    groups: dict[tuple[str, str], list[Trial]] = {}
    seen: set[tuple[str, str, int, str]] = set()
    case_splits: dict[tuple[str, str, str], str] = {}
    count = 0

    for row in trials:
        if count >= MAX_TRIALS:
            raise ValueError(f"At most {MAX_TRIALS} trials are allowed")
        _validate(row)
        count += 1
        identity = (row.skill_id, row.case_id, row.replicate, row.arm)
        if identity in seen:
            raise ValueError("duplicate skill/case/replicate/arm trial")
        seen.add(identity)
        task_identity = (row.dataset_revision, row.task_revision, row.case_id)
        previous_split = case_splits.get(task_identity)
        if previous_split is not None and previous_split != row.split:
            raise ValueError("a task must not appear in more than one split")
        case_splits[task_identity] = row.split
        groups.setdefault((row.skill_id, row.split), []).append(row)

    reports = [
        _summarize(skill_id, split, groups[(skill_id, split)])
        for skill_id, split in sorted(groups)
    ]
    return {
        "trials": count,
        "skills": reports,
        "note": (
            "Paired descriptive evaluation only. Unpaired trials are excluded from outcome deltas; "
            "mismatched provenance is rejected. No automatic skill enablement, rewrite, or promotion occurs. "
            "Keep holdout tasks sealed from skill authoring and tuning."
        ),
    }
