import pytest

from star.active_perception import (
    ActivePerceptionPolicy,
    EvidenceCandidate,
    PerceptionPolicyConfig,
)


def candidate(candidate_id="c1", **overrides):
    values = {
        "candidate_id": candidate_id,
        "session_id": "session-1",
        "dedupe_key": f"event-{candidate_id}",
        "kind": "frame",
        "reason_code": "state_change",
        "priority": 0.8,
        "relevance": 0.9,
        "uncertainty": 0.7,
        "novelty": 0.6,
        "media_units": 2,
        "created_at": 10.0,
        "evidence_at": 10.0,
        "max_evidence_age_ms": 500,
        "deadline_at": 11.0,
    }
    values.update(overrides)
    return EvidenceCandidate(**values)


def select(items, *, policy=None, now=10.1):
    return (policy or ActivePerceptionPolicy()).select(
        items, session_id="session-1", now=now
    )


def test_selects_highest_value_per_media_unit_deterministically():
    expensive = candidate(
        "expensive", priority=1.0, relevance=1.0, uncertainty=1.0,
        novelty=1.0, media_units=16,
    )
    focused = candidate(
        "focused", priority=0.9, relevance=0.95, uncertainty=0.9,
        novelty=0.8, media_units=2,
    )
    first = select([expensive, focused])
    second = select([expensive, focused])
    assert first == second
    assert [item.candidate.candidate_id for item in first.selected] == ["focused", "expensive"]


def test_media_unit_budget_skips_expensive_candidate_and_keeps_smaller_one():
    policy = ActivePerceptionPolicy(
        PerceptionPolicyConfig(max_media_units_per_turn=4, max_requests_per_turn=3)
    )
    expensive = candidate("large", priority=1.0, relevance=1.0, media_units=5)
    small = candidate("small", media_units=2)
    result = select([expensive, small], policy=policy)
    assert [item.candidate.candidate_id for item in result.selected] == ["small"]
    assert result.used_media_units == 2
    assert result.remaining_media_units == 2
    assert ("large", "media_budget_exhausted") in {
        (item.candidate_id, item.reason) for item in result.rejected
    }


def test_stale_candidate_is_rejected():
    result = select([candidate(created_at=1.0)], now=10.0)
    assert not result.selected
    assert result.rejected[0].reason == "stale_candidate"


def test_future_candidate_is_rejected():
    result = select([candidate(created_at=20.0)], now=10.0)
    assert result.rejected[0].reason == "future_candidate"


def test_wrong_session_is_rejected():
    result = select([candidate(session_id="other-session")])
    assert result.rejected[0].reason == "wrong_session"


def test_expired_deadline_is_rejected():
    result = select([candidate(deadline_at=10.1)], now=10.1)
    assert result.rejected[0].reason == "deadline_expired"


def test_deadline_cannot_predate_candidate():
    result = select([candidate(created_at=10.2, deadline_at=10.1)], now=10.2)
    assert result.rejected[0].reason == "deadline_predates_candidate"


def test_stale_evidence_is_rejected_even_when_candidate_is_new():
    result = select([candidate(evidence_at=9.0, max_evidence_age_ms=500)])
    assert result.rejected[0].reason == "stale_evidence"


def test_future_evidence_is_rejected():
    result = select([candidate(evidence_at=20.0)], now=10.0)
    assert result.rejected[0].reason == "future_evidence"


def test_evidence_age_boundary_is_inclusive():
    result = select([candidate(evidence_at=9.5, max_evidence_age_ms=500)], now=10.0)
    assert len(result.selected) == 1


def test_candidate_age_boundary_is_inclusive():
    policy = ActivePerceptionPolicy(PerceptionPolicyConfig(max_candidate_age_ms=500))
    result = select([candidate(created_at=9.5)], policy=policy, now=10.0)
    assert len(result.selected) == 1


def test_duplicate_evidence_key_is_selected_only_once():
    first = candidate("first", dedupe_key="same-event", priority=0.9)
    second = candidate("second", dedupe_key="same-event", priority=0.7)
    result = select([second, first])
    assert [item.candidate.candidate_id for item in result.selected] == ["first"]
    assert ("second", "duplicate_evidence") in {
        (item.candidate_id, item.reason) for item in result.rejected
    }


def test_duplicate_candidate_id_is_rejected():
    result = select([candidate("same"), candidate("same", priority=0.1)])
    assert len(result.selected) == 1
    assert ("same", "duplicate_candidate_id") in {
        (item.candidate_id, item.reason) for item in result.rejected
    }


def test_request_limit_is_enforced():
    policy = ActivePerceptionPolicy(
        PerceptionPolicyConfig(max_requests_per_turn=2, max_media_units_per_turn=20)
    )
    items = [candidate(f"c{i}", dedupe_key=f"e{i}") for i in range(4)]
    result = select(items, policy=policy)
    assert len(result.selected) == 2
    assert sum(x.reason == "request_limit_exhausted" for x in result.rejected) == 2


def test_zero_information_candidate_is_not_selected():
    result = select([candidate(
        priority=0.0, relevance=0.0, uncertainty=0.0, novelty=0.0
    )])
    assert not result.selected
    assert result.rejected[0].reason == "no_information_value"


def test_non_candidate_is_rejected_without_crashing():
    result = select([object()])
    assert result.rejected[0].reason == "invalid_candidate"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"kind": "unknown"}, "invalid_kind"),
        ({"reason_code": "unsafe reason text"}, "invalid_reason_code"),
        ({"priority": True}, "invalid_priority"),
        ({"relevance": 1.1}, "invalid_relevance"),
        ({"uncertainty": -0.1}, "invalid_uncertainty"),
        ({"novelty": float("nan")}, "invalid_novelty"),
        ({"media_units": True}, "invalid_media_units"),
        ({"media_units": 129}, "invalid_media_units"),
        ({"max_evidence_age_ms": 10, "evidence_at": None},
         "evidence_age_limit_without_timestamp"),
    ],
)
def test_invalid_candidate_fields_fail_closed(change, reason):
    result = select([candidate(**change)])
    assert not result.selected
    assert result.rejected[0].reason == reason


def test_candidate_list_bound_is_enforced():
    policy = ActivePerceptionPolicy(PerceptionPolicyConfig(max_candidates=1))
    with pytest.raises(ValueError):
        select([candidate("a"), candidate("b")], policy=policy)


def test_invalid_session_and_clock_are_rejected():
    policy = ActivePerceptionPolicy()
    with pytest.raises(ValueError):
        policy.select([candidate()], session_id="", now=10.0)
    with pytest.raises(ValueError):
        policy.select([candidate()], session_id="session-1", now=float("inf"))


def test_invalid_config_is_rejected():
    with pytest.raises(ValueError):
        PerceptionPolicyConfig(max_media_units_per_turn=0)


def test_unknown_future_skew_is_bounded():
    policy = ActivePerceptionPolicy(PerceptionPolicyConfig(max_future_skew_ms=0))
    result = select([candidate(created_at=10.2)], policy=policy, now=10.0)
    assert result.rejected[0].reason == "future_candidate"
