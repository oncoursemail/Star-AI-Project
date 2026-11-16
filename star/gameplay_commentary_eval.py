"""Offline evaluation of event-driven gameplay commentary decisions.

This module scores a policy's choice to comment, acknowledge, stay silent, or
yield when a labelled gameplay/stream event occurs. It deliberately stores
only opaque case IDs and adjudicated metadata: no media, transcripts, viewer
identifiers, network access, or runtime actions.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import ceil, isfinite
from typing import cast

ACTIONS = ("comment", "acknowledge", "silence", "yield")
SPEECH_ACTIONS = frozenset(("comment", "acknowledge"))
MAX_OBSERVATIONS = 100_000


@dataclass(frozen=True, slots=True)
class Observation:
    """One independently labelled event/decision pair.

    Timestamps are milliseconds on one monotonic clock. deadline_ms is a
    duration from event_ms. Use synthetic case IDs, never viewer IDs.
    grounded is an independent human/fixture judgement of whether the
    emitted speech was supported by the observed event.
    """

    sample_id: str
    expected_action: str
    predicted_action: str
    event_ms: float
    decision_ms: float | None = None
    deadline_ms: float | None = None
    negative_control: bool = False
    grounded: bool | None = None


def _number(value: object, field: str, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if type(value) not in (int, float):
        raise ValueError(f"{field} must be a finite non-negative number")
    number = cast(int | float, value)
    if not isfinite(number) or number < 0:
        raise ValueError(f"{field} must be a finite non-negative number")
    return float(number)


def _rate(numerator: float, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 6)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[ceil(percentile * len(ordered)) - 1], 3)


def evaluate(observations: Iterable[Observation]) -> dict:
    """Return separate action, silence, grounding, and timing metrics.

    No composite human-likeness score is produced: strong answer accuracy
    must not hide false commentary, poor silence behaviour, or ungrounded speech.
    Missing timestamps and unreviewed grounding remain missing, never imputed.
    Input is consumed incrementally and bounded before any unbounded materialization.
    """
    rows: list[Observation] = []
    for row in observations:
        if len(rows) >= MAX_OBSERVATIONS:
            raise ValueError(f"At most {MAX_OBSERVATIONS} observations are allowed")
        if not isinstance(row, Observation):
            raise ValueError("Every row must be an Observation")
        rows.append(row)

    ids: set[str] = set()
    confusion = {
        expected: {predicted: 0 for predicted in ACTIONS}
        for expected in ACTIONS
    }

    for row in rows:
        sample_id = row.sample_id
        if (not isinstance(sample_id, str) or not sample_id.strip()
                or len(sample_id) > 128 or sample_id in ids):
            raise ValueError(
                "Sample IDs must be unique, non-empty text of at most 128 characters"
            )
        ids.add(sample_id)

        if row.expected_action not in ACTIONS or row.predicted_action not in ACTIONS:
            raise ValueError("Unknown expected or predicted action")

        event_ms = _number(row.event_ms, "event_ms")
        assert event_ms is not None
        decision_ms = _number(row.decision_ms, "decision_ms", optional=True)
        _number(row.deadline_ms, "deadline_ms", optional=True)

        if decision_ms is not None and decision_ms < event_ms:
            raise ValueError("decision_ms cannot precede event_ms")
        if type(row.negative_control) is not bool:
            raise ValueError("negative_control must be a boolean")
        if row.negative_control and row.expected_action != "silence":
            raise ValueError("Negative controls must expect silence")
        if row.grounded is not None and type(row.grounded) is not bool:
            raise ValueError("grounded must be true, false, or unknown")
        if row.grounded is not None and row.predicted_action not in SPEECH_ACTIONS:
            raise ValueError("grounded is only applicable to speech-producing decisions")

        confusion[row.expected_action][row.predicted_action] += 1

    total = len(rows)
    correct = sum(confusion[action][action] for action in ACTIONS)
    per_action: dict[str, dict] = {}
    recalls: list[float] = []
    f1s: list[float] = []

    for action in ACTIONS:
        true_positive = confusion[action][action]
        false_positive = sum(
            confusion[expected][action]
            for expected in ACTIONS if expected != action
        )
        false_negative = sum(
            confusion[action][predicted]
            for predicted in ACTIONS if predicted != action
        )
        support = true_positive + false_negative
        precision = _rate(true_positive, true_positive + false_positive)
        recall = _rate(true_positive, support)
        f1 = (
            None if support == 0 else
            round(
                (2 * true_positive) /
                (2 * true_positive + false_positive + false_negative),
                6,
            )
        )
        per_action[action] = {
            "support": support,
            "tp": true_positive,
            "fp": false_positive,
            "fn": false_negative,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
        if support:
            assert recall is not None and f1 is not None
            recalls.append(recall)
            f1s.append(f1)

    negative_controls = [row for row in rows if row.negative_control]
    false_speech = sum(
        row.predicted_action in SPEECH_ACTIONS for row in negative_controls
    )
    expected_silence = sum(row.expected_action == "silence" for row in rows)
    predicted_silence = sum(row.predicted_action == "silence" for row in rows)
    true_silence = confusion["silence"]["silence"]

    speech_latencies: list[float] = []
    missing_speech_timestamps = 0
    grounded_reviewed = 0
    grounded_true = 0
    eligible_deadlines = 0
    on_time = 0
    late = 0

    for row in rows:
        if row.predicted_action in SPEECH_ACTIONS:
            if row.decision_ms is None:
                missing_speech_timestamps += 1
            else:
                speech_latencies.append(float(row.decision_ms) - float(row.event_ms))
            if row.grounded is not None:
                grounded_reviewed += 1
                grounded_true += int(row.grounded)

        if (
            row.expected_action in SPEECH_ACTIONS
            and row.predicted_action == row.expected_action
            and row.decision_ms is not None
            and row.deadline_ms is not None
        ):
            eligible_deadlines += 1
            if row.decision_ms - row.event_ms <= row.deadline_ms:
                on_time += 1
            else:
                late += 1

    return {
        "schema": 1,
        "samples": total,
        "accuracy": _rate(correct, total),
        "macro_recall": _rate(sum(recalls), len(recalls)),
        "macro_f1": _rate(sum(f1s), len(f1s)),
        "actions": per_action,
        "confusion": confusion,
        "silence": {
            "precision": _rate(true_silence, predicted_silence),
            "recall": _rate(true_silence, expected_silence),
            "expected": expected_silence,
            "predicted": predicted_silence,
        },
        "negative_controls": {
            "count": len(negative_controls),
            "false_speech": false_speech,
            "false_speech_rate": _rate(false_speech, len(negative_controls)),
        },
        "speech_grounding": {
            "reviewed": grounded_reviewed,
            "grounded": grounded_true,
            "rate": _rate(grounded_true, grounded_reviewed),
        },
        "speech_timing": {
            "n": len(speech_latencies),
            "missing_timestamps": missing_speech_timestamps,
            "p50_ms": _percentile(speech_latencies, 0.50),
            "p95_ms": _percentile(speech_latencies, 0.95),
            "max_ms": round(max(speech_latencies), 3) if speech_latencies else None,
            "deadline_n": eligible_deadlines,
            "on_time": on_time,
            "late": late,
            "on_time_rate": _rate(on_time, eligible_deadlines),
        },
        "note": (
            "Offline aggregate evaluator only; no audio, video, transcript, "
            "viewer ID, or runtime action is stored."
        ),
    }
