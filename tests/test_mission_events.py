"""One canonical mission event stream: every event carries its sender and whether it was real or simulated."""
import pytest

from star.agent_session import SessionEvent
from star.mission_events import MissionEvent, MissionStream


def test_session_events_become_ordered_events_with_distinct_senders():
    s = MissionStream("m1", origin="simulation")
    a = s.add("opencode", SessionEvent("text", {"text": "hi"}))
    b = s.add("gemini-cli", SessionEvent("tool_call", {"id": "t1", "source": "agent_reported"}))
    assert [e.seq for e in s.events] == [1, 2] and (a.sender, b.sender) == ("opencode", "gemini-cli")
    assert {e.mission_id for e in s.events} == {"m1"}
    assert s.senders() == ("opencode", "gemini-cli")


def test_simulation_never_claims_real_tool_use():
    s = MissionStream("m1", origin="simulation")
    e = s.add("opencode", SessionEvent("tool_call", {"id": "t1"}))
    assert e.origin == "simulation" and e.verified is False
    live = MissionStream("m2", origin="live").add("opencode", SessionEvent("tool_call", {"id": "t1"}))
    assert live.verified is False   # an agent's own report is never host-verified


def test_rejects_unnamed_sender_and_unknown_origin():
    with pytest.raises(ValueError):
        MissionStream("m1", origin="guess")
    with pytest.raises(ValueError):
        MissionStream("m1", origin="live").add("", SessionEvent("text"))
    with pytest.raises(ValueError):
        MissionEvent("", 1, "a", "text", {}, "live")
