from __future__ import annotations

import copy
import json
import unittest

from star.skill_contract import (
    evaluate_skill_coverage, parse_skill_contract, validate_execution_receipt,
)


def valid_contract():
    return {
        "schema_version": 1,
        "skill_id": "roblox-open-door",
        "version": "1.2.0",
        "domain": "roblox",
        "summary": "Open a door after observing its state and checking the interaction preconditions.",
        "environment_fingerprint": "a" * 64,
        "expires_at": "2026-12-01T00:00:00Z",
        "preconditions": [
            {"kind": "fresh_observation", "subject": "door", "max_age_ms": 1000},
            {"kind": "owner_consent", "subject": "selected_test_place", "value": True},
        ],
        "steps": [
            {"step_id": "inspect", "operation": "observe", "intent": "Read the selected door state."},
            {"step_id": "interact", "operation": "request_tool", "intent": "Request the approved interaction tool.",
             "tool_name": "studio.inspect", "required_capabilities": ["studio.read"],
             "expected_deltas": [{"path": "door.open", "operator": "equals", "value": True}]},
            {"step_id": "verify", "operation": "verify", "intent": "Independently inspect the resulting door state."},
        ],
        "behavior_constraints": [
            {"constraint_id": "inspect-before-act",
             "condition": {"kind": "state_exists", "subject": "door"},
             "expected_behavior": "Inspect the target door before requesting a mutating tool.",
             "severity": "critical"},
            {"constraint_id": "verify-result",
             "condition": {"kind": "state_equals", "subject": "door.open", "operator": "equals", "value": True},
             "expected_behavior": "Verify the door state using an independent host observation."},
        ],
        "postconditions": [{"path": "door.open", "operator": "equals", "value": True}],
        "resource_budget": {
            "max_elapsed_ms": 30000, "max_steps": 3, "max_tool_calls": 1,
            "max_tokens": 2000, "max_retries": 1, "max_ram_mib": 256,
        },
        "provenance": [
            {"kind": "url", "locator": "https://create.roblox.com/docs/reference/engine/classes/ProximityPrompt"},
            {"kind": "evaluation", "locator": "roblox-door-holdout-v1"},
        ],
    }


def valid_receipt(contract):
    return {
        "schema_version": 1,
        "run_id": "run-0001",
        "skill_id": contract.skill_id,
        "skill_version": contract.version,
        "contract_sha256": contract.digest(),
        "environment_fingerprint": "a" * 64,
        "started_at": "2026-11-15T10:00:00Z",
        "finished_at": "2026-11-15T10:00:10Z",
        "outcome": "success",
        "preconditions_passed": True,
        "postconditions_verified": True,
        "verifier": "independent_host",
        "evidence_sha256": "b" * 64,
        "holdout": True,
    }


class SkillContractTests(unittest.TestCase):
    def test_valid_contract_round_trips_and_digest_is_stable(self):
        contract = parse_skill_contract(valid_contract())
        self.assertEqual(contract.skill_id, "roblox-open-door")
        self.assertEqual(contract.digest(), parse_skill_contract(contract.to_dict()).digest())

    def test_json_string_is_supported(self):
        contract = parse_skill_contract(json.dumps(valid_contract()))
        self.assertEqual(contract.domain, "roblox")

    def test_unknown_top_level_fields_are_rejected(self):
        raw = valid_contract()
        raw["python_code"] = "print('execute me')"
        with self.assertRaisesRegex(ValueError, "unknown python_code"):
            parse_skill_contract(raw)

    def test_unknown_step_fields_are_rejected(self):
        raw = valid_contract()
        raw["steps"][0]["command"] = "powershell"
        with self.assertRaisesRegex(ValueError, "unknown command"):
            parse_skill_contract(raw)

    def test_schema_version_must_match(self):
        raw = valid_contract()
        raw["schema_version"] = 2
        with self.assertRaisesRegex(ValueError, "unsupported"):
            parse_skill_contract(raw)

    def test_semver_is_required(self):
        raw = valid_contract()
        raw["version"] = "latest"
        with self.assertRaisesRegex(ValueError, "semantic version"):
            parse_skill_contract(raw)

    def test_domain_is_allowlisted(self):
        raw = valid_contract()
        raw["domain"] = "root-shell"
        with self.assertRaisesRegex(ValueError, "unsupported skill domain"):
            parse_skill_contract(raw)

    def test_duplicate_step_ids_are_rejected(self):
        raw = valid_contract()
        raw["steps"][1]["step_id"] = raw["steps"][0]["step_id"]
        with self.assertRaisesRegex(ValueError, "unique"):
            parse_skill_contract(raw)

    def test_duplicate_behavior_constraint_ids_are_rejected(self):
        raw = valid_contract()
        raw["behavior_constraints"][1]["constraint_id"] = raw["behavior_constraints"][0]["constraint_id"]
        with self.assertRaisesRegex(ValueError, "constraint ids must be unique"):
            parse_skill_contract(raw)

    def test_tool_step_requires_tool_and_capability(self):
        raw = valid_contract()
        raw["steps"][1]["required_capabilities"] = []
        with self.assertRaisesRegex(ValueError, "requires a tool_name"):
            parse_skill_contract(raw)

    def test_tool_name_cannot_be_smuggled_into_reason_step(self):
        raw = valid_contract()
        raw["steps"][0]["tool_name"] = "filesystem.write"
        with self.assertRaisesRegex(ValueError, "only valid"):
            parse_skill_contract(raw)

    def test_path_traversal_is_rejected(self):
        raw = valid_contract()
        raw["postconditions"][0]["path"] = "../secret"
        with self.assertRaisesRegex(ValueError, "relative logical path"):
            parse_skill_contract(raw)

    def test_fresh_observation_requires_age(self):
        raw = valid_contract()
        raw["preconditions"][0].pop("max_age_ms")
        with self.assertRaisesRegex(ValueError, "requires max_age_ms"):
            parse_skill_contract(raw)

    def test_owner_consent_is_a_requirement_not_a_grant(self):
        raw = valid_contract()
        raw["preconditions"][1]["value"] = False
        with self.assertRaisesRegex(ValueError, "cannot encode consent"):
            parse_skill_contract(raw)

    def test_artifact_requires_digest(self):
        raw = valid_contract()
        raw["provenance"] = [{"kind": "artifact", "locator": "asset://door-model"}]
        with self.assertRaisesRegex(ValueError, "require a SHA-256"):
            parse_skill_contract(raw)

    def test_source_url_must_be_https_without_credentials(self):
        raw = valid_contract()
        raw["provenance"][0]["locator"] = "https://user:pass@example.com/docs"
        with self.assertRaisesRegex(ValueError, "without embedded credentials"):
            parse_skill_contract(raw)

    def test_budget_must_cover_declared_steps(self):
        raw = valid_contract()
        raw["resource_budget"]["max_steps"] = 2
        with self.assertRaisesRegex(ValueError, "exceed"):
            parse_skill_contract(raw)

    def test_budget_values_are_bounded(self):
        raw = valid_contract()
        raw["resource_budget"]["max_tokens"] = 1_000_000_000
        with self.assertRaisesRegex(ValueError, "max_tokens"):
            parse_skill_contract(raw)

    def test_receipt_schema_version_must_match(self):
        contract = parse_skill_contract(valid_contract())
        receipt = valid_receipt(contract)
        receipt["schema_version"] = 2
        with self.assertRaisesRegex(ValueError, "unsupported execution receipt"):
            validate_execution_receipt(receipt, contract)

    def test_receipt_must_match_contract_digest(self):
        contract = parse_skill_contract(valid_contract())
        receipt = valid_receipt(contract)
        receipt["contract_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "digest does not match"):
            validate_execution_receipt(receipt, contract)

    def test_receipt_must_match_environment(self):
        contract = parse_skill_contract(valid_contract())
        receipt = valid_receipt(contract)
        receipt["environment_fingerprint"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "environment does not match"):
            validate_execution_receipt(receipt, contract)

    def test_success_requires_verified_pre_and_postconditions(self):
        contract = parse_skill_contract(valid_contract())
        receipt = valid_receipt(contract)
        receipt["postconditions_verified"] = False
        with self.assertRaisesRegex(ValueError, "success requires"):
            validate_execution_receipt(receipt, contract)

    def test_verified_postconditions_require_independent_evidence(self):
        contract = parse_skill_contract(valid_contract())
        receipt = valid_receipt(contract)
        receipt["verifier"] = "none"
        with self.assertRaisesRegex(ValueError, "independent verifier"):
            validate_execution_receipt(receipt, contract)

    def test_holdout_receipt_requires_evidence_digest(self):
        contract = parse_skill_contract(valid_contract())
        receipt = valid_receipt(contract)
        receipt["evidence_sha256"] = None
        receipt["postconditions_verified"] = False
        receipt["verifier"] = "none"
        receipt["outcome"] = "failure"
        with self.assertRaisesRegex(ValueError, "holdout receipts"):
            validate_execution_receipt(receipt, contract)

    def test_receipt_duration_is_bounded(self):
        contract = parse_skill_contract(valid_contract())
        receipt = valid_receipt(contract)
        receipt["finished_at"] = "2026-11-15T11:00:00Z"
        with self.assertRaisesRegex(ValueError, "time budget"):
            validate_execution_receipt(receipt, contract)

    def test_expired_contract_cannot_be_reused(self):
        raw = valid_contract()
        raw["expires_at"] = "2026-11-01T00:00:00Z"
        contract = parse_skill_contract(raw)
        with self.assertRaisesRegex(ValueError, "expired"):
            validate_execution_receipt(valid_receipt(contract), contract)

    def test_receipt_rejects_naive_timestamps(self):
        contract = parse_skill_contract(valid_contract())
        receipt = valid_receipt(contract)
        receipt["started_at"] = "2026-11-15T10:00:00"
        with self.assertRaisesRegex(ValueError, "timezone"):
            validate_execution_receipt(receipt, contract)

    def test_failed_attempt_is_valid_evidence_without_claiming_success(self):
        contract = parse_skill_contract(valid_contract())
        receipt = valid_receipt(contract)
        receipt.update(outcome="failure", postconditions_verified=False, verifier="none", holdout=False,
                       evidence_sha256=None)
        validated = validate_execution_receipt(receipt, contract)
        self.assertEqual(validated.outcome, "failure")

    def test_contract_parser_does_not_mutate_input(self):
        raw = valid_contract()
        before = copy.deepcopy(raw)
        parse_skill_contract(raw)
        self.assertEqual(raw, before)

    def test_oversized_json_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "too large"):
            parse_skill_contract(" " * 64_001)

    def test_non_boolean_evidence_flags_are_rejected(self):
        contract = parse_skill_contract(valid_contract())
        receipt = valid_receipt(contract)
        receipt["holdout"] = 1
        with self.assertRaisesRegex(ValueError, "booleans"):
            validate_execution_receipt(receipt, contract)

    def test_coverage_counts_only_observed_constraints(self):
        contract = parse_skill_contract(valid_contract())
        report = evaluate_skill_coverage(contract, [
            {"constraint_id": "inspect-before-act", "verdict": "pass",
             "verifier": "independent_host", "evidence_sha256": "c" * 64},
            {"constraint_id": "verify-result", "verdict": "not_observed", "verifier": "none"},
        ])
        self.assertEqual(report.total_constraints, 2)
        self.assertEqual(report.covered_constraints, 1)
        self.assertEqual(report.unobserved_constraints, 1)
        self.assertEqual(report.coverage_rate, 0.5)
        self.assertFalse(report.review_recommended)

    def test_coverage_reports_critical_failures(self):
        contract = parse_skill_contract(valid_contract())
        report = evaluate_skill_coverage(contract, [
            {"constraint_id": "inspect-before-act", "verdict": "fail",
             "verifier": "independent_replay", "evidence_sha256": "c" * 64},
            {"constraint_id": "verify-result", "verdict": "pass",
             "verifier": "independent_host", "evidence_sha256": "d" * 64},
        ])
        self.assertEqual(report.critical_failures, 1)
        self.assertFalse(report.review_recommended)

    def test_coverage_review_signal_needs_full_coverage_and_no_failures(self):
        contract = parse_skill_contract(valid_contract())
        report = evaluate_skill_coverage(contract, [
            {"constraint_id": "inspect-before-act", "verdict": "pass",
             "verifier": "independent_host", "evidence_sha256": "c" * 64},
            {"constraint_id": "verify-result", "verdict": "pass",
             "verifier": "independent_replay", "evidence_sha256": "d" * 64},
        ])
        self.assertTrue(report.review_recommended)
        self.assertEqual(contract.skill_id, "roblox-open-door")

    def test_coverage_requires_exact_constraint_roster(self):
        contract = parse_skill_contract(valid_contract())
        rows = [{"constraint_id": "inspect-before-act", "verdict": "not_observed", "verifier": "none"}]
        with self.assertRaisesRegex(ValueError, "exactly match"):
            evaluate_skill_coverage(contract, rows)

    def test_coverage_rejects_duplicate_constraint_labels(self):
        contract = parse_skill_contract(valid_contract())
        rows = [
            {"constraint_id": "inspect-before-act", "verdict": "not_observed", "verifier": "none"},
            {"constraint_id": "inspect-before-act", "verdict": "not_observed", "verifier": "none"},
        ]
        with self.assertRaisesRegex(ValueError, "every constraint exactly once"):
            evaluate_skill_coverage(contract, rows)

    def test_coverage_labels_require_independent_evidence(self):
        contract = parse_skill_contract(valid_contract())
        rows = [
            {"constraint_id": "inspect-before-act", "verdict": "pass", "verifier": "none"},
            {"constraint_id": "verify-result", "verdict": "not_observed", "verifier": "none"},
        ]
        with self.assertRaisesRegex(ValueError, "independent verifier"):
            evaluate_skill_coverage(contract, rows)

    def test_unobserved_cannot_claim_evidence(self):
        contract = parse_skill_contract(valid_contract())
        rows = [
            {"constraint_id": "inspect-before-act", "verdict": "not_observed",
             "verifier": "independent_host", "evidence_sha256": "c" * 64},
            {"constraint_id": "verify-result", "verdict": "not_observed", "verifier": "none"},
        ]
        with self.assertRaisesRegex(ValueError, "must not claim"):
            evaluate_skill_coverage(contract, rows)

    def test_invalid_coverage_threshold_is_rejected(self):
        contract = parse_skill_contract(valid_contract())
        rows = [
            {"constraint_id": "inspect-before-act", "verdict": "not_observed", "verifier": "none"},
            {"constraint_id": "verify-result", "verdict": "not_observed", "verifier": "none"},
        ]
        with self.assertRaisesRegex(ValueError, "from 0 to 1"):
            evaluate_skill_coverage(contract, rows, minimum_coverage=1.1)


if __name__ == "__main__":
    unittest.main()


def test_contract_json_rejects_duplicate_keys_at_every_level():
    raw = json.dumps(valid_contract())
    duplicate_top_level = raw[:-1] + ',"skill_id":"attacker-skill"}'
    with unittest.TestCase().assertRaisesRegex(ValueError, "duplicate JSON object key"):
        parse_skill_contract(duplicate_top_level)

    duplicate_nested = raw.replace('"kind": "owner_consent"', '"kind": "owner_consent","kind":"state_exists"')
    with unittest.TestCase().assertRaisesRegex(ValueError, "duplicate JSON object key"):
        parse_skill_contract(duplicate_nested)


def test_contract_json_rejects_nonstandard_numeric_constants():
    raw = json.dumps(valid_contract()).replace('"max_tokens": 100', '"max_tokens": NaN')
    with unittest.TestCase().assertRaisesRegex(ValueError, "non-standard JSON constant"):
        parse_skill_contract(raw)
