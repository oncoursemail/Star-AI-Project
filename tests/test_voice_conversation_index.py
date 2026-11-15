import pytest

from star.voice.conversation_index import (
    ConversationContextIndex,
    ConversationEvent,
    ConversationIndexConfig,
)


def event(event_id="e1", *, sequence=1, observed_at=10.0, speaker="p1", source="chat",
          intent="direct_question", addressee=None, reply_to=None, topic=None,
          session="s1", confidence=0.99, final=True):
    return ConversationEvent(
        event_id=event_id,
        session_id=session,
        speaker_ref=speaker,
        source=source,
        intent=intent,
        sequence=sequence,
        observed_at=observed_at,
        addressee_ref=addressee,
        reply_to_event_id=reply_to,
        topic_ref=topic,
        confidence=confidence,
        final=final,
    )


def test_ingest_and_context_include_reply_chain_topic_and_recent_events():
    index = ConversationContextIndex("s1")
    assert index.ingest(event("root", sequence=1, topic="t1"), now=10.1).accepted
    assert index.ingest(
        event("reply", sequence=2, observed_at=10.2, speaker="p2", reply_to="root", topic="t1"),
        now=10.2,
    ).accepted
    assert index.ingest(
        event("followup", sequence=3, observed_at=10.3, reply_to="reply", topic="t1"),
        now=10.3,
    ).accepted

    context = index.context_for("followup", now=10.4)
    assert context is not None
    assert [item.event_id for item in context.reply_chain] == ["reply", "root"]
    assert [item.event_id for item in context.topic_events] == ["root", "reply", "followup"]
    assert [item.event_id for item in context.recent_events] == ["root", "reply", "followup"]
    assert not context.missing_reply_parent


def test_context_reports_missing_parent_after_eviction():
    index = ConversationContextIndex("s1", ConversationIndexConfig(max_events=1))
    assert index.ingest(event("root", sequence=1), now=10.0).accepted
    assert index.ingest(event("reply", sequence=2, observed_at=10.1, reply_to="root"), now=10.1).accepted
    context = index.context_for("reply", now=10.2)
    assert context is not None
    assert context.reply_chain == ()
    assert context.missing_reply_parent
    assert index.stats.evicted == 1


def test_wrong_session_and_stale_or_future_events_are_rejected():
    index = ConversationContextIndex("s1", ConversationIndexConfig(max_age_seconds=5.0))
    assert index.ingest(event("wrong", session="s2"), now=10.0).reason == "wrong_session"
    assert index.ingest(event("stale", observed_at=1.0), now=10.0).reason == "stale_event"
    assert index.ingest(event("future", observed_at=20.0), now=10.0).reason == "future_event"


def test_partial_events_are_not_retained_and_do_not_consume_sequence():
    index = ConversationContextIndex("s1")
    assert index.ingest(event("partial", final=False), now=10.0).reason == "partial_not_retained"
    assert index.ingest(event("final", sequence=1), now=10.0).accepted


def test_duplicate_and_out_of_order_events_are_rejected():
    index = ConversationContextIndex("s1")
    assert index.ingest(event("one", sequence=1), now=10.0).accepted
    assert index.ingest(event("one", sequence=2, observed_at=10.1), now=10.1).reason == "duplicate_event"
    assert index.ingest(event("two", sequence=1, observed_at=10.2), now=10.2).reason == "out_of_order_sequence"


def test_reply_parent_must_be_earlier_when_present():
    index = ConversationContextIndex("s1")
    assert index.ingest(event("one", sequence=1), now=10.0).accepted
    result = index.ingest(event("two", sequence=2, observed_at=10.1, reply_to="two"), now=10.1)
    assert result.reason == "self_reply"
    result = index.ingest(event("three", sequence=2, observed_at=10.1, reply_to="one"), now=10.1)
    assert result.accepted


def test_capacity_limits_are_enforced_and_old_events_expire():
    index = ConversationContextIndex(
        "s1",
        ConversationIndexConfig(max_events=4, max_participants=2, max_topics=1, max_age_seconds=5),
    )
    assert index.ingest(event("one", sequence=1, topic="t1", speaker="p1"), now=10.0).accepted
    assert index.ingest(event("two", sequence=2, observed_at=10.1, topic="t1", speaker="p2"), now=10.1).accepted
    topic_result = index.ingest(
        event("three", sequence=3, observed_at=10.2, topic="t2", speaker="p1"), now=10.2
    )
    participant_result = index.ingest(
        event("four", sequence=3, observed_at=10.2, speaker="p3"), now=10.2
    )
    assert topic_result.reason == "topic_capacity"
    assert participant_result.reason == "participant_capacity"
    assert index.ingest(event("five", sequence=3, observed_at=15.2, topic="t2", speaker="p3"), now=15.2).accepted
    assert index.stats.expired == 2


def test_clock_regression_and_invalid_metadata_fail_closed():
    index = ConversationContextIndex("s1")
    assert index.ingest(event("one", sequence=1, observed_at=10.0), now=10.0).accepted
    assert index.ingest(event("two", sequence=2, observed_at=9.9), now=10.0).reason == "observation_clock_regressed"
    assert index.ingest(event("bad", sequence=True, observed_at=10.1), now=10.1).reason == "invalid_sequence"
    bad_source = index.ingest(
        event("bad-source", sequence=2, observed_at=10.1, source="unknown"), now=10.1
    )
    bad_confidence = index.ingest(
        event("bad-confidence", sequence=2, observed_at=10.1, confidence=float("nan")), now=10.1
    )
    assert bad_source.reason == "invalid_source"
    assert bad_confidence.reason == "invalid_confidence"


def test_session_close_erases_context_and_rejects_future_events():
    index = ConversationContextIndex("s1")
    assert index.ingest(event("one"), now=10.0).accepted
    index.close()
    assert index.context_for("one", now=10.1) is None
    assert index.stats.events == 0
    assert index.stats.closed
    assert index.ingest(event("two", sequence=2, observed_at=10.2), now=10.2).reason == "session_closed"


def test_no_raw_message_fields_are_part_of_the_event_contract():
    assert {field for field in ConversationEvent.__dataclass_fields__} == {
        "event_id", "session_id", "speaker_ref", "source", "intent", "sequence",
        "observed_at", "addressee_ref", "reply_to_event_id", "topic_ref", "confidence", "final",
    }
    with pytest.raises(ValueError):
        ConversationContextIndex("contains spaces")


def test_capacity_is_reclaimed_when_the_oldest_event_is_evicted():
    index = ConversationContextIndex(
        "s1",
        ConversationIndexConfig(max_events=1, max_participants=1, max_topics=1),
    )
    assert index.ingest(event("one", sequence=1, topic="t1", speaker="p1"), now=10.0).accepted
    result = index.ingest(
        event("two", sequence=2, observed_at=10.1, topic="t2", speaker="p2"),
        now=10.1,
    )
    assert result.accepted
    assert result.evicted_events == 1
    assert index.stats.participants == 1
    assert index.stats.topics == 1


def test_unhashable_source_and_intent_are_rejected_without_raising():
    index = ConversationContextIndex("s1")
    assert index.ingest(event("source", source=[]), now=10.0).reason == "invalid_source"
    assert index.ingest(event("intent", intent={}), now=10.0).reason == "invalid_intent"
