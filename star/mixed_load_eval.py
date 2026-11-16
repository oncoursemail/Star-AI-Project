"""Offline evaluation of STAR's simultaneous inference, game, voice, and stream load.

The evaluator consumes aggregate numeric benchmark rows only. It never reads
media, transcripts, viewer identifiers, device names, or live system state.
It reports distributions and matched deltas; it deliberately emits no
composite performance score or automatic promotion decision.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import ceil, isfinite
import re
from typing import cast

ARMS = ("baseline", "candidate")
SCENARIOS = ("idle", "game_only", "stream_only", "mixed")
PHASES = ("cold", "warm")
MAX_SAMPLES = 20_000
_MAX_COUNTER = 1_000_000_000
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z")

NUMERIC_FIELDS = (
    "ttft_ms",
    "client_heard_ms",
    "task_completion_ms",
    "decode_tokens_per_second",
    "game_fps",
    "cpu_percent",
    "ram_mb",
    "vram_mb",
)
COUNTER_FIELDS = (
    "audio_underruns",
    "obs_dropped_frames",
    "avatar_dropped_frames",
)
DEADLINE_FIELDS = (
    ("client_heard_ms", "client_heard_deadline_ms"),
    ("task_completion_ms", "task_deadline_ms"),
)


@dataclass(frozen=True, slots=True)
class Sample:
    """One repetition of a fixed benchmark case on one machine/configuration.

    case_id must identify the same scripted workload in both arms. sample_id
    is an opaque repetition ID. Use cold/warm and scenario labels consistently.
    client_heard_ms is valid only when the client-side loopback/measurement
    point actually observed audible output; queue submission is not enough.
    Resource values are host-measured aggregates, not inferred from model data.
    """

    sample_id: str
    case_id: str
    replicate_id: str
    arm: str
    scenario: str
    phase: str
    ttft_ms: float | None = None
    client_heard_ms: float | None = None
    task_completion_ms: float | None = None
    decode_tokens_per_second: float | None = None
    game_fps: float | None = None
    cpu_percent: float | None = None
    ram_mb: float | None = None
    vram_mb: float | None = None
    audio_underruns: int | None = None
    obs_dropped_frames: int | None = None
    avatar_dropped_frames: int | None = None
    task_success: bool | None = None
    client_heard_deadline_ms: float | None = None
    task_deadline_ms: float | None = None


def _opaque_id(value: object, field: str) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise ValueError(f"{field} must be a bounded opaque identifier")
    return value


def _number(value: object, field: str) -> float | None:
    if value is None:
        return None
    if type(value) not in (int, float):
        raise ValueError(f"{field} must be a finite nonnegative number or None")
    number = cast(int | float, value)
    if not isfinite(number) or number < 0:
        raise ValueError(f"{field} must be a finite nonnegative number or None")
    return float(number)


def _counter(value: object, field: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= _MAX_COUNTER:
        raise ValueError(f"{field} must be a bounded nonnegative integer or None")
    return value


def _validate(sample: Sample) -> None:
    _opaque_id(sample.sample_id, "sample_id")
    _opaque_id(sample.case_id, "case_id")
    _opaque_id(sample.replicate_id, "replicate_id")
    if sample.arm not in ARMS:
        raise ValueError("arm must be baseline or candidate")
    if sample.scenario not in SCENARIOS:
        raise ValueError("unknown benchmark scenario")
    if sample.phase not in PHASES:
        raise ValueError("phase must be cold or warm")

    for field in NUMERIC_FIELDS:
        value = _number(getattr(sample, field), field)
        if field == "cpu_percent" and value is not None and value > 100:
            raise ValueError("cpu_percent cannot exceed 100")
    for field in COUNTER_FIELDS:
        _counter(getattr(sample, field), field)

    if sample.task_success is not None and type(sample.task_success) is not bool:
        raise ValueError("task_success must be true, false, or None")

    for latency_field, deadline_field in DEADLINE_FIELDS:
        latency = _number(getattr(sample, latency_field), latency_field)
        deadline = _number(getattr(sample, deadline_field), deadline_field)
        if deadline is not None and latency is None:
            raise ValueError(f"{deadline_field} requires {latency_field}")


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[ceil(percentile * len(ordered)) - 1], 3)


def _distribution(values: list[float], total: int) -> dict:
    observed = len(values)
    return {
        "n": observed,
        "missing": total - observed,
        "mean": round(sum(values) / observed, 3) if observed else None,
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "p99": _percentile(values, 0.99),
        "max": round(max(values), 3) if values else None,
    }


def _deadline_summary(rows: list[Sample], latency_field: str, deadline_field: str) -> dict:
    eligible = [
        row for row in rows
        if getattr(row, latency_field) is not None
        and getattr(row, deadline_field) is not None
    ]
    on_time = sum(
        getattr(row, latency_field) <= getattr(row, deadline_field)
        for row in eligible
    )
    return {
        "eligible": len(eligible),
        "on_time": on_time,
        "late": len(eligible) - on_time,
        "on_time_rate": round(on_time / len(eligible), 6) if eligible else None,
    }


def _group_summary(rows: list[Sample]) -> dict:
    metrics: dict[str, dict] = {}
    for field in NUMERIC_FIELDS:
        values = [
            float(value) for row in rows
            if (value := getattr(row, field)) is not None
        ]
        metrics[field] = _distribution(values, len(rows))

    counters: dict[str, dict] = {}
    for field in COUNTER_FIELDS:
        values = [
            value for row in rows
            if (value := getattr(row, field)) is not None
        ]
        counters[field] = {
            "n": len(values),
            "missing": len(rows) - len(values),
            "total": sum(values) if values else None,
            "max": max(values) if values else None,
        }

    success = [row.task_success for row in rows if row.task_success is not None]
    return {
        "samples": len(rows),
        "metrics": metrics,
        "counters": counters,
        "task_success": {
            "n": len(success),
            "passed": sum(value is True for value in success),
            "failed": sum(value is False for value in success),
            "rate": round(sum(value is True for value in success) / len(success), 6)
            if success else None,
        },
        "deadlines": {
            "client_heard": _deadline_summary(rows, *DEADLINE_FIELDS[0]),
            "task_completion": _deadline_summary(rows, *DEADLINE_FIELDS[1]),
        },
    }


def _paired_summary(
    index: dict[tuple[str, str, str, str], dict[str, Sample]],
) -> dict:
    keys = set(index)
    matched = sorted(
        key for key, arms in index.items()
        if "baseline" in arms and "candidate" in arms
    )
    baseline_only = sum("baseline" in index[key] and "candidate" not in index[key] for key in keys)
    candidate_only = sum("candidate" in index[key] and "baseline" not in index[key] for key in keys)

    deltas: dict[str, dict] = {}
    for field in NUMERIC_FIELDS:
        values = []
        for key in matched:
            before = getattr(index[key]["baseline"], field)
            after = getattr(index[key]["candidate"], field)
            if before is not None and after is not None:
                values.append(float(after) - float(before))
        deltas[field] = _distribution(values, len(matched))

    success_improved = success_regressed = success_unchanged = success_missing = 0
    for key in matched:
        before = index[key]["baseline"].task_success
        after = index[key]["candidate"].task_success
        if before is None or after is None:
            success_missing += 1
        elif before is False and after is True:
            success_improved += 1
        elif before is True and after is False:
            success_regressed += 1
        else:
            success_unchanged += 1

    return {
        "matched_cases": len(matched),
        "baseline_only_cases": baseline_only,
        "candidate_only_cases": candidate_only,
        "numeric_candidate_minus_baseline": deltas,
        "task_success": {
            "improved": success_improved,
            "regressed": success_regressed,
            "unchanged": success_unchanged,
            "missing": success_missing,
        },
    }


def evaluate(samples: Iterable[Sample]) -> dict:
    """Summarize cold/warm and idle/stream/game/mixed runs without a composite score.

    Rows are bounded before retention. Pairing uses case/scenario/phase, not
    wall-clock order. Missing measurements stay missing and unmatched cases
    are reported rather than silently discarded.
    """
    rows: list[Sample] = []
    for sample in samples:
        if len(rows) >= MAX_SAMPLES:
            raise ValueError(f"At most {MAX_SAMPLES} samples are allowed")
        if not isinstance(sample, Sample):
            raise ValueError("Every row must be a Sample")
        _validate(sample)
        rows.append(sample)

    sample_ids: set[str] = set()
    index: dict[tuple[str, str, str, str], dict[str, Sample]] = {}
    groups: dict[tuple[str, str, str], list[Sample]] = {}
    for row in rows:
        if row.sample_id in sample_ids:
            raise ValueError("sample_id values must be unique")
        sample_ids.add(row.sample_id)

        key = (row.case_id, row.replicate_id, row.scenario, row.phase)
        arms = index.setdefault(key, {})
        if row.arm in arms:
            raise ValueError("A case/replicate/scenario/phase may appear once per arm")
        arms[row.arm] = row
        groups.setdefault((row.arm, row.scenario, row.phase), []).append(row)

    group_reports = []
    for key in sorted(groups):
        arm, scenario, phase = key
        group_reports.append({
            "arm": arm,
            "scenario": scenario,
            "phase": phase,
            **_group_summary(groups[key]),
        })

    return {
        "schema": 1,
        "samples": len(rows),
        "groups": group_reports,
        "paired": _paired_summary(index),
        "note": (
            "Offline aggregate evaluator only. No composite score or promotion "
            "decision is produced; compare identical cases and retain target-PC "
            "hardware, workload, and software provenance separately."
        ),
    }
