from dataclasses import replace
import hashlib
import unittest

from star.memory_action_eval import (
    MemoryActionCase,
    MemoryActionManifest,
    MemoryActionReceipt,
    evaluate_memory_action_grounding,
    sign_receipt,
)

KEY = b"star-memory-action-test-key-32-bytes-minimum"
NOW = 1_800_000_000_000


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_manifest(split="holdout", sessions=8):
    cases = []
    domains = ("coding", "gaming", "research", "creator")
    for index in range(sessions):
        session = f"session-{index:02}"
        domain = domains[index % len(domains)]
        first = "memory_off" if index % 2 == 0 else "memory_on"
        required = f"required-{index:02}"
        distractor = f"distractor-{index:02}"
        cases.extend([
            MemoryActionCase(
                f"dependent-{index:02}", session, 0, domain, True,
                (required, distractor), (required,), (distractor,),
                "calendar.create", sha(f"dependent-args-{index}"), first,
            ),
            MemoryActionCase(
                f"independent-{index:02}", session, 1, domain, False,
                (distractor,), (), (distractor,),
                "docs.search", sha(f"independent-args-{index}"), first,
            ),
        ])
    return MemoryActionManifest(
        "memory-action-campaign", split, sha("backbone"), sha("runner"), sha("grader"),
        sha("prompt"), sha("tools"), sha("memory-off"), sha("memory-on"),
        8192, 1024, 2048, tuple(cases),
    )


def make_receipt(manifest, case, arm, *, correct=True, retrieved=None, decision=None,
                 memory_tokens=None, elapsed_ms=1000, retrieval_ms=None, run_suffix=""):
    arm_order = 0 if arm == case.first_arm else 1
    if decision is None:
        decision = "act"
    tool = case.expected_tool_name if decision == "act" else None
    args = case.expected_arguments_sha256 if decision == "act" else None
    if not correct and decision == "act":
        args = sha(f"wrong-args-{case.case_id}-{arm}")
    ids = tuple(retrieved or ())
    tokens = (20 if ids else 0) if memory_tokens is None else memory_tokens
    retrieval = (25 if ids else 0) if retrieval_ms is None else retrieval_ms
    unsigned = MemoryActionReceipt(
        manifest.sha256, case.case_id, case.session_id, arm, arm_order,
        f"run-{case.case_id}-{arm}{run_suffix}", sha(f"evidence-{case.case_id}-{arm}{run_suffix}"),
        decision, tool, args, ids, NOW - 1000, elapsed_ms, retrieval,
        500, 100, tokens,
    )
    return replace(unsigned, signature=sign_receipt(unsigned, KEY))


def receipts_for(manifest, *, dependent_gain=True, independent_harm=False, miss_required=False):
    receipts = []
    for case in manifest.cases:
        for arm in ("memory_off", "memory_on"):
            if case.memory_required:
                correct = arm == "memory_on" if dependent_gain else True
                retrieved = () if arm == "memory_off" or miss_required else case.required_memory_ids
            else:
                correct = not (arm == "memory_on" and independent_harm)
                retrieved = ()
            receipts.append(make_receipt(
                manifest, case, arm, correct=correct, retrieved=retrieved,
                elapsed_ms=1000 if arm == "memory_off" else 1040,
            ))
    return tuple(receipts)


class MemoryActionEvalTests(unittest.TestCase):
    def evaluate(self, manifest, receipts, **kwargs):
        return evaluate_memory_action_grounding(
            manifest, receipts, validation_key=KEY, expected_manifest_sha256=manifest.sha256,
            now_unix_ms=NOW, **kwargs,
        )

    def test_memory_grounding_gain_recommends_manual_review_only(self):
        manifest = build_manifest()
        report = self.evaluate(manifest, receipts_for(manifest))
        self.assertEqual(report.verdict, "manual_review_recommended")
        self.assertEqual(report.completed_pairs, len(manifest.cases))
        self.assertEqual(report.dependent_gain_pp, 100.0)
        self.assertEqual(report.independent_gain_pp, 0.0)
        self.assertEqual(report.required_memory_recall_pp, 100.0)
        self.assertEqual(report.improved_sessions, 8)
        self.assertAlmostEqual(report.session_sign_test_p, 1 / 256)

    def test_development_campaign_never_recommends_holdout_review(self):
        manifest = build_manifest(split="development")
        report = self.evaluate(manifest, receipts_for(manifest))
        self.assertEqual(report.verdict, "development_signal_only")

    def test_independent_task_regression_blocks_positive_transfer(self):
        manifest = build_manifest()
        report = self.evaluate(manifest, receipts_for(manifest, independent_harm=True))
        self.assertEqual(report.verdict, "memory_regressed")
        self.assertEqual(report.independent_gain_pp, -100.0)

    def test_required_memory_miss_prevents_manual_review(self):
        manifest = build_manifest()
        report = self.evaluate(manifest, receipts_for(manifest, miss_required=True))
        self.assertEqual(report.verdict, "inconclusive")
        self.assertEqual(report.required_memory_recall_pp, 0.0)

    def test_missing_arm_is_inconclusive(self):
        manifest = build_manifest()
        report = self.evaluate(manifest, receipts_for(manifest)[:-1])
        self.assertEqual(report.verdict, "inconclusive")
        self.assertEqual(report.incomplete_pairs, 1)

    def test_infrastructure_error_contaminates_campaign(self):
        manifest = build_manifest()
        receipts = list(receipts_for(manifest))
        original = receipts[0]
        bad = replace(original, decision="infra_error", tool_name=None,
                      arguments_sha256=None, signature="")
        receipts[0] = replace(bad, signature=sign_receipt(bad, KEY))
        report = self.evaluate(manifest, receipts)
        self.assertEqual(report.verdict, "contaminated")
        self.assertIsNone(report.overall_gain_pp)

    def test_bad_signature_rejected(self):
        manifest = build_manifest()
        receipts = list(receipts_for(manifest))
        receipts[0] = replace(receipts[0], signature="0" * 64)
        with self.assertRaises(PermissionError):
            self.evaluate(manifest, receipts)

    def test_manifest_mismatch_rejected(self):
        manifest = build_manifest()
        with self.assertRaises(PermissionError):
            evaluate_memory_action_grounding(
                manifest, (), validation_key=KEY, expected_manifest_sha256=sha("wrong"),
                now_unix_ms=NOW,
            )

    def test_memory_off_must_report_zero_memory_activity(self):
        manifest = build_manifest()
        receipts = list(receipts_for(manifest))
        original = next(item for item in receipts if item.arm == "memory_off")
        case = next(item for item in manifest.cases if item.case_id == original.case_id)
        bad = replace(
            original, retrieved_memory_ids=case.available_memory_ids[:1],
            memory_tokens_read=1, retrieval_ms=1, signature="",
        )
        receipts[receipts.index(original)] = replace(bad, signature=sign_receipt(bad, KEY))
        with self.assertRaises(PermissionError):
            self.evaluate(manifest, receipts)

    def test_memory_on_cannot_reference_unavailable_memory(self):
        manifest = build_manifest()
        receipts = list(receipts_for(manifest))
        original = next(item for item in receipts if item.arm == "memory_on" and item.case_id.startswith("dependent"))
        bad = replace(original, retrieved_memory_ids=("not-available",), signature="")
        receipts[receipts.index(original)] = replace(bad, signature=sign_receipt(bad, KEY))
        with self.assertRaises(PermissionError):
            self.evaluate(manifest, receipts)

    def test_memory_budget_is_enforced(self):
        manifest = build_manifest()
        receipts = list(receipts_for(manifest))
        original = next(item for item in receipts if item.arm == "memory_on" and item.retrieved_memory_ids)
        bad = replace(original, memory_tokens_read=manifest.memory_budget_tokens + 1, signature="")
        receipts[receipts.index(original)] = replace(bad, signature=sign_receipt(bad, KEY))
        with self.assertRaises(PermissionError):
            self.evaluate(manifest, receipts)

    def test_duplicate_case_arm_rejected(self):
        manifest = build_manifest()
        receipts = list(receipts_for(manifest))
        duplicate = replace(receipts[0], run_id="fresh-run", evidence_sha256=sha("fresh-evidence"),
                            signature="")
        receipts.append(replace(duplicate, signature=sign_receipt(duplicate, KEY)))
        with self.assertRaises(ValueError):
            self.evaluate(manifest, receipts)

    def test_duplicate_evidence_rejected(self):
        manifest = build_manifest()
        receipts = list(receipts_for(manifest))
        original = receipts[1]
        duplicate = replace(original, run_id="fresh-run", evidence_sha256=receipts[0].evidence_sha256,
                            signature="")
        receipts[1] = replace(duplicate, signature=sign_receipt(duplicate, KEY))
        with self.assertRaises(ValueError):
            self.evaluate(manifest, receipts)

    def test_future_receipt_rejected(self):
        manifest = build_manifest()
        receipts = list(receipts_for(manifest))
        original = receipts[0]
        future = replace(original, observed_unix_ms=NOW + 1, signature="")
        receipts[0] = replace(future, signature=sign_receipt(future, KEY))
        with self.assertRaises(PermissionError):
            self.evaluate(manifest, receipts)

    def test_stale_receipt_rejected(self):
        manifest = build_manifest()
        receipts = list(receipts_for(manifest))
        original = receipts[0]
        stale = replace(original, observed_unix_ms=NOW - 40 * 24 * 60 * 60 * 1000, signature="")
        receipts[0] = replace(stale, signature=sign_receipt(stale, KEY))
        with self.assertRaises(PermissionError):
            self.evaluate(manifest, receipts)

    def test_unnecessary_memory_injection_blocks_acceptance(self):
        manifest = build_manifest()
        receipts = list(receipts_for(manifest))
        for index, receipt in enumerate(receipts):
            case = next(item for item in manifest.cases if item.case_id == receipt.case_id)
            if receipt.arm == "memory_on" and not case.memory_required:
                bad = replace(receipt, retrieved_memory_ids=case.irrelevant_memory_ids,
                              memory_tokens_read=20, retrieval_ms=25, signature="")
                receipts[index] = replace(bad, signature=sign_receipt(bad, KEY))
        report = self.evaluate(manifest, receipts)
        self.assertEqual(report.verdict, "inconclusive")
        self.assertEqual(report.unnecessary_memory_use_pp, 100.0)

    def test_small_holdout_is_inconclusive(self):
        manifest = build_manifest(sessions=4)
        report = self.evaluate(manifest, receipts_for(manifest))
        self.assertEqual(report.verdict, "inconclusive")

    def test_invalid_case_memory_partition_rejected(self):
        with self.assertRaises(ValueError):
            MemoryActionCase(
                "bad", "session", 0, "coding", True, ("a", "b"), ("a",), (),
                "tool.run", sha("args"), "memory_off",
            )

    def test_memory_required_flag_must_match_evidence(self):
        with self.assertRaises(ValueError):
            MemoryActionCase(
                "bad", "session", 0, "coding", False, ("a",), ("a",), (),
                "tool.run", sha("args"), "memory_off",
            )

    def test_campaign_requires_dependent_and_independent_cases_per_session(self):
        manifest = build_manifest()
        first = manifest.cases[0]
        cases = tuple(case for case in manifest.cases if case.case_id != "independent-00")
        with self.assertRaises(ValueError):
            MemoryActionManifest(
                manifest.campaign_id, manifest.split, manifest.backbone_sha256,
                manifest.runner_sha256, manifest.grader_sha256, manifest.prompt_template_sha256,
                manifest.tool_policy_sha256, manifest.memory_off_policy_sha256,
                manifest.memory_on_policy_sha256, manifest.context_budget_tokens,
                manifest.output_budget_tokens, manifest.memory_budget_tokens, cases,
            )

    def test_receipt_tool_and_argument_digest_must_be_paired(self):
        manifest = build_manifest()
        case = manifest.cases[0]
        with self.assertRaises(ValueError):
            MemoryActionReceipt(
                manifest.sha256, case.case_id, case.session_id, "memory_off", 0, "run",
                sha("evidence"), "act", "calendar.create", None, (), NOW, 100, 0, 10, 10, 0,
            )


if __name__ == "__main__":
    unittest.main()
