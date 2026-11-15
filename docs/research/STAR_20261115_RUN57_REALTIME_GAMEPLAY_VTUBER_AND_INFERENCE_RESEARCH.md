# STAR Run 57 — Real-Time Gameplay, VTuber Conversation and Inference Research

**Date:** 2026-11-15  
**Status:** research and integration plan; no production defaults changed  
**Related work:** #584, #1201, #1207, #1208, #1209

## Executive summary

The next meaningful STAR improvement is not another general-purpose agent loop. It is a coordinated real-time runtime that protects gameplay, voice and avatar responsiveness while slower reasoning, research, memory and self-improvement run in the background.

The research points to five engineering principles:

1. **Measure completion, not apparent progress.** A game agent can make substantial progress and still fail to complete the objective. Use state-verifiable success and progress as separate metrics.
2. **Treat real-time play as a different benchmark track.** A paused environment hides inference delay. STAR's streaming/game mode must be evaluated with the environment advancing while the agent reasons.
3. **Treat conversation endpointing as its own latency problem.** False cutoffs and conversational dead air must be measured separately from model TTFT and tokens/sec.
4. **Evaluate skills as interventions.** Compare the same task with and without a skill, inspect paired traces, measure behavior changes and token cost, and test for negative transfer.
5. **Tune inference on the actual host.** Speculative decoding, KV cache, MoE cache and CPU/GPU offload are hardware/model dependent. Preserve an unoptimized baseline and reject any change that harms the live workload.

This document reuses STAR's existing skill contracts, Gamer Brain, Creator evaluation, streaming directors, OBS telemetry, resource planner and speculative-decoding canary. It does not propose another controller, scheduler, memory database, permission authority or voice pipeline.

## Research findings

### 1. GameWorld: progress and task success are different

GameWorld evaluates multimodal game agents across 34 browser games and 170 tasks spanning runner, arcade, platformer, puzzle and simulation genres. It compares low-level computer-use control with semantic generalist control and computes progress and success from serialized game state rather than screenshot heuristics or an LLM judge.

The project reports a large gap between partial progress and completion in its evaluated agents. Its FAQ also describes **GameWorld-RT**, where the environment continues running during inference; the standard paused track and real-time track must be interpreted separately.

**STAR application**
- Keep `progress` and `success` separate in every game evaluation.
- Prefer game-state evaluators (score, checkpoint, inventory, health, objective flags) in controlled sandboxes.
- For unknown commercial games, use permitted visual/UI evidence and independent replay or task-state checks where available.
- Maintain two benchmark tracks: paused/turn-based for reasoning quality and real-time for latency-sensitive play.
- Report game family, seed/map, action budget, model, controller, observation cadence and evaluator version.

Source: https://gameworld-project.github.io/

### 2. GameDevBench: evaluate the whole creation loop

GameDevBench is an ICML 2026 benchmark with 333 tasks in a modern game engine, spanning 2D graphics, 3D graphics, UI and gameplay. It provides a useful external signal for general game-development capability, but it is not a substitute for STAR's Roblox/Luau/Studio-specific tests.

**STAR application**
- Use GameDevBench as a reference benchmark, not as a claim of Roblox competence.
- Keep a separate Roblox acceptance suite: Luau static analysis, Studio DataModel checks, server/client behavior, multiplayer, visual snapshots and playtests.
- Score code correctness, scene correctness, visual match, playability and performance independently.
- Require at least one actual runtime/playtest check before calling a game task complete.

Source: https://github.com/waynchi/gamedevbench

### 3. LiveKit EoT-Bench v1.1: conversational timing is not model speed

The current EoT-Bench repository documents 14 languages and v1.1 English cohorts for accented speech and short turns. It measures false cutoffs against endpointing latency and includes a VAD-only baseline. Its README explicitly distinguishes conversational endpointing delay from model inference latency.

**STAR application**
- Measure false-cutoff rate, endpointing delay, interruption precision/recall and response appropriateness separately.
- Do not tune a detector to minimize dead air without a false-cutoff budget.
- Include accented speech, short acknowledgements, hesitations and incomplete clauses in replay tests.
- Preserve the audio and text context available at each decision point; do not score using future audio.
- Keep the microphone/turn detector responsive even when the main LLM is busy generating or the avatar is rendering.

Source: https://github.com/livekit/eot-bench  
Dataset: https://huggingface.co/datasets/livekit/eot-bench-data

### 4. Skill Coverage and Counterfactual Trace Auditing

Skill Coverage argues that task pass/fail alone cannot show whether the agent exercised and followed the reusable constraints in a skill. Counterfactual Trace Auditing compares paired runs with and without a skill and inspects how the skill changed the agent's behavior, including cases where aggregate pass rate barely changes.

**STAR application**
- Keep the existing `pass` / `fail` / `not_observed` contract coverage labels.
- Add a paired evaluation protocol: same task, same initial state, same model/settings, skill off versus skill on.
- Compare success, progress, steps, wall time, tokens, tool calls, recovery, off-task artifacts and constraint coverage.
- Test dependent transfer (where the skill should help) and independent interference (where it should not apply).
- Do not let the skill author modify the sealed grader or holdout cases.
- A skill that improves success but multiplies token cost or causes unrelated artifacts is not an automatic promotion.

Sources:
- https://arxiv.org/abs/2606.20659
- https://arxiv.org/abs/2605.11946

### 5. llama.cpp SPEED-Bench and MoE cache tuning

The official SPEED-Bench client measures an already-running `llama-server`; its guidance recommends matching client concurrency to server parallel slots (`--np`). Its documented baseline-versus-speculative workflow saves comparable JSON runs and compares them. The MoE cache documentation explains that frequently used experts can be cached in device memory while experts remain in host RAM; whether CPU-side cache-miss computation helps depends on RAM speed, PCIe bandwidth, pinning and cache size.

**STAR application**
- Establish a fixed baseline before changing runtime flags.
- Keep model, quantization, context, prompt set, output length, server slots, batching and power mode identical between arms.
- Measure prefill, decode, TTFT, inter-token latency, acceptance, memory, VRAM and thermal/power behavior.
- For MoE models, test host expert placement and device cache size only if the selected model and binary support it.
- Do not assume a larger cache or more CPU offload is faster; run the upstream tuner on the actual machine.
- Keep speculative decoding and MoE cache options off unless paired tests show a stable gain.

Sources:
- https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench
- https://github.com/ggml-org/llama.cpp/blob/master/docs/moe-cache.md
- https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md

## Recommended STAR runtime architecture

### A. Two-speed gameplay control

Separate the control plane from the reasoning plane.

**Fast control plane**
- Consumes recent observations and a compact state estimate.
- Executes bounded, short-horizon actions through an approved controller.
- Handles movement, aim, jump timing, camera and immediate dodge/interaction.
- Uses deadlines and cancels stale actions when the scene changes.
- Runs at a cadence chosen per game and hardware; do not hard-code one universal FPS.

**Strategic reasoning plane**
- Plans objectives, routes, resource use, team coordination and boss strategies.
- Runs on events, objective changes or low-frequency intervals rather than every rendered frame.
- Produces a goal/constraint/action proposal for the fast controller.
- Replans when the state estimate diverges from the expected state.

**Required loop**
`observe → estimate state → choose bounded action → execute → verify outcome → update belief`

The language model should not be asked to emit every mouse/keyboard frame. A deterministic local controller should own high-frequency control, while the model handles semantic decisions and adaptation.

### B. Creator Brain and game-production verification

For each build task, STAR should retain:
- A requirement checklist tied to the original request.
- A scene/DataModel snapshot before and after edits.
- Static-analysis output.
- Runtime logs and errors.
- A playtest trace.
- Visual captures at defined camera/viewport settings.
- Performance measurements on a named target device.

Use the existing Luau tools, Studio automation, OpenGameEval adapter and skill-contract coverage. A successful file write is not proof of a working game.

### C. VTuber conversation and avatar coordination

Use one shared conversation/event timeline, not separate systems inventing their own context.

Suggested event record fields:
- monotonic timestamp and source;
- speaker/addressee when known;
- transcript segment and confidence;
- turn state (listening, hold, end-of-turn, interrupted);
- game/stream event references;
- response intent and priority;
- audio playback start/end/cancel;
- avatar expression/motion cue and expiry.

The conversation planner should choose among speak, short reaction, defer, ask for clarification or remain silent. Silence is a valid output. Do not synthesize fake personal experiences; keep STAR's AI identity clear while allowing a consistent expressive character.

For avatar control, use a single writer/arbiter for parameter updates. Give cues an expiry time, cancel stale cues on interruption, and synchronize mouth movement to actual playback time rather than the time text generation finished.

### D. Mixed-load resource policy

Use one shared host budget with explicit reservations:
1. audio capture/playback and turn detection;
2. gameplay capture/control;
3. OBS stream output and avatar rendering;
4. foreground reasoning;
5. background research, indexing and self-play.

When the host is saturated, shed work in reverse order: pause background self-play, defer indexing, lower nonessential avatar effects, reduce optional visual sampling, then route foreground reasoning to a smaller/fast path if available. Do not silently starve audio or gameplay to keep background agents busy.

Use hysteresis and minimum dwell times so the scheduler does not thrash between profiles. Every throttle decision should emit a reason and before/after telemetry.

### E. Memory and skill improvement

Keep semantic facts, episodic stream/game events, procedural skills and causal lessons distinguishable. Each retained item needs provenance, confidence, timestamp, scope and a review/expiry policy. A viewer's claim is not automatically a verified fact; a successful run on one map is not proof that a game skill transfers.

Promote a candidate skill only after:
- valid contract and source review;
- independent host/replay evidence;
- dependent transfer improvement;
- independent interference guardrail;
- sealed holdout success;
- resource-cost review;
- owner/policy gate.

## Evaluation scorecard

| Domain | Primary metrics | Guardrail |
|---|---|---|
| General reasoning | task success, factuality, calibration, evidence coverage | contradiction and unsupported-claim rate |
| Gaming | success rate, normalized progress, action latency, retries | real-time frame-time and input freshness |
| Game creation | code/scene correctness, playtest success, visual match | regression and performance budget |
| Streaming conversation | EoT false cutoffs, endpointing delay, relevance, interruption handling | never optimize latency without cutoff budget |
| Voice | first-audible latency, jitter, underruns, ASR quality | no audio backlog or stale speech |
| Avatar | cue-to-motion latency, lip-sync offset, stale cue rate | one parameter writer; reduced-motion support |
| Inference | TTFT, prefill/decode throughput, inter-token p95/p99 | quality and mixed-load guardrails |
| Host | CPU/GPU/VRAM/RAM, thermal headroom, OBS dropped frames | foreground reservations and hysteresis |
| Learning | dependent transfer, independent interference, skill coverage | sealed holdout and rollback |

## Phased implementation plan

### Phase 0 — restore trustworthy baseline
- Fix the current exact-head contract test failures.
- Keep PR #1209 draft until all exact-head CI jobs pass.
- Record current PR head SHA, test run IDs and unresolved failures.
- Do not describe a cancelled/skipped check as passing.

### Phase 1 — paired evaluation harness
- Add skill-on/skill-off paired trace metadata to the existing evaluation system.
- Reuse existing evaluators and resource planner.
- Add cost metrics (tokens, calls, elapsed time) to skill utility decisions.
- Keep graders and holdout data separate from candidate skill generation.

### Phase 2 — real-time Gamer Brain
- Add a paused GameWorld-compatible track and a distinct GameWorld-RT track.
- Add action deadline and observation freshness checks.
- Measure completion separately from partial progress.
- Begin with a small representative game set before scaling to all genres.

### Phase 3 — human-feeling stream loop
- Replay EoT-Bench v1.1 with a local adapter or documented provider adapter.
- Add a trusted multi-speaker replay set for addressee and turn-taking evaluation.
- Measure false cutoff and endpointing latency separately from model TTFT.
- Connect game events to a single stream event timeline and avatar cue arbiter.

### Phase 4 — measured inference tuning
- Run baseline SPEED-Bench with concurrency matched to actual server slots.
- Test one optimization at a time: n-gram speculation, batch settings, cache settings, or MoE cache where supported.
- Repeat under idle, game-only, OBS-only and mixed-load conditions.
- Promote only if paired results are reproducible and all real-time guardrails pass.

### Phase 5 — creator and knowledge transfer
- Add Roblox-specific state-verifiable task suites.
- Add game-creation acceptance tests and visual regression captures.
- Evaluate factual research with source/recency/contradiction checks.
- Test skill transfer across new maps, projects and independent domains.

## Explicit non-goals and safety boundaries

- No automatic public streaming, game publishing, purchases, messages, account changes or external irreversible actions.
- No generated code execution from a skill contract.
- No permission grants derived from model output or skill metadata.
- No silent hosted-model fallback.
- No unbounded self-play or background model downloads.
- No automatic skill promotion based only on self-reported success.
- No claim of human consciousness or real human experiences.

## Current implementation status

This Run 57 document is research and integration guidance. The accompanying CI follow-up changes correct a test fixture and add an explicit diagnostic assertion for the optional sidecar loader. They do not enable the optional contract path or change production behavior.

The repository's latest exact-head CI must be re-run after the new commits; GitHub API-created commits in this run did not return new workflow-run IDs at the time this document was written. No Windows hardware, microphone, OBS, VTube Studio, Roblox gameplay, GPU or live-stream acceptance is claimed.
