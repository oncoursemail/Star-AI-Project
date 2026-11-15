# STAR Run 47 — Mixed-Load Streaming Performance, Generalist Learning, and Creator Runtime

**Date:** 2026-11-15  
**Status:** research + offline evaluator prototype; runtime integrations remain gated  
**Related acceptance:** [#584 — STAR Creator Studio](https://github.com/oncoursemail/Star-AI-Project/issues/584)

## Executive finding

STAR already has useful but separate foundations: stream_budget.py makes conservative workload recommendations; resource_planner_service.py and agent_resource_planner.py arbitrate machine capacity; streamer_creator.py holds a bounded moderated-chat queue and owner-reviewed broadcast intent; streamer_media.py derives avatar motion envelopes from actual PCM and creates non-destructive edit decision lists; gameplay_skill_bank.py and active_practice.py keep signed practice evidence separate from game-control authorization.

The missing proof is whether a proposed optimization improves STAR's whole live experience when game, model, voice, avatar, OBS, and background work compete for the same hardware. A token-throughput-only benchmark can reward a configuration that makes gameplay stutter or voice crackle.

Run 47 adds an offline, paired mixed-load evaluator. It consumes host-signed aggregate measurements, compares matched baseline/candidate runs, and refuses to call a change successful if protected voice, game, OBS, task-quality, or resource metrics regress beyond preregistered budgets. It cannot start workloads, read telemetry, change routing, control OBS, operate a microphone, or promote a configuration.

## New implementation

- star/mixed_load_eval.py
- tests/test_mixed_load_eval.py

The evaluator is standard-library-only. Each observation is bound to:
- Campaign and split (practice, validation, or holdout).
- Hardware fingerprint and exact game build.
- A workload digest representing the same scripted scene, request schedule, and task mix.
- Baseline/candidate runtime, model, and config revisions.
- A matched pair ID, measurement-window duration, and timestamp.
- A complete fixed metric set with units and sample counts.
- An HMAC receipt produced by the trusted host; the key must remain outside model prompts and worker sandboxes.

The manifest pins the primary metric and thresholds before observations are collected. A one-sided paired sign test is applied only to that preregistered primary metric. Protected guard metrics are evaluated separately. A positive result returns eligible_for_owner_review, never permission to modify runtime settings. Missing pairs are inconclusive; stale, replayed, mismatched, malformed, or unsigned evidence is rejected.

### Metrics recorded

| Family | Metrics |
|---|---|
| Inference | TTFT p95, tokens/sec, model queue wait p95 |
| Voice | First audible output p95, endpointing delay p95, false-cutoff rate, speech backlog p95, audio underruns/min |
| Gameplay | Frame-time p95/p99 |
| Broadcast | OBS dropped frames/min |
| Quality | Independently verified task success rate |
| Resources | CPU p95, RAM p95, VRAM p95, GPU utilization p95 |
| Creator tools | Tool completion p95 |

The aggregate metric definitions, sampling windows, clocks, and measurement sources must be pinned by the host-side harness. GPU utilization is reported as a diagnostic rather than treated as monotonic: higher utilization can mean more useful work. HMAC authenticates the host receipt; it does not prove that a sensor or grader is truthful. A separate independent observer and deterministic task verifier are still required.

## Research synthesis and engineering decisions

### 1. End-of-turn detection is not model inference latency

LiveKit's EoT-Bench evaluates the decision at real pauses, not merely speech classification on isolated clips. Version 1.1 covers 14 languages and includes accented-English and short-turn cohorts. Some short-turn rows end at a mid-thought HOLD pause and have no observed EOT; those are right-censored examples, not missing labels to fabricate.

The benchmark explicitly separates false cutoffs from endpointing delay. Endpointing delay is conversational dead air after a true turn end, not TTFT or model compute time. STAR should report separately:
- False-cutoff rate and missed-final rate.
- Endpointing delay.
- ASR finalization delay.
- Model TTFT / time to first useful output.
- TTS first-audio latency.
- Playback queue and device output delay.

Do not collapse these into one “response latency” number. Keep the existing strict rehearsal evaluator default and use the right-censored adapter only on compatible benchmark inputs.

Sources:
- https://github.com/livekit/eot-bench
- https://livekit.com/benchmarks/eot-bench

### 2. Benchmark the actual serving path, not an isolated model

NVIDIA AIPerf distinguishes TTFT, time to first output, inter-token latency, inter-chunk latency, per-user throughput, prefill throughput, and quality goodput. Goodput counts requests meeting all declared SLOs; raw throughput alone can conceal poor user experience.

llama.cpp's server supports continuous batching, parallel decoding, monitoring endpoints, speculative decoding, and a model router. Its SPEED-Bench client benchmarks an already-running server; concurrency should match the configured server slot count for meaningful throughput comparisons. Draft-model or n-gram speculative decoding should be tested on STAR's real prompts and output lengths, not enabled by assumption.

Recommended experiment order:
1. Establish a repeatable single-user baseline.
2. Match client concurrency to server slots.
3. Record cold-load and warm-cache runs separately.
4. Test prompt-cache reuse with identical prefix distributions.
5. Test speculative decoding only with a pinned draft/model/runtime pair.
6. Repeat with voice + game + avatar + OBS mixed load.
7. Reject any speed gain that violates foreground SLOs or verified task quality.

Sources:
- https://docs.nvidia.com/aiperf/reference/ai-perf-metrics-reference
- https://docs.nvidia.com/aiperf/getting-started/ai-perf-comprehensive-llm-benchmarking
- https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- https://github.com/ggml-org/llama.cpp/blob/master/tools/server/bench/speed-bench/README.md

### 3. Generalist gaming: learn actions and transfer, not just game descriptions

Google DeepMind's SIMA 2 work combines high-level goal reasoning with visual interaction through keyboard/mouse actions. Its published research describes self-directed play, experience accumulation, and transfer of concepts across different games, while also evaluating held-out environments.

STAR should borrow the evaluation pattern, not assume that a text LLM becomes a capable gamer by receiving a large guide:
- Separate visual observation, state estimation, planning, and low-latency control.
- Keep the motor loop local and time-bounded; do not put an LLM round trip on every frame.
- Train/practice in resettable, permitted environments.
- Store attempts with game build, map/seed, action, observed state delta, and independent outcome evidence.
- Promote reusable skills only after held-out maps/seeds and task variants.
- Measure real-time success separately from paused/slowed reasoning.

Sources:
- https://deepmind.google/blog/sima-2-an-agent-that-plays-reasons-and-learns-with-you-in-virtual-3d-worlds/
- https://gameworld-project.github.io/
- https://github.com/Roblox/open-game-eval

### 4. Roblox Creator Brain: plan → inspect → build → playtest → repair

Roblox's April 15, 2026 announcement describes a multistep planning workflow, a structured task manifest, built-in Studio MCP access, and a playtesting agent that inspects code/data, reads logs, and exercises a test character. This is a better model than one-shot script generation.

STAR's Creator Brain should:
1. Inspect the existing place and exact objects/scripts a task touches.
2. Produce a reviewable task plan and expected state deltas.
3. Make small, reversible edits.
4. Run static Luau checks.
5. Playtest in an unpublished disposable place.
6. Capture logs and independent state assertions.
7. Repair and replay.
8. Test regressions and held-out scenarios.
9. Return an artifact/evidence receipt, not just “done”.

Keep Studio MCP tools scoped to an owner-selected project and permitted operations. A successful Studio playtest is not evidence that an external live game can be controlled or that a published place is authorized.

Source: https://about.roblox.com/newsroom/2026/04/roblox-studio-going-agentic

### 5. Human-like streaming is orchestration, timing, and restraint

Two open-source references are useful as architecture studies:
- AITuber OnAir separates chat, voice, memory, avatar templates, and agent integration into modular packages.
- Lumi_Nox describes a scheduler and one-voice-at-a-time arbitration for two AI co-hosts, with a runnable coordination demo and game bridge.

STAR should not import their character IP, voice assets, source code, or provider configuration. Reuse ideas only after license and dependency review. The important design lesson is that multiple event sources need one speech/floor authority.

Preserve STAR's existing RoomTurnDirector, playback owner, ChatAttention, and ConversationContextIndex boundaries. Do not add a second speech queue or independent social director. A trusted event pipeline should supply source-scoped, session-local metadata:
- speaker and addressee confidence;
- reply-to and topic references;
- moderation result;
- game urgency and verified event type;
- current speech/playback state.

The director should choose among speak, short acknowledgement, laugh/reaction, gaze/gesture, defer, or silence. Silence is a valid output. The speech renderer must remain driven by actual playback timestamps; generated text or PCM amplitude alone must not claim that a laugh occurred. Long-term viewer memory must be opt-in, bounded, source-scoped, deletable, and never merge identities across platforms.

Sources:
- https://github.com/shinshin86/aituber-onair
- https://github.com/MIO-456/Lumi_Nox
- https://github.com/livekit/eot-bench

## Integration map

| Existing STAR component | Run 47 decision |
|---|---|
| stream_budget.py | Keep as advisory policy; calibrate only from real mixed-load measurements |
| resource_planner_service.py / agent_resource_planner.py | Remain the sole resource-admission authority |
| streamer_creator.py | Keep chat moderation/attention and owner-controlled broadcast intent; no new scheduler |
| streamer_media.py | Keep one playback-clock authority and PCM-grounded motion |
| gameplay_skill_bank.py / active_practice.py | Keep practice evidence separate from validation and action authorization |
| #1185 conversation context | Integrate only through the existing room host and source-scoped metadata |
| #1187 EoT adapter | Keep opt-in for compatible EoT-Bench data; preserve strict default |
| #1199 causal game probes | Use separate deterministic reset/scoring adapters and held-out transfer tests |
| #1200 OpenGameEval adapter | Pin exact upstream suite/revision; do not confuse parsing with Studio integration |

## Hardware experiment protocol

Run on one explicitly selected machine at a time. For each scenario:
1. Record exact Windows build, CPU, RAM, GPU/driver, model file hash/quantization, llama.cpp commit/build flags, app commit, game build, OBS version/settings, avatar renderer version, and audio device.
2. Fix the workload trace and hash it. Use synthetic chat and deterministic permitted game scenes; no real viewer identities or private audio.
3. Randomize baseline/candidate order inside matched blocks to reduce thermal, cache, and time-of-day bias.
4. Use at least eight complete matched pairs for screening; use a larger untouched holdout for acceptance.
5. Keep each measurement window 1–60 minutes, with a pinned warm-up and cooldown policy.
6. Record p50/p95/p99 and counts; preserve raw diagnostics locally under owner retention controls, while publishing only minimized aggregate receipts.
7. Compare one optimization at a time before testing interactions.
8. Run a 60-minute endurance rehearsal with stop/mute controls and power-loss recovery; restart must remain offline.
9. Obtain owner approval after reviewing plots, traces, voice playback, visual quality, and the actual game.

The evaluator's eligible_for_owner_review is only a screening result. It is not production acceptance, a runtime permission, or a claim of better intelligence.

## What is implemented vs. still missing

Implemented in this branch:
- Offline manifest-bound mixed-load aggregate schema.
- Host HMAC receipt verification.
- Paired baseline/candidate matching.
- Split, hardware, workload, game-build, model/runtime/config pinning.
- Stale/future/duplicate/malformed evidence rejection.
- Exact one-sided paired sign test for one preregistered primary metric.
- Protected regression checks for voice, OBS, game, task quality, and resources.
- 20 synthetic regression tests.

Not implemented:
- Windows/Brain 1/Brain 2 telemetry collectors.
- OBS WebSocket or audio-device integration.
- LiveKit/ASR/TTS provider integration.
- llama.cpp model router changes or model installation.
- Roblox Studio MCP connection or game controller.
- Skill promotion or runtime policy changes.
- Avatar/voice art or licensed voice assets.
- Public chat, OAuth, streaming, or auto-publishing.

No model weights, credentials, third-party source code, raw audio, transcripts, private viewer data, or copyrighted assets are included. Production defaults and main remain unchanged.
