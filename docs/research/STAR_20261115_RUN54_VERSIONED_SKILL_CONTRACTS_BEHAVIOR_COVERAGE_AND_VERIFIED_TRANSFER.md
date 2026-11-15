# STAR Run 54 — Versioned Skill Contracts, Behavior Coverage and Verified Transfer

**Date:** 2026-11-15  
**Status:** research + offline implementation proposal  
**Related acceptance:** oncoursemail/Star-AI-Project#584

## Executive finding

STAR already has several valuable pieces: portable SKILL.md loading, project-scoped lessons, a protected evaluation gate, resource admission, screen-to-game-action safety, causal gameplay evaluation, OpenGameEval result parsing, continual-learning evaluation, memory-to-tool grounding, mixed-load performance evaluation, streaming memory, OBS telemetry, and capability-gated speculative decoding.

The missing link is a common, versioned contract that states what a reusable skill requires, what it intends to do, what observable behavior it must exhibit, what state change should result, how much work it may consume, and what independent evidence supports a successful run.

Run 54 adds an offline declarative Skill Contract v1 and a behavior-coverage evaluator. It deliberately does not create a new executor, scheduler, memory database, tool policy, or skill-promotion authority.

## Research findings

### 1. Skill instructions need behavior-level evaluation

Skill Coverage: A Test Adequacy Metric for Agent Skills (arXiv:2606.20659, 2026-06-09) argues that task pass/fail does not reveal whether the agent exercised and followed the reusable constraints inside a skill. The paper extracts semi-structured behavior constraints, maps trajectories to Pass, Fail, or uncovered behavior, and reports 38.66–45.51% average constraint coverage across its evaluated leaderboard rows. Emphasizing failed constraints yielded a reported 16.0% recovery rate on those tested rows.

STAR implication:
- Give every important instruction a stable constraint ID.
- Record whether the condition was actually exercised.
- Require independent evidence for pass/fail.
- Keep not_observed separate from pass.
- Improve the exact failed instruction, not the whole prompt indiscriminately.

Paper: https://arxiv.org/abs/2606.20659

### 2. Continual learning needs dependent transfer and independent interference tests

AGENTCL (arXiv:2606.02461, 2026-06-01; revised 2026-09-26) constructs controlled task streams where earlier solutions are intentionally reusable, then contrasts them with independent tasks. The authors report that naive task streams can hide memory differences, while independent tasks reveal memory-induced degradation.

STAR implication:
- A skill must improve a later dependent task, not only repeat the task on which it was learned.
- Test independent tasks where the skill should not fire.
- Measure negative transfer, retrieval overhead and retention separately.
- Preserve the sealed holdout and do not let a skill author edit its own grader.

Paper: https://arxiv.org/abs/2606.02461

### 3. Memory structures may need domain-specific policies

ALMA (arXiv:2602.07755, 2026-02-08) explores meta-learning memory designs across sequential decision domains. Its central direction is that fixed, hand-crafted memory schemas may not be optimal for every domain.

STAR implication:
- Keep factual, episodic, causal and procedural memories distinct.
- Evaluate update/retrieval policies by domain.
- Do not let an agent-generated memory design execute in the production memory path.
- First test candidate schemas offline with fixed tasks, budgets, graders and held-out distribution shifts.

Paper: https://arxiv.org/abs/2602.07755

### 4. Reusable game skills should be compositional, but their execution must be governed

Voyager (arXiv:2305.16291, 2023-05-25) combines an automatic curriculum, an expanding skill library and iterative improvement from environment feedback in Minecraft. Its results demonstrate the value of retrieving and composing previously learned behaviors in that experimental environment.

STAR implication:
- Build skills that compose: navigate-to-object, inspect-object, interact, verify-result.
- Store preconditions and environmental assumptions.
- Retest skills in a new map/seed rather than trusting one successful trajectory.
- Keep generated behavior declarative until an approved executor and sandbox exist; STAR's current policy prohibits self-generated code from becoming automatically executable.

Paper: https://arxiv.org/abs/2305.16291

### 5. Roblox development rewards observation before editing

OpenGameEval (arXiv:2610.02563, 2026-10-01) evaluates agents in stateful Roblox Studio sessions and separates observation tools from editing tools. The paper reports 84 curated tasks, 13 evaluated models and 16 attempts per task. In its matched analysis, runs that inspected every object touched by the reference solution passed 13.4 percentage points more often on scene-only tasks and 9.8 points more often on script-only tasks than runs that inspected none.

STAR implication:
- Make observe-before-act a critical, measurable skill constraint.
- Capture target identity and pre-edit state.
- Bind each action to the exact fresh observation that justified it.
- Verify both the edited DataModel and actual play behavior.
- Use task-level and constraint-level metrics together.

Paper: https://arxiv.org/abs/2610.02563  
Open implementation: https://github.com/Roblox/open-game-eval

### 6. Portable skill documents are not security boundaries

The Agent Skills open format uses a folder with a SKILL.md, metadata and optional references/scripts/assets, and encourages progressive disclosure. That is useful for STAR's large catalog, but format validity says nothing about whether instructions are safe or whether a tool call is authorized.

STAR implication:
- Keep SKILL.md for human-readable guidance and progressive loading.
- Add the contract as an optional structured companion.
- Never interpret required_capabilities as a grant.
- Enforce actual operations through star/policy.py, the trusted host and the existing game/Studio gates.

Specification: https://github.com/agentskills/agentskills


### 7. VTuber turn-taking is a separate skill domain, not just a persona prompt

**MP-Bench** (arXiv:2609.13076, 2026-09-11; accepted to EMNLP 2026 Findings) evaluates voice agents as active participants in multi-party conversations. It separates turn-taking awareness, response appropriateness and comprehension. Its 12-agent evaluation found that real-time systems remained at or below 22% on multiparty comprehension and near chance on multiparty turn-taking.

**LiveKit EoT-Bench** evaluates whether an agent should keep listening through a mid-turn pause or take the floor after a genuine turn end. Its causal pause-level evaluation reports the trade-off between false cutoffs and endpointing latency, rather than conflating conversational timing with model inference latency.

STAR implication:
- Encode human-floor preservation, stop-on-human-resolution, addressee relevance and truthful AI identity as separate behavior constraints.
- Evaluate them on trusted replay events; a language model's own explanation is not the label.
- Keep EoT false-cutoff rate, endpointing delay, interruption precision/recall, response appropriateness and audible latency separate.
- Do not optimize for constant speech; silence and not-speaking decisions are valid outcomes.

Sources: https://arxiv.org/abs/2609.13076 and https://github.com/livekit/eot-bench


## Repository architecture audit

The current main branch already contains:

| Existing component | Preserve / use |
|---|---|
| star/agent_skills.py | Portable SKILL.md discovery and untrusted reference loading |
| star/lessons.py, star/knowledge.py | Project-scoped lesson trust and reviewed knowledge |
| star/selfbuild.py | Isolated candidate skill authoring; generated code is syntax-checked, not executed |
| star/evals.py, star/eval_gate.py | Protected benchmark definitions and promotion gate |
| star/agent_resource_planner.py | Resource-aware planning |
| Draft #1182 | Screen-to-game-action freshness/consent gate |
| Draft #1199 | Matched-state causal game mechanic evaluation |
| Draft #1200 | OpenGameEval result adapter |
| Draft #1109 | Continual-learning transfer/interference evaluator |
| Draft #1192 | Memory-to-tool argument grounding evaluator |
| Draft #1201 | Paired mixed-load streaming performance evaluator |
| Draft #1178 / #1186 / #1187 | Streamer persona, multiparty decisions and EoT evaluation |
| Draft #1202 | Long-horizon stream memory |
| Draft #1207 | Read-only OBS telemetry transport |
| Draft #1208 | Capability-gated speculative-decoding canaries |

The open PRs are independent work in progress. Run 54 does not modify their branches or duplicate their schedulers, controllers, memories or evaluators.

## Implementation added in Run 54

### star/skill_contract.py

A standard-library-only parser and validator for:
- schema-versioned skill IDs and semantic versions;
- domain classification;
- structured preconditions;
- bounded declarative steps;
- explicit tool/capability requirements (descriptive only);
- behavior constraints with critical/normal severity;
- expected state deltas;
- hard time/step/tool/token/RAM/retry budgets;
- provenance references and artifact digests;
- optional environment pin and expiry;
- execution receipts bound to the canonical contract digest;
- constraint coverage reports with pass, fail, and not_observed labels.

evaluate_skill_coverage() requires the exact constraint roster, rejects duplicate/missing labels, and requires independent evidence for pass/fail. It returns descriptive metrics and a review_recommended triage flag only when the configured coverage threshold is met with no observed failures. It does not promote the skill.

### Trust boundaries

- No generated Python, shell, Luau or tool arguments are stored in a contract.
- No code is executed.
- No permission is granted.
- No database or runtime setting is changed.
- No skill is automatically activated, trusted or promoted.
- No private game/session data or model weights are stored.
- No external requests are made by the module.

## Next integration plan

1. Add optional contract discovery beside agent_skills.py, preserving progressive disclosure and existing SKILL.md behavior.
2. Convert a small set of existing Roblox, gaming and creator skills into contracts.
3. Add a host-signed, content-minimized trace adapter that maps actual observation/action/verification events to constraint IDs.
4. Evaluate skill-off vs skill-on on dependent task streams and independent interference tasks.
5. Run OpenGameEval scene/script tasks and separate game-play transfer tests on new maps/seeds.
6. Measure skill retrieval tokens, TTFT, completion latency, tool calls, game frame-time p95/p99, OBS drops and audio underruns under mixed load.
7. Only after exact-head CI, sealed holdout, Windows host testing and owner review should a skill be considered for promotion.

## Acceptance criteria

- Every contract has a stable ID, semantic version and canonical digest.
- Every skill declares bounded preconditions, steps, behavior constraints and postconditions.
- Every request_tool step declares a tool and required capability names, but the runtime independently checks permission.
- Every claimed pass/fail constraint has independent evidence.
- Missing evidence is reported as not_observed.
- A contract update invalidates old receipts through the digest.
- A pinned environment mismatch or expired contract blocks receipt reuse.
- No skill is promoted from development-only coverage.
- A new skill must improve dependent transfer without harming independent tasks.
- No streaming, gameplay, OBS or GPU performance claim is made without a paired mixed-load measurement.

## Sources

- Skill Coverage: https://arxiv.org/abs/2606.20659
- AGENTCL: https://arxiv.org/abs/2606.02461
- ALMA: https://arxiv.org/abs/2602.07755
- Voyager: https://arxiv.org/abs/2305.16291
- OpenGameEval: https://arxiv.org/abs/2610.02563
- OpenGameEval code: https://github.com/Roblox/open-game-eval
- Agent Skills specification: https://github.com/agentskills/agentskills


## Run 55 research addendum — lifelong skill utility, game completion, and capability transfer

**Research date:** 2026-11-15. This addendum extends the original contract design; it does not claim that the external benchmarks have been run against STAR.

### 1. Skill usage is not skill value

**SkillFlow** evaluates lifelong skill discovery and evolution over 166 tasks in 20 task families. Its reported results show why STAR must not use skill-selection frequency as a success metric: one evaluated system gained 8.43 percentage points from lifelong skill evolution, while another showed only 0.60 points despite using skills frequently; another configuration regressed against its no-skill baseline.

STAR consequence:

- Record skill-off and skill-on results on matched task families.
- Track per-skill success uplift, latency, tokens, tool calls, repair rate, and regression rate.
- Separate dependent transfer (where the prior skill should help) from independent tasks (where it should not).
- Retain a skill only when its measured utility is positive on sealed holdouts and it does not cause unacceptable interference.
- Measure discovery, patching, repair, reuse, and library coherence—not just whether a skill was selected.

Source: https://arxiv.org/abs/2604.17308

### 2. General game-playing needs both progress and task closure

**GameWorld** covers 34 browser games and 170 tasks across runner, arcade, platformer, puzzle, and simulation genres. It uses serialized game state to calculate normalized progress and binary success rather than relying on screenshot heuristics or an LLM judge. Its published results show a material gap between progress and completion; the site also separates its real-time track from its paused track.

STAR consequence:

- Report normalized progress and completed-task success separately.
- A run at 90% progress is not a win.
- Record the exact objective, action budget, reset state, game build, and evaluator version.
- Include timing-sensitive tasks, spatial navigation, recovery, and long-horizon coordination.
- Keep paused and real-time evaluation results in separate cohorts.
- Use an environment-provided state oracle only for evaluation; do not expose hidden evaluator state to the acting agent.

Source: https://gameworld-bench.github.io/  
Paper: https://arxiv.org/abs/2604.07429

### 3. Game creation is a distinct capability from game playing

**GameDevBench** evaluates 333 Godot game-development tasks spanning 2D graphics, 3D graphics, UI, and gameplay. Its public results emphasize that visual feedback matters and that the more visually demanding categories remain harder. It is a useful general creator benchmark, but it is not a substitute for Roblox Studio/Luau tests.

STAR consequence:

- Maintain separate Creator Brain scores for code correctness, visual correctness, scene structure, runtime behavior, and performance.
- Use screenshots/video as observations, not as proof of hidden scene structure.
- Verify the saved project and executable play result.
- Pin the engine version, benchmark revision, task subset, and test harness.
- Keep Roblox-specific acceptance in Studio/OpenGameEval and use GameDevBench only as a cross-engine comparison.

Sources:
- https://waynechi.com/gamedevbench/
- https://github.com/waynchi/gamedevbench
- https://arxiv.org/abs/2602.11103

### 4. Externalized reflective learning is promising, but requires governance

**Memento-Skills** studies a read/write reflective loop in which agents route to reusable skills, then revise or add skill artifacts from experience without changing foundation-model weights. This is a useful model for local-first adaptation, but it does not remove the need for evidence, review, or rollback.

STAR consequence:

- Keep the read path selective and token-budgeted.
- Make the write path propose versioned candidate patches only.
- Require reproducible tests, provenance, dependent transfer, independent interference checks, and rollback before promotion.
- Keep model-generated skill text non-executable and separate from runtime authorization.

Source: https://arxiv.org/abs/2603.18743

### 5. Streaming naturalness must be measured at pauses, not guessed from transcript text

LiveKit's **EoT-Bench** provides aligned speech/context with pause-level annotations across 14 languages. It distinguishes mid-turn hesitation from a true end of turn, which is directly relevant to avoiding premature VTuber interruptions.

STAR consequence:

- Evaluate false cutoffs, missed final turns, p95 decision latency, and language-specific results.
- Keep silence/hold decisions separate from speech-generation latency.
- Do not use generated text as evidence that playback finished.
- Preserve actual silence as an acceptable action.
- Keep multiparty speaker identity session-scoped and avoid building persistent viewer profiles by default.

Source: https://github.com/livekit/eot-bench

### 6. Inference speed must be benchmarked at the server's real concurrency

The upstream **llama.cpp SPEED-Bench** client evaluates an already-running server and reports category-level throughput, latency, and speculative-draft acceptance. Its documentation recommends matching client concurrency to the server's configured parallel slots.

STAR consequence:

- Compare identical model weights, quantization, prompt, context, generation settings, and host conditions.
- Match concurrency to actual server slots; do not inflate it to manufacture throughput.
- Report first-content latency, TTFT, decode/inter-token latency, throughput, acceptance, and memory pressure separately.
- Repeat under gaming + OBS + voice load.
- Reject an optimization if task quality, audio continuity, or game frame-time tails regress—even if tokens/second rises.

Source: https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench

### 7. Unified capability scorecard for STAR

Do not collapse STAR into one self-reported “intelligence” number. Maintain a versioned scorecard with independent evidence for:

| Capability | Evidence to require |
|---|---|
| General knowledge | Source-grounded accuracy, freshness, calibration, contradiction handling |
| Research | Claim-level provenance, reproducibility, uncertainty, source diversity |
| Game playing | Progress, completion, control latency, recovery, held-out transfer |
| Game creation | Build validity, visual/structural checks, playable result, performance |
| Memory | Correct retrieval, action grounding, temporal updates, forgetting, privacy |
| Skill learning | Matched skill uplift, repair success, dependent transfer, independent interference |
| Streaming | Turn timing, groundedness, spoken-task accuracy, audio continuity, viewer-event moderation |
| Avatar | Audio-to-mouth sync, frame age, expression appropriateness, dropped/coalesced frames |
| Inference | TTFT, first audible, inter-token latency, throughput, CPU/RAM/VRAM, cost per verified task |

Each score must identify its benchmark version, task split, environment fingerprint, evidence source, and sample size. Missing evidence is inconclusive, not zero and not a pass.

### 8. Integration map and next engineering order

The repository already has focused draft work for causal gameplay probes (#1199), Roblox Creator evaluation (#1200), paired stream/model evaluation (#1166), spoken-task and long-form voice quality (#1165), end-of-turn evaluation (#1187), speculative decoding (#1208), and versioned skill contracts (#1209). Do not create parallel schedulers, memory stores, voice pipelines, or game controllers.

Next, in order:

1. Fix and pass exact-head CI for this contract PR.
2. Add a trusted-host adapter that maps minimized, real action/observation/verification events to contract constraints.
3. Connect skill contracts to the existing candidate-skill and promotion workflow only after independent review.
4. Add SkillFlow-style matched skill-off/skill-on dependent-transfer and independent-interference cohorts.
5. Add a GameWorld-compatible result adapter only if no existing branch already owns that schema.
6. Run GameDevBench-style creator tasks alongside Roblox-specific Studio evaluations.
7. Run the private VTuber rehearsal with EoT/MP-Bench-derived measures and real OBS/audio/avatar telemetry.
8. Run paired inference and mixed-load tests before changing any model or scheduler defaults.

**Implementation boundary:** this addendum is research and acceptance guidance. It does not enable skills, run games, change voice behavior, launch OBS, control VTube Studio, change inference defaults, or claim a hardware performance gain.
