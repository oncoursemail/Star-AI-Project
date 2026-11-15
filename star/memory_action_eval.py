"""Content-free evaluation of long-term memory applied to tool arguments.

This complements continual_learning_eval.py: that module measures transfer and
retention across task streams; this module measures whether retrieved memories
are actually used to choose the right tool and ground its parameters.

The evaluator never executes tools or stores prompts, memory values, transcripts,
or raw arguments. A trusted host supplies HMAC-signed receipts containing only
opaque memory IDs and SHA-256 digests. A positive holdout result recommends
manual review only; it never promotes a memory policy automatically.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import math
import re
from statistics import median
from typing import Sequence

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/+-]{0,95}$")
_TOOL = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,95}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ARMS = {"memory_off", "memory_on"}
_DECISIONS = {"act", "abstain", "timeout", "infra_error"}
_MAX_CASES = 512
_MAX_RECEIPTS = 2_048
_MAX_MEMORY_IDS = 64
_MAX_TOKENS = 2_000_000
_MAX_ELAPSED_MS = 3_600_000
_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1_000


def _id(value: object, label: str) -> None:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise ValueError(f"invalid {label}")


def _sha(value: object, label: str) -> None:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise ValueError(f"invalid {label}")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("ascii")


def _percent(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(100.0 * numerator / denominator, 4)


def _sign_test_p(improved: int, worse: int) -> float:
    """Exact one-sided sign-test probability over independent sessions."""
    trials = improved + worse
    if trials == 0:
        return 1.0
    return sum(math.comb(trials, count) for count in range(improved, trials + 1)) / (2 ** trials)


@dataclass(frozen=True)
class MemoryActionCase:
    """One synthetic, preregistered task; no prompt or memory value is stored."""

    case_id: str
    session_id: str
    sequence: int
    domain: str
    memory_required: bool
    available_memory_ids: tuple[str, ...]
    required_memory_ids: tuple[str, ...]
    irrelevant_memory_ids: tuple[str, ...]
    expected_tool_name: str | None
    expected_arguments_sha256: str | None
    first_arm: str

    def __post_init__(self) -> None:
        for name in ("case_id", "session_id", "domain"):
            _id(getattr(self, name), name)
        if type(self.sequence) is not int or not 0 <= self.sequence <= 4_095:
            raise ValueError("invalid case sequence")
        if type(self.memory_required) is not bool:
            raise ValueError("memory_required must be boolean")
        if self.first_arm not in _ARMS:
            raise ValueError("invalid first arm")
        for name in ("available_memory_ids", "required_memory_ids", "irrelevant_memory_ids"):
            values = getattr(self, name)
            if type(values) is not tuple or len(values) > _MAX_MEMORY_IDS:
                raise ValueError(f"{name} must be a bounded tuple")
            for value in values:
                _id(value, name)
            if len(set(values)) != len(values):
                raise ValueError(f"duplicate value in {name}")
        available = set(self.available_memory_ids)
        required = set(self.required_memory_ids)
        irrelevant = set(self.irrelevant_memory_ids)
        if required & irrelevant or required | irrelevant != available:
            raise ValueError("available memory must be partitioned into required and irrelevant IDs")
        if not required <= available or not irrelevant <= available:
            raise ValueError("memory labels must refer to available evidence")
        if self.memory_required != bool(required):
            raise ValueError("memory_required must match required_memory_ids")
        if (self.expected_tool_name is None) != (self.expected_arguments_sha256 is None):
            raise ValueError("expected tool and argument digest must both be present or absent")
        if self.expected_tool_name is not None:
            if type(self.expected_tool_name) is not str or _TOOL.fullmatch(self.expected_tool_name) is None:
                raise ValueError("invalid expected tool name")
            _sha(self.expected_arguments_sha256, "expected arguments digest")


@dataclass(frozen=True)
class MemoryActionManifest:
    """Pinned paired experiment; only the memory policy may differ."""

    campaign_id: str
    split: str
    backbone_sha256: str
    runner_sha256: str
    grader_sha256: str
    prompt_template_sha256: str
    tool_policy_sha256: str
    memory_off_policy_sha256: str
    memory_on_policy_sha256: str
    context_budget_tokens: int
    output_budget_tokens: int
    memory_budget_tokens: int
    cases: tuple[MemoryActionCase, ...]

    def __post_init__(self) -> None:
        _id(self.campaign_id, "campaign ID")
        if self.split not in {"development", "holdout"}:
            raise ValueError("split must be development or holdout")
        for name in (
            "backbone_sha256", "runner_sha256", "grader_sha256", "prompt_template_sha256",
            "tool_policy_sha256", "memory_off_policy_sha256", "memory_on_policy_sha256",
        ):
            _sha(getattr(self, name), name)
        if self.memory_off_policy_sha256 == self.memory_on_policy_sha256:
            raise ValueError("memory policies must differ")
        for name, low, high in (
            ("context_budget_tokens", 512, 2_000_000),
            ("output_budget_tokens", 1, 65_536),
            ("memory_budget_tokens", 1, 1_000_000),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"invalid {name}")
        if type(self.cases) is not tuple or not 8 <= len(self.cases) <= _MAX_CASES:
            raise ValueError("campaign requires 8..512 cases")
        if any(not isinstance(case, MemoryActionCase) for case in self.cases):
            raise TypeError("cases must be MemoryActionCase values")
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("duplicate case ID")

        sessions: dict[str, list[MemoryActionCase]] = {}
        for case in self.cases:
            sessions.setdefault(case.session_id, []).append(case)
        if not 4 <= len(sessions) <= 128:
            raise ValueError("campaign requires 4..128 independent sessions")
        first_arms = [items[0].first_arm for items in sessions.values()]
        if abs(first_arms.count("memory_off") - first_arms.count("memory_on")) > 1:
            raise ValueError("session first-arm assignment must be balanced")
        for items in sessions.values():
            items.sort(key=lambda item: item.sequence)
            if len({item.sequence for item in items}) != len(items):
                raise ValueError("duplicate sequence within session")
            if len({item.first_arm for item in items}) != 1:
                raise ValueError("first-arm assignment changed within session")
            if not any(item.memory_required for item in items):
                raise ValueError("each session needs a memory-dependent case")
            if not any(not item.memory_required for item in items):
                raise ValueError("each session needs an independent case")

    def canonical_dict(self) -> dict:
        return {
            "schema": 1,
            "campaign_id": self.campaign_id,
            "split": self.split,
            "backbone_sha256": self.backbone_sha256,
            "runner_sha256": self.runner_sha256,
            "grader_sha256": self.grader_sha256,
            "prompt_template_sha256": self.prompt_template_sha256,
            "tool_policy_sha256": self.tool_policy_sha256,
            "memory_off_policy_sha256": self.memory_off_policy_sha256,
            "memory_on_policy_sha256": self.memory_on_policy_sha256,
            "context_budget_tokens": self.context_budget_tokens,
            "output_budget_tokens": self.output_budget_tokens,
            "memory_budget_tokens": self.memory_budget_tokens,
            "cases": [
                {
                    "case_id": case.case_id,
                    "session_id": case.session_id,
                    "sequence": case.sequence,
                    "domain": case.domain,
                    "memory_required": case.memory_required,
                    "available_memory_ids": list(case.available_memory_ids),
                    "required_memory_ids": list(case.required_memory_ids),
                    "irrelevant_memory_ids": list(case.irrelevant_memory_ids),
                    "expected_tool_name": case.expected_tool_name,
                    "expected_arguments_sha256": case.expected_arguments_sha256,
                    "first_arm": case.first_arm,
                }
                for case in self.cases
            ],
        }

    @property
    def sha256(self) -> str:
        return hashlib.sha256(
            b"star.memory-action.manifest.v1\x00" + _canonical(self.canonical_dict())
        ).hexdigest()


@dataclass(frozen=True)
class MemoryActionReceipt:
    """Trusted host receipt; no prompt, memory content, or raw tool arguments."""

    manifest_sha256: str
    case_id: str
    session_id: str
    arm: str
    arm_order: int
    run_id: str
    evidence_sha256: str
    decision: str
    tool_name: str | None
    arguments_sha256: str | None
    retrieved_memory_ids: tuple[str, ...]
    observed_unix_ms: int
    elapsed_ms: int
    retrieval_ms: int
    input_tokens: int
    output_tokens: int
    memory_tokens_read: int
    signature: str = ""

    def __post_init__(self) -> None:
        _sha(self.manifest_sha256, "manifest digest")
        _id(self.case_id, "case ID")
        _id(self.session_id, "session ID")
        _id(self.run_id, "run ID")
        _sha(self.evidence_sha256, "evidence digest")
        if self.arm not in _ARMS or type(self.arm_order) is not int or self.arm_order not in (0, 1):
            raise ValueError("invalid arm or arm order")
        if self.decision not in _DECISIONS:
            raise ValueError("invalid decision")
        if self.decision == "act":
            if type(self.tool_name) is not str or _TOOL.fullmatch(self.tool_name) is None:
                raise ValueError("act decision requires a valid tool name")
            _sha(self.arguments_sha256, "arguments digest")
        elif self.tool_name is not None or self.arguments_sha256 is not None:
            raise ValueError("non-act decision cannot carry a tool or argument digest")
        if type(self.retrieved_memory_ids) is not tuple or len(self.retrieved_memory_ids) > _MAX_MEMORY_IDS:
            raise ValueError("retrieved_memory_ids must be a bounded tuple")
        for value in self.retrieved_memory_ids:
            _id(value, "retrieved memory ID")
        if len(set(self.retrieved_memory_ids)) != len(self.retrieved_memory_ids):
            raise ValueError("duplicate retrieved memory ID")
        for name, low, high in (
            ("observed_unix_ms", 1, 10**14),
            ("elapsed_ms", 1, _MAX_ELAPSED_MS),
            ("retrieval_ms", 0, _MAX_ELAPSED_MS),
            ("input_tokens", 0, _MAX_TOKENS),
            ("output_tokens", 0, _MAX_TOKENS),
            ("memory_tokens_read", 0, _MAX_TOKENS),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"invalid {name}")
        if self.retrieval_ms > self.elapsed_ms:
            raise ValueError("retrieval time cannot exceed total elapsed time")
        if bool(self.retrieved_memory_ids) != bool(self.memory_tokens_read):
            raise ValueError("retrieved memory IDs and memory token reads must agree")
        if type(self.signature) is not str or (self.signature and _SHA.fullmatch(self.signature) is None):
            raise ValueError("invalid receipt signature")


@dataclass(frozen=True)
class MemoryActionReport:
    verdict: str
    split: str
    case_count: int
    completed_pairs: int
    incomplete_pairs: int
    session_count: int
    domain_count: int
    memory_off_accuracy_pp: float | None
    memory_on_accuracy_pp: float | None
    overall_gain_pp: float | None
    dependent_gain_pp: float | None
    independent_gain_pp: float | None
    tool_accuracy_pp: float | None
    argument_accuracy_pp: float | None
    required_memory_recall_pp: float | None
    required_memory_precision_pp: float | None
    unnecessary_memory_use_pp: float | None
    median_retrieval_ms: float | None
    median_elapsed_overhead_ms: float | None
    improved_sessions: int
    worse_sessions: int
    tied_sessions: int
    session_sign_test_p: float | None
    warnings: tuple[str, ...]


def _receipt_payload(receipt: MemoryActionReceipt) -> dict:
    return {
        "manifest_sha256": receipt.manifest_sha256,
        "case_id": receipt.case_id,
        "session_id": receipt.session_id,
        "arm": receipt.arm,
        "arm_order": receipt.arm_order,
        "run_id": receipt.run_id,
        "evidence_sha256": receipt.evidence_sha256,
        "decision": receipt.decision,
        "tool_name": receipt.tool_name,
        "arguments_sha256": receipt.arguments_sha256,
        "retrieved_memory_ids": list(receipt.retrieved_memory_ids),
        "observed_unix_ms": receipt.observed_unix_ms,
        "elapsed_ms": receipt.elapsed_ms,
        "retrieval_ms": receipt.retrieval_ms,
        "input_tokens": receipt.input_tokens,
        "output_tokens": receipt.output_tokens,
        "memory_tokens_read": receipt.memory_tokens_read,
    }


def sign_receipt(receipt: MemoryActionReceipt, key: bytes) -> str:
    """Sign a content-free receipt with a host-only key."""
    if type(key) is not bytes or len(key) < 32:
        raise ValueError("validation key must contain at least 32 bytes")
    return hmac.new(
        key, b"star.memory-action.receipt.v1\x00" + _canonical(_receipt_payload(receipt)),
        hashlib.sha256,
    ).hexdigest()


def _correct(case: MemoryActionCase, receipt: MemoryActionReceipt) -> bool:
    if case.expected_tool_name is None:
        return receipt.decision == "abstain"
    return (
        receipt.decision == "act"
        and receipt.tool_name == case.expected_tool_name
        and receipt.arguments_sha256 == case.expected_arguments_sha256
    )


def _tool_correct(case: MemoryActionCase, receipt: MemoryActionReceipt) -> bool:
    if case.expected_tool_name is None:
        return receipt.decision == "abstain"
    return receipt.decision == "act" and receipt.tool_name == case.expected_tool_name


def _argument_correct(case: MemoryActionCase, receipt: MemoryActionReceipt) -> bool:
    return (
        case.expected_tool_name is not None
        and receipt.decision == "act"
        and receipt.tool_name == case.expected_tool_name
        and receipt.arguments_sha256 == case.expected_arguments_sha256
    )


def evaluate_memory_action_grounding(
    manifest: MemoryActionManifest,
    receipts: Sequence[MemoryActionReceipt],
    *,
    validation_key: bytes,
    expected_manifest_sha256: str,
    now_unix_ms: int,
    max_receipt_age_ms: int = _MAX_AGE_MS,
    minimum_sessions: int = 8,
    minimum_domains: int = 3,
    minimum_dependent_gain_pp: float = 5.0,
    maximum_independent_regression_pp: float = 5.0,
    minimum_required_memory_recall_pp: float = 80.0,
    maximum_unnecessary_memory_use_pp: float = 20.0,
    alpha: float = 0.05,
) -> MemoryActionReport:
    """Evaluate paired memory-off/on tool proposals without executing the tools.

    The trusted host must independently grade the proposed action and sign the
    receipt. The holdout manifest and its expected argument digests stay outside
    model/tool context. A positive verdict is a manual-review recommendation only.
    """
    if not isinstance(manifest, MemoryActionManifest):
        raise TypeError("manifest must be a MemoryActionManifest")
    if type(validation_key) is not bytes or len(validation_key) < 32:
        raise ValueError("validation key must contain at least 32 bytes")
    _sha(expected_manifest_sha256, "expected manifest digest")
    if not hmac.compare_digest(manifest.sha256, expected_manifest_sha256):
        raise PermissionError("manifest does not match the preregistered digest")
    if type(now_unix_ms) is not int or now_unix_ms <= 0:
        raise ValueError("now_unix_ms must be a positive integer")
    if type(max_receipt_age_ms) is not int or not 1 <= max_receipt_age_ms <= _MAX_AGE_MS:
        raise ValueError("invalid maximum receipt age")
    if type(minimum_sessions) is not int or not 4 <= minimum_sessions <= 128:
        raise ValueError("invalid minimum session count")
    if type(minimum_domains) is not int or not 1 <= minimum_domains <= 128:
        raise ValueError("invalid minimum domain count")
    for name, value in (
        ("minimum_dependent_gain_pp", minimum_dependent_gain_pp),
        ("maximum_independent_regression_pp", maximum_independent_regression_pp),
        ("minimum_required_memory_recall_pp", minimum_required_memory_recall_pp),
        ("maximum_unnecessary_memory_use_pp", maximum_unnecessary_memory_use_pp),
        ("alpha", alpha),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    if not 0.0 <= minimum_dependent_gain_pp <= 100.0:
        raise ValueError("invalid minimum dependent gain")
    if not 0.0 <= maximum_independent_regression_pp <= 100.0:
        raise ValueError("invalid maximum independent regression")
    if not 0.0 <= minimum_required_memory_recall_pp <= 100.0:
        raise ValueError("invalid required-memory recall threshold")
    if not 0.0 <= maximum_unnecessary_memory_use_pp <= 100.0:
        raise ValueError("invalid unnecessary-memory threshold")
    if not 0.0 < alpha <= 0.5:
        raise ValueError("alpha must be in (0, 0.5]")
    if not isinstance(receipts, Sequence) or isinstance(receipts, (str, bytes, bytearray)):
        raise TypeError("receipts must be a sequence")
    if len(receipts) > _MAX_RECEIPTS:
        raise ValueError("receipt count exceeds its bounded limit")

    cases = {case.case_id: case for case in manifest.cases}
    paired: dict[tuple[str, str], MemoryActionReceipt] = {}
    seen_runs: set[str] = set()
    seen_evidence: set[str] = set()
    infrastructure_error = False

    for receipt in receipts:
        if not isinstance(receipt, MemoryActionReceipt):
            raise TypeError("receipts must contain MemoryActionReceipt values")
        expected_signature = hmac.new(
            validation_key,
            b"star.memory-action.receipt.v1\x00" + _canonical(_receipt_payload(receipt)),
            hashlib.sha256,
        ).hexdigest()
        if not receipt.signature or not hmac.compare_digest(receipt.signature, expected_signature):
            raise PermissionError("receipt signature is missing or invalid")
        if receipt.manifest_sha256 != manifest.sha256:
            raise PermissionError("receipt is bound to a different manifest")
        case = cases.get(receipt.case_id)
        if case is None or receipt.session_id != case.session_id:
            raise ValueError("receipt references an unknown case or wrong session")
        expected_order = 0 if receipt.arm == case.first_arm else 1
        if receipt.arm_order != expected_order:
            raise PermissionError("receipt arm order differs from the preregistered order")
        if receipt.observed_unix_ms > now_unix_ms or now_unix_ms - receipt.observed_unix_ms > max_receipt_age_ms:
            raise PermissionError("receipt timestamp is future-dated or stale")
        if receipt.run_id in seen_runs or receipt.evidence_sha256 in seen_evidence:
            raise ValueError("duplicate run or evidence receipt")
        seen_runs.add(receipt.run_id)
        seen_evidence.add(receipt.evidence_sha256)
        key = (receipt.case_id, receipt.arm)
        if key in paired:
            raise ValueError("duplicate case/arm receipt")
        if receipt.arm == "memory_off":
            if receipt.retrieved_memory_ids or receipt.memory_tokens_read or receipt.retrieval_ms:
                raise PermissionError("memory-off arm reported memory activity")
        else:
            if receipt.memory_tokens_read > manifest.memory_budget_tokens:
                raise PermissionError("memory budget exceeded")
            if not set(receipt.retrieved_memory_ids) <= set(case.available_memory_ids):
                raise PermissionError("receipt references memory not available to the case")
        infrastructure_error = infrastructure_error or receipt.decision == "infra_error"
        paired[key] = receipt

    expected_pairs = len(manifest.cases) * 2
    completed_pairs = sum(
        (case.case_id, "memory_off") in paired and (case.case_id, "memory_on") in paired
        for case in manifest.cases
    )
    incomplete_pairs = len(manifest.cases) - completed_pairs
    session_count = len({case.session_id for case in manifest.cases})
    domain_count = len({case.domain for case in manifest.cases})
    base_warnings = (
        "No tools are executed by this evaluator.",
        "Memory payloads, prompts, transcripts, and raw arguments are not retained.",
        "A positive holdout verdict authorizes manual review only; it never promotes memory policy.",
    )

    if infrastructure_error:
        return MemoryActionReport(
            "contaminated", manifest.split, len(manifest.cases), completed_pairs, incomplete_pairs,
            session_count, domain_count, None, None, None, None, None, None, None, None, None,
            None, None, None, 0, 0, 0, None,
            base_warnings + ("An infrastructure error contaminated the paired campaign.",),
        )
    if incomplete_pairs or len(paired) != expected_pairs:
        return MemoryActionReport(
            "inconclusive", manifest.split, len(manifest.cases), completed_pairs, incomplete_pairs,
            session_count, domain_count, None, None, None, None, None, None, None, None, None,
            None, None, None, 0, 0, 0, None,
            base_warnings + ("Every case requires exactly one receipt from each arm.",),
        )
    for case in manifest.cases:
        first_receipt = paired[(case.case_id, case.first_arm)]
        second_arm = "memory_on" if case.first_arm == "memory_off" else "memory_off"
        second_receipt = paired[(case.case_id, second_arm)]
        if first_receipt.observed_unix_ms >= second_receipt.observed_unix_ms:
            raise PermissionError("receipt timestamps contradict the preregistered arm order")

    session_pairs: dict[str, list[tuple[bool, bool]]] = {}
    session_dependent_deltas: dict[str, list[float]] = {}
    session_independent_deltas: dict[str, list[float]] = {}
    retrieval_hits = 0
    required_count = 0
    relevant_retrieved = 0
    all_retrieved_for_dependent = 0
    unnecessary_cases = 0
    independent_cases = 0
    tool_correct_count = 0
    action_case_count = 0
    argument_correct_count = 0
    retrieval_times: list[int] = []
    elapsed_overheads: list[int] = []

    for case in manifest.cases:
        off = paired[(case.case_id, "memory_off")]
        on = paired[(case.case_id, "memory_on")]
        off_ok = _correct(case, off)
        on_ok = _correct(case, on)
        delta = float(on_ok) - float(off_ok)
        session_pairs.setdefault(case.session_id, []).append((off_ok, on_ok))
        if case.memory_required:
            session_dependent_deltas.setdefault(case.session_id, []).append(delta)
            required = set(case.required_memory_ids)
            retrieved = set(on.retrieved_memory_ids)
            required_count += len(required)
            retrieval_hits += len(required & retrieved)
            relevant_retrieved += len(required & retrieved)
            all_retrieved_for_dependent += len(retrieved)
        else:
            session_independent_deltas.setdefault(case.session_id, []).append(delta)
            independent_cases += 1
            if on.retrieved_memory_ids:
                unnecessary_cases += 1
        if case.expected_tool_name is not None:
            action_case_count += 1
            if _argument_correct(case, on):
                argument_correct_count += 1
        if _tool_correct(case, on):
            tool_correct_count += 1
        retrieval_times.append(on.retrieval_ms)
        elapsed_overheads.append(on.elapsed_ms - off.elapsed_ms)

    session_off_rates = [
        sum(1 for off_ok, _ in pairs if off_ok) / len(pairs)
        for pairs in session_pairs.values()
    ]
    session_on_rates = [
        sum(1 for _, on_ok in pairs if on_ok) / len(pairs)
        for pairs in session_pairs.values()
    ]
    session_overall_deltas = [
        sum(float(on_ok) - float(off_ok) for off_ok, on_ok in pairs) / len(pairs)
        for pairs in session_pairs.values()
    ]
    memory_off_accuracy = round(100.0 * sum(session_off_rates) / len(session_off_rates), 4)
    memory_on_accuracy = round(100.0 * sum(session_on_rates) / len(session_on_rates), 4)
    overall_gain = round(100.0 * sum(session_overall_deltas) / len(session_overall_deltas), 4)
    dependent_means = [
        sum(values) / len(values) for values in session_dependent_deltas.values() if values
    ]
    independent_means = [
        sum(values) / len(values) for values in session_independent_deltas.values() if values
    ]
    dependent_gain = round(100.0 * sum(dependent_means) / len(dependent_means), 4) if dependent_means else None
    independent_gain = round(100.0 * sum(independent_means) / len(independent_means), 4) if independent_means else None
    required_recall = _percent(retrieval_hits, required_count)
    required_precision = _percent(relevant_retrieved, all_retrieved_for_dependent)
    unnecessary_rate = _percent(unnecessary_cases, independent_cases)
    argument_accuracy = _percent(argument_correct_count, action_case_count)
    tool_accuracy = _percent(tool_correct_count, len(manifest.cases))

    improved_sessions = worse_sessions = tied_sessions = 0
    for pairs in session_pairs.values():
        mean_delta = sum(float(on_ok) - float(off_ok) for off_ok, on_ok in pairs) / len(pairs)
        if mean_delta > 0:
            improved_sessions += 1
        elif mean_delta < 0:
            worse_sessions += 1
        else:
            tied_sessions += 1
    sign_p = _sign_test_p(improved_sessions, worse_sessions)
    median_retrieval = float(median(retrieval_times)) if retrieval_times else None
    median_overhead = float(median(elapsed_overheads)) if elapsed_overheads else None

    verdict = "inconclusive"
    if manifest.split == "development":
        verdict = "development_signal_only"
    elif session_count < minimum_sessions or domain_count < minimum_domains:
        verdict = "inconclusive"
    elif (
        dependent_gain is not None
        and dependent_gain < -maximum_independent_regression_pp
    ) or (
        independent_gain is not None
        and independent_gain < -maximum_independent_regression_pp
    ):
        verdict = "memory_regressed"
    elif (
        dependent_gain is not None
        and dependent_gain >= minimum_dependent_gain_pp
        and independent_gain is not None
        and independent_gain >= -maximum_independent_regression_pp
        and required_recall is not None
        and required_recall >= minimum_required_memory_recall_pp
        and unnecessary_rate is not None
        and unnecessary_rate <= maximum_unnecessary_memory_use_pp
        and sign_p <= alpha
    ):
        verdict = "manual_review_recommended"

    warnings = list(base_warnings)
    if required_recall is not None and required_recall < minimum_required_memory_recall_pp:
        warnings.append("Required-memory retrieval recall is below the configured threshold.")
    if unnecessary_rate is not None and unnecessary_rate > maximum_unnecessary_memory_use_pp:
        warnings.append("The memory-on arm injected irrelevant memory into too many independent cases.")
    if manifest.split == "development":
        warnings.append("Development results are screening signals and cannot authorize holdout promotion.")
    if verdict == "inconclusive":
        warnings.append("The evidence did not satisfy all preregistered holdout acceptance conditions.")

    return MemoryActionReport(
        verdict, manifest.split, len(manifest.cases), completed_pairs, incomplete_pairs,
        session_count, domain_count, memory_off_accuracy, memory_on_accuracy, overall_gain,
        dependent_gain, independent_gain, tool_accuracy, argument_accuracy, required_recall,
        required_precision, unnecessary_rate, median_retrieval, median_overhead,
        improved_sessions, worse_sessions, tied_sessions, sign_p, tuple(warnings),
    )

