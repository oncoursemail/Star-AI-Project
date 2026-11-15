# STAR Run 22 — Low-Latency Audio Freshness, Intent-Aware Duplex Control & Inspect-First Game Agents

**Research date:** 2026-11-14  
**Target branch:** feat/resource-admission-20261113-run21  
**Repository head audited:** 5fbc58035d7467802c3328bbc9b6683a851717c1  
**Scope:** real-time audio reliability, conversational floor control, local inference performance, Roblox/game-agent evaluation, VTuber orchestration, and transferable general skills.

## Executive decision

The next useful improvement is not another model download or a second scheduler. It is to remove avoidable latency in STAR's live input path, make conversational decisions more evidence-aware, and make game agents inspect and verify their environments before changing them.

This run makes one small runtime correction and one static-analysis correction:

1. The microphone queue now holds at most 16 frames (about 512 ms) and drops the oldest frame when full, preserving fresh speech instead of preserving stale backlog.
2. Voice bridge attributes are explicitly typed, removing four new Pyright attribute-access errors found on the previous exact-head run.

The new research adds an inspect-first Roblox workflow and a more precise full-duplex voice state model. No new model, provider, scheduler, credential, or external integration is enabled.

## 1. Verified repository baseline

At the start of this run:

- PR #1178 was open and draft, targeting the existing task-communication-ledger development branch.
- Its head was 5fbc58035d7467802c3328bbc9b6683a851717c1; it was not merged into production main.
- The draft stack already describes a single resource-admission authority in PRs #1140/#1142. Those are also draft dependencies, not production-main capabilities.
- The voice runtime uses 32 ms microphone frames, Silero VAD, Smart Turn endpointing, one-shot faster-whisper transcription, streaming model text, sentence chunking, and Kokoro TTS.
- The room host owns trusted ingress and the room director owns response/stop decisions.
- OBS and VTube Studio APIs are researched but no provider transport is installed or enabled by this change.

### Exact-head CI audit

The previous head's offline workflow had successful Python compilation, Ruff, research-catalog validation, and offline regression tests, but the overall workflow failed its Pyright baseline gate. The four reported errors were in star/voice/bridge.py:

- inferred-None assignments for the active call's speaker, microphone, and session;
- calling synthesize on a value inferred as object.

The previous Windows desktop workflow completed successfully, including its configured Windows offline test shards. This is CI evidence only; it is not a physical microphone, GPU, OBS, VTube Studio, or livestream test.

## 2. Critical live-audio finding: stale queue backlog

### Previous behavior

The microphone adapter used a queue capacity of 300 frames. At 32 ms per frame, that permits approximately 9.6 seconds of queued audio.

When the queue filled, put_nowait rejected the newest frame. The consumer therefore kept the oldest audio and discarded current speech. If the consumer fell behind, STAR could process stale audio long after the speaker had moved on.

That is the wrong overload policy for a live conversational assistant. It can preserve data while destroying conversational timing.

### New behavior

The queue is now bounded to 16 frames:

- frame duration: 32 ms;
- maximum queued audio: 512 ms;
- overload policy: discard the oldest queued frame, then enqueue the newest frame;
- diagnostics: cumulative queue drops, current depth, capacity in frames, and capacity in seconds.

The queue remains non-blocking in the PortAudio callback. The callback does not wait for the consumer. No audio samples or device names are exposed through diagnostics.

### Trade-off

This is a freshness policy, not a lossless recorder. A queue drop creates a gap in the audio timeline. The counter makes overload visible; the application must not treat a stream with drops as archival-quality audio. If reliable recording is needed, it must use a separate recorder with its own storage and consent policy.

A 512 ms queue is a conservative initial bound, not a universal optimum. Physical-device tests must compare 8, 16, and 24 frames under CPU/GPU contention before changing the constant again.

## 3. Full-duplex speech research: keep the decisions separate

### Voice-Light

Voice-Light is a useful end-to-end systems study because it combines streaming ASR, a causal turn-taking adapter, reversible playback, private speculative generation, typed tool orchestration, and browser playback acknowledgements.

Its most important engineering lesson is not the headline latency. Its locked evaluation found that the learned completion checkpoint had only 12.53% end-of-turn recall at the selected low-false-cutoff threshold, while the deployed system retained a hybrid Silero timing policy. The paper also reports a 758 ms median from final VAD endpoint to first server audio across 36 operator-run turns; those sessions are an instrumented case study, not a controlled population evaluation.

**STAR decision:** reuse the architecture ideas, not the weights or thresholds. Keep the existing host-side room director authoritative. Do not replace Smart Turn or Silero until a locked, conversation-disjoint test shows a better false-cutoff/latency trade-off.

### FD-VAD

FD-VAD studies causal semantic endpointing from bounded audio windows without requiring a transcript. It uses confidence-gated endpoint commitment because early stopping and extra delay have different costs.

**STAR decision:** treat it as a candidate for a separate endpointing experiment. Compare it with current Smart Turn and silence-only baselines on the same recorded, consented, held-out audio. Report false cutoffs, missed endpoints, endpoint delay, CPU/GPU cost, and calibration.

### HiThink Turn

HiThink Turn makes a useful distinction: a complete utterance does not always require a response, and an unfinished utterance can already reveal enough intent to justify a floor change. It conditions the decision on whether STAR is currently speaking.

**STAR decision:** do not collapse response intent, semantic completion, speaker attribution, and floor ownership into one classifier. Use a typed state machine:

1. Acoustic onset: is new speech present?
2. Semantic completion: is the current speaker likely finished?
3. Response intent: is the speech directed to STAR and does it request a response?
4. Playback state: should STAR continue, duck, stop, or resume?
5. Trusted host decision: is the source permitted and is this exact event still current?

Each stage must expose confidence and evidence. A low-confidence classifier may defer to the current conservative policy; it must not invent authority to speak.

## 4. Speculative generation and audible-history correctness

Voice-Light demonstrates a strong invariant: work may be prepared speculatively, but it must not become audible or durable until causal checks pass.

For STAR, a future implementation should associate every response with:

- conversation/session ID;
- triggering event ID;
- response generation ID;
- transcript revision and finality;
- audio chunk sequence number;
- playback acknowledgement range;
- cancellation/supersession state.

Rules:

- Provisional ASR text never triggers tools or durable memory.
- Speculative text/audio remains private until the room director authorizes the response.
- A canceled generation cannot append later chunks to history.
- Only audio acknowledged as played by the client may be treated as heard.
- If client playback acknowledgements are unavailable, server queue submission must not be mislabeled as audience-heard audio.
- Tool execution remains behind existing permission and source validation.

The existing metric first_audio_at means audio was handed to a local speaker queue. It is not proof that a remote viewer heard it. Keep that distinction in dashboards.

## 5. Roblox game creation: OpenGameEval and inspect-first behavior

OpenGameEval is a particularly relevant new benchmark because it runs agents inside reproducible, stateful Roblox Studio sessions. It separates observation tools from editing tools and scores both the edited scene and a simulated play session.

The published study describes 84 human-curated core tasks, 13 evaluated models, and 16 attempts per task. The best reported model solved 51.7% on one attempt and 39.4% across five-of-five consistency. Its exploration analysis found that inspecting every object touched by a reference solution was associated with 13.4 percentage points higher pass rate on scene-only tasks and 9.8 points on script-only tasks than inspecting none.

**STAR decision:** implement an inspect-first planner, not blind prompt-to-edit generation.

Recommended loop:

1. Read the task and convert it into explicit acceptance checks.
2. Inspect the current DataModel, relevant scripts, properties, and dependencies.
3. Record the exact objects and versions observed.
4. Plan a minimal edit.
5. Apply edits only to the intended targets.
6. Run static checks and Studio playtests.
7. Inspect output logs, changed objects, and screenshots.
8. Verify the original acceptance checks.
9. Roll back or repair if a check fails.
10. Save a reproducible task trace and a verified skill candidate.

Keep observation and mutation tools distinct. Exploration should be measured rather than hidden inside a large opaque tool call.

### Multi-Studio routing

Roblox's 2026 Studio MCP multi-agent update makes Studio targeting explicit through a studio_id on tool calls. STAR should not rely on a mutable global active-Studio selection when multiple Studio instances are open.

Every future Studio request should carry a validated target studio_id, and the adapter should reject missing or stale IDs. Each session should own its own task state, logs, and cancellation token.

OpenGameEval requires credentials for its remote evaluation API. STAR should not store those credentials in the repository or silently invoke remote evaluation. Local Studio playtests and owner-authorized remote evaluation must remain separate modes.

## 6. Gamer Brain: fast control, slow planning

Do not call a large language model for every frame or every button press.

Use two coordinated layers:

- Fast controller: game-native input cadence, immediate movement, camera correction, cooldowns, and safety constraints.
- Strategic planner: objectives, route selection, resource planning, tactics, and recovery after meaningful events.

Trigger expensive reasoning on events such as death, objective completion, an unexpected enemy, repeated failure, a new area, or a major resource change.

Every planned action should include:
- target game/session ID;
- observation timestamp or state hash;
- preconditions;
- expected effect;
- expiry;
- abort condition.

If the observed state no longer matches the plan's preconditions, discard the stale action and observe again.

Learning must use sandboxed environments, deterministic replay where possible, held-out maps or scenarios, and a versioned skill library. Measure win/objective rate, completion time, deaths, resource efficiency, action latency, and transfer to unfamiliar variants.

## 7. Local inference speed: benchmark the backend, not the headline

The upstream llama.cpp feature matrix shows that kernel and Flash Attention support varies by backend and quantization type. A format being accepted by a command line does not prove that the intended GPU kernel is actually selected or that it is faster.

NVIDIA TensorRT-LLM documents KV-cache quantization, sparse attention, and storage-tier compression, while SGLang describes session-aware prefix reuse for hybrid attention state. These are useful design references, but they are not drop-in llama.cpp settings and their large-server results do not predict performance on STAR's single 8 GB GPU.

**STAR decision:** keep the existing inference engine and settings until a paired local benchmark proves an improvement.

Benchmark each candidate with the same:
- model checkpoint and weight quantization;
- prompt and context length;
- output length;
- batch and concurrent request count;
- CPU thread count and GPU layer count;
- KV-cache types and attention configuration;
- warm/cold cache state;
- foreground/background workload mix.

Measure:
- time to first token;
- inter-token latency and decode tokens/second;
- prompt-processing throughput;
- p50/p95/p99 response latency;
- GPU/CPU/RAM usage and thermal throttling;
- cache hit/miss and eviction behavior where exposed;
- answer quality and task success.

For an 8 GB GPU, reserve headroom for the desktop, OBS, Studio, model runtime, and KV cache. Do not select a model solely because its weight file fits. Do not increase parallel slots until per-slot KV capacity and tail latency have been measured.

Stable system prefixes, compact task-specific context, retrieval of only relevant evidence, and a small-model fast path are lower-risk optimizations than installing a much larger model. Keep changing timestamps, viewer messages, and task state out of the reusable system prefix.

## 8. VTuber and stream presence

The existing research catalog already includes the OBS WebSocket and VTube Studio APIs. The next integration should be event-driven and local-first:

- VTube Studio events for model/tracking/hotkey changes rather than constant polling where possible.
- OBS statistics for render and output health.
- A single monotonic event timeline joining microphone, transcript, chat, game events, model output, TTS chunks, and avatar actions.
- Generation IDs so an old expression or speech chunk cannot overwrite a newer reaction.
- Client playback acknowledgement so the avatar mouth follows audio actually played, not just generated text.
- Graceful reconnect and visible degraded-state reporting.

Natural presence comes from relevance, timing, varied but restrained reactions, attention to viewer-to-viewer conversation, and comfortable silence. It must not be manufactured through fake memories, fabricated perception, or claims that STAR is human. STAR remains transparently an AI character.

## 9. General knowledge and transferable skills

Use two distinct memory products:

### Evidence-backed knowledge cards
- atomic claim;
- source and retrieval date;
- validity date or supersession;
- confidence and uncertainty;
- contradictory evidence;
- concise explanation;
- links to related concepts.

### Executable skill records
- goal and preconditions;
- procedure;
- tools required;
- expected outputs;
- positive and negative tests;
- known failure modes;
- version and provenance;
- held-out transfer results;
- rollback pointer.

A memory is useful only if it improves a future decision or action. Evaluate retrieval by task success and evidence correctness, not by how many facts can be recalled in isolation.

## 10. Implementation and acceptance gates

### Implemented in this run
- Microphone queue reduced from 300 frames (~9.6 s) to 16 frames (~512 ms).
- Queue overload now drops the oldest frame and preserves newest input.
- Aggregate diagnostics expose queue capacity and current depth.
- Device tests verify newest-frame retention, ordering, drop counts, and absence of audio/transcript/device-name leakage.
- Voice bridge active-device/session attributes and TTS return type are explicitly typed to address the exact-head Pyright failure.
- Voice-call documentation now describes the freshness and non-archival semantics.
- Eleven primary references added to the research catalog.

### Required CI acceptance
- Pyright baseline gate: no new errors; preferably reduce the existing bridge.py errors.
- Ruff and Python compilation pass.
- All offline voice and repository regression tests pass.
- Windows desktop build and both offline test shards pass.
- Research catalog JSON and duplicate-ID validation pass.

### Required physical acceptance before enabling more aggressive voice behavior
- Real microphone and headphones on the target Windows PC.
- 30-minute conversation under CPU/GPU contention.
- Injected consumer stalls to verify queue stays bounded and recovers to fresh audio.
- Measure queue drops, endpoint delay, false cutoffs, playback underruns, and user-heard first-audio latency.
- OBS and VTube Studio tests with explicit owner authorization.
- Separate gameplay and Studio tests; no remote game input without a dedicated permission gate.

## 11. Priority roadmap

1. Complete exact-head CI and fix any regressions.
2. Run physical microphone queue/freshness tests on the target Windows machine.
3. Add playback acknowledgements and generation-safe cancellation.
4. Benchmark current Smart Turn against FD-VAD/HiThink-style candidates on a locked holdout.
5. Add per-Studio explicit routing and inspect-first Roblox planning.
6. Add OpenGameEval-compatible local task manifests and executable scene/play checks.
7. Add event-triggered Gamer Brain with replay and held-out transfer.
8. Add one shared OBS/VTube Studio event timeline.
9. Add evidence-backed knowledge cards and executable skill records.
10. Run mixed-load benchmarks before changing model or resource defaults.

## 12. Explicit limits

- This run does not install ASR, diarization, endpointing, or foundation model weights.
- No model/provider routing, inference defaults, GPU/RAM budgets, permissions, OAuth credentials, or installer behavior change.
- No OBS/VTube Studio transport or Roblox Studio MCP client is enabled.
- No real microphone, RTX 4060, game-control, or livestream hardware test is claimed.
- Research-paper and vendor benchmark numbers are not treated as STAR measurements.
- The microphone freshness queue is not suitable for archival recording.
- Production main remains unchanged; PR #1178 remains draft pending exact-head CI and owner review.
