"""Host-neutral KV-residency admission planning for long-running AI sessions.

This module is deliberately side-effect free. It does not call a model server,
cancel a request, suspend a session, or grant permission. A trusted serving
adapter must re-check live measurements and acknowledge every proposed action.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal


# Lower number means more important. Equal-priority work is never preempted.
_PRIORITY: dict[str, int] = {
    "speech": 0,
    "interactive": 1,
    "gameplay": 1,
    "vision": 2,
    "research": 3,
    "training": 4,
    "render": 4,
}
_EPSILON_MIB = 1e-6


def _identifier(value: object, name: str) -> str:
    if (type(value) is not str or not value or value != value.strip()
            or len(value) > 128 or any(ord(char) < 32 for char in value)):
        raise ValueError(f"{name} must be a nonempty opaque identifier")
    return value


def _quantity(value: object, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite nonnegative number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise ValueError(f"{name} must be a finite {'positive' if positive else 'nonnegative'} number")
    return result


def _timestamp(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative monotonic millisecond integer")
    return value


def _workload(value: object) -> str:
    if type(value) is not str or value not in _PRIORITY:
        raise ValueError("unsupported workload class")
    return value


@dataclass(frozen=True, slots=True)
class KVSession:
    """One currently resident session, described by a backend measurement."""

    session_id: str
    workload: str
    resident_mib: float
    last_active_ms: int
    suspendable: bool = True

    def __post_init__(self) -> None:
        _identifier(self.session_id, "session_id")
        _workload(self.workload)
        _quantity(self.resident_mib, "resident_mib", positive=True)
        _timestamp(self.last_active_ms, "last_active_ms")
        if type(self.suspendable) is not bool:
            raise ValueError("suspendable must be an explicit boolean")


@dataclass(frozen=True, slots=True)
class KVSnapshot:
    """A single, internally consistent backend capacity observation."""

    capacity_mib: float
    reserved_mib: float
    captured_at_ms: int
    sessions: tuple[KVSession, ...]

    def __post_init__(self) -> None:
        capacity = _quantity(self.capacity_mib, "capacity_mib", positive=True)
        reserve = _quantity(self.reserved_mib, "reserved_mib")
        if reserve >= capacity:
            raise ValueError("reserved_mib must be smaller than capacity_mib")
        _timestamp(self.captured_at_ms, "captured_at_ms")
        if type(self.sessions) is not tuple:
            raise ValueError("sessions must be an immutable tuple")
        if any(not isinstance(item, KVSession) for item in self.sessions):
            raise TypeError("sessions must contain KVSession values")
        ids = [item.session_id for item in self.sessions]
        if len(ids) != len(set(ids)):
            raise ValueError("session identifiers must be unique")
        if any(item.last_active_ms > self.captured_at_ms for item in self.sessions):
            raise ValueError("session activity cannot be newer than the snapshot")
        resident = sum(item.resident_mib for item in self.sessions)
        if resident > capacity + _EPSILON_MIB:
            raise ValueError("reported resident KV exceeds backend capacity")


@dataclass(frozen=True, slots=True)
class AdmissionRequest:
    """A proposed session with a conservative KV upper-bound estimate."""

    session_id: str
    workload: str
    requested_mib: float

    def __post_init__(self) -> None:
        _identifier(self.session_id, "session_id")
        _workload(self.workload)
        _quantity(self.requested_mib, "requested_mib", positive=True)


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    """A recommendation, never a backend authorization or completed action."""

    action: Literal["admit", "suspend_then_admit", "defer"]
    suspend_session_ids: tuple[str, ...]
    resident_before_mib: float
    requested_mib: float
    effective_capacity_mib: float
    projected_resident_mib: float
    headroom_after_mib: float
    sample_age_ms: int
    host_ack_required: bool
    reason: str

    @property
    def immediately_admissible(self) -> bool:
        """True only when no existing session needs to be suspended."""
        return self.action == "admit"


def plan_admission(
    snapshot: KVSnapshot,
    request: AdmissionRequest,
    *,
    now_ms: int,
    max_sample_age_ms: int = 2_000,
) -> AdmissionDecision:
    """Plan admission using a measured capacity snapshot and priority policy.

    The budget is capacity minus a fixed safety reserve. If the request does
    not fit, only lower-priority, explicitly suspendable sessions are proposed
    as victims. Equal- and higher-priority sessions are never preempted.

    A stale snapshot fails closed. The host must collect a fresh snapshot and
    must not execute a suspension based solely on this returned recommendation.
    """
    if not isinstance(snapshot, KVSnapshot) or not isinstance(request, AdmissionRequest):
        raise TypeError("snapshot and request must use the declared immutable types")
    now = _timestamp(now_ms, "now_ms")
    if type(max_sample_age_ms) is not int or max_sample_age_ms < 1:
        raise ValueError("max_sample_age_ms must be a positive integer")
    if snapshot.captured_at_ms > now:
        raise ValueError("snapshot timestamp cannot be in the future")

    session_ids = {item.session_id for item in snapshot.sessions}
    if request.session_id in session_ids:
        raise ValueError("request session_id is already resident")

    age = now - snapshot.captured_at_ms
    resident = sum(item.resident_mib for item in snapshot.sessions)
    effective = snapshot.capacity_mib - snapshot.reserved_mib
    projected = resident + request.requested_mib

    def decision(
        action: Literal["admit", "suspend_then_admit", "defer"],
        victims: tuple[str, ...],
        projected_after: float,
        host_ack: bool,
        reason: str,
    ) -> AdmissionDecision:
        return AdmissionDecision(
            action=action,
            suspend_session_ids=victims,
            resident_before_mib=resident,
            requested_mib=request.requested_mib,
            effective_capacity_mib=effective,
            projected_resident_mib=projected_after,
            headroom_after_mib=effective - projected_after,
            sample_age_ms=age,
            host_ack_required=host_ack,
            reason=reason,
        )

    if age > max_sample_age_ms:
        return decision("defer", (), projected, False, "capacity snapshot is stale")
    if request.requested_mib > effective + _EPSILON_MIB:
        return decision("defer", (), projected, False, "request exceeds usable KV capacity")
    if projected <= effective + _EPSILON_MIB:
        return decision("admit", (), projected, False, "request fits measured KV headroom")

    incoming_priority = _PRIORITY[request.workload]
    candidates = [
        item for item in snapshot.sessions
        if item.suspendable and _PRIORITY[item.workload] > incoming_priority
    ]
    # Protect importance first; within a class suspend least-recently-active
    # sessions first, using resident size as a deterministic tie-breaker.
    candidates.sort(key=lambda item: (
        -_PRIORITY[item.workload],
        item.last_active_ms,
        -item.resident_mib,
        item.session_id,
    ))

    reclaimed = 0.0
    victims: list[str] = []
    for item in candidates:
        reclaimed += item.resident_mib
        victims.append(item.session_id)
        projected_after = projected - reclaimed
        if projected_after <= effective + _EPSILON_MIB:
            return decision(
                "suspend_then_admit",
                tuple(victims),
                projected_after,
                True,
                "lower-priority sessions must be host-suspended and remeasured first",
            )

    return decision(
        "defer",
        (),
        projected,
        False,
        "insufficient reclaimable KV without preempting protected sessions",
    )


__all__ = [
    "AdmissionDecision",
    "AdmissionRequest",
    "KVSession",
    "KVSnapshot",
    "plan_admission",
]
