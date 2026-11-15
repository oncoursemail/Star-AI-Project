# STAR Run 48 — Hour-Scale Session Continuity, Event Memory, and Streaming Intelligence

**Date:** 2026-11-15  
**Status:** Implementation candidate; draft PR only  
**Scope:** Long-form VTuber continuity and a low-overhead event-memory substrate

## Executive finding

STAR already has three related but deliberately different mechanisms:

- `StreamMomentMemory` selects immediate gameplay reactions and has a short age window.
- `StreamEpisode` summarizes signed PRACTICE outcomes for one game situation; it is not a general stream-event timeline.
- `StreamContextHost` retrieves reviewed knowledge and approved practice aggregates through the existing `StreamBrainGovernor` and `StarStage` path.

The missing layer is a bounded, queryable timeline of **public, host-attested events across a long stream**. A 60-minute stream can contain a question, an answer, a game setback, a comeback, a creator action, and a later callback. A short rolling window cannot reliably connect those events; retaining full audio/video or raw chat would be unnecessary and privacy-expensive.

Run 48 adds `star/stream_long_horizon_memory.py`: an in-memory, one-hour event index with explicit consent, host-signed event envelopes, source-scoped sequence numbers, time-window retrieval, deletion tombstones, and content-free health metrics.

This is a substrate, not a claim that STAR now understands every livestream. The module is not yet wired into the live voice path; the existing room director, turn-taking gate, playback clock, and stage remain the only speech authorities.

## Research findings

### 1. StreamArena / StreamMind — measure the whole hour, not the last few seconds

Primary paper: [StreamArena: Toward Continuous, Interactive, and Long-Horizon Agentic Streaming Video Understanding](https://arxiv.org/abs/2608.05703), submitted 2026-08-06.

The benchmark contains 243 full-length videos averaging 88.8 minutes and 3,646 open-ended questions. It evaluates real-time perception, historical retrospection, proactive interaction, and multimodal tool use. The paper identifies a failure pattern directly relevant to STAR: short recent-frame windows miss distant events, text-only conversion can lose visual evidence, and repeated compression can erode fine detail. Its StreamMind architecture separates latency-critical interaction from asynchronous memory construction and retrieval.

**STAR decision:** keep the immediate reaction path small and responsive. Build event summaries asynchronously in the trusted host, then retrieve a small number of relevant, time-bounded events only when a question or planned callback needs history. Do not run a large model over every frame or every chat message.

### 2. EventMemAgent — organize around event boundaries

Primary paper: [EventMemAgent: Hierarchical Event-Centric Memory for Online Video Understanding with Adaptive Tool Use](https://arxiv.org/abs/2602.15329), listed as submitted 2026-09-11.

The paper separates a bounded short-term buffer from an event-granular long-term archive and describes active evidence capture. Its key lesson for STAR is architectural: a stream should be represented as meaningful events, not an unbounded sequence of frames.

**STAR decision:** accept only already-curated event summaries with an evidence digest. The new module does not perform vision, ASR, event segmentation, or LLM summarization; those expensive tasks belong in an asynchronous host worker and are not implemented here.

### 3. Chronos — time must be part of the memory key

Primary paper: [Chronos: Temporal-Aware Conversational Agents with Structured Event Retrieval for Long-Term Memory](https://arxiv.org/abs/2603.16862), submitted 2026-03-17.

Chronos pairs timestamped event records with turn-level context and uses query-specific temporal retrieval. The paper reports results on LongMemEvalS, but those benchmark scores are not transferable to STAR.

**STAR decision:** use a monotonic event clock, explicit lookback horizons, source provenance, and topic filters. A semantically similar event from the wrong time or another stream is not valid continuity evidence.

### 4. TiMem — hierarchical consolidation belongs off the live path

Primary paper: [TiMem: Temporal-Hierarchical Memory Consolidation for Long-Horizon Conversational Agents](https://aclanthology.org/2026.findings-acl.1091/).

TiMem introduces a temporal memory tree and complexity-aware recall. Its paper reports reduced recalled memory length on LoCoMo. This is a useful later direction for cross-session memory, but it is not a reason to add an embedding model or consolidation job to STAR's latency-critical stream loop.

**STAR decision:** keep the first implementation bounded and symbolic. Consider hierarchical consolidation only after a measured retrieval benchmark shows that the fixed one-hour event index is insufficient.

### 5. TSHMem — temporal validity is as important as semantic relevance

Primary paper: [TSHMem: A Temporal-Semantic Hierarchical Memory Graph for Long-Term Conversational Agents](https://aclanthology.org/2026.emnlp-main.1034/).

TSHMem explicitly targets semantically similar but temporally invalid evidence and reports fewer retrieved evidence tokens in its benchmark setup.

**STAR decision:** filter by session and time before relevance ranking. Do not let a matching topic pull in an event from a different session or an expired time window.

### 6. Episodic and relational memory are complementary

Primary paper: [Long-Term Agent Memory through Complementary Curation and Consolidation](https://aclanthology.org/2026.findings-aacl.218.pdf), Findings of IJCNLP-AACL 2026 (2026-11-06 to 2026-11-10).

The authors combine episodic memories with structured relational memories and report 90.2% on LoCoMo and 85.5% on LongMemEval-S for their evaluated system. They also study offline consolidation. These are paper-specific results, not STAR results.

**STAR decision:** preserve the separation already present in STAR:
- session event continuity for "what happened during this stream?";
- reviewed knowledge for factual/general-knowledge questions;
- signed practice evidence for game-skill history;
- durable user-approved memory for cross-session preferences.

Do not merge these into one undifferentiated transcript store.

### 7. Multiparty conversation is still difficult

Primary paper: [MP-Bench: Evaluating Voice Agents as a Multiparty Conversation Participant](https://aclanthology.org/2026.findings-emnlp.1437/).

The authors evaluate turn-taking awareness, response appropriateness, and comprehension in multiparty conversations. They report weak performance among the 12 evaluated agents, including at-or-below 22% multiparty comprehension for the real-time systems tested.

**STAR decision:** event continuity must not become a second conversation director. The event index can provide context; the existing room host decides who is speaking, whether STAR is addressed, whether another person already answered, and whether silence is appropriate. This implementation stores no speaker IDs and never merges identities across Twitch, YouTube, or local sources.

### 8. Roblox creation is a runtime problem, not a file-generation problem

Official source: [Building The Next Era of Creation on Roblox](https://about.roblox.com/newsroom/2026/11/building-the-next-era-of-creation-on-roblox), published 2026-11-13.

Roblox describes a game as a system of scripts, physics, UI, server logic, and multiplayer state. It emphasizes the loop of change, run, observe, fix, repeat, and states that games are verified by play.

**STAR decision:** keep the Creator Brain roadmap tied to real Studio inspection, deterministic test places, playtests, logs, server/client checks, and independent holdouts. Event memory can later provide a timeline of verified creator actions, but it cannot substitute for Studio tests.

## Implementation delivered

### New module

`star/stream_long_horizon_memory.py`

Public types:

- `StreamEvent`: one short, host-attested, audience-safe event.
- `ContinuityItem`: a compact recall item with relative age and a local evidence reference.
- `ContinuityPacket`: a bounded user-priority context packet; it is not a speech request.
- `StreamLongHorizonMemory`: bounded in-memory session index.

### Invariants

1. **Explicit opt-in:** starting a session requires both owner approval and separate audience-memory approval. Retrieval additionally requires a distinct broadcast approval and a host-confirmed audience-hearing state.
2. **Host authenticity:** event payloads use domain-separated HMAC receipts. The host key must be supplied at runtime and is not stored in the repository.
3. **Honest evidence semantics:** an HMAC authenticates the adapter that submitted an event; it does not prove the adapter's observation was true.
4. **No raw media:** no PCM, video frames, transcripts, provider message IDs, viewer handles, or speaker identities are represented.
5. **Platform isolation:** source-scoped sequence and deduplication keys keep Twitch, YouTube, game, and local events separate. No cross-platform person identity is inferred.
6. **Moderation:** only explicitly audience-safe, approved summaries are accepted. Contact details, URLs, handles, and phone-like strings are rejected by a conservative preflight.
7. **Bounded retention:** default maximum is 512 events per session, four active sessions, and 60 minutes of retention. Oldest events are evicted under capacity pressure.
8. **Replay protection:** source/event keys are retained only within the one-hour replay horizon. Duplicate, out-of-order, stale, and pre-session events are rejected.
9. **Deletion:** a trusted moderation tombstone removes an event from recall while keeping its key blocked against replay until its retention horizon ends. Stopping the session erases all session state.
10. **Time correctness:** all timestamps use the host's monotonic millisecond clock; wall-clock changes cannot reorder a live session.
11. **Small retrieval:** only 1, 5, 15, 30, and 60 minute horizons are accepted. Retrieval is bounded to eight items and can filter by topic and event kind.
12. **No authority:** packets are explicitly labeled user-priority context, never commands or tool permissions. They do not start TTS, OBS, game input, or network operations.
13. **Content-free metrics:** status exposes counts only, never event text, IDs, hashes, or viewer data.

### Performance rationale

The module is pure Python and standard-library only. Ingestion does no inference, embedding, disk I/O, or network I/O. Retrieval scans at most the configured event cap (512 by default), then emits at most eight summaries and a 4 KB context record. This is intentionally simpler than a vector database for a one-hour, bounded event window.

A future Windows host should call it from a worker that is separate from audio callbacks and the game/render thread. No database or model call belongs in a microphone callback, audio callback, or 60 FPS capture loop.

### Existing systems preserved

- `StreamMomentMemory` remains the short-window reaction/cue selector.
- `StreamEpisode` remains the signed PRACTICE outcome memory.
- `StreamContextHost` remains the approved knowledge/practice retrieval adapter.
- `StreamBrainGovernor`, `StreamDirector`, `TurnTakingGate`, `StarStage`, and the physical playback host remain authoritative for speech and interruption.

The new memory module is **not yet wired into** `StreamContextHost` or `StarStage`. That integration needs its own change and acceptance tests so it cannot bypass intent filtering, audience consent, turn-taking, playback acknowledgement, or the resource governor.

## Test coverage

New file: `tests/test_stream_long_horizon_memory.py`

24 offline tests cover:
- dual approval;
- HMAC validation;
- unstarted sessions;
- audience-hearing consent;
- all five retrieval horizons;
- topic/kind filtering;
- independent source sequences;
- absence of speaker/provider IDs in model-facing context;
- moderation and audience-safety rejection;
- contact-detail preflight;
- stale, future, and pre-session events;
- deduplication and replay rejection;
- source sequence ordering;
- TTL expiry;
- bounded eviction with replay protection;
- moderation tombstones;
- session isolation and deletion;
- active-session limits;
- backward clock rejection;
- bounded packets and content-free metrics.

The isolated Python 3.13 harness ran **24 tests successfully** before the GitHub commit. Exact-head repository CI remains required.

## Run 49 integration plan

1. Add a trusted Windows event adapter that normalizes game state, moderated room events, and creator milestones into local opaque event IDs.
2. Run summary curation asynchronously; never invoke a large model on every frame or every chat message.
3. Connect the recall packet to the existing `StreamContextHost` / `StreamBrainGovernor` / `StarStage` path with intent-specific inclusion rules.
4. Ensure a viewer question can retrieve relevant history, but ordinary chat cannot request tools or force speech.
5. Ensure game-danger events take priority over callbacks and chat.
6. Keep the existing playback epoch and audible acknowledgement authoritative.
7. Add 60-minute rehearsal traces with queries at 1, 5, 15, 30, and 60 minutes.
8. Measure retrieval p50/p95/p99, memory size, false callbacks, stale recall, missed recall, and mixed-load FPS/audio/OBS impact.
9. Test deletion and moderation revocation across every active cache before any public pilot.
10. Keep cross-session memory separate and owner-reviewed.

## Broader STAR roadmap retained

- **Gamer Brain:** live-speed, slowed, and paused performance must be measured separately; use state-based outcomes and held-out game transfer, not self-reported success.
- **Creator Brain:** use official Roblox Studio MCP and StudioTestService, disposable test places, server/client assertions, visual evidence, and independent holdouts.
- **General knowledge:** retain source URL, publication time, scope, confidence, contradiction links, and freshness. Distinguish factual knowledge from procedural skill and autobiographical memory.
- **Streaming personality:** use natural silence, addressee awareness, multiparty comprehension, evidence-grounded callbacks, playback-synchronized expression, and stable persona. Do not fabricate human experiences.
- **Speed:** use event-triggered perception, bounded context, asynchronous memory construction, cache-aware model routing, and mixed-load A/B measurements. Optimize useful completed work per second, not tokens/sec alone.

## Limitations

- This PR adds an offline in-memory event store and tests only.
- No Twitch/YouTube credentials or live connections were created.
- No microphone, OBS, VTube Studio, Roblox Studio, game controller, GPU model, or Windows host was exercised.
- No persistent database, transcript archive, or viewer identity graph was added.
- No claim of human equivalence, autonomous streaming readiness, game mastery, or measured speedup is made.
- No third-party benchmark dataset or model weights were copied into STAR.

## Sources

- StreamArena / StreamMind (2026-08-06): https://arxiv.org/abs/2608.05703
- EventMemAgent (2026-09-11): https://arxiv.org/abs/2602.15329
- Chronos (2026-03-17): https://arxiv.org/abs/2603.16862
- TiMem (Findings of ACL 2026): https://aclanthology.org/2026.findings-acl.1091/
- TSHMem (EMNLP 2026): https://aclanthology.org/2026.emnlp-main.1034/
- Long-Term Agent Memory through Complementary Curation and Consolidation (IJCNLP-AACL 2026, 2026-11-06 to 2026-11-10): https://aclanthology.org/2026.findings-aacl.218.pdf
- MP-Bench (Findings of EMNLP 2026): https://aclanthology.org/2026.findings-emnlp.1437/
- Roblox creator direction (published 2026-11-13): https://about.roblox.com/newsroom/2026/11/building-the-next-era-of-creation-on-roblox
