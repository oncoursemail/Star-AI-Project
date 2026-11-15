# STAR Run 49 — Live Continuity Integration, Memory-to-Action, and Generalist Intelligence

**Date:** 2026-11-15  
**Status:** Stacked implementation candidate; draft PR only  
**Parent:** Run 48 / draft PR #1202  
**Scope:** Connect bounded one-hour stream-event memory to STAR's existing governed speech-context path without creating a second scheduler, playback owner, or permission system.

## Executive finding

The repository already has distinct mechanisms for immediate reactions, verified gameplay practice, reviewed factual knowledge, and long-session event storage. Run 48 added the event store, but it was not yet connected to the actual stage plan. This run closes that specific gap.

The new integration carries a typed `ContinuityPacket` through the existing `StreamContextHost -> StreamBrainGovernor -> StarStage` path. It remains opt-in, host-clocked, bounded, and ephemeral. It is added only to viewer-question, game-observation, and game-success plans. It cannot schedule speech, interrupt audio, animate the avatar, execute tools, or authorize game input.

This is a stacked PR based on #1202. It does not alter the production `main` branch or claim that a live Windows streamer is already wired to the adapter.

## New research and engineering findings

### 1. AMA-Bench: agent memory must preserve objective and causal state

Primary paper: [AMA-Bench: Evaluating Long-Horizon Memory for Agentic Applications](https://arxiv.org/abs/2602.22769), ICML 2026.

AMA-Bench evaluates memory over agent-environment trajectories, not only dialogue. The authors identify missing causal and objective information as weaknesses of similarity-only retrieval. Their AMA-Agent proposal combines a causality graph with tool-augmented retrieval. The paper reports 57.22% average accuracy on its benchmark and an 11.16-point lead over its strongest memory baseline; those are paper-specific results, not STAR measurements.

**STAR decision:** keep the one-hour stream timeline separate from the verified game-skill/causal ledger. A stream event can say that a gate opened; only a trusted game-state adapter can establish which action caused it. Future gameplay memory should preserve state-before, action, state-after, objective, game build, map/seed, verifier, and evidence digest. Never infer causality from a narration summary.

### 2. MemPO: memory policy is an optimization target, not just storage

Primary paper: [MemPO: Self-Memory Policy Optimization for Long-Horizon Agents](https://aclanthology.org/2026.findings-acl.1166/), Findings of ACL 2026.

MemPO studies an agent policy that chooses what to retain and how to summarize it. The paper reports lower token use while preserving or improving task performance in its evaluation setup.

**STAR decision:** do not add an LLM call to the live ingestion path. Keep event capture cheap and deterministic; if later consolidation is introduced, run it in a background/idle worker, compare memory policies on fixed trajectories, and measure both recall quality and prompt-token cost. Keep original evidence digests and deletion semantics.

### 3. SWE-Skills-Bench: more skill documents do not automatically mean more intelligence

Primary paper: [SWE-Skills-Bench](https://arxiv.org/abs/2603.15401), March 2026 preprint.

The benchmark pairs 49 skills with real repositories and executable acceptance criteria. In its reported evaluation, 39 of 49 skills produced no pass-rate improvement, average gain was +1.2%, and version-mismatched guidance sometimes reduced success.

**STAR decision:** stop treating the size of the skill library as a quality metric. Route a skill only when its domain and project version match; measure paired success with/without it, token overhead, latency, regression rate, and sealed holdout performance. Retire or quarantine skills that cause negative transfer. This builds on STAR's existing skill-pack and review gates rather than creating another catalog.

### 4. MP-Bench: human-like streaming requires group-conversation judgment

Primary paper: [MP-Bench](https://aclanthology.org/2026.findings-emnlp.1437/), Findings of EMNLP 2026.

The paper evaluates turn-taking awareness, response appropriateness, and multiparty comprehension. The 12 evaluated agents performed poorly on group conversation, with real-time systems at or below 22% on multiparty comprehension in that benchmark.

**STAR decision:** continuity memory is context only. The existing RoomTurnDirector, ConversationContextIndex, playback clock, and playback owner remain the only authorities for addressee selection, waiting, interruption, speech start, and silence. Preserve source-scoped identities; never merge Twitch, YouTube, and local identities.

### 5. Roblox: creation is verified by play, not by generated files

Official source: [Building The Next Era of Creation on Roblox](https://about.roblox.com/newsroom/2026/11/building-the-next-era-of-creation-on-roblox), published 2026-11-13.

Roblox describes a game as a coupled system of scripts, physics, UI, server logic, and multiplayer state. It states that a game is finished only when people play it and emphasizes change/run/observe/fix/repeat. The article says creators of over 80% of the top 100 Roblox games use AI in their workflow; that is Roblox's reported ecosystem statistic, not a quality guarantee for any particular agent.

Official workflow reference: [Roblox Studio is Going Agentic](https://about.roblox.com/newsroom/2026/04/roblox-studio-going-agentic). Its plan/build/test direction and Studio MCP support reinforce STAR's existing Creator Brain design.

**STAR decision:** keep the creator loop tied to actual Studio inspection, playtests, logs, deterministic resets, server/client validation, and untouched holdouts. OpenGameEval and the causal game-probe work remain separate evaluators; stream-event memory cannot promote a skill.

## Implementation in this PR

### Files changed

- `star/stream_context_host.py`
- `star/stream_brain_governor.py`
- `star/stream_stage.py`
- `tests/test_stream_context_host.py`
- This research document.

### Integration behavior

1. The context host accepts an optional `StreamLongHorizonMemory`, opaque session ID, and the exact same trusted monotonic-millisecond clock used by the ingestion adapter.
2. Enabling the feature requires the existing owner and broadcast approvals plus a separate `audience_memory_approved=True` consent.
3. Disabling the context host erases that session from the in-memory event store.
4. Historical recall is never automatic. The host must explicitly request one of the supported 1/5/15/30/60-minute windows.
5. The host must separately attest `audience_can_hear=True` for that turn. Without it, the memory store returns no packet.
6. Retrieval is bounded to at most four events by default (hard maximum eight) and uses the existing event-store cap.
7. The typed packet travels through the existing governor and stage; only viewer questions, game observations, and game successes can receive it.
8. Retrieval faults fail closed and content-free counters never expose summaries, IDs, or evidence.
9. The stage still requires its existing speech lease, queue acknowledgement, device-confirmed audible start, playback completion, and interruption rules.

### Explicit non-goals

- No ASR, diarization, chat ingestion, event segmentation, or summarization model was added.
- No OBS, VTube Studio, Twitch, YouTube, microphone, audio, or Windows hardware adapter was added.
- No voice scheduler, RoomTurnDirector, playback clock, avatar frame pump, or GameControlGate was replaced.
- No game input, tool grant, publish permission, or public stream is authorized by memory.
- No model weights, datasets, cloud services, keys, user data, raw audio/video, or transcripts were added.
- No measured intelligence gain, gameplay mastery, inference speedup, or human-equivalent behavior is claimed.

## Performance rationale

The live path performs no model call, embedding, network request, disk write, or video/audio processing. Retrieval scans at most the bounded event list and returns a compact packet. The default limit of four items is deliberately lower than the store's hard maximum to reduce prompt-prefill cost.

The existing voice measurements in `docs/STAR_VOICE_CALLS.md` show why this matters: the local Qwen3.5-4B Vulkan call path was measured around 57 tokens/s with roughly 1.05 seconds from push-to-talk release to first sound in the documented run; a separate CPU server run under load showed 11.3 seconds to first token and 3.8–4.6 tokens/s. These are historical, machine-specific measurements, not a new benchmark or a claim about the current RTX 4060 setup.

The next experiment should compare continuity off/on using the same fixed historical questions and hardware. Record added prompt tokens, retrieval p50/p95/p99, TTFT, first-audible latency, answer evidence accuracy, game frame-time p95/p99, audio underruns, and OBS dropped frames. Reject the feature if historical recall does not improve held-out accuracy enough to justify added context cost.

## Acceptance tests

- Separate audience-memory consent is required when the memory store is configured.
- Historical events reach only the existing governed stage plan.
- A host-confirmed audience-hearing flag is required.
- Urgent danger and unrelated commentary do not receive historical context.
- Retrieval faults fail closed and do not leak event text through metrics.
- Disabling the context host erases its session.
- Existing hosts without a continuity store retain their old behavior.
- Existing speech lease, playback acknowledgement, and stop semantics remain unchanged.
- Full repository CI and the Windows desktop workflow must pass on the exact PR head before integration is considered verified.

## Next work

1. Complete exact-head CI for this stacked PR and parent #1202.
2. Connect a trusted local event adapter that emits minimized, moderated summaries from verified game/room events.
3. Add a historical-question classifier in the host, with explicit thresholds and a no-recall/abstain path; do not let model-generated text request memory permissions.
4. Build a causal game ledger from state/action/state-delta receipts and keep it separate from the stream timeline.
5. Evaluate memory retrieval on fixed 1/5/15/30/60-minute replay questions with evidence-backed scoring.
6. Run the same stream with continuity disabled/enabled under game + ASR/TTS + avatar + OBS mixed load.
7. Complete a private owner rehearsal with actual microphone, playback, avatar, and game capture before any public-stream permission is considered.
