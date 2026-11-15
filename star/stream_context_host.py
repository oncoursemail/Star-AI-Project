"""On-air, consent-scoped retrieval of verified STAR experiences and public facts.

Connects the existing StreamBrainGovernor (hardware-aware speech timing),
StreamEpisode (signed *practice* evidence) and KnowledgeStore (reviewed notes).
Unlike merely writing these packets to a document, this host actually forwards
them to a StarStage plan through the governed, live speech path.

The host performs no inference, recording, networking, playback, game input,
personal-data retention or publishing. It never reads hidden validation data.
An embedding local application must moderate audience text, provide trustworthy
clocks and explicitly curate public note IDs and game action IDs. These public
permissions cannot be granted by model-generated text or a viewer.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from threading import RLock, get_ident
from typing import Callable
import time

from .knowledge import KnowledgeStore
from .stream_brain_governor import StreamBrainGovernor
from .stream_episode import StreamEpisode
from .stream_knowledge import public_knowledge_packet
from .stream_long_horizon_memory import StreamLongHorizonMemory
from .stream_stage import StagePlan
from .stream_turntaking import TurnAdvice

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")


class StreamContextHost:
    """A fail-conservative, owner-approved local streaming context adapter.

    SQLite connections belong to one host worker thread. The caller must
    marshal calls to prepare() onto the constructing thread. The two clocks
    have different purposes: UTC for knowledge age, and Unix seconds for
    signed practice freshness. The governor independently uses monotonic time.
    """

    def __init__(
        self, *, governor: StreamBrainGovernor, knowledge: KnowledgeStore,
        episode: StreamEpisode | None, project: str,
        public_note_ids: frozenset[int],
        public_action_ids: frozenset[str],
        utc_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        unix_clock: Callable[[], int] = lambda: int(time.time()),
        continuity_memory: StreamLongHorizonMemory | None = None,
        continuity_session_id: str | None = None,
        continuity_clock_ms: Callable[[], int] | None = None,
    ) -> None:
        if not isinstance(governor, StreamBrainGovernor):
            raise TypeError("governor must be the existing StreamBrainGovernor")
        if not isinstance(knowledge, KnowledgeStore):
            raise TypeError("knowledge must be an existing KnowledgeStore")
        if episode is not None and not isinstance(episode, StreamEpisode):
            raise TypeError("episode must be StreamEpisode or None")
        if type(project) is not str or _ID.fullmatch(project) is None:
            raise ValueError("project must be a bounded project name")
        if (type(public_note_ids) is not frozenset or len(public_note_ids) > 128 or
                any(type(x) is not int or x <= 0 for x in public_note_ids)):
            raise ValueError("public notes must be curated numeric IDs")
        if (type(public_action_ids) is not frozenset or len(public_action_ids) > 32 or
                any(type(x) is not str or _ID.fullmatch(x) is None for x in public_action_ids)):
            raise ValueError("public actions must be curated short IDs")
        if not callable(utc_clock) or not callable(unix_clock):
            raise TypeError("trusted clocks are required")
        if continuity_memory is not None and not isinstance(
                continuity_memory, StreamLongHorizonMemory):
            raise TypeError("continuity_memory must be StreamLongHorizonMemory")
        if continuity_memory is None:
            if continuity_session_id is not None or continuity_clock_ms is not None:
                raise ValueError("continuity session and clock require a memory store")
        else:
            if type(continuity_session_id) is not str or _ID.fullmatch(continuity_session_id) is None:
                raise ValueError("continuity_session_id must be a bounded opaque ID")
            if not callable(continuity_clock_ms):
                raise TypeError("continuity_clock_ms must use the same trusted monotonic clock as ingestion")
        self._governor = governor
        self._knowledge = knowledge
        self._episode = episode
        self._project = project
        self._note_ids = public_note_ids
        self._action_ids = public_action_ids
        self._utc_clock = utc_clock
        self._unix_clock = unix_clock
        self._continuity_memory = continuity_memory
        self._continuity_session_id = continuity_session_id
        self._continuity_clock_ms = continuity_clock_ms
        self._continuity_started = False
        self._owner_thread = get_ident()
        self._lock = RLock()
        self._enabled = False
        self._counts = {
            "prepared": 0, "silence": 0, "knowledge_candidates": 0,
            "episode_candidates": 0, "retrieval_faults": 0,
            "continuity_candidates": 0, "continuity_misses": 0,
            "continuity_faults": 0,
        }

    def enable(self, *, owner_approved: bool = False,
               broadcast_approved: bool = False,
               audience_memory_approved: bool = False) -> None:
        """Enable reviewed context; event memory needs a third, separate consent."""
        if owner_approved is not True or broadcast_approved is not True:
            raise PermissionError("owner and on-air publication approvals required")
        if type(audience_memory_approved) is not bool:
            raise ValueError("audience_memory_approved must be boolean")
        with self._lock:
            if self._enabled:
                raise RuntimeError("disable before enabling a new context session")
            if self._continuity_memory is not None:
                assert self._continuity_session_id is not None
                assert self._continuity_clock_ms is not None
                self._continuity_memory.start_session(
                    self._continuity_session_id,
                    now_ms=self._continuity_clock_ms(),
                    owner_approved=owner_approved,
                    audience_memory_approved=audience_memory_approved,
                )
                self._continuity_started = True
            elif audience_memory_approved:
                raise ValueError("no continuity memory is configured")
            self._enabled = True

    def disable(self) -> None:
        """Stop context retrieval and erase this session's ephemeral event memory."""
        with self._lock:
            self._enabled = False
            if self._continuity_started and self._continuity_memory is not None:
                assert self._continuity_session_id is not None
                self._continuity_memory.stop_session(self._continuity_session_id)
                self._continuity_started = False

    def prepare(
        self, *, moderated_question: str | None = None,
        voice_speaking: bool = False,
        viewer_speaking: bool = False,
        gameplay_critical: bool = False,
        turn: TurnAdvice | None = None,
        continuity_lookback_ms: int | None = None,
        continuity_topic_id: str | None = None,
        continuity_kinds: frozenset[str] | None = None,
        continuity_limit: int = 4,
        audience_can_hear: bool = False,
    ) -> StagePlan | None:
        """Prepare a hardware-governed response with approved context only.

        The question must be supplied after upstream moderation and is used
        solely as a database lookup term. It is not placed in this packet.
        StarStage injects reviewed facts, practice evidence, and continuity only
        for their explicitly allowed intent kinds. Historical recall is opt-in
        per request and requires a host-confirmed audience-hearing flag. Inference
        jobs still require a separate governor speech lease and audio acknowledgement.
        """
        if moderated_question is not None and (
                type(moderated_question) is not str
                or not 1 <= len(moderated_question.strip()) <= 300):
            raise ValueError("moderated_question must contain 1..300 characters")
        if type(audience_can_hear) is not bool:
            raise ValueError("audience_can_hear must be a trusted boolean")
        if type(continuity_limit) is not int or not 1 <= continuity_limit <= 8:
            raise ValueError("continuity_limit must be 1..8")
        if continuity_lookback_ms is not None:
            if type(continuity_lookback_ms) is not int or continuity_lookback_ms not in {
                60_000, 300_000, 900_000, 1_800_000, 3_600_000
            }:
                raise ValueError("continuity lookback must be 1, 5, 15, 30, or 60 minutes")
            if self._continuity_memory is None:
                raise RuntimeError("continuity memory is not configured")
        elif continuity_topic_id is not None or continuity_kinds is not None:
            raise ValueError("continuity filters require an explicit lookback request")
        if continuity_topic_id is not None and (
                type(continuity_topic_id) is not str or _ID.fullmatch(continuity_topic_id) is None):
            raise ValueError("continuity_topic_id must be a bounded opaque ID")
        if continuity_kinds is not None and (
                type(continuity_kinds) is not frozenset or not continuity_kinds):
            raise ValueError("continuity_kinds must be a nonempty frozenset")
        if get_ident() != self._owner_thread:
            raise RuntimeError("marshal context retrieval to the SQLite owner thread")
        with self._lock:
            if not self._enabled or self._governor.status()["enabled"] is not True:
                self._counts["silence"] += 1
                return None
            if self._governor.status()["stage_phase"] != "idle":
                self._counts["silence"] += 1
                return None

            public_facts = None
            public_episode = None
            continuity_packet = None
            try:
                if moderated_question is not None and self._note_ids:
                    public_facts = public_knowledge_packet(
                        self._knowledge, project=self._project,
                        query=moderated_question,
                        public_note_ids=self._note_ids, now=self._utc_clock(),
                        limit=3,
                    )
                if self._episode is not None and self._action_ids:
                    public_episode = self._episode.public_packet(
                        now_unix_s=self._unix_clock(),
                        public_action_ids=self._action_ids,
                        broadcast_approved=True, limit=3,
                    )
                if continuity_lookback_ms is not None:
                    assert self._continuity_memory is not None
                    assert self._continuity_session_id is not None
                    assert self._continuity_clock_ms is not None
                    continuity_packet = self._continuity_memory.retrieve(
                        self._continuity_session_id,
                        now_ms=self._continuity_clock_ms(),
                        lookback_ms=continuity_lookback_ms,
                        topic_id=continuity_topic_id,
                        kinds=continuity_kinds,
                        limit=continuity_limit,
                        broadcast_approved=True,
                        audience_can_hear=audience_can_hear,
                    )
                    if continuity_packet is None:
                        self._counts["continuity_misses"] += 1
            except Exception:
                # A broken note DB, UTC clock, or invalid episode state must
                # not degrade into invented context or a partial disclosure.
                self._counts["retrieval_faults"] += 1
                if continuity_lookback_ms is not None:
                    self._counts["continuity_faults"] += 1
                self._counts["silence"] += 1
                return None

            result = self._governor.prepare(
                voice_speaking=voice_speaking,
                viewer_speaking=viewer_speaking,
                gameplay_critical=gameplay_critical, turn=turn,
                knowledge=public_facts, episode=public_episode,
                continuity=continuity_packet,
            )
            if result is None:
                self._counts["silence"] += 1
            else:
                self._counts["prepared"] += 1
                self._counts["knowledge_candidates"] += int(
                    public_facts is not None and result.kind == "viewer_question"
                )
                self._counts["episode_candidates"] += int(
                    public_episode is not None and result.kind in {
                        "viewer_question", "game_success", "game_observation"
                    }
                )
                self._counts["continuity_candidates"] += int(
                    continuity_packet is not None and result.kind in {
                        "viewer_question", "game_success", "game_observation"
                    }
                )
            return result

    def status(self) -> dict[str, int | bool]:
        """Anonymous counts, never actual viewer text or private fact content."""
        with self._lock:
            return {**self._counts, "enabled": self._enabled}


__all__ = ["StreamContextHost"]
