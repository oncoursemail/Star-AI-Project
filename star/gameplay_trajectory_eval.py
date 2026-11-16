"""Offline evaluation of exploration-first, long-horizon game-agent episodes.

Only redacted event metadata and adjudicated outcomes are accepted. This module
does not connect to a game engine, editor, controller, filesystem, or agent.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import ceil, isfinite
from statistics import median
import re
from typing import cast

SPLITS = ("train", "validation", "holdout")
EVENT_KINDS = ("observe", "edit", "act", "verify", "verify_final", "recover")
_ACTION_KINDS = frozenset(("edit", "act"))
_VERIFY_KINDS = frozenset(("verify", "verify_final"))
MAX_EPISODES = 5_000
MAX_EVENTS = 100_000
MAX_EVENTS_PER_EPISODE = 10_000
_MAX_INDEX = 1_000_000_000
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\\Z")


@dataclass(frozen=True, slots=True)
class Event:
    """One redacted event from a game-agent trace.

    target_id is an opaque, episode-local reference, never a scene name or
    player identifier. at_ms and latency_ms use the same monotonic clock.
    """

    index: int
    kind: str
    at_ms: float
    target_id: str | None = None
    valid_action: bool | None = None
    passed: bool | None = None
    latency_ms: float | None = None


@dataclass(frozen=True, slots=True)
class Episode:
    """One attempt on a fixed task/case/seed.

    case_id must identify the same task variant and seed across attempts.
    attempt_index defines the order used by empirical pass@k/all@k reporting.
    """

    episode_id: str
    task_id: str
    case_id: str
    attempt_index: int
    split: str
    events: Iterable[Event]
    goal_reached: bool | None = None
    save_reload_verified: bool | None = None
    requires_save_reload: bool = False


@dataclass(frozen=True, slots=True)
class _Record:
    task_id: str
    case_id: str
    attempt_index: int
    split: str
    goal_reached: bool | None
    final_verified: bool | None
    accepted: bool
    save_reload_required: bool
    save_reload_verified: bool | None
    action_count: int
    invalid_actions: int
    target_actions: int
    observed_target_actions: int
    verification_checks: int
    verification_passes: int
    recovery_events: int
    latency_ms: tuple[float, ...]


def _opaque_id(value: object, field: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError(f"{field} must be a bounded opaque identifier")
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


def _optional_bool(value: object, field: str) -> bool | None:
    if value is not None and type(value) is not bool:
        raise ValueError(f"{field} must be true, false, or None")
    return cast(bool | None, value)


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
        "max": round(max(values), 3) if values else None,
    }


def _repeatability(records: list[_Record]) -> dict:
    cases: dict[tuple[str, str], list[_Record]] = {}
    for record in records:
        cases.setdefault((record.task_id, record.case_id), []).append(record)

    report: dict[str, dict] = {}
    for k in (1, 3, 5):
        eligible = [
            sorted(items, key=lambda item: item.attempt_index)
            for items in cases.values()
            if len(items) >= k
        ]
        passed = sum(any(item.accepted for item in items[:k]) for items in eligible)
        all_passed = sum(all(item.accepted for item in items[:k]) for items in eligible)
        report[str(k)] = {
            "eligible_cases": len(eligible),
            "cases_with_at_least_one_acceptance": passed,
            "empirical_pass_at_k": _rate(passed, len(eligible)),
            "cases_with_all_first_k_accepted": all_passed,
            "empirical_all_at_k": _rate(all_passed, len(eligible)),
        }
    return report


def _summary(records: list[_Record], *, include_repeatability: bool) -> dict:
    known_goals = [item.goal_reached for item in records if item.goal_reached is not None]
    accepted = sum(item.accepted for item in records)
    final_passed = sum(item.final_verified is True for item in records)
    final_failed = sum(item.final_verified is False for item in records)
    final_missing = len(records) - final_passed - final_failed

    actions = sum(item.action_count for item in records)
    invalid = sum(item.invalid_actions for item in records)
    target_actions = sum(item.target_actions for item in records)
    observed_actions = sum(item.observed_target_actions for item in records)
    checks = sum(item.verification_checks for item in records)
    check_passes = sum(item.verification_passes for item in records)
    recoveries = sum(item.recovery_events for item in records)
    recovery_episodes = sum(item.recovery_events > 0 for item in records)

    required_reload = [item for item in records if item.save_reload_required]
    reload_passed = sum(item.save_reload_verified is True for item in required_reload)
    reload_failed = sum(item.save_reload_verified is False for item in required_reload)

    latencies = [value for item in records for value in item.latency_ms]
    result = {
        "episodes": len(records),
        "cases": len({(item.task_id, item.case_id) for item in records}),
        "goal_reached": {
            "known": len(known_goals),
            "true": sum(value is True for value in known_goals),
            "false": sum(value is False for value in known_goals),
            "missing": len(records) - len(known_goals),
            "rate": _rate(sum(value is True for value in known_goals), len(known_goals)),
        },
        "final_verification": {
            "passed": final_passed,
            "failed": final_failed,
            "missing": final_missing,
        },
        "verified_acceptance": {
            "accepted": accepted,
            "not_accepted": len(records) - accepted,
            "rate": _rate(accepted, len(records)),
        },
        "save_reload": {
            "required": len(required_reload),
            "passed": reload_passed,
            "failed": reload_failed,
            "missing": len(required_reload) - reload_passed - reload_failed,
        },
        "actions": {
            "total": actions,
            "invalid": invalid,
            "invalid_rate": _rate(invalid, actions),
            "targeted": target_actions,
            "target_observed_before_action": observed_actions,
            "target_observation_rate": _rate(observed_actions, target_actions),
            "target_not_observed_before_action": target_actions - observed_actions,
        },
        "subgoal_verification": {
            "checks": checks,
            "passed": check_passes,
            "failed": checks - check_passes,
            "pass_rate": _rate(check_passes, checks),
        },
        "recovery": {
            "events": recoveries,
            "episodes_with_recovery": recovery_episodes,
            "episode_rate": _rate(recovery_episodes, len(records)),
        },
        "event_latency_ms": _distribution(latencies),
    }
    if include_repeatability:
        result["repeatability"] = _repeatability(records)
    return result


def evaluate(episodes: Iterable[Episode]) -> dict:
    """Evaluate exploration, action validity, recovery, and verified completion.

    pass@k is empirical over the first k ordered attempts for the same
    task/case, not an independence-based estimate. Train, validation, and
    holdout results are always reported separately.
    """
    records: list[_Record] = []
    episode_ids: set[str] = set()
    attempt_keys: set[tuple[str, str, str, int]] = set()
    total_events = 0

    for episode in episodes:
        if len(records) >= MAX_EPISODES:
            raise ValueError(f"At most {MAX_EPISODES} episodes are allowed")
        if not isinstance(episode, Episode):
            raise ValueError("Every item must be an Episode")

        episode_id = _opaque_id(episode.episode_id, "episode_id")
        task_id = _opaque_id(episode.task_id, "task_id")
        case_id = _opaque_id(episode.case_id, "case_id")
        if episode_id in episode_ids:
            raise ValueError("episode_id values must be unique")
        episode_ids.add(episode_id)

        if type(episode.attempt_index) is not int or not 0 <= episode.attempt_index <= _MAX_INDEX:
            raise ValueError("attempt_index must be a bounded nonnegative integer")
        if episode.split not in SPLITS:
            raise ValueError("split must be train, validation, or holdout")
        goal_reached = _optional_bool(episode.goal_reached, "goal_reached")
        save_reload_verified = _optional_bool(
            episode.save_reload_verified, "save_reload_verified"
        )
        if type(episode.requires_save_reload) is not bool:
            raise ValueError("requires_save_reload must be a boolean")

        attempt_key = (episode.split, task_id, case_id, episode.attempt_index)
        if attempt_key in attempt_keys:
            raise ValueError("attempt_index must be unique within each task/case/split")
        attempt_keys.add(attempt_key)

        observed_targets: set[str] = set()
        previous_index = -1
        previous_time = -1.0
        final_verified: bool | None = None
        final_seen = False
        action_count = invalid_actions = 0
        target_actions = observed_target_actions = 0
        verification_checks = verification_passes = recovery_events = 0
        latencies: list[float] = []
        event_count = 0

        for event in episode.events:
            if event_count >= MAX_EVENTS_PER_EPISODE:
                raise ValueError(
                    f"At most {MAX_EVENTS_PER_EPISODE} events are allowed per episode"
                )
            if total_events >= MAX_EVENTS:
                raise ValueError(f"At most {MAX_EVENTS} total events are allowed")
            if not isinstance(event, Event):
                raise ValueError("Every event must be an Event")

            if type(event.index) is not int or not 0 <= event.index <= _MAX_INDEX:
                raise ValueError("event index must be a bounded nonnegative integer")
            if event.index <= previous_index:
                raise ValueError("event indices must be strictly increasing")
            at_ms = _number(event.at_ms, "at_ms")
            assert at_ms is not None
            if at_ms < previous_time:
                raise ValueError("event timestamps must be monotonic")
            if not isinstance(event.kind, str) or event.kind not in EVENT_KINDS:
                raise ValueError("unknown event kind")

            target_id = None
            if event.kind in ("observe", "edit", "act"):
                target_id = _opaque_id(event.target_id, "target_id")
            elif event.target_id is not None:
                target_id = _opaque_id(event.target_id, "target_id")

            if event.kind in _ACTION_KINDS:
                if type(event.valid_action) is not bool:
                    raise ValueError("edit and act events require valid_action")
            elif event.valid_action is not None:
                raise ValueError("valid_action only applies to edit and act events")

            if event.kind in _VERIFY_KINDS:
                if type(event.passed) is not bool:
                    raise ValueError("verification events require passed")
            elif event.passed is not None:
                raise ValueError("passed only applies to verification events")

            latency = _number(event.latency_ms, "latency_ms", optional=True)
            if latency is not None:
                latencies.append(latency)

            if event.kind == "observe":
                assert target_id is not None
                observed_targets.add(target_id)
            elif event.kind in _ACTION_KINDS:
                if final_seen:
                    raise ValueError("no edit or act may follow final verification")
                assert target_id is not None
                action_count += 1
                target_actions += 1
                if event.valid_action is False:
                    invalid_actions += 1
                if target_id in observed_targets:
                    observed_target_actions += 1
            elif event.kind == "verify":
                verification_checks += 1
                verification_passes += event.passed is True
            elif event.kind == "verify_final":
                if final_seen:
                    raise ValueError("an episode may contain only one final verification")
                final_seen = True
                final_verified = event.passed
            elif event.kind == "recover":
                recovery_events += 1

            previous_index = event.index
            previous_time = at_ms
            event_count += 1
            total_events += 1

        accepted = (
            goal_reached is True
            and final_verified is True
            and (
                not episode.requires_save_reload
                or save_reload_verified is True
            )
        )
        records.append(_Record(
            task_id=task_id,
            case_id=case_id,
            attempt_index=episode.attempt_index,
            split=episode.split,
            goal_reached=goal_reached,
            final_verified=final_verified,
            accepted=accepted,
            save_reload_required=episode.requires_save_reload,
            save_reload_verified=save_reload_verified,
            action_count=action_count,
            invalid_actions=invalid_actions,
            target_actions=target_actions,
            observed_target_actions=observed_target_actions,
            verification_checks=verification_checks,
            verification_passes=verification_passes,
            recovery_events=recovery_events,
            latency_ms=tuple(latencies),
        ))

    return {
        "schema": 1,
        "episodes": len(records),
        "overall": _summary(records, include_repeatability=False),
        "by_split": {
            split: _summary(
                [item for item in records if item.split == split],
                include_repeatability=True,
            )
            for split in SPLITS
        },
        "note": (
            "Offline metadata evaluator only. No game, editor, controller, "
            "screen, scene name, player identity, or agent runtime is accessed. "
            "Acceptance requires goal reached, passing final verification, and "
            "save/reload verification when the task requires it. No composite "
            "score or automatic promotion decision is produced."
        ),
    }
