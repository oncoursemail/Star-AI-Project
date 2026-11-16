"""Offline evaluation for intent-aware, full-duplex voice turn control.

This complements the frame-level VAD/endpointer in star.voice.turn. It scores
the higher-level policy that decides whether to respond, backchannel, yield
the floor, hold for more evidence, or ignore non-addressed speech.

Only synthetic case IDs and adjudicated metadata are accepted. This module
does not process audio, identify speakers, access devices, or control playback.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import ceil, isfinite
from typing import cast

ACTIONS = ("respond", "backchannel", "yield", "hold", "ignore")
INTENTS = (
    "addressed_request",
    "addressed_interruption",
    "backchannel",
    "side_conversation",
    "floor_handoff",
    "uncertain",
)
NON_TAKEOVER_INTENTS = frozenset(("backchannel", "side_conversation", "uncertain"))
MAX_OBSERVATIONS = 100_000


@dataclass(frozen=True, slots=True)
class Observation:
    """One labelled policy decision on a single monotonic clock.

    event_ms and decision_ms are absolute milliseconds on the same monotonic
    clock. deadline_ms is a duration from event_ms. Addressee fields are
    adjudicated booleans, not speaker IDs. followed_through records whether a
    correctly selected yield was followed by the required next-turn handling.
    """

    sample_id: str
    intent: str
    assistant_speaking: bool
    expected_action: str
    predicted_action: str
    event_ms: float
    decision_ms: float | None = None
    deadline_ms: float | None = None
    expected_addressee: bool | None = None
    predicted_addressee: bool | None = None
    followed_through: bool | None = None


def _number(value: object, field: str, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if type(value) not in (int, float):
        raise ValueError(f"{field} must be a finite non-negative number")
    number = cast(int | float, value)
    if not isfinite(number) or number < 0:
        raise ValueError(f"{field} must be a finite non-negative number")
    return float(number)


def _rate(numerator: int | float, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 6)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[ceil(percentile * len(ordered)) - 1], 3)


def _validate(rows: list[Observation]) -> None:
    ids: set[str] = set()
    for row in rows:
        if not isinstance(row, Observation):
            raise ValueError("Every row must be an Observation")
        if (
            not isinstance(row.sample_id, str)
            or not row.sample_id.strip()
            or len(row.sample_id) > 128
            or row.sample_id in ids
        ):
            raise ValueError("Sample IDs must be unique, non-empty text of at most 128 characters")
        ids.add(row.sample_id)

        if row.intent not in INTENTS:
            raise ValueError("Unknown conversational intent")
        if row.expected_action not in ACTIONS or row.predicted_action not in ACTIONS:
            raise ValueError("Unknown expected or predicted action")
        if type(row.assistant_speaking) is not bool:
            raise ValueError("assistant_speaking must be a boolean")

        event_ms = _number(row.event_ms, "event_ms")
        assert event_ms is not None
        decision_ms = _number(row.decision_ms, "decision_ms", optional=True)
        _number(row.deadline_ms, "deadline_ms", optional=True)
        if decision_ms is not None and decision_ms < event_ms:
            raise ValueError("decision_ms cannot precede event_ms")

        for field, value in (
            ("expected_addressee", row.expected_addressee),
            ("predicted_addressee", row.predicted_addressee),
            ("followed_through", row.followed_through),
        ):
            if value is not None and type(value) is not bool:
                raise ValueError(f"{field} must be true, false, or unknown")

        if row.followed_through is not None and row.predicted_action != "yield":
            raise ValueError("followed_through is only applicable after a predicted yield")


def _action_metrics(confusion: dict[str, dict[str, int]]) -> tuple[dict[str, dict], list[float]]:
    per_action: dict[str, dict] = {}
    f1s: list[float] = []
    for action in ACTIONS:
        true_positive = confusion[action][action]
        false_positive = sum(
            confusion[expected][action] for expected in ACTIONS if expected != action
        )
        false_negative = sum(
            confusion[action][predicted] for predicted in ACTIONS if predicted != action
        )
        support = true_positive + false_negative
        precision = _rate(true_positive, true_positive + false_positive)
        recall = _rate(true_positive, support)
        f1 = (
            None
            if support == 0
            else round(
                (2 * true_positive)
                / (2 * true_positive + false_positive + false_negative),
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
        if f1 is not None:
            f1s.append(f1)
    return per_action, f1s


def evaluate(observations: Iterable[Observation]) -> dict:
    """Return disaggregated action, intent, addressee, interruption and timing metrics.

    There is deliberately no single 'human-likeness' score. Good turn control
    must not hide false interruptions, missed takeovers, wrong addressees,
    failed follow-through, or missing timing evidence.
    """
    rows: list[Observation] = []
    for row in observations:
        if len(rows) >= MAX_OBSERVATIONS:
            raise ValueError(f"At most {MAX_OBSERVATIONS} observations are allowed")
        rows.append(row)
    _validate(rows)

    confusion = {expected: {predicted: 0 for predicted in ACTIONS} for expected in ACTIONS}
    for row in rows:
        confusion[row.expected_action][row.predicted_action] += 1

    total = len(rows)
    correct = sum(confusion[action][action] for action in ACTIONS)
    per_action, f1s = _action_metrics(confusion)
    recalls = [
        metrics["recall"]
        for metrics in per_action.values()
        if metrics["recall"] is not None
    ]

    by_intent: dict[str, dict] = {}
    for intent in INTENTS:
        subset = [row for row in rows if row.intent == intent]
        matched = sum(row.expected_action == row.predicted_action for row in subset)
        by_intent[intent] = {
            "samples": len(subset),
            "correct": matched,
            "accuracy": _rate(matched, len(subset)),
        }

    by_playback_state: dict[str, dict] = {}
    for speaking, label in ((True, "assistant_speaking"), (False, "assistant_listening")):
        subset = [row for row in rows if row.assistant_speaking is speaking]
        matched = sum(row.expected_action == row.predicted_action for row in subset)
        by_playback_state[label] = {
            "samples": len(subset),
            "correct": matched,
            "accuracy": _rate(matched, len(subset)),
        }

    expected_yields = [row for row in rows if row.expected_action == "yield"]
    missed_yields = sum(row.predicted_action != "yield" for row in expected_yields)
    non_takeovers = [row for row in rows if row.intent in NON_TAKEOVER_INTENTS]
    false_yields = sum(row.predicted_action == "yield" for row in non_takeovers)

    correct_yields = [
        row for row in rows
        if row.expected_action == "yield" and row.predicted_action == "yield"
    ]
    reviewed_follow_through = [
        row for row in correct_yields if row.followed_through is not None
    ]
    completed_follow_through = sum(
        row.followed_through is True for row in reviewed_follow_through
    )

    addressee_rows = [
        row for row in rows
        if row.expected_addressee is not None and row.predicted_addressee is not None
    ]
    addressee_tp = sum(
        row.expected_addressee is True and row.predicted_addressee is True
        for row in addressee_rows
    )
    addressee_tn = sum(
        row.expected_addressee is False and row.predicted_addressee is False
        for row in addressee_rows
    )
    addressee_fp = sum(
        row.expected_addressee is False and row.predicted_addressee is True
        for row in addressee_rows
    )
    addressee_fn = sum(
        row.expected_addressee is True and row.predicted_addressee is False
        for row in addressee_rows
    )

    latencies: list[float] = []
    deadline_latencies: list[tuple[float, float]] = []
    for row in rows:
        if row.decision_ms is None:
            continue
        latency = float(row.decision_ms) - float(row.event_ms)
        latencies.append(latency)
        if row.deadline_ms is not None:
            deadline_latencies.append((latency, float(row.deadline_ms)))
    on_time = sum(latency <= deadline for latency, deadline in deadline_latencies)

    return {
        "schema": 1,
        "samples": total,
        "accuracy": _rate(correct, total),
        "macro_recall": _rate(sum(recalls), len(recalls)),
        "macro_f1": _rate(sum(f1s), len(f1s)),
        "actions": per_action,
        "confusion": confusion,
        "by_intent": by_intent,
        "by_playback_state": by_playback_state,
        "interruption": {
            "expected_yields": len(expected_yields),
            "missed_yields": missed_yields,
            "missed_yield_rate": _rate(missed_yields, len(expected_yields)),
            "non_takeover_events": len(non_takeovers),
            "false_yields": false_yields,
            "false_yield_rate": _rate(false_yields, len(non_takeovers)),
        },
        "follow_through": {
            "correct_yields": len(correct_yields),
            "reviewed": len(reviewed_follow_through),
            "completed": completed_follow_through,
            "missing": len(correct_yields) - len(reviewed_follow_through),
            "rate": _rate(completed_follow_through, len(reviewed_follow_through)),
        },
        "addressee": {
            "reviewed": len(addressee_rows),
            "missing": total - len(addressee_rows),
            "tp": addressee_tp,
            "tn": addressee_tn,
            "fp": addressee_fp,
            "fn": addressee_fn,
            "accuracy": _rate(addressee_tp + addressee_tn, len(addressee_rows)),
            "false_target_rate": _rate(addressee_fp, addressee_fp + addressee_tn),
            "missed_target_rate": _rate(addressee_fn, addressee_fn + addressee_tp),
        },
        "decision_timing": {
            "n": len(latencies),
            "missing_timestamps": total - len(latencies),
            "p50_ms": _percentile(latencies, 0.50),
            "p95_ms": _percentile(latencies, 0.95),
            "max_ms": round(max(latencies), 3) if latencies else None,
            "deadline_n": len(deadline_latencies),
            "on_time": on_time,
            "late": len(deadline_latencies) - on_time,
            "on_time_rate": _rate(on_time, len(deadline_latencies)),
        },
        "note": (
            "Offline aggregate evaluator only. No audio, video, transcript, speaker ID, "
            "viewer ID, or runtime action is stored."
        ),
    }
