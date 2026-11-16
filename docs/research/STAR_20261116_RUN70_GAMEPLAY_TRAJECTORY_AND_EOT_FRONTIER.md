# STAR Run 70 — Exploration-First Game Agents, End-of-Turn Tradeoffs, and Evidence-Gated Capability Growth

**Research date:** 2026-11-16  
**Scope:** offline trajectory evaluation, offline voice-endpointing evaluation, source review, and integration plan  
**Runtime status:** both evaluators are offline-only. Neither connects to Roblox Studio, a game controller, microphone, speaker, OBS, VTube Studio, model router, or production scheduler.

## Executive decisions

Run 70 turns two research findings into reusable, dependency-free evaluation infrastructure:

1. **Game-agent quality must include exploration and execution history.** A successful final scene or script does not show whether the agent inspected the right objects, used valid actions, recovered from errors, or completed the same task reliably on held-out cases.
2. **Natural voice timing is a tradeoff, not one latency number.** A system must avoid false cutoffs while responding promptly after a real end-of-turn. Conversational endpointing delay is distinct from model inference time and from audio playback latency.

The new modules accept redacted metadata only. They do not capture media, control tools, select models, or promote a candidate. They are intended to complement STAR's existing gameplay, voice, playback, memory, and resource-admission authorities—not replace them.

## 1. Roblox agent research: observe before mutate

### OpenGameEval — October 1, 2026

Primary paper: https://arxiv.org/abs/2610.02563  
Official implementation and task suite: https://github.com/Roblox/open-game-eval

OpenGameEval evaluates agents in reproducible, stateful Roblox Studio sessions. Its eight-tool action space separates observation from editing, and it checks both the edited scene and simulated play behavior. The paper reports 13 frontier models, 84 human-curated core tasks, and 16 attempts per task. On that task set, the best reported single-attempt pass rate is 51.7%, while 39.4% of tasks pass all five of five attempts; six tasks are unsolved by every tested model.

The most actionable result is about exploration: holding task and model fixed, inspecting every object touched by a reference solution is associated with a 13.4 percentage-point higher pass rate on scene-only tasks and 9.8 points on script-only tasks compared with inspecting none. This is evidence from that benchmark, not a universal causal guarantee.

**STAR design decisions:**
- Keep observation tools distinct from edit/action tools in the game adapter.
- Record opaque target references and whether each target was inspected before its first mutation.
- Preserve action validity, verification outcomes, recovery events, and monotonic timing.
- Split train, validation, and holdout cases. Never tune a policy on the holdout split.
- Report empirical pass@k and all@k over ordered attempts for the same task/case. Do not use an independence-based estimate when attempts may learn from one another.
- Treat a task as accepted only when the goal was reached and a final independent verification passed.
- Require save/reload verification for tasks whose contract includes persistence.

### Roblox's official agentic workflow direction — April 15, 2026

Source: https://about.roblox.com/newsroom/2026/04/roblox-studio-going-agentic

Roblox describes a plan/build/test workflow, a reviewable task plan, Studio MCP exposure, and a playtesting agent that checks behavior against the original plan. This supports using a design document as a testable contract rather than a one-shot prompt.

**STAR application:** inspect the existing place, scripts, hierarchy, and server/client ownership before editing; produce a task manifest; make bounded changes; run the experience; use actual input; inspect logs and state; and verify the original contract. Keep Studio's existing least-privilege APIs and STAR's action authorization gates. No Studio permissions are expanded by this run.

### CEGame-Bench — October 19, 2026

Paper: https://arxiv.org/abs/2610.26098

CEGame-Bench covers complete-game creation across Defold, Godot, Roblox Studio, Unity, and Unreal Engine. Its acceptance path uses real player input and a hidden evaluator. The paper reports that only 16% of agent runs reached the ending in its evaluated setup, and describes a Game Completion Boost skill that improved execution-based scores by 14.1–24.3 points for three tested models.

**STAR application:** build acceptance around launch, play, ending, restart, and persistence—not compilation alone. Keep engine-specific test adapters because the paper finds that engine choice changes agent rankings and task difficulty.

## 2. New gameplay trajectory evaluator

Added:
- `star/gameplay_trajectory_eval.py`
- `tests/test_gameplay_trajectory_eval.py`

The evaluator accepts episode metadata and a bounded event stream with:
- `observe`, `edit`, `act`, `verify`, `verify_final`, and `recover` events;
- monotonic event indexes and timestamps;
- opaque, bounded target IDs;
- explicit action-validity and verification outcomes;
- goal-reached and optional save/reload adjudication;
- train, validation, and holdout splits.

It reports:
- target-observation-before-action coverage;
- invalid action rate;
- subgoal verification pass rate;
- recovery frequency;
- event latency distributions;
- final-verification and verified-acceptance counts;
- save/reload outcomes for tasks that require persistence;
- empirical pass@1/3/5 and all@1/3/5 for ordered repeated attempts.

It rejects duplicate episodes/attempts, invalid event order, actions after final verification, malformed values, and over-limit streams. It emits no composite score and cannot trigger an agent action or promotion.

**Important boundary:** this is a trace evaluator, not a Roblox Studio adapter. A future adapter must produce trustworthy observations from the actual editor/game session and independent playtest oracle results. Synthetic fixtures alone are not evidence of game mastery.

## 3. Human-like VTuber timing: evaluate the cutoff/latency frontier

### LiveKit EoT-Bench

Repository: https://github.com/livekit/eot-bench  
Dataset: https://huggingface.co/datasets/livekit/eot-bench-data  
License declared by the project: Apache-2.0 for the benchmark and dataset.

The project provides real human-to-agent turns in 14 languages and labels silence pauses as either true end-of-turn (`eot`) or mid-turn hesitation (`hold`). Its README's committed validation snapshot covers 125,703 prediction points across 5,454 turns. It evaluates actual streaming pauses under explicit latency and false-cutoff budgets, rather than relying only on isolated-clip accuracy.

The published English comparison illustrates why the tradeoff matters: at a 5% false-cutoff budget, its table reports 810 ms endpointing latency for LiveKit Turn Detector v1.1 and 1,600 ms for a VAD-only baseline in the pooled English cohorts. These are benchmark-specific endpointing results, not STAR measurements or targets. The project explicitly distinguishes conversational endpointing delay from model inference latency.

**STAR design decisions:**
- Measure false cutoffs on mid-turn hesitations separately from missed true turn endings.
- Report endpointing delay including the configured timeout for missed EOTs; otherwise a policy that never responds could look artificially fast.
- Report results by language and cohort; do not hide accented or short-turn failures in an overall average.
- Compare policies only on the exact same adjudicated sample set. Incomplete coverage disables the Pareto frontier.
- Keep the false-cutoff rate, missed-EOT rate, p50/p95/p99 endpoint delay, and false-cutoff delay visible as separate measures.
- Keep conversational endpointing, model compute, TTS generation, speaker playback, and client-heard audio as distinct timestamps.

### New endpointing evaluator

Added:
- `star/voice/endpointing_eval.py`
- `tests/test_endpointing_eval.py`

The evaluator accepts redacted pause labels and policy decisions. It calculates false-cutoff rate, missed-EOT rate, endpoint delay, per-language/cohort breakdowns, paired-sample coverage, and a three-metric Pareto frontier (false cutoffs, missed EOTs, p95 endpoint delay). Missed EOTs are charged at the configured timeout. The frontier is omitted if policy sample sets differ.

It does not load audio, run ASR/VAD, access a microphone, or control the live turn director. No EoT-Bench audio was downloaded or committed.

## 4. Inference speed: separate the actual bottlenecks

### I/O for LLM inference survey — July 24, 2026

Open-access paper: https://link.springer.com/article/10.1007/s10462-026-11651-1

The survey separates model-weight I/O, KV-cache I/O, and activation I/O. It describes prefill as generally compute-heavy and decode as strongly memory-bandwidth constrained, and discusses quantization, KV-cache compression, offloading, prefix caching, continuous batching, and chunked prefill.

**STAR application:**
- Preserve separate prompt-prefill and decode measurements; one tokens/sec number is insufficient.
- Benchmark cold and warm prompt-cache behavior independently.
- Sweep context length and concurrency while recording model hash, quantization, KV types, GPU layers, context size, slot count, and background load.
- Test chunked prefill only if long research prompts demonstrably stall latency-sensitive voice/game decode.
- Record host RAM, VRAM, PCIe transfer, and storage pressure before trying offload strategies.
- Keep cache isolation and session separation as correctness requirements.
- Run matched A/B experiments on STAR's actual GPU and CPU; do not transfer results from unrelated accelerators or server GPUs.

The existing `star/mixed_load_eval.py` remains the aggregate evaluator for simultaneous idle/game/stream/mixed scenarios. Run 70 does not add another scheduler or inference router.

## 5. Integrated capability architecture

Extend existing authorities:

| Existing STAR area | Responsibility |
|---|---|
| `star/play/` and `star/play/learn/` | Game adapters, practice, skill reuse and learning |
| Existing game-action gate | Authorize and cancel gameplay input |
| `star/voice/` room/turn/playback path | Capture, floor control, playback and delivery evidence |
| Existing avatar/Live2D authority | Single writer for expressions and motion |
| Existing resource-admission path | CPU/RAM/VRAM admission and priority |
| Existing memory governance | Retention, provenance, expiry and forgetting |
| New Run 70 evaluators | Offline evidence only; no runtime authority |

Do not introduce a second scheduler, voice engine, game controller, avatar writer, memory database, or model router.

## 6. Additional feature roadmap

### VTuber and streaming
- Multi-party addressee awareness and reply-chain continuity.
- Natural turn-taking with explicit false-cutoff and dead-air budgets.
- Event-driven gameplay commentary with stale-event expiry.
- Playback-grounded captions and Live2D mouth/face timing.
- Listening expressions and contextual reactions.
- Viewer safety, moderation, privacy controls, and clear AI disclosure.
- Rehearsal mode with synthetic viewers and scripted interruptions before public streaming.

### Gamer Brain
- Environment adapters with explicit observation/action schemas.
- Strategic planner plus fast reactive policy.
- Held-out maps, seeds, and opponents.
- Skill transfer, forgetting, and negative-interference tests.
- Error recovery, resource planning, navigation, combat, crafting, building, and team coordination.
- Independent objective and state verification.

### Creator Brain
- Design document as an executable acceptance contract.
- Inspect-before-edit workflows.
- Build/run/play/ending/restart/save/reload gates.
- Roblox, Godot, Unity, Unreal, and Blender-specific adapters.
- Visual regression, performance budgets, networking tests, and asset/license provenance.

### General knowledge and research
- Multi-hop source collection with provenance.
- Claim-level verification and uncertainty reporting.
- Contradiction detection and source freshness.
- Separate parametric knowledge, live web research, local project context, and user-approved memory.
- Held-out factuality tests to detect contamination and memorized benchmark answers.

## 7. Security, privacy, and reproducibility

- Evaluators retain only opaque sample/target IDs and aggregate labels.
- No transcripts, audio, video, screenshots, viewer identifiers, or account IDs are accepted.
- No third-party source code or model weights are copied.
- No datasets are downloaded by this run.
- No microphone, OBS, VTube Studio, Roblox Studio, game controller, model route, permission, scheduler, or production setting is changed.
- Keep public-stream actions, account changes, publishing, purchases, and destructive operations behind existing owner approval gates.

## 8. Validation plan and limitations

Required for this branch:
1. Run focused tests for both new evaluators.
2. Run Ruff, Pyright, and the complete offline regression suite on the exact final commit.
3. Run the desktop/Windows workflow on the exact final commit; inspect the failed install/smoke step if it recurs.
4. Confirm no test imports media, opens devices, or requires network access.

Required before runtime claims:
1. Build a read-only Roblox Studio trace adapter and compare it with the OpenGameEval task contract.
2. Run independent real-input playtests on held-out tasks/seeds.
3. Feed EoT-Bench-compatible redacted decisions from a reviewed voice adapter; do not assume dataset compatibility without checking its schema and license.
4. Run physical microphone/speaker loopback and OBS/VTube Studio rehearsal.
5. Benchmark the actual target PC under simultaneous game, inference, voice, avatar, and OBS load.

No model training, measured speedup, live gameplay mastery, public broadcast, or human-equivalent behavior is claimed by Run 70. The implementation improves evaluation coverage and makes future claims harder to fake.
