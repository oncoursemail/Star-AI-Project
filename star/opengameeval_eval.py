"""Offline OpenGameEval result and exploration analysis for STAR.

This module parses exported OpenGameEval job records and local, content-minimized
tool traces. It performs no network requests, never reads credentials, executes
no Luau, and does not authorize Studio/game actions or promote skills.

The official benchmark's executable checks remain the source of task outcomes.
Exploration annotations are diagnostic only and are treated as unavailable when
the upstream task leaves them absent or empty.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import comb
import re
from typing import Any, Mapping, Sequence

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,127}\Z")
_PATH_MAX = 512
_MODES = {"EDIT", "PLAY"}
_STATUSES = {"QUEUED", "PENDING", "COMPLETED", "FAILED"}
_SPLITS = {"practice", "validation", "holdout"}


def _identifier(value: object, field: str) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise ValueError(f"{field} must be a bounded identifier")
    return value


def _path(value: object, field: str) -> str:
    if (type(value) is not str or not value or len(value) > _PATH_MAX
            or any(ord(ch) < 32 for ch in value)):
        raise ValueError(f"{field} must be a bounded, printable instance path")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _mode(value: object) -> str:
    if type(value) is not str:
        raise ValueError("mode must be a string")
    normalized = value.strip().strip("[]").upper()
    if normalized not in _MODES:
        raise ValueError(f"unsupported OpenGameEval mode: {value!r}")
    return normalized


def _annotation_names(value: object, field: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if type(value) not in (tuple, list):
        raise ValueError(f"{field} must be a list or tuple")
    names: list[str] = []
    for item in value:
        if type(item) is not str:
            raise ValueError(f"{field} entries must be strings")
        # OpenGameEval task annotations may include a Lua comment after a name.
        name = item.split("--", 1)[0].strip()
        if not name:
            continue
        names.append(_identifier(name, field))
    if not names:
        return None
    if len(set(names)) != len(names):
        raise ValueError(f"{field} must not contain duplicates")
    return tuple(names)


def _annotation_paths(value: object, field: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if type(value) not in (tuple, list):
        raise ValueError(f"{field} must be a list or tuple")
    paths = tuple(_path(item, field) for item in value)
    if not paths:
        return None
    if len(set(paths)) != len(paths):
        raise ValueError(f"{field} must not contain duplicates")
    return paths


@dataclass(frozen=True)
class TaskAnnotations:
    """Private evaluator-side annotations; never include them in agent prompts."""

    expected_tool_calls: tuple[str, ...] | None = None
    expected_script_instances: tuple[str, ...] | None = None
    expected_non_script_instances: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "expected_tool_calls",
            _annotation_names(self.expected_tool_calls, "expected_tool_calls"))
        object.__setattr__(
            self, "expected_script_instances",
            _annotation_paths(self.expected_script_instances,
                              "expected_script_instances"))
        object.__setattr__(
            self, "expected_non_script_instances",
            _annotation_paths(self.expected_non_script_instances,
                              "expected_non_script_instances"))

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "TaskAnnotations":
        if raw is None:
            return cls()
        if not isinstance(raw, Mapping):
            raise TypeError("annotations must be a mapping or None")
        return cls(
            expected_tool_calls=raw.get("expected_tool_calls"),
            expected_script_instances=raw.get("expected_script_instances"),
            expected_non_script_instances=raw.get("expected_non_script_instances"),
        )

    @property
    def expected_instances(self) -> tuple[str, ...] | None:
        values = tuple(dict.fromkeys(
            (self.expected_script_instances or ()) +
            (self.expected_non_script_instances or ())))
        return values or None


@dataclass(frozen=True)
class ToolEvent:
    """Minimal local trace event; no source code, prompts, or raw tool arguments."""

    sequence: int
    operation: str
    tool_name: str
    target_path: str | None = None
    succeeded: bool = True

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("sequence must be a non-negative integer")
        if type(self.operation) is not str or self.operation not in {
                "observe", "edit", "playtest", "other"}:
            raise ValueError("unsupported tool operation")
        _identifier(self.tool_name, "tool_name")
        if self.target_path is not None:
            _path(self.target_path, "target_path")
        if type(self.succeeded) is not bool:
            raise ValueError("succeeded must be boolean")


@dataclass(frozen=True)
class ModeResult:
    mode: str
    passes: int
    fails: int
    checks: int
    warnings: int = 0
    error_present: bool = False
    interruptions: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", _mode(self.mode))
        for field in ("passes", "fails", "checks", "warnings", "interruptions"):
            _nonnegative_int(getattr(self, field), field)
        if self.passes + self.fails != self.checks:
            raise ValueError("passes + fails must equal checks")
        if type(self.error_present) is not bool:
            raise ValueError("error_present must be boolean")

    @property
    def passed(self) -> bool:
        # Zero checks is not a pass. An API error invalidates the result.
        return self.checks > 0 and self.passes == self.checks and not self.error_present


def _warning_count(result: Mapping[str, Any]) -> int:
    value = result.get("warnings", result.get("warning", 0))
    if type(value) is int:
        return _nonnegative_int(value, "warnings")
    if type(value) is str:
        return 1 if value.strip() else 0
    if type(value) in (tuple, list):
        return len(value)
    raise ValueError("warnings must be an integer, string, or list")


def _error_present(result: Mapping[str, Any]) -> bool:
    value = result.get("error", "")
    if type(value) is bool:
        return value
    if type(value) is str:
        return bool(value.strip())
    if value is None:
        return False
    return True


def _interruptions_count(result: Mapping[str, Any]) -> int:
    value = result.get("interruptions", [])
    if type(value) is int:
        return _nonnegative_int(value, "interruptions")
    if type(value) in (tuple, list):
        return len(value)
    raise ValueError("interruptions must be an integer or list")


@dataclass(frozen=True)
class OpenGameEvalAttempt:
    task_id: str
    attempt_id: str
    split: str
    benchmark_revision: str
    environment_revision: str
    agent_revision: str
    status: str
    required_modes: tuple[str, ...] = ("EDIT", "PLAY")
    results: tuple[ModeResult, ...] = ()
    events: tuple[ToolEvent, ...] = ()
    annotations: TaskAnnotations = TaskAnnotations()

    def __post_init__(self) -> None:
        for field in ("task_id", "attempt_id", "benchmark_revision",
                      "environment_revision", "agent_revision"):
            _identifier(getattr(self, field), field)
        if type(self.split) is not str or self.split not in _SPLITS:
            raise ValueError("split must be practice, validation, or holdout")
        if type(self.status) is not str or self.status not in _STATUSES:
            raise ValueError("unknown OpenGameEval job status")
        if type(self.required_modes) not in (tuple, list):
            raise TypeError("required_modes must be a tuple or list")
        modes = tuple(_mode(mode) for mode in self.required_modes)
        if not modes or len(set(modes)) != len(modes):
            raise ValueError("required_modes must be unique and non-empty")
        object.__setattr__(self, "required_modes", modes)
        if type(self.results) not in (tuple, list):
            raise TypeError("results must be a tuple or list")
        results = tuple(self.results)
        if any(not isinstance(row, ModeResult) for row in results):
            raise TypeError("results must contain ModeResult values")
        object.__setattr__(self, "results", results)
        result_modes = [row.mode for row in results]
        if len(set(result_modes)) != len(result_modes):
            raise ValueError("duplicate result mode")
        if type(self.events) not in (tuple, list):
            raise TypeError("events must be a tuple or list")
        events = tuple(self.events)
        if any(not isinstance(event, ToolEvent) for event in events):
            raise TypeError("events must contain ToolEvent values")
        object.__setattr__(self, "events", events)
        sequences = [event.sequence for event in events]
        if sequences != sorted(sequences) or len(set(sequences)) != len(sequences):
            raise ValueError("tool events must have strictly increasing sequence numbers")
        if not isinstance(self.annotations, TaskAnnotations):
            raise TypeError("annotations must be TaskAnnotations")

    @classmethod
    def from_api_record(
        cls, *, task_id: str, attempt_id: str, split: str,
        benchmark_revision: str, environment_revision: str, agent_revision: str,
        record: Mapping[str, Any], required_modes: Sequence[str] = ("EDIT", "PLAY"),
        events: Sequence[ToolEvent] = (),
        annotations: TaskAnnotations | Mapping[str, Any] | None = None,
    ) -> "OpenGameEvalAttempt":
        """Parse an exported API record after the caller verifies its source; no HTTP."""
        if not isinstance(record, Mapping):
            raise TypeError("record must be a mapping")
        status = record.get("status")
        if type(status) is not str:
            raise ValueError("record status is missing")
        raw_results = record.get("results", [])
        if type(raw_results) not in (tuple, list):
            raise ValueError("record results must be a list")
        parsed: list[ModeResult] = []
        for row in raw_results:
            if not isinstance(row, Mapping):
                raise ValueError("each result row must be a mapping")
            payload = row.get("result")
            if not isinstance(payload, Mapping):
                raise ValueError("each result row must contain a result mapping")
            parsed.append(ModeResult(
                mode=row.get("mode"),
                passes=payload.get("passes"),
                fails=payload.get("fails"),
                checks=payload.get("checks"),
                warnings=_warning_count(payload),
                error_present=_error_present(payload),
                interruptions=_interruptions_count(payload),
            ))
        if annotations is None or isinstance(annotations, TaskAnnotations):
            parsed_annotations = annotations or TaskAnnotations()
        else:
            parsed_annotations = TaskAnnotations.from_mapping(annotations)
        return cls(
            task_id=task_id, attempt_id=attempt_id, split=split,
            benchmark_revision=benchmark_revision,
            environment_revision=environment_revision,
            agent_revision=agent_revision, status=status.upper(),
            required_modes=tuple(required_modes), results=tuple(parsed),
            events=tuple(events), annotations=parsed_annotations,
        )

    @property
    def result_by_mode(self) -> dict[str, ModeResult]:
        return {row.mode: row for row in self.results}

    @property
    def completed(self) -> bool:
        return self.status == "COMPLETED"

    @property
    def success(self) -> bool:
        if not self.completed:
            return False
        by_mode = self.result_by_mode
        return all(mode in by_mode and by_mode[mode].passed
                   for mode in self.required_modes)

    def mode_passed(self, mode: str) -> bool:
        result = self.result_by_mode.get(_mode(mode))
        return self.completed and result is not None and result.passed

    @property
    def tool_error_rate(self) -> float | None:
        if not self.events:
            return None
        return sum(not event.succeeded for event in self.events) / len(self.events)

    @property
    def expected_tool_call_recall(self) -> float | None:
        expected = self.annotations.expected_tool_calls
        if not expected:
            return None
        observed = {event.tool_name for event in self.events}
        return sum(name in observed for name in expected) / len(expected)

    @property
    def pre_edit_inspection_coverage(self) -> float | None:
        targets = self.annotations.expected_instances
        if not targets:
            return None
        observed: dict[str, list[int]] = defaultdict(list)
        edited: dict[str, list[int]] = defaultdict(list)
        for event in self.events:
            if (event.succeeded and event.operation == "observe"
                    and event.target_path is not None):
                observed[event.target_path].append(event.sequence)
            elif (event.succeeded and event.operation == "edit"
                  and event.target_path is not None):
                edited[event.target_path].append(event.sequence)
        covered = 0
        for target in targets:
            observations = observed.get(target, [])
            edits = edited.get(target, [])
            if observations and (not edits or min(observations) < min(edits)):
                covered += 1
        return covered / len(targets)

    @property
    def edits_before_observation(self) -> int | None:
        targets = self.annotations.expected_instances
        if not targets:
            return None
        count = 0
        for target in targets:
            observations = [e.sequence for e in self.events
                            if e.succeeded and e.operation == "observe"
                            and e.target_path == target]
            edits = [e.sequence for e in self.events
                     if e.succeeded and e.operation == "edit"
                     and e.target_path == target]
            if edits and (not observations or min(edits) < min(observations)):
                count += 1
        return count


@dataclass(frozen=True)
class TaskMetrics:
    task_id: str
    split: str
    attempts: int
    completed: int
    failed_jobs: int
    pending_jobs: int
    successes: int
    pass_at_k: float | None
    cons_at_k: float | None
    all_at_k: float | None
    edit_pass_rate: float | None
    play_pass_rate: float | None
    tool_error_rate: float | None
    expected_tool_call_recall: float | None
    pre_edit_inspection_coverage: float | None
    edits_before_observation: float | None
    warnings_per_completed_attempt: float | None
    interruptions_per_completed_attempt: float | None


@dataclass(frozen=True)
class BenchmarkReport:
    split: str
    benchmark_revision: str
    agent_revision: str
    k: int
    tasks: tuple[TaskMetrics, ...]
    macro_pass_at_k: float | None
    macro_cons_at_k: float | None
    macro_all_at_k: float | None
    macro_edit_pass_rate: float | None
    macro_play_pass_rate: float | None
    macro_tool_error_rate: float | None
    macro_expected_tool_call_recall: float | None
    macro_pre_edit_inspection_coverage: float | None
    macro_warnings_per_completed_attempt: float | None
    macro_interruptions_per_completed_attempt: float | None
    tasks_scored_at_k: int
    tasks_unscored_at_k: int
    attempts: int
    completed: int
    failed_jobs: int
    pending_jobs: int

    @property
    def completed_job_rate(self) -> float | None:
        return self.completed / self.attempts if self.attempts else None


def _mean(values: Sequence[float | None]) -> float | None:
    usable = [value for value in values if value is not None]
    return sum(usable) / len(usable) if usable else None


def _at_k(successes: int, attempts: int, k: int) -> tuple[float, float, float] | None:
    if attempts < k:
        return None
    denominator = comb(attempts, k)
    failures = attempts - successes
    pass_at_k = 1.0 - (comb(failures, k) / denominator if failures >= k else 0.0)
    threshold = (k // 2) + 1
    consistent = sum(
        comb(successes, wins) * comb(failures, k - wins)
        for wins in range(threshold, k + 1)
        if wins <= successes and k - wins <= failures
    ) / denominator
    all_at_k = comb(successes, k) / denominator if successes >= k else 0.0
    return pass_at_k, consistent, all_at_k


def evaluate_attempts(
    attempts: Sequence[OpenGameEvalAttempt], *, k: int = 5,
) -> BenchmarkReport:
    """Compute task-macro OpenGameEval metrics from completed exported attempts.

    Failed/queued jobs are reported separately and excluded from pass@k
    denominators because they lack a completed evaluator record. A completed
    record missing a required mode or containing an API error is a failed
    attempt. Warnings and interruptions remain diagnostic fields, not silent
    success/failure overrides.
    """
    if type(attempts) not in (tuple, list) or not attempts:
        raise ValueError("provide a non-empty attempt sequence")
    if type(k) is not int or not 1 <= k <= 16:
        raise ValueError("k must be between 1 and 16")
    if any(not isinstance(row, OpenGameEvalAttempt) for row in attempts):
        raise TypeError("attempts must contain OpenGameEvalAttempt values")
    ids = [row.attempt_id for row in attempts]
    if len(set(ids)) != len(ids):
        raise ValueError("attempt_id values must be globally unique")

    run_signatures = {(row.split, row.benchmark_revision, row.agent_revision)
                      for row in attempts}
    if len(run_signatures) != 1:
        raise ValueError("evaluate one split and pinned benchmark/agent revision at a time")
    split, benchmark_revision, agent_revision = next(iter(run_signatures))
    grouped: dict[str, list[OpenGameEvalAttempt]] = defaultdict(list)
    for row in attempts:
        grouped[row.task_id].append(row)

    task_rows: list[TaskMetrics] = []
    for task_id in sorted(grouped):
        rows = grouped[task_id]
        signatures = {(row.split, row.benchmark_revision,
                       row.environment_revision, row.agent_revision,
                       row.required_modes) for row in rows}
        if len(signatures) != 1:
            raise ValueError("task attempts must share split and pinned revisions")
        completed_rows = [row for row in rows if row.completed]
        successes = sum(row.success for row in completed_rows)
        at_k = _at_k(successes, len(completed_rows), k)
        edit_rate = (
            sum(row.mode_passed("EDIT") for row in completed_rows)
            / len(completed_rows)
            if completed_rows and "EDIT" in rows[0].required_modes else None)
        play_rate = (
            sum(row.mode_passed("PLAY") for row in completed_rows)
            / len(completed_rows)
            if completed_rows and "PLAY" in rows[0].required_modes else None)
        events = [event for row in completed_rows for event in row.events]
        error_rate = (sum(not event.succeeded for event in events) / len(events)
                      if events else None)
        tool_recalls = [row.expected_tool_call_recall for row in completed_rows]
        inspections = [row.pre_edit_inspection_coverage for row in completed_rows]
        early_edits = [float(row.edits_before_observation)
                       for row in completed_rows
                       if row.edits_before_observation is not None]
        warnings = [sum(result.warnings for result in row.results)
                    for row in completed_rows]
        interruptions = [sum(result.interruptions for result in row.results)
                         for row in completed_rows]
        task_rows.append(TaskMetrics(
            task_id=task_id, split=rows[0].split,
            attempts=len(rows), completed=len(completed_rows),
            failed_jobs=sum(row.status == "FAILED" for row in rows),
            pending_jobs=sum(row.status in {"QUEUED", "PENDING"} for row in rows),
            successes=successes,
            pass_at_k=at_k[0] if at_k else None,
            cons_at_k=at_k[1] if at_k else None,
            all_at_k=at_k[2] if at_k else None,
            edit_pass_rate=edit_rate, play_pass_rate=play_rate,
            tool_error_rate=error_rate,
            expected_tool_call_recall=_mean(tool_recalls),
            pre_edit_inspection_coverage=_mean(inspections),
            edits_before_observation=_mean(early_edits),
            warnings_per_completed_attempt=_mean(warnings),
            interruptions_per_completed_attempt=_mean(interruptions),
        ))

    return BenchmarkReport(
        split=split, benchmark_revision=benchmark_revision,
        agent_revision=agent_revision, k=k, tasks=tuple(task_rows),
        macro_pass_at_k=_mean([row.pass_at_k for row in task_rows]),
        macro_cons_at_k=_mean([row.cons_at_k for row in task_rows]),
        macro_all_at_k=_mean([row.all_at_k for row in task_rows]),
        macro_edit_pass_rate=_mean([row.edit_pass_rate for row in task_rows]),
        macro_play_pass_rate=_mean([row.play_pass_rate for row in task_rows]),
        macro_tool_error_rate=_mean([row.tool_error_rate for row in task_rows]),
        macro_expected_tool_call_recall=_mean(
            [row.expected_tool_call_recall for row in task_rows]),
        macro_pre_edit_inspection_coverage=_mean(
            [row.pre_edit_inspection_coverage for row in task_rows]),
        macro_warnings_per_completed_attempt=_mean(
            [row.warnings_per_completed_attempt for row in task_rows]),
        macro_interruptions_per_completed_attempt=_mean(
            [row.interruptions_per_completed_attempt for row in task_rows]),
        tasks_scored_at_k=sum(row.pass_at_k is not None for row in task_rows),
        tasks_unscored_at_k=sum(row.pass_at_k is None for row in task_rows),
        attempts=len(attempts),
        completed=sum(row.completed for row in attempts),
        failed_jobs=sum(row.status == "FAILED" for row in attempts),
        pending_jobs=sum(row.status in {"QUEUED", "PENDING"} for row in attempts),
    )
