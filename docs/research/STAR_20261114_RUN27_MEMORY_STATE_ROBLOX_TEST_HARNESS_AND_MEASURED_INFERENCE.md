# STAR Run 27 — Memory State Integrity, Roblox Test Harness, and Measured Local Inference

**Research date:** 2026-11-14  
**Repository:** `oncoursemail/Star-AI-Project`  
**Research branch:** `research/star-run24-integration-blueprint-20261114`  
**Related draft trains:** #1151, #1177, #1178, #1180, #1140, #1142, #1160, #1166, #1167, #1108, #1109, #1117  
**Scope:** long-horizon memory correctness, official Roblox multiplayer test automation, local inference observability, CPU-first streaming ASR, audio callback integration, and capability acceptance.

---

## Executive decision

Run 27 adds five implementation-relevant findings that were not sufficiently resolved by the previous research documents:

1. **Memory must preserve execution state and revisions, not merely retrieve semantically similar notes.** LongMINT demonstrates severe interference and revision-recall weaknesses; MAGE proposes a hierarchical state tree with explicit growth, compression, validation, and revision.
2. **STAR Creator should use Roblox's official StudioTestService for deterministic multiplayer tests.** This provides a real path beyond single-client Play mode and is especially valuable for lobbies, parties, replication, matchmaking, disconnects, and client/server trust boundaries.
3. **The llama.cpp server exposes enough instrumentation to separate prompt-prefill, decode, cache reuse, slot pressure, and queueing.** STAR should consume those measurements before changing model, context, batching, cache, or offload defaults.
4. **ASR candidates should be compared as complete streaming providers.** Moonshine and sherpa-onnx are practical local candidates, but STAR should retain Faster-Whisper until paired accuracy/latency tests on the owner's hardware justify a change.
5. **The open voice branches contain a concrete integration gap.** PR #1151 has the bounded asynchronous speaker-meter worker; PR #1178 still has an output callback that performs NumPy RMS work after preloading NumPy. The branches are on different bases and should be reconciled deliberately, not blindly merged.

This is an integration and experiment specification. It does not install a model, add a dependency, change production defaults, enable a permission, or claim a measured speedup.

---

## 1. Repository reality and the actionable audio integration gap

The repository audit was performed against live GitHub metadata on 2026-11-14.

### Relevant branch state

| PR | Responsibility | Inspected head | State |
|---|---|---|---|
| #1151 | Playback clock, microphone freshness, asynchronous output metering | `f73fc7e6ecab46370fd6ea80dab9b875c5e426cc` | Open draft |
| #1177 | Durable task and communication ledger | `c3ef33d5634828c23b6b7492f69c273bb8d767ce` | Open draft |
| #1178 | Natural streamer persona and resolved-reply stopping | `0fb5d5e75c41be8e509c924d4f75863fcf8351d4` | Open draft |
| #1180 | Research and integration blueprint | `08d5d6d66805d573ea3e14d9d77eabaa6bb5e5f8` | Open draft |
| #1140/#1142 | Authoritative resource admission and stream-pressure composition | Separate dependent drafts | Open drafts |
| #1160 | Stable-prefix incremental thinking | Separate dependent draft | Open draft |
| #1166/#1167 | Paired evaluation and inference timing | Separate drafts | Open drafts |

### What the source comparison shows

In PR #1178's `star/voice/devices.py`, NumPy is imported before opening the stream, which removes a cold import from the first callback. However, the callback still converts the PCM block to a NumPy array, allocates intermediate arrays, calculates RMS, and appends meter history.

PR #1151 moves RMS work to a bounded worker queue. The output callback copies PCM, records bounded playback telemetry, and enqueues best-effort meter observations. Queue overflow drops meter observations rather than audio; the worker detects sequence gaps and treats uncertain echo-meter state conservatively.

**Integration decision:** use PR #1151's worker-based metering as the candidate implementation when the #1178 branch is reconciled. Preserve #1178's persona and room-stop behavior. Do not copy the whole branch or change the authoritative scheduler as part of this audio integration.

### Remaining callback limitations

PR #1151 is a soft-real-time improvement, not a hard-real-time audio engine:

- The speaker callback still acquires the PCM-buffer lock and copies a bounded block.
- The microphone callback still allocates a bytes object and uses a bounded `queue.Queue` plus a statistics lock.
- Python scheduling and the GIL remain in the path.
- A native SPSC ring buffer is not justified until Windows device traces show reproducible callback deadline misses, priority inversion, or underflows.

The next measurement should report callback duration distribution, input overflow, queue drops, output underflows, queue age, and p95/p99 jitter on actual Windows devices. A smaller audio period must not be forced without measuring CPU cost and device support.

**Source references:** [PortAudio callback guidance](https://github.com/PortAudio/portaudio/wiki/Tips_Callbacks) · [python-sounddevice](https://python-sounddevice.readthedocs.io/en/latest/) · [Microsoft IAudioClient3 shared-mode engine period](https://learn.microsoft.com/en-us/windows/win32/api/audioclient/nf-audioclient-iaudioclient3-getsharedmodeengineperiod).

---

## 2. Long-horizon memory: preserve state, revisions, and causal history

### 2.1 LongMINT — memory under interference

[LongMINT (2026-05-18)](https://arxiv.org/abs/2605.18565) evaluates memory when facts are updated repeatedly and later information interferes with earlier facts. Its benchmark includes 15.6k question/answer pairs, long interconnected contexts, multiple domains, and both single-target and multi-target questions.

The paper reports 27.9% average accuracy across seven evaluated systems, with substantial difficulty on questions requiring aggregation across multiple pieces of evidence. It identifies retrieval and memory construction as major limitations and reports degradation when facts are revised or interrupted by later updates.

**STAR implication:** a memory result must carry its time, source, revision, and validity scope. A newer value should supersede an older value only within the same entity/property/scope. It must not erase historical evidence needed to answer “what was true before?” or “why did the plan change?”

### 2.2 MAGE — memory as execution-state management

[MAGE (2026-06-04)](https://arxiv.org/abs/2606.06090) models long-horizon memory as a hierarchical state tree rather than a flat semantic archive. Its four operations are:

- **Grow:** append new observations and actions to the active branch.
- **Compress:** summarize completed subgoals.
- **Maintain:** validate summaries against their underlying traces.
- **Revise:** return to a known-good boundary and continue on a new branch after a faulty assumption or action.

On MemoryArena, the authors report 7.8–20.4 percentage-point improvements over their baselines and 55.1% fewer tokens. These are paper-specific results, not predicted STAR gains.

### 2.3 Proposed STAR memory record

Every durable memory item should have:

| Field | Purpose |
|---|---|
| `memory_id` | Immutable identity |
| `subject`, `predicate`, `object` | Explicit fact or relation |
| `scope` | Project, game, session, person, machine, or global |
| `valid_from`, `valid_until` | Time validity |
| `observed_at` | When STAR learned it |
| `source_ref` | Conversation, file, tool result, benchmark, or external URL |
| `evidence_grade` | Direct observation, trusted tool result, user assertion, inference, or hypothesis |
| `revision_of` | Prior memory superseded or corrected |
| `confidence` | Calibrated confidence, not model fluency |
| `active_branch` | Whether it belongs to the current task state |
| `verification_refs` | Tests or observations that support it |

The schema should be versioned and append-oriented. Corrections create a new record linked to the prior one; they do not silently mutate historical evidence.

### 2.4 State-tree operations for STAR

Place this logic over the existing #1177 task/communication ledger and #1117 governed consolidation work:

1. Append an immutable event for each user change, tool result, task transition, and verified outcome.
2. Maintain a root-to-current path for each long-running task.
3. Compress only completed subgoals, retaining references to source events.
4. Validate summaries by replaying selected facts against source events and current project state.
5. When a premise is invalidated, mark the affected descendant branch stale and resume from the last verified checkpoint.
6. Keep user preferences, project facts, hypotheses, and temporary task state in distinct namespaces.
7. Provide a reversible “what changed and why?” view before any consolidation proposal is accepted.

### 2.5 Required memory tests

Create a STAR-local LongMINT-style suite with synthetic, non-personal project data:

- A value is set, revised, then revised back.
- Two projects use the same property name but different values.
- A task is cancelled while a background worker is using an earlier task generation.
- A model-generated hypothesis is later disproved by a tool result.
- A summary omits a constraint that appears in the underlying event log.
- A query asks for both the current value and the historical value.
- Multiple independent memories must be combined without cross-project contamination.

Pass criteria: current state is correct; historical answers remain reconstructable; stale branches are never treated as active; provenance is available; compaction does not change task outcomes; and token/context cost is measured separately from answer accuracy.

---

## 3. Roblox Creator: official multiplayer test automation

### 3.1 StudioTestService

Roblox documents [StudioTestService](https://create.roblox.com/docs/reference/engine/classes/StudioTestService) as a plugin-security service for automating Test and Run mode. Its API includes:

- `ExecuteMultiplayerTestAsync(numPlayers, args)`
- `AddPlayers(numPlayers)`
- `EndTest(value)`
- `CanLeaveTest()`
- `LeaveTest()`
- `GetTestArgs()`

The official documentation describes a server plus simulated client DataModels and support for up to eight clients in one multiplayer test. The call is yielding and must be run in a coroutine if the plugin UI needs to remain responsive. Only one multiplayer test session can run at a time per Studio instance. Server-side methods and client-side leave methods must be called from their respective DataModels. The documentation also notes a known client-side `GetTestArgs` issue.

### 3.2 Why this is a significant STAR Creator upgrade

The current Studio MCP `start_stop_play` path is useful for a single Play Client session. StudioTestService provides a more deterministic route for multi-client behavior that is otherwise difficult to validate by inspecting scripts alone.

Prioritize test scenarios that commonly fail in real Roblox games:

1. Lobby spawn and late join.
2. Party creation, invite, accept, decline, and timeout.
3. Matchmaking with players joining during queue formation.
4. Server-authoritative inventory and currency updates.
5. RemoteEvent validation and rate limiting.
6. Ownership transfer and item pickup races.
7. Player death, respawn, leave, and reconnect.
8. Client disconnect while the server is committing a transaction.
9. Replication timing and duplicate event delivery.
10. Team balancing and round-state transitions.

### 3.3 Proposed Studio Lab test protocol

**Inspect → Build in isolated test place → Launch deterministic test → Collect server/client evidence → Repair → Re-run → Promote**

A test case should define:

- Stable test ID and place revision.
- Number of simulated clients.
- Seeded scenario arguments.
- Preconditions and expected server state.
- Client-visible assertions.
- Server-authoritative assertions.
- Timeout and cleanup behavior.
- Structured result and evidence references.

Use a plugin coroutine for the yielding test invocation. The server test script owns server assertions and calls `EndTest`; clients own their client-side leave behavior. Avoid using client-reported state as proof of server-authoritative success.

**Important boundaries:** one multiplayer test at a time per Studio instance; do not assume eight clients means eight concurrent test sessions. Run isolated test places and never publish to a public experience as part of automated verification. Keep destructive edits, publishing, or live-place changes behind explicit owner approval.

### 3.4 Cross-engine Creator

GameDevBench remains useful for broader Godot-based multimodal creator evaluation: [official repository](https://github.com/waynchi/gamedevbench). Pair it with Roblox StudioTestService rather than treating one engine's benchmark as proof of Roblox competence.

STAR Creator must evaluate both:
- **Artifact correctness:** scripts, assets, scene structure, UI, animation, and configuration.
- **Runtime correctness:** actual play behavior, replication, frame-time, visual result, and failure recovery.

A successful compile is only one intermediate check.

---

## 4. Local inference: instrument before tuning

### 4.1 llama.cpp server capabilities

The upstream [llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) exposes several useful controls and measurements:

- `cache_prompt` reuses a matching prompt prefix where possible.
- `timings_per_token` reports prompt-processing and generation timing.
- `return_progress` reports prompt progress, including total, cached, processed, and elapsed time.
- `GET /slots` exposes slot state and per-slot activity.
- `GET /metrics` (when enabled) exposes prompt tokens/second, generation tokens/second, requests processing/deferred, busy-slot counts, and speculative-decoding counters.
- Server configuration includes continuous batching, parallel slots, and KV-cache options.

The server documentation warns that prompt-cache reuse can produce non-bit-identical logits across different batch sizes/backends. This does not mean cache reuse is inherently incorrect; it means STAR should compare answer quality and deterministic test behavior as well as speed.

### 4.2 STAR inference experiment

Use the existing #1167 measurement path and #1166 paired evaluator. Do not create a second inference benchmark framework.

Run a fixed workload matrix:

| Workload | Why it matters |
|---|---|
| Short chat, stable system prefix | Typical interactive prefill |
| Long project conversation | Context/prefill pressure |
| Repeated tool schema | Prefix-cache reuse |
| Roblox code generation | Quality-sensitive structured output |
| Voice reply under a strict time budget | First-content latency |
| Background research plus foreground chat | Mixed-load isolation |
| Multiple simultaneous sessions | Slot/cache contention |

Compare one variable at a time:

- Prompt cache on/off.
- Stable versus changing system prefix.
- One versus multiple server slots.
- Continuous batching on/off.
- Context length and retained history.
- CPU-only versus the available GPU offload configuration.
- Speculative decoding off/on only when a compatible draft model is available.

Record:
- Time to first token.
- Prompt-processing tokens/second.
- Decode tokens/second.
- Cached versus processed prompt tokens.
- p50/p95/p99 request latency.
- Queue wait and deferred requests.
- Peak RAM and VRAM.
- Answer correctness, tool correctness, and structured-output validity.

Use the same model build, prompt, task set, and machine state for paired comparisons. Warm up each configuration, repeat runs, report confidence intervals, and keep a sealed holdout. A speed configuration is rejected if it materially degrades correctness, tool selection, or structured output.

### 4.3 8 GB VRAM / CPU-first recommendation

Keep the existing quick path responsive. Do not load a second large model just to speculate. Prefer:
- a compact always-ready model for quick routing, classification, and short responses;
- a stronger model only for tasks that need deeper reasoning;
- retrieval and deterministic tools for exact facts;
- CPU-friendly VAD/ASR where the measured CPU cost is acceptable;
- GPU admission based on actual free VRAM and active model residency;
- background work that yields before live audio, avatar, or game-control deadlines.

No model replacement or inference default change is justified by paper benchmarks alone.

---

## 5. Streaming ASR: compare complete providers, not isolated WER claims

Two practical local candidates deserve paired evaluation:

### Moonshine Voice

[Moonshine Voice](https://github.com/moonshine-ai/moonshine-v2) offers a streaming-oriented API with transcript update events and a Python microphone transcriber. Its API also includes semantic intent-recognition concepts. Evaluate it for early partials and command-like utterances.

### sherpa-onnx

[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) supports offline local speech processing, streaming and non-streaming ASR, TTS, VAD, speaker diarization/identification, and Windows builds. Its model catalog includes small streaming transducer options, including an English Zipformer model listed at 20M parameters.

### Proposed provider contract

Each provider emits typed, revisioned events:

`TranscriptEvent(session_epoch, sequence, revision, start_ms, end_ms, text, is_final, speaker_id, confidence, provider)`

Rules:

- Partial transcripts may drive read-only preparation and UI captions.
- Only finalized, current-epoch transcript events may create authoritative conversation turns.
- Only trusted, final classifications may trigger room-control actions such as resolving another speaker's question.
- A new revision invalidates dependent speculative work unless it remains valid for the unchanged semantic prefix.
- Speaker IDs are session-scoped pseudonyms, not durable identities.
- Raw audio retention remains off by default.

### Paired ASR evaluation

Compare Moonshine, sherpa-onnx, and existing Faster-Whisper on the same consented recordings:

- Word error rate and entity/name accuracy.
- Time to first useful partial.
- Time to stable/final transcript.
- Revision count and late corrections.
- Speaker diarization error where enabled.
- CPU utilization, peak RAM, and real-time factor.
- False end-of-turn and false barge-in effects.
- Total conversation task success.

Use a two-pass design only if it improves end-to-end quality: a fast streaming provider for partials and a higher-accuracy finalizer for committed text. The finalizer must not delay ordinary turn-taking beyond the measured target.

No provider becomes the default until it wins on the actual Windows/CPU/GPU configuration and the full voice pipeline, not merely a model-card benchmark.

---

## 6. Natural VTuber presence and more capable streaming

The previous research already defines a shared event timeline, a Social Director, and an Avatar Director. Run 27 turns these into acceptance requirements.

### Social behavior

- Answer direct questions, not every sentence heard.
- Distinguish a viewer addressing STAR from viewers talking to one another.
- Track whether a question was answered by someone else.
- Use brief backchannels when appropriate; do not interrupt every pause.
- Allow silence, listening, and focused gameplay.
- Vary phrasing without inventing personal memories or offline experiences.
- Preserve a consistent AI-character identity and disclose that she is an AI.

### Audiovisual behavior

- Mouth movement follows PCM actually emitted by the speaker.
- Expression transitions are smoothed and have explicit priority.
- A blink cannot be cancelled by an ordinary gaze update.
- Gestures are event-triggered and rate-limited.
- Interrupted speech cancels stale mouth frames and stale expressions.
- OBS health is measured independently from model latency.

### Stream features to prioritize

1. Live captions with correction-aware partials.
2. Contextual game-event commentary with a mute/quiet mode.
3. Viewer question tracking and answer deduplication.
4. Opt-in highlight candidate detection; no automatic publishing.
5. Co-op game planner and strategy coach.
6. Audience polls and simple interactive game events.
7. Stream session summaries with explicit evidence links.
8. Creator mode that can switch from gameplay to Roblox Studio development without losing the stream conversation.
9. Multilingual captioning/translation as an opt-in capability.
10. A stream-health panel showing audio, inference, avatar, OBS, and game performance separately.

InteractionBench demonstrates why timing, spoken-task accuracy, acoustic behavior, and long-conversation grounding must remain separate score dimensions: [paper](https://arxiv.org/abs/2611.02430) · [benchmark](https://www.fullduplex.ai/benchmarks/interactionbench). Full-Duplex-Bench v3 adds natural disfluencies and chained tool tasks: [benchmark](https://www.fullduplex.ai/benchmarks/fdb-v3).

---

## 7. Capability acceptance gates

STAR should report verified capability rather than a single vague intelligence score.

| System | Required measurements | Promotion gate |
|---|---|---|
| Audio runtime | callback p95/p99, input drops, output underflows, queue age | No regression under mixed load |
| Voice interaction | first useful partial, first audible output, interruption precision/recall | Paired task and turn-taking score maintained |
| ASR | WER, entity accuracy, partial/final delay, CPU/RAM | Better end-to-end tradeoff on target machine |
| Inference | prefill, decode, cache, queue, p95 latency, RAM/VRAM | Faster without quality loss |
| Memory | revision recall, stale-branch rejection, provenance, token cost | No cross-project contamination |
| Roblox Creator | static checks plus server/client assertions | Repeated deterministic multiplayer pass |
| Gamer Brain | cold-start score, learning curve, held-out transfer | Transfer beyond practiced map |
| VTuber | audio/avatar sync, long-session grounding, OBS stats | Stable multi-hour rehearsal |
| General knowledge | factuality, source quality, freshness, contradiction handling | Claims trace to evidence and uncertainty |
| Autonomy | task completion, cancellation, rollback, permission compliance | No stale task or unauthorized side effect |

Use p50, p95, p99, sample count, hardware, model hash, software version, and test-set version. Averages alone hide the tail failures that viewers notice.

---

## 8. Security, privacy, and operational boundaries

- No raw microphone or viewer audio is stored by default.
- Speaker attribution is session-scoped and must not become identity recognition.
- Captions and transcripts need clear retention controls.
- OBS WebSocket must use authentication and remain local/private unless explicitly configured.
- VTube Studio permissions should be requested only for the features enabled.
- Gameplay input, public chat, account actions, publishing, spending, and external messages remain separately permissioned.
- Test places must be isolated from public production experiences.
- A model-generated plan is not authorization to execute it.
- Cancellation and task-generation checks must be enforced by host code.
- Skill promotion requires independent evidence and held-out tests; self-reported success is insufficient.

---

## 9. Implementation order

1. **Reconcile #1151 and #1178 audio changes.** Carry the bounded meter worker and playback clock into the persona/room branch without duplicating telemetry or changing unrelated room semantics.
2. **Run exact-head CI** after reconciliation; then perform Windows device profiling for callback timing and underflows.
3. **Extend #1108/Studio Lab** with a StudioTestService plugin harness for deterministic 1–8-client tests, respecting the one-session-per-Studio limit.
4. **Build LongMINT-style memory interference tests** over #1177/#1117 before adding new memory features.
5. **Instrument the existing llama.cpp path** through #1167; pair every cache/batching/offload change with #1166 quality evaluation.
6. **Add ASR provider prototypes** behind opt-in settings and benchmark Moonshine, sherpa-onnx, and Faster-Whisper.
7. **Run mixed-load VTuber rehearsals** with speech, chat, gameplay, avatar, OBS, and background research active simultaneously.
8. **Promote only verified capabilities** into a release candidate after hardware, privacy, and rollback checks.

### Explicit non-goals for this run

- No model weights or datasets downloaded.
- No ASR/TTS dependency installed.
- No microphone, OBS, VTube Studio, or game-input permission enabled.
- No model routing, context size, batching, cache, or resource defaults changed.
- No Roblox public experience edited or published.
- No PR merged and no production release changed.

---

## Sources

1. LongMINT — [arXiv:2605.18565](https://arxiv.org/abs/2605.18565)
2. MAGE — [arXiv:2606.06090](https://arxiv.org/abs/2606.06090)
3. Roblox StudioTestService — [official Creator Hub API](https://create.roblox.com/docs/reference/engine/classes/StudioTestService)
4. llama.cpp server — [official server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
5. Moonshine Voice — [official repository](https://github.com/moonshine-ai/moonshine-v2)
6. sherpa-onnx — [official repository](https://github.com/k2-fsa/sherpa-onnx)
7. InteractionBench — [paper](https://arxiv.org/abs/2611.02430) and [benchmark](https://www.fullduplex.ai/benchmarks/interactionbench)
8. Full-Duplex-Bench v3 — [benchmark](https://www.fullduplex.ai/benchmarks/fdb-v3)
9. GameDevBench — [official repository](https://github.com/waynchi/gamedevbench)
10. PortAudio — [callback guidance](https://github.com/PortAudio/portaudio/wiki/Tips_Callbacks)
11. python-sounddevice — [callback documentation](https://python-sounddevice.readthedocs.io/en/latest/)
12. Microsoft — [IAudioClient3 shared-mode period API](https://learn.microsoft.com/en-us/windows/win32/api/audioclient/nf-audioclient-iaudioclient3-getsharedmodeengineperiod)

---

**Run 27 conclusion:** the next real quality jump for STAR is a combination of correct long-term state, reproducible multiplayer game tests, instrumented inference, and a measured low-latency audio path. These improvements make her more capable because she can preserve the right knowledge, test what she builds, understand live speech sooner, and remain responsive while several systems operate together.
