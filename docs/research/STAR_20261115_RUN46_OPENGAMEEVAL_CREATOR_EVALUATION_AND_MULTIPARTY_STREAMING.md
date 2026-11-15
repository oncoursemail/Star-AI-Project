# STAR Run 46 — OpenGameEval Creator Intelligence, Exploration Quality, and Reproducible Mixed-Load Acceptance

**Date:** 2026-11-15  
**Scope:** research plus an offline evaluation adapter; no production runtime activation.

## Executive summary

Run 46 turns a newly important Roblox-specific benchmark into a STAR-native, reproducible evaluation path.

The repository audit found that **star/next** already has:

- **star/gameplay_skill_bank.py**: signed practice/validation evidence, with holdouts hidden from the practice view.
- **star/active_practice.py**: bounded practice suggestions, never direct game-control authorization.
- **star/game_mechanic_probe_lab.py**: observational comparisons, explicitly not causal inference.
- Open draft work for causal probes, memory-to-tool grounding, streaming inference measurement, and multiparty room policy.

The missing bridge is a consistent way to evaluate an agent's *whole Creator Brain attempt*: inspect the project, make edits, validate the edited scene, run the game, and prove the result with executable checks. OpenGameEval is a strong fit for that gap.

This run adds:

1. **star/opengameeval_eval.py** — a standard-library-only, offline parser and evaluator for exported OpenGameEval records plus minimized local tool traces.
2. **tests/test_opengameeval_eval.py** — 24 regression tests.
3. **docs/research/STAR_OPENGAMEEVAL_RUN_MANIFEST_TEMPLATE.yaml** — a credential-free, revision-pinned run template.
4. This research and integration blueprint.

The adapter does not submit evaluations, call Roblox APIs, read credentials, run Luau, control Studio, expose holdouts, or promote skills. It converts completed evaluator records into comparable task-level metrics.

## 1. Research findings

### 1.1 OpenGameEval is the right Roblox Creator Brain benchmark

Primary sources:

- Repository: https://github.com/Roblox/open-game-eval
- Paper: https://arxiv.org/abs/2610.02563
- Current expanded leaderboard: https://github.com/Roblox/open-game-eval/blob/main/LLM_LEADERBOARD.md
- Eval Runner guide: https://github.com/Roblox/open-game-eval/blob/main/EvalPlugin/USER_GUIDE.md

The paper describes reproducible, stateful Roblox Studio sessions and executable checks in both edit mode and a simulated play session. The action space distinguishes observation tools from editing tools, which makes exploration behavior measurable instead of judging only the final scene. The paper reports 84 human-curated core tasks, 16 attempts per task, and 13 evaluated frontier models. It reports that inspection of task-relevant objects before editing is associated with higher success; this is a useful diagnostic hypothesis, not a universal rule that every object must always be inspected.

The current repository README/leaderboard has evolved beyond the paper snapshot: the expanded leaderboard describes an 87-eval set and a separate debug suite. Do not call the paper's 84-task snapshot and the current 87-eval suite the same release. Pin the exact upstream commit and suite name for every run.

The current leaderboard reports:
- **Pass@1**: success on one attempt.
- **Pass@5**: at least one success in five attempts.
- **Cons@5**: at least three successes in five attempts.
- **All@5**: five successes in five attempts.
- Average tool-error rate.

The debug suite is a separate capability slice: diagnosing and repairing injected bugs is not equivalent to greenfield code generation.

The current expanded leaderboard is useful as an external calibration point, not as a STAR result or a local-model target. Its displayed top entry for the expanded set reports Pass@1 50.34%, Pass@5 62.07%, Cons@5 51.09%, All@5 39.52%, and 1.40% average tool-error rate. Its separate debug table reports different values and must not be blended into the greenfield suite. These figures are tied to the upstream suite/model configuration and are not transferable to STAR's hardware without a matched run.


### 1.2 The result contract is more useful than a screenshot-only score

The official README documents result rows by mode, including **[EDIT]** and **[PLAY]**, and per-mode **passes**, **fails**, **checks**, warnings, errors and interruptions. The benchmark considers an evaluation successful only when all checks pass.

STAR should therefore report at least:

- EDIT pass rate.
- PLAY pass rate.
- Joint task success (all required modes pass).
- Missing/incomplete mode results.
- API/evaluator errors.
- Warnings and interruptions separately.
- Tool errors.
- Exploration diagnostics where annotations and traces exist.

A task with zero checks must not count as a pass. A completed job missing a required mode is a failed attempt for the joint score, not a partial success. A failed/queued/pending API job has no completed evaluator result and must be reported separately rather than silently treated as a valid agent attempt.

### 1.3 Exploration annotations are optional and must stay evaluator-side

The upstream README describes optional task annotations such as expected tool calls and expected script/non-script instances. Empty fields mean "not annotated", not "the agent inspected zero objects". Keep these fields out of the model prompt and use them only after the run.

The adapter reports:
- Expected-tool-call recall, when the task supplies a non-empty annotation.
- Pre-edit inspection coverage, when expected instance paths are annotated and a local trace is available.
- Successful edits that occurred before a successful observation of the same target.
- Tool error rate.

These are diagnostic measurements. They must not replace executable scene/play checks or reward rote use of a particular tool sequence when another valid workflow exists.

### 1.4 Statistical aggregation: report reliability, not only best-case success

For **n** completed attempts with **c** successful attempts, the adapter calculates the expected score over all size-**k** subsets sampled without replacement:

- **pass@k**: probability a selected size-k subset contains at least one success.
- **cons@k**: probability it contains a strict majority of successes (>= 3/5 when k=5).
- **all@k**: probability every selected attempt succeeds.

When exactly five attempts are present, these reduce to the leaderboard's intuitive five-run indicators. When more attempts are present, the finite-sample combinatorial expectation avoids cherry-picking the best five. Tasks with fewer than **k** completed attempts are marked unscored for **k**; the report includes scored/unscored task counts.

Reports are macro-averaged by task so a task with many attempts cannot dominate a task with fewer attempts. Each report is restricted to one split and one benchmark/agent revision. Practice, validation and holdout must be run separately.

### 1.5 External API constraints and cost boundaries

The official OpenGameEval README currently documents:
- A Roblox account and an Open Cloud API key with the **studio-evaluations** create permission.
- A separate model-provider API key for non-reference model evaluation.
- Job-creation limits of 50 requests/hour and 100/day per API key.
- A default evaluation timeout of 10 minutes.
- Polling limits.

The benchmark is not free merely because its harness is open source. Every model evaluation can consume provider quota and Roblox API capacity. Do not run a full suite from an hourly automation. Start with a tiny, owner-authorized pilot on synthetic projects, one concurrent job, and an explicit cost ceiling. Never place keys in GitHub, manifests, logs, prompts, or generated artifacts.

This run did not submit an OpenGameEval job because the required owner-controlled Roblox and model-provider credentials were not available to this run, and a live run would incur external API/model usage.

## 2. STAR architecture mapping

### 2.1 Creator Brain loop

The intended workflow is:

1. **Inspect:** enumerate relevant project objects and scripts through the approved Studio observation surface.
2. **Plan:** translate the task into a constrained edit plan with preconditions and expected state changes.
3. **Edit:** apply a minimal patch using the approved Studio editing surface.
4. **Static validation:** run Luau analysis/lint/type checks where applicable.
5. **Scene validation:** run edit-mode executable checks.
6. **Play validation:** run simulated play-mode checks.
7. **Inspect failures:** correlate failing checks with logs and observed state.
8. **Repair:** make a bounded follow-up patch.
9. **Replay:** rerun both scene and play checks.
10. **Holdout:** test task variants or held-out places/seeds without exposing expected solutions to the agent.
11. **Evidence:** save pinned revisions, result digests and minimized tool events.
12. **Review:** offer the skill/patch for owner review; never self-promote based on one benchmark result.

OpenGameEval provides the benchmark-specific executable check layer. STAR's own Studio MCP/host adapter remains responsible for safe tool scopes, session lifecycle, reset, logs, artifact capture and source revision.

### 2.2 Preserve existing authorities

Do not introduce a second:
- Task/session ledger.
- Game-control authority.
- Skill bank or promotion service.
- Resource-admission scheduler.
- Voice room director.
- Playback clock.
- Persistent memory store.

The new adapter is a pure evaluation/reporting component. It does not call **GameplaySkillBank.ingest**, **ActivePracticePlanner**, **GameControlGate**, or a Studio tool. A later integration may export reviewed results into the existing evidence path, but only through the existing trusted host signer and independent validation process.

### 2.3 Why observation and editing need separate traces

A final diff cannot show whether STAR understood the project before changing it. The local trace should retain only bounded metadata:

- Monotonic event sequence.
- Operation category: observe, edit, playtest, other.
- Tool name.
- Optional target instance path.
- Success/failure bit.

Do not persist raw source code, full tool arguments, private prompts, player data, screenshots, access tokens, or audio in the evaluation report. Store any necessary screenshots/logs separately in an access-controlled, short-retention evidence store and reference them by digest.

## 3. Implemented adapter

### star/opengameeval_eval.py

The new module is deliberately standard-library-only and offline.

It supports:
- Parsing exported OpenGameEval job records.
- Normalizing [EDIT] / [PLAY] mode labels.
- Validating passes + fails == checks.
- Refusing zero-check false positives.
- Treating API/evaluator errors as failed mode results.
- Requiring all task-declared modes for joint success.
- Separating failed/pending jobs from completed attempts.
- Pinned benchmark, environment and agent revisions.
- Strictly ordered, content-minimized local tool events.
- Optional annotation handling (None/empty means unavailable).
- Pre-edit inspection coverage and expected tool-call recall.
- Tool error, warning and interruption diagnostics.
- Per-task pass@k, cons@k, and all@k.
- Macro averages and counts of tasks that did/did not have enough attempts.

The module performs no HTTP, subprocess, filesystem, Studio, Luau, game-input or model operations. It does not contain or accept API keys.

### Important metric semantics

- Warnings and interruptions are reported, not silently converted into success or failure.
- A non-empty evaluator error invalidates that mode even if its check counters appear successful.
- Missing required modes fail joint success.
- Failed/queued/pending jobs are counted separately and excluded from completed-attempt pass denominators.
- An unannotated task receives None, not a zero exploration score.
- A failed observation does not count as inspected.
- A tool call may count toward attempted tool-call recall even when the tool itself fails; tool failure is separately reflected in tool-error rate.

### Tests

**tests/test_opengameeval_eval.py** contains 24 tests for:
- Joint EDIT/PLAY requirements.
- Zero-check handling.
- Counter consistency.
- API record parsing.
- API error handling.
- Duplicate modes and attempt IDs.
- Optional annotations.
- Lua-comment stripping in expected-tool annotations.
- Observation-before-edit ordering.
- Failed observations.
- Tool error rate.
- pass@k / cons@k / all@k.
- Insufficient attempts.
- Failed and pending job accounting.
- Revision/split isolation.
- Macro task weighting.
- Event ordering and bounded k.

The 24 tests passed in an isolated Python 3.13 harness during this run. They have not yet run inside the repository's complete CI environment; exact-head GitHub Actions is still required.

## 4. Reproducible benchmark plan

Use **docs/research/STAR_OPENGAMEEVAL_RUN_MANIFEST_TEMPLATE.yaml** for every external run.

### Pilot phases

**Phase A — Harness correctness**
- Use OpenGameEval reference mode only to validate locally authored task checks.
- Verify each task has non-zero executable checks.
- Verify both edit and play checks where required.
- Confirm reset produces identical initial place state.
- Confirm the evaluator reports failures correctly.

**Phase B — Small model pilot**
- Select 5–10 non-sensitive synthetic tasks across script edits, scene edits, and debugging.
- Run five attempts per task for leaderboard-style consistency metrics.
- Keep concurrency at one.
- Pin model, prompt, tool schema, Studio version, place file, plugin and benchmark commit.
- Record actual provider usage and elapsed time.
- Do not use real user projects or public production places.

**Phase C — Exploration analysis**
- Use only tasks with non-empty upstream annotations.
- Keep annotations hidden from the model.
- Compare inspection coverage with pass rate.
- Report sample size and task category.
- Do not infer causation from correlation; use controlled matched-start-state experiments separately.

**Phase D — Generalization**
- Hold out task variants, places, and project versions.
- Measure script-authoring, scene-editing and debugging separately.
- Require repeated success, not just Pass@1.
- Keep a sealed holdout evaluator independent from the agent.

**Phase E — Mixed-load acceptance**
- Run Creator Brain only after the benchmark harness is stable.
- Measure Roblox Studio frame time, local inference queue wait, TTFT, first useful content, first audible audio, inter-token latency, CPU/RAM/VRAM, game FPS, OBS dropped frames, audio underruns and task success.
- Compare idle and mixed-load runs on the same pinned machine and software revisions.
- Reject an inference change if token throughput rises but voice latency, game frame-time, OBS health or verified task success regresses.

## 5. Broader intelligence and VTuber implications

### 5.1 General knowledge vs. procedural skill

Keep factual knowledge and executable skills separate.

A general-knowledge claim should carry:
- Source and publication/update date.
- Scope and assumptions.
- Supporting and contradicting evidence.
- Freshness/expiry policy.
- Confidence and abstention reason.

A procedural skill should carry:
- Preconditions.
- Allowed tools and scope.
- Expected state delta.
- Execution trace.
- Independent verifier.
- Failure/recovery path.
- Resource/time budget.
- Version and expiry/revalidation.

STAR should not turn a plausible answer into a learned skill. The skill must work in a controlled environment and transfer to held-out tasks.

### 5.2 Gaming intelligence

OpenGameEval measures creation, not general gameplay. Keep it separate from GameWorld/SIMA-style game-playing evaluation and from causal game-mechanic probes.

Use three distinct tracks:
- **Creator:** author/edit/debug a game in Studio.
- **Player:** control a game in paused, slowed and real-time conditions.
- **Mechanic learner:** compare actions from matched starting states and test on held-out seeds.

A model that writes a good script has not demonstrated real-time gameplay skill. A model that wins one game seed has not demonstrated generalization.

### 5.3 Human-like streaming

Natural streaming needs a single, coordinated stage policy, not more competing voice agents.

Retain the existing RoomTurnDirector and playback owner. The runtime should combine:
- Trusted session-local speaker/addressee/reply metadata.
- End-of-turn decisions with a measured false-cutoff/latency frontier.
- Multiparty response appropriateness and silence preservation.
- Game-event relevance and urgency.
- Playback-grounded avatar motion.
- Cancellation tied to the exact response generation.
- Bounded stream-event memory with provenance and expiry.

Research references:
- MP-Bench: https://aclanthology.org/2026.findings-emnlp.1437/
- Duplex-MPE: https://arxiv.org/abs/2609.31948
- EoT-Bench v1.1: https://github.com/livekit/eot-bench
- Full-Duplex-Bench v3: https://arxiv.org/abs/2604.04847

MP-Bench evaluates voice agents as active participants in multiparty conversation; its authors report that the tested real-time agents reached at most 22% on multiparty comprehension and remained near chance on multiparty turn-taking. Duplex-MPE adds 2,000 three-/four-human scenarios and explicitly scores when the assistant should answer, stay silent, or stop after a human resolves a request. EoT-Bench v1.1 was updated on 2026-11-13 and exposes 7,342 human-to-agent turns across 14 languages, with a policy sweep that makes false-cutoff rate and endpointing delay visible as a Pareto trade-off. These are benchmark findings, not STAR performance claims.

A believable AI streamer is not one that speaks constantly. It is one that follows the conversation, recognizes when she is addressed, reacts appropriately, remembers relevant context, and is comfortable remaining silent. Keep AI identity transparent; do not invent human autobiography.

### 5.4 Cross-application creation

WindowsWorld and WeaveBench show why isolated single-app success is insufficient:
- WindowsWorld: 181 tasks across 17 applications; its paper reports less than 21% success for evaluated agents on multi-application tasks.
- WeaveBench: 114 hybrid GUI/CLI tasks across eight work domains; its paper reports a best pass rate of 41.2% in its evaluated pairings and warns that outcome-only grading can overestimate success.

Sources:
- https://aclanthology.org/2026.findings-acl.750/
- https://www.microsoft.com/en-us/research/publication/weavebench-a-long-horizon-real-world-benchmark-for-computer-use-agents-with-hybrid-interfaces/

For STAR, this motivates end-to-end workflows that cross Studio, terminal, Blender, asset inspection, logs and output verification inside disposable workspaces. It does not justify unrestricted access to the owner's desktop.

## 6. Speed and intelligence: what to optimize next

Do not equate token/s with intelligence or user-perceived speed.

Measure separate stages:
- Queue wait.
- Prompt prefill.
- First token.
- First non-reasoning/useful content.
- First generated audio packet.
- First audible audio at playback.
- Inter-token latency.
- End-of-turn delay.
- Tool round-trip.
- Verification time.
- End-to-end time to verified completion.

The existing streaming inference benchmark work is the right foundation. Compare configurations with identical prompt/model/tool revisions and the same sample set. Use warm and cold runs, concurrency matched to server slots, and a mixed-load pass.

Candidate optimizations to test one at a time:
1. Stable prompt prefixes and cache reuse.
2. Context trimming by task-relevant evidence, not arbitrary truncation.
3. Fast/deep/background routing using the existing resource-admission authority.
4. Bounded tool-result compaction with evidence read-back.
5. Continuous batching and slot/concurrency tuning.
6. Speculative decoding only when the draft model fits the actual hardware budget and improves end-to-end goodput.
7. Model residency and unload policy that protects foreground voice/game workloads.

Do not enable five large models simultaneously on an 8 GB GPU. Preserve VRAM for the game, OBS, avatar, audio and the foreground model. The benchmark must measure p95/p99 latency and task quality, not only average tokens/s.

## 7. Security, privacy, and licensing gates

- No API keys or provider credentials in GitHub.
- No private user projects or player data in public benchmark artifacts.
- No raw audio, transcripts, viewer IDs, voiceprints or chat logs in evaluation reports.
- No holdout annotations in model-visible prompts.
- No automatic public stream, platform OAuth, or game-control permission.
- No anti-cheat bypass or interaction with games where automation is prohibited.
- No skill promotion from benchmark correlation alone.
- No third-party model/dataset install without license, hardware and privacy review.
- External API runs require explicit owner approval and cost limits.

## 8. Run 47 implementation priorities

1. Finish exact-head CI for this adapter and resolve any type/lint findings.
2. Pin the OpenGameEval upstream commit and current expanded suite.
3. Validate reference checks on a disposable Roblox template.
4. Add a read-only OpenGameEval result-export adapter to the existing host evidence pipeline.
5. Capture minimized observation/edit/playtest traces from STAR's Studio MCP adapter.
6. Run a 5–10 task owner-authorized pilot with one concurrent job and a cost cap.
7. Compare script, scene and debug task categories independently.
8. Evaluate skill changes on held-out task variants and project seeds.
9. Integrate Creator Brain with the existing resource-admission controller.
10. Run the complete Windows mixed-load rehearsal: Studio + game + voice + avatar + OBS + background research.
11. Keep public streaming and automatic skill promotion separately gated.

## 9. Acceptance status

| Area | Run 46 status |
|---|---|
| OpenGameEval research | Completed |
| Offline result adapter | Implemented |
| Optional exploration annotations | Implemented |
| Pass@k / Cons@k / All@k | Implemented |
| Regression tests | 24 passed in isolated Python 3.13 harness |
| Repository CI | Pending exact-head Actions |
| OpenGameEval API submission | Not run; owner credentials/authorization and external cost required |
| Roblox Studio integration | Not implemented in this PR |
| Real gameplay | Not tested |
| Windows/GPU/OBS/microphone/VTube Studio | Not tested |
| Measured inference speedup | Not claimed |
| Skill promotion | Not enabled |

**Run 46 is an evaluation-foundation improvement, not a claim that STAR has already mastered Roblox development or become a human-equivalent streamer.**
