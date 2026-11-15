# STAR Run 34 — Fresh-Frame Game Control, Full-Duplex Evaluation, and Human-Presence Runtime

**Research date:** 2026-11-14 (America/Chicago)  
**Repository:** `oncoursemail/Star-AI-Project`  
**Research branch:** `research/star-run24-integration-blueprint-20261114`  
**Companion runtime PRs:** #1181 (voice playback/telemetry), #1182 (game-control gate)  
**Scope:** close the gap between continuous perception and delayed action; establish a reproducible full-duplex streamer evaluation; connect voice, avatar, OBS, game control, creator tools, and general knowledge without duplicating authorities.

---

## Executive decisions

Run 34 makes six decisions.

1. **Capture may be continuous; action evidence must be bounded.** A 60 FPS capture loop can produce several newer frames while a model is reasoning. A decision should remain tied to the exact source frame that produced it, provided that frame is still within a strict age budget. Requiring every decision to reference the newest captured frame makes a slower but valid controller reject nearly every action.
2. **Retain a bounded observation window, not an unbounded screenshot history.** Store only a small number of metadata records and short-lived frame references. Eviction invalidates permits. Keep the pixels in a latest-wins GPU/frame buffer; do not persist raw gameplay by default.
3. **Permit ordering is part of control safety.** Only one unconsumed action permit may be outstanding. A permit is single-use, tied to target/session/epoch/frame/sequence, and expires no later than the source observation's freshness deadline.
4. **Evaluate natural streaming as a task, not a voice demo.** Measure interruption, self-correction, multi-step tool use, turn timing, task completion, and whether unfinished work is resumed and delivered.
5. **One event spine and one scheduler remain mandatory.** Reuse the existing RoomStreamHost/RoomTurnDirector, task ledger, resource admission, playback clock, and avatar frame pump. Do not add a second social director, task ledger, playback clock, or GPU scheduler.
6. **Use evidence, licensing, and owner approval as promotion gates.** Research results are not STAR results; a benchmark score is not production readiness; a model's speed is not useful if it harms speech quality, game success, avatar sync, or stream stability.

No new model, dataset, credential, provider, package, or production default is enabled by this document.

---

## 1. Repository audit and new runtime finding

The Run 31 game-control gate in #1182 was deliberately conservative: every action had to reference the latest accepted frame, and consuming a permit required that same frame still be the latest.

That is safe for a paused, request/response test, but it is a poor fit for a continuously running capture loop.

At 60 FPS, a new frame arrives about every 16.7 ms. If perception plus reasoning takes 100 ms, roughly six frames can arrive before the action is ready. If the host submits every captured frame to the gate, a strict latest-frame comparison rejects the decision even though its source frame may still be fresh enough for the configured action budget.

This is not a reason to accept stale actions. It is a reason to distinguish:
- the newest frame available to perception;
- the exact frame used to make a decision;
- the maximum allowed age of that decision when authorization and execution occur.

### Run 34 implementation in companion PR #1182

The gate now uses a bounded observation history (default 64 metadata records, configurable from 2 to 256).

- A proposed action must identify an exact frame ID, capture epoch, and monotonically increasing sequence that is still in the bounded history.
- The source observation must still be within the configured observation-age limit.
- The action timestamp must not predate the source observation beyond the allowed clock skew.
- Each observation sequence can authorize at most one action.
- Only one unconsumed permit can be in flight, preventing two action batches from being consumed out of order and overwriting held-button state.
- A permit remains tied to the exact source observation and expires no later than that observation's freshness deadline, the action-age deadline, or session expiry.
- If the source frame is evicted, its pending permit is removed and cannot be consumed.
- A changed capture epoch still stops the session and returns all held controls for release.
- The gate still does not capture pixels or inject operating-system input. Trusted host adapters must supply target, consent, focus, process identity, and monotonic timestamps.

### Required regression cases

- New frames arrive while an older-but-still-fresh decision is being computed: the decision remains eligible.
- The same decision becomes too old before authorization: reject it.
- The permit expires before consumption: reject it.
- A newer frame evicts the source frame: reject and remove the pending permit.
- Two different observations are present: do not allow a second unconsumed permit until the first is consumed or expires.
- A repeated action ID, wrong process, changed window, changed executable hash, focus loss, manual override, revoked consent, or capture-epoch change fails closed.
- Stop, focus loss, session expiry, and capture reset return every held control for release.

The bounded window is not permission to execute old decisions. The configured per-game age limit remains authoritative. Fast games should use tighter values than slow turn-based games; calibrate from measured end-to-end perception-to-input latency, not guesswork.

---

## 2. Full-duplex speech: move beyond endpoint detection

A natural AI streamer must decide whether to continue listening, backchannel, answer, yield, interrupt itself, or resume an unfinished response. Simple voice activity detection cannot make all of these decisions.

### Full-Duplex-Bench v3

The current benchmark description documents 100 human-recorded spoken requests across 79 scenarios and 12 speakers, four domains, five disfluency categories, and tasks requiring one to three chained tool calls against mock APIs. Audio is streamed through LiveKit. Scoring includes tool-call accuracy, Pass@1, latency, and turn-taking.

The published paper's reported results include a Pass@1 of 0.600 for GPT-Realtime and 4.25 seconds as the fastest reported latency for Gemini Live 3.1 in that evaluation. Only two model configurations are listed in the current benchmark catalogue; these numbers must not be treated as a universal model ranking or a STAR target.

**STAR application:** create a small, licensed, consented internal replay suite inspired by the benchmark's failure categories:
- self-correction ("go left—actually right");
- hesitation and long pauses;
- overlapping viewer speech;
- a viewer addressing another viewer;
- a multi-step request with tool calls;
- request changes while a task is in progress;
- interrupted speech that must be resumed;
- a task completed but not yet communicated;
- a request that should be acknowledged but not answered immediately.

### FD-VAD: semantic endpointing

FD-VAD studies an ASR-free streaming endpoint classifier that maps bounded causal audio windows to Continue/Stop decisions. Its design uses confidence-gated endpoint commitment and boundary-focused hard negatives. The paper reports 0.853 end-of-turn recall at a false-positive rate no greater than 0.10 on the TurnBench development set.

**STAR application:** evaluate semantic endpointing as a small turn-control signal, not as the conversation brain. It must not independently trigger tools, commit transcripts, or decide that a viewer's message is a command. Compare it with the existing room director and acoustic VAD using:
- false interruption rate;
- missed interruption rate;
- stop latency after a true interruption;
- false end-of-turn rate during hesitation;
- response delay after a completed request;
- playback-resume correctness;
- tool-call correctness after self-correction.

### State machine recommendation

Reuse the existing RoomTurnDirector and represent turn state explicitly:

- LISTENING
- PARTIAL_UNDERSTANDING
- USER_HOLDS_FLOOR
- RESPONSE_READY
- SPEAKING
- INTERRUPT_REQUESTED
- YIELDED
- RESUME_PENDING
- DELIVERY_PENDING
- DELIVERED

The task ledger remains the source of truth for unfinished work. The room director owns who has the floor. The playback clock owns when audio was submitted and scheduled. A response is not marked delivered merely because TTS generated it; delivery requires the existing playback acknowledgement policy.

---

## 3. Human-presence streaming: what to optimize

The objective is a believable, expressive AI character—not continuous chatter and not fabricated human biography.

### Conversation policy

- Use contextual backchannels only when they do not interrupt the current speaker.
- Let viewers talk to each other without STAR taking every turn.
- Prefer short acknowledgements for low-value events and fuller answers for direct questions.
- Maintain a bounded question queue with age, addressee, relevance, and moderation state.
- Do not speak a message that has been deleted, held, or removed by moderation.
- Avoid repeating a response when a viewer or co-host has already answered.
- Preserve an unfinished task across a topic switch, then return when there is a natural opening.
- Allow quiet focus during difficult gameplay or creation work.
- Make laughter and expressive reactions contextual and playback-synchronized; do not force a laugh on every joke.
- Maintain stable character preferences and conversational style while being transparent that STAR is an AI.

### Avatar timing

VTube Studio's public API supports authenticated plugins, Live2D parameter reads, custom parameter creation, parameter injection, hotkeys, events, and item operations. The API requires user approval for plugin access. Parameter injection must be refreshed at least once per second or the parameter is considered lost and returns to its previous controller/default.

**STAR application:**
- Keep a persistent authenticated local adapter with explicit user approval.
- Use a latest-wins parameter frame for high-frequency mouth, gaze, and expression values.
- Keep semantic expression intent separate from the audio playback cursor.
- Derive mouth-open/viseme timing from the actual PCM playback timeline, not text generation time.
- Smooth and clamp parameter values; send only parameters owned by STAR's plugin.
- Reconnect by re-authenticating the current session with the stored token; handle revoked access as a hard disconnected state.
- Do not create custom parameters automatically without a reviewed model mapping and user-visible explanation.

### OBS control

OBS WebSocket is bundled with OBS 28 and later. The official project strongly recommends password protection. Its protocol separates connection identification, events, requests, and request responses.

**STAR application:**
- Bind to loopback by default; never expose OBS control to the public internet.
- Require the OBS authentication handshake.
- Use an allowlisted request set for scene changes, recording state, stream status, and approved transitions.
- Keep starting a public broadcast, changing stream destinations, and changing keys behind explicit owner approval.
- Record scene/recording state as events on the same event spine; do not poll at high frequency when event subscriptions are available.
- A power-loss restart must restore the desktop service, not silently resume a public stream.

---

## 4. Windows visual runtime: GPU-resident capture and freshness

Microsoft's DXGI Desktop Duplication API returns desktop frames as DXGI surfaces and exposes dirty and move rectangles. This can reduce unnecessary pixel processing, but it does not make full-frame CPU readback free.

### Recommended capture path

1. Acquire the next DXGI frame.
2. Validate output/display identity and capture epoch.
3. Crop to the explicitly approved game window/region.
4. Use dirty/move metadata to avoid reprocessing unchanged regions where the vision model can benefit.
5. Keep a bounded latest-frame slot for visual perception.
6. Preserve only frame metadata and short-lived references needed by the decision loop.
7. Release the acquired DXGI frame promptly.
8. On access loss, display changes, lock-screen transitions, or target-window changes, reset the capture epoch and stop the game-control session.

### GPU/CPU transfer policy

- Keep frame processing on the GPU as long as the selected vision stack permits.
- If CPU inference is used, perform one explicit, measured readback and reuse the resulting crop; avoid repeated conversions and copies.
- Do not queue every screenshot for a slow model. Drop superseded frames and process the newest useful observation.
- Use lower-frequency strategic vision and higher-frequency lightweight tracking only where a verified tracker exists.
- Keep the game render thread, capture thread, vision inference, and input executor separately measured.

---

## 5. Faster local inference: measure the whole request

The official llama.cpp server documentation lists CPU/GPU quantized inference, parallel decoding, continuous batching, multimodal support, monitoring endpoints, schema-constrained output, function calling, and speculative decoding. The repository also provides SPEED-Bench tooling for evaluating speculative-decoding configurations with per-category latency, throughput, and draft acceptance.

### STAR's inference measurement contract

Every paired test should record:
- queue wait;
- prompt prefill duration and prompt tokens/sec;
- time to first token;
- time per output token and decode tokens/sec;
- total generated tokens;
- cache hit/reuse indicators where available;
- draft tokens proposed and accepted for speculative decoding;
- cancellation latency after interruption;
- first TTS chunk;
- first PCM submitted;
- first callback with non-empty PCM;
- estimated DAC playback time;
- CPU utilization, GPU utilization, VRAM, RAM, and thermal/power state.

### Resource policy for the local 8 GB GPU

- Preserve one resource-admission authority from #1140/#1142.
- Reserve the foreground budget for speech, current conversation, and approved game control.
- Avoid loading several large vision/audio/reasoning models onto the 8 GB GPU simultaneously.
- Benchmark CPU ASR against GPU ASR under the full mixed workload, not in isolation.
- Run visual understanding on event-triggered crops instead of continuous full-resolution inference.
- Keep background research, embedding/index maintenance, large asset generation, and bulk game building in the background lane or on the separate development machine.
- Do not unload/reload the active reasoning model during a live conversation unless the user has explicitly enabled a tested transition policy.
- Speculative decoding is a candidate only when draft acceptance is high enough to reduce end-to-end latency without raising memory pressure or worsening output quality.

The best configuration is the one that improves p95/p99 interactive latency while preserving answer quality, audio reliability, game FPS, and task success—not the one with the highest isolated tokens/sec.

---

## 6. Gamer Brain: score competence, not activity

The current GameWorld research direction separates normalized progress from task success. Gym-Anything-RT demonstrates why live-speed, slowed, and paused performance must be reported separately.

### Required evaluation dimensions

- success rate on the practiced task;
- success rate on unseen maps/seeds;
- progress before failure;
- deaths, retries, and recovery time;
- action freshness at authorization and consumption;
- perception-to-action latency p50/p95/p99;
- manual intervention rate;
- dropped or evicted observations;
- input release correctness;
- live-speed versus slowed versus paused gap;
- skill retention after a delay;
- transfer to a different game with similar mechanics.

### Skill promotion

A game episode produces candidate knowledge only:
1. Record the objective, game version, map/seed, and observation/action trace metadata.
2. Separate the observed result from the model's explanation of the result.
3. Verify success from a game state, trusted test harness, or independently checkable outcome.
4. Generate a candidate procedural skill with preconditions and failure modes.
5. Replay it on held-out seeds or maps.
6. Promote only if it improves the paired baseline without increasing unsafe actions or manual interventions.
7. Retain provenance and allow a skill to be contradicted, revised, or retired after a game update.

No anti-cheat, DRM, game memory, or platform restrictions may be bypassed. Start with owner-approved offline or sandbox games and games that permit automation.

---

## 7. Creator Brain: visual verification is a first-class test

The current official GameDevBench repository describes 333 Godot 4.4.1 tasks across 2D graphics/animation, 3D graphics/animation, UI, and gameplay logic. It emphasizes multimodal feedback and visual inspection. Earlier 132-task paper snapshots are not the same release as the current 333-task benchmark; STAR must pin the exact benchmark version and never mix scores across versions.

### STAR build loop

- Inspect the existing project and establish a clean baseline.
- Write a short plan and define observable acceptance conditions.
- Make the smallest coherent edit.
- Run static checks and engine-native tests.
- Launch the game in a disposable test session.
- Capture screenshots/video and compare against the requested behavior.
- Inspect logs, errors, frame time, and multiplayer state.
- Repair and rerun the failing test.
- Run at least one held-out scenario.
- Save the exact source revision, assets, test results, and visual evidence.

### Roblox-specific plan

Use Roblox Studio's built-in MCP server as the preferred local bridge. Use StudioTestService for plugin-driven play/run tests and multiplayer sessions. The official API documents up to eight simulated clients and one multiplayer test session per Studio instance. A single Play Client MCP session is not a substitute for deterministic multi-client testing.

Build reusable test templates for:
- lobby and matchmaking;
- party invite/leave;
- player disconnect/reconnect;
- replication and server authority;
- inventory/economy;
- combat hit validation;
- respawn and round transitions;
- exploit-resistant RemoteEvent validation;
- mobile/controller input;
- performance under increasing player count.

The benchmark's public task data is for evaluation. Do not train on held-out answer artifacts or report benchmark completion without following the benchmark's current license and evaluation rules.

---

## 8. General knowledge and broader creator abilities

STAR should keep factual knowledge and procedural skills separate.

### Factual knowledge record

Each claim should retain:
- claim text;
- source URL and source type;
- author/publisher where available;
- publication and retrieval dates;
- applicable time period and scope;
- confidence and evidence excerpts;
- contradictory claims;
- supersession/revision relationship;
- whether the source is primary, secondary, or community-generated.

Use authoritative sources for fast-changing software APIs, scientific claims, and current events. If sources conflict, preserve the disagreement and explain uncertainty instead of silently choosing one.

### Procedural skill record

Each skill should retain:
- task and preconditions;
- tool/environment versions;
- exact steps or policy;
- expected observable result;
- verification procedure;
- failure modes and recovery;
- successful and failed trials;
- held-out transfer results;
- last revalidation date.

This supports programming, Roblox, Godot, Unity, Blender, art, animation, audio, video editing, streaming, science, history, and everyday general knowledge without treating an unverified answer as a proven skill.

---

## 9. Integration map — do not create competing systems

| Concern | Existing authority to reuse | Run 34 rule |
|---|---|---|
| Live audience and turn state | #1178 RoomStreamHost / RoomTurnDirector | Platform adapters feed the existing host |
| Unfinished work | #1177 task/communication ledger | Task completion and delivery remain separate |
| GPU/CPU scheduling | #1140 / #1142 | One resource admission controller |
| Incremental thinking | #1160 stable-prefix policy | Speculation cannot cause side effects |
| Speed/quality evaluation | #1166 / #1167 and paired eval train | Compare on the same prompts, models, hardware, and workload |
| Playback time | #1181 PlaybackSnapshot | DAC estimate is not acoustic/remote-viewer proof |
| Avatar frames | #1159 latest-wins pump | Coalesce visual samples, never discard task/speech events |
| Game action policy | #1182 GameControlGate | Exact observation binding and one outstanding permit |
| Creator tests | Roblox Studio MCP / StudioTestService | Engine-native test evidence plus visual holdouts |
| Long-term knowledge | #1117 governed consolidation | Promote only evidence-backed, reversible memories |

---

## 10. Acceptance gates

### A. Fresh-frame game-control gate
- 60 FPS synthetic capture with 50–200 ms decision latency.
- Bounded history remains within configured capacity.
- Fresh source frames remain eligible despite newer frames.
- Expired, evicted, replayed, wrong-target, and wrong-epoch actions are rejected.
- Only one outstanding permit exists.
- Every stop path releases all held controls.
- No action is injected after owner manual override or focus loss.

### B. Full-duplex voice gate
- Replay human-consented test utterances with hesitations, self-corrections, overlap, and interruptions.
- Report false interruption, missed interruption, end-of-turn recall, response latency, task success, and delivery completion.
- Confirm interrupted speech is cancelled promptly and unfinished work is resumed once.
- No duplicate TTS, duplicate tool side effects, or stale partial transcript is committed.

### C. VTuber mixed-load gate
- Run a private rehearsal with local synthetic chat, OBS recording, VTube Studio, gameplay, ASR, LLM, and TTS.
- Record game FPS p10/p50, audio callback p95/p99, underflows, ASR latency, TTFT, TTS first-chunk, DAC playback estimate, avatar frame age, OBS render/encode lag, CPU/GPU/VRAM/RAM.
- Verify mouth movement follows playback, not text generation.
- Verify a direct owner mute/stop works even if model inference is stalled.
- Verify reconnect does not silently start a public stream.

### D. Creator and learning gate
- Complete a fixed set of Roblox/Godot tasks with clean baselines.
- Verify server/client behavior and screenshots.
- Re-run on held-out seeds/maps.
- Promote skills only when the independent verifier passes.
- Keep benchmark version, harness, model, effort, and confidence intervals attached to results.

No public broadcast, model replacement, game automation, or permanent memory promotion is approved by this research document.

---

## 11. Source register

1. Full-Duplex-Bench v3 benchmark description — https://www.fullduplex.ai/benchmarks/fdb-v3
2. FD-VAD paper — https://arxiv.org/abs/2609.35791
3. HiThink Turn paper — https://arxiv.org/abs/2609.34096
4. Full-Duplex-Bench v2 — https://www.fullduplex.ai/benchmarks/fdb-v2
5. llama.cpp server README — https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
6. llama.cpp SPEED-Bench README — https://github.com/ggml-org/llama.cpp/blob/master/tools/server/bench/speed-bench/README.md
7. Microsoft DXGI Desktop Duplication — https://learn.microsoft.com/en-us/windows/win32/direct3ddxgi/desktop-dup-api
8. DXGI dirty rectangles — https://learn.microsoft.com/en-us/windows/win32/api/dxgi1_2/nf-dxgi1_2-idxgioutputduplication-getframedirtyrects
9. VTube Studio API — https://github.com/DenchiSoft/VTubeStudio
10. OBS WebSocket — https://github.com/obsproject/obs-websocket
11. Roblox StudioTestService — https://create.roblox.com/docs/reference/engine/classes/StudioTestService
12. Roblox built-in Studio MCP announcement — https://devforum.roblox.com/t/assistant-updates-studio-built-in-mcp-server-and-playtest-automation/4474643
13. GameDevBench official repository — https://github.com/waynchi/gamedevbench
14. GameDevBench ICML 2026 paper — https://proceedings.mlr.press/v306/chi26a.html
15. OpenTelemetry GenAI metrics (Development status) — https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-metrics.md

---

## Explicit limitations

- The game-control change is a host-side policy gate only; no DXGI capture or input executor is added by this document.
- No speech model, TTS voice, ASR model, or speculative-decoding mode is installed or enabled.
- No OBS or VTube Studio connection is established.
- No Twitch/YouTube credentials are created or used.
- No real game, Roblox Studio, microphone, speaker, RTX 4060, or public stream is tested here.
- Paper and benchmark numbers are source-reported and are not STAR measurements.
- The 16-record observation history is a bounded default, not a universal tuning result; tune per game using measured latency and safety tests.
- PRs #1180, #1181, and #1182 remain draft/unmerged until their exact-head CI, dependency review, and owner acceptance are complete.
- Production main remains unchanged.
