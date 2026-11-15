"""Bounded, deterministic evidence selection for active perception.

This is a policy-only layer. It does not capture media, call models, schedule CPU/GPU
work, execute tools, or authorize game input. Compute admission remains with STAR's
resource governor; game actions remain behind GameControlGate.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Sequence


_TOKEN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_REASON = re.compile(r"^[a-z0-9_.-]{1,48}$")
_KINDS = frozenset({"frame", "clip", "audio", "event_recall"})


def _finite(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


@dataclass(frozen=True)
class EvidenceCandidate:
    """A small metadata-only proposal for evidence to inspect.

    The candidate carries no frame bytes, transcript, viewer text, URL, or tool
    arguments. Adapters should keep those payloads in their own bounded stores.
    """

    candidate_id: str
    session_id: str
    dedupe_key: str
    kind: str
    reason_code: str
    priority: float
    relevance: float
    uncertainty: float
    novelty: float
    media_units: int
    created_at: float
    evidence_at: float | None = None
    max_evidence_age_ms: int | None = None
    deadline_at: float | None = None


@dataclass(frozen=True)
class PerceptionPolicyConfig:
    """Per-turn context limits, not machine-resource scheduling limits."""

    max_candidates: int = 256
    max_candidate_age_ms: int = 5_000
    max_future_skew_ms: int = 100
    max_media_units_per_turn: int = 24
    max_requests_per_turn: int = 4

    def __post_init__(self) -> None:
        for name, low, high in (
            ("max_candidates", 1, 1_024),
            ("max_candidate_age_ms", 1, 600_000),
            ("max_future_skew_ms", 0, 5_000),
            ("max_media_units_per_turn", 1, 4_096),
            ("max_requests_per_turn", 1, 32),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer from {low} to {high}")


@dataclass(frozen=True)
class SelectedEvidence:
    candidate: EvidenceCandidate
    score: float


@dataclass(frozen=True)
class RejectedEvidence:
    candidate_id: str
    reason: str


@dataclass(frozen=True)
class PerceptionSelection:
    selected: tuple[SelectedEvidence, ...]
    rejected: tuple[RejectedEvidence, ...]
    used_media_units: int
    remaining_media_units: int


class ActivePerceptionPolicy:
    """Select high-value evidence proposals under bounded per-turn context.

    The transparent baseline score is:
        (0.35 * priority + 0.30 * relevance
         + 0.20 * uncertainty + 0.15 * novelty) / sqrt(media_units)

    It is deliberately deterministic and easy to evaluate. Weights are not
    learned or silently adapted. Change them only through paired offline tests.
    """

    def __init__(self, config: PerceptionPolicyConfig | None = None) -> None:
        self.config = config or PerceptionPolicyConfig()
        if not isinstance(self.config, PerceptionPolicyConfig):
            raise TypeError("config must be a PerceptionPolicyConfig")

    def select(
        self,
        candidates: Sequence[EvidenceCandidate],
        *,
        session_id: str,
        now: float,
    ) -> PerceptionSelection:
        if not _TOKEN.fullmatch(session_id) if isinstance(session_id, str) else True:
            raise ValueError("session_id must be a bounded token")
        if not _finite(now):
            raise ValueError("now must be a finite monotonic timestamp")
        if not isinstance(candidates, (list, tuple)):
            raise TypeError("candidates must be a list or tuple")
        if len(candidates) > self.config.max_candidates:
            raise ValueError("candidate list exceeds the configured bound")

        eligible: list[SelectedEvidence] = []
        rejected: list[RejectedEvidence] = []
        seen_ids: set[str] = set()
        future_skew = self.config.max_future_skew_ms / 1000.0

        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, EvidenceCandidate):
                rejected.append(RejectedEvidence(f"index-{index}", "invalid_candidate"))
                continue

            candidate_id = (
                candidate.candidate_id
                if isinstance(candidate.candidate_id, str)
                and _TOKEN.fullmatch(candidate.candidate_id)
                else f"index-{index}"
            )
            if candidate_id in seen_ids:
                rejected.append(RejectedEvidence(candidate_id, "duplicate_candidate_id"))
                continue
            if _TOKEN.fullmatch(candidate_id):
                seen_ids.add(candidate_id)

            problem = self._candidate_problem(
                candidate, session_id=session_id, now=float(now), future_skew=future_skew
            )
            if problem is not None:
                rejected.append(RejectedEvidence(candidate_id, problem))
                continue

            value = (
                0.35 * candidate.priority
                + 0.30 * candidate.relevance
                + 0.20 * candidate.uncertainty
                + 0.15 * candidate.novelty
            )
            score = value / math.sqrt(candidate.media_units)
            eligible.append(SelectedEvidence(candidate, score))

        eligible.sort(
            key=lambda item: (
                -item.score,
                item.candidate.deadline_at
                if item.candidate.deadline_at is not None
                else math.inf,
                item.candidate.candidate_id,
            )
        )

        selected: list[SelectedEvidence] = []
        selected_dedupe: set[str] = set()
        used_units = 0
        for item in eligible:
            candidate = item.candidate
            if candidate.priority == 0.0 and candidate.relevance == 0.0 and (
                candidate.uncertainty == 0.0 and candidate.novelty == 0.0
            ):
                rejected.append(RejectedEvidence(candidate.candidate_id, "no_information_value"))
                continue
            if candidate.dedupe_key in selected_dedupe:
                rejected.append(RejectedEvidence(candidate.candidate_id, "duplicate_evidence"))
                continue
            if len(selected) >= self.config.max_requests_per_turn:
                rejected.append(RejectedEvidence(candidate.candidate_id, "request_limit_exhausted"))
                continue
            if used_units + candidate.media_units > self.config.max_media_units_per_turn:
                rejected.append(RejectedEvidence(candidate.candidate_id, "media_budget_exhausted"))
                continue
            selected.append(item)
            selected_dedupe.add(candidate.dedupe_key)
            used_units += candidate.media_units

        rejected.sort(key=lambda item: (item.candidate_id, item.reason))
        return PerceptionSelection(
            selected=tuple(selected),
            rejected=tuple(rejected),
            used_media_units=used_units,
            remaining_media_units=self.config.max_media_units_per_turn - used_units,
        )

    def _candidate_problem(
        self,
        candidate: EvidenceCandidate,
        *,
        session_id: str,
        now: float,
        future_skew: float,
    ) -> str | None:
        if not _TOKEN.fullmatch(candidate.candidate_id):
            return "invalid_candidate_id"
        if not _TOKEN.fullmatch(candidate.session_id):
            return "invalid_candidate_session"
        if candidate.session_id != session_id:
            return "wrong_session"
        if not _TOKEN.fullmatch(candidate.dedupe_key):
            return "invalid_dedupe_key"
        if candidate.kind not in _KINDS:
            return "invalid_kind"
        if not isinstance(candidate.reason_code, str) or not _REASON.fullmatch(
            candidate.reason_code
        ):
            return "invalid_reason_code"
        for name in ("priority", "relevance", "uncertainty", "novelty"):
            value = getattr(candidate, name)
            if not _finite(value) or not 0.0 <= value <= 1.0:
                return f"invalid_{name}"
        if type(candidate.media_units) is not int or not 1 <= candidate.media_units <= 128:
            return "invalid_media_units"
        if not _finite(candidate.created_at):
            return "invalid_created_at"
        if candidate.evidence_at is not None and not _finite(candidate.evidence_at):
            return "invalid_evidence_at"
        if candidate.max_evidence_age_ms is not None and (
            type(candidate.max_evidence_age_ms) is not int
            or not 0 <= candidate.max_evidence_age_ms <= 600_000
        ):
            return "invalid_evidence_age_limit"
        if candidate.evidence_at is None and candidate.max_evidence_age_ms is not None:
            return "evidence_age_limit_without_timestamp"
        if candidate.deadline_at is not None and not _finite(candidate.deadline_at):
            return "invalid_deadline"
        if (
            candidate.deadline_at is not None
            and candidate.deadline_at < candidate.created_at
        ):
            return "deadline_predates_candidate"
        if candidate.created_at > now + future_skew:
            return "future_candidate"
        if (now - candidate.created_at) * 1000.0 > self.config.max_candidate_age_ms:
            return "stale_candidate"
        if candidate.deadline_at is not None and now >= candidate.deadline_at:
            return "deadline_expired"
        if candidate.evidence_at is not None:
            if candidate.evidence_at > now + future_skew:
                return "future_evidence"
            if candidate.max_evidence_age_ms is not None and (
                (now - candidate.evidence_at) * 1000.0
                > candidate.max_evidence_age_ms
            ):
                return "stale_evidence"
        return None
