# STAR Run 37 — Generalist Skill Foundry, World Models, and Verifiable Computer Use

**Research date:** 2026-11-14 (America/Chicago)  
**Repository:** oncoursemail/Star-AI-Project  
**Research branch:** research/star-run24-integration-blueprint-20261114  
**Companion implementation branch:** feat/game-control-gate-20261114-run31  
**Scope:** cross-domain skill acquisition, general computer use, visual world prediction, game transfer, autonomous creation, resource-efficient reasoning, and natural VTuber presence.

---

## Executive decision

STAR already has separate work for task continuity, event memory research, causal game experiments, screen-to-action authorization, multiparty voice, workload admission, avatar transport, and creator automation. The next useful step is not another agent swarm or another permanent memory store. It is a **Generalist Skill Foundry** that turns verified experience into reusable, scoped, testable skills and proves that those skills transfer to new environments.

Run 37 makes seven decisions:

1. **Use SIMA 2 as a learning-loop reference, not a model to install.** Its important pattern is the combination of high-level reasoning, visual interaction, human demonstrations, generated feedback, self-directed practice, and a bank of experience that can improve later training generations.
2. **Use V-JEPA 2 as a world-prediction research reference, not a game controller.** Predicting visual state changes can help compare candidate actions, but a latent predictor is not itself a safe action policy or proof that a goal was completed.
3. **Add a cross-domain computer-use evaluation ladder.** Use the current OSWorld 2.1 release for long-horizon desktop workflows and AndroidWorld for dynamic mobile tasks. Keep environments isolated and version-pinned.
4. **Create portable skill contracts.** Every skill must declare its preconditions, environment/version scope, required tools, expected state change, independent verifier, failure recovery, resource budget, provenance, and expiry/revalidation rule.
5. **Separate planner, executor, and verifier.** The model that proposes an action must not be the only component that declares it successful. Prefer environment state, tests, or independent evidence.
6. **Optimize end-to-end usefulness, not isolated token speed.** Keep the live audio/game path protected; make perception adaptive; route routine work to small/cheap components and reserve expensive reasoning for uncertain or high-impact decisions.
7. **Make streaming presence evidence-led and socially aware.** STAR should be expressive, humorous, attentive, and comfortable with silence while remaining transparent that she is an AI character. She must not invent human biography or claim to have seen events that host evidence does not establish.

This is a research and integration plan plus a research-catalog update. It does not install models, download gated datasets, change production model routing, grant new desktop permissions, create platform credentials, or enable public streaming.

---

## 1. Repository audit and integration boundary

The repository already has the foundations needed to make this direction additive:

| Existing work | Run 37 decision |
|---|---|
| #1177 task and communication ledger | Keep task state and delivery obligations authoritative. A skill run references task IDs; it does not create a parallel task ledger. |
| #1178 RoomTurnDirector / RoomStreamHost | Keep one floor-control and spoken-response authority. Skill results may propose a commentary event but cannot grant themselves the floor. |
| #1140 / #1142 resource admission and stream-pressure governor | Keep one lease/admission authority. Skill budgets are requests to this authority, not a second scheduler. |
| #1151 / #1181 audio playback work | Reconcile to one playback clock and one callback authority before connecting new avatar behaviors. |
| #1159 latest-wins Live2D frame pump | Keep replaceable pose samples latest-wins; never queue stale poses behind current speech. |
| #1165 / #1166 paired quality evaluation | Use paired task sets and held-out scenarios to measure quality before and after optimizations. |
| #1167 inference timing | Reuse the existing timing path; report queue, prefill, first token, decode, first audio, and audible playback separately. |
| #1182 GameControlGate | Keep it as the only game-action authorization/permit authority. A skill cannot bypass consent, focus, allowlist, freshness, stop, or release checks. |
| #1180 research branch | Extend the current research PR; do not create another disconnected roadmap. |

### Audit finding

The current Game Lab catalog is a read-only source index. Its existing tests enforce HTTPS URLs, unique IDs, explicit research-only statuses, and warnings that prevent paper results from being presented as STAR capabilities. Run 37 extends that catalog with five cross-domain sources and keeps them research-only.

The screen-to-action gate remains a policy primitive. It is not a DXGI capture implementation, a Windows input executor, a Roblox Studio controller, or proof that STAR can play a game. Those capabilities still require their own adapter, permission checks, and target-machine acceptance.

---

## 2. SIMA 2: the strongest new game-learning pattern

Primary source: https://deepmind.google/blog/sima-2-an-agent-that-plays-reasons-and-learns-with-you-in-virtual-3d-worlds/

Google DeepMind introduced SIMA 2 on 2025-11-13. The article describes an agent that uses a Gemini reasoning core to interpret high-level goals, converse with a user, and act in 3D game worlds. SIMA 1 had learned more than 600 language-following skills across several games using visual observations and virtual keyboard/mouse actions. SIMA 2 adds goal-directed reasoning and can describe its intended steps.

The most useful part for STAR is the learning loop:

- Begin with human demonstration videos and language labels.
- Use model-generated labels/feedback to help interpret trajectories.
- Practice through self-directed interaction in supported environments.
- Record experience, including failures.
- Reuse the experience bank in later training iterations.
- Test transfer in games/worlds that were not part of the original training set.

DeepMind reports transfer experiments involving MineDojo, ASKA, and generated Genie environments. The same article is explicit about important remaining limitations: very long multi-step tasks, goal verification, short interaction memory, precise low-level keyboard/mouse control, and robust visual understanding remain difficult. SIMA 2 was announced as a limited research preview for a small cohort of academics and game developers, not as a generally downloadable local model.

### STAR application: copy the evidence loop, not the whole model

Build a local Skill Foundry around existing game-control and procedural-memory work:

1. **Observe:** capture an approved, bounded game observation and trusted game/session metadata.
2. **Interpret:** identify the goal, relevant entities, controls, and uncertainty.
3. **Plan:** create a short action plan with an explicit expected state change.
4. **Act:** request a short-lived permit from GameControlGate and execute only through an approved host adapter.
5. **Verify:** compare the observed state with the expected result using a state verifier, game telemetry, a test assertion, or independent visual evidence.
6. **Learn:** store the trajectory, outcome, failure reason, and conditions under which the action worked.
7. **Generalize:** test the skill on another map, seed, level, game version, or equivalent task.
8. **Promote:** add it to the procedural skill library only after independent holdout success.

The experience bank should store compact structured records and evidence references, not unbounded raw video or private viewer transcripts. Retain negative examples because failures often reveal missing preconditions, incorrect assumptions, or a game update.

### Skill transfer must be explicit

A skill called “collect a resource” is not universally valid merely because it worked once. The skill should describe semantic intent and its adapter-specific realization:

- In one game, the resource may be a visible object and a contextual interact key.
- In another, it may require a tool, inventory slot, or timed action.
- In Roblox Studio, it may be a deterministic test fixture or simulated player action.
- In a desktop editor, it may be a menu command or property edit.

The shared skill is the intent and verification contract; the environment adapter supplies permitted controls and exact mechanics. Transfer is a hypothesis until a new environment passes its own verifier.

---

## 3. V-JEPA 2: learn to predict what actions will change

Primary source: https://ai.meta.com/research/vjepa/  
Official implementation: https://github.com/facebookresearch/vjepa2

Meta describes V-JEPA 2 as a self-supervised video world model for visual understanding and prediction. Its encoder/predictor is pretrained on video, and the V-JEPA 2-AC research uses 62 hours of robot data from the DROID dataset for downstream action-conditioned planning in new environments.

The official implementation now also announces **V-JEPA 2.1 (2026-03-16)**, with temporally consistent dense features and pretrained checkpoint sizes from 80 million parameters (ViT-B/16) through 300M, 1B, and 2B variants. The same repository documents V-JEPA 2-AC as a latent action-conditioned model post-trained from the V-JEPA 2 backbone. This makes the 80M V-JEPA 2.1 checkpoint a more sensible first resource experiment than starting with a 1B–2B model, but parameter count alone does not establish memory use, Windows compatibility, or real-time speed.

### What STAR should learn from it

The useful idea is **predictive state comparison**:

- What does the scene look like now?
- What is likely to change if STAR takes action A?
- What might change if she takes action B?
- Which predicted changes are relevant to the objective?
- Which prediction is uncertain enough to require another observation?
- Did the real environment match the prediction after execution?

For a game, this could eventually help predict movement, obstacle motion, enemy approach, projectile travel, or the likely result of an interaction. For Creator Brain, a similar concept can predict whether a proposed UI or scene edit is likely to alter the intended region.

### Strict limitations

- V-JEPA 2 / 2.1 and V-JEPA 2-AC are research models, not drop-in desktop-control agents. The action-conditioned variant was developed for robot manipulation; that is not proof of game-control transfer.
- A latent prediction is not a verified state transition.
- Robot-action fine-tuning does not prove transfer to arbitrary video games.
- Model size, inference cost, licensing, and Windows deployment must be checked against the actual artifact before any local experiment.
- Do not load it alongside STAR's live speech/game models on the 8 GB GPU by default.

### Recommended STAR experiment

Start with a cheap baseline before testing a large world model:

1. Define a small set of visible state variables.
2. Record short action/outcome pairs from a deterministic simulator or approved game.
3. Predict a small number of measurable changes.
4. Compare prediction error against a simple constant/heuristic baseline.
5. Test on held-out maps/seeds and changed game versions.
6. Only then evaluate a learned visual predictor as an optional background worker. Start with the 80M V-JEPA 2.1 checkpoint for a resource-cost baseline, then compare larger variants only if the small model is insufficient.

A learned predictor is worth adopting only if it improves decisions or reduces expensive perception calls without increasing false confidence.

---

## 4. General computer-use capability: OSWorld 2.1

Official repository: https://github.com/xlang-ai/OSWorld-V2  
Current recommended release: https://github.com/xlang-ai/OSWorld-V2/tree/osworld-v2.1  
Paper: https://arxiv.org/abs/2606.29537

The OSWorld-V2 repository identifies the 2026-09-16 release tag osworld-v2.1 as the recommended benchmark release. It is designed for long-horizon real-world computer-use evaluation and provides separate release-pinned code, task classes, assets, website fixtures, and provider images.

The release instructions are important for reproducibility:

- Use the same release tag for code, task classes, assets, mocked websites, and provider images.
- Do not mix release assets or replace pinned versions with main or latest.
- Official task classes and complete assets are distributed through gated Hugging Face datasets.
- Some tasks require self-hosted mocked websites and GitLab fixtures.
- The project supports isolated providers such as Docker and AWS, with additional provider code paths.
- The documented host environment requires Python 3.12 or later.

### STAR use

OSWorld 2.1 should become a **general desktop-workflow evaluation target**, not a dependency of STAR's production runtime.

Representative task families:

- Locate, inspect, and organize files.
- Edit and export documents.
- Configure an application.
- Use a browser and a desktop application in one workflow.
- Build a project, run tests, inspect output, and repair a failure.
- Complete a multi-step workflow with a final state verifier.

### Security and cost requirements

- Use a disposable VM or isolated worker; never run untrusted benchmark tasks on the live streaming desktop.
- Do not place owner credentials or personal files inside the benchmark VM.
- Gated task access, cloud resources, external accounts, private tokens, or paid provider infrastructure require separate owner authorization.
- Keep benchmark credentials in a secret store/environment, never in task prompts, traces, screenshots, or GitHub commits.
- Start with a tiny smoke subset; do not provision parallel cloud workers automatically.
- Pin every benchmark component and preserve the release manifest with results.

OSWorld's release instructions warn that the complete task and asset set is separate from public runtime assets. A partially downloaded task set must not be reported as a complete benchmark run.

---

## 5. Dynamic mobile skill transfer: AndroidWorld

Official repository: https://github.com/google-research/android_world  
Project page: https://google-research.github.io/android_world/  
Paper: https://arxiv.org/abs/2405.14573

AndroidWorld runs against a live Android emulator and provides 116 hand-crafted tasks across 20 apps. Tasks can be instantiated with randomized parameters, creating many variants. The environment exposes initialization, interaction, and durable reward/state checks, and can integrate MiniWoB++ tasks.

### STAR use

This is a useful cross-platform test of whether a skill is truly semantic or merely memorized for one UI layout.

For example, STAR may learn a general “create a calendar event” workflow on desktop, then be tested on mobile with different event titles, dates, time zones, and initial app states.

### Evaluation rules

- Randomize task parameters.
- Use separate seeds for practice and holdout.
- Check the resulting app/system state, not the model's claim that it finished.
- Record app version, emulator image, screen size, permissions, and task seed.
- Compare accessibility-tree-assisted and screenshot-only conditions separately.
- Do not mix results from different environment versions or task families.

Do not install Android Studio or an emulator as part of this research-only update. The current repository does not yet have a configured AndroidWorld runner.

---

## 6. Coding and creation quality: OpenHands Index

Official index: https://index.openhands.dev/  
OpenHands SDK: https://github.com/OpenHands/software-agent-sdk

The OpenHands Index evaluates coding agents across five task categories:

- Issue resolution.
- Greenfield application creation.
- Frontend development.
- Test generation.
- Information gathering.

It also exposes cost/performance comparisons rather than reducing the result to one model leaderboard.

### STAR Creator Brain application

Use the categories to prevent overfitting STAR's coding evaluation to one type of task:

- Fix an existing Luau/Python/TypeScript bug with a regression test.
- Create a small new project from a written specification.
- Implement a UI change and validate it with screenshots and tests.
- Add a test for an existing bug.
- Research a dependency/API and produce a source-backed decision.

Every task should have a fresh isolated worktree or disposable project copy, a clear initial state, a verifier, and a recorded cost/time budget.

For Roblox, the verifier should include Luau analysis, project-specific tests, Studio playtests, and visual checks where applicable. A green Python test suite does not prove a Roblox place works; a successful Studio playtest does not prove that a desktop screen-to-controller agent can play an unrelated commercial game.

---

## 7. The STAR Skill Foundry: proposed architecture

This is the main architectural proposal from Run 37.

### A. Skill contract

Every reusable skill should contain:

| Field | Requirement |
|---|---|
| skill_id / version | Stable identity and revision |
| intent | Human-readable capability |
| scope | Game, app, engine, platform, and version range |
| preconditions | Observable conditions required before execution |
| required_observations | Data needed to make a safe decision |
| required_tools | Named tools and least-privilege scopes |
| action_plan | Short bounded actions, not an opaque macro |
| expected_state_delta | What should change if successful |
| verifier | Independent evidence of completion |
| failure_modes | Known failure patterns |
| recovery | Reversible cleanup or safe stop behavior |
| budget | Time, tokens, CPU, RAM, VRAM, action count |
| provenance | Demonstrations, tests, source revisions, and evidence refs |
| holdout_results | Unseen task/map/seed results |
| expiry / revalidate_on | Version changes, repeated failures, or evidence expiry |

A skill cannot grant itself a tool permission. The host policy decides whether the requested scope is allowed. A skill with missing preconditions, expired evidence, or a failed verifier must not be promoted as “known working.”

### B. Three distinct roles

**Planner**
- Interprets the goal.
- Selects a candidate skill.
- Produces a short plan and success conditions.
- Estimates uncertainty and cost.

**Executor**
- Uses the environment adapter.
- Requests the existing host authorization.
- Performs bounded actions.
- Emits exact action/observation IDs.

**Verifier**
- Checks the resulting state independently.
- Rejects unsupported completion claims.
- Records the evidence and failure reason.
- Decides whether the trajectory is eligible for learning.

The same model may perform more than one role during an inexpensive task, but high-impact or hard-to-verify tasks should use an independent verifier or deterministic test.

### C. Skill lifecycle

Candidate → Practiced → Verified → Holdout-tested → Promoted → Monitored → Revalidated / Retired

Promotion gates:

- Repeatable success on the practice set.
- Success on unseen seeds or task parameters.
- No violation of tool/permission boundaries.
- A reliable independent verifier.
- Acceptable resource cost and latency.
- No regression on previously supported tasks.

Retirement triggers:

- Game/app version changes.
- Repeated verifier disagreement.
- Preconditions no longer observable.
- A safer or more reliable skill supersedes it.
- Provenance or license becomes invalid.

### D. Cross-domain skill adapters

Keep semantic skill intent separate from environment-specific action APIs:

| Environment | Observation | Action adapter | Verifier |
|---|---|---|---|
| Approved desktop game | DXGI frame + trusted host facts | GameControlGate + approved input executor | Game telemetry or independent state evidence |
| Roblox Studio | Studio tree, logs, screenshots, test state | Official/local Studio integration | Luau checks, Studio tests, server/client assertions |
| Godot/Unity | Editor state, project files, playtest output | Engine-specific adapter | Engine tests, build output, visual capture |
| Desktop application | Screenshot/accessibility tree | Sandboxed desktop adapter | File/state diff or app-specific assertion |
| Android emulator | Screenshot/UI tree | AndroidWorld adapter | Durable app/system-state reward |
| Blender | Scene graph, object properties, rendered preview | Blender Python/API adapter | Scene assertions, render inspection, geometry checks |

Do not give one universal action executor access to every environment. Each adapter should expose only the actions and state needed for its task.

---

## 8. Faster intelligence without starving the live stream

The new benchmark and world-model research reinforces a practical design: use a small number of specialized, bounded loops rather than running a large model at every frame.

### Two-speed control

**Fast loop**
- Owner stop/mute/manual override.
- Audio callback and active playback.
- Lightweight VAD and audio buffering.
- Current game input safety.
- Low-cost visual change detection.
- Latest-wins avatar pose delivery.

**Slow loop**
- Strategic game planning.
- Historical event retrieval.
- General knowledge research.
- Game-skill experiments.
- Creator tasks and code generation.
- World-model prediction.
- Memory consolidation and offline evaluation.

The fast loop must never wait for background research or skill training.

### Adaptive perception

- Keep a low-cost latest-frame path for ordinary observation.
- Increase sampling or invoke expensive vision only during action, scene transitions, uncertainty, or high-value events.
- Reuse existing event-memory evidence rather than reprocessing the entire stream.
- Crop to the owner-approved application/game region.
- Coalesce stale frames; do not build a queue of old screenshots.
- If a capture epoch changes, invalidate all state and action permits tied to the old epoch.

### Model routing

Route by task and measured quality, not by model brand:

- Small model/heuristics: routing, simple classification, stable structured extraction, low-risk summaries.
- Specialized local models: ASR, embeddings, OCR, lightweight vision, TTS.
- Strong reasoning model: ambiguous planning, code architecture, difficult debugging, multi-step research.
- Deterministic tools: tests, parsers, schema validation, state checks, file diffs, and arithmetic.

Use speculative decoding, prefix/KV reuse, batching, quantization, and CPU/GPU offload only after a paired benchmark shows a net win on the actual model, backend, and target hardware.

### Required speed metrics

Record at least:

- Queue wait and resource-admission delay.
- Prefill time, time-to-first-token, inter-token p50/p95/p99.
- First ASR partial, final transcript, first TTS chunk.
- First non-empty playback callback and estimated DAC time.
- Cancellation-to-silence and interruption-to-resume.
- Capture-to-event and capture-to-action latency.
- Game frame-time p50/p95/p99 and missed frames.
- OBS render/encoder lag.
- CPU, RAM, VRAM, disk I/O, and per-process utilization.
- Task success, verifier agreement, and cost per verified completion.

A faster model is not an improvement if it causes more wrong actions, false interruptions, missed viewer intent, lower game FPS, or worse final task success.

---

## 9. Human-like VTuber presence through verified continuity

A believable AI streamer needs a coherent stage state and a consistent character, not a continuous stream of reactions.

### Stage state

Use the existing RoomTurnDirector and task ledger to coordinate:

- Listening to a viewer.
- Responding to a direct mention.
- Following viewer-to-viewer conversation.
- Focusing on a difficult gameplay section.
- Celebrating a verified milestone.
- Quietly waiting.
- Resuming an unfinished obligation.
- Handling a moderation or stream-health event.

### Commentary policy

A commentary candidate should reference:
- A verified event ID.
- The active game/topic.
- Whether the event has already been acknowledged.
- Social relevance and urgency.
- Whether STAR currently has the floor.
- Whether the source is safe for public commentary.
- Whether a response would interrupt another participant.

Silence is a valid successful action. A natural streamer does not need to narrate every frame or answer every message.

### Avatar and voice coordination

- Keep the reconciled playback clock authoritative for mouth timing.
- Use audio/prosody and selected semantic intent for expression and gesture.
- Use the existing latest-wins Live2D frame pump.
- Stop speech and neutralize the corresponding animation on owner mute, cancellation, stale generation, or playback failure.
- Do not trigger laughter or emotional expressions solely because the LLM generated a textual token such as “haha.”
- Keep the character warm, playful, expressive, and consistent while remaining transparent that she is an AI character.

### Privacy

- Keep viewer identities platform-scoped and session-scoped.
- Do not merge Twitch, YouTube, Discord, or game identities without explicit consent and a legitimate reason.
- Respect moderation tombstones and deletion/retention policies.
- Do not use private chat or viewer data as training material by default.
- Never let viewer messages issue privileged desktop, game, file, or streaming commands.

---

## General knowledge and research intelligence

The Skill Foundry must cover factual and conceptual learning as well as actions. STAR should not confuse reading about a subject with being able to explain it accurately, and should not confuse explaining a procedure with successfully executing it.

### Claim-level knowledge record

For each important factual claim, retain:

- A stable claim identifier and concise statement.
- Source identifiers and exact supporting sections or evidence anchors.
- Publication/update date and the time the claim was checked.
- Scope, assumptions, jurisdiction/version, and known exceptions.
- Separate support, contradiction, and uncertainty links.
- A freshness or revalidation rule for time-sensitive claims.
- Whether the claim is directly sourced, inferred, or only a hypothesis.

Prefer primary sources for API behavior, laws, product documentation, benchmark methods, and official announcements. Use peer-reviewed papers or technical reports for research claims, then seek independent replication or counterevidence where practical. Community discussions are valuable for discovering failure modes but should not silently become authoritative facts.

### Research workflow

1. Turn the question into testable subquestions.
2. Identify the strongest primary sources and their dates.
3. Search for independent corroboration and plausible counterexamples.
4. Extract only the evidence needed for each claim.
5. Record conflicts rather than flattening them into one answer.
6. Recheck volatile facts before presenting them.
7. Answer with calibrated confidence and abstain when evidence is inadequate.
8. Promote durable knowledge only through the existing governed memory process.

### Knowledge and skill are different evaluations

Use separate tests:

- **Recall:** can STAR retrieve the correct claim and its source?
- **Reasoning:** can she apply the claim to a changed scenario and identify assumptions?
- **Freshness:** can she detect that a version, price, API, or policy has changed?
- **Contradiction handling:** can she compare conflicting sources and explain why one is stronger?
- **Procedure:** can she perform the task in a sandbox?
- **Transfer:** can she apply the concept in a new domain without copying an old sequence?

A high score on a quiz is not proof of tool competence. A successful tool action is not proof of broad conceptual understanding.

### General knowledge curriculum

Build a rotating, difficulty-calibrated curriculum across mathematics, science, programming, game design, history, geography, language, art, music, media production, systems administration, and everyday practical knowledge. Each domain should include factual questions, explanation tasks, source-checking tasks, and practical sandbox tasks where a safe verifier exists.

Track learning curves and recurring misconceptions. Use spaced review for concepts that decay, but do not repeatedly rehearse facts that are already stable unless they are time-sensitive. The research agent should create candidate notes; the existing memory-governance system decides what becomes durable knowledge.

## 10. Evaluation plan: prove transfer, not just practice

Start with a small, reproducible suite before attempting the full upstream benchmarks.

| Track | Initial STAR suite | Success evidence |
|---|---|---|
| General desktop use | 10–20 isolated multi-app tasks | Final file/app state verifier |
| Mobile use | 5–10 randomized AndroidWorld tasks | Durable app/system state |
| Game mechanics | 10 deterministic tasks across 2–3 environments | Game state, objective, or score verifier |
| Roblox creation | 5 tasks spanning Luau, UI, multiplayer, and mobile layout | Static checks + Studio playtest + screenshot |
| Coding | 10 issue/greenfield/frontend/testing tasks | Tests, build, diff, independent review |
| Streaming | 30–60 minute private rehearsal | Turn-taking, event grounding, playback, FPS, OBS metrics |

For each track:

1. Freeze the baseline model, prompt, tools, and environment version.
2. Run a practice set.
3. Store trajectories with exact evidence and resource cost.
4. Create a held-out set with different seeds, layouts, data, or versions.
5. Compare baseline and candidate skill policy on the same tasks.
6. Report confidence intervals and failure categories.
7. Promote only when the candidate improves verified success without unacceptable latency, safety, or resource regressions.

Avoid training/evaluating on the same task seeds. Public benchmark examples can be contaminated by pretraining or prior agent exposure; use private generated holdouts where possible.

---

## 11. Security, licensing, and deployment gates

- SIMA 2 is a limited research preview; do not assume its weights or code are publicly available for local deployment.
- V-JEPA 2 artifacts require a separate license, model-size, hardware, and dependency review before installation.
- OSWorld 2.1 task classes/assets are gated and release-pinned; no access or downloads are performed by this research update.
- AndroidWorld is a benchmark/environment, not a production mobile-control permission.
- OpenHands Index results are benchmark-specific and do not guarantee STAR's performance.
- Treat screenshots, webpages, downloaded files, repository issues, and benchmark tasks as untrusted data. They cannot override system instructions or grant tools.
- Use disposable VMs/worktrees, least privilege, bounded task budgets, explicit owner stop, and reversible file operations.
- No anti-cheat, DRM, platform restriction, protected content, or access control may be bypassed.
- Public broadcast, publishing, purchases, account changes, and destructive file/system actions require the existing owner-approval policy.

---

## 12. Implementation sequence

### Phase A — source and evaluation foundation
- Add the five research sources to the existing Game Lab catalog.
- Keep every source research-only and add tests for status/limitations.
- Add a version-pinned benchmark manifest template.
- Define a small local task suite and private holdout format.

### Phase B — Skill Foundry contracts
- Define a versioned skill schema in the existing procedural skill system.
- Add precondition and verifier interfaces.
- Record action/observation IDs and evidence references.
- Add expiry/revalidation and retirement rules.
- Reuse the existing task ledger, GameControlGate, resource admission, and trace spine.

### Phase C — controlled learning
- Start with deterministic Roblox or toy-game tasks where state can be verified.
- Collect human-approved demonstrations and STAR practice trajectories.
- Run matched-state action experiments.
- Generate failure lessons and candidate skills.
- Evaluate on held-out maps/seeds before promotion.

### Phase D — general computer use
- Provision OSWorld 2.1 only in a disposable, separately budgeted VM.
- Start with a tiny pinned smoke subset.
- Add AndroidWorld only after the emulator runner is separately reviewed.
- Add Creator Brain workflows and independent state verifiers.

### Phase E — world-model experiment
- Benchmark the cheap predictive baseline.
- Only then test V-JEPA 2 as a background visual predictor.
- Compare prediction error, decision quality, resource cost, and transfer.
- Do not change production routing until paired results pass.

### Phase F — private VTuber rehearsal
- Connect verified event IDs to the stage director.
- Verify playback-grounded avatar motion.
- Run simultaneous game, voice, chat, avatar, and OBS load.
- Measure p95/p99 latency and FPS.
- Require owner visual/listening approval before any public stream.

---

## 13. Research references

1. Google DeepMind, **SIMA 2: An Agent that Plays, Reasons, and Learns With You in Virtual 3D Worlds** (2025-11-13): https://deepmind.google/blog/sima-2-an-agent-that-plays-reasons-and-learns-with-you-in-virtual-3d-worlds/
2. Meta AI, **V-JEPA 2: A Self-Supervised Foundation World Model**: https://ai.meta.com/research/vjepa/
3. V-JEPA implementation: https://github.com/facebookresearch/vjepa
4. XLang, **OSWorld 2.1** current recommended release: https://github.com/xlang-ai/OSWorld-V2/tree/osworld-v2.1
5. OSWorld 2.0 paper: https://arxiv.org/abs/2606.29537
6. Google Research, **AndroidWorld**: https://github.com/google-research/android_world
7. AndroidWorld project and benchmark: https://google-research.github.io/android_world/
8. OpenHands Index: https://index.openhands.dev/
9. OpenHands Software Agent SDK: https://github.com/OpenHands/software-agent-sdk

---

## Acceptance checklist

- [ ] Skill schema is implemented in the existing procedural skill authority, not a parallel store.
- [ ] A skill cannot grant itself a tool permission or bypass the host adapter.
- [ ] Planner, executor, and verifier evidence are separately recorded.
- [ ] At least one skill succeeds on a held-out map/seed or UI/task variant.
- [ ] Failed/expired skills are demoted or retired.
- [ ] OSWorld 2.1 components are pinned to one release before any benchmark run.
- [ ] Benchmark VM contains no owner credentials or personal files.
- [ ] World-model prediction is compared against a cheap baseline.
- [ ] All model-routing changes are paired against the same task set and target hardware.
- [ ] Live audio, game control, owner stop, and avatar deadlines remain protected under background load.
- [ ] Stream commentary is tied to verified events and respects the existing room/floor authority.
- [ ] No public broadcast or irreversible action starts without the existing owner approval.

**Run 37 conclusion:** STAR's next intelligence leap should come from a disciplined loop that turns experience into portable, evidence-backed skills and tests those skills in genuinely new games, apps, and creative workflows. The system should get more capable because its verified skill library improves—not because it accumulates more untested prompts, agents, or model names.
