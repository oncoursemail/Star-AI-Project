# STAR Run 33 — Realtime Media Pipeline, Resource Budgets, and Measured Creator Runtime

**Research date:** 2026-11-14  
**Status:** architecture and implementation plan; a companion playback-clock integration has been committed to draft PR #1181 and is awaiting its exact-head CI run.  
**Purpose:** turn STAR's existing voice, room, scheduler, game-control, Roblox, memory, and creator prototypes into one measurable live runtime without claiming unmerged or untested capabilities are shipped.

---

## 1. Executive decisions

1. Keep one host-owned scheduler, one event envelope, one monotonic time domain, and one task/delivery ledger. Do not create a second VTuber scheduler or another chat queue beside the existing RoomStreamHost.
2. Treat speech recognition, speech generation, reasoning, game perception, avatar animation, OBS, and audience ingestion as separate services with explicit resource leases and cancellation generations.
3. Do not run every model on the 8 GB GPU at once. Protect the audio/game/voice/avatar reserve already represented by the workload-admission work in PRs #1140 and #1142. The policy components still need a real Windows process supervisor and calibrated host budgets.
4. Use measured full-stream TTS as the next speech experiment. VoXtream2.5 is technically compelling, but its Hugging Face model card marks the weights CC-BY-NC-4.0. Do not use those weights for monetized/public commercial streaming unless rights are separately cleared. Kokoro is a smaller Apache-licensed baseline, but its documented pipeline is sentence/chunk oriented rather than the same full-stream interface.
5. Keep Moshi as an architecture reference or remote-server experiment, not a default RTX 4060 8 GB deployment: the upstream project describes a 7B temporal transformer, approximately 200 ms practical latency on an L4, and says its PyTorch path needs significant GPU memory; Windows is not officially supported.
6. Measure the audio path through PortAudio DAC time, then separately through loopback capture, OBS render/encode, and remote playback. A local callback timestamp is not proof that a viewer heard the audio.
7. Evaluate game agents on outcome-verified tasks, not screenshots that merely look successful. GameWorld's published results show that partial progress and task success are materially different.
8. Make natural streaming a consequence of good turn-taking, social attention, memory continuity, voice timing, and expressive animation—not a prompt that forces constant talking or fake human autobiography.

---

## 2. Repository reality audit

The current public architecture is a local-first Windows desktop application with a React interface, Python host, local llama.cpp/Qwen runtime, project knowledge and memory, and scoped Roblox Studio tools. The architecture document explicitly distinguishes shipped code from unmerged candidates.

Relevant existing foundations inspected:

- PR #1180: cumulative research and integration blueprints.
- PR #1181: freshness-first microphone buffering, asynchronous speaker-level metering, and per-reply PortAudio DAC-time PlaybackSnapshot.
- PR #1182: fail-closed game-control policy gate and one-action-per-observation budget.
- PR #1140: bounded CPU/RAM/VRAM workload admission policy.
- PR #1142: bridge between the stream-pressure governor and workload admission.
- PR #1178 and related room work: room director, bounded queues, short-lived payload storage, host-only room submission, and opt-in room-only desktop construction.
- Issue #584: the actual Creator Studio acceptance checklist.

Important limitations from the source audit:

- The workload admission controller reserves abstract resource vectors; it does not start, stop, preempt, or measure operating-system processes.
- The room host accepts trusted, already-classified events; it does not itself implement Twitch/YouTube clients, diarization, ASR, or addressee classification.
- The game-control gate authorizes actions; it does not capture DXGI frames or inject keyboard/mouse input.
- Roblox Studio MCP can operate an open Studio session, but it is not a general-purpose consumer-game controller.
- Physical audio tests are still needed. Synthetic callback tests cannot establish device-level callback p99 or acoustic latency.
- Public streaming, channel OAuth, monetized broadcasting, original art approval, and full Windows owner acceptance remain open milestones in issue #584.

Do not describe any of these unmerged adapters as released capabilities.

---

## 3. New speech-generation research

### 3.1 VoXtream2.5 — strongest full-stream TTS candidate to benchmark

Sources:
- https://github.com/herimor/voxtream
- https://herimor.github.io/voxtream/
- https://huggingface.co/herimor/voxtream2.5

The upstream project describes VoXtream2.5 as a zero-shot full-stream TTS model that accepts text incrementally and can adjust speaking rate while an utterance is being generated. Its README reports 30 ms first-packet latency and roughly 10x real-time generation on an RTX 3090; its model card reports real-time CPU inference for the int8 GGUF path through llama.cpp. The model card lists approximately 0.5B parameters.

Hardware implications:
- The project reports about 3 GB VRAM for its normal configuration and about 2 GB additional VRAM for prompt enhancement.
- The RTX 3090 measurements are not STAR's RTX 4060 measurements.
- The CPU GGUF path is worth testing because it could preserve GPU headroom for the game and reasoning model.
- First-packet latency, sustained real-time factor, audio quality, CPU contention, and interruption behavior must all be measured together.

**Critical rights gate:** the Hugging Face model card labels the weights CC-BY-NC-4.0. The repository code has MIT/Apache components, but code licensing does not override the model-weight license. Do not package or use these weights for monetized streaming unless a rights holder provides a compatible written license. The project also prohibits generating another person's voice without consent. Use only STAR's owner-approved original voice prompt and voice assets.

### 3.2 Kokoro-82M — small permissive baseline

Sources:
- https://github.com/hexgrad/kokoro
- https://huggingface.co/hexgrad/Kokoro-82M

The official repository describes an 82M-parameter TTS model and identifies Apache-2.0 weights. It is an excellent compact quality/latency baseline for STAR's current fallback path. It supports multiple languages and voice packs, but the documented Python pipeline generates text chunks; it should not be assumed to provide the same word-by-word full-stream behavior as VoXtream.

Benchmark:
- first PCM chunk latency;
- real-time factor under CPU-only and GPU modes;
- pronunciation and prosody on STAR's actual scripts;
- sentence-boundary artifacts;
- barge-in cancellation latency;
- memory residency while the game and local LLM are active;
- voice consistency across laughter, short acknowledgements, and long explanations.

The exact voice pack and every dependency still need a license review before bundling.

### 3.3 Kyutai Delayed Streams Modeling — streaming STT and TTS research

Source: https://github.com/kyutai-labs/delayed-streams-modeling

The upstream project describes streaming STT models with word-level timestamps and semantic VAD. Its README lists a 1B English/French model with approximately 0.5-second delay and a 2.6B English model with approximately 2.5-second delay. It also describes a Rust production server and reports multi-stream throughput on L40S hardware.

Use this as:
- a remote Brain 2 / server-side STT candidate;
- a reference for chunked, timestamped speech pipelines;
- a comparison against Faster-Whisper, Moonshine, and sherpa-onnx.

Do not infer that the H100/L40S throughput numbers apply to a Windows RTX 4060.

### 3.4 Moshi — full-duplex architecture reference

Source: https://github.com/kyutai-labs/moshi

Moshi models incoming and outgoing audio streams jointly. The project describes a 7B temporal transformer, 80 ms Mimi frames, 160 ms theoretical pipeline latency, and approximately 200 ms practical latency on an L4 GPU. Its upstream README says the PyTorch path requires substantial GPU memory and that Windows is not officially supported.

Recommendation:
- study its simultaneous listening/speaking architecture and turn-taking behavior;
- do not install it as STAR's default local voice stack on the 8 GB Windows GPU;
- consider a separately budgeted remote service only if Brain 2 has suitable hardware and the network latency is measured.

### 3.5 Speech stack selection rule

Do not select a TTS/ASR provider based on a single headline latency number. Select on a matched test set with:
- first partial transcript;
- final transcript;
- first generated audio packet;
- first DAC-scheduled audio;
- total generation real-time factor;
- WER and punctuation quality;
- speaker/addressee confusion;
- CPU, RAM, and VRAM peaks;
- barge-in and cancellation behavior;
- voice identity consistency;
- commercial and voice-consent rights.

Keep the provider interface swappable and keep one active TTS voice stream per response generation.

---

## 4. Real-time architecture: one timeline, many workers

Recommended host-owned pipeline:

1. Audio capture adapter emits bounded PCM frames and device health counters.
2. Streaming VAD/ASR emits provisional hypotheses with word timestamps.
3. Turn controller decides whether to wait, acknowledge, interrupt, or close a turn.
4. Room host validates source, session, moderation result, deduplication, rate limit, and final-event status.
5. Social director chooses whether STAR should speak now, queue a response, stay quiet, or focus on gameplay.
6. Task ledger tracks unfinished work and whether the result has actually been delivered.
7. Resource runtime grants bounded leases to inference, game perception, TTS, avatar, research, and asset-generation workers.
8. Reasoning model produces a short, streamable response with explicit uncertainty.
9. Sentence/phrase chunker sends incremental text to TTS.
10. Speaker callback writes PCM and emits DAC-time playback evidence.
11. Avatar timeline consumes the same response generation and audible-time evidence.
12. OBS adapter observes scene/recording/stream state and reports events to the host.
13. Post-stream editor consumes recorded media and a non-destructive edit decision list.

Every event should carry:
- opaque session ID;
- unique event ID;
- source and source sequence;
- host monotonic timestamp;
- response-generation ID when applicable;
- cancellation generation;
- moderation and consent status;
- expiry;
- content hash or short-lived payload reference.

Use monotonic timestamps inside the host. Convert Twitch/YouTube wall-clock timestamps once at ingress; never compare provider wall clocks directly with audio callback monotonic clocks.

### One source of truth

- RoomStreamHost owns room event admission.
- RoomTurnDirector owns respond/queue/ignore/wait/interrupt decisions.
- Workload runtime owns resource admission.
- GameControlGate owns action authorization.
- Task ledger owns unfinished obligations and delivery state.
- Avatar director owns expressive animation state, but not speech truth.
- OBS adapter owns OBS request/event transport, but not publication permission.

No model-generated text may grant a capability, alter an owner permission, or mark an action as verified.

---

## 5. Resource budgeting for a Windows 8 GB VRAM host

The 8 GB VRAM constraint changes the design. Do not attempt to keep a large reasoning model, vision model, ASR, TTS, game, OBS, and avatar renderer resident on the GPU simultaneously.

### 5.1 Priority lanes

Use the existing lane model from PRs #1140/#1142:

| Lane | Priority | Policy |
|---|---:|---|
| Audio callback and device recovery | Highest | Never wait on model work |
| Game-control executor | Highest | Short bounded actions only |
| Voice/turn control | High | Protect first-response and interruption latency |
| Avatar render and sync | High | Keep frame pacing stable |
| Interactive chat/tools | Medium | Bounded concurrency |
| Research and long reasoning | Low | Defer during game/stream pressure |
| Learning/evaluation | Low | Run in background windows |
| Asset generation | Lowest | Run off-stream or on a separate machine |

The controller's resource vectors are accounting units, not live OS measurements. A trusted host adapter must:
- sample GPU VRAM, process RAM, CPU load, game frame time, OBS render/encode lag, and audio underflows;
- calibrate per-process peak memory from repeated runs;
- set a conservative STAR budget below installed hardware capacity;
- reserve room for Windows, drivers, the game, OBS, and transient spikes;
- mark health stale if telemetry stops;
- never free an active lease merely because its TTL elapsed; confirm worker termination first.

### 5.2 Model placement

Recommended experiments, not defaults:

- Small local text model: interactive quick responses and simple classification.
- Larger reasoning model: only when the task justifies it; route to Brain 2 or an explicitly selected hosted provider if local VRAM pressure is too high.
- ASR: prefer CPU or a separate host when its latency/accuracy remains acceptable.
- TTS: benchmark CPU GGUF and GPU modes separately; do not run ASR and TTS on the same GPU without mixed-load measurements.
- Vision: process at a bounded rate and resolution; use event-triggered crops rather than continuous high-resolution model calls.
- Avatar: keep rendering on the GPU only if the measured game/OBS frame budget allows it; otherwise reduce avatar update complexity, not game-control correctness.
- Asset generation: off-stream by default.

No silent cloud fallback. External inference must be an explicit owner-configured provider and must disclose that prompts/context leave the local machine.

### 5.3 llama.cpp optimization order

The current architecture already preserves a stable prompt prefix and measures TTFT. Keep that design.

Tune in this order:
1. measure cold load and warm request separately;
2. measure prompt prefill separately from decode when server counters exist;
3. preserve byte-identical system prefix and stable tool ordering;
4. keep per-turn retrieval and volatile data out of the stable prefix;
5. trim history in whole turns and use provenance-preserving summaries;
6. compare one slot vs two under the same interactive workload;
7. test speculative decoding only with a draft model that fits the real memory budget;
8. compare cache hits, decode speed, and correctness together;
9. reject any configuration that improves tokens/s but worsens p95 time-to-first-audio or task success.

The llama.cpp server documents parallel decoding, continuous batching, monitoring endpoints, schema-constrained output, multimodal support, and speculative decoding. Those are capabilities to benchmark, not a guarantee that every build/model/backend supports every combination.

---

## 6. OpenTelemetry and observability

Sources:
- https://github.com/open-telemetry/semantic-conventions-genai
- https://opentelemetry.io/docs/

The GenAI semantic-conventions repository covers spans, metrics, and events for GenAI clients, MCP, and provider-specific conventions. The repository currently shows its schema URL as TODO, so STAR should pin a reviewed commit and map its own stable internal names rather than blindly tracking a moving draft.

### Required trace tree

One interaction trace should connect:

- microphone frame receipt;
- VAD decision;
- ASR partial and final;
- intent/addressee decision;
- room moderation and queue;
- scheduler wait and lease;
- model queue, prefill, first token, and completion;
- TTS first packet and real-time factor;
- PortAudio callback and DAC estimate;
- avatar frame selection;
- OBS render/encode events;
- final delivery or cancellation.

### Metrics

| Metric | Why |
|---|---|
| p50/p95/p99 ASR partial latency | Listening responsiveness |
| End-of-speech to final transcript | Turn closure delay |
| Turn-decision latency | Avoid awkward pauses |
| Model queue wait | Scheduler bottleneck |
| TTFT and decode tokens/s | Reasoning speed |
| First TTS packet | Speech start |
| First DAC-scheduled PCM | Local output timing evidence |
| PortAudio input/output underflows | Device reliability |
| Meter queue drops | Echo/floor confidence |
| Avatar audio-to-mouth drift | Lip-sync quality |
| OBS render/encode lag | Stream quality |
| Game FPS p10 and frame-time p99 | Gameplay stability |
| Peak VRAM/RAM and CPU | Resource pressure |
| Queue age and obligation age | Lost or delayed work |
| Task success and holdout regressions | Actual intelligence |

Privacy defaults:
- no raw microphone PCM in traces;
- no full transcript or viewer message in metric labels;
- no API keys, stream keys, OAuth tokens, or private file paths;
- no persistent viewer identity profile by default;
- use opaque IDs and short retention;
- keep opt-in diagnostic captures local and redact them before sharing.

---

## 7. Natural VTuber streaming: behavior design

A natural streamer is not a system that talks constantly. The quality comes from timing, context, consistency, and attention.

### 7.1 Social attention scheduler

Classify events into:
- direct owner/operator instruction;
- direct viewer question or mention;
- safety/moderation event;
- high-salience gameplay event;
- ongoing viewer conversation;
- low-priority ambient chat.

Use:
- bounded queue with age and priority;
- per-source and per-speaker rate limits;
- deduplication by provider event ID;
- conversational turn ownership;
- a short "already answered" window;
- fair scheduling so one viewer cannot monopolize STAR;
- a quiet/focus mode during difficult gameplay;
- explicit owner interrupt and mute controls.

Do not read every chat message aloud. Acknowledge important messages naturally, answer selected questions, and allow viewers to talk to each other.

### 7.2 Personality and presence

- Keep STAR's established persona, lore, voice, and visual identity stable.
- Use varied but context-appropriate sentence openings.
- Permit short acknowledgements and silence.
- Avoid repetitive "thank you" loops.
- Let gameplay determine commentary density.
- Allow uncertainty and corrections.
- Laugh only when the interaction genuinely supports it; do not inject a laugh sound after every line.
- Do not claim a human body, private offline experiences, real-world memories, or feelings as biological facts.
- Be transparent that STAR is an AI character while allowing expressive character performance.

### 7.3 Avatar timing

- Audio playback is the authority for mouth timing.
- Semantic intent can select expression, gaze, and gesture, but cannot override the audible-time timeline.
- Every animation event carries the response-generation ID.
- Barge-in cancels stale speech and its associated animation.
- If playback telemetry is absent or invalid, the avatar should use a conservative fallback rather than inventing a precise sync time.
- Use a small fixed set of expressive motion primitives first, then layer gaze, blink, hair, ears, tail, and body physics.
- Keep 60 FPS as an acceptance target under game + OBS load; measure p95/p99 frame time, not just average FPS.

---

## 8. Gamer Brain: actual skill, not a game-themed chatbot

Research:
- https://gameworld-project.github.io/
- https://github.com/gym-anything/gym-anything-rt
- https://github.com/microsoft/KEEL-TTCL26
- https://github.com/unifyai/continual-arc

GameWorld describes 34 browser games and 170 tasks across runner, arcade, platformer, puzzle, and simulation genres. It evaluates serialized game state and distinguishes progress from successful completion. Its published results show that leading agents still have low task success rates in that benchmark. This is a warning against claiming human-level game skill from a few demonstrations.

### Three-rate controller

1. Fast control: short action horizons, movement, aiming, dodge/jump timing.
2. Perception: object tracking, HUD reading, scene changes, objective state.
3. Strategy: map planning, mechanics discovery, risk selection, skill selection.

The fast controller must be bounded by GameControlGate and must never reuse a stale frame permit.

### Learning cycle

1. Record game/version, map/seed, objective, controls, and initial state.
2. Attempt the task with a bounded action budget.
3. Record outcome evidence from game state or trusted completion signal.
4. Separate a failed strategy from an execution failure or perception failure.
5. Create a candidate skill with preconditions, steps, failure modes, and recovery.
6. Test on a held-out map/seed or unseen task.
7. Promote only when independent checks show repeatable improvement.
8. Retire a skill when the game patch or new evidence contradicts it.

### Evaluation

Measure:
- completion rate;
- time-to-completion;
- deaths/failures;
- unnecessary actions;
- recovery rate;
- performance on unseen seeds/maps;
- transfer to a different game with shared mechanics;
- action freshness rejection rate;
- owner override and emergency-stop latency.

Use paused/slowed game tests to diagnose reasoning quality, then live-speed tests to diagnose control latency. Do not merge the two results into one score.

---

## 9. Creator Brain: build, play, inspect, repair

Sources:
- https://create.roblox.com/docs/studio/mcp
- https://create.roblox.com/docs/reference/engine/classes/StudioTestService
- https://github.com/Roblox/open-game-eval
- https://github.com/seth-games/GameDevBench

The official Roblox Studio MCP server is built into Studio and exposes script reading/editing/search, Luau execution, DataModel exploration, generated animation/mesh/material/avatar tools, playtesting, screenshots, and simulated player input. This is a high-value integration because it operates on the actual open Studio session.

Recommended workflow:

1. Inspect the existing DataModel and project constraints.
2. Plan a bounded patch.
3. Apply edits through the reviewed Studio adapter.
4. Run static Luau analysis and formatting.
5. Start play mode.
6. Capture screenshots and runtime state.
7. Run scripted assertions.
8. Run multiplayer fixtures through StudioTestService.
9. Compare actual UI geometry and game state.
10. Repair only the failing component.
11. Re-run the same tests and independent holdouts.
12. Save a reproducible artifact and evidence bundle.

Keep separate acceptance categories:
- code correctness;
- gameplay behavior;
- visual quality;
- performance;
- security;
- multiplayer;
- asset/rights provenance.

A screenshot is not proof that the game works. A passing Luau type check is not proof that the multiplayer economy is secure. A Studio playtest agent is not the same as a consumer game being played through screen input.

### New feature opportunities

- automatic UI overlap and safe-area checking;
- camera and lighting regression captures;
- physics/rig/attachment inspection;
- animation loop and grip stability tests;
- network replication assertions;
- server-authoritative inventory/economy tests;
- map navigation and spawn safety checks;
- accessibility and localization checks;
- device-mode screenshots;
- automated regression place generation.

---

## 10. General knowledge and research intelligence

Separate factual knowledge from procedural skills.

### Factual knowledge record

Each retained fact should include:
- exact claim;
- source URL and source type;
- source publication/update date;
- retrieval date;
- subject/entity;
- scope and geographic/time context;
- confidence and uncertainty;
- contradictory evidence;
- expiry/recheck policy;
- owner approval when the fact is personal or sensitive.

### Procedural skill record

Each skill should include:
- task and preconditions;
- tool/version/environment;
- steps;
- expected output;
- verified evidence;
- known failure modes;
- recovery procedure;
- held-out transfer score;
- last validation date.

### Research workflow

- form a small set of falsifiable questions;
- search primary sources first;
- record source provenance;
- cross-check claims;
- distinguish evidence from inference;
- identify conflicts and stale documentation;
- produce a concise decision record;
- keep rejected hypotheses so STAR does not repeat failed experiments.

### Broad domains to add to the general knowledge evaluation

- math and logic;
- science and engineering;
- history and geography;
- language and writing;
- software and systems;
- economics and business;
- art, music, and design;
- health/safety information with strong abstention and source requirements;
- game mechanics and strategy;
- current events with explicit retrieval dates.

Do not measure general intelligence by a single trivia score. Use domain-stratified, source-grounded, correction, calibration, and multi-step task suites.

---

## 11. OBS, recording, and creator workflow

Source: https://github.com/obsproject/obs-websocket

OBS WebSocket 5.x uses a Hello → Identify → Identified handshake. Authentication is derived from the server challenge/salt when enabled. STAR must wait for Identified before requests, keep the socket on loopback by default, protect the password, and never log secrets.

Future Creator Studio workflow:
- owner selects a scene/profile and confirms recording;
- STAR observes scene/recording state;
- capture audio/video with explicit storage limits;
- generate a non-destructive edit decision list;
- attach source timestamps and media hashes;
- run transcript correction and scene-change detection;
- create horizontal and vertical draft cuts;
- generate captions and chapter markers;
- verify audio loudness, clipping, black frames, and subtitle safe areas;
- owner reviews story, rights, privacy, and final publication.

Never auto-publish a public video or stream just because an internal render succeeded. A reboot must not silently start a public stream.

---

## 12. Benchmark plan: one mixed-load truth set

Run the same deterministic test suite in four conditions:

| Profile | Active workloads |
|---|---|
| P0 | Text chat only |
| P1 | Voice conversation + avatar |
| P2 | Game + voice + avatar |
| P3 | Game + voice + avatar + OBS + live chat + bounded background research |

For every profile, record:
- machine/OS/driver/build;
- CPU/GPU/RAM/VRAM;
- exact model and quant hashes;
- model template, context, slots, and generation options;
- ASR/TTS versions and model hashes;
- game build, map/seed, and capture rate;
- OBS scene/profile and encoder;
- warm/cold status;
- run ID and fixture hash;
- p50/p95/p99 latency;
- task outcome and quality;
- dropped frames, underflows, and resource peaks.

Use at least 30 repeated short-turn samples for latency percentiles and multiple independent long sessions for stability. Keep a separate blind holdout for intelligence/skill quality. Compare identical hardware and fixed settings; report confidence intervals and failures, not just best runs.

### Hard release gates

- No audio callback regression or unexplained device underflow.
- No sustained audio queue growth.
- No avatar animation from cancelled/stale response generations.
- No game action from a stale observation or unapproved target.
- No model/tool request that bypasses host permissions.
- No silent external provider fallback.
- No sustained game/OBS frame-time regression beyond the agreed budget.
- No candidate skill promotion without held-out outcome evidence.
- No lost task obligation after interruption or restart.
- No public stream/publish action without explicit owner authorization.

---

## 13. Implementation sequence

### A. Finish the audio clock chain
- Reconcile freshness-first microphone queue and asynchronous speaker meter with DAC-time playback telemetry.
- Connect the snapshot through the lip-sync wrapper.
- Compare DAC estimate to WASAPI/loopback and OBS captured audio.
- Calibrate avatar timeline only after loopback evidence exists.

### B. Benchmark TTS
- Kokoro as the permissive compact baseline.
- VoXtream2.5 only in a non-commercial/rights-cleared test profile until the model license is resolved.
- Existing fallback as control.
- Compare CPU and GPU placement under game + OBS load.

### C. Benchmark ASR
- Faster-Whisper;
- Moonshine;
- sherpa-onnx;
- Kyutai streaming STT on a separately budgeted host.

### D. Complete resource runtime
- Add a trusted Windows sampler.
- Convert real measurements to conservative host budgets.
- Bind leases to process identity and cancellation tokens.
- Confirm worker exit before releasing resources.
- Add watchdog and restart recovery.
- Keep the policy module independent of process execution.

### E. Complete streaming adapters
- Twitch EventSub and YouTube Live Chat read-only pilots.
- Normalize provider IDs/timestamps.
- Apply moderation, dedupe, queue limits, and source consent.
- Add owner mute/stop and reconnect tests.

### F. Complete game execution
- DXGI capture adapter;
- bounded frame pipeline;
- permitted input adapter;
- manual input detection and immediate override;
- real game fixtures;
- held-out skill transfer.

### G. Complete Creator Studio
- Roblox Studio MCP adapter;
- StudioTestService multiplayer fixtures;
- visual/gameplay evaluation;
- non-destructive recording/edit workflow;
- owner art and voice approval.

### H. Complete broad knowledge
- factual claim ledger;
- procedural skill store;
- source-grounded retrieval;
- correction and abstention evaluation;
- periodic revalidation.

---

## 14. Research sources and what they contribute

| Source | Contribution | STAR disposition |
|---|---|---|
| VoXtream2.5 — https://github.com/herimor/voxtream | Full-stream TTS, dynamic speaking rate, CPU GGUF path | Benchmark; weights are CC-BY-NC-4.0 |
| Kokoro — https://github.com/hexgrad/kokoro | Compact 82M Apache-licensed TTS baseline | Benchmark |
| Kyutai DSM — https://github.com/kyutai-labs/delayed-streams-modeling | Streaming STT/TTS and word timestamps | Remote/server candidate |
| Moshi — https://github.com/kyutai-labs/moshi | Full-duplex audio architecture | Research reference; too heavy for default 8 GB local path |
| llama.cpp — https://github.com/ggml-org/llama.cpp | Continuous batching, monitoring, tool calls, speculative decoding | Existing local inference foundation |
| OpenTelemetry GenAI — https://github.com/open-telemetry/semantic-conventions-genai | Traces/metrics for LLM, MCP, tools | Pin reviewed convention revision |
| GameWorld — https://gameworld-project.github.io/ | Outcome-verified multimodal game agent evaluation | Game Lab evaluation candidate |
| Roblox Studio MCP — https://create.roblox.com/docs/studio/mcp | Actual Studio editing, inspection, playtest, screenshot, and generation tools | High-priority reviewed adapter |
| Roblox StudioTestService — https://create.roblox.com/docs/reference/engine/classes/StudioTestService | Multiplayer test automation | Creator acceptance |
| OBS WebSocket — https://github.com/obsproject/obs-websocket | Authenticated OBS RPC/events | Owner-authorized local adapter |
| KEEL-TTCL26 — https://github.com/microsoft/KEEL-TTCL26 | Verifier-backed skill evolution | Research candidate |
| Continual-ARC — https://github.com/unifyai/continual-arc | Held-out continual learning evaluation | Research candidate |

---

## 15. Explicit non-goals for this run

- No TTS/ASR model installed or enabled.
- No model weights trained or modified.
- No automatic cloud routing.
- No OBS or streaming credentials stored.
- No Twitch/YouTube OAuth connection.
- No public stream or video published.
- No Roblox place edited or published.
- No anti-cheat bypass or game-memory manipulation.
- No claim of human-level gaming, general intelligence, or human consciousness.
- No claim of physical audio or avatar acceptance.

The next success criterion is a measured Windows mixed-load rehearsal, not another feature count.
