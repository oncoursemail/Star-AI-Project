"""Versioned, declarative contracts for reusable STAR skills.

A skill contract describes when a skill may be considered, its bounded steps,
expected state changes, resource budget, provenance and verification evidence.
It is reference/evaluation data only: it never executes code, grants permissions,
or replaces the runtime policy, resource lease, game-control gate or human review.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import urlsplit

SCHEMA_VERSION = 1
MAX_STEPS = 32
MAX_CONDITIONS = 32
MAX_SOURCES = 32
MAX_CAPABILITIES = 16
MAX_TEXT = 1000
MAX_TOOL_CALLS = 64
MAX_TOKENS = 100_000
MAX_RAM_MIB = 1_048_576

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,79}$")
_SKILL_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DOMAINS = frozenset({"general", "research", "desktop", "game", "roblox", "creator", "streaming"})
_CONDITION_KINDS = frozenset({
    "state_equals", "state_exists", "capability_present", "fresh_observation",
    "owner_consent", "resource_available", "environment_matches",
})
_EXPECTATION_OPERATORS = frozenset({"equals", "exists", "changed", "contains", "count_at_least"})
_OPERATIONS = frozenset({"observe", "reason", "request_tool", "verify", "recover"})
_OUTCOMES = frozenset({"success", "failure", "aborted", "timeout"})
_VERIFIERS = frozenset({"none", "independent_host", "independent_replay"})
_SOURCE_KINDS = frozenset({"url", "artifact", "evaluation", "owner_note"})
_SCALAR_TYPES = (str, int, float, bool, type(None))


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], required: set[str], optional: set[str], label: str) -> None:
    missing = required - set(value)
    extra = set(value) - required - optional
    if missing or extra:
        bits = []
        if missing:
            bits.append("missing " + ", ".join(sorted(missing)))
        if extra:
            bits.append("unknown " + ", ".join(sorted(extra)))
        raise ValueError(f"{label} has " + "; ".join(bits))


def _text(value: Any, label: str, *, limit: int = MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label} must be non-empty text of at most {limit} characters")
    return value.strip()


def _identifier(value: Any, label: str) -> str:
    text = _text(value, label, limit=80)
    if not _IDENTIFIER.fullmatch(text):
        raise ValueError(f"{label} must be a bounded identifier")
    return text


def _digest(value: Any, label: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _aware_time(value: Any, label: str) -> datetime:
    text = _text(value, label, limit=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _scalar(value: Any, label: str) -> str | int | float | bool | None:
    if type(value) not in _SCALAR_TYPES:
        raise ValueError(f"{label} must be a scalar")
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        raise ValueError(f"{label} must be finite")
    if isinstance(value, str) and len(value) > 300:
        raise ValueError(f"{label} text is too long")
    return value


@dataclass(frozen=True)
class Condition:
    kind: str
    subject: str
    operator: str | None = None
    value: str | int | float | bool | None = None
    max_age_ms: int | None = None

    @classmethod
    def from_dict(cls, raw: Any) -> "Condition":
        obj = _mapping(raw, "condition")
        _exact_keys(obj, {"kind", "subject"}, {"operator", "value", "max_age_ms"}, "condition")
        kind = _text(obj["kind"], "condition.kind", limit=40)
        if kind not in _CONDITION_KINDS:
            raise ValueError("unsupported condition.kind")
        subject = _text(obj["subject"], "condition.subject", limit=160)
        operator = obj.get("operator")
        if operator is not None:
            operator = _text(operator, "condition.operator", limit=40)
            if operator not in _EXPECTATION_OPERATORS:
                raise ValueError("unsupported condition.operator")
        value = _scalar(obj.get("value"), "condition.value")
        age = obj.get("max_age_ms")
        if age is not None and (type(age) is not int or not 1 <= age <= 3_600_000):
            raise ValueError("condition.max_age_ms must be 1..3600000")
        if kind == "fresh_observation" and age is None:
            raise ValueError("fresh_observation requires max_age_ms")
        if kind == "state_equals" and (operator != "equals" or value is None):
            raise ValueError("state_equals requires operator=equals and a value")
        if kind == "state_exists" and operator not in (None, "exists"):
            raise ValueError("state_exists only supports operator=exists")
        if kind == "owner_consent" and value is not True:
            raise ValueError("owner_consent requires value=true; a contract cannot encode consent")
        if kind == "capability_present" and value is not True:
            raise ValueError("capability_present requires value=true")
        if kind == "environment_matches" and (value is None or not isinstance(value, str)):
            raise ValueError("environment_matches requires a string fingerprint")
        return cls(kind, subject, operator, value, age)


@dataclass(frozen=True)
class StateExpectation:
    path: str
    operator: str
    value: str | int | float | bool | None = None

    @classmethod
    def from_dict(cls, raw: Any) -> "StateExpectation":
        obj = _mapping(raw, "state expectation")
        _exact_keys(obj, {"path", "operator"}, {"value"}, "state expectation")
        path = _text(obj["path"], "state expectation.path", limit=200)
        if path.startswith("/") or ".." in path.split("/") or "\\" in path:
            raise ValueError("state expectation.path must be a relative logical path")
        operator = _text(obj["operator"], "state expectation.operator", limit=40)
        if operator not in _EXPECTATION_OPERATORS:
            raise ValueError("unsupported state expectation operator")
        value = _scalar(obj.get("value"), "state expectation.value")
        if operator in {"equals", "contains", "count_at_least"} and value is None:
            raise ValueError(f"{operator} requires a value")
        if operator == "count_at_least" and (type(value) is not int or value < 0):
            raise ValueError("count_at_least value must be a non-negative integer")
        return cls(path, operator, value)


@dataclass(frozen=True)
class SkillStep:
    step_id: str
    operation: str
    intent: str
    tool_name: str | None = None
    required_capabilities: tuple[str, ...] = ()
    expected_deltas: tuple[StateExpectation, ...] = ()

    @classmethod
    def from_dict(cls, raw: Any) -> "SkillStep":
        obj = _mapping(raw, "skill step")
        _exact_keys(obj, {"step_id", "operation", "intent"},
                    {"tool_name", "required_capabilities", "expected_deltas"}, "skill step")
        step_id = _identifier(obj["step_id"], "step_id")
        operation = _text(obj["operation"], "step.operation", limit=40)
        if operation not in _OPERATIONS:
            raise ValueError("unsupported step operation")
        intent = _text(obj["intent"], "step.intent")
        tool = obj.get("tool_name")
        if tool is not None:
            tool = _identifier(tool, "tool_name")
        caps_raw = obj.get("required_capabilities", [])
        if not isinstance(caps_raw, list) or len(caps_raw) > MAX_CAPABILITIES:
            raise ValueError("required_capabilities must be a bounded list")
        caps = tuple(_identifier(x, "required capability") for x in caps_raw)
        if len(set(caps)) != len(caps):
            raise ValueError("duplicate required capability")
        if operation == "request_tool" and (tool is None or not caps):
            raise ValueError("request_tool requires a tool_name and explicit required_capabilities")
        if operation != "request_tool" and tool is not None:
            raise ValueError("tool_name is only valid for request_tool steps")
        deltas_raw = obj.get("expected_deltas", [])
        if not isinstance(deltas_raw, list) or len(deltas_raw) > MAX_CONDITIONS:
            raise ValueError("expected_deltas must be a bounded list")
        deltas = tuple(StateExpectation.from_dict(x) for x in deltas_raw)
        return cls(step_id, operation, intent, tool, caps, deltas)


@dataclass(frozen=True)
class SkillBehaviorConstraint:
    """One observable rule extracted from a reusable skill's instructions."""

    constraint_id: str
    condition: Condition
    expected_behavior: str
    severity: str = "normal"

    @classmethod
    def from_dict(cls, raw: Any) -> "SkillBehaviorConstraint":
        obj = _mapping(raw, "behavior constraint")
        _exact_keys(obj, {"constraint_id", "condition", "expected_behavior"},
                    {"severity"}, "behavior constraint")
        constraint_id = _identifier(obj["constraint_id"], "constraint_id")
        condition = Condition.from_dict(obj["condition"])
        expected = _text(obj["expected_behavior"], "expected_behavior")
        severity = _text(obj.get("severity", "normal"), "constraint.severity", limit=20)
        if severity not in {"normal", "critical"}:
            raise ValueError("constraint.severity must be normal or critical")
        return cls(constraint_id, condition, expected, severity)


@dataclass(frozen=True)
class SkillCoverageObservation:
    """Independent label for whether one behavior constraint was exercised and followed."""

    constraint_id: str
    verdict: str
    verifier: str
    evidence_sha256: str | None = None

    @classmethod
    def from_dict(cls, raw: Any) -> "SkillCoverageObservation":
        obj = _mapping(raw, "coverage observation")
        _exact_keys(obj, {"constraint_id", "verdict", "verifier"},
                    {"evidence_sha256"}, "coverage observation")
        constraint_id = _identifier(obj["constraint_id"], "coverage.constraint_id")
        verdict = _text(obj["verdict"], "coverage.verdict", limit=20)
        if verdict not in {"pass", "fail", "not_observed"}:
            raise ValueError("coverage.verdict must be pass, fail or not_observed")
        verifier = _text(obj["verifier"], "coverage.verifier", limit=32)
        if verifier not in _VERIFIERS:
            raise ValueError("unsupported coverage verifier")
        evidence = _digest(obj.get("evidence_sha256"), "coverage.evidence_sha256", optional=True)
        if verdict in {"pass", "fail"} and (verifier == "none" or evidence is None):
            raise ValueError("pass/fail coverage labels require an independent verifier and evidence digest")
        if verdict == "not_observed" and (verifier != "none" or evidence is not None):
            raise ValueError("not_observed coverage must not claim a verifier or evidence digest")
        return cls(constraint_id, verdict, verifier, evidence)


@dataclass(frozen=True)
class SkillCoverageReport:
    total_constraints: int
    covered_constraints: int
    passed_constraints: int
    failed_constraints: int
    unobserved_constraints: int
    critical_failures: int
    coverage_rate: float
    pass_rate_when_covered: float | None
    review_recommended: bool


@dataclass(frozen=True)
class ResourceBudget:
    max_elapsed_ms: int
    max_steps: int
    max_tool_calls: int
    max_tokens: int
    max_retries: int
    max_ram_mib: int

    @classmethod
    def from_dict(cls, raw: Any) -> "ResourceBudget":
        obj = _mapping(raw, "resource_budget")
        keys = {"max_elapsed_ms", "max_steps", "max_tool_calls", "max_tokens", "max_retries", "max_ram_mib"}
        _exact_keys(obj, keys, set(), "resource_budget")
        limits = {
            "max_elapsed_ms": (100, 3_600_000),
            "max_steps": (1, MAX_STEPS),
            "max_tool_calls": (0, MAX_TOOL_CALLS),
            "max_tokens": (0, MAX_TOKENS),
            "max_retries": (0, 5),
            "max_ram_mib": (64, MAX_RAM_MIB),
        }
        values = {}
        for key, (low, high) in limits.items():
            value = obj[key]
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"resource_budget.{key} must be an integer in {low}..{high}")
            values[key] = value
        return cls(**values)


@dataclass(frozen=True)
class SourceRef:
    kind: str
    locator: str
    sha256: str | None = None

    @classmethod
    def from_dict(cls, raw: Any) -> "SourceRef":
        obj = _mapping(raw, "source reference")
        _exact_keys(obj, {"kind", "locator"}, {"sha256"}, "source reference")
        kind = _text(obj["kind"], "source.kind", limit=32)
        if kind not in _SOURCE_KINDS:
            raise ValueError("unsupported source kind")
        locator = _text(obj["locator"], "source.locator", limit=500)
        digest = _digest(obj.get("sha256"), "source.sha256", optional=True)
        if kind == "url":
            parsed = urlsplit(locator)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("source URL must be HTTPS without embedded credentials")
        elif kind == "artifact" and digest is None:
            raise ValueError("artifact sources require a SHA-256 digest")
        return cls(kind, locator, digest)


@dataclass(frozen=True)
class SkillContract:
    skill_id: str
    version: str
    domain: str
    summary: str
    preconditions: tuple[Condition, ...]
    steps: tuple[SkillStep, ...]
    behavior_constraints: tuple[SkillBehaviorConstraint, ...]
    postconditions: tuple[StateExpectation, ...]
    resource_budget: ResourceBudget
    provenance: tuple[SourceRef, ...]
    environment_fingerprint: str | None = None
    expires_at: str | None = None
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, raw: Any) -> "SkillContract":
        obj = _mapping(raw, "skill contract")
        required = {"schema_version", "skill_id", "version", "domain", "summary",
                    "preconditions", "steps", "behavior_constraints", "postconditions",
                    "resource_budget", "provenance"}
        optional = {"environment_fingerprint", "expires_at"}
        _exact_keys(obj, required, optional, "skill contract")
        if type(obj["schema_version"]) is not int or obj["schema_version"] != SCHEMA_VERSION:
            raise ValueError("unsupported skill contract schema_version")
        skill_id = _text(obj["skill_id"], "skill_id", limit=80)
        if not _SKILL_ID.fullmatch(skill_id):
            raise ValueError("skill_id must be lowercase kebab-case")
        version = _text(obj["version"], "version", limit=40)
        if not _SEMVER.fullmatch(version):
            raise ValueError("version must be semantic version x.y.z")
        domain = _text(obj["domain"], "domain", limit=32)
        if domain not in _DOMAINS:
            raise ValueError("unsupported skill domain")
        summary = _text(obj["summary"], "summary")
        pre_raw, steps_raw, constraints_raw, post_raw, sources_raw = (
            obj["preconditions"], obj["steps"], obj["behavior_constraints"],
            obj["postconditions"], obj["provenance"])
        if not isinstance(pre_raw, list) or len(pre_raw) > MAX_CONDITIONS:
            raise ValueError("preconditions must be a bounded list")
        if not isinstance(steps_raw, list) or not 1 <= len(steps_raw) <= MAX_STEPS:
            raise ValueError("steps must contain 1..32 entries")
        if not isinstance(constraints_raw, list) or not 1 <= len(constraints_raw) <= MAX_CONDITIONS:
            raise ValueError("behavior_constraints must contain 1..32 entries")
        if not isinstance(post_raw, list) or not post_raw or len(post_raw) > MAX_CONDITIONS:
            raise ValueError("postconditions must contain 1..32 entries")
        if not isinstance(sources_raw, list) or not 1 <= len(sources_raw) <= MAX_SOURCES:
            raise ValueError("provenance must contain 1..32 entries")
        pre = tuple(Condition.from_dict(x) for x in pre_raw)
        steps = tuple(SkillStep.from_dict(x) for x in steps_raw)
        constraints = tuple(SkillBehaviorConstraint.from_dict(x) for x in constraints_raw)
        post = tuple(StateExpectation.from_dict(x) for x in post_raw)
        if len({x.step_id for x in steps}) != len(steps):
            raise ValueError("step_id values must be unique")
        if len({x.constraint_id for x in constraints}) != len(constraints):
            raise ValueError("behavior constraint ids must be unique")
        sources = tuple(SourceRef.from_dict(x) for x in sources_raw)
        env = _digest(obj.get("environment_fingerprint"), "environment_fingerprint", optional=True)
        expires = obj.get("expires_at")
        if expires is not None:
            _aware_time(expires, "expires_at")
        budget = ResourceBudget.from_dict(obj["resource_budget"])
        if len(steps) > budget.max_steps:
            raise ValueError("declared steps exceed resource_budget.max_steps")
        tool_steps = sum(step.operation == "request_tool" for step in steps)
        if tool_steps > budget.max_tool_calls:
            raise ValueError("declared tool steps exceed resource_budget.max_tool_calls")
        return cls(skill_id, version, domain, summary, pre, steps, constraints, post,
                   budget, sources, env, expires)

    def to_dict(self) -> dict[str, Any]:
        # JSON normalization converts immutable tuples to the list representation
        # accepted by the on-disk schema.
        return json.loads(json.dumps(asdict(self), ensure_ascii=False))

    def digest(self) -> str:
        """Stable digest over the normalized, versioned contract."""
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SkillExecutionReceipt:
    schema_version: int
    run_id: str
    skill_id: str
    skill_version: str
    contract_sha256: str
    environment_fingerprint: str
    started_at: str
    finished_at: str
    outcome: str
    preconditions_passed: bool
    postconditions_verified: bool
    verifier: str
    evidence_sha256: str | None
    holdout: bool

    @classmethod
    def from_dict(cls, raw: Any) -> "SkillExecutionReceipt":
        obj = _mapping(raw, "execution receipt")
        required = {"schema_version", "run_id", "skill_id", "skill_version", "contract_sha256",
                    "environment_fingerprint", "started_at", "finished_at", "outcome",
                    "preconditions_passed", "postconditions_verified", "verifier", "holdout"}
        optional = {"evidence_sha256"}
        _exact_keys(obj, required, optional, "execution receipt")
        if type(obj["schema_version"]) is not int or obj["schema_version"] != SCHEMA_VERSION:
            raise ValueError("unsupported execution receipt schema_version")
        run_id = _identifier(obj["run_id"], "run_id")
        skill_id = _text(obj["skill_id"], "receipt.skill_id", limit=80)
        if not _SKILL_ID.fullmatch(skill_id):
            raise ValueError("receipt.skill_id must be lowercase kebab-case")
        version = _text(obj["skill_version"], "receipt.skill_version", limit=40)
        if not _SEMVER.fullmatch(version):
            raise ValueError("receipt.skill_version must be semantic version x.y.z")
        contract_sha = _digest(obj["contract_sha256"], "contract_sha256")
        env = _digest(obj["environment_fingerprint"], "environment_fingerprint")
        started = _text(obj["started_at"], "started_at", limit=64)
        finished = _text(obj["finished_at"], "finished_at", limit=64)
        start_dt, finish_dt = _aware_time(started, "started_at"), _aware_time(finished, "finished_at")
        if finish_dt < start_dt:
            raise ValueError("finished_at must not precede started_at")
        outcome = _text(obj["outcome"], "outcome", limit=32)
        if outcome not in _OUTCOMES:
            raise ValueError("unsupported receipt outcome")
        pre = obj["preconditions_passed"]
        post = obj["postconditions_verified"]
        holdout = obj["holdout"]
        if type(pre) is not bool or type(post) is not bool or type(holdout) is not bool:
            raise ValueError("receipt evidence flags must be booleans")
        verifier = _text(obj["verifier"], "verifier", limit=32)
        if verifier not in _VERIFIERS:
            raise ValueError("unsupported verifier")
        evidence = _digest(obj.get("evidence_sha256"), "evidence_sha256", optional=True)
        if post and (verifier == "none" or evidence is None):
            raise ValueError("verified postconditions require an independent verifier and evidence digest")
        if outcome == "success" and (not pre or not post):
            raise ValueError("success requires passed preconditions and verified postconditions")
        if holdout and evidence is None:
            raise ValueError("holdout receipts require an evidence digest")
        return cls(SCHEMA_VERSION, run_id, skill_id, version, contract_sha, env, started, finished,
                   outcome, pre, post, verifier, evidence, holdout)


def validate_execution_receipt(raw: Any, contract: SkillContract) -> SkillExecutionReceipt:
    """Validate evidence binding; this does not promote the skill or authorize actions."""
    receipt = SkillExecutionReceipt.from_dict(raw)
    if receipt.skill_id != contract.skill_id or receipt.skill_version != contract.version:
        raise ValueError("receipt is bound to a different skill id/version")
    if receipt.contract_sha256 != contract.digest():
        raise ValueError("receipt contract digest does not match")
    if contract.environment_fingerprint and receipt.environment_fingerprint != contract.environment_fingerprint:
        raise ValueError("receipt environment does not match the pinned contract")
    started = _aware_time(receipt.started_at, "started_at")
    finished = _aware_time(receipt.finished_at, "finished_at")
    elapsed_ms = int((finished - started).total_seconds() * 1000)
    if elapsed_ms > contract.resource_budget.max_elapsed_ms:
        raise ValueError("receipt exceeded the contract time budget")
    if contract.expires_at and started > _aware_time(contract.expires_at, "expires_at"):
        raise ValueError("skill contract was expired when execution started")
    return receipt


def evaluate_skill_coverage(
    contract: SkillContract,
    observations: list[Mapping[str, Any]],
    *,
    minimum_coverage: float = 0.8,
) -> SkillCoverageReport:
    """Measure exercised skill constraints; never infer a pass from missing evidence.

    review_recommended is only a triage signal. It is not skill promotion,
    trust, tool authorization, or a substitute for a sealed transfer holdout.
    """
    if not isinstance(contract, SkillContract):
        raise ValueError("contract must be a parsed SkillContract")
    if isinstance(minimum_coverage, bool) or not isinstance(minimum_coverage, (int, float)):
        raise ValueError("minimum_coverage must be a number from 0 to 1")
    if not 0.0 <= float(minimum_coverage) <= 1.0:
        raise ValueError("minimum_coverage must be a number from 0 to 1")
    if not isinstance(observations, list) or len(observations) != len(contract.behavior_constraints):
        raise ValueError("coverage observations must exactly match the contract constraint roster")
    parsed = tuple(SkillCoverageObservation.from_dict(row) for row in observations)
    expected = {item.constraint_id for item in contract.behavior_constraints}
    observed = [item.constraint_id for item in parsed]
    if len(set(observed)) != len(observed) or set(observed) != expected:
        raise ValueError("coverage observations must contain every constraint exactly once")
    by_id = {item.constraint_id: item for item in parsed}
    critical = {item.constraint_id for item in contract.behavior_constraints if item.severity == "critical"}
    passed = sum(item.verdict == "pass" for item in parsed)
    failed = sum(item.verdict == "fail" for item in parsed)
    unobserved = sum(item.verdict == "not_observed" for item in parsed)
    covered = passed + failed
    total = len(parsed)
    coverage_rate = covered / total
    pass_rate = passed / covered if covered else None
    critical_failures = sum(by_id[key].verdict == "fail" for key in critical)
    review = coverage_rate >= float(minimum_coverage) and failed == 0
    return SkillCoverageReport(total, covered, passed, failed, unobserved, critical_failures,
                               coverage_rate, pass_rate, review)


def parse_skill_contract(raw: str | Mapping[str, Any]) -> SkillContract:
    """Parse a JSON object or mapping; unknown fields are rejected rather than ignored."""
    if isinstance(raw, str):
        if len(raw) > 64_000:
            raise ValueError("skill contract JSON is too large")
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("skill contract must be valid JSON") from exc
    return SkillContract.from_dict(raw)
