"""Randomized matched-start-state evaluation for causal game-mechanic probes.

This is an offline evaluator and assignment planner. It does not capture frames,
reset a game, execute controls, call models, write skills, or authorize play.
A trusted host must independently verify that each paired trial really began
from the same state and must keep the randomization seed hidden until the run
is complete. HMAC receipts authenticate the host report, not the truth of its
sensor or reset implementation.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import hashlib
import hmac
import json
import math
import re
from statistics import mean, median
from typing import Sequence

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ROSTER_DOMAIN = b"star.causal-game-probe.roster.v1\x00"
_MANIFEST_DOMAIN = b"star.causal-game-probe.manifest.v1\x00"
_RANDOM_DOMAIN = b"star.causal-game-probe.randomization.v1\x00"
_OUTCOME_DOMAIN = b"star.causal-game-probe.outcome.v1\x00"
_BLOCK_DOMAIN = b"star.causal-game-probe.block.v1\x00"
_RANK_DOMAIN = b"star.causal-game-probe.rank.v1\x00"
_ASSIGNMENT_DOMAIN = b"star.causal-game-probe.assignment.v1\x00"
_MAX_CASES = 512
_MAX_OUTCOMES = 1024
_MAX_AGE_S = 30 * 86400


def _identifier(value: object, field: str) -> None:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise ValueError(f"{field} must be a bounded opaque identifier")


def _digest(value: object, field: str) -> None:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _key(value: object, field: str) -> bytes:
    if type(value) is not bytes or not 32 <= len(value) <= 128:
        raise ValueError(f"{field} must contain 32..128 bytes")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("ascii")


@dataclass(frozen=True)
class ProbeCase:
    """One preregistered matched-start-state pair; hashes reveal no game state."""

    pair_id: str
    block_id: str
    game_id: str
    game_version: str
    objective_id: str
    situation_id: str
    start_state_sha256: str
    stratum_id: str = "default"

    def __post_init__(self) -> None:
        for field in (
            "pair_id", "block_id", "game_id", "game_version",
            "objective_id", "situation_id", "stratum_id",
        ):
            _identifier(getattr(self, field), field)
        _digest(self.start_state_sha256, "start_state_sha256")


@dataclass(frozen=True)
class ProbeManifest:
    """Frozen experiment scope and pre-run commitments."""

    experiment_id: str
    game_id: str
    game_version: str
    objective_id: str
    baseline_action_id: str
    candidate_action_id: str
    roster_sha256: str
    randomization_commitment: str
    minimum_pairs: int = 20
    minimum_blocks: int = 8
    minimum_effect_milli: int = 50
    max_pair_gap_s: int = 600
    max_age_s: int = 30 * 86400
    max_block_regression_milli: int = 200
    max_stratum_regression_milli: int = 200

    def __post_init__(self) -> None:
        for field in (
            "experiment_id", "game_id", "game_version", "objective_id",
            "baseline_action_id", "candidate_action_id",
        ):
            _identifier(getattr(self, field), field)
        if self.baseline_action_id == self.candidate_action_id:
            raise ValueError("baseline and candidate actions must differ")
        _digest(self.roster_sha256, "roster_sha256")
        _digest(self.randomization_commitment, "randomization_commitment")
        limits = (
            (self.minimum_pairs, 8, _MAX_CASES, "minimum_pairs"),
            (self.minimum_blocks, 4, 64, "minimum_blocks"),
            (self.minimum_effect_milli, 10, 500, "minimum_effect_milli"),
            (self.max_pair_gap_s, 30, 3600, "max_pair_gap_s"),
            (self.max_age_s, 60, _MAX_AGE_S, "max_age_s"),
            (self.max_block_regression_milli, 0, 1000, "max_block_regression_milli"),
            (self.max_stratum_regression_milli, 0, 1000, "max_stratum_regression_milli"),
        )
        for value, lower, upper, field in limits:
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError(f"invalid {field}")


@dataclass(frozen=True)
class TrialAssignment:
    """Host-only assignment for one pair; do not expose future assignments to the agent."""

    pair_id: str
    block_id: str
    order: str
    first_action_id: str
    second_action_id: str
    assignment_sha256: str


@dataclass(frozen=True)
class ProbeOutcome:
    """One independently scored trial from a trusted game-observer host."""

    pair_id: str
    block_id: str
    action_id: str
    trial_id: str
    run_id: str
    start_state_sha256: str
    assignment_sha256: str
    attempt_index: int
    score_milli: int
    success: bool
    observed_unix_s: int
    evidence_sha256: str

    def __post_init__(self) -> None:
        for field in ("pair_id", "block_id", "action_id", "trial_id", "run_id"):
            _identifier(getattr(self, field), field)
        _digest(self.start_state_sha256, "start_state_sha256")
        _digest(self.assignment_sha256, "assignment_sha256")
        _digest(self.evidence_sha256, "evidence_sha256")
        if type(self.attempt_index) is not int or self.attempt_index not in (0, 1):
            raise ValueError("attempt_index must be 0 or 1")
        if type(self.score_milli) is not int or not 0 <= self.score_milli <= 1000:
            raise ValueError("score_milli must be an integer in 0..1000")
        if type(self.success) is not bool:
            raise ValueError("success must be a boolean")
        if type(self.observed_unix_s) is not int or not 0 < self.observed_unix_s <= 10**11:
            raise ValueError("invalid observed_unix_s")

    def canonical_bytes(self) -> bytes:
        return _OUTCOME_DOMAIN + _canonical(asdict(self))


@dataclass(frozen=True)
class SignedProbeOutcome:
    outcome: ProbeOutcome
    receipt: str


@dataclass(frozen=True)
class CausalProbeReport:
    verdict: str
    preregistered_pairs: int
    completed_pairs: int
    incomplete_pairs: int
    independent_blocks: int
    positive_blocks: int
    negative_blocks: int
    tied_blocks: int
    baseline_first_pairs: int
    candidate_first_pairs: int
    baseline_success_rate: float | None
    candidate_success_rate: float | None
    mean_effect_milli: float | None
    median_effect_milli: float | None
    block_sign_p: float | None
    reverse_block_sign_p: float | None
    stratum_effects_milli: tuple[tuple[str, float], ...]
    note: str = (
        "randomized matched-start-state evidence; host signatures authenticate reports, "
        "not the truth of game resets or scoring; owner review required"
    )


def _checked_cases(cases: Sequence[ProbeCase]) -> tuple[ProbeCase, ...]:
    if type(cases) not in (tuple, list) or not 1 <= len(cases) <= _MAX_CASES:
        raise ValueError(f"provide 1..{_MAX_CASES} preregistered cases")
    if any(not isinstance(case, ProbeCase) for case in cases):
        raise TypeError("cases must contain ProbeCase values")
    rows = tuple(cases)
    if len({case.pair_id for case in rows}) != len(rows):
        raise ValueError("duplicate pair_id in preregistered roster")
    return rows


def roster_digest(cases: Sequence[ProbeCase]) -> str:
    """Hash the exact matched-state roster before the experiment begins."""
    rows = _checked_cases(cases)
    payload = sorted(
        (case.pair_id, case.block_id, case.game_id, case.game_version,
         case.objective_id, case.situation_id, case.start_state_sha256, case.stratum_id)
        for case in rows
    )
    return hashlib.sha256(_ROSTER_DOMAIN + _canonical(payload)).hexdigest()


def randomization_commitment(seed: bytes) -> str:
    """Commit to a host-only seed; reveal it only after all trials are complete."""
    secret = _key(seed, "randomization seed")
    return hashlib.sha256(_RANDOM_DOMAIN + secret).hexdigest()


def manifest_digest(manifest: ProbeManifest) -> str:
    if not isinstance(manifest, ProbeManifest):
        raise TypeError("manifest must be a ProbeManifest")
    return hashlib.sha256(_MANIFEST_DOMAIN + _canonical(asdict(manifest))).hexdigest()


def assignment_plan(
    cases: Sequence[ProbeCase],
    manifest: ProbeManifest,
    *,
    randomization_seed: bytes,
) -> tuple[TrialAssignment, ...]:
    """Generate a deterministic, concealed, block-balanced randomized order.

    The host should request only the next pair assignment at execution time.
    The full plan and seed must remain unavailable to the evaluated agent.
    """
    rows = _checked_cases(cases)
    seed = _key(randomization_seed, "randomization seed")
    if not isinstance(manifest, ProbeManifest):
        raise TypeError("manifest must be a ProbeManifest")
    if not hmac.compare_digest(roster_digest(rows), manifest.roster_sha256):
        raise PermissionError("case roster differs from preregistered manifest")
    if not hmac.compare_digest(randomization_commitment(seed), manifest.randomization_commitment):
        raise PermissionError("randomization seed does not match pre-run commitment")
    for case in rows:
        if (case.game_id, case.game_version, case.objective_id) != (
            manifest.game_id, manifest.game_version, manifest.objective_id
        ):
            raise ValueError("case scope differs from manifest")

    manifest_sha = bytes.fromhex(manifest_digest(manifest))
    blocks: dict[str, list[ProbeCase]] = defaultdict(list)
    for case in rows:
        blocks[case.block_id].append(case)

    assignments: list[TrialAssignment] = []
    for block_id, block_cases in sorted(blocks.items()):
        block_key = hmac.new(
            seed, _BLOCK_DOMAIN + manifest_sha + block_id.encode("ascii"), hashlib.sha256
        ).digest()
        ranked = sorted(
            block_cases,
            key=lambda case: hmac.new(
                seed, _RANK_DOMAIN + manifest_sha + case.pair_id.encode("ascii"),
                hashlib.sha256,
            ).digest(),
        )
        offset = block_key[0] & 1
        for index, case in enumerate(ranked):
            baseline_first = (index + offset) % 2 == 0
            first = manifest.baseline_action_id if baseline_first else manifest.candidate_action_id
            second = manifest.candidate_action_id if baseline_first else manifest.baseline_action_id
            order = "baseline_first" if baseline_first else "candidate_first"
            assignment_payload = {
                "manifest_sha256": manifest_digest(manifest),
                "pair_id": case.pair_id,
                "block_id": case.block_id,
                "start_state_sha256": case.start_state_sha256,
                "order": order,
                "first_action_id": first,
                "second_action_id": second,
            }
            assignment_sha = hashlib.sha256(
                _ASSIGNMENT_DOMAIN + _canonical(assignment_payload)
            ).hexdigest()
            assignments.append(TrialAssignment(
                case.pair_id, case.block_id, order, first, second, assignment_sha
            ))
    return tuple(sorted(assignments, key=lambda item: item.pair_id))


def sign_outcome(outcome: ProbeOutcome, key: bytes) -> str:
    """Host helper; keep the signing key outside model and tool-worker processes."""
    secret = _key(key, "outcome signing key")
    if not isinstance(outcome, ProbeOutcome):
        raise TypeError("outcome must be a ProbeOutcome")
    return hmac.new(secret, outcome.canonical_bytes(), hashlib.sha256).hexdigest()


def _sign_test_p(wins: int, losses: int) -> float | None:
    """Exact one-sided sign-test p-value across independent block means."""
    n = wins + losses
    if n == 0:
        return None
    return sum(math.comb(n, k) for k in range(wins, n + 1)) / (2 ** n)


def evaluate_causal_probe(
    manifest: ProbeManifest,
    cases: Sequence[ProbeCase],
    signed_outcomes: Sequence[SignedProbeOutcome],
    *,
    randomization_seed: bytes,
    outcome_key: bytes,
    expected_manifest_sha256: str,
    now_unix_s: int,
) -> CausalProbeReport:
    """Verify a completed randomized probe and return an advisory causal estimate.

    The expected manifest digest must come from an independently timestamped host
    log created before the first trial. The evaluated agent must not receive
    that log, the randomization seed, or the sealed case roster before execution.
    """
    if not isinstance(manifest, ProbeManifest):
        raise TypeError("manifest must be a ProbeManifest")
    if type(now_unix_s) is not int or not 0 < now_unix_s <= 10**11:
        raise ValueError("invalid current Unix timestamp")
    _digest(expected_manifest_sha256, "expected_manifest_sha256")
    seed = _key(randomization_seed, "randomization seed")
    secret = _key(outcome_key, "outcome signing key")
    if hmac.compare_digest(seed, secret):
        raise ValueError("randomization and outcome keys must be independent")
    actual_manifest_sha = manifest_digest(manifest)
    if not hmac.compare_digest(actual_manifest_sha, expected_manifest_sha256):
        raise PermissionError("manifest differs from independently sealed pre-run digest")
    rows = _checked_cases(cases)
    plan = {
        item.pair_id: item
        for item in assignment_plan(rows, manifest, randomization_seed=seed)
    }
    if type(signed_outcomes) not in (tuple, list) or len(signed_outcomes) > _MAX_OUTCOMES:
        raise ValueError(f"provide at most {_MAX_OUTCOMES} signed outcomes")

    roster = {case.pair_id: case for case in rows}
    slots: dict[str, dict[int, ProbeOutcome]] = {}
    seen_trials: set[str] = set()
    seen_runs: set[str] = set()
    for signed in signed_outcomes:
        if not isinstance(signed, SignedProbeOutcome) or not isinstance(signed.outcome, ProbeOutcome):
            raise TypeError("expected SignedProbeOutcome values")
        outcome = signed.outcome
        case = roster.get(outcome.pair_id)
        assignment = plan.get(outcome.pair_id)
        if case is None or assignment is None:
            raise ValueError("outcome is outside the preregistered roster")
        if outcome.block_id != case.block_id or outcome.start_state_sha256 != case.start_state_sha256:
            raise PermissionError("outcome does not match the preregistered matched start state")
        if outcome.assignment_sha256 != assignment.assignment_sha256:
            raise PermissionError("outcome does not match the randomized assignment")
        expected_action = (
            assignment.first_action_id if outcome.attempt_index == 0
            else assignment.second_action_id
        )
        if outcome.action_id != expected_action:
            raise PermissionError("action order differs from the randomized assignment")
        if not 0 <= now_unix_s - outcome.observed_unix_s <= manifest.max_age_s:
            raise ValueError("stale or future-dated outcome")
        if outcome.trial_id in seen_trials or outcome.run_id in seen_runs:
            raise ValueError("reused trial_id or run_id")
        if type(signed.receipt) is not str or not _SHA.fullmatch(signed.receipt):
            raise PermissionError("invalid host outcome receipt")
        expected = sign_outcome(outcome, secret)
        if not hmac.compare_digest(expected, signed.receipt):
            raise PermissionError("host outcome signature mismatch")
        pair = slots.setdefault(outcome.pair_id, {})
        if outcome.attempt_index in pair:
            raise ValueError("duplicate attempt for matched pair")
        pair[outcome.attempt_index] = outcome
        seen_trials.add(outcome.trial_id)
        seen_runs.add(outcome.run_id)

    completed = [pair for pair in slots.values() if len(pair) == 2]
    incomplete = len(rows) - len(completed)
    if incomplete:
        return CausalProbeReport(
            "inconclusive", len(rows), len(completed), incomplete, 0, 0, 0, 0,
            0, 0, None, None, None, None, None, None, (),
        )

    effects: list[int] = []
    block_effects: dict[str, list[int]] = defaultdict(list)
    stratum_effects: dict[str, list[int]] = defaultdict(list)
    baseline_successes = candidate_successes = 0
    baseline_first = candidate_first = 0
    for case in rows:
        pair = slots[case.pair_id]
        first, second = pair[0], pair[1]
        if first.observed_unix_s > second.observed_unix_s:
            raise ValueError("attempt timestamps contradict randomized order")
        if second.observed_unix_s - first.observed_unix_s > manifest.max_pair_gap_s:
            raise ValueError("matched pair exceeded the maximum reset/measurement gap")
        assignment = plan[case.pair_id]
        if assignment.order == "baseline_first":
            baseline_first += 1
        else:
            candidate_first += 1
        outcomes = {first.action_id: first, second.action_id: second}
        baseline = outcomes[manifest.baseline_action_id]
        candidate = outcomes[manifest.candidate_action_id]
        effect = candidate.score_milli - baseline.score_milli
        effects.append(effect)
        block_effects[case.block_id].append(effect)
        stratum_effects[case.stratum_id].append(effect)
        baseline_successes += int(baseline.success)
        candidate_successes += int(candidate.success)

    block_means = {block: mean(values) for block, values in block_effects.items()}
    positive = sum(value > 0 for value in block_means.values())
    negative = sum(value < 0 for value in block_means.values())
    tied = len(block_means) - positive - negative
    p_value = _sign_test_p(positive, negative)
    reverse_p = _sign_test_p(negative, positive)
    strata = tuple(sorted(
        (name, round(mean(values), 2)) for name, values in stratum_effects.items()
    ))
    coverage = len(rows) >= manifest.minimum_pairs and len(block_means) >= manifest.minimum_blocks
    no_major_regression = (
        all(value >= -manifest.max_block_regression_milli for value in block_means.values())
        and all(value >= -manifest.max_stratum_regression_milli for _, value in strata)
    )
    average_effect = mean(effects)
    eligible = (
        coverage and average_effect >= manifest.minimum_effect_milli
        and p_value is not None and p_value < 0.025 and no_major_regression
    )
    regressed = (
        coverage and average_effect <= -manifest.minimum_effect_milli
        and reverse_p is not None and reverse_p < 0.025
    )
    verdict = "eligible_for_owner_review" if eligible else "regressed" if regressed else "inconclusive"
    total = len(rows)
    return CausalProbeReport(
        verdict, total, total, 0, len(block_means), positive, negative, tied,
        baseline_first, candidate_first,
        round(baseline_successes / total, 4),
        round(candidate_successes / total, 4),
        round(average_effect, 2), round(median(effects), 2),
        round(p_value, 7) if p_value is not None else None,
        round(reverse_p, 7) if reverse_p is not None else None, strata,
    )


__all__ = [
    "ProbeCase", "ProbeManifest", "TrialAssignment", "ProbeOutcome",
    "SignedProbeOutcome", "CausalProbeReport", "roster_digest",
    "randomization_commitment", "manifest_digest", "assignment_plan",
    "sign_outcome", "evaluate_causal_probe",
]
