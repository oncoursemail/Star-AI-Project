# STAR Run 26 — Runtime Bottlenecks, Cache Stability, and Integration-First Capability Plan

**Research date:** 2026-11-14  
**Repository:** `oncoursemail/Star-AI-Project`  
**Research branch:** `research/star-run24-integration-blueprint-20261114`  
**Related drafts:** #1178, #1180, #1151, #1167, #1166, #1140, #1142, #1143, #1152, #1153  
**Scope:** source-grounded runtime audit and implementation priorities for fast local inference, continuous VTuber interaction, transferable game skills, creator workflows, and general-purpose research.

---

## Executive decision

STAR's next major improvement should be an **integration and bottleneck-removal pass**, not another collection of disconnected feature prototypes.

The repository already contains draft work for resource admission, stream-pressure control, inference measurement, paired quality evaluation, voice playback timing, trusted OBS telemetry, multiparty room control, and task/communication persistence. The most valuable work is to make those systems compose on one runtime path and verify that the result remains responsive under simultaneous streaming, gameplay, and background work.

This run adds one evidence-grounded integration plan. It does not claim a runtime speedup, install a model, change production defaults, or merge any draft PR.

### Five decisions

1. Keep one resource-admission authority and one task ledger. Compose new behavior through #1140/#1142 and #1177 rather than adding parallel schedulers or databases.
2. Treat real-time audio callbacks as deadline-sensitive transport only. Move analysis, metering, logging, and expensive conversions to bounded worker queues.
3. Budget inference by **resident KV working set and active session state**, not just request count or total RAM.
4. Measure the whole audience experience—from capture to audible playback and avatar synchronization—while separately measuring task correctness and game frame-time.
5. Promote game and creator skills only after external verification and held-out transfer, not because the model says it succeeded.

---

## 1. New inference-serving risk: cache collapse after a short burst

### 1.1 Bursts That Outlast Themselves (2026-11-10)

The November 10 preprint *Bursts That Outlast Themselves: Persistent Degradation in Prefix-Cached Agent Serving* describes a feedback loop in agent-serving systems:

- More arrivals increase active sessions.
- More active sessions enlarge the resident KV working set.
- Prefix-cache hit rate falls.
- Requests must recompute long contexts.
- Slower requests remain active longer.
- The queue and working set grow further.

In the authors' vLLM experiments, a short arrival burst drove the cache-hit ratio to roughly 10% and throughput to about half of the healthy comparison for the remaining observation window. The study reports that admission throttling alone often failed to recover the collapsed runs, while suspending admitted sessions under a resident-KV capacity budget recovered all tested collapsed runs. The authors also report a similar phenomenon with SGLang.

**Interpretation for STAR:** this is a serious risk hypothesis for long-running agent sessions, not proof that STAR's llama.cpp configuration has the same failure. The paper's tested serving stacks and workload are not identical to STAR's local runtime.

Source: https://arxiv.org/abs/2611.13412

### 1.2 KVSET: estimate the working set instead of guessing cache size

The September 2026 KVSET paper applies Mattson stack-distance analysis to estimate hit-rate curves for different cache capacities from a prefix-page reference trace. Its useful idea is to determine the smallest cache capacity that meets a target hit rate, instead of retaining every historical prefix or selecting a cache size by intuition.

Source: https://arxiv.org/abs/2609.27746

**STAR application:**

- Record content-free cache and session events where the backend exposes them.
- Build offline replay traces from request-prefix identities or backend cache-page identifiers; never log raw prompts or private conversation text.
- Estimate the working-set curve for interactive, research, and coding workloads separately.
- Compare estimated hit rates with backend-reported prompt-cache reuse.
- Do not claim KVSET accuracy for llama.cpp until its cache behavior and trace granularity are shown to satisfy the analyzer's assumptions.

KVSET is an analysis candidate, not a reason to add a new cache tier immediately.

### 1.3 llama.cpp-specific caution

The current llama.cpp server documentation exposes useful controls and measurements, including `cache_prompt`, `timings_per_token`, prompt-processing progress, parallel slots, and speculative decoding. Prefix reuse primarily saves repeated prompt prefill; it does not automatically make decode tokens per second faster.

The upstream issue tracker also contains recent reports of prompt-cache/slot interactions and blocking work during idle-slot saves under particular configurations. These are issue reports, not proof that every build or STAR configuration is affected. They are sufficient reason to pin and test the exact llama.cpp commit and concurrency configuration before changing defaults.

Sources:
- https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md
- https://github.com/ggml-org/llama.cpp/issues/22942
- https://github.com/ggml-org/llama.cpp/issues/30252
- https://github.com/ggml-org/llama.cpp/issues/30961

**Decision:** preserve the current backend defaults until paired measurements exist. Do not increase parallel slots, context size, or cache retention based on a single isolated benchmark.

---

## 2. Repository audit: a concrete voice integration gap

I inspected the current source on two separate development trains:

- PR #1178 head branch: `feat/resource-admission-20261113-run21`
- PR #1151 head branch: `feat/voice-playback-clock-and-validation-fix-20261112`

### 2.1 What is present on #1178

In `star/voice/devices.py`, `SoundSpeaker` preloads NumPy during construction, which avoids a cold module import on the PortAudio callback. However, `SoundSpeaker._callback` still performs:

- `np.frombuffer(...)`
- float-array conversion with `astype`
- an RMS reduction
- a write to the shared level-history deque

Those operations are not needed to deliver PCM to the device. They still consume work on the high-priority callback and create avoidable deadline pressure.

### 2.2 What is already implemented on #1151

The separate #1151 branch moves RMS analysis to a bounded asynchronous meter worker. The callback hands off bounded best-effort samples; telemetry drops do not alter the PCM delivered to the audio device. That branch also contains playback-clock telemetry.

This is a useful implementation to integrate, but #1151 and #1178 are on different stacked dependency trains. The #1151 version imports the playback telemetry module and changes additional behavior. Copying the file wholesale into #1178 without reconciling its dependencies would be unsafe.

### 2.3 Required integration action

When the dependency trains are reconciled:

1. Keep callback responsibilities limited to copying the next PCM block, filling the device output buffer, updating minimal counters, and performing a non-blocking bounded handoff.
2. Compute RMS/echo meter values on a worker thread.
3. Keep telemetry best-effort: a full meter queue may drop a meter sample but must never drop or modify outgoing PCM.
4. If meter data is pending, dropped, stale, or failed, treat the echo state conservatively as audible rather than falsely declaring silence.
5. Drain or explicitly abandon the bounded meter queue on shutdown; never block device shutdown indefinitely.
6. Preserve playback timestamps as separate stages: TTS generated, queued, callback scheduled, estimated DAC playback, and acknowledged delivery.

**Do not create another audio-meter implementation.** Reconcile #1151's tested worker design with #1178's room/stream integration and preserve the existing test coverage.

This is the clearest source-level integration gap found in this audit.

---

## 3. Speed engineering: optimize the correct latency component

A single "response speed" number hides several different bottlenecks. STAR should maintain a stage-level latency model:

| Stage | Metric | Typical cause when slow |
|---|---|---|
| Audio capture | frame age / queue delay | device or capture backlog |
| Endpointing | pause-to-final-turn | VAD / turn detector thresholds |
| ASR | first committed text and final transcript | model size, repeated re-transcription |
| Inference prefill | prompt tokens/sec and time-to-first-token | long or changing prompt prefix |
| Inference decode | inter-token latency and output tokens/sec | model compute, memory bandwidth, contention |
| Sentence boundary | first speakable sentence | verbose response shape or chunker |
| TTS | first audio chunk and synthesis RTF | voice model, chunk size, warmup |
| Playback | queue-to-DAC estimate and underruns | callback work, queue depth, device |
| Avatar | audio-to-mouth offset and stale-frame age | transport cadence and parameter scheduling |
| Broadcast | OBS render/output skips and encoder lag | GPU contention or capture/encoding load |

### 3.1 Prompt-prefix stability

Keep stable system and persona instructions at the beginning of the prompt. Put volatile stream state, timestamps, viewer messages, and task-specific context after the stable prefix. Do not inject changing values into the prefix simply for convenience.

This improves the opportunity for prefix reuse. It must be verified using the backend's own prompt-cache/timing telemetry.

### 3.2 Speculative decoding

llama.cpp supports draft-model and n-gram-cache speculative decoding. The target model verifies proposed tokens in batches. It can improve decode throughput when enough draft tokens are accepted, but draft inference itself consumes CPU, RAM, and possibly GPU resources.

For STAR's 8 GB GPU class, a second model can compete with the target model, game rendering, or avatar pipeline. Therefore:

- Benchmark target-only, n-gram, and small-draft configurations separately.
- Measure first-token latency, inter-token latency, output tokens/sec, CPU, RAM, VRAM, game FPS p10, audio underruns, and OBS skips.
- Run the same prompts and concurrency levels with warm and cold caches.
- Promote only if the paired evaluator finds a real net win without violating stream-quality guardrails.
- Keep speculative decoding disabled by default until this is demonstrated on the target machine.

### 3.3 Context control is an intelligence improvement too

Longer context is not automatically better. Use task-specific retrieval, compact state summaries, evidence references, and versioned memory. Preserve the raw source where retention is appropriate, but do not resend every past observation to every model call.

The memory system should retrieve:
- the current task state;
- relevant prior decisions;
- evidence-backed facts;
- verified procedural skills;
- unresolved uncertainties;
- recent changes that could invalidate old results.

This reduces prefill cost while making the active context more relevant.

---

## 4. Full-duplex VTuber: optimize what the audience actually hears

### 4.1 Full-Duplex-Bench v3

The benchmark uses natural human speech with disfluencies and chained tool-use tasks. Its reported results show why a voice agent cannot be judged by latency alone: task success, tool selection, argument accuracy, response quality, interruption behavior, and latency are separate outcomes.

On the benchmark page's November 2026 snapshot, the reported GPT-Realtime configuration has 60% task success and 6.89-second task latency; Gemini Live 3.1 has 54% task success and 4.25-second latency. These are benchmark-specific results from different model configurations, not a direct prediction of STAR performance.

Source: https://www.fullduplex.ai/benchmarks/fdb-v3

### 4.2 Realtime-Venus: two loops, one conversation

Realtime-Venus describes a live perception/speech loop alongside a delegated background-task loop. It preserves the context of a request, lets delegated work continue while interaction remains live, and returns prepared results to the same conversation. Its frontend controls when to speak and tracks playback.

Source: https://realtime-venus.github.io/

**STAR design:**

- Foreground loop: ASR, floor control, immediate response, TTS, avatar, game control.
- Background loop: research, long reasoning, skill practice, code generation, creator playtests.
- Shared host-owned event/session identity and monotonic clock.
- Bounded queues with explicit priority and expiry.
- A task generation/version fences stale results.
- A background result is not spoken until the Social Director confirms it is still relevant and playback is available.
- The host—not the language model—owns whether STAR has the floor.

### 4.3 Human-like streaming without deceptive behavior

The target is believable timing and socially appropriate behavior, not pretending to be a human.

STAR should:
- respond to direct questions without narrating every frame;
- recognize when viewers are talking to one another;
- use brief acknowledgements when useful;
- tolerate natural silence;
- avoid repeating a question that another person has already resolved;
- recover gracefully from interruptions;
- vary phrasing without forced catchphrases;
- use humor and excitement proportionate to actual events;
- express character emotion as an AI character, without claiming human lived experience;
- remain transparent that she is an AI.

Evaluate long sessions, not only isolated prompt samples. Track false interruptions, missed opportunities, repeated answers, wrong-addressee responses, grounding over 20+ turns, and the rate of unnecessary narration.

---

## 5. Gamer Brain: fast control plus slow strategy

### 5.1 Two-rate design

Do not ask a large vision-language model to reason from scratch on every frame.

**Reactive controller**
- consumes compact observations at the rate required by the game;
- handles movement, camera, aiming, dodging, jumping, and immediate interaction;
- uses bounded action durations and a hard stop path;
- reports state changes and failures to the planner.

**Strategic planner**
- interprets objectives and mechanics;
- selects subgoals;
- decides when to explore or change tactics;
- requests new observations when the state is ambiguous;
- reviews outcomes and proposes reusable skills.

The exact control frequency should be measured per game. A fixed 10 Hz or 30 Hz target is not universally appropriate.

### 5.2 Learn by verified skill, not narrative memory

Use a skill lifecycle:

1. Observe a task and its initial state.
2. Form a small, testable hypothesis.
3. Practice in a sandbox or explicitly approved environment.
4. Record the action sequence and state transitions.
5. Verify success using environment state, not model self-report.
6. Save a versioned skill with game/version/preconditions.
7. Test on held-out maps or changed starting conditions.
8. Retire or revise the skill when it fails.

A skill should include:
- name and version;
- game and build identifier;
- preconditions;
- required observations;
- action schema;
- expected postconditions;
- known failure states;
- evidence and test results;
- confidence and expiry/revalidation policy.

### 5.3 Evaluation sources

- **GameWorld**: 34 browser games and 170 tasks with state-verifiable outcomes; includes real-time interaction and memory-sensitivity investigations. https://arxiv.org/abs/2604.07429
- **OmniGameArena**: 12 Unreal Engine 5 games / 60 maps, including solo, PvP, and co-op, with improvement curves and held-out variants. https://arxiv.org/abs/2606.09826
- **Voyager**: an open-ended Minecraft agent with automatic curriculum, executable skill library, environment feedback, and transfer to a new world. https://github.com/caixianzhou/voyager
- **SIMA 2**: DeepMind's research agent combines visual understanding, language instructions, and actions in 3D worlds; its held-out-game and generated-world demonstrations are useful architectural references, not a drop-in local package. https://deepmind.google/blog/sima-2-an-agent-that-plays-reasons-and-learns-with-you-in-virtual-3d-worlds/

For STAR, pair generic game benchmarks with Roblox-specific Studio/Play-mode tests. Do not infer Roblox proficiency from Minecraft or browser-game scores.

---

## 6. Creator Brain: the visual verification loop

GameDevBench evaluates 333 Godot game-development tasks across 2D graphics/animation, 3D graphics/animation, UI, and gameplay logic. The authors show that visual feedback can materially improve agent task success; their reported GPT-5.4 result increased from 41.1% to 52.0% with visual feedback in the tested setup.

Source: https://github.com/waynchi/gamedevbench

**STAR Creator loop:**

`Inspect → Plan → Edit → Build → Run → Capture → Compare → Repair → Verify`

A generated script is not a finished feature. The creator should verify:
- compilation and static analysis;
- object hierarchy and references;
- UI layout at target resolutions;
- animation and VFX timing;
- asset/material correctness;
- client/server behavior;
- runtime errors;
- gameplay postconditions;
- performance on representative hardware.

For Roblox, inspect the DataModel and existing scripts before editing, use Luau analysis/linting, run in Studio Play mode, and verify the actual resulting state. For Godot/Unity, use engine-native import/build/run and screenshot/video feedback. For Blender, verify scene objects, materials, rigs, animation playback, and export artifacts.

---

## 7. General-knowledge research workbench

STAR should distinguish **retrieval**, **reasoning**, **tool execution**, and **verified completion**.

For every consequential factual answer, retain a compact evidence record:
- claim;
- source URL and publisher;
- publication/update date;
- retrieval timestamp;
- quoted or extracted support span;
- source reliability class;
- corroborating or contradictory sources;
- freshness requirement;
- confidence and unresolved uncertainty.

Research flow:

1. Convert the request into explicit questions.
2. Search for primary sources first.
3. Follow references for hard-to-find claims.
4. Extract claim-level evidence.
5. Compare independent sources.
6. identify disagreement and outdated information.
7. Use tools or experiments where a claim can be tested.
8. Answer with calibrated uncertainty and source links.
9. Store reusable findings as versioned knowledge, not unbounded transcript text.

Build domain skills for software, game engines, math, science, history, art, audio, video, hardware, and everyday research. Each domain skill should include source quality rules and a test set appropriate to that domain.

---

## 8. VTuber and broadcast integration contracts

### VTube Studio

The official API uses a local WebSocket server and an explicit plugin-authentication/permission flow. The user must approve plugin access; the application should expose a configurable port and handle revocation/reconnection.

Sources:
- https://github.com/DenchiSoft/VTubeStudio
- https://github.com/DenchiSoft/VTubeStudio/wiki/Plugins

### OBS

OBS WebSocket is included with OBS Studio 28+ and supports remote control. Protect it with a password; do not expose the control socket to the public internet.

Source: https://github.com/obsproject/obs-websocket

### STAR adapter requirements

- Keep OBS and VTube Studio adapters behind explicit local configuration and consent.
- Bind every request to a session generation and request ID.
- Validate response IDs and event sequence.
- Reconnect with bounded exponential backoff.
- Treat missing telemetry as unknown, not zero.
- Never let avatar telemetry or a failed OBS connection block audio playback.
- Use playback acknowledgements for mouth movement and response-delivery state.
- Separate render-thread skips from output-thread skips.
- Keep stream control and audience-facing chat permissions separate.

---

## 9. Unified acceptance matrix

Run all lanes simultaneously after isolated tests pass.

| Lane | Primary metrics | Hard regression examples |
|---|---|---|
| Voice capture | frame age, queue drops, endpointing p95 | audio backlog grows without bound |
| ASR | first committed text, final WER, correction rate | provisional transcript triggers tools |
| Inference | TTFT, inter-token p50/p95, tokens/sec, prefill reuse | faster output with worse task success |
| TTS/playback | first-audio, queue-to-DAC, underruns | callback telemetry delays PCM |
| Social | false interruption, missed turn, wrong addressee, repeated answer | STAR speaks over a resolved conversation |
| Avatar | mouth/audio offset, stale frame age | avatar speaks before audio or after stop |
| Gamer | objective success, action validity, FPS p10/p99 | model blocks real-time control |
| Creator | build pass, visual pass, runtime assertions | code compiles but scene is broken |
| Memory | retrieval precision, stale-memory rejection, held-out transfer | old skill overrides newer evidence |
| Broadcast | OBS render/output skips, encoder lag, reconnect time | background work destabilizes stream |

Use paired trials on the same model, machine, game build, prompt, and task roster. Report p50/p95/p99 and sample counts. Use a sealed holdout for promotion. Do not use the same adaptive test cases repeatedly to tune a threshold and then report them as independent validation.

### Mixed-load scenarios

1. STAR is speaking while a viewer interrupts.
2. STAR is playing a game while chat activity spikes.
3. A background research task starts during a game scene transition.
4. A creator build runs while OBS and the avatar are active.
5. The inference cache is warm, then receives a burst of new sessions.
6. The model server restarts while the foreground stream remains active.
7. VTube Studio disconnects and reconnects while TTS continues.
8. A task is cancelled or revised while its worker is still running.
9. A stale background result arrives after a newer request.
10. Audio meter telemetry overflows while PCM playback continues.

---

## 10. Ordered implementation plan

### P0 — Reconcile existing branches
- Map dependency ancestry for #1140/#1142, #1151, #1166/#1167, and #1171–#1178.
- Identify duplicated files and incompatible parent revisions.
- Integrate #1151's asynchronous audio meter/playback telemetry into the multiparty voice train through an explicit reviewed merge or rebase.
- Run exact-head CI after every dependency-changing integration.
- Keep #1180 as a documentation-only research train; do not merge it into a code stack simply to share notes.

### P1 — Protect the real-time path
- Remove NumPy/RMS analysis from PortAudio callbacks.
- Bound all audio, avatar, chat, and observation queues.
- Preserve freshness for live audio and game observations.
- Keep telemetry best-effort and content-free.
- Test shutdown, overflow, device errors, and callback timing with fakes before hardware tests.

### P2 — Calibrate mixed-load scheduling
- Reuse #1140/#1142 as the single resource-admission path.
- Measure process-scoped CPU/RAM and trustworthy VRAM.
- Include game FPS p10, audio underruns, OBS skips, and queue age in host health.
- Add resident-KV working-set estimates and a capacity-aware session budget.
- Suspend or checkpoint low-priority background sessions before foreground responsiveness degrades; do not silently starve or kill foreground work.
- Recover with hysteresis and verify that the cache hit rate and queue actually recover.

### P3 — Finish end-to-end streaming
- Incremental ASR with explicit partial/committed/final/correction events.
- Full-duplex floor control and multiparty addressee estimation.
- Streaming TTS and exact playback acknowledgement.
- Audio-synchronized avatar updates.
- Local OBS/VTube Studio adapters with consent and authenticated transport.
- Long-session rehearsals and audience-simulation evaluation.

### P4 — Make game and creator skills transferable
- Start with one instrumented game and a small set of deterministic tasks.
- Add observation/action adapters and state-verifiable outcomes.
- Add a versioned skill bank with preconditions and held-out transfer tests.
- Add visual feedback to the creator loop.
- Expand to Roblox, Minecraft, Godot, Unity, and Blender only after each adapter has its own acceptance suite.

### P5 — Expand general knowledge and autonomy
- Claim-level evidence graph and freshness policy.
- Domain-specific retrieval skills.
- Safe background research and project planning.
- Task-generation fencing, cancellation, checkpoints, and evidence-linked delivery.
- Owner approval for irreversible, external, financial, account, or public actions.

---

## 11. Security, privacy, and trust boundaries

- Viewer messages, chat, game text, screenshots, and web pages are untrusted input, never tool authorization.
- Keep speaker IDs opaque and session-scoped.
- Do not create persistent viewer identity or voiceprint profiles by default.
- Do not retain raw viewer audio or private chat longer than needed for the explicitly enabled feature.
- Keep API tokens in the OS credential store; never place secrets in prompts, logs, source files, or GitHub artifacts.
- Keep OBS/VTube Studio sockets local and authenticated.
- Require owner approval for public posts, purchases, account changes, irreversible file operations, and other consequential external actions.
- Treat executable game skills as untrusted code: sandbox, resource-limit, version, test, and revoke them.
- Do not claim human identity, human experiences, or perception that the runtime has not supplied.

---

## 12. Source register

| Source | Date / status | STAR use |
|---|---|---|
| Bursts That Outlast Themselves, arXiv:2611.13412 | 2026-11-10 preprint | Cache-collapse and session-budget risk |
| KVSET, arXiv:2609.27746 | 2026-09-23 preprint | Offline/online cache working-set analysis |
| llama.cpp server documentation | Rolling upstream docs | Prompt reuse, timing, concurrency, speculative decoding |
| llama.cpp issues #22942, #30252, #30961 | Upstream issue reports | Pin exact backend build and regression-test cache behavior |
| Full-Duplex-Bench v3 | 2026-05 benchmark release; 2026-11 snapshot | Natural speech, disfluency, tool accuracy, latency |
| Realtime-Venus | 2026 research project | Live interaction plus asynchronous delegation |
| GameWorld, arXiv:2604.07429 | 2026-04-08 | Verifiable general game-agent evaluation |
| OmniGameArena, arXiv:2606.09826 | 2026-06-08 | Learning curves, PvP/co-op, held-out game variants |
| GameDevBench | ICML 2026 | Multimodal game-development tasks and visual feedback |
| Voyager, arXiv:2305.16291 | TMLR 2024 | Executable skill library and continual game learning |
| SIMA 2 | DeepMind research announcement | Visual instruction following and generalization in 3D worlds |
| VTube Studio API | Rolling official docs | Consented local Live2D control |
| OBS WebSocket | Rolling official docs | Authenticated local broadcast control |

No benchmark dataset or model weight is redistributed by this document. Review each project's license and dataset terms before integrating code, models, or data into STAR or a commercial distribution.

---

## Explicit scope and limitations

- This is a research and integration-plan commit only.
- No runtime module, model weight, package, provider, API credential, model default, cache flag, permission, installer, or production release setting is changed.
- No benchmark dataset is downloaded or redistributed.
- The cache-collapse paper is a preprint and its findings are not assumed to reproduce on STAR's exact llama.cpp build.
- Upstream llama.cpp issue reports are configuration-specific reports, not a universal claim about every release.
- No physical RTX 4060, microphone, audio loopback, OBS, VTube Studio, Roblox Studio, Godot, Unity, Minecraft, or livestream acceptance test was run.
- No speedup, intelligence gain, game mastery, human-equivalence, or production readiness is claimed.
- The shared `docs/FRONTIER_SOURCES.json` is intentionally untouched because multiple draft trains update it; this document carries its own source register.
- Keep PR #1180 draft and unmerged pending review and exact integration work.
