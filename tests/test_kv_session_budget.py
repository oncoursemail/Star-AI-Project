"""Deterministic tests for host-neutral KV session admission planning."""
import math
import pytest

from star.kv_session_budget import (
    AdmissionRequest,
    KVSession,
    KVSnapshot,
    plan_admission,
)


def session(name, workload, mib, active=100, suspendable=True):
    return KVSession(name, workload, mib, active, suspendable)


def snapshot(*sessions, capacity=8192, reserve=1024, captured=1000):
    return KVSnapshot(capacity, reserve, captured, tuple(sessions))


def request(name="new", workload="speech", mib=1024):
    return AdmissionRequest(name, workload, mib)


def test_admit_when_measured_headroom_is_sufficient():
    result = plan_admission(
        snapshot(session("voice", "speech", 2048)),
        request(mib=2048), now_ms=1100,
    )
    assert result.action == "admit"
    assert result.immediately_admissible
    assert not result.host_ack_required
    assert result.suspend_session_ids == ()


def test_defer_when_capacity_is_full_and_no_lower_priority_session_exists():
    result = plan_admission(
        snapshot(session("voice-1", "speech", 4500),
                 session("voice-2", "speech", 4500), capacity=10000, reserve=1000),
        request(mib=1024), now_ms=1100,
    )
    assert result.action == "defer"
    assert result.suspend_session_ids == ()


def test_speech_can_propose_suspending_background_training():
    result = plan_admission(
        snapshot(session("training", "training", 5000)),
        request(mib=2500), now_ms=1100,
    )
    assert result.action == "suspend_then_admit"
    assert result.suspend_session_ids == ("training",)
    assert result.host_ack_required
    assert not result.immediately_admissible


def test_equal_priority_is_never_preempted():
    result = plan_admission(
        snapshot(session("old-speech", "speech", 5000)),
        request(name="new-speech", workload="speech", mib=3000),
        now_ms=1100,
    )
    assert result.action == "defer"
    assert result.suspend_session_ids == ()


def test_higher_priority_is_never_preempted():
    result = plan_admission(
        snapshot(session("speech", "speech", 5000)),
        request(workload="training", mib=3000), now_ms=1100,
    )
    assert result.action == "defer"


def test_non_suspendable_background_session_is_protected():
    result = plan_admission(
        snapshot(session("training", "training", 5000, suspendable=False)),
        request(mib=3000), now_ms=1100,
    )
    assert result.action == "defer"


def test_lower_priority_oldest_session_is_selected_first():
    result = plan_admission(
        snapshot(
            session("research-old", "research", 1200, active=100),
            session("research-new", "research", 1200, active=900),
            session("training", "training", 1200, active=200),
        ),
        request(mib=5500), now_ms=1100,
    )
    assert result.action == "suspend_then_admit"
    assert result.suspend_session_ids[0] == "training"
    assert result.suspend_session_ids[1] == "research-old"


def test_minimal_victim_set_is_returned():
    result = plan_admission(
        snapshot(
            session("train-large", "training", 3000),
            session("train-small", "training", 700),
        ),
        request(mib=4000), now_ms=1100,
    )
    assert result.action == "suspend_then_admit"
    assert result.suspend_session_ids == ("train-large",)


def test_snapshot_reserve_is_never_consumed():
    result = plan_admission(
        snapshot(session("current", "interactive", 2500),
                 capacity=4096, reserve=1024),
        request(workload="interactive", mib=600), now_ms=1100,
    )
    assert result.action == "defer"
    assert result.effective_capacity_mib == 3072


def test_request_larger_than_usable_capacity_is_deferred():
    result = plan_admission(
        snapshot(capacity=4096, reserve=1024),
        request(mib=3073), now_ms=1100,
    )
    assert result.action == "defer"
    assert "exceeds" in result.reason


def test_stale_snapshot_fails_closed():
    result = plan_admission(
        snapshot(session("training", "training", 2000)),
        request(mib=2000), now_ms=4001, max_sample_age_ms=2000,
    )
    assert result.action == "defer"
    assert result.suspend_session_ids == ()
    assert "stale" in result.reason


def test_future_snapshot_is_rejected():
    with pytest.raises(ValueError, match="future"):
        plan_admission(snapshot(captured=1200), request(), now_ms=1100)


def test_duplicate_session_ids_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        snapshot(session("same", "training", 100),
                 session("same", "research", 100))


def test_request_cannot_reuse_an_active_session_id():
    with pytest.raises(ValueError, match="already resident"):
        plan_admission(
            snapshot(session("same", "training", 100)),
            request(name="same"), now_ms=1100,
        )


@pytest.mark.parametrize("value", [True, -1, math.nan, math.inf, "2048"])
def test_invalid_resident_measurements_are_rejected(value):
    with pytest.raises(ValueError):
        session("bad", "training", value)


@pytest.mark.parametrize("workload", ["admin", "shell", "tool", None])
def test_unknown_workload_classes_are_rejected(workload):
    with pytest.raises(ValueError):
        request(workload=workload)


@pytest.mark.parametrize("timestamp", [True, -1, 1000.0, "1000"])
def test_timestamps_must_be_monotonic_integer_milliseconds(timestamp):
    with pytest.raises(ValueError):
        plan_admission(snapshot(), request(), now_ms=timestamp)


def test_invalid_capacity_and_reserve_are_rejected():
    with pytest.raises(ValueError):
        KVSnapshot(0, 0, 1000, ())
    with pytest.raises(ValueError):
        KVSnapshot(4096, 4096, 1000, ())


def test_snapshot_cannot_claim_more_resident_memory_than_capacity():
    with pytest.raises(ValueError, match="exceeds"):
        snapshot(session("a", "speech", 3000),
                 session("b", "training", 3000), capacity=4096, reserve=512)


def test_stale_data_does_not_propose_suspensions():
    result = plan_admission(
        snapshot(session("training", "training", 3000)),
        request(mib=3000), now_ms=5000, max_sample_age_ms=1000,
    )
    assert result.action == "defer"
    assert not result.host_ack_required
    assert result.suspend_session_ids == ()


def test_planning_is_pure_and_does_not_mutate_the_snapshot():
    original = snapshot(session("training", "training", 2500))
    before = original.sessions
    plan_admission(original, request(mib=2500), now_ms=1100)
    assert original.sessions == before
    assert original.sessions[0].resident_mib == 2500


def test_max_sample_age_must_be_positive_integer():
    for value in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            plan_admission(snapshot(), request(), now_ms=1100,
                           max_sample_age_ms=value)
