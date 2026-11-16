"""Offline evaluation of end-of-turn policy tradeoffs.

The evaluator consumes redacted pause labels and policy decisions only. It
does not load audio, run ASR/VAD, access a microphone, or control turn-taking.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import ceil, isfinite
from statistics import median
import re
from typing import cast

MAX_DECISIONS = 100_000
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z")
_LANGUAGE = re.compile(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*\Z")


@dataclass(frozen=True, slots=True)
class Decision:
    """One policy decision at one adjudicated silence pause.

    label is eot for a true turn ending or hold for a mid-turn hesitation.
    decision_latency_ms is measured from pause onset when the policy triggers.
    timeout_ms is the configured maximum wait; a missed EOT is censored at
    this timeout so a policy that never speaks cannot look artificially fast.
    """

    policy_id: str
    sample_id: str
    language: str
    cohort: str
    label: str
    action: str
    timeout_ms: float
    decision_latency_ms: float | None = None


def _opaque_id(value: object, field: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError(f"{field} must be a bounded identifier")
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


def _trigger_latency(row: Decision) -> float:
    assert row.decision_latency_ms is not None
    return float(row.decision_latency_ms)


def _summary(rows: list[Decision]) -> dict:
    eot_rows = [row for row in rows if row.label == "eot"]
    hold_rows = [row for row in rows if row.label == "hold"]
    triggered_eot = [row for row in eot_rows if row.action == "trigger"]
    missed_eot = len(eot_rows) - len(triggered_eot)
    false_cutoffs = [row for row in hold_rows if row.action == "trigger"]

    endpoint_delays = [
        _trigger_latency(row)
        if row.action == "trigger"
        else float(row.timeout_ms)
        for row in eot_rows
    ]
    false_cutoff_delays = [
        _trigger_latency(row) for row in false_cutoffs
    ]
    return {
        "decisions": len(rows),
        "end_of_turn": {
            "pauses": len(eot_rows),
            "triggered": len(triggered_eot),
            "missed": missed_eot,
            "missed_rate": _rate(missed_eot, len(eot_rows)),
            "endpoint_delay_ms": _distribution(endpoint_delays),
            "triggered_delay_ms": _distribution([
                _trigger_latency(row) for row in triggered_eot
            ]),
        },
        "mid_turn_hold": {
            "pauses": len(hold_rows),
            "false_cutoffs": len(false_cutoffs),
            "false_cutoff_rate": _rate(len(false_cutoffs), len(hold_rows)),
            "false_cutoff_delay_ms": _distribution(false_cutoff_delays),
        },
    }


def _dominates(left: tuple[float, float, float], right: tuple[float, float, float]) -> bool:
    return (
        all(a <= b for a, b in zip(left, right))
        and any(a < b for a, b in zip(left, right))
    )


def evaluate(decisions: Iterable[Decision]) -> dict:
    """Compare policies on false cutoffs, missed turns, and endpoint delay.

    The Pareto frontier is emitted only when every policy has the exact same
    adjudicated sample set. No scalar score or automatic policy selection is
    produced. Endpoint delay includes the configured timeout for missed EOTs.
    """
    rows: list[Decision] = []
    sample_metadata: dict[str, tuple[str, str, str]] = {}
    policy_samples: dict[str, set[str]] = {}
    by_policy: dict[str, list[Decision]] = {}
    seen: set[tuple[str, str]] = set()

    for row in decisions:
        if len(rows) >= MAX_DECISIONS:
            raise ValueError(f"At most {MAX_DECISIONS} decisions are allowed")
        if not isinstance(row, Decision):
            raise ValueError("Every item must be a Decision")

        policy_id = _opaque_id(row.policy_id, "policy_id")
        sample_id = _opaque_id(row.sample_id, "sample_id")
        _opaque_id(row.cohort, "cohort")
        if not isinstance(row.language, str) or _LANGUAGE.fullmatch(row.language) is None:
            raise ValueError("language must be a lowercase BCP-47-style tag")
        if row.label not in ("eot", "hold"):
            raise ValueError("label must be eot or hold")
        if row.action not in ("trigger", "hold"):
            raise ValueError("action must be trigger or hold")

        timeout = _number(row.timeout_ms, "timeout_ms")
        assert timeout is not None
        if timeout <= 0:
            raise ValueError("timeout_ms must be greater than zero")
        latency = _number(
            row.decision_latency_ms, "decision_latency_ms", optional=True
        )
        if row.action == "trigger":
            if latency is None:
                raise ValueError("trigger decisions require decision_latency_ms")
            if latency > timeout:
                raise ValueError("trigger latency cannot exceed timeout_ms")
        elif latency is not None:
            raise ValueError("hold decisions must not provide decision_latency_ms")

        pair = (policy_id, sample_id)
        if pair in seen:
            raise ValueError("sample_id must be unique within each policy")
        seen.add(pair)

        metadata = (row.language, row.cohort, row.label)
        previous = sample_metadata.get(sample_id)
        if previous is not None and previous != metadata:
            raise ValueError("policy rows disagree on sample language, cohort, or label")
        sample_metadata[sample_id] = metadata
        policy_samples.setdefault(policy_id, set()).add(sample_id)
        by_policy.setdefault(policy_id, []).append(row)
        rows.append(row)

    policy_ids = sorted(by_policy)
    union_samples = set(sample_metadata)
    common_samples = set(union_samples)
    for policy_id in policy_ids:
        common_samples.intersection_update(policy_samples[policy_id])
    complete = bool(policy_ids) and all(
        policy_samples[key] == union_samples for key in policy_ids
    )

    reports = []
    points: dict[str, tuple[float, float, float]] = {}
    for policy_id in policy_ids:
        policy_rows = by_policy[policy_id]
        summary = _summary(policy_rows)
        by_language = {
            language: _summary([row for row in policy_rows if row.language == language])
            for language in sorted({row.language for row in policy_rows})
        }
        by_cohort = {
            cohort: _summary([row for row in policy_rows if row.cohort == cohort])
            for cohort in sorted({row.cohort for row in policy_rows})
        }
        reports.append({
            "policy_id": policy_id,
            **summary,
            "by_language": by_language,
            "by_cohort": by_cohort,
        })

        false_rate = summary["mid_turn_hold"]["false_cutoff_rate"]
        missed_rate = summary["end_of_turn"]["missed_rate"]
        p95_delay = summary["end_of_turn"]["endpoint_delay_ms"]["p95"]
        if false_rate is not None and missed_rate is not None and p95_delay is not None:
            points[policy_id] = (false_rate, missed_rate, p95_delay)

    frontier: list[str] = []
    if complete and len(points) == len(policy_ids):
        for policy_id, point in points.items():
            if not any(
                other_id != policy_id and _dominates(other, point)
                for other_id, other in points.items()
            ):
                frontier.append(policy_id)

    return {
        "schema": 1,
        "decisions": len(rows),
        "policies": reports,
        "paired_coverage": {
            "complete": complete,
            "policy_count": len(policy_ids),
            "union_samples": len(union_samples),
            "common_samples": len(common_samples),
            "by_policy": {
                policy_id: len(policy_samples[policy_id]) for policy_id in policy_ids
            },
        },
        "pareto_frontier": sorted(frontier),
        "note": (
            "Offline redacted-metadata evaluator only; no audio, transcript, "
            "microphone, speaker identity, or live turn-control action is used. "
            "Endpoint delay is conversational wait after a true turn ending, "
            "not model inference latency. Missed EOTs are charged at timeout. "
            "No composite score or automatic policy selection is produced."
        ),
    }
