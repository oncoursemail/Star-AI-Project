from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import hmac
import unittest

from star.stream_long_horizon_memory import StreamEvent, StreamLongHorizonMemory

KEY = b"stream-event-host-key-32-bytes-minimum-123456"
START = 100_000


def make_event(
    event_id: str,
    sequence: int,
    occurred_ms: int,
    *,
    source: str = "game",
    kind: str = "gameplay",
    topic_id: str = "boss",
    summary: str = "The boss changed phase after the gate opened.",
) -> StreamEvent:
    return StreamEvent(
        session_id="session_one",
        event_id=event_id,
        sequence=sequence,
        source=source,
        kind=kind,
        topic_id=topic_id,
        summary=summary,
        occurred_ms=occurred_ms,
        evidence_sha256=sha256(event_id.encode()).hexdigest(),
    )


def sign(event: StreamEvent) -> str:
    return hmac.new(KEY, event.canonical_bytes(), sha256).hexdigest()


class StreamLongHorizonMemoryTests(unittest.TestCase):
    def setUp(self):
        self.memory = StreamLongHorizonMemory(host_key=KEY)
        self.memory.start_session(
            "session_one", now_ms=START,
            owner_approved=True, audience_memory_approved=True,
        )

    def test_two_separate_approvals_are_required(self):
        memory = StreamLongHorizonMemory(host_key=KEY)
        with self.assertRaises(PermissionError):
            memory.start_session("session_one", now_ms=START, owner_approved=True)
        with self.assertRaises(PermissionError):
            memory.start_session("session_one", now_ms=START, audience_memory_approved=True)

    def test_host_signature_is_required(self):
        event = make_event("evt_1", 1, START + 1000)
        with self.assertRaises(PermissionError):
            self.memory.ingest(event, "0" * 64, now_ms=START + 1000)

    def test_unstarted_session_is_silent(self):
        event = replace(make_event("evt_1", 1, START + 1000), session_id="not_started")
        self.assertFalse(self.memory.ingest(event, sign(event), now_ms=START + 1000))

    def test_retrieval_is_off_without_audience_consent(self):
        event = make_event("evt_1", 1, START + 1000)
        self.assertTrue(self.memory.ingest(event, sign(event), now_ms=START + 1000))
        self.assertIsNone(self.memory.retrieve(
            "session_one", now_ms=START + 2000, audience_can_hear=False,
        ))

    def test_retrieval_requires_separate_broadcast_approval(self):
        event = make_event("evt_1", 1, START + 1000)
        self.memory.ingest(event, sign(event), now_ms=START + 1000)
        self.assertIsNone(self.memory.retrieve(
            "session_one", now_ms=START + 2000, audience_can_hear=True,
        ))

    def test_all_five_memory_horizons(self):
        now = START + 3_700_000
        ages = (59 * 60_000, 29 * 60_000, 14 * 60_000, 4 * 60_000, 30_000)
        for index, age in enumerate(ages, 1):
            event = make_event(f"evt_{index}", index, now - age)
            self.assertTrue(self.memory.ingest(event, sign(event), now_ms=now))
        expected = {60_000: 1, 300_000: 2, 900_000: 3, 1_800_000: 4, 3_600_000: 5}
        for horizon, count in expected.items():
            packet = self.memory.retrieve(
                "session_one", now_ms=now, lookback_ms=horizon,
                audience_can_hear=True, limit=8,
            )
            self.assertIsNotNone(packet)
            self.assertEqual(len(packet.items), count)

    def test_topic_and_kind_filtering(self):
        now = START + 10_000
        a = make_event("evt_1", 1, now - 3000, topic_id="boss", kind="gameplay")
        b = make_event("evt_2", 2, now - 2000, topic_id="shop", kind="creator_action")
        for event in (a, b):
            self.memory.ingest(event, sign(event), now_ms=now)
        packet = self.memory.retrieve(
            "session_one", now_ms=now, lookback_ms=60_000,
            topic_id="boss", kinds=frozenset({"gameplay"}),
            audience_can_hear=True,
        )
        self.assertEqual([item.topic_id for item in packet.items], ["boss"])

    def test_cross_platform_sequences_are_independent(self):
        now = START + 5000
        twitch = make_event("evt_t", 1, now - 2000, source="twitch", kind="viewer_question")
        youtube = make_event("evt_y", 1, now - 1000, source="youtube", kind="viewer_answer")
        self.assertTrue(self.memory.ingest(twitch, sign(twitch), now_ms=now))
        self.assertTrue(self.memory.ingest(youtube, sign(youtube), now_ms=now))

    def test_no_speaker_identity_field_or_provider_id_in_prompt(self):
        event = make_event("local_evt_1", 1, START + 1000)
        self.memory.ingest(event, sign(event), now_ms=START + 1000)
        packet = self.memory.retrieve(
            "session_one", now_ms=START + 2000,
            lookback_ms=60_000, audience_can_hear=True,
        )
        self.assertFalse(hasattr(event, "speaker_id"))
        self.assertNotIn(event.event_id, packet.context_record)
        self.assertNotIn(event.evidence_sha256, packet.context_record)
        self.assertEqual(packet.user_message()["role"], "user")

    def test_unapproved_or_unsafe_event_is_rejected_at_construction(self):
        base = make_event("evt_1", 1, START + 1000)
        with self.assertRaises(ValueError):
            replace(base, audience_safe=False)
        with self.assertRaises(ValueError):
            replace(base, moderation_state="pending")

    def test_private_contact_details_are_rejected(self):
        bad = (
            "Email alex@example.com about the event.",
            "See https://example.com/private",
            "Viewer @somehandle asked a question.",
            "Call 555-123-4567 about the stream.",
        )
        for index, summary in enumerate(bad, 1):
            with self.subTest(summary=summary), self.assertRaises(ValueError):
                make_event(f"evt_{index}", index, START + index, summary=summary)

    def test_future_and_pre_session_events_are_rejected(self):
        future = make_event("evt_future", 1, START + 20_000)
        self.assertFalse(self.memory.ingest(future, sign(future), now_ms=START + 1000))
        prior = make_event("evt_prior", 1, START - 1)
        self.assertFalse(self.memory.ingest(prior, sign(prior), now_ms=START + 1000))

    def test_stale_events_are_rejected(self):
        now = START + 3_700_000
        stale = make_event("evt_stale", 1, START + 1)
        self.assertFalse(self.memory.ingest(stale, sign(stale), now_ms=now))

    def test_duplicate_event_is_rejected(self):
        event = make_event("evt_1", 1, START + 1000)
        self.memory.ingest(event, sign(event), now_ms=START + 1000)
        with self.assertRaises(ValueError):
            self.memory.ingest(event, sign(event), now_ms=START + 2000)

    def test_source_sequence_must_increase(self):
        first = make_event("evt_1", 2, START + 2000)
        second = make_event("evt_2", 1, START + 3000)
        self.memory.ingest(first, sign(first), now_ms=START + 3000)
        with self.assertRaises(ValueError):
            self.memory.ingest(second, sign(second), now_ms=START + 3000)

    def test_retention_expiry(self):
        event = make_event("evt_1", 1, START + 1000)
        self.memory.ingest(event, sign(event), now_ms=START + 1000)
        self.assertIsNone(self.memory.retrieve(
            "session_one", now_ms=START + 3_601_001,
            lookback_ms=3_600_000, audience_can_hear=True,
        ))
        self.assertEqual(self.memory.status()["expired"], 1)

    def test_bounded_eviction_keeps_replay_protection(self):
        memory = StreamLongHorizonMemory(host_key=KEY, max_events_per_session=2)
        memory.start_session("session_one", now_ms=START,
                             owner_approved=True, audience_memory_approved=True)
        events = [make_event(f"evt_{i}", i, START + i * 1000) for i in range(1, 4)]
        for event in events:
            self.assertTrue(memory.ingest(event, sign(event), now_ms=event.occurred_ms))
        self.assertEqual(memory.status()["retained_events"], 2)
        with self.assertRaises(ValueError):
            memory.ingest(events[0], sign(events[0]), now_ms=START + 5000)

    def test_moderation_tombstone_removes_event_and_blocks_replay(self):
        event = make_event("evt_1", 1, START + 1000)
        self.memory.ingest(event, sign(event), now_ms=START + 1000)
        with self.assertRaises(PermissionError):
            self.memory.revoke_event("session_one", "game", "evt_1")
        self.assertTrue(self.memory.revoke_event(
            "session_one", "game", "evt_1", trusted_moderation=True,
        ))
        self.assertIsNone(self.memory.retrieve(
            "session_one", now_ms=START + 2000,
            lookback_ms=60_000, audience_can_hear=True,
        ))
        with self.assertRaises(ValueError):
            self.memory.ingest(event, sign(event), now_ms=START + 3000)

    def test_sessions_do_not_mix(self):
        other = StreamLongHorizonMemory(host_key=KEY)
        other.start_session("session_two", now_ms=START,
                            owner_approved=True, audience_memory_approved=True)
        event = make_event("evt_1", 1, START + 1000)
        other_event = replace(event, session_id="session_two")
        other.ingest(other_event, sign(other_event), now_ms=START + 1000)
        self.assertIsNone(other.retrieve(
            "session_one", now_ms=START + 2000, audience_can_hear=True,
        ))

    def test_stop_session_erases_all_memory_and_replay_state(self):
        event = make_event("evt_1", 1, START + 1000)
        self.memory.ingest(event, sign(event), now_ms=START + 1000)
        self.assertTrue(self.memory.stop_session("session_one"))
        self.assertEqual(self.memory.status()["active_sessions"], 0)
        self.assertFalse(self.memory.ingest(event, sign(event), now_ms=START + 2000))

    def test_active_session_capacity_is_bounded(self):
        memory = StreamLongHorizonMemory(host_key=KEY, max_sessions=1)
        memory.start_session("session_one", now_ms=START,
                             owner_approved=True, audience_memory_approved=True)
        with self.assertRaises(OverflowError):
            memory.start_session("session_two", now_ms=START,
                                 owner_approved=True, audience_memory_approved=True)

    def test_clock_cannot_move_backwards(self):
        event = make_event("evt_1", 1, START + 1000)
        self.memory.ingest(event, sign(event), now_ms=START + 1000)
        with self.assertRaises(ValueError):
            self.memory.retrieve("session_one", now_ms=START + 500,
                                 broadcast_approved=True, audience_can_hear=True)

    def test_packet_is_bounded_and_does_not_authorize_speech(self):
        event = make_event("evt_1", 1, START + 1000)
        self.memory.ingest(event, sign(event), now_ms=START + 1000)
        packet = self.memory.retrieve(
            "session_one", now_ms=START + 2000,
            lookback_ms=60_000, audience_can_hear=True,
        )
        self.assertLess(len(packet.context_record), 4000)
        self.assertFalse(hasattr(packet, "audio"))
        self.assertFalse(hasattr(self.memory, "broadcast"))

    def test_metrics_are_content_free(self):
        event = make_event("evt_1", 1, START + 1000)
        self.memory.ingest(event, sign(event), now_ms=START + 1000)
        status = str(self.memory.status())
        self.assertNotIn("boss", status)
        self.assertNotIn("evt_1", status)
        self.assertNotIn(event.evidence_sha256, status)


if __name__ == "__main__":
    unittest.main()
