"""Content-free, holdout-gated evaluation of STAR's multiparty room decisions.

The host supplies opaque scenario labels and independently scored outcomes. This module
does not capture audio, transcribe speech, identify people, call models, control playback,
or authorize speech. A pass is a replay-evaluation result, never an automatic promotion.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import math
import re
from typing import Sequence, cast

from .room import RoomAction


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_DOMAIN = b"star.multiparty-room-outcome.v1\x00"
_MAX_CASES = 512
_MAX_AGE_S = 30 * 86400
_MAX_MS = 300_000
_MAX_PARTICIPANTS = 16
_CATEGORIES = frozenset({
    "explicit_direct",
    "implicit_direct",
    "side_conversation",
    "backchannel",
    "human_resolution",
    "urgent_barge_in",
    "game_event",
    "ambiguous",
})
_RESPONSE_ACTIONS = frozenset({
    RoomAction.RESPOND,
    RoomAction.QUEUE,
    RoomAction.INTERRUPT,
})
_SILENCE_ACTIONS = frozenset({
    RoomAction.IGNORE,
    RoomAction.CONTINUE,
    RoomAction.WAIT,
})


def _identifier(value: object, label: str) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise ValueError(f"{label} must be a bounded opaque identifier")
    return value


def _digest(value: object, label: str) -> str:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _finite_rate(value: object, label: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite number in 0..1")
    number = float(cast(int | float, value))
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"{label} must be a finite number in 0..1")
    return number


def _rate(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 6)


def _nearest_rank(values: list[int], quantile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(quantile * len(ordered)))
    return ordered[rank - 1]


@dataclass(frozen=True)
class RoomReplayCase:
    """A preregistered content-free scenario label."""

    case_id: str
    scenario_sha256: str
    split: str
    cue_category: str
    participant_count: int
    expected_response: bool
    expected_stop: bool = False
    expected_interrupt: bool = False
    matched_pair_id: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.case_id, "case_id")
        _digest(self.scenario_sha256, "scenario_sha256")
        if self.matched_pair_id is not None:
            _identifier(self.matched_pair_id, "matched_pair_id")
        if type(self.split) is not str or self.split not in {"development", "holdout"}:
            raise ValueError("split must be development or holdout")
        if type(self.cue_category) is not str or self.cue_category not in _CATEGORIES:
            raise ValueError("cue_category is unsupported")
        if (
            type(self.participant_count) is not int
            or not 2 <= self.participant_count <= _MAX_PARTICIPANTS
        ):
            raise ValueError("participant_count must be an integer in 2..16")
        for name in ("expected_response", "expected_stop", "expected_interrupt"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be boolean")

        if self.cue_category in {"explicit_direct", "implicit_direct"} and not self.expected_response:
            raise ValueError("direct-address cases must expect a response")
        if self.cue_category in {"side_conversation", "backchannel", "ambiguous"} and self.expected_response:
            raise ValueError("non-directed/ambiguous cases must not expect a response")
        if self.cue_category == "human_resolution":
            if not self.expected_stop or self.expected_response or self.expected_interrupt:
                raise ValueError("human_resolution must expect STOP and no new response")
        elif self.expected_stop:
            raise ValueError("expected_stop is only valid for human_resolution")
        if self.cue_category == "urgent_barge_in":
            if not self.expected_response or not self.expected_interrupt:
                raise ValueError("urgent_barge_in must expect a response and an interrupt")
        elif self.expected_interrupt:
            raise ValueError("expected_interrupt is only valid for urgent_barge_in")


@dataclass(frozen=True)
class RoomReplayOutcome:
    """One host-observed policy/playback outcome, with no raw content."""

    case_id: str
    actual_action: RoomAction
    audible_response_started: bool
    response_latency_ms: int | None
    answer_correct: bool | None
    response_appropriate: bool | None
    evidence_sha256: str
    observed_unix_s: int

    def __post_init__(self) -> None:
        _identifier(self.case_id, "case_id")
        if not isinstance(self.actual_action, RoomAction):
            raise ValueError("actual_action must be a RoomAction")
        if type(self.audible_response_started) is not bool:
            raise ValueError("audible_response_started must be boolean")
        _digest(self.evidence_sha256, "evidence_sha256")
        if type(self.observed_unix_s) is not int or not 0 < self.observed_unix_s <= 10**11:
            raise ValueError("observed_unix_s must be a valid positive Unix timestamp")

        for name in ("answer_correct", "response_appropriate"):
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise ValueError(f"{name} must be boolean or None")

        if self.audible_response_started:
            if self.actual_action not in _RESPONSE_ACTIONS:
                raise ValueError("an audible response requires RESPOND, QUEUE, or INTERRUPT")
            if (
                type(self.response_latency_ms) is not int
                or not 0 <= self.response_latency_ms <= _MAX_MS
            ):
                raise ValueError("response_latency_ms must be an integer in 0..300000")
        elif any(
            value is not None
            for value in (self.response_latency_ms, self.answer_correct, self.response_appropriate)
        ):
            raise ValueError("response metrics require an audible response")

    def canonical_bytes(self) -> bytes:
        """Canonical, domain-separated receipt payload; no raw media or transcript."""
        payload = {
            "case_id": self.case_id,
            "actual_action": self.actual_action.value,
            "audible_response_started": self.audible_response_started,
            "response_latency_ms": self.response_latency_ms,
            "answer_correct": self.answer_correct,
            "response_appropriate": self.response_appropriate,
            "evidence_sha256": self.evidence_sha256,
            "observed_unix_s": self.observed_unix_s,
        }
        return _DOMAIN + json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")


@dataclass(frozen=True)
class SignedRoomReplayOutcome:
    outcome: RoomReplayOutcome
    receipt: str

    def __post_init__(self) -> None:
        if type(self.outcome) is not RoomReplayOutcome:
            raise TypeError("outcome must be RoomReplayOutcome")
        _digest(self.receipt, "receipt")


def sign_room_replay_outcome(
    outcome: RoomReplayOutcome,
    *,
    validation_key: bytes,
) -> SignedRoomReplayOutcome:
    """Host-only helper. Never expose the validation key as an LLM tool."""
    if type(outcome) is not RoomReplayOutcome:
        raise TypeError("outcome must be RoomReplayOutcome")
    if type(validation_key) is not bytes or len(validation_key) < 32:
        raise ValueError("requires an independent host-owned validation key")
    receipt = hmac.new(validation_key, outcome.canonical_bytes(), hashlib.sha256).hexdigest()
    return SignedRoomReplayOutcome(outcome=outcome, receipt=receipt)


def roster_digest(cases: Sequence[RoomReplayCase]) -> str:
    """Seal the scenario roster and labels before a policy is evaluated."""
    if type(cases) not in (tuple, list) or not 1 <= len(cases) <= _MAX_CASES:
        raise ValueError("provide 1..512 preregistered room replay cases")
    if any(type(case) is not RoomReplayCase for case in cases):
        raise TypeError("all cases must be RoomReplayCase")
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("case IDs must be unique")
    scenario_splits: dict[str, str] = {}
    pair_groups: dict[str, list[RoomReplayCase]] = {}
    for case in cases:
        previous_split = scenario_splits.setdefault(case.scenario_sha256, case.split)
        if previous_split != case.split:
            raise ValueError("scenario hashes must be disjoint across development and holdout")
        if case.matched_pair_id is not None:
            pair_groups.setdefault(case.matched_pair_id, []).append(case)
    for pair_id, pair in pair_groups.items():
        if (
            len(pair) != 2
            or {case.cue_category for case in pair} != {"explicit_direct", "implicit_direct"}
            or len({case.split for case in pair}) != 1
            or len({case.scenario_sha256 for case in pair}) != 2
        ):
            raise ValueError(f"matched pair {pair_id} must contain one explicit and one implicit case in the same split")
    rows = sorted(
        (
            case.case_id,
            case.scenario_sha256,
            case.split,
            case.cue_category,
            case.participant_count,
            case.expected_response,
            case.expected_stop,
            case.expected_interrupt,
            case.matched_pair_id,
        )
        for case in cases
    )
    payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(b"star.multiparty-room-roster.v1\x00" + payload).hexdigest()


@dataclass(frozen=True)
class RoomReplayLimits:
    """Operator-set holdout gates; no automatic runtime or skill promotion."""

    min_holdout_cases: int = 40
    min_cases_per_category: int = 4
    min_answer_labels: int = 20
    min_appropriateness_labels: int = 20
    min_latency_samples: int = 20
    max_validation_age_s: int = 7 * 86400
    required_categories: tuple[str, ...] = (
        "explicit_direct",
        "side_conversation",
        "human_resolution",
        "urgent_barge_in",
    )
    min_direct_response_delivery_rate: float = 0.90
    max_unwanted_response_decision_rate: float = 0.05
    min_silence_preservation_rate: float = 0.95
    min_human_resolution_stop_rate: float = 0.95
    max_false_stop_rate: float = 0.01
    min_urgent_interrupt_recall: float = 0.90
    max_false_interrupt_rate: float = 0.02
    min_answer_accuracy: float = 0.85
    min_response_appropriateness: float = 0.85
    max_response_latency_p95_ms: int = 2500

    def __post_init__(self) -> None:
        for name in (
            "min_holdout_cases",
            "min_cases_per_category",
            "min_answer_labels",
            "min_appropriateness_labels",
            "min_latency_samples",
        ):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= _MAX_CASES:
                raise ValueError(f"{name} must be an integer in 1..512")
        if (
            type(self.max_validation_age_s) is not int
            or not 1 <= self.max_validation_age_s <= _MAX_AGE_S
        ):
            raise ValueError("max_validation_age_s must be in 1..30 days")
        if (
            type(self.max_response_latency_p95_ms) is not int
            or not 1 <= self.max_response_latency_p95_ms <= _MAX_MS
        ):
            raise ValueError("max_response_latency_p95_ms must be in 1..300000")
        if (
            type(self.required_categories) is not tuple
            or not 1 <= len(self.required_categories) <= len(_CATEGORIES)
            or any(type(item) is not str or item not in _CATEGORIES for item in self.required_categories)
            or len(set(self.required_categories)) != len(self.required_categories)
        ):
            raise ValueError("required_categories must be a unique bounded tuple")
        for name in (
            "min_direct_response_delivery_rate",
            "max_unwanted_response_decision_rate",
            "min_silence_preservation_rate",
            "min_human_resolution_stop_rate",
            "max_false_stop_rate",
            "min_urgent_interrupt_recall",
            "max_false_interrupt_rate",
            "min_answer_accuracy",
            "min_response_appropriateness",
        ):
            _finite_rate(getattr(self, name), name)


def _summarize(
    cases: Sequence[RoomReplayCase],
    outcomes: dict[str, RoomReplayOutcome],
) -> dict[str, object]:
    rows = [(case, outcomes[case.case_id]) for case in cases]
    expected_response = [(case, outcome) for case, outcome in rows if case.expected_response]
    no_response_expected = [(case, outcome) for case, outcome in rows if not case.expected_response]
    silence_cases = [
        (case, outcome)
        for case, outcome in rows
        if case.cue_category in {"side_conversation", "backchannel", "ambiguous"}
        and not case.expected_response
    ]
    expected_stop = [(case, outcome) for case, outcome in rows if case.expected_stop]
    no_stop_expected = [(case, outcome) for case, outcome in rows if not case.expected_stop]
    expected_interrupt = [(case, outcome) for case, outcome in rows if case.expected_interrupt]
    no_interrupt_expected = [(case, outcome) for case, outcome in rows if not case.expected_interrupt]

    answer_labels = [
        outcome.answer_correct
        for _, outcome in rows
        if outcome.audible_response_started and outcome.answer_correct is not None
    ]
    appropriateness_labels = [
        outcome.response_appropriate
        for _, outcome in rows
        if outcome.audible_response_started and outcome.response_appropriate is not None
    ]
    latencies = [
        outcome.response_latency_ms
        for _, outcome in rows
        if outcome.audible_response_started and isinstance(outcome.response_latency_ms, int)
    ]

    category_counts = {
        category: sum(1 for case, _ in rows if case.cue_category == category)
        for category in sorted(_CATEGORIES)
    }
    participant_buckets = {
        "2-3": sum(1 for case, _ in rows if 2 <= case.participant_count <= 3),
        "4-8": sum(1 for case, _ in rows if 4 <= case.participant_count <= 8),
        "9-16": sum(1 for case, _ in rows if 9 <= case.participant_count <= 16),
    }

    return {
        "case_count": len(rows),
        "expected_response_cases": len(expected_response),
        "audible_response_count": len(latencies),
        "direct_response_delivery_rate": _rate(
            sum(1 for _, outcome in expected_response if outcome.audible_response_started),
            len(expected_response),
        ),
        "unwanted_response_decision_rate": _rate(
            sum(1 for _, outcome in no_response_expected if outcome.actual_action in _RESPONSE_ACTIONS),
            len(no_response_expected),
        ),
        "silence_preservation_rate": _rate(
            sum(1 for _, outcome in silence_cases if outcome.actual_action in _SILENCE_ACTIONS),
            len(silence_cases),
        ),
        "human_resolution_stop_rate": _rate(
            sum(1 for _, outcome in expected_stop if outcome.actual_action is RoomAction.STOP),
            len(expected_stop),
        ),
        "false_stop_rate": _rate(
            sum(1 for _, outcome in no_stop_expected if outcome.actual_action is RoomAction.STOP),
            len(no_stop_expected),
        ),
        "urgent_interrupt_recall": _rate(
            sum(1 for _, outcome in expected_interrupt if outcome.actual_action is RoomAction.INTERRUPT),
            len(expected_interrupt),
        ),
        "false_interrupt_rate": _rate(
            sum(1 for _, outcome in no_interrupt_expected if outcome.actual_action is RoomAction.INTERRUPT),
            len(no_interrupt_expected),
        ),
        "answer_accuracy": _rate(sum(1 for value in answer_labels if value), len(answer_labels)),
        "answer_label_count": len(answer_labels),
        "response_appropriateness": _rate(
            sum(1 for value in appropriateness_labels if value),
            len(appropriateness_labels),
        ),
        "appropriateness_label_count": len(appropriateness_labels),
        "response_latency_ms_p50": _nearest_rank(latencies, 0.50),
        "response_latency_ms_p95": _nearest_rank(latencies, 0.95),
        "latency_sample_count": len(latencies),
        "category_counts": category_counts,
        "participant_count_buckets": participant_buckets,
    }


def evaluate_multiparty_replay(
    cases: Sequence[RoomReplayCase],
    signed_outcomes: Sequence[SignedRoomReplayOutcome],
    *,
    validation_key: bytes,
    expected_roster_sha256: str,
    now_unix_s: int,
    limits: RoomReplayLimits | None = None,
) -> dict[str, object]:
    """Evaluate one room-policy revision on a sealed, independently labeled replay.

    Only holdout cases drive acceptance. Development cases are reported separately.
    Every outcome must be signed by the host and correspond to exactly one roster case.
    A PASS never changes the live room policy or promotes a skill.
    """
    if type(validation_key) is not bytes or len(validation_key) < 32:
        raise ValueError("requires an independent host-owned validation key")
    if type(now_unix_s) is not int or not 0 < now_unix_s <= 10**11:
        raise ValueError("now_unix_s must be a valid positive Unix timestamp")
    if limits is None:
        limits = RoomReplayLimits()
    if type(limits) is not RoomReplayLimits:
        raise TypeError("limits must be RoomReplayLimits")

    roster_sha = roster_digest(cases)
    _digest(expected_roster_sha256, "expected_roster_sha256")
    if not hmac.compare_digest(roster_sha, expected_roster_sha256):
        raise ValueError("scenario roster digest does not match the sealed evaluation")

    rows = tuple(cases)
    if type(signed_outcomes) not in (tuple, list) or len(signed_outcomes) != len(rows):
        raise ValueError("provide exactly one signed outcome per preregistered case")

    case_ids = {case.case_id for case in rows}
    outcomes: dict[str, RoomReplayOutcome] = {}
    for signed in signed_outcomes:
        if type(signed) is not SignedRoomReplayOutcome:
            raise TypeError("signed_outcomes must contain SignedRoomReplayOutcome values")
        outcome = signed.outcome
        if outcome.case_id not in case_ids:
            raise ValueError("outcome references a case outside the sealed roster")
        expected_receipt = hmac.new(
            validation_key,
            outcome.canonical_bytes(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_receipt, signed.receipt):
            raise ValueError("outcome receipt is invalid")
        age_s = now_unix_s - outcome.observed_unix_s
        if age_s < -60:
            raise ValueError("outcome timestamp is too far in the future")
        if age_s > limits.max_validation_age_s:
            raise ValueError("outcome evidence is stale")
        if outcome.case_id in outcomes:
            raise ValueError("duplicate outcome for a case")
        outcomes[outcome.case_id] = outcome

    if set(outcomes) != case_ids:
        raise ValueError("one or more preregistered cases have no outcome")

    holdout_cases = tuple(case for case in rows if case.split == "holdout")
    development_cases = tuple(case for case in rows if case.split == "development")
    holdout = _summarize(holdout_cases, outcomes)
    development = _summarize(development_cases, outcomes)

    inconclusive: list[str] = []
    if len(holdout_cases) < limits.min_holdout_cases:
        inconclusive.append("insufficient_holdout_cases")
    counts = holdout.get("category_counts")
    if not isinstance(counts, dict):
        inconclusive.append("missing_category_counts")
    else:
        for category in limits.required_categories:
            category_count = counts.get(category)
            if type(category_count) is not int or category_count < limits.min_cases_per_category:
                inconclusive.append(f"insufficient_category:{category}")
    answer_label_count = holdout.get("answer_label_count")
    if type(answer_label_count) is not int or answer_label_count < limits.min_answer_labels:
        inconclusive.append("insufficient_answer_labels")
    appropriateness_label_count = holdout.get("appropriateness_label_count")
    if (
        type(appropriateness_label_count) is not int
        or appropriateness_label_count < limits.min_appropriateness_labels
    ):
        inconclusive.append("insufficient_appropriateness_labels")
    latency_sample_count = holdout.get("latency_sample_count")
    if type(latency_sample_count) is not int or latency_sample_count < limits.min_latency_samples:
        inconclusive.append("insufficient_latency_samples")

    failures: list[str] = []
    if not inconclusive:
        checks = (
            ("direct_response_delivery_rate", "min", limits.min_direct_response_delivery_rate),
            ("unwanted_response_decision_rate", "max", limits.max_unwanted_response_decision_rate),
            ("silence_preservation_rate", "min", limits.min_silence_preservation_rate),
            ("human_resolution_stop_rate", "min", limits.min_human_resolution_stop_rate),
            ("false_stop_rate", "max", limits.max_false_stop_rate),
            ("urgent_interrupt_recall", "min", limits.min_urgent_interrupt_recall),
            ("false_interrupt_rate", "max", limits.max_false_interrupt_rate),
            ("answer_accuracy", "min", limits.min_answer_accuracy),
            ("response_appropriateness", "min", limits.min_response_appropriateness),
        )
        for metric, direction, threshold in checks:
            value = holdout[metric]
            if not isinstance(value, (int, float)):
                inconclusive.append(f"missing_metric:{metric}")
            elif direction == "min" and value < threshold:
                failures.append(metric)
            elif direction == "max" and value > threshold:
                failures.append(metric)
        latency = holdout["response_latency_ms_p95"]
        if not isinstance(latency, int):
            inconclusive.append("missing_metric:response_latency_ms_p95")
        elif latency > limits.max_response_latency_p95_ms:
            failures.append("response_latency_ms_p95")

    status = "INCONCLUSIVE" if inconclusive else ("FAIL" if failures else "PASS")
    return {
        "status": status,
        "roster_sha256": roster_sha,
        "holdout": holdout,
        "development": development,
        "inconclusive_reasons": inconclusive,
        "failed_gates": failures,
        "note": (
            "A PASS applies only to this sealed replay and configured thresholds; "
            "it does not authorize speech, change runtime policy, or promote a skill."
        ),
    }
