"""Offline tests for randomized matched-start-state causal game probes."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import unittest

from star.causal_game_probe import (
    ProbeCase,
    ProbeManifest,
    ProbeOutcome,
    SignedProbeOutcome,
    assignment_plan,
    evaluate_causal_probe,
    manifest_digest,
    randomization_commitment,
    roster_digest,
    sign_outcome,
)

SEED = b"star-run45-randomization-seed-2026"
KEY = b"star-run45-independent-outcome-key"
NOW = 2_000_000_000


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_cases(*, blocks: int = 8, per_block: int = 3, hard_block: int | None = None):
    rows = []
    for block in range(blocks):
        for index in range(per_block):
            number = block * per_block + index
            rows.append(ProbeCase(
                pair_id=f"pair-{number:03d}",
                block_id=f"block-{block:02d}",
                game_id="obby",
                game_version="build-7",
                objective_id="finish",
                situation_id="jump-gap",
                start_state_sha256=sha(f"start-state-{number}"),
                stratum_id="hard" if hard_block == block else "normal",
            ))
    return tuple(rows)


def make_manifest(cases, *, blocks: int = 8, minimum_pairs: int = 20):
    return ProbeManifest(
        experiment_id="jump-gap-ab",
        game_id="obby",
        game_version="build-7",
        objective_id="finish",
        baseline_action_id="short-jump",
        candidate_action_id="long-jump",
        roster_sha256=roster_digest(cases),
        randomization_commitment=randomization_commitment(SEED),
        minimum_pairs=minimum_pairs,
        minimum_blocks=blocks,
        minimum_effect_milli=50,
        max_pair_gap_s=60,
    )


def signed_trials(cases, manifest, *, candidate_score=700, baseline_score=400,
                  candidate_success=True, baseline_success=False, bad_block=None):
    plan = {row.pair_id: row for row in assignment_plan(
        cases, manifest, randomization_seed=SEED
    )}
    result = []
    for number, case in enumerate(cases):
        assignment = plan[case.pair_id]
        for attempt_index, action in enumerate((
            assignment.first_action_id, assignment.second_action_id
        )):
            is_candidate = action == manifest.candidate_action_id
            score = candidate_score if is_candidate else baseline_score
            success = candidate_success if is_candidate else baseline_success
            if bad_block == case.block_id:
                score = baseline_score if is_candidate else candidate_score
                success = baseline_success if is_candidate else candidate_success
            outcome = ProbeOutcome(
                pair_id=case.pair_id,
                block_id=case.block_id,
                action_id=action,
                trial_id=f"trial-{number:03d}-{attempt_index}",
                run_id=f"run-{number:03d}-{attempt_index}",
                start_state_sha256=case.start_state_sha256,
                assignment_sha256=assignment.assignment_sha256,
                attempt_index=attempt_index,
                score_milli=score,
                success=success,
                observed_unix_s=NOW + number * 20 + attempt_index * 5,
                evidence_sha256=sha(f"evidence-{number}-{attempt_index}"),
            )
            result.append(SignedProbeOutcome(outcome, sign_outcome(outcome, KEY)))
    return tuple(result)


def evaluate(cases, manifest, outcomes):
    return evaluate_causal_probe(
        manifest,
        cases,
        outcomes,
        randomization_seed=SEED,
        outcome_key=KEY,
        expected_manifest_sha256=manifest_digest(manifest),
        now_unix_s=NOW + 10_000,
    )


class CausalGameProbeTests(unittest.TestCase):
    def setUp(self):
        self.cases = make_cases()
        self.manifest = make_manifest(self.cases)

    def test_assignment_is_deterministic_and_balanced_within_each_block(self):
        first = assignment_plan(self.cases, self.manifest, randomization_seed=SEED)
        second = assignment_plan(self.cases, self.manifest, randomization_seed=SEED)
        self.assertEqual(first, second)
        for block in {case.block_id for case in self.cases}:
            orders = [row.order for row in first if row.block_id == block]
            self.assertLessEqual(abs(orders.count("baseline_first") -
                                     orders.count("candidate_first")), 1)

    def test_candidate_gain_is_eligible_only_for_owner_review(self):
        report = evaluate(self.cases, self.manifest,
                          signed_trials(self.cases, self.manifest))
        self.assertEqual(report.verdict, "eligible_for_owner_review")
        self.assertEqual(report.completed_pairs, len(self.cases))
        self.assertEqual(report.independent_blocks, 8)
        self.assertEqual(report.mean_effect_milli, 300)
        self.assertLess(report.block_sign_p, 0.025)
        self.assertIsNotNone(report.baseline_success_rate)
        self.assertIsNotNone(report.candidate_success_rate)

    def test_baseline_gain_is_reported_as_regression(self):
        outcomes = signed_trials(
            self.cases, self.manifest,
            candidate_score=400, baseline_score=700,
            candidate_success=False, baseline_success=True,
        )
        report = evaluate(self.cases, self.manifest, outcomes)
        self.assertEqual(report.verdict, "regressed")
        self.assertEqual(report.mean_effect_milli, -300)

    def test_missing_pair_is_inconclusive_without_partial_scores(self):
        outcomes = signed_trials(self.cases, self.manifest)[:-1]
        report = evaluate(self.cases, self.manifest, outcomes)
        self.assertEqual(report.verdict, "inconclusive")
        self.assertEqual(report.incomplete_pairs, 1)
        self.assertIsNone(report.mean_effect_milli)
        self.assertIsNone(report.candidate_success_rate)

    def test_wrong_randomization_seed_is_rejected(self):
        with self.assertRaises(PermissionError):
            assignment_plan(self.cases, self.manifest,
                            randomization_seed=b"different-randomization-seed")

    def test_roster_change_is_rejected(self):
        changed = list(self.cases)
        changed[0] = replace(changed[0], start_state_sha256=sha("different-state"))
        with self.assertRaises(PermissionError):
            assignment_plan(changed, self.manifest, randomization_seed=SEED)

    def test_manifest_must_match_external_prerun_seal(self):
        outcomes = signed_trials(self.cases, self.manifest)
        with self.assertRaises(PermissionError):
            evaluate_causal_probe(
                self.manifest, self.cases, outcomes,
                randomization_seed=SEED, outcome_key=KEY,
                expected_manifest_sha256=sha("not-the-preregistered-manifest"),
                now_unix_s=NOW + 10_000,
            )

    def test_tampered_receipt_is_rejected(self):
        outcomes = list(signed_trials(self.cases, self.manifest))
        outcomes[0] = replace(outcomes[0], receipt=sha("tampered"))
        with self.assertRaises(PermissionError):
            evaluate(self.cases, self.manifest, outcomes)

    def test_wrong_randomized_action_order_is_rejected(self):
        outcomes = list(signed_trials(self.cases, self.manifest))
        first = outcomes[0].outcome
        wrong_action = (
            self.manifest.candidate_action_id
            if first.action_id == self.manifest.baseline_action_id
            else self.manifest.baseline_action_id
        )
        wrong = replace(first, action_id=wrong_action)
        outcomes[0] = SignedProbeOutcome(wrong, sign_outcome(wrong, KEY))
        with self.assertRaises(PermissionError):
            evaluate(self.cases, self.manifest, outcomes)

    def test_mismatched_start_state_is_rejected(self):
        outcomes = list(signed_trials(self.cases, self.manifest))
        changed = replace(outcomes[0].outcome, start_state_sha256=sha("not-matched"))
        outcomes[0] = SignedProbeOutcome(changed, sign_outcome(changed, KEY))
        with self.assertRaises(PermissionError):
            evaluate(self.cases, self.manifest, outcomes)

    def test_duplicate_trial_identity_is_rejected(self):
        outcomes = list(signed_trials(self.cases, self.manifest))
        duplicate = replace(outcomes[1].outcome, trial_id=outcomes[0].outcome.trial_id)
        outcomes[1] = SignedProbeOutcome(duplicate, sign_outcome(duplicate, KEY))
        with self.assertRaises(ValueError):
            evaluate(self.cases, self.manifest, outcomes)

    def test_pair_time_gap_is_bounded(self):
        outcomes = list(signed_trials(self.cases, self.manifest))
        changed = replace(outcomes[1].outcome, observed_unix_s=NOW + 10_000)
        outcomes[1] = SignedProbeOutcome(changed, sign_outcome(changed, KEY))
        with self.assertRaises(ValueError):
            evaluate(self.cases, self.manifest, outcomes)

    def test_attempt_timestamps_must_follow_randomized_order(self):
        outcomes = list(signed_trials(self.cases, self.manifest))
        first, second = outcomes[0].outcome, outcomes[1].outcome
        earlier = replace(second, observed_unix_s=first.observed_unix_s - 1)
        outcomes[1] = SignedProbeOutcome(earlier, sign_outcome(earlier, KEY))
        with self.assertRaises(ValueError):
            evaluate(self.cases, self.manifest, outcomes)

    def test_many_pairs_in_one_block_do_not_fake_independent_replication(self):
        cases = make_cases(blocks=1, per_block=24)
        manifest = make_manifest(cases, blocks=8)
        report = evaluate(cases, manifest, signed_trials(cases, manifest))
        self.assertEqual(report.verdict, "inconclusive")
        self.assertEqual(report.independent_blocks, 1)

    def test_one_bad_block_prevents_promotion_despite_large_overall_gain(self):
        cases = make_cases(blocks=10, per_block=3)
        manifest = make_manifest(cases, blocks=8)
        outcomes = signed_trials(
            cases, manifest, bad_block="block-09"
        )
        report = evaluate(cases, manifest, outcomes)
        self.assertEqual(report.verdict, "inconclusive")
        self.assertEqual(report.negative_blocks, 1)

    def test_bad_stratum_is_visible_and_blocks_promotion(self):
        cases = make_cases(blocks=10, per_block=3, hard_block=9)
        manifest = make_manifest(cases, blocks=8)
        outcomes = signed_trials(cases, manifest, bad_block="block-09")
        report = evaluate(cases, manifest, outcomes)
        self.assertEqual(report.verdict, "inconclusive")
        self.assertIn(("hard", -300.0), report.stratum_effects_milli)

    def test_invalid_boolean_and_score_types_are_rejected(self):
        assignment = assignment_plan(
            self.cases, self.manifest, randomization_seed=SEED
        )[0]
        with self.assertRaises(ValueError):
            ProbeOutcome(
                pair_id=assignment.pair_id, block_id=assignment.block_id,
                action_id=assignment.first_action_id, trial_id="trial-bad",
                run_id="run-bad", start_state_sha256=self.cases[0].start_state_sha256,
                assignment_sha256=assignment.assignment_sha256, attempt_index=0,
                score_milli=True, success=True, observed_unix_s=NOW,
                evidence_sha256=sha("bad"),
            )
        with self.assertRaises(ValueError):
            ProbeOutcome(
                pair_id=assignment.pair_id, block_id=assignment.block_id,
                action_id=assignment.first_action_id, trial_id="trial-bad",
                run_id="run-bad", start_state_sha256=self.cases[0].start_state_sha256,
                assignment_sha256=assignment.assignment_sha256, attempt_index=0,
                score_milli=1001, success=1, observed_unix_s=NOW,
                evidence_sha256=sha("bad"),
            )

    def test_duplicate_pair_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            roster_digest((self.cases[0], self.cases[0]))


if __name__ == "__main__":
    unittest.main()
