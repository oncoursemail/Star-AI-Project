# STAR Run 29 — Observability, Audio Integration, and Capability Gates

**Research date:** 2026-11-14  
**Repository:** `oncoursemail/Star-AI-Project`  
**Branch:** `research/star-run24-integration-blueprint-20261114`  
**Scope:** measured runtime performance, audio callback integration, GenAI observability, streaming ASR, local inference, Roblox automation, Gamer Brain, Creator Brain, VTuber social presence, and evidence-based capability promotion.

---

## Executive decision

STAR has enough parallel research and prototype branches that another independent scheduler, event bus, audio meter, memory store, or benchmark would increase integration risk. The next improvement should be a **single measurement and integration layer** that tells the team which subsystem is actually limiting a live session, then promotes only changes that improve the whole experience.

Run 29 makes five decisions:

1. **Reconcile duplicate audio implementations before adding more audio code.** PR #1151 and PR #1181 both contain bounded asynchronous speaker metering. They are not interchangeable: #1151 also contains playback-clock telemetry; #1181 adds a much fresher microphone queue and more device diagnostics.
2. **Use one end-to-end trace for a stream turn.** Correlate microphone frame, ASR partial/final, room decision, model request, tool calls, TTS chunks, actual output callback, avatar frame, and OBS/game health.
3. **Measure quality and latency together.** A faster model or recognizer is not an improvement if it creates more transcription revisions, false interruptions, wrong answers, game failures, or avatar desynchronization.
4. **Prefer CPU speech recognition when it protects the 8 GB GPU budget.** Add Nemotron Streaming through sherpa-onnx to the ASR comparison; do not select a provider from paper numbers alone.
5. **Use Roblox Studio's built-in MCP and StudioTestService as the Creator Brain's practical test surface.** Script generation must lead to visual and multiplayer verification, not stop at successful code output.

No model, dependency, credential, device permission, model route, or production default is changed by this document.

---

## 1. Repository reality check — an important duplicate-work finding

This audit inspected the actual source files on the open draft branches, not just their PR descriptions.

| PR / branch | Inspected state | What it contributes | Integration decision |
|---|---|---|---|
| #1151 — `feat/voice-playback-clock-and-validation-fix-20261112` | Source inspected | Bounded speaker RMS worker plus DAC-time playback telemetry and expanded turn-latency breakdown | Preserve its playback-clock work |
| #1178 — natural streamer persona | Parent of #1181 | Room stop semantics, resolved-reply handling, natural persona | Preserve its room and persona behavior |
| #1181 — `fix/voice-meter-off-callback-20261114` | Exact commit `bcc6fa36f7336028487a18af42eed6456cdc93af` inspected | Bounded speaker meter worker; 16-frame microphone queue that evicts stale input; input/output device counters | Preserve the microphone freshness policy and reconcile speaker code rather than merging a second meter |
| #1180 — research blueprint | Research branch inspected | Runs 24–27 architecture and capability research | Add this integration/measurement handoff here |

### Speaker-path overlap

Both #1151 and #1181 now move PCM16 RMS calculation away from the high-priority output callback using a bounded 64-block deque, sequence numbers, a worker thread, and conservative handling of pending/dropped meter data.

The implementations should not both be merged as independent versions of the same speaker path.

### The meaningful microphone difference

The inspected #1151 branch uses a 300-frame microphone queue, approximately ten seconds at the documented 32 ms frame size, and drops the newest frame when full. That preserves stale backlog and can make a live conversation react to audio that is already several seconds old.

The inspected #1181 branch uses 16 frames, approximately 512 ms, and evicts the oldest queued frame when full so the recognizer receives fresher speech. It also records driver overflow/underflow and queue-drop diagnostics.

**Recommended reconciliation:** retain #1151's DAC-time playback snapshot and latency stages; retain #1181's 16-frame freshness-first microphone policy and device diagnostics; keep exactly one speaker meter worker and one playback telemetry authority. Reconcile parent dependencies before cherry-picking or retargeting. Do not merge the PRs blindly.

### Exact-head CI evidence

For #1181 commit `bcc6fa36f7336028487a18af42eed6456cdc93af`, GitHub Actions returned successful offline-check and desktop workflow runs:

- Offline checks run #6136 — success.
- Desktop workflow run #3225 — success.

These are repository CI results for that code head, not a physical Windows audio-device test or a proof of lower acoustic latency.

---

## 2. Audio callback audit — what is improved and what is still not real-time safe

### What the current speaker-worker design gets right

- RMS arithmetic and Python-level sample iteration run outside the PortAudio output callback.
- The telemetry queue is bounded.
- Meter overload can discard old telemetry without changing the PCM already copied to the output buffer.
- Sequence gaps reveal dropped meter blocks.
- Pending, dropped, or failed meter data is treated as conservatively audible so an echo gate does not mistake unknown output for silence.
- The speaker worker is stopped after the device stream is stopped.

This is a useful soft-real-time improvement. It is not a hard real-time guarantee.

### Remaining callback risks visible in the inspected implementation

**Input callback**
- The microphone callback takes a statistics lock.
- It uses `queue.Queue.put_nowait`, whose implementation still acquires an internal mutex.
- It copies the callback buffer to a Python bytes object.
- On queue overflow it performs an additional queue operation and counter update.

**Output callback**
- It takes the same lock used by playback producers.
- It creates a bytes copy from the playback bytearray and deletes a slice.
- It fills underrun silence in Python.
- It calls the monotonic clock and appends telemetry.
- Python allocation, lock contention, the GIL, and a large concurrent playback-buffer append can still contribute to jitter.

PortAudio's callback guidance recommends keeping high-priority callbacks to bounded data movement/math and avoiding locks that can be held by lower-priority threads, allocation, and unpredictable work. The current implementation is therefore a meaningful reduction in callback work, not the final native low-latency architecture.

### Staged audio optimization

1. **Instrument first:** record callback execution p50/p95/p99/max, callback deadline, input queue age, input drops, output underflows, and worker lag. Store aggregate numbers only.
2. **Profile contention:** separately measure time waiting for the playback-buffer lock and time spent copying/filling PCM.
3. **Keep freshness explicit:** preserve the short input queue for live conversation; archival recording, if ever needed, must use a separate lossless path.
4. **Only if traces justify it:** prototype a native single-producer/single-consumer ring buffer for PCM handoff. Compare it with the current Python path on Windows CPython, including shutdown, device changes, cancellation, and underrun behavior.
5. **Windows-specific follow-up:** evaluate WASAPI shared-mode periods through IAudioClient3 and event-driven capture/playback. Query supported periods first; do not force the minimum period on every device. Microsoft documents that the engine period is device/format dependent and that requested periods must respect the returned fundamental/minimum/maximum constraints.
6. **Playback truth:** keep three separate timestamps: TTS queue submission, PortAudio's estimated DAC output time, and physical acoustic arrival. The first two do not prove when a listener hears sound; validate the third with a loopback/reference measurement.

Do not add MMCSS, custom WASAPI, or a native extension until real device traces show that the current PortAudio callback is the bottleneck.

---

## 3. One causal observability layer for all of STAR

The most important infrastructure gap is not another dashboard. It is the inability to answer, from one correlated trace, why a particular stream turn was slow or wrong.

### Proposed trace for one user/viewer turn

`stream.session`
→ `audio.capture`
→ `asr.partial` / `asr.final`
→ `turn.detect`
→ `room.director`
→ `agent.invoke`
→ `model.inference`
→ zero or more `tool.execute` / `memory.retrieve`
→ `tts.first_chunk` / `tts.chunk`
→ `speaker.submit`
→ `speaker.dac_estimate`
→ `avatar.apply`
→ `obs.sample` and `game.sample`

Every span should carry a trace ID, parent/span relationship, session epoch, bounded event ID, task generation where applicable, and monotonic timing. A model-generated transcript or game observation may be linked as evidence, but it must not gain tool authority from being present in a trace.

### Adopt OpenTelemetry GenAI conventions carefully

The OpenTelemetry GenAI semantic-conventions project now has a dedicated repository. Its metrics and span conventions are still marked Development, so STAR should pin a reviewed specification revision and record the schema version instead of assuming the names are permanently stable.

Useful existing convention names include:

| Signal | Why STAR needs it |
|---|---|
| `gen_ai.client.inference.time_to_first_chunk` | Time from inference request to first streamed response chunk |
| `gen_ai.client.inference.duration` | Full client-side model operation duration |
| `gen_ai.server.time_to_first_token` | Server-side first-token latency |
| `gen_ai.server.time_per_output_token` | Decode cost after the first token |
| `gen_ai.invoke_agent.duration` | End-to-end agent invocation duration |
| `gen_ai.invoke_agent.inference_calls` | Model-call count for one agent invocation |
| `gen_ai.invoke_agent.tool_calls` | Client-side tool-call count for one agent invocation |
| `gen_ai.execute_tool.duration` | Tool execution duration |
| `gen_ai.retrieval.duration` | Retrieval pipeline duration |
| `gen_ai.client.inference.usage.input_tokens` | Input-token usage when available |

These metrics complement STAR's existing voice-turn timing and PR #1167 inference work; they should not replace either.

### STAR-specific measurements to add to the existing evaluators

- ASR: first useful partial, stable/final transcript, revision count, word error rate, named-entity accuracy.
- Conversation: speech-end-to-first-response, false barge-in rate, missed interruption rate, answered-by-human suppression, unresolved question age.
- Audio: callback p95/p99/max, input queue age, dropped frames, output underruns, meter lag.
- TTS: first chunk, chunk gap p95, synthesis real-time factor, cancellation-to-silence.
- Avatar: audio-to-mouth offset, stale frame age, dropped/coalesced frame count, expression transition delay.
- OBS: skipped frames, render lag, output drops, stream reconnects.
- Game: FPS p10, frame-time p95, input-to-action delay, objective success, deaths/retries, held-out map transfer.
- Inference: queue wait, prefill time, TTFT, inter-token time, tokens/sec, cache hit/reuse, active slots, RAM, VRAM, CPU/GPU utilization.
- Agent: total workflow time, inference/tool calls, retries, verified completion, rollback count, stale-result rejection.

Report p50/p95/p99/max and sample count. Keep the test set, model hash, software version, hardware profile, warm/cold state, and concurrency level with each benchmark result.

### Privacy-preserving defaults

OpenTelemetry's GenAI documentation warns that prompt variables, system instructions, messages, and tool definitions may contain sensitive information. STAR should therefore:

- Export aggregate metrics by default.
- Keep prompt, transcript, raw audio, viewer message, and tool payload recording disabled by default.
- Use random bounded correlation IDs in traces, not viewer names or durable speaker identities.
- Redact credentials and local paths before export.
- Make detailed trace capture explicit, short-lived, local-first, and user-controlled.
- Keep metrics labels low-cardinality; place per-session correlation in traces rather than metric labels.

A useful performance trace must explain the system without becoming a transcript archive.

---

## 4. Faster local inference — optimize the actual bottleneck

STAR should not use one headline tokens-per-second number as its performance target.

Separate:
- queue wait;
- prompt prefill;
- first token;
- decode time per output token;
- streaming chunk interval;
- TTS generation;
- speaker queue delay;
- actual playback estimate.

### Request-aware inference modes

A small, deterministic controller can choose among already-installed, already-approved modes based on task class and resource state:

| Workload | Preferred path |
|---|---|
| Short social acknowledgement | Fast, low-latency model |
| Live stream question | Fast model with strict response budget |
| Complex Roblox architecture | Stronger reasoning model with bounded tool plan |
| Code repair | Specialist coder plus static tests and runtime verifier |
| Background research | Lower-priority model/search workers |
| Game control | Small perception/action policy; strategic model only at meaningful events |
| Creator visual review | Vision model on selected screenshots, not every frame |

Do not load multiple large models simultaneously on the 8 GB GPU. Prefer sequential model residency or CPU execution for supporting workloads when benchmarks show that it protects the foreground latency budget.

### Speculative decoding

llama.cpp supports draft-model and n-gram speculative decoding. It can improve decode throughput when draft proposals are accepted often enough to offset draft overhead. Benchmark it against the same prompts and output-quality tests. Record acceptance rate, tokens/sec, first-token latency, CPU/GPU use, and memory. Disable it automatically when it loses on the target machine.

### KV-cache compression watchlist

Google Research's TurboQuant is promising for memory-bound long-context inference. Google reports large KV-memory reductions and attention-logit speed improvements on its evaluated high-end hardware. Those figures are not an end-to-end speed guarantee for STAR's RTX 4060 8 GB system.

A separate multimodal direction, OmniKVQuant, explores 2-bit caches for audio/video/text-capable models with modality-specific treatment and fused Triton kernels. Treat both as research-only until the exact serving backend, GPU kernel, model architecture, and quality tests are supported. Do not patch a custom KV-cache implementation into llama.cpp from a paper alone.

### Mixed-load benchmark matrix

Run the same fixed task suite in these conditions:

1. Idle model server.
2. Voice only.
3. Voice plus viewer chat.
4. Voice plus gameplay.
5. Voice plus OBS/avatar.
6. All foreground workloads plus one background research job.
7. All foreground workloads plus the maximum admitted background load.

For each condition, compare baseline and candidate with the same model hash, quantization, context, prompt, temperature, test data, and hardware power profile. Report quality and latency together. Repeat warm and cold runs; include p95/p99 so occasional stream-breaking stalls are visible.

---

## 5. New ASR candidate: Nemotron Streaming through sherpa-onnx

Previous STAR research already identified Moonshine and sherpa-onnx as candidates. Run 29 adds a more specific option: the Nemotron Speech Streaming model family documented by sherpa-onnx.

The official sherpa-onnx model page lists streaming chunk variants at 80 ms, 160 ms, 560 ms, and 1120 ms. Larger chunks may improve accuracy while increasing algorithmic delay.

The April 2026 on-device ASR study evaluated more than 50 configurations. It reports a Nemotron 0.6B streaming configuration with 7.28% average WER and 0.56 s algorithmic delay before its later quantized ONNX optimization. Its optimized int4 pipeline reports a model size as low as 0.67 GB and 8.20% average WER across eight benchmarks. These are paper results on the authors' datasets and implementation, not STAR's microphone results.

### Recommended paired test

Compare:
- current Faster-Whisper;
- Moonshine Tiny and Small streaming;
- sherpa-onnx Zipformer/transducer;
- sherpa-onnx Nemotron Streaming at 80/160/560/1120 ms where supported.

Measure WER, proper-name/entity accuracy, first useful partial, finalization delay, transcript revisions, false endpoint rate, CPU, peak RAM, and performance while the local LLM and game are active.

Use partial transcripts for captions and read-only preparation only. Only the final, current-epoch transcript may become an authoritative conversation turn. Do not let a partial transcript trigger a tool action, public message, or room-control decision.

---

## 6. Roblox Creator Brain — use the tools Roblox already ships

The official Roblox Studio MCP server is built into Studio and communicates with an AI client through a local stdio process. Its documented tools include:

- DataModel tree search and instance inspection.
- Script read, search, grep, and multi-edit.
- Luau execution in Edit, Client, or Server contexts.
- Starting/stopping playtests.
- Console output and viewport screenshots.
- Character navigation and simulated keyboard/mouse input.
- Asset search/insertion.
- Procedural model, mesh, material, animation, and avatar generation.
- Specialized explore/playtest subagents.

This is a major practical Creator Brain surface. Prefer the built-in server over maintaining a forked Studio bridge unless STAR has a specific missing capability.

### Multiplayer test design

Combine the Studio MCP playtest loop with StudioTestService for scripted server-plus-client scenarios. StudioTestService supports up to eight simulated clients per session, but only one multiplayer test session per Studio instance. Its plugin/server/client execution boundaries must be respected.

Required test suites:
- player join/leave and reconnect;
- party and matchmaking;
- inventory/equipment replication;
- server-authoritative purchases and rewards;
- remote-event validation and rate limits;
- respawn/team transitions;
- client disconnect during a transaction;
- network latency/jitter/loss;
- UI across device form factors;
- visual screenshot regression.

The creator loop becomes:

**Inspect → Plan → Edit → Static checks → Launch → Observe → Multiplayer test → Repair → Re-run → Save evidence**

A script compiling is not proof that a game feature works.

---

## 7. Gamer Brain — real-time control plus strategic learning

Keep two different loops:

**Reactive controller**
- camera and movement;
- aiming and interaction;
- short-horizon dodging/jumping;
- immediate controls with strict deadlines.

**Strategic planner**
- understand goals and mechanics;
- choose routes and strategies;
- manage resources;
- decide when to practice or switch tactics;
- request a specialist tool only when needed.

Do not send every video frame to a large language model. Use event-triggered observation: scene changes, objective updates, damage, deaths, inventory changes, new UI, navigation failure, or a bounded periodic checkpoint. A lightweight vision/perception path can handle routine frames; the strategic model should reason when state changes matter.

### Reusable game skill format

Each promoted skill should include:
- game/engine and version;
- preconditions and expected state;
- action sequence or controller;
- expected effects;
- known failure modes;
- resource/time budget;
- evidence and test IDs;
- confidence and scope;
- held-out maps/tasks passed.

Evaluate cold-start performance, practice learning curve, retention after a delay, and held-out transfer. A skill that works only on the exact practiced map is not general mastery.

---

## 8. Natural VTuber presence — human-like interaction without false human claims

The objective is a convincing AI character, not a system that fabricates a human biography or pretends to have senses it does not possess.

### Social Director

- Distinguish a viewer addressing STAR from viewer-to-viewer conversation.
- Answer a direct question once; suppress duplicate answers when a human has already resolved it.
- Use short backchannels when useful.
- Allow quiet listening and focused gameplay.
- Avoid narrating every frame or forcing a catchphrase into every reply.
- Track unresolved audience questions with bounded age and session scope.
- Keep speaker labels ephemeral and consent-aware.

### Avatar Director

- Drive mouth motion from audio actually emitted, not text merely generated.
- Use a priority system for speaking, listening, reactions, gestures, blinks, and idle motion.
- Cancel stale avatar commands when a speech generation is interrupted.
- Coalesce obsolete frame updates but never silently drop semantic events or playback acknowledgements.
- Measure audio-to-avatar offset separately from model latency.

### Useful streaming features

1. Correction-aware live captions.
2. Viewer Q&A with answer deduplication.
3. Contextual game commentary with a quiet/focus mode.
4. Co-op strategy and challenge modes.
5. Stream highlight markers with owner review before publishing.
6. Audience polls and bounded interactive events.
7. Post-stream session summaries linked to evidence.
8. A creator mode that can move from gameplay into Roblox Studio without losing conversation state.
9. Opt-in multilingual captions/translation.
10. A stream-health panel showing voice, inference, avatar, OBS, and game health separately.

---

## 9. General knowledge and independent learning

STAR's research system should maintain a claim ledger, not a pile of scraped pages.

Each useful claim should carry:
- source URL and publisher;
- publication/update date;
- retrieval date;
- source type and authority;
- exact supporting passage or structured data pointer;
- scope and assumptions;
- freshness requirement;
- conflicting evidence;
- confidence/uncertainty;
- downstream tasks that depend on the claim.

Separate stable knowledge (for example, a programming concept) from volatile knowledge (for example, a current API, release, price, or event). Volatile claims must be revalidated before action.

A research task should end with a concise evidence-backed answer, an explicit unknowns list, and reusable notes/skills only when the evidence supports them.

---

## 10. Implementation order and promotion gates

### Phase A — integration truth
1. Reconcile #1151 and #1181 into one audio implementation.
2. Preserve #1178 room/persona behavior and the existing #1177 task-ledger contract.
3. Confirm there is one playback clock, one meter worker, one microphone freshness policy, and one resource-admission authority.
4. Run exact-head CI after the final branch changes.

### Phase B — measurement
1. Add causal trace IDs across voice, inference, tools, avatar, OBS, and game samples.
2. Adopt a pinned OpenTelemetry GenAI schema revision.
3. Keep content capture disabled by default.
4. Build a repeatable mixed-load benchmark with p50/p95/p99 and quality scores.
5. Record a baseline before tuning any model or cache setting.

### Phase C — capability pilots
1. Benchmark Nemotron Streaming, Moonshine, sherpa-onnx, and Faster-Whisper on target Windows hardware.
2. Add Roblox Studio MCP playtest evidence and StudioTestService multiplayer scenarios.
3. Add event-triggered Gamer Brain observations and held-out skill transfer.
4. Add playback-acknowledged avatar synchronization.
5. Run a multi-hour rehearsal with voice, chat, game, OBS, avatar, and one bounded background task.

### Promotion gates

| Capability | Required evidence before promotion |
|---|---|
| Audio runtime | Callback p95/p99, no unexplained underflows, bounded queue age |
| ASR | Better end-to-end WER/latency/CPU tradeoff on the target PC |
| Inference | Lower p95/p99 response latency without answer-quality regression |
| VTuber | Correct turn-taking, interruption, playback/avatar sync, stable long session |
| Gamer Brain | Verified objective outcomes and held-out transfer |
| Creator Brain | Static checks plus repeated solo and multiplayer playtests |
| General knowledge | Claim-level sources, freshness checks, contradiction handling |
| Autonomy | Task generation/version checks, cancellation, rollback, permission compliance |

### Explicit non-goals

- No hard real-time guarantee is claimed for Python/PortAudio.
- No ASR/TTS provider or model weight is installed by this research document.
- No model routing, batching, KV-cache, context-size, or resource default is changed.
- No raw microphone/viewer audio is retained by default.
- No OBS, VTube Studio, game-input, public-chat, publishing, spending, or account permission is granted by a model-generated plan.
- No Roblox public experience is edited or published by this research.
- No physical Windows device, RTX 4060, OBS, VTube Studio, gameplay, or live-stream acceptance is claimed.

---

## Sources reviewed

1. OpenTelemetry GenAI metrics: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-metrics.md
2. OpenTelemetry client inference conventions: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/client-inference.md
3. OpenTelemetry GenAI token metrics: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-token-metrics.md
4. Google Research TurboQuant: https://research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression/
5. OmniKVQuant: https://arxiv.org/abs/2609.11582
6. llama.cpp speculative decoding: https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md
7. Nemotron on-device streaming ASR study: https://arxiv.org/abs/2604.14493
8. sherpa-onnx Nemotron streaming models: https://k2-fsa.github.io/sherpa/onnx/nemo/nemotron-streaming.html
9. Moonshine v2: https://arxiv.org/abs/2602.12241
10. Moonshine Voice implementation: https://github.com/moonshine-ai/moonshine-v2
11. PortAudio callback guidance: https://github.com/PortAudio/portaudio/wiki/Tips_Callbacks
12. Microsoft IAudioClient3 shared-mode engine periods: https://learn.microsoft.com/en-us/windows/win32/api/audioclient/nf-audioclient-iaudioclient3-getsharedmodeengineperiod
13. Roblox Studio MCP: https://create.roblox.com/docs/studio/mcp
14. Roblox StudioTestService: https://create.roblox.com/docs/reference/engine/classes/StudioTestService
15. Roblox client/server security: https://create.roblox.com/docs/scripting/security/client-server-boundary
16. Full-Duplex-Bench v3: https://www.full-duplex.ai/benchmarks/fdb-v3
17. InteractionBench: https://www.fullduplex.ai/benchmarks/interactionbench
18. GameWorld: https://gameworld-project.github.io/
19. GameDevBench: https://github.com/waynchi/gamedevbench
20. OBS WebSocket: https://github.com/obsproject/obs-websocket
21. VTube Studio API: https://github.com/DenchiSoft/VTubeStudio

---

**Run 29 conclusion:** STAR's next quality jump depends on seeing the whole system clearly. A correlated trace, a single reconciled audio path, CPU-friendly streaming ASR, verified Roblox playtests, held-out game-skill transfer, and playback-grounded avatar behavior are more valuable than another disconnected agent or another unmeasured model setting.
