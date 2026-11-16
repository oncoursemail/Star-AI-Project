# STAR Run 60 — Integration Gates, Long-Horizon Reliability, and Real-Time Capability Acceptance

**Research date:** 2026-11-15  
**Branch:** research/run60-integration-gates-long-horizon-20261115  
**Target integration branch:** star/next  
**Status:** research and integration plan; no runtime behavior changed in this run

## Executive decision

STAR has accumulated a broad set of valuable draft capabilities: governed voice rooms, natural streamer persona, a durable task/communication ledger, long-horizon stream memory, game-action freshness gates, Roblox evaluation, causal game probes, OBS telemetry, mixed-load performance evaluation, KV-residency planning, speculative-decoding canaries, memory-to-tool evaluation, and versioned skill contracts.

The highest-value next step is **integration and acceptance, not another parallel subsystem**.

This run consolidates current research into one practical integration order and a capability scorecard. It adds fresh source audits for:

- LiveKit EoT-Bench v1.1, updated 2026-11-13;
- the October 2026 OpenGameEval paper and its 84-task Roblox Studio evaluation;
- WindowsWorld's 181 cross-application desktop tasks;
- the Agent Memory Leaderboard's textual, multimodal, coding, governance, and privacy dimensions;
- long-horizon reliability curves and failure accumulation;
- current llama.cpp speculative-decoding modes and SPEED-Bench requirements;
- Google Research's TurboQuant KV-cache compression work.

The plan deliberately reuses the open STAR work. It does not add a second voice engine, scheduler, memory database, task ledger, OBS client, avatar writer, or game-control authority.

## 1. Current product baseline and honest capability boundary

The inspected main README describes STAR v1.0 as a local-first Windows 11 desktop assistant with:

- a local 4B model path for a machine with about 8 GB of VRAM;
- an optional larger CPU-only STAR Server;
- saved chats, screen capture on explicit request, image generation through optional ComfyUI, and optional web search;
- Roblox documentation retrieval, Luau checkers, and opt-in Roblox Studio access;
- 300 server-side practice tasks and a reviewed learning workflow;
- basic optional voice calls, while the richer streamer voice experience remains in development.

The README also says the v1.0 learning bundle is empty and that its model weights are not retrained by the lesson loop. The current general-foundations smoke suite is not a broad general-knowledge benchmark. Therefore:

1. A draft PR is not a shipped feature.
2. A passing unit test is not proof of live hardware integration.
3. More stored lessons are not proof that the model became more intelligent.
4. A generated Roblox place is not a successful game until play behavior and state are verified.
5. A voice persona prompt is not natural multiparty conversation without trusted speaker/addressee and turn-control signals.

STAR should make claims only from the latest published release, exact-head CI, and separately observed native acceptance.

## 2. New research findings

### 2.1 EoT-Bench v1.1: current multilingual turn-taking evidence

LiveKit's EoT-Bench repository and leaderboard were updated on 2026-11-13. The public set contains 7,342 human-to-agent turns across 14 languages. Silences of at least 100 ms are labelled as either a true end-of-turn or a mid-turn hold. The v1.1 English results pool general, accented-English, and short-turn cohorts.

The benchmark evaluates causal decisions at pauses and exposes a Pareto frontier between false cutoffs and response delay. Its key lesson is that endpointing delay is not model inference latency. A fast LLM can still feel rude or sluggish if the turn detector takes the floor too early or waits too long.

STAR decisions:

- Keep endpointing, ASR, model TTFT, TTS first-packet, and actual playback-start as separate measurements.
- Re-run the adapter against the exact v1.1 dataset and evaluation contract; do not reuse an earlier cohort score as if it were the new version.
- Preserve right-censored HOLD-only examples as censored observations. Never invent a true endpoint or endpoint latency for them.
- Report false-cutoff rate and endpointing delay together at multiple operating budgets.
- Evaluate short acknowledgements, hesitation, accented English, multilingual turns, background speech, and long pauses separately.
- Add a production-like room track with overlapping speakers and addressee changes; the public EoT dataset alone does not test all multiparty social reasoning.

Sources:
- https://github.com/livekit/eot-bench
- https://livekit.com/benchmarks/eot-bench

### 2.2 OpenGameEval: the Roblox benchmark has moved beyond the original small suite

The October 1, 2026 OpenGameEval paper describes 84 human-curated core tasks in reproducible stateful Roblox Studio sessions, with 16 attempts per task across 13 evaluated models. The framework separates observation tools from editing tools and checks both the edited scene and a simulated play session.

The paper reports a best single-attempt pass rate of 51.7% and a best five-of-five consistency result of 39.4% among the evaluated systems. It also reports that inspecting every relevant object before acting was associated with higher pass rates in matched analyses. These are benchmark results for the evaluated models, not STAR results.

STAR decisions:

- Pin the exact OpenGameEval release, task roster, place files, plugin revision, evaluator revision, model, prompt, and attempt count.
- Report pass@1, pass@k, consistency/all@k, tool errors, observation coverage, and scene-versus-play failures separately.
- Preserve EDIT and PLAY mode evidence. A task that only passes scene checks but fails play checks is not a completed game task.
- Require inspect-before-edit behavior where the task depends on unknown DataModel state.
- Keep development, validation, and sealed holdout places/seeds separate.
- Use the benchmark as an external adapter; keep STAR's own Roblox-specific acceptance suite for tasks not covered by OpenGameEval.

Source:
- https://arxiv.org/abs/2610.02563
- https://github.com/Roblox/open-game-eval

### 2.3 WindowsWorld: cross-application autonomy is much harder than single-app clicking

WindowsWorld contains 181 tasks across 17 desktop applications, with an average of five subgoals per task; 78% require multiple applications. The paper reports that tested GUI agents achieved less than 21% success on multi-application tasks and struggled with conditional decisions across three or more applications.

STAR decisions:

- Add a cross-application acceptance track, not just single-window click tests.
- Grade intermediate checkpoints and final artifacts, not screenshots alone.
- Test recovery after application restart, lost focus, modal dialogs, changed layouts, and partial completion.
- Require state inspection before a destructive or irreversible step.
- Use a disposable VM and synthetic accounts/files for benchmark runs.
- Record task completion, artifact correctness, recovery, step count, elapsed time, and unnecessary actions.

This is a strong general-computer-intelligence target for STAR's desktop automation and creator workflows.

Source:
- https://aclanthology.org/2026.findings-acl.750/
- https://arxiv.org/abs/2604.27776

### 2.4 Agent Memory Leaderboard: evaluate governance and execution, not only recall

The Agent Memory Leaderboard publishes separate textual, multimodal, and coding-memory tracks. Its public description covers more than ten datasets, over 1,500 histories/tasks, and nearly 5,000 evaluation questions, with dimensions including explicit fact recall, compositional inference, temporal/event reasoning, memory governance, personalization/care, context learning/execution, and safety/privacy.

STAR decisions:

- Keep the existing memory stores and policies; use this as an external evaluation protocol, not a reason to install another memory database.
- Evaluate whether a memory is useful, current, correctly scoped, and safe to retrieve.
- Measure temporal contradiction resolution, stale-memory handling, irrelevant-memory injection, and memory-to-tool argument accuracy.
- Test whether a remembered fact is actually applied to the correct action.
- Include privacy, retention, consent, deletion, and cross-project isolation tests.
- Do not submit private histories, viewer messages, transcripts, credentials, or internal prompts to public benchmark services.

Sources:
- https://agentmemories.ai/docs
- https://github.com/AML-memory/agent-memory-leaderboard

### 2.5 Long-horizon reliability: success probability decays as dependent steps accumulate

The Reliability Science Framework argues that pass@1 on short tasks can hide failures that emerge as task duration and dependency count increase. It proposes reliability decay curves, variance amplification, graceful-degradation scores, and a meltdown-onset point. A separate long-horizon degradation study reports that even strong agents can fall sharply as the number of dependent steps grows.

STAR decisions:

- Measure the same task family at increasing horizons, such as 1, 4, 8, 16, and 32 dependent steps.
- Report per-task repeatability and success-by-horizon, not only one aggregate pass rate.
- Preserve checkpoints and verified artifacts so a failure does not erase already completed work.
- Classify failure as planning, stale observation, tool error, state drift, context loss, resource starvation, timeout, or verifier mismatch.
- Measure recovery after interruption, process restart, network loss, and model cancellation.
- Never allow the agent to mark a task complete without the external verifier and required evidence.

Sources:
- https://arxiv.org/abs/2603.29231
- https://arxiv.org/abs/2609.01660

### 2.6 llama.cpp: speculative decoding needs exact capability and matched-load evidence

The current upstream llama.cpp documentation lists multiple speculative-decoding families, including draft models, EAGLE-3, DFlash, DSpark, MTP, n-gram cache, simple n-gram, map-k, map-k4v, and ngram-mod. The upstream SPEED-Bench client reports latency, throughput, and draft acceptance. Its documentation recommends matching client concurrency to the server slot count.

STAR decisions:

- Keep the existing capability-gated canary; do not enable a mode because it appears in upstream documentation.
- Inspect the exact installed llama-server binary's help output and version before constructing flags.
- Confirm the runtime actually enters speculative mode and emits draft/acceptance telemetry.
- Compare identical prompt categories, output lengths, model hashes, server slots, cache state, and concurrency.
- Measure first-token latency, inter-token latency, output throughput, acceptance, p50/p95/p99, and end-to-end user-perceived latency.
- Test interactive one-slot streaming separately from background multi-agent workloads.
- Reject any candidate that improves isolated tokens/second but worsens voice, gameplay, or mixed-load tail latency.

Sources:
- https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md
- https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench

### 2.7 TurboQuant: promising KV compression, not a drop-in STAR optimization

Google Research introduced TurboQuant, QJL, and PolarQuant on 2026-03-24 as quantization methods intended to reduce memory overhead in high-dimensional vectors and LLM KV caches.

This is relevant to STAR's constrained local inference budget, but the paper/blog result does not establish that the current llama.cpp build, model format, or STAR runtime supports TurboQuant directly.

STAR decisions:

- Treat TurboQuant as a research candidate, not an available command-line switch.
- First inspect upstream implementation status and supported backends.
- If a compatible implementation becomes available, test exact model/task quality, long-context retrieval, cache memory, prefill/decode latency, and concurrency.
- Keep a full-precision or current supported cache baseline for paired comparison.
- Do not trade away Roblox code correctness, factuality, or tool-argument accuracy for a smaller cache.

Source:
- https://research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression/

## 3. Repository integration audit — reuse the current PR fleet

The following open PRs were inspected through GitHub search on 2026-11-15. They are separate draft/integration candidates, not features shipped in the v1.0 installer.

| PR | Existing work | Integration role |
|---|---|---|
| #1140 / #1142 | Authoritative multi-resource admission and stream-pressure composition, referenced by #1178 | One scheduler and one admission authority |
| #1151–#1153 | Host telemetry, coherent sampling windows, freshness/skew checks | Trusted live metrics |
| #1175 / #1176 | Voice room host and room response dispatcher | Trusted room ingress and bounded delivery |
| #1177 | Durable task and communication ledger | Checkpoints, leases, evidence and report obligations |
| #1178 | Natural streamer persona, human-resolution stop semantics, voice research | Social/turn behavior and persona |
| #1182 | Fail-closed screen-to-game-action gate | Fresh-frame, authorized game input |
| #1187 | EoT-Bench adapter | Voice endpointing evaluation |
| #1192 | Memory-to-tool parameter grounding evaluator | Prove memory changes actions correctly |
| #1199 | Randomized matched-state causal mechanic probes | Learn game action effects |
| #1200 | OpenGameEval result/exploration adapter | Roblox Creator evaluation |
| #1201 | Paired mixed-load streaming performance evaluator | Quality-adjusted speed A/B |
| #1202 | Hour-scale stream continuity memory | Governed event recall |
| #1205 | KV-residency session admission planner | Future backend/session memory planning |
| #1207 | Authenticated local OBS telemetry collector | Read-only stream measurements |
| #1208 | Capability-gated speculative-decoding canaries | Inference experimentation |
| #1209 | Versioned skill contracts and behavior coverage | Skill specification and evidence |

### Integration constraints discovered

1. #1178 explicitly identifies #1140/#1142 as the single resource scheduling path. Do not introduce a second ALLOW/DEFER authority.
2. #1177 is stacked on the voice-room work. Keep task completion separate from communication/playback completion.
3. #1207 is stacked on the coherent host-sampling chain. Do not bypass the freshness and sampling-window checks.
4. #1201 should consume trusted telemetry and compare matched workloads; it should not become another resource scheduler.
5. #1202 is an event-memory substrate, not a reason to add a competing conversation database.
6. #1182 remains the authority for permitted screen-to-controller actions. Model output must not bypass it.
7. #1200 and #1199 complement each other: one evaluates Roblox creation outcomes/exploration, the other tests causal action effects from matched states.
8. #1192 and #1209 complement memory and skills, but neither grants a tool permission or authorizes self-promotion.

## 4. Recommended integration sequence

### Phase A — trust and observability foundation

Review the existing dependency chain first:

- resource admission and stream-pressure authority;
- coherent host telemetry and stream sampling;
- trusted voice-room ingress and task/delivery ledger;
- game-action freshness and one-shot permit gate;
- authenticated read-only OBS telemetry.

Acceptance:
- no duplicate scheduler or action authority;
- stale/future/cross-epoch observations rejected;
- worker lease release occurs only after host-confirmed stop;
- task completion requires result and evidence references;
- interruption, cancellation, focus loss, and disconnect leave controls/audio in a safe state.

### Phase B — natural live conversation and avatar

Integrate the room director, persona, EoT adapter, and stream memory.

Required behavior:
- distinguish speaker from addressee;
- understand direct questions, replies, group conversation, and unrelated speech;
- stop an answer when the exact question has already been resolved;
- retain unanswered questions only within the approved session/retention policy;
- allow natural silence instead of forced commentary;
- cancel stale TTS and avatar state on interruption;
- use one playback clock and one avatar parameter arbiter;
- send latest avatar state rather than queueing stale expressions.

Acceptance:
- EoT-Bench v1.1 with version-pinned cohorts;
- multiparty synthetic replay with overlapping speakers and topic changes;
- false-cutoff and response-delay Pareto curves;
- interruption-to-silence latency;
- avatar lip-sync drift against actual playback;
- no viewer transcript/audio in default telemetry.

### Phase C — Gamer Brain and Creator Brain

Integrate the game-control gate, causal probes, OpenGameEval adapter, and skill contracts.

Gamer Brain:
- a fast deterministic control loop for movement, aiming, camera, jump, dodge, and menu navigation;
- a slower strategic planner for objectives, route planning, resource use, and learning between attempts;
- fresh observations with frame IDs and monotonic timestamps;
- short action leases, bounded holds, manual override, and immediate release on focus loss;
- state-verifiable outcomes for wins, deaths, objectives, pickups, and checkpoints.

Creator Brain:
- inspect the project before editing;
- plan changes against the actual DataModel/scene;
- build in disposable test places;
- run Luau/static checks;
- playtest with server/client and multiplayer scenarios;
- capture visual evidence;
- compare against the design specification;
- repair and rerun the failing check.

Acceptance:
- OpenGameEval 84-task release pinned;
- GameWorld paused and real-time tracks reported separately;
- GameDevBench external evaluation where its license permits;
- randomized held-out maps/seeds;
- scene correctness and play-session correctness both required;
- generated skills evaluated with skill-on/skill-off paired runs and negative-transfer tests.

### Phase D — memory, knowledge, and continual learning

Use existing memory authorities and add evaluation coverage rather than new stores.

Knowledge Brain:
- parametric recall for stable common facts;
- retrieval for obscure or changing facts;
- multi-source synthesis for difficult research;
- claim-level citations with source date and scope;
- explicit uncertainty when evidence is missing or conflicting.

Memory:
- current task state;
- episodic stream events;
- procedural skills;
- semantic/project knowledge;
- task ledger/checkpoints.

Acceptance:
- explicit fact recall;
- compositional inference;
- temporal event reasoning;
- memory governance and stale-memory reconciliation;
- memory-to-tool argument accuracy;
- irrelevant-memory injection;
- cross-project isolation;
- citation entailment and freshness;
- calibrated abstention.

A retrieved memory is evidence to consider, not a permission grant and not automatically a fact.

### Phase E — inference and mixed-load optimization

Only after the preceding telemetry is trustworthy:

1. Establish a baseline on the exact STAR host and model.
2. Test current supported quantization and cache modes.
3. Evaluate speculative modes using exact binary capability detection.
4. Compare candidate model routes on the same task set.
5. Measure cold and warm cache states.
6. Run gaming + voice + OBS + avatar + background research simultaneously.
7. Promote only if task quality is non-inferior and interactive tail latency/resource headroom improves.

The 8 GB local GPU path should not attempt to keep multiple large ASR, TTS, vision, draft, and reasoning models resident at once. Use the existing resource admission authority and, where available, the owner's separate server for background work.

## 5. Capability scorecard — measure STAR as one system

| Domain | Primary measure | Required guard |
|---|---|---|
| General knowledge | Correctness, evidence entailment, freshness, calibration | No fabricated citations; abstain on missing evidence |
| Long reasoning | Success by horizon and repeated-run reliability | Checkpoints and verified completion |
| Computer use | Cross-app checkpoint completion and artifact correctness | Disposable environment; inspect before mutation |
| Roblox creation | Pass@1, consistency, EDIT/PLAY success | Test place, server/client checks, sealed holdout |
| Game playing | State-verified win/objective rate and action validity | Fresh-frame gate and manual override |
| Skill learning | Skill-on/off delta, transfer, negative transfer | Independent grader and sealed holdout |
| Memory | Recall, temporal accuracy, action grounding, governance | Scope, retention and privacy controls |
| Voice | False cutoffs, endpointing delay, TTFT, first-audio, interruption recovery | Distinguish endpointing from inference |
| Avatar | Lip-sync drift, stale-state duration, parameter conflicts | Single writer and playback clock |
| Inference | TTFT, ITL, tokens/s, p50/p95/p99, goodput | Same hardware/model/workload |
| Mixed load | Voice/game/OBS quality under concurrency | One admission controller; no starvation |
| Reliability | Success-by-horizon, recovery, duplicate work, false completion | Evidence-backed state transitions |

Do not collapse these into one vanity score. A model can be better at coding and worse at live conversation; STAR needs a capability profile.

## 6. Reproducible acceptance protocol

Every meaningful benchmark run should pin:

- STAR commit and PR head;
- model file hash, backend build, quantization, context length, and sampling settings;
- prompt/system-prefix revision;
- skill pack and contract revisions;
- tool and permission configuration;
- benchmark release, task roster, seeds, and evaluator hash;
- host CPU/GPU/RAM/VRAM, driver, OS, power profile, and thermal state;
- server slot count and concurrency;
- cache state and warm-up protocol;
- OBS, game, audio, and avatar workload revisions;
- start/end timestamps and monotonic clock epoch;
- raw result artifact hashes and evidence references.

Use matched pairs for performance changes. Keep holdout cases sealed. Report sample counts and confidence intervals. If the workload, model, evaluator, or host changes, label the run as a different experiment rather than comparing it as a clean A/B.

## 7. Human-like streaming: what matters most

A compelling AI streamer is not one that talks constantly or imitates human biography. It is one that is socially aware, expressive, consistent, responsive, and honest.

Priority behaviors:

- notices when a viewer addresses her directly;
- remembers the question while handling a gameplay interruption;
- follows viewer-to-viewer conversations without hijacking them;
- uses humor and callbacks grounded in actual shared context;
- reacts to a clutch play, mistake, surprise, or achievement proportionately;
- can be quiet during focused gameplay or another person's story;
- resumes unfinished tasks after an interruption;
- synchronizes voice, mouth, eyes, expressions, and hair movement;
- transparently identifies as an AI character and never invents lived experience.

The architecture should use one stream event timeline and one authoritative director. Individual subsystems may propose cues, but the trusted host decides whether STAR may speak and the playback/avatar controllers decide what is actually heard and shown.

## 8. Run 60 implementation scope and limits

This branch adds:
- this source-linked integration and acceptance blueprint;
- a reproducibility manifest for future matched runs;
- a reviewed dependency map across the existing open PRs;
- explicit benchmark-version, privacy, hardware, and release gates.

This run does **not**:
- merge any open PR;
- alter main or star/next;
- enable a new model, provider, dataset, tool permission, or scheduler;
- download benchmark media or model weights;
- connect to the owner's microphone, OBS, VTube Studio, Roblox Studio, or game;
- run a physical GPU benchmark or public livestream;
- claim that STAR's model weights became more intelligent;
- claim a runtime speedup or new gameplay skill.

The purpose is to stop research from fragmenting into parallel prototypes and to make the next engineering work measurable and mergeable.

## 9. Immediate next actions

1. Confirm the dependency graph and changed-file overlap for each draft PR.
2. Complete exact-head CI on each code-bearing branch.
3. Merge only the reviewed foundational trust/telemetry dependencies into the integration train.
4. Run EoT-Bench v1.1 and OpenGameEval on pinned revisions.
5. Connect one stream trace across voice, task ledger, game, avatar, OBS, and inference without duplicating storage.
6. Run long-horizon repeated-task tests and skill-on/skill-off transfer.
7. Run mixed-load A/B on the actual Windows host and GPU.
8. Perform a private, owner-observed stream rehearsal before claiming VTuber acceptance.

## Sources and version notes

- LiveKit EoT-Bench v1.1, updated 2026-11-13: https://github.com/livekit/eot-bench
- LiveKit EoT-Bench leaderboard: https://livekit.com/benchmarks/eot-bench
- OpenGameEval, arXiv:2610.02563, 2026-10-01: https://arxiv.org/abs/2610.02563
- Official Roblox OpenGameEval repository: https://github.com/Roblox/open-game-eval
- WindowsWorld, Findings of ACL 2026: https://aclanthology.org/2026.findings-acl.750/
- WindowsWorld preprint: https://arxiv.org/abs/2604.27776
- Agent Memory Leaderboard documentation: https://agentmemories.ai/docs
- Agent Memory Leaderboard repository: https://github.com/AML-memory/agent-memory-leaderboard
- Beyond pass@1: A Reliability Science Framework for Long-Horizon LLM Agents, arXiv:2603.29231: https://arxiv.org/abs/2603.29231
- How Fast Do Agents Rot?, arXiv:2609.01660: https://arxiv.org/abs/2609.01660
- llama.cpp speculative decoding documentation: https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md
- llama.cpp SPEED-Bench: https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench
- Google Research TurboQuant, 2026-03-24: https://research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression/

All benchmark findings above describe the cited external systems and experiments. They are not STAR measurements. Upstream documentation on a moving branch must be pinned to a commit before a reproducible STAR experiment.
