"""One canonical event stream per STAR mission (#424): every event names its sender and its origin.

Events from different agents land in one ordered list so the chat shows one conversation. An agent's own
tool-call reports stay ``verified=False``; only the host can verify, and nothing here does. A stream
labelled ``simulation`` never presents its events as real tool use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from star.agent_session import SessionEvent

Origin = Literal["live", "simulation"]
_ORIGINS = ("live", "simulation")


@dataclass(frozen=True)
class MissionEvent:
    mission_id: str
    seq: int
    sender: str
    kind: str
    data: Mapping[str, Any]
    origin: Origin
    verified: bool = False

    def __post_init__(self) -> None:
        if not self.mission_id or not self.sender or self.seq < 1 or self.origin not in _ORIGINS:
            raise ValueError("A mission event needs a mission, a sender, a sequence number and an origin")


@dataclass
class MissionStream:
    mission_id: str
    origin: Origin
    events: list[MissionEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.mission_id or self.origin not in _ORIGINS:
            raise ValueError("A mission stream needs an id and a live or simulation origin")

    def add(self, sender: str, event: SessionEvent) -> MissionEvent:
        item = MissionEvent(self.mission_id, len(self.events) + 1, sender, event.kind,
                            dict(event.data), self.origin)
        self.events.append(item)
        return item

    def senders(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(e.sender for e in self.events))
