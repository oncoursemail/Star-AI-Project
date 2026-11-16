# STAR Run 58 — Memory Routing, Skill Utility, and Real-Time Agent Acceptance

**Research date:** 2026-11-15  
**Scope:** intelligence quality, long-term memory, reusable skills, real-time gaming, game creation, multiparty VTuber interaction, and local inference performance.

## Executive decision

STAR should not optimize for the largest memory, the most loaded skills, the highest raw tokens/second, or the most frequent commentary. It should optimize for **verified useful work completed within the live interaction budget**.

That means one coordinated architecture with domain-specific evidence and different time scales:

- a fast interaction loop for audio, avatar freshness, and game controls;
- a slower reasoning loop for planning, research, memory reconciliation, and game strategy;
- one resource-admission authority;
- one durable task/event spine;
- domain-specific evaluation, with promotion only after paired holdout evidence.

This run deliberately reuses existing STAR work rather than proposing a second scheduler, memory database, voice pipeline, game controller, or permission authority.

## 1. New research synthesis

### 1.1 Memory substrates should be routed by task, not standardized into one giant store

[Harness the Memory (2026-08-15)](https://arxiv.org/abs/2608.15008) evaluates dense/sparse indices, text records, structural and hierarchical stores, refinement-based memory, parametric updates, and activation-compatible context mechanisms across multiple models and benchmark suites. Its central finding is that no substrate dominates every workload. Broad retrieval can help long-context factual QA, while excessive retrieval can harm sequential decision-making by displacing action-critical context.

**STAR decision:** do not add another memory database. Add a policy layer over the existing governed memory systems that selects a retrieval profile by task class:

| Task class | Preferred evidence | Retrieval budget |
| --- | --- | --- |
| Live gameplay | Current observation, recent action/outcome, active objective | Very small; freshness-first |
| Live conversation | Current speaker/turn, recent stream events, a few relevant remembered facts | Small; privacy- and latency-first |
| General knowledge | Source-grounded documents and contradiction checks | Medium; recall-oriented |
| Long-running project | Project-scoped decisions, current task checkpoint, verified artifacts | Medium; state-oriented |
| Game creation | Project files, API docs, test/playtest evidence, visual diffs | Adaptive; tool/evidence-oriented |

The router must expose why a memory item was selected and measure retrieval cost, irrelevant-context rate, stale-memory rate, and downstream task effect. It must not silently convert unverified viewer statements into durable facts.

### 1.2 Memory quality means using the right fact to take the right action

[Mem2ActBench (ACL 2026)](https://aclanthology.org/2026.acl-long.370/) evaluates whether an agent actively applies long-term memory to tool selection and argument grounding, rather than merely answering a question about a remembered fact. Its dataset contains 2,029 synthesized sessions and 400 tool-use tasks; the authors report that 91.3% of the tasks were judged strongly memory-dependent.

**STAR decision:** evaluate memory-on versus memory-off using identical initial states and task rosters. Score:
- correct tool choice;
- exact argument grounding;
- task completion;
- stale or contradictory memory use;
- irrelevant retrieval and token cost;
- unintended side effects;
- performance on a sealed holdout.

Retrieval success alone is not an acceptance criterion.

### 1.3 A reusable skill is valuable only when it improves outcomes

[SkillFlow (2026-04-19)](https://arxiv.org/abs/2604.17308) evaluates 166 tasks across 20 families under lifelong skill discovery and evolution. It reports that a skill can be used frequently without producing meaningful task gains; some tested configurations improved substantially while others barely improved or regressed.

**STAR decision:** keep the existing versioned skill contracts, coverage evaluator, and optional SkillLibrary sidecars. Add a paired skill-on/off utility gate before promotion:
1. freeze the task roster and environment;
2. run skill-off and skill-on arms with balanced order;
3. record exact skill and model revisions;
4. measure success, behavior coverage, time, tokens, tool calls, and recovery;
5. test related-task transfer and unrelated-task interference;
6. promote only after sealed holdout review.

A skill contract is declarative guidance/evaluation data, not a permission grant or executable plan.

### 1.4 Human-like live interaction requires measuring timing and task quality together

[Full-Duplex-Bench-v3 (2026-04-06)](https://arxiv.org/abs/2604.04847) uses real human audio with disfluencies and scenarios requiring chained tool calls. It measures accuracy, latency, and turn-taking; the paper identifies self-correction handling and multi-step reasoning under difficult scenarios as persistent failure modes.

The [LiveKit End-of-Turn benchmark](https://github.com/livekit/eot-bench) provides real conversational pauses and multilingual data to distinguish a genuine end-of-turn from mid-sentence hesitation.

**STAR decision:** retain separate measurements for:
- false interruption / false cutoff;
- endpointing delay;
- first useful text;
- first audible audio;
- tool-chain correctness;
- interruption cancellation;
- answer accuracy;
- conversational appropriateness.

Do not collapse endpointing delay and model inference latency into one number. A natural VTuber should be able to listen, wait, backchannel, speak, stop, and resume without stale responses or overlapping playback. Comfortable silence is a valid behavior.

### 1.5 Game-playing must be state-verifiable and real-time

[GameWorld (2026-04-08)](https://arxiv.org/abs/2604.07429) provides 34 browser games and 170 tasks with state-verifiable outcomes. It studies direct keyboard/mouse control and semantic action parsing, and highlights latency, sparse feedback, invalid actions, context-memory sensitivity, and the gap between progress and actual completion.

**STAR decision:** maintain two coordinated control rates:
- **fast controller:** movement, camera, aim, jump, dodge, and bounded immediate reactions;
- **strategic planner:** objectives, route choice, opponent patterns, resource management, and learning between attempts.

Every action must be grounded in a fresh observation and every claimed win must be checked against environment state. Use deterministic practice scenarios and sealed levels to test transfer. Never infer mastery from progress percentage alone.

### 1.6 Game creation needs visual feedback, not code-only acceptance

[GameDevBench (ICML 2026)](https://github.com/waynchi/gamedevbench) contains 333 multimodal game-development tasks spanning 2D/3D graphics and animation, UI, and gameplay. Its paper reports that visual feedback improved one evaluated model's result from 41.1% to 52.0%.

**STAR decision:** retain separate gates for code correctness, visual correctness, scene structure, gameplay, and performance. The loop should be plan → edit → run → inspect screenshot/video → playtest → repair → verify. Use GameDevBench as an external reference; keep Roblox Studio, Luau analysis, TestService, multiplayer replication, and owner-project acceptance as the platform-specific gate.

### 1.7 Local inference needs matched workloads and live-system goodput

The official [llama.cpp SPEED-Bench guide](https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench) measures prompt/decode throughput, latency, and speculative draft acceptance. Its documentation recommends matching client concurrency to server slots and keeping the benchmark, category, output length, and sample limit identical between baseline and speculative runs.

**STAR decision:** run sequential, paired tests on the actual local model and host. Report:
- prefill tokens/s;
- decode tokens/s;
- TTFT and p50/p95/p99 response latency;
- inter-token latency;
- speculative acceptance;
- peak RAM/VRAM and CPU/GPU utilization;
- first-audible latency;
- audio callback jitter/underflows;
- game frame-time p95/p99;
- OBS dropped frames;
- verified task success.

The primary metric should be **goodput**: verified tasks completed while all voice, game, avatar, and host guardrails remain within their budgets. Raw tokens/s is diagnostic, not the product objective.

## 2. STAR architecture recommendations

### One spine, specialized brains

Keep one event/task identity and correlate ASR, room decisions, inference, tools, TTS, playback, avatar, OBS, gameplay, and verification through bounded trace IDs. Store content only in the subsystem that owns it; default telemetry should remain content-free.

| Brain | Responsibility | Acceptance evidence |
| --- | --- | --- |
| Social/stream brain | Speaker/addressee, turn-taking, humor timing, silence, memory callbacks | Multiparty replay + full-duplex holdout |
| Gamer brain | Visual state, fast controls, strategy, causal learning | State-verified wins + transfer |
| Creator brain | Project understanding, code/assets, visual feedback, playtesting | GameDevBench + Roblox-specific gates |
| Knowledge brain | Research, source provenance, freshness, contradictions | Claim-level evidence and factual holdouts |
| Memory policy | Select the smallest useful memory substrate for the task | Memory-on/off utility and cost |
| Skill Foundry | Discover, version, test, repair, and transfer reusable skills | Paired utility + behavior coverage |
| Runtime governor | Admit/cancel work under CPU/RAM/VRAM/audio/game budgets | Mixed-load p95/p99 and no protected-lane regressions |

Do not create parallel authorities for resource admission, memory persistence, voice playback, avatar writes, or game input. Existing host-owned policy components remain authoritative.

## 3. Prioritized engineering plan

### P0 — restore exact-head confidence

- Fix the structured skill-contract render budget mismatch.
- Keep the optional contract feature off by default.
- Run the complete offline suite and both Windows shards on the exact resulting commit.
- Require Pyright, Ruff, Luau template specs, desktop asset build, packaged EXE smoke test, and installer smoke test before merge.

### P1 — skill utility, not skill volume

- Add paired skill-on/off experiments to the existing skill evaluator.
- Include behavior coverage, token/tool/time cost, recovery, transfer, and negative transfer.
- Keep development and sealed holdout separate.
- Do not automatically promote a candidate skill.

### P2 — task-aware memory routing

- Reuse existing project memory, stream event memory, task ledger, and knowledge systems.
- Route by task class and deadline.
- Prefer fresh state for live control and source-grounded records for factual research.
- Measure retrieval usefulness and irrelevant-context cost.

### P3 — natural live VTuber

- Reuse the existing room director, queue, delivery ledger, full-duplex evaluation, and latest-wins avatar transport.
- Add one correlated event timeline and explicit response-generation cancellation.
- Test human-resolution stopping, short replies, disfluencies, multiple speakers, game interruptions, and comfortable silence.
- Keep avatar parameters single-writer and discard stale animation frames.

### P4 — Gamer and Creator mastery

- Reuse the existing screen-to-action gate and causal gameplay evaluator.
- Add GameWorld-style state verification and real-time timing.
- Reuse the existing Roblox Creator evaluation and add visual before/after evidence.
- Separate practice, validation, and holdout environments.

### P5 — inference and mixed-load performance

- Reuse the speculative-decoding canary, prompt-cache isolation, streaming inference benchmark, KV admission planner, and mixed-load evaluator.
- Compare one variable at a time on identical workloads.
- Reject any candidate that improves decode speed while degrading first-audible latency, frame-time, callback health, OBS, or task accuracy.

## 4. Run 58 implementation note — skill contract render budget

Exact-head GitHub Actions for PR #1209 exposed two failures in the opt-in structured skill-contract rendering tests. The sidecar parser successfully loaded the bundled contract, but the render function omitted it because the canonical dataclass serialization includes explicit optional/default fields and exceeded the 2,600-character per-contract cap.

This run:
- raises the bounded per-contract cap to 3,600 characters;
- preserves the separate 6,500-character total skill-block cap;
- preserves the explicit opt-in (STAR_SKILL_CONTRACTS=on) and default-off behavior;
- adds a regression assertion that the normalized serialized contract fits the configured cap.

This is a bounded prompt-rendering correction, not a permission change, skill executor, model change, or performance claim. Exact-head CI must confirm it.

## 5. Non-claims and release gates

- No model weights were trained or downloaded.
- No new memory database, scheduler, voice pipeline, game controller, or permission authority was added.
- No default skill, model route, OBS setting, VTube Studio setting, or game-control permission was enabled.
- No local RTX 4060 benchmark, physical microphone/audio loopback, live Roblox Studio session, or public stream was performed in this run.
- Research results from papers and upstream projects are not STAR measurements.
- PR #1209 remains a draft and must not be merged until exact-head CI and review pass.

## Sources

1. [Harness the Memory: A Holistic Evaluation of Memory Substrates in Memory Agents](https://arxiv.org/abs/2608.15008) — 2026-08-15.
2. [Mem2ActBench](https://aclanthology.org/2026.acl-long.370/) — ACL 2026.
3. [SkillFlow](https://arxiv.org/abs/2604.17308) — 2026-04-19.
4. [Full-Duplex-Bench-v3](https://arxiv.org/abs/2604.04847) — 2026-04-06.
5. [LiveKit EoT-Bench](https://github.com/livekit/eot-bench) — benchmark repository and data documentation.
6. [GameWorld](https://arxiv.org/abs/2604.07429) — 2026-04-08.
7. [GameDevBench](https://github.com/waynchi/gamedevbench) — ICML 2026.
8. [llama.cpp SPEED-Bench](https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench) — upstream benchmark methodology.
