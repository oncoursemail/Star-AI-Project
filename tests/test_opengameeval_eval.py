import unittest

from star.opengameeval_eval import (
    ModeResult,
    OpenGameEvalAttempt,
    TaskAnnotations,
    ToolEvent,
    evaluate_attempts,
)


def attempt(task, n, *, success=True, split="validation", status="COMPLETED",
            required=("EDIT", "PLAY"), annotations=None, events=None,
            revision="oeval-2026-11"):
    results = ()
    if status == "COMPLETED":
        results = (
            ModeResult("EDIT", 2 if success else 1, 0 if success else 1, 2),
            ModeResult("PLAY", 1 if success else 0, 0 if success else 1, 1),
        )
    return OpenGameEvalAttempt(
        task_id=task, attempt_id=f"{task}-{n}", split=split,
        benchmark_revision=revision, environment_revision="place-sha",
        agent_revision="agent-sha", status=status, required_modes=required,
        results=results, annotations=annotations or TaskAnnotations(),
        events=tuple(events or ()),
    )


class OpenGameEvalTests(unittest.TestCase):
    def test_all_required_modes_must_pass(self):
        row = attempt("task_a", 1, success=True)
        self.assertTrue(row.success)
        edit_only = OpenGameEvalAttempt(
            task_id="task_b", attempt_id="task-b-1", split="validation",
            benchmark_revision="r1", environment_revision="e1",
            agent_revision="a1", status="COMPLETED",
            required_modes=("EDIT", "PLAY"),
            results=(ModeResult("EDIT", 1, 0, 1),),
        )
        self.assertFalse(edit_only.success)

    def test_zero_checks_never_counts_as_success(self):
        row = ModeResult("EDIT", 0, 0, 0)
        self.assertFalse(row.passed)

    def test_passes_fails_must_match_checks(self):
        with self.assertRaises(ValueError):
            ModeResult("EDIT", 2, 0, 3)

    def test_api_record_parses_edit_and_play_modes(self):
        row = OpenGameEvalAttempt.from_api_record(
            task_id="scene_01", attempt_id="run_1", split="validation",
            benchmark_revision="r1", environment_revision="e1",
            agent_revision="a1",
            record={"status": "COMPLETED", "results": [
                {"mode": "[EDIT]", "result": {
                    "passes": 2, "fails": 0, "checks": 2,
                    "warnings": 1, "error": "", "interruptions": []}},
                {"mode": "[PLAY]", "result": {
                    "passes": 1, "fails": 0, "checks": 1,
                    "warning": "", "error": "", "interruptions": [1]}},
            ]},
        )
        self.assertTrue(row.success)
        self.assertEqual(row.result_by_mode["EDIT"].warnings, 1)
        self.assertEqual(row.result_by_mode["PLAY"].interruptions, 1)

    def test_api_error_invalidates_mode_even_when_checks_pass(self):
        row = OpenGameEvalAttempt.from_api_record(
            task_id="scene_02", attempt_id="run_2", split="validation",
            benchmark_revision="r1", environment_revision="e1",
            agent_revision="a1",
            record={"status": "COMPLETED", "results": [
                {"mode": "EDIT", "result": {
                    "passes": 1, "fails": 0, "checks": 1,
                    "error": "runtime error"}},
                {"mode": "PLAY", "result": {
                    "passes": 1, "fails": 0, "checks": 1}},
            ]},
        )
        self.assertFalse(row.success)

    def test_duplicate_modes_are_rejected(self):
        with self.assertRaises(ValueError):
            OpenGameEvalAttempt(
                task_id="task_a", attempt_id="run_3", split="validation",
                benchmark_revision="r1", environment_revision="e1",
                agent_revision="a1", status="COMPLETED",
                results=(ModeResult("EDIT", 1, 0, 1),
                         ModeResult("[EDIT]", 1, 0, 1)),
            )

    def test_task_annotations_empty_means_unavailable(self):
        annotation = TaskAnnotations.from_mapping({
            "expected_tool_calls": [],
            "expected_script_instances": [],
            "expected_non_script_instances": [],
        })
        self.assertIsNone(annotation.expected_tool_calls)
        self.assertIsNone(annotation.expected_instances)

    def test_expected_tool_calls_strip_lua_comments(self):
        annotation = TaskAnnotations.from_mapping({
            "expected_tool_calls": ["game_tree -- find the model", "inspect_instance"],
        })
        self.assertEqual(annotation.expected_tool_calls,
                         ("game_tree", "inspect_instance"))

    def test_pre_edit_inspection_coverage_uses_sequence_order(self):
        annotation = TaskAnnotations(
            expected_script_instances=("game.ServerScriptService.Main",),
            expected_non_script_instances=("game.Workspace.Door",),
        )
        events = (
            ToolEvent(1, "observe", "inspect_instance",
                      "game.ServerScriptService.Main"),
            ToolEvent(2, "edit", "execute_luau",
                      "game.ServerScriptService.Main"),
            ToolEvent(3, "edit", "set_property", "game.Workspace.Door"),
            ToolEvent(4, "observe", "inspect_instance", "game.Workspace.Door"),
        )
        row = attempt("task_a", 1, annotations=annotation, events=events)
        self.assertEqual(row.pre_edit_inspection_coverage, 0.5)
        self.assertEqual(row.edits_before_observation, 1)

    def test_observation_without_later_edit_counts_as_inspected(self):
        annotation = TaskAnnotations(expected_non_script_instances=(
            "game.Workspace.Lights",))
        row = attempt("task_a", 1, annotations=annotation, events=(
            ToolEvent(1, "observe", "inspect_instance", "game.Workspace.Lights"),
        ))
        self.assertEqual(row.pre_edit_inspection_coverage, 1.0)
        self.assertEqual(row.edits_before_observation, 0)

    def test_unannotated_tasks_do_not_receive_zero_exploration_score(self):
        row = attempt("task_a", 1)
        self.assertIsNone(row.pre_edit_inspection_coverage)
        self.assertIsNone(row.expected_tool_call_recall)

    def test_failed_observation_does_not_count_as_exploration(self):
        annotation = TaskAnnotations(expected_non_script_instances=(
            "game.Workspace.Lights",))
        row = attempt("task_a", 1, annotations=annotation, events=(
            ToolEvent(1, "observe", "inspect_instance",
                      "game.Workspace.Lights", succeeded=False),
        ))
        self.assertEqual(row.pre_edit_inspection_coverage, 0.0)

    def test_tool_error_rate_is_diagnostic(self):
        row = attempt("task_a", 1, success=True, events=(
            ToolEvent(1, "observe", "game_tree", succeeded=True),
            ToolEvent(2, "edit", "execute_luau", succeeded=False),
        ))
        self.assertTrue(row.success)
        self.assertEqual(row.tool_error_rate, 0.5)

    def test_tool_recall_and_warning_metrics_are_separate(self):
        row = OpenGameEvalAttempt(
            task_id="task_a", attempt_id="task-a-metrics", split="validation",
            benchmark_revision="r1", environment_revision="e1",
            agent_revision="a1", status="COMPLETED",
            results=(ModeResult("EDIT", 1, 0, 1, warnings=2),
                     ModeResult("PLAY", 1, 0, 1, interruptions=1)),
            events=(ToolEvent(1, "observe", "game_tree"),),
            annotations=TaskAnnotations(expected_tool_calls=(
                "game_tree", "inspect_instance")),
        )
        report = evaluate_attempts([row], k=1)
        self.assertEqual(row.expected_tool_call_recall, 0.5)
        self.assertEqual(report.tasks[0].warnings_per_completed_attempt, 2.0)
        self.assertEqual(report.tasks[0].interruptions_per_completed_attempt, 1.0)

    def test_pass_consistency_and_all_at_k(self):
        rows = [attempt("task_a", i, success=i < 4) for i in range(1, 6)]
        report = evaluate_attempts(rows, k=5)
        metrics = report.tasks[0]
        self.assertEqual(metrics.successes, 3)
        self.assertEqual(metrics.pass_at_k, 1.0)
        self.assertEqual(metrics.cons_at_k, 1.0)
        self.assertEqual(metrics.all_at_k, 0.0)

    def test_pass_at_k_is_missing_when_too_few_completed_attempts(self):
        rows = [attempt("task_a", 1), attempt("task_a", 2, status="FAILED")]
        report = evaluate_attempts(rows, k=2)
        self.assertIsNone(report.tasks[0].pass_at_k)
        self.assertEqual(report.failed_jobs, 1)

    def test_failed_jobs_are_reported_not_scored_as_completed(self):
        rows = [
            attempt("task_a", 1, success=True),
            attempt("task_a", 2, status="FAILED"),
            attempt("task_a", 3, status="PENDING"),
        ]
        report = evaluate_attempts(rows, k=1)
        self.assertEqual((report.attempts, report.completed,
                          report.failed_jobs, report.pending_jobs), (3, 1, 1, 1))
        self.assertEqual(report.completed_job_rate, 1 / 3)
        self.assertEqual(report.tasks[0].successes, 1)

    def test_duplicate_attempt_ids_are_rejected(self):
        first = attempt("task_a", 1)
        second = OpenGameEvalAttempt(
            task_id="task_b", attempt_id=first.attempt_id, split="validation",
            benchmark_revision="oeval-2026-11", environment_revision="place-sha",
            agent_revision="agent-sha", status="COMPLETED",
            results=(ModeResult("EDIT", 2, 0, 2),
                     ModeResult("PLAY", 1, 0, 1)),
        )
        with self.assertRaises(ValueError):
            evaluate_attempts([first, second], k=1)

    def test_revision_or_split_mismatch_is_rejected(self):
        rows = [
            attempt("task_a", 1),
            attempt("task_a", 2, revision="different"),
        ]
        with self.assertRaises(ValueError):
            evaluate_attempts(rows, k=1)

    def test_macro_scores_average_tasks_not_attempts(self):
        rows = [
            attempt("task_a", 1, success=True),
            attempt("task_a", 2, success=True),
            attempt("task_b", 1, success=False),
        ]
        report = evaluate_attempts(rows, k=1)
        self.assertAlmostEqual(report.macro_pass_at_k, 0.5)

    def test_unknown_status_and_mode_are_rejected(self):
        with self.assertRaises(ValueError):
            OpenGameEvalAttempt(
                task_id="task_a", attempt_id="run", split="validation",
                benchmark_revision="r1", environment_revision="e1",
                agent_revision="a1", status="DONE",
            )
        with self.assertRaises(ValueError):
            ModeResult("TRAIN", 1, 0, 1)

    def test_tool_events_must_be_ordered_and_unique(self):
        with self.assertRaises(ValueError):
            attempt("task_a", 1, events=(
                ToolEvent(2, "observe", "game_tree"),
                ToolEvent(1, "edit", "execute_luau"),
            ))
        with self.assertRaises(ValueError):
            attempt("task_a", 1, events=(
                ToolEvent(1, "observe", "game_tree"),
                ToolEvent(1, "edit", "execute_luau"),
            ))

    def test_k_is_bounded(self):
        with self.assertRaises(ValueError):
            evaluate_attempts([attempt("task_a", 1)], k=17)

    def test_splits_cannot_be_mixed_in_one_report(self):
        rows = [
            attempt("task_a", 1, split="validation"),
            attempt("task_b", 1, split="holdout"),
        ]
        with self.assertRaises(ValueError):
            evaluate_attempts(rows, k=1)


if __name__ == "__main__":
    unittest.main()
