"""Fail-closed freshness and consent gate for a future screen-to-controller adapter.

This module does not capture frames, inject input, inspect game memory, launch processes,
or grant permissions. A trusted host supplies verified target/consent/focus facts. The gate
binds each short-lived action permit to the exact fresh observation that produced it.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
import hashlib
import math
import re
import threading


_TOKEN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CONTROL = re.compile(r"^[A-Z0-9_.-]{1,32}$")


def _finite(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _token(value: object) -> bool:
    return isinstance(value, str) and _TOKEN.fullmatch(value) is not None


def _fingerprint(target: "GameTarget") -> str:
    material = "\0".join((
        target.session_id,
        str(target.process_id),
        target.process_start_token,
        target.window_id,
        target.executable_sha256,
    ))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class GateState(str, Enum):
    DISARMED = "disarmed"
    ARMED = "armed"
    STOPPED = "stopped"


@dataclass(frozen=True)
class GameControlConfig:
    """Per-game control limits supplied by trusted application configuration."""

    allowed_controls: frozenset[str]
    max_observation_age_ms: int = 250
    max_action_age_ms: int = 250
    max_action_duration_ms: int = 250
    max_actions_per_second: int = 30
    max_controls_per_action: int = 8
    max_mouse_delta: float = 100.0
    max_future_skew_ms: int = 50
    max_session_seconds: float = 1800.0
    dedupe_capacity: int = 1024

    def __post_init__(self) -> None:
        if type(self.allowed_controls) is not frozenset or not self.allowed_controls:
            raise ValueError("allowed_controls must be a non-empty frozenset")
        if any(type(item) is not str or _CONTROL.fullmatch(item) is None
               for item in self.allowed_controls):
            raise ValueError("allowed_controls must contain canonical control names")
        for name, low, high in (
            ("max_observation_age_ms", 1, 10_000),
            ("max_action_age_ms", 1, 5_000),
            ("max_action_duration_ms", 1, 2_000),
            ("max_actions_per_second", 1, 240),
            ("max_controls_per_action", 1, 32),
            ("max_future_skew_ms", 0, 1_000),
            ("dedupe_capacity", 1, 16_384),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer from {low} to {high}")
        if not _finite(self.max_mouse_delta) or not 0.0 < self.max_mouse_delta <= 10_000.0:
            raise ValueError("max_mouse_delta must be finite and positive")
        if not _finite(self.max_session_seconds) or not 0.0 < self.max_session_seconds <= 86_400.0:
            raise ValueError("max_session_seconds must be finite and bounded")


@dataclass(frozen=True)
class GameTarget:
    """Trusted host snapshot; booleans must come from host checks, never model text."""

    session_id: str
    process_id: int
    process_start_token: str
    window_id: str
    executable_sha256: str
    allowlisted: bool
    owner_consent: bool
    automation_permitted: bool
    foreground: bool
    manual_override: bool = False


@dataclass(frozen=True)
class GameObservation:
    session_id: str
    frame_id: str
    capture_epoch: str
    sequence: int
    captured_at: float
    target_fingerprint: str


@dataclass(frozen=True)
class GameAction:
    action_id: str
    session_id: str
    frame_id: str
    capture_epoch: str
    observation_sequence: int
    issued_at: float
    controls: tuple[str, ...]
    duration_ms: int
    mouse_dx: float = 0.0
    mouse_dy: float = 0.0


@dataclass(frozen=True)
class ActionPermit:
    action_id: str
    session_id: str
    target_fingerprint: str
    frame_id: str
    capture_epoch: str
    observation_sequence: int
    controls: tuple[str, ...]
    mouse_dx: float
    mouse_dy: float
    hold_until: float
    expires_at: float


@dataclass(frozen=True)
class GateResult:
    accepted: bool
    reason: str
    permit: ActionPermit | None = None
    release_controls: tuple[str, ...] = ()


class GameControlGate:
    """Single-session policy gate; it never performs operating-system input."""

    def __init__(self, config: GameControlConfig) -> None:
        if not isinstance(config, GameControlConfig):
            raise TypeError("config must be a GameControlConfig")
        self.config = config
        self._lock = threading.RLock()
        self._state = GateState.DISARMED
        self._session_id: str | None = None
        self._target_fingerprint: str | None = None
        self._session_expires_at: float | None = None
        self._capture_epoch: str | None = None
        self._latest_frame_id: str | None = None
        self._latest_sequence: int | None = None
        self._latest_captured_at: float | None = None
        self._action_times: deque[float] = deque()
        self._seen_action_order: deque[str] = deque()
        self._seen_actions: set[str] = set()
        self._issued_permits: dict[str, ActionPermit] = {}
        self._held_controls: set[str] = set()
        self._held_until: float | None = None

    @property
    def state(self) -> GateState:
        with self._lock:
            return self._state

    @property
    def held_controls(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._held_controls))

    def arm(self, target: GameTarget, *, now: float, expires_at: float) -> GateResult:
        """Arm only for one explicitly consented, allowlisted, permitted foreground game."""
        with self._lock:
            if self._state is GateState.ARMED:
                return GateResult(False, "already_armed")
            if not _finite(now) or not _finite(expires_at):
                return GateResult(False, "invalid_clock")
            reason = self._target_problem(target, require_foreground=True)
            if reason is not None:
                return GateResult(False, reason)
            if expires_at <= now or expires_at - now > self.config.max_session_seconds:
                return GateResult(False, "invalid_session_expiry")
            self._state = GateState.ARMED
            self._session_id = target.session_id
            self._target_fingerprint = _fingerprint(target)
            self._session_expires_at = float(expires_at)
            self._capture_epoch = None
            self._latest_frame_id = None
            self._latest_sequence = None
            self._latest_captured_at = None
            self._action_times.clear()
            self._seen_action_order.clear()
            self._seen_actions.clear()
            self._issued_permits.clear()
            self._held_controls.clear()
            self._held_until = None
            return GateResult(True, "armed")

    def observe(
        self, observation: GameObservation, target: GameTarget, *, now: float
    ) -> GateResult:
        """Accept a fresh, monotonic observation from the exact armed target."""
        with self._lock:
            if self._state is not GateState.ARMED:
                return GateResult(False, "not_armed")
            if not _finite(now):
                return GateResult(False, "invalid_clock")
            if self._session_expires_at is not None and now >= self._session_expires_at:
                return self._stop_locked("session_expired")
            problem = self._active_target_problem(target)
            if problem is not None:
                return self._stop_locked(problem)
            if not self._valid_observation(observation):
                return GateResult(False, "invalid_observation")
            assert self._target_fingerprint is not None
            if (observation.session_id != self._session_id
                    or observation.target_fingerprint != self._target_fingerprint):
                return self._stop_locked("observation_target_mismatch")
            if observation.captured_at > now + self.config.max_future_skew_ms / 1000.0:
                return GateResult(False, "future_observation")
            age_ms = (now - observation.captured_at) * 1000.0
            if age_ms > self.config.max_observation_age_ms:
                return GateResult(False, "stale_observation")
            if self._capture_epoch is not None and observation.capture_epoch != self._capture_epoch:
                return self._stop_locked("capture_epoch_changed")
            if self._latest_sequence is not None and observation.sequence <= self._latest_sequence:
                return GateResult(False, "non_monotonic_frame")
            self._capture_epoch = observation.capture_epoch
            self._latest_frame_id = observation.frame_id
            self._latest_sequence = observation.sequence
            self._latest_captured_at = float(observation.captured_at)
            return GateResult(True, "observation_accepted")

    def authorize(self, action: GameAction, target: GameTarget, *, now: float) -> GateResult:
        """Issue a one-use, short-lived permit for an action tied to the latest frame."""
        with self._lock:
            if self._state is not GateState.ARMED:
                return GateResult(False, "not_armed")
            if not _finite(now):
                return GateResult(False, "invalid_clock")
            if self._session_expires_at is not None and now >= self._session_expires_at:
                return self._stop_locked("session_expired")
            problem = self._active_target_problem(target)
            if problem is not None:
                return self._stop_locked(problem)
            if not self._valid_action(action):
                return GateResult(False, "invalid_action")
            if action.session_id != self._session_id:
                return GateResult(False, "wrong_session")
            if action.action_id in self._seen_actions:
                return GateResult(False, "duplicate_action")
            if (self._latest_frame_id is None or self._latest_sequence is None
                    or self._capture_epoch is None or self._latest_captured_at is None):
                return GateResult(False, "no_fresh_observation")
            if (action.frame_id != self._latest_frame_id
                    or action.observation_sequence != self._latest_sequence
                    or action.capture_epoch != self._capture_epoch):
                return GateResult(False, "stale_frame")
            observation_age_ms = (now - self._latest_captured_at) * 1000.0
            if observation_age_ms < -self.config.max_future_skew_ms or (
                observation_age_ms > self.config.max_observation_age_ms
            ):
                return GateResult(False, "stale_observation")
            if action.issued_at < self._latest_captured_at - self.config.max_future_skew_ms / 1000.0:
                return GateResult(False, "action_predates_observation")
            action_age_ms = (now - action.issued_at) * 1000.0
            if action_age_ms < -self.config.max_future_skew_ms:
                return GateResult(False, "future_action")
            if action_age_ms > self.config.max_action_age_ms:
                return GateResult(False, "stale_action")
            if action.duration_ms > self.config.max_action_duration_ms:
                return GateResult(False, "action_duration_exceeded")
            if len(action.controls) > self.config.max_controls_per_action:
                return GateResult(False, "too_many_controls")
            if len(set(action.controls)) != len(action.controls):
                return GateResult(False, "duplicate_control")
            if any(control not in self.config.allowed_controls for control in action.controls):
                return GateResult(False, "control_not_allowed")
            if (not _finite(action.mouse_dx) or not _finite(action.mouse_dy)
                    or abs(action.mouse_dx) > self.config.max_mouse_delta
                    or abs(action.mouse_dy) > self.config.max_mouse_delta):
                return GateResult(False, "mouse_delta_out_of_bounds")
            if not action.controls and action.mouse_dx == 0.0 and action.mouse_dy == 0.0:
                return GateResult(False, "empty_action")
            while self._action_times and now - self._action_times[0] >= 1.0:
                self._action_times.popleft()
            if len(self._action_times) >= self.config.max_actions_per_second:
                return GateResult(False, "action_rate_limited")
            for permit_id, issued in tuple(self._issued_permits.items()):
                if now > issued.expires_at:
                    self._issued_permits.pop(permit_id, None)
            if len(self._issued_permits) >= self.config.dedupe_capacity:
                return GateResult(False, "permit_capacity")
            assert self._target_fingerprint is not None
            assert self._session_expires_at is not None
            hold_until = min(now + action.duration_ms / 1000.0, self._session_expires_at)
            expires_at = min(
                now + self.config.max_action_age_ms / 1000.0,
                self._session_expires_at,
            )
            self._action_times.append(float(now))
            self._remember_action(action.action_id)
            permit = ActionPermit(
                action_id=action.action_id,
                session_id=action.session_id,
                target_fingerprint=self._target_fingerprint,
                frame_id=action.frame_id,
                capture_epoch=action.capture_epoch,
                observation_sequence=action.observation_sequence,
                controls=action.controls,
                mouse_dx=float(action.mouse_dx),
                mouse_dy=float(action.mouse_dy),
                hold_until=hold_until,
                expires_at=expires_at,
            )
            self._issued_permits[action.action_id] = permit
            return GateResult(True, "authorized", permit=permit)

    def consume(self, permit: ActionPermit, target: GameTarget, *, now: float) -> GateResult:
        """Consume an issued permit exactly once immediately before host execution."""
        with self._lock:
            if self._state is not GateState.ARMED:
                return GateResult(False, "not_armed")
            if not _finite(now):
                return GateResult(False, "invalid_clock")
            if self._session_expires_at is not None and now >= self._session_expires_at:
                return self._stop_locked("session_expired")
            problem = self._active_target_problem(target)
            if problem is not None:
                return self._stop_locked(problem)
            if not isinstance(permit, ActionPermit):
                return GateResult(False, "invalid_permit")
            issued = self._issued_permits.get(permit.action_id)
            if issued is None or issued != permit:
                return GateResult(False, "permit_missing_or_replayed")
            if now >= permit.expires_at or now >= permit.hold_until:
                self._issued_permits.pop(permit.action_id, None)
                return GateResult(False, "permit_expired")
            if (permit.session_id != self._session_id
                    or permit.target_fingerprint != self._target_fingerprint
                    or permit.capture_epoch != self._capture_epoch
                    or permit.frame_id != self._latest_frame_id
                    or permit.observation_sequence != self._latest_sequence):
                self._issued_permits.pop(permit.action_id, None)
                return GateResult(False, "permit_observation_stale")
            self._issued_permits.pop(permit.action_id, None)
            released = tuple(sorted(self._held_controls.difference(permit.controls)))
            self._held_controls = set(permit.controls)
            self._held_until = permit.hold_until if self._held_controls else None
            return GateResult(True, "permit_consumed", permit=permit, release_controls=released)

    def release_due(self, *, now: float) -> GateResult:
        """Return controls whose bounded hold duration has elapsed."""
        with self._lock:
            if not _finite(now):
                return GateResult(False, "invalid_clock")
            if self._held_until is None or now < self._held_until:
                return GateResult(True, "no_release_due")
            released = tuple(sorted(self._held_controls))
            self._held_controls.clear()
            self._held_until = None
            return GateResult(True, "action_duration_elapsed", release_controls=released)

    def stop(self, reason: str = "owner_stop") -> GateResult:
        """Revoke the session immediately and return every held control for release."""
        with self._lock:
            if not _token(reason):
                reason = "stopped"
            return self._stop_locked(reason)

    def _stop_locked(self, reason: str) -> GateResult:
        released = tuple(sorted(self._held_controls))
        self._state = GateState.STOPPED
        self._session_id = None
        self._target_fingerprint = None
        self._session_expires_at = None
        self._capture_epoch = None
        self._latest_frame_id = None
        self._latest_sequence = None
        self._latest_captured_at = None
        self._action_times.clear()
        self._seen_action_order.clear()
        self._seen_actions.clear()
        self._issued_permits.clear()
        self._held_controls.clear()
        self._held_until = None
        return GateResult(False, reason, release_controls=released)

    def _remember_action(self, action_id: str) -> None:
        self._seen_actions.add(action_id)
        self._seen_action_order.append(action_id)
        while len(self._seen_action_order) > self.config.dedupe_capacity:
            expired = self._seen_action_order.popleft()
            self._seen_actions.discard(expired)

    def _active_target_problem(self, target: GameTarget) -> str | None:
        problem = self._target_problem(target, require_foreground=True)
        if problem is not None:
            return problem
        if self._target_fingerprint is None or _fingerprint(target) != self._target_fingerprint:
            return "target_identity_changed"
        return None

    @staticmethod
    def _target_problem(target: GameTarget, *, require_foreground: bool) -> str | None:
        if not isinstance(target, GameTarget):
            return "invalid_target"
        if (not _token(target.session_id) or type(target.process_id) is not int
                or target.process_id <= 0 or not _token(target.process_start_token)
                or not _token(target.window_id) or not isinstance(target.executable_sha256, str)
                or _SHA256.fullmatch(target.executable_sha256) is None):
            return "invalid_target"
        if any(type(value) is not bool for value in (
            target.allowlisted, target.owner_consent, target.automation_permitted,
            target.foreground, target.manual_override,
        )):
            return "invalid_target"
        if not target.allowlisted:
            return "game_not_allowlisted"
        if not target.owner_consent:
            return "owner_consent_required"
        if not target.automation_permitted:
            return "automation_not_permitted"
        if require_foreground and not target.foreground:
            return "target_not_foreground"
        if target.manual_override:
            return "manual_override"
        return None

    @staticmethod
    def _valid_observation(observation: GameObservation) -> bool:
        return (
            isinstance(observation, GameObservation)
            and _token(observation.session_id)
            and _token(observation.frame_id)
            and _token(observation.capture_epoch)
            and type(observation.sequence) is int
            and observation.sequence > 0
            and _finite(observation.captured_at)
            and isinstance(observation.target_fingerprint, str)
            and _SHA256.fullmatch(observation.target_fingerprint) is not None
        )

    @staticmethod
    def _valid_action(action: GameAction) -> bool:
        return (
            isinstance(action, GameAction)
            and _token(action.action_id)
            and _token(action.session_id)
            and _token(action.frame_id)
            and _token(action.capture_epoch)
            and type(action.observation_sequence) is int
            and action.observation_sequence > 0
            and _finite(action.issued_at)
            and type(action.controls) is tuple
            and all(type(control) is str and _CONTROL.fullmatch(control) is not None
                    for control in action.controls)
            and type(action.duration_ms) is int
            and 1 <= action.duration_ms <= 2_000
            and _finite(action.mouse_dx)
            and _finite(action.mouse_dy)
        )
