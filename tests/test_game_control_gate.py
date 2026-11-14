import hashlib

import pytest

from star.game_control_gate import (
    ActionPermit,
    GameAction,
    GameControlConfig,
    GameControlGate,
    GameObservation,
    GameTarget,
    GateState,
)


def make_config(**overrides):
    values = {
        "allowed_controls": frozenset({"W", "A", "S", "D", "SPACE"}),
        "max_observation_age_ms": 250,
        "max_action_age_ms": 250,
        "max_action_duration_ms": 200,
        "max_actions_per_second": 3,
    }
    values.update(overrides)
    return GameControlConfig(**values)


def make_target(**overrides):
    values = {
        "session_id": "session-1",
        "process_id": 1234,
        "process_start_token": "started-1",
        "window_id": "window-1",
        "executable_sha256": "a" * 64,
        "allowlisted": True,
        "owner_consent": True,
        "automation_permitted": True,
        "foreground": True,
        "manual_override": False,
    }
    values.update(overrides)
    return GameTarget(**values)


def target_fingerprint(target):
    material = "\0".join((
        target.session_id,
        str(target.process_id),
        target.process_start_token,
        target.window_id,
        target.executable_sha256,
    ))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def make_observation(target, *, sequence=1, frame_id=None, epoch="capture-1", captured_at=10.0):
    return GameObservation(
        session_id=target.session_id,
        frame_id=frame_id or f"frame-{sequence}",
        capture_epoch=epoch,
        sequence=sequence,
        captured_at=captured_at,
        target_fingerprint=target_fingerprint(target),
    )


def make_action(observation, *, action_id="action-1", issued_at=10.01,
                controls=("W",), duration_ms=100, mouse_dx=0.0, mouse_dy=0.0):
    return GameAction(
        action_id=action_id,
        session_id=observation.session_id,
        frame_id=observation.frame_id,
        capture_epoch=observation.capture_epoch,
        observation_sequence=observation.sequence,
        issued_at=issued_at,
        controls=controls,
        duration_ms=duration_ms,
        mouse_dx=mouse_dx,
        mouse_dy=mouse_dy,
    )


def armed_gate(*, config=None, target=None, now=10.0, expires_at=20.0):
    target = target or make_target()
    gate = GameControlGate(config or make_config())
    assert gate.arm(target, now=now, expires_at=expires_at).reason == "armed"
    return gate, target


def test_arm_requires_allowlist_consent_permission_and_foreground():
    for change, expected in (
        ({"allowlisted": False}, "game_not_allowlisted"),
        ({"owner_consent": False}, "owner_consent_required"),
        ({"automation_permitted": False}, "automation_not_permitted"),
        ({"foreground": False}, "target_not_foreground"),
        ({"manual_override": True}, "manual_override"),
    ):
        gate = GameControlGate(make_config())
        result = gate.arm(make_target(**change), now=10.0, expires_at=20.0)
        assert not result.accepted
        assert result.reason == expected
        assert gate.state is GateState.DISARMED


def test_arm_rejects_invalid_or_excessive_session_expiry():
    gate = GameControlGate(make_config())
    target = make_target()
    assert gate.arm(target, now=10.0, expires_at=10.0).reason == "invalid_session_expiry"
    assert gate.arm(target, now=10.0, expires_at=10_000.0).reason == "invalid_session_expiry"


def test_fresh_observation_authorizes_single_use_permit_and_timed_release():
    gate, target = armed_gate()
    observation = make_observation(target)
    assert gate.observe(observation, target, now=10.02).accepted

    authorized = gate.authorize(make_action(observation), target, now=10.03)
    assert authorized.accepted
    assert authorized.reason == "authorized"
    assert isinstance(authorized.permit, ActionPermit)
    assert gate.held_controls == ()

    assert authorized.permit is not None
    consumed = gate.consume(authorized.permit, target, now=10.04)
    assert consumed.accepted
    assert consumed.reason == "permit_consumed"
    assert gate.held_controls == ("W",)

    replay = gate.consume(authorized.permit, target, now=10.05)
    assert not replay.accepted
    assert replay.reason == "permit_missing_or_replayed"

    early = gate.release_due(now=10.10)
    assert early.accepted and early.reason == "no_release_due"
    released = gate.release_due(now=10.14)
    assert released.accepted
    assert released.release_controls == ("W",)
    assert gate.held_controls == ()


def test_stale_and_future_observations_are_rejected():
    gate, target = armed_gate()
    stale = make_observation(target, captured_at=9.0)
    assert gate.observe(stale, target, now=10.0).reason == "stale_observation"

    future = make_observation(target, sequence=2, captured_at=11.0)
    assert gate.observe(future, target, now=10.0).reason == "future_observation"


def test_non_monotonic_frames_are_rejected():
    gate, target = armed_gate()
    first = make_observation(target, sequence=4)
    assert gate.observe(first, target, now=10.01).accepted
    duplicate = make_observation(target, sequence=4, frame_id="another-frame")
    assert gate.observe(duplicate, target, now=10.02).reason == "non_monotonic_frame"


def test_action_must_reference_latest_frame_and_capture_epoch():
    gate, target = armed_gate()
    first = make_observation(target, sequence=1)
    second = make_observation(target, sequence=2, captured_at=10.02)
    assert gate.observe(first, target, now=10.01).accepted
    assert gate.observe(second, target, now=10.03).accepted

    old_frame = make_action(first)
    assert gate.authorize(old_frame, target, now=10.04).reason == "stale_frame"


def test_action_cannot_predate_the_observation():
    gate, target = armed_gate()
    observation = make_observation(target, captured_at=10.05)
    assert gate.observe(observation, target, now=10.06).accepted
    action = make_action(observation, issued_at=9.0)
    assert gate.authorize(action, target, now=10.07).reason == "action_predates_observation"


def test_action_age_and_duration_are_bounded():
    gate, target = armed_gate()
    observation = make_observation(target)
    assert gate.observe(observation, target, now=10.01).accepted

    stale = make_action(observation, action_id="stale", issued_at=9.0)
    assert gate.authorize(stale, target, now=10.02).reason == "stale_action"

    too_long = make_action(observation, action_id="long", duration_ms=201)
    assert gate.authorize(too_long, target, now=10.03).reason == "action_duration_exceeded"


def test_unapproved_controls_and_mouse_deltas_are_rejected():
    gate, target = armed_gate()
    observation = make_observation(target)
    assert gate.observe(observation, target, now=10.01).accepted

    unknown = make_action(observation, action_id="unknown", controls=("F12",))
    assert gate.authorize(unknown, target, now=10.02).reason == "control_not_allowed"

    huge_mouse = make_action(observation, action_id="mouse", controls=(), mouse_dx=101.0)
    assert gate.authorize(huge_mouse, target, now=10.03).reason == "mouse_delta_out_of_bounds"


def test_empty_action_and_duplicate_controls_are_rejected():
    gate, target = armed_gate()
    observation = make_observation(target)
    assert gate.observe(observation, target, now=10.01).accepted

    empty = make_action(observation, action_id="empty", controls=())
    assert gate.authorize(empty, target, now=10.02).reason == "empty_action"

    duplicate = make_action(observation, action_id="duplicate", controls=("W", "W"))
    assert gate.authorize(duplicate, target, now=10.03).reason == "duplicate_control"


def test_duplicate_action_id_is_rejected():
    gate, target = armed_gate()
    observation = make_observation(target)
    assert gate.observe(observation, target, now=10.01).accepted
    action = make_action(observation)
    assert gate.authorize(action, target, now=10.02).accepted
    assert gate.authorize(action, target, now=10.03).reason == "duplicate_action"


def test_action_rate_is_bounded():
    gate, target = armed_gate(config=make_config(max_actions_per_second=1))
    first = make_observation(target, sequence=1)
    assert gate.observe(first, target, now=10.01).accepted
    assert gate.authorize(make_action(first, action_id="one"), target, now=10.02).accepted

    second = make_observation(target, sequence=2, captured_at=10.03)
    assert gate.observe(second, target, now=10.04).accepted
    assert gate.authorize(
        make_action(second, action_id="two", issued_at=10.04),
        target,
        now=10.05,
    ).reason == "action_rate_limited"


def test_focus_loss_and_manual_override_stop_and_release_controls():
    for change, expected in (
        ({"foreground": False}, "target_not_foreground"),
        ({"manual_override": True}, "manual_override"),
    ):
        gate, target = armed_gate()
        observation = make_observation(target)
        assert gate.observe(observation, target, now=10.01).accepted
        permit = gate.authorize(make_action(observation), target, now=10.02).permit
        assert permit is not None
        assert gate.consume(permit, target, now=10.03).accepted

        stopped = gate.authorize(
            make_action(observation, action_id="next", issued_at=10.04),
            make_target(**change),
            now=10.04,
        )
        assert not stopped.accepted
        assert stopped.reason == expected
        assert stopped.release_controls == ("W",)
        assert gate.state is GateState.STOPPED


def test_target_process_identity_change_stops_session():
    gate, target = armed_gate()
    observation = make_observation(target)
    assert gate.observe(observation, target, now=10.01).accepted
    changed = make_target(process_start_token="started-2")
    result = gate.authorize(make_action(observation), changed, now=10.02)
    assert result.reason == "target_identity_changed"
    assert gate.state is GateState.STOPPED


def test_capture_epoch_change_stops_and_releases_controls():
    gate, target = armed_gate()
    first = make_observation(target, sequence=1, epoch="epoch-1")
    assert gate.observe(first, target, now=10.01).accepted
    permit = gate.authorize(make_action(first), target, now=10.02).permit
    assert permit is not None
    assert gate.consume(permit, target, now=10.03).accepted

    second = make_observation(target, sequence=2, epoch="epoch-2", captured_at=10.04)
    stopped = gate.observe(second, target, now=10.05)
    assert stopped.reason == "capture_epoch_changed"
    assert stopped.release_controls == ("W",)
    assert gate.state is GateState.STOPPED


def test_new_frame_invalidates_an_unconsumed_permit():
    gate, target = armed_gate()
    first = make_observation(target, sequence=1)
    assert gate.observe(first, target, now=10.01).accepted
    permit = gate.authorize(make_action(first), target, now=10.02).permit
    assert permit is not None

    second = make_observation(target, sequence=2, captured_at=10.03)
    assert gate.observe(second, target, now=10.04).accepted
    assert gate.consume(permit, target, now=10.05).reason == "permit_observation_stale"


def test_session_expiry_stops_and_returns_held_controls():
    gate, target = armed_gate(expires_at=10.5)
    observation = make_observation(target)
    assert gate.observe(observation, target, now=10.01).accepted
    permit = gate.authorize(make_action(observation), target, now=10.02).permit
    assert permit is not None
    assert gate.consume(permit, target, now=10.03).accepted

    result = gate.observe(make_observation(target, sequence=2, captured_at=10.5),
                          target, now=10.5)
    assert result.reason == "session_expired"
    assert result.release_controls == ("W",)
    assert gate.state is GateState.STOPPED


def test_owner_stop_returns_held_controls_and_clears_state():
    gate, target = armed_gate()
    observation = make_observation(target)
    assert gate.observe(observation, target, now=10.01).accepted
    permit = gate.authorize(make_action(observation), target, now=10.02).permit
    assert gate.consume(permit, target, now=10.03).accepted

    stopped = gate.stop()
    assert stopped.reason == "owner_stop"
    assert stopped.release_controls == ("W",)
    assert gate.state is GateState.STOPPED
    assert gate.held_controls == ()


def test_invalid_configuration_is_rejected():
    with pytest.raises(ValueError):
        make_config(allowed_controls=frozenset())
    with pytest.raises(ValueError):
        make_config(max_action_duration_ms=True)
    with pytest.raises(ValueError):
        make_config(max_session_seconds=float("inf"))


def test_pending_permits_are_bounded():
    gate, target = armed_gate(config=make_config(dedupe_capacity=1, max_actions_per_second=3))
    first = make_observation(target, sequence=1)
    assert gate.observe(first, target, now=10.01).accepted
    assert gate.authorize(make_action(first, action_id="one"), target, now=10.02).accepted

    second = make_observation(target, sequence=2, captured_at=10.03)
    assert gate.observe(second, target, now=10.04).accepted
    result = gate.authorize(
        make_action(second, action_id="two", issued_at=10.04),
        target,
        now=10.05,
    )
    assert result.reason == "permit_capacity"


def test_rearm_after_stop_starts_a_clean_session():
    gate, target = armed_gate()
    assert gate.stop().reason == "owner_stop"
    next_target = make_target(session_id="session-2")
    assert gate.arm(next_target, now=20.0, expires_at=30.0).accepted
    assert gate.state is GateState.ARMED


def test_permit_expiry_never_outlives_observation_freshness():
    gate, target = armed_gate()
    observation = make_observation(target, captured_at=10.0)
    assert gate.observe(observation, target, now=10.01).accepted
    action = make_action(observation, issued_at=10.20, duration_ms=200)
    authorized = gate.authorize(action, target, now=10.20)
    assert authorized.accepted
    assert authorized.permit is not None
    assert authorized.permit.expires_at <= 10.25
    assert authorized.permit.hold_until <= authorized.permit.expires_at
    assert gate.consume(authorized.permit, target, now=10.26).reason == "permit_expired"
