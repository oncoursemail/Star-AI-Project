# STAR Run 45 — Causal Game Learning, Runtime-Verified Creation, and Quality-Adjusted Intelligence

**Research date:** 2026-11-15  
**Implementation:** `star/causal_game_probe.py`  
**Branch:** `feat/causal-game-probe-eval-20261115-run45`  
**Status:** offline randomized-probe evaluator and source-linked integration plan; no live game control, model training, streaming, or automatic skill promotion.

## Executive finding

STAR already has a substantial game-learning stack:

- `star/game_mechanic_probe_lab.py` proposes balanced practice actions from signed practice aggregates, but explicitly states that its observations are **not causal** because level seeds, player skill, learning, and time can confound the comparison.
- `star/gameplay_skill_bank.py` stores scoped, signed practice and validation outcomes.
- `star/game_transfer_eval.py` evaluates candidate skills on preregistered held-out game situations.
- `star/game_closed_loop.py` defines a one-step observation/action protocol but does not own the actual controller.
- `star/game_skill_promotion.py` separates practice from held-out promotion evidence.
- `star/stream_realtime_benchmark.py`, `star/inference_benchmark.py`, `star/inference_ab.py`, and `star/prefill_warm.py` already cover important parts of local performance measurement and prompt-cache warming.

The specific missing link is **controlled causal attribution**: when STAR tries two actions, can she distinguish the action's effect from environmental drift, starting-state differences, order effects, or a changing player/agent skill level?

Run 45 adds a separate randomized matched-start-state evaluator. It complements the existing practice bank and transfer evaluator; it does not replace either, add another game controller, or automatically write a skill.

## 1. OnlineWM — learn action effects, not visual correlations

Primary source: https://onlinewm.github.io/  
Paper: https://arxiv.org/abs/2609.23753

OnlineWM identifies two important weaknesses in static world-model training:

1. A fixed dataset can stop matching the model's current prediction errors.
2. An observational prediction objective can exploit correlations that do not represent the effect of an action.

Its proposed loop actively queries a simulator for informative trajectories, then contrasts different actions from the same conditioning state. The paper reports action-controllability and held-out Minecraft-sequence evaluations; its public project page says code is forthcoming, so this is a research pattern, not a dependency STAR can install today.

### STAR application

For a controlled mechanic experiment:

- Hold game build, objective, starting-state digest, tool policy, and scoring definition fixed.
- Compare two predeclared symbolic actions from the same reset state.
- Randomize which action is attempted first.
- Keep the full assignment seed hidden from the agent until the campaign ends.
- Record independently observed state/effect evidence.
- Re-run on different reset states and held-out maps/seeds.
- Store the result as a scoped candidate, not a universal game rule.

Examples:
- Short jump versus long jump across the same gap.
- Walk versus dash over a fixed distance.
- Two camera sensitivities against the same aiming task.
- Two interaction ranges against the same target.
- Two resource-gathering routes from the same spawn state.

A successful experiment establishes evidence only for its declared game build, mechanic, objective, and scope.

## 2. CausalGame — test whether STAR can reason about confounding

Primary source: https://proceedings.mlr.press/v306/chen26l.html  
Project: https://causalgame.github.io/

CausalGame (ICML 2026 / PMLR 306) evaluates agents that design experiments, gather observations, and explain causal conclusions. Its 14 game settings include hidden confounders, selection bias, and noisy measurements. The paper reports that the 29 evaluated frontier agents consistently struggled to recover the underlying causal relationships.

### STAR's required adversarial curriculum

Add synthetic evaluation cases for:

- **Hidden confounder:** a hidden difficulty variable affects both action choice and success.
- **Selection bias:** only successful or completed runs are retained.
- **Order effect:** the second attempt benefits from learning or suffers fatigue.
- **Environmental drift:** hazards, timers, or NPC states change between attempts.
- **Measurement noise:** the observer occasionally misclassifies a success or score.
- **Regression to the mean:** a strategy is tested only after an unusually bad run.
- **Survivorship bias:** failed runs disappear from the experience log.
- **Policy leakage:** the model sees future assignment order or holdout labels.

STAR should have to identify when evidence is insufficient and request a better experiment. A plausible causal story is not a result.

## 3. New implementation — randomized matched-start-state probe evaluator

New module: `star/causal_game_probe.py`  
Tests: `tests/test_causal_game_probe.py`

### What it implements

- A frozen experiment manifest with game/build/objective/action scope.
- A precommitted SHA-256 digest of the matched-start-state roster.
- A separate commitment to a host-only randomization seed.
- Deterministic HMAC-derived assignment order, balanced within each block.
- Per-pair assignment digests binding the exact pair, start-state digest, and action order.
- Host-HMAC-signed outcome receipts.
- Exact action/order verification for both attempts in each pair.
- Stale/future timestamp rejection and bounded pair-gap checks.
- Duplicate trial/run rejection.
- Matched start-state digest verification.
- Pair-level score effects and block-level sign testing.
- Independent-block and per-stratum regression checks.
- An inconclusive result for missing pairs or insufficient independent blocks.

The primary score is a bounded integer in 0..1000. The report separates average/median score effect, block consistency, and baseline/candidate success rates.

### Why blocks matter

Twenty-four pairs collected from one block are not twenty-four independent replications. The evaluator uses the block as the sign-test unit, requires a minimum number of independent blocks, and reports block/stratum regressions separately. This avoids allowing a large number of highly correlated attempts to create false confidence.

### Trust boundary

The evaluator cannot prove that the game was actually reset correctly. A matching state hash is only as trustworthy as the host that measured it. HMAC authenticates a report from a key holder; it does not prove that the sensor, game adapter, or scorer was honest.

Therefore:
- The host must own game reset, action execution, observation, and signing.
- The randomization seed must remain outside the model/tool worker and be revealed only after the campaign.
- The host should expose one assignment at a time, not the future plan.
- The manifest digest must be recorded in an independently timestamped log before the first trial.
- A positive result only becomes `eligible_for_owner_review`; it does not promote a skill or authorize game input.

## 4. GameWorld — evaluate actual game completion, not convincing narration

Primary source: https://gameworld-project.github.io/  
Code: https://github.com/gameworld-project/GameWorld  
Paper: https://arxiv.org/abs/2604.07429

GameWorld covers 34 browser games and 170 tasks across runner, arcade, platformer, puzzle, and simulation genres. It supports computer-use and semantic-action interfaces, with task outcomes read from serialized game state rather than relying only on screenshots or an LLM judge. Its real-time track keeps the environment moving during inference; that track must be reported separately from paused evaluation.

The public leaderboard snapshot observed on 2026-11-15 shows a substantial gap between current agent progress/success and the novice-player baseline. This is a useful warning: partial progress is not mastery.

### STAR benchmark tracks

- **Paused reasoning:** isolate planning quality from reaction latency.
- **Slowed control:** evaluate a bounded real-time budget.
- **Real-time control:** environment continues advancing during inference.
- **State-verified completion:** score the actual objective state.
- **Transfer:** new maps, seeds, builds, and task wording.
- **Recovery:** measure whether the agent recovers from mistakes without unsafe actions.

Report task success, normalized progress, invalid actions, timeouts, action latency, recovery, and resource cost separately.

## 5. SIMA 2 — generalist visual control and transferable skills

Primary source: https://deepmind.google/blog/sima-2-an-agent-that-plays-reasons-and-learns-with-you-in-virtual-3d-worlds/

SIMA 2 is a useful reference for combining visual observation, language goals, reasoning, and grounded action in 3D worlds. The key lesson for STAR is to organize gameplay as reusable primitives and subgoals rather than one memorized key sequence.

### STAR's cross-game skill contract

Each learned skill should carry:

- Supported game/build and control mapping.
- Preconditions and observable state cues.
- Goal and expected state change.
- Action primitive and timing budget.
- Failure signatures and recovery path.
- Evidence provenance and scorer version.
- Practice history and held-out transfer results.
- Expiration/invalidation conditions.

Transfer should be attempted only after STAR verifies that the relevant mechanics are equivalent. Two games that look alike may have different physics, cooldowns, hitboxes, or server authority.

## 6. Roblox Creator Brain — games are systems verified by play

Official Roblox sources:

- https://about.roblox.com/newsroom/2026/11/building-the-next-era-of-creation-on-roblox
- https://about.roblox.com/newsroom/2026/04/roblox-studio-going-agentic

Roblox's 2026-11-13 creator update emphasizes that a game is a system of interdependent scripts, physics, UI, server logic, and multiplayer state; it is verified by playing, not by inspecting a file or screenshot alone. Roblox's Studio agentic direction adds plan/build/test workflows and an integrated MCP surface.

### STAR's required creator loop

1. Inspect the current project and establish the exact project/build identity.
2. Produce a requirement manifest with explicit acceptance tests.
3. Build in an owner-approved disposable/test place.
4. Run static checks and deterministic tests.
5. Launch a Studio playtest with a bounded robot/player scenario.
6. Inspect logs, DataModel state, and actual behavior.
7. Capture evidence for each requirement.
8. Patch the smallest failing component.
9. Replay the same case and run regression/holdout variants.
10. Deliver the project artifact and evidence summary.

Separate robotic Studio playtests from visual screen-controlled gameplay. A Studio test agent does not prove STAR can play a retail game through screenshots and keyboard/mouse input.

## 7. Human-like VTuber streaming — preserve the single authorities

LiveKit EoT-Bench: https://github.com/livekit/eot-bench  
Roblox Studio agentic workflow: https://about.roblox.com/newsroom/2026/04/roblox-studio-going-agentic

Run 45 does not create a second voice stack. The existing work already separates end-of-turn detection, multiparty addressee/floor reasoning, room decisions, playback, and avatar transport.

The next integrated rehearsal should combine:
- A viewer asking a question.
- Another viewer answering first.
- A relevant prior topic.
- A gameplay event with a short reaction deadline.
- A mid-sentence pause that is not the end of the turn.
- A true barge-in that must stop current playback.
- An avatar expression that follows the actual audio playback clock.

Measure end-of-turn false cutoffs, missed finals, addressee precision/recall, unwanted responses, appropriate silence, first audible latency, interruption recovery, avatar sync error, and long-session grounding separately.

A good streamer does not talk constantly. Silence, listening, and not stealing another viewer's conversation are valid successful actions. STAR should be transparent that she is an AI and must not invent human autobiography or fake experiences.

## 8. Faster intelligence — quality-adjusted goodput under mixed load

Existing STAR foundations to reuse:

- `star/inference_benchmark.py`: measured local request latency and throughput.
- `star/inference_ab.py`: paired local inference experiments.
- `star/prefill_warm.py`: optional local prompt-cache warming while the owner types.
- `star/stream_realtime_benchmark.py`: same-clock first-audio and game-frame measurements.
- Existing resource-admission and stream-pressure work in the open #1140/#1142 chain.

NVIDIA AIPerf metric reference: https://docs.nvidia.com/aiperf/reference/ai-perf-metrics-reference  
llama.cpp server: https://github.com/ggml-org/llama.cpp/tree/master/tools/server

Do not optimize only decode tokens/second. The useful measure is verified work completed per second while voice, gameplay, avatar, and OBS remain responsive.

Measure:
- Queue wait and model-load time.
- Prompt assembly, retrieval, and prefill time.
- Time to first token and first audible PCM.
- Inter-token latency and output throughput.
- Cache hit/reuse and speculative acceptance.
- Task success and argument correctness.
- CPU, RAM, and per-process VRAM.
- Game frame-time p95/p99 and OBS dropped frames.
- Audio underflows, speech backlog, and interruption latency.
- Background work admitted/deferred during the live session.

On an 8 GB GPU, protect the foreground game/OBS/avatar/audio budget first. Keep one primary model resident where possible; use a small draft model only when measured acceptance and end-to-end latency improve for the specific task. Cache affinity should keep a conversation on the model slot that owns its warm prefix when that reduces prefill without creating unfair queueing. Model swapping is a latency event and must be measured, not hidden.

Never enable a speculative-decoding mode globally based on one coding benchmark. Compare by workload class, warm/cold state, and concurrent load. A higher token rate that increases audible latency or causes frame drops is a regression.

### 8.1 AIPerf goodput and llama.cpp router implications

AIPerf defines goodput as completed requests per second that meet **all configured service-level objectives**, not raw throughput. Its TTFT includes network, queueing, prompt processing, and first-token generation; TTFO distinguishes the first non-reasoning output from a reasoning token. ITL is a decode average and should be read alongside request latency, output length, and chunk-jitter distributions. References:

- https://docs.nvidia.com/aiperf/reference/ai-perf-metrics-reference
- https://docs.nvidia.com/aiperf/tutorials/metrics-analysis/benchmark-goodput-with-ai-perf

For STAR, define separate SLOs for:
- First audible PCM for a short streamer reaction.
- First useful text token for a foreground answer.
- p95/p99 completion latency for a bounded tool task.
- Game frame-time and OBS dropped-frame limits during that task.

Count only requests that satisfy every applicable SLO as goodput. Include failed/cancelled requests in the denominator so overload cannot appear faster by silently dropping work.

The current llama.cpp server documentation exposes a router with model-count limits and optional memory-based LRU unloading. With `--models-memory-margin`, it measures each model's minimum/maximum device requirements and unloads idle models until the requested model fits while keeping the configured device-memory margin; a model serving a request is not unloaded. The docs explicitly warn that host RAM is assumed unlimited and multimodal projector memory is not yet included in the estimates. See https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md#memory-based-unloading.

STAR should therefore test router mode only as an opt-in experiment:
1. Pin exact llama.cpp build, model hashes, quantization, context, slots, and device placement.
2. Keep the foreground voice/chat model resident during live rehearsal.
3. Permit LRU eviction only for idle background models.
4. Reserve extra VRAM beyond router estimates for mmproj, OBS, avatar rendering, capture, and transient allocations.
5. Measure model-load/unload latency and cache loss as part of end-to-end latency.
6. Reject a configuration if first-audio latency, p99 frame-time, audio underflows, or task success regresses.

Prompt caching, cache reuse, idle-slot caching, context checkpoints, KV-cache quantization, CPU/GPU layer placement, and speculative decoding are separate experimental variables. Change one at a time, use paired warm/cold trials, and retain the simplest configuration that improves quality-adjusted goodput.

## 9. General knowledge and creator capability

Reuse STAR's existing general-knowledge lab, knowledge practice host, source grounding, and skill retrieval. Do not create another memory database.

Each reusable knowledge card should carry:
- Claim and scope.
- Primary source(s), retrieval date, and source revision.
- Supporting and contradictory evidence.
- Confidence and known uncertainty.
- Freshness/expiry policy.
- A practical task or test that demonstrates understanding.

Evaluate factual accuracy, source grounding, freshness, contradiction handling, and practical application separately. A memorized answer is not proof that STAR can perform the procedure.

## 10. Run 45 acceptance gates

1. Exact-head Python tests, Ruff, Pyright, and GitHub Actions pass.
2. The pre-run manifest digest is independently timestamped before assignment.
3. Assignment seed and future pair order remain host-only until the campaign ends.
4. The host independently verifies reset-state equality and game outcomes.
5. All preregistered pairs are complete; missing data is inconclusive.
6. At least the configured number of independent blocks is represented.
7. Block and stratum regression checks pass.
8. A positive practice result is evaluated again on untouched game builds/maps/seeds.
9. Skill promotion still uses the existing independent held-out promotion gate.
10. No live stream, public broadcast, game publication, or permission change follows from a benchmark pass.

## 11. Explicit limitations

This PR adds a pure offline assignment/evaluation protocol. It does not connect to a game, capture screenshots, reset a game, execute input, train a world model, import GameWorld/CausalGame/OnlineWM code or datasets, modify the gameplay skill bank, promote a skill, or enable a live stream. No measured STAR intelligence gain, gameplay mastery, inference speedup, naturalness improvement, Windows acceptance, or production readiness is claimed.

The next host-side step is a disposable deterministic game adapter that can reset to a recorded state, apply one symbolic action, collect independently verified state deltas, and sign receipts. Only after that exists can STAR run a real causal-learning pilot.
