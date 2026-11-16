# STAR Run 59 — Reliability-First Streaming, Gameplay, Learning, and Inference

**Research date:** 2026-11-15  
**Implementation:** additive voice-turn percentile summary  
**Status:** draft research and offline instrumentation; exact-head CI required

## Executive decision

STAR already has unusually useful foundations for this scope: a cancellable voice-call pipeline, per-turn stage timestamps, an inference benchmark, a dry-run resource planner, conversation memory with source digests, a game-action freshness gate under development, game and Roblox evaluations, OBS telemetry work, and versioned skill contracts.

The highest-value gap is not another agent, database, scheduler, or persona prompt. It is **reliability under repeated, concurrent, real-time use**.

A capable run is not enough. STAR must repeatedly complete the same class of task while:
- speaking without cutting people off;
- preserving the current game-control deadline;
- keeping audio and avatar output synchronized;
- remembering the correct context without flooding the prompt;
- avoiding regressions from newly learned skills;
- protecting the interactive workload from background research and training;
- reporting failures honestly.

Run 59 adds an additive, offline latency_summary() to the existing voice metrics module. It reports nearest-rank p50/p95/p99 per stage, sample counts, incomplete-turn counts, interruption/error rates, and explicit minimum sample guidance. It does not change voice behavior or introduce a new runtime authority.

## 1. Research findings and STAR decisions

### 1.1 Skill learning needs external feedback and negative-transfer tests

**SkillLearnBench** (Zhong et al., 2026-04-22) evaluates continual skill generation on 20 verified skill-dependent tasks across 15 subdomains. It scores skill quality, execution trajectories, and task outcomes. The paper reports that no evaluated method wins consistently across all tasks and models; stronger base models do not automatically produce better skills. Iterative external feedback helped, while self-feedback alone could create recursive drift.

STAR decision:
- Keep candidate skills separate from trusted skills.
- Compare skill-off and skill-on using the same initial states and task roster.
- Use independent task oracles and external execution feedback.
- Measure task success, behavior coverage, time, token/tool cost, recovery, transfer, and negative transfer.
- Never let the candidate skill author modify the grader or see sealed holdout answers.
- Do not auto-promote because a skill was used frequently or because its author says it improved.

Source: https://arxiv.org/abs/2604.20087

### 1.2 Computer-use agents must be evaluated for repeatability, not lucky success

**On the Reliability of Computer Use Agents** (Gonzalez-Pumariega et al., 2026-04-20) studies why an agent can succeed once and fail on a repeated execution of the same task. It analyzes execution stochasticity, task ambiguity, and behavioral variability, and advocates repeated-run evaluation with paired comparisons.

STAR decision:
- Report per-task repeatability, not only aggregate pass rate or pass@k.
- Repeat the same task from the same reset state with controlled seeds and environment versions.
- Record whether failure came from ambiguous instructions, stale observations, a changed UI, action timing, or planning variance.
- Let STAR resolve genuine ambiguity through a bounded observation step before an irreversible action.
- Prefer stable, verified action sequences over one lucky success.
- Test idempotency and recovery after application restarts, dropped connections, and partial completion.

A practical acceptance report should include pass^k (all k repeats pass), per-task success variance, recovery rate, and paired task-level deltas. Do not compare unrelated task sets as if they were paired.

Source: https://arxiv.org/abs/2604.17849

### 1.3 Multiparty conversation is a separate capability from single-user voice chat

**MP-Bench** (Findings of EMNLP 2026) evaluates voice agents as active participants in multi-party conversations. It measures turn-taking awareness, response appropriateness, and comprehension. The authors report that the evaluated real-time agents remained at or below 22% on multiparty comprehension and near chance on multiparty turn-taking.

STAR decision:
- Speaker recognition and addressee resolution must be distinct from speech transcription.
- Track who is speaking, who is being addressed, whether the utterance is a reply, and whether another participant currently owns the floor.
- Do not answer every detected voice or every chat message.
- Use explicit priority classes: direct question to STAR, safety/moderation event, urgent game event, group conversation, low-priority chat.
- Permit backchannels and silence; do not optimize for continuous speech.
- Evaluate overlapping speakers, crosstalk, names, short acknowledgements, jokes, sarcasm, and topic shifts separately.

Source: https://aclanthology.org/2026.findings-emnlp.1437/

### 1.4 Turn detection, interruption, preemptive generation, and audio cleanup are different stages

LiveKit's current turn-taking documentation separates user activity/end-of-turn detection, interruption handling, preemptive generation, and audio preprocessing. It also documents adaptive interruption handling, false-interruption recovery, and the difference between server-side realtime turn detection and client-side turn control.

STAR decision:
- Keep the existing star/voice/turn.py as the deterministic turn-state boundary.
- Keep the brain request cancellable and stop queued audio on a genuine barge-in.
- Do not conflate endpointing delay with model time-to-first-token or TTS time-to-first-audio.
- Measure false cutoffs, missed interruptions, interruption-to-silence latency, and stale response cancellation separately.
- Preemptive generation is a speculative optimization: discard its result if the user continues, changes topic, or interrupts.
- For a multi-speaker room, prefer background-noise suppression over isolating only one speaker.

Sources:
- https://docs.livekit.io/agents/logic/turns/
- https://docs.livekit.io/agents/logic/turns/tuning/
- https://github.com/livekit/eot-bench

### 1.5 VTube Studio parameter injection requires ownership and freshness

The official VTube Studio API documents parameter injection, custom parameters, expression state, and plugin authentication. API-injected values need to be refreshed at least once per second to remain active; only one plugin can set/override a parameter at a time, although additive mode is available for compatible effects.

STAR decision:
- Use one trusted avatar-parameter arbiter as the only writer for each parameter.
- Merge face tracking, emotion, lip-sync, gaze, idle motion, and game reactions before sending a frame.
- Apply per-parameter ownership and priority; do not let two subsystems race to set the same parameter.
- Send the latest state, not a backlog of stale animation frames.
- Expire transient expressions and return parameters to neutral on cancellation, disconnect, or shutdown.
- Keep model-specific parameter IDs and ranges in a validated profile; never assume all Live2D models share the same rig.

Sources:
- https://github.com/DenchiSoft/VTubeStudio
- https://github.com/DenchiSoft/VTubeStudio/wiki/Expressions-%28a.k.a.-Stickers-or-Emotes%29

### 1.6 OBS automation is powerful and must remain local and authenticated

The official OBS WebSocket project is included with OBS 28.0 and later. Its documentation recommends protecting the server with a password. The protocol can control scenes and sources and expose events.

STAR decision:
- Keep OBS connection restricted to loopback by default.
- Require explicit user setup and authentication.
- Do not allow model-generated host/port/password values.
- Separate read-only telemetry from scene/recording mutations.
- Keep a visible manual stop/override.
- On disconnect, stop issuing actions and preserve the user's current recording/stream state.
- Record content-free counters by default; do not persist viewer audio/video or chat bodies as telemetry.

Source: https://github.com/obsproject/obs-websocket

### 1.7 Game mastery needs state-verifiable outcomes and a real-time track

**GameWorld** (2026-04-08) provides 34 browser games and 170 tasks with verifiable outcome metrics. It studies direct keyboard/mouse control and semantic action parsing, and identifies latency, sparse feedback, invalid actions, and context-memory sensitivity as important challenges.

STAR decision:
- Use a fast bounded controller for movement, aim, camera, jump, dodge, and menu navigation.
- Use a slower strategic planner for objectives, routes, resource use, enemy patterns, and learning between attempts.
- Keep the fast controller deterministic where possible; do not invoke a large reasoning model for every input frame.
- Every action must be grounded in a fresh observation with a known coordinate/window/game-state version.
- Verify wins, pickups, objective changes, deaths, and checkpoint completion from environment state when available.
- Keep practice and holdout maps/seeds separate; never report progress percentage as a win.

Source: https://arxiv.org/abs/2604.07429  
Project: https://gameworld-bench.github.io/

### 1.8 Game creation requires visual and runtime feedback, not code-only grading

**GameDevBench** (ICML 2026) contains 333 multimodal game-development tasks across 2D/3D graphics and animation, UI, and gameplay. Its reported experiments show that visual feedback can improve evaluated creation performance.

STAR decision:
- Keep separate scores for code correctness, scene structure, visual quality, gameplay behavior, and performance.
- The creator loop is inspect → plan → edit → run → capture → compare → playtest → repair → verify.
- Preserve screenshots/video and test outputs as evidence linked to the exact project revision.
- For Roblox, retain Luau analysis, DataModel inspection, server/client security checks, TestService, multiplayer tests, and real Studio acceptance.
- For other engines, pin the engine version, project settings, renderer, assets, and import pipeline.

Source: https://github.com/waynchi/gamedevbench

### 1.9 Speculative decoding must be load-aware

**An Interpretable Latency Model for Speculative Decoding in LLM Serving** (2026-05-14) models drafting, verification, acceptance probability, and load-dependent latency. It explains why isolated or fixed-batch speedups may diminish as production request load changes.

STAR decision:
- Keep the existing capability-gated speculative-decoding canary.
- Measure acceptance rate and end-to-end latency under the actual request arrival pattern.
- Test the interactive single-user case separately from concurrent background work.
- Disable speculation when draft overhead, VRAM pressure, or verification cost worsens p95/p99.
- Compare the same prompt set, output limits, slot count, model revisions, and warm/cold cache states.
- Do not infer RTX 4060 performance from another GPU's paper result.

Sources:
- https://arxiv.org/abs/2605.15051
- https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench

## 2. Repository architecture audit and reuse map

Run 59 intentionally reuses existing components:

| Existing path / work | Run 59 use |
|---|---|
| star/voice/turn.py | Deterministic turn/end/interruption state |
| star/voice/call.py | Cancellable brain/TTS/speaker pipeline |
| star/voice/metrics.py | Per-turn timing and new tail summary |
| star/voice/bridge.py | Desktop voice actions and event contract |
| docs/STAR_VOICE_CALLS.md | Existing measured voice pipeline and test boundaries |
| star/brain_router.py | Deterministic, zero-extra-inference model routing |
| star/inference_benchmark.py | Local endpoint measurement |
| star/agent_resource_planner.py | Dry-run resource admission |
| star/conversation_memory.py | Scoped, digest-bound conversation memory |
| star/skill_contract.py | Versioned declarative skill requirements and behavior coverage |
| star/skill_evolution_lab.py | Development/holdout skill comparison |
| star/clips_obs.py | Authenticated local OBS replay-buffer integration |
| Existing game-action and Creator evaluation PRs | Freshness gates, causal probes, Roblox and mixed-load evaluation |

Do not add a second voice engine, avatar writer, OBS client, memory database, resource scheduler, or game-control authority.

## 3. Run 59 implementation — voice tail latency

### Change

star/voice/metrics.py now exposes:

latency_summary(turns: list[TurnMetrics]) -> dict

It returns:
- total, complete, interrupted, and errored turn counts;
- interruption and error rates;
- nearest-rank p50, p95, and p99 for each observed duration stage;
- per-stage sample counts;
- token-generation-rate percentiles;
- explicit guidance that p95 should not be used as a release gate below 20 samples and p99 below 100 samples.

Incomplete turns remain in the top-level counts and rates; a missing timestamp is not silently converted to zero. Each stage uses only records that actually contain both timestamps for that stage. Percentiles use nearest-rank rather than an undocumented interpolation rule.

The summary does not include user text, reply text, audio, transcripts, chat messages, or viewer identities. It is an in-memory aggregate. No persistence or telemetry upload is added.

### Why this matters

The existing voice report shows per-turn measurements and means. A mean can hide occasional long pauses that make a live conversation feel broken. Tail percentiles let STAR compare:
- end-of-turn wait;
- ASR completion;
- transcript-to-first-token;
- first-token-to-first-audio;
- speech-end-to-first-audio;
- generation rate.

The helper is additive. Existing TurnMetrics, to_dict(), and latency_table() behavior is preserved. No runtime consumer is changed in this run.

### Validation

New unit tests cover:
- nearest-rank percentile selection;
- incomplete turns;
- interrupted and errored turn counts;
- empty input;
- missing stage samples;
- rejection of untyped records.

Exact-head GitHub Actions must pass before this change is considered validated. No local microphone, audio-device, OBS, avatar, GPU, or public-stream test is claimed.

## 4. Proposed unified live-session acceptance

The next integration should correlate events using a random session ID and per-turn ID, with monotonic timestamps. Keep event content in its owning subsystem; the shared trace should carry only metadata and bounded evidence references.

Recommended stages:

1. capture_started
2. speech_started
3. speech_paused
4. turn_confirmed
5. transcript_ready
6. brain_first_token
7. tool_started / tool_finished
8. first_sentence_ready
9. tts_first_chunk
10. playback_started
11. avatar_state_applied
12. playback_interrupted or playback_finished
13. turn_persisted

For game streams, add:
- game_observation
- action_proposed
- action_authorized
- action_sent
- state_verified
- strategy_updated

Each event should contain a schema version, session/turn correlation ID, monotonic timestamp, component name/revision, outcome, and optional content-free counters. Do not place raw audio, full transcripts, secrets, viewer messages, screenshots, or model chain-of-thought in the trace.

## 5. Mixed-load acceptance matrix

Run the same pinned scenario set under these conditions:

| Scenario | Concurrent work | Required measurements |
|---|---|---|
| Voice only | none | endpoint, ASR, TTFT, first audio, interruption |
| Game only | controller + strategy | action age, invalid actions, frame-time p95/p99, verified objective rate |
| Stream only | chat + voice + avatar | addressee accuracy, false cutoffs, audible latency, stale avatar frames |
| Voice + game | voice and gameplay | both latency sets, audio underruns, frame-time |
| Full stream | voice, game, chat, OBS, avatar | goodput, dropped frames, turn quality, resource pressure |
| Full stream + background research | above + bounded research | admission/preemption correctness, protected-lane regressions |
| Recovery | disconnect/restart mid-task | cancellation, reconnect, idempotency, no duplicate side effects |

For each scenario report:
- p50/p95/p99 with sample counts;
- verified task/turn success;
- interrupted and failed operations;
- CPU/RAM/VRAM/GPU utilization and peak memory;
- audio callback underruns and queue depth;
- game frame-time and stale-action age;
- OBS dropped frames and reconnect events;
- resource-admission decisions;
- baseline/candidate model, prompt, skill, and runtime revisions.

Primary metric: **verified useful goodput under protected interaction budgets**. Raw tokens/s is diagnostic, not the acceptance target.

## 6. Prioritized implementation plan

### P0 — land and validate tail summaries
- Run exact-head Python and Windows tests.
- Keep the new helper additive.
- Confirm existing voice reports remain unchanged.
- Do not add a new telemetry store.

### P1 — repeatability harness
- Add repeated identical-task trials to computer-use and game evaluations.
- Report pass^k, per-task variance, paired deltas, and recovery.
- Record environment, application, seed, and model versions.
- Add ambiguity-resolution trials.

### P2 — unified session timeline
- Reuse existing voice and OBS event bridges.
- Add correlation IDs and monotonic timing.
- Make cancellation and stale-result rejection explicit.
- Keep default traces content-free.

### P3 — multiparty stream director
- Evaluate speaker/addressee resolution, floor ownership, interruption, and response appropriateness independently.
- Use event priority and deadline budgets.
- Preserve silence as a valid action.

### P4 — avatar and OBS reliability
- Add a single-writer avatar parameter arbiter.
- Keep VTube Studio plugin authentication user-controlled.
- Use latest-wins state updates and explicit neutralization on disconnect.
- Keep OBS authenticated and loopback-only by default.

### P5 — Gamer/Creator transfer
- Add real-time GameWorld-style tests with state-verifiable success.
- Use practice/validation/holdout separation.
- Preserve visual evidence and project revision for creator tasks.
- Require new maps/seeds and unfamiliar tasks for transfer.

### P6 — measured inference optimization
- Run paired llama.cpp tests with actual model and server slots.
- Compare speculation on/off and cache states.
- Protect audio and gameplay lanes.
- Reject speedups that worsen end-to-end p95/p99 or task accuracy.

## 7. Explicit non-claims

- No model weights were trained or changed.
- No model provider, route, scheduler, permission, game controller, OBS setting, or VTube Studio setting was changed.
- No automatic skill promotion was added.
- No new memory database or telemetry persistence was added.
- No physical microphone, speaker, GPU, OBS, VTube Studio, Roblox Studio, live game, or public broadcast was tested.
- Research results are not STAR benchmark results.
- The new percentile helper is not a performance speedup; it makes tail latency measurable.
- PR #1209 remains a draft and must not be merged without exact-head CI and owner review.

## Sources

1. SkillLearnBench (2026-04-22): https://arxiv.org/abs/2604.20087
2. On the Reliability of Computer Use Agents (2026-04-20): https://arxiv.org/abs/2604.17849
3. MP-Bench, Findings of EMNLP 2026: https://aclanthology.org/2026.findings-emnlp.1437/
4. LiveKit turn handling: https://docs.livekit.io/agents/logic/turns/
5. LiveKit turn-taking tuning: https://docs.livekit.io/agents/logic/turns/tuning/
6. LiveKit EoT-Bench: https://github.com/livekit/eot-bench
7. VTube Studio API: https://github.com/DenchiSoft/VTubeStudio
8. VTube Studio expressions: https://github.com/DenchiSoft/VTubeStudio/wiki/Expressions-%28a.k.a.-Stickers-or-Emotes%29
9. OBS WebSocket: https://github.com/obsproject/obs-websocket
10. GameWorld (2026-04-08): https://arxiv.org/abs/2604.07429
11. GameWorld project: https://gameworld-bench.github.io/
12. GameDevBench: https://github.com/waynchi/gamedevbench
13. Speculative-decoding latency model (2026-05-14): https://arxiv.org/abs/2605.15051
14. llama.cpp SPEED-Bench: https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench
15. AITuber OnAir (modular TypeScript reference implementation; inspect, do not adopt blindly): https://github.com/shinshin86/aituber-onair
