# STAR Run 31 — Real-Time Screen-to-Action Gaming, Verified Skill Evolution, and Natural VTuber Presence

**Research date:** 2026-11-14  
**Repository:** `oncoursemail/Star-AI-Project`  
**Research branch:** `research/star-run24-integration-blueprint-20261114`  
**Parent:** draft PR #1180, based on production `main`  
**Related implementation trains:** #1139, #1151–#1155, #1159–#1167, #1171–#1181  
**Acceptance anchor:** issue #584 — STAR Creator Studio: production VTuber, games, live chat, multistream and auto-editing acceptance  
**Scope:** real-time screen-to-controller gameplay, action freshness, Windows capture/input boundaries, verifier-grounded skill evolution, cross-game transfer, and playback-grounded avatar expression.

---

## Executive decision

STAR's most important remaining gaming gap is not another game-planning prompt or another game API. The acceptance issue requires **permitted actual screen-to-controller gameplay** and explicitly distinguishes that from a robotic Studio playtest or direct game-state access.

Build one narrow, host-owned game-control path:

**capture → perceive → plan → validate action → execute → observe outcome → verify → learn**

The new path must operate on the visible game and ordinary permitted controls for approved games. It must not bypass anti-cheat, inspect protected game memory, inject into another process, exploit Roblox remotes, or treat a benchmark's privileged state API as evidence of real screen-to-controller ability.

The key design insight from the latest real-time benchmark research is that a screenshot-based agent can be strategically correct and still fail because the world changes while the model is thinking. STAR therefore needs a fast, bounded control loop between slower strategic reasoning. It also needs a hard freshness gate so an action derived from an obsolete frame cannot reach the input adapter.

The companion learning decision is equally important: **an experience is not a skill until an independent verifier supports the claim.** Successful behavior should become a reusable skill; failures should become corrective lessons; later evidence must be able to contradict, replace, or retire either one.

This run adds the source-grounded architecture and a small deterministic action-safety policy to a separate draft implementation PR. It does not claim that the Windows capture or input executor is already connected.

## 1. Repository audit: preserve the existing foundations

The following components already exist on `main` or in active draft trains. The Run 31 design reuses them rather than introducing competing authorities.

| Existing component / PR | Existing responsibility | Run 31 decision |
|---|---|---|
| `star/game_lab_catalog.py` | Reviewed, read-only Game Lab source catalog | Extend its research index with real-time game, continual-learning, and Windows capture/input references; keep every new source research-only |
| `star/skill_evolution_lab.py` | Bounded candidate search with development feedback and sealed holdout evaluation | Reuse for skill-document evolution; never disclose sealed holdout results to the proposer |
| `star/game_projects.py` / workspace tools | Bounded project discovery, inspection, and command planning | Reuse for Creator Brain project inspection; execution remains a separate permissioned phase |
| PR #1139 | Optional, owner-approved cross-session stream continuity for signed gameplay practice evidence | Reuse as the only proposed cross-session gameplay continuity store; do not persist viewer profiles or raw media |
| PRs #1132–#1134 | Bounded, privacy-safe causal tracing and trace analysis | Add game capture, action, and verification spans through the existing trace adapters |
| PRs #1135 / #1165 | Private stream rehearsal and extended interaction quality gates | Reuse for game + voice + avatar mixed-load acceptance |
| PR #1138 | Evidence-bounded stream bottleneck triage | Use for diagnosis, not a second scheduler |
| PRs #1140 / #1142 | Authoritative resource admission and stream-pressure governance | Keep as the only resource-admission authority |
| PRs #1151–#1153 | Playback timing, audio isolation, trusted host telemetry and coherent sampling | Reuse trusted host clocks and measured audio/game/OBS health |
| PRs #1154 / #1155 | Versioned task ledger and absolute-deadline correctness | Reuse for long-running game/creator jobs; no new task ledger |
| PRs #1156–#1158 | Segmented delivery, durable delivery recovery, and trace correlation | Reuse for result delivery; game completion is not complete until its report is actually delivered |
| PR #1159 | Latest-wins Live2D frame pump with playback-epoch checks | Reuse for avatar samples only; never apply latest-wins coalescing to ordered gameplay actions |
| PRs #1160 / #1161 | Stable-prefix incremental thinking and scheduler admission | Reuse only for speculative preparation; partial ASR cannot authorize game input |
| PRs #1162–#1164 | Calibrated thinker resource budgets and process telemetry | Reuse measured process resource vectors rather than guessed model costs |
| PRs #1165 / #1166 / #1167 | Interaction quality, paired holdout evaluation, and streamed inference timing | Reuse for all candidate comparisons |
| PRs #1171–#1178 | Room turn director, queue, payload store, host, desktop bridge, and natural streamer persona | Route only verified, high-confidence game events through the existing room host |
| PR #1181 | Speaker RMS metering moved off the high-priority PortAudio callback | Keep audio callback work bounded; game perception must not steal the voice/audio reserve |
| PR #1180 | Runs 24–30 integration research | This document adds the missing real-time screen-to-action and evidence-evolution layer |

### Confirmed missing acceptance capability

Issue #584 still lists the actual screen-to-controller game-play milestone as not achieved. The repository has game-development tooling, skill evolution, project inspection, and research plans, but the reviewed acceptance contract does not establish a production Windows screen-capture + game-input executor for arbitrary permitted games.

Treat this as a genuine integration gap, not as an already-shipped feature.

## 2. Research finding: real-time game play is a latency problem as well as a reasoning problem

### 2.1 Gym-Anything-RT

Primary sources:

- Paper: https://arxiv.org/abs/2610.37567
- Project/code: https://github.com/gym-anything/gym-anything-rt

Gym-Anything-RT constructs 100 real-time visual minigames and pairs each with a non-real-time counterpart. It varies the environment clock while keeping the task, controls, and information comparable. The full matrix spans 100 games, five difficulty levels, two interaction modes, and real-time / non-real-time timing conditions.

A headline result from the paper: GPT-6 Astra (xHigh) passed 9% of the live real-time tasks, versus 57% with the environment slowed to 64× and 75% when the environment was paused. The same work reports that a sandboxed code-assisted visual controller raised the live result in its tested setup, illustrating the value of fast perception/action between model calls.

**Interpretation for STAR:** a large model's paused score is not its real-time gaming ability. Report live, slowed, and paused performance separately. A system that succeeds only when the game waits is a useful planner, but it is not yet a real-time player.

### 2.2 GameWorld

Primary source: https://gameworld-project.github.io/

GameWorld provides 34 browser games and 170 tasks across runner, arcade, platformer, puzzle, and simulation genres. It compares computer-use and multimodal generalist agents under a shared environment and scores both normalized progress and task success from serialized game state.

The benchmark's published results show why task completion must be scored separately from partial progress: strong systems can accumulate meaningful progress while still failing to complete the task. Its verifiers inspect task-relevant game state rather than asking an LLM to judge a screenshot.

**Interpretation for STAR:** use state-verifiable sandbox benchmarks to test planning and strategy, but do not let those results stand in for screen-only gameplay. Maintain separate tracks:

1. **Privileged sandbox track:** game APIs or serialized state may be used by the verifier and, where allowed, by the agent.
2. **Computer-use track:** the agent sees rendered frames and uses the permitted visible controls.
3. **Real-time track:** the game clock continues while the agent reasons.
4. **Transfer track:** unseen maps, seeds, or games test whether the skill generalized.

Never combine these scores into one headline number.

### 2.3 What this means for STAR's runtime

The control loop must not wait for a full high-level reasoning response on every frame. Use three rates:

- **Fast control:** a deterministic, small, game-specific controller executes short bounded actions and handles immediate corrections.
- **Visual perception:** a lightweight vision path tracks the current scene, HUD, hazards, objectives, and state changes; expensive VLM calls are event-triggered.
- **Strategic reasoning:** STAR's general model chooses goals, plans routes, explains mistakes, and revises strategy asynchronously.

The fast controller must remain simple and inspectable. It may not invent a game API, inspect protected memory, or bypass the visible control surface. The strategic model can suggest an action, but the host gate decides whether that action is fresh and permitted.

## 3. Windows capture research: keep frames fresh and avoid needless GPU copies

Primary Microsoft documentation:

- Desktop Duplication API: https://learn.microsoft.com/en-us/windows/win32/direct3ddxgi/desktop-dup-api
- `AcquireNextFrame`: https://learn.microsoft.com/en-us/windows/win32/api/dxgi1_2/nf-dxgi1_2-idxgioutputduplication-acquirenextframe
- `ReleaseFrame`: https://learn.microsoft.com/en-us/windows/win32/api/dxgi1_2/nf-dxgi1_2-idxgioutputduplication-releaseframe

The DXGI Desktop Duplication API exposes desktop frames through a DXGI surface in GPU memory and provides dirty-region / move-region metadata. It can capture visible full-screen DirectX applications. The capture path must handle `DXGI_ERROR_ACCESS_LOST` after desktop switches, display-mode changes, or full-screen transitions. Microsoft also recommends releasing the current frame before acquiring the next one and minimizing the interval between those operations.

### Proposed capture adapter

The future Windows host adapter should:

1. Require an owner-approved game session and exact target process identity.
2. Capture only the selected display/window region needed for the game; never forward the whole desktop to the model by default.
3. Keep the source texture GPU-resident where possible; crop/resize on the GPU before transferring a compact observation.
4. Use dirty/move metadata to avoid reprocessing unchanged regions where the perception algorithm can safely use it.
5. Attach a monotonic timestamp, frame sequence, opaque frame ID, target process-start token, and capture epoch to each observation.
6. Use a single latest-frame slot for perception. If the model falls behind, discard superseded frames instead of building a stale FIFO.
7. Treat access loss, resolution changes, display switches, protected-content frames, or unknown capture state as a pause requiring a fresh frame and revalidation.

The frame queue is a time-sample stream, so latest-wins is appropriate for perception. **It is not appropriate for actions:** actions must remain ordered, individually validated, and tied to the exact observation that produced them.

## 4. Windows input research: distinguish device input from automation input

Primary sources:

- Win32 `SendInput`: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput
- Microsoft GameInput: https://aka.ms/gameinput
- GameInput PC 3.4 announcement: https://developer.microsoft.com/en-us/games/articles/2026/05/gameinput-update-now-available/

### 4.1 SendInput limitations

Win32 `SendInput` inserts keyboard/mouse events serially into the system input stream. It is subject to User Interface Privilege Isolation (UIPI), does not reset pre-existing key state, and does not guarantee operation in every application. It is not a game-specific automation API and must not be treated as a way to defeat a game's input protections.

If used for an explicitly permitted foreground game, the trusted host must verify the foreground window/process immediately before execution, use a narrow per-game control allowlist, issue short bounded holds, and release all held controls on focus loss, stop, exception, or session end.

### 4.2 GameInput is not a synthetic-input bypass

Microsoft GameInput provides a unified, timestamped interface for reading physical keyboards, mice, gamepads, and other input devices. It is useful for observing physical input and detecting manual override. It is not a blanket permission to synthesize controller input into arbitrary games.

For the first desktop pilot:

- Use GameInput (or the existing approved device reader) for physical-input observation and manual override.
- Use the simplest documented, permitted control path for the approved game.
- Do not install a virtual HID driver or emulate protected hardware.
- Do not bypass anti-cheat, platform rules, or game restrictions.
- Prefer official game APIs and Studio tools for development/testing environments, while keeping those results separate from screen-only play.

## 5. New deterministic action-safety contract

A new pure policy module is proposed in draft PR #1182: `star/game_control_gate.py`.

It is deliberately **not** an input executor. It validates host-provided facts and emits a short-lived permit that a future trusted adapter may consume.

### Required session facts

- Owner consent for this exact game session.
- Explicit game/process allowlist entry.
- Host-confirmed permission for automation in that game.
- Process ID plus process-start token (to reject PID reuse).
- Exact foreground window identity.
- Executable digest / version identity.
- Session ID and monotonic expiry.
- Manual-input state from the trusted host.

### Observation contract

Every observation carries:

- Session ID.
- Target fingerprint.
- Monotonic capture timestamp.
- Strictly increasing frame sequence.
- Opaque frame ID.
- Capture epoch.

The host must reject a frame from another process, another session, an earlier capture epoch, a future timestamp, or an expired freshness window.

### Action contract

Every proposed action carries:

- Unique action ID.
- Session ID.
- Exact frame ID and observation sequence.
- Monotonic issue time.
- Bounded button/key set from the game's reviewed allowlist.
- Bounded mouse delta, if the game uses mouse look.
- Short duration / expiry.

The gate rejects stale-frame actions, duplicate IDs, out-of-order frames, unapproved controls, oversized mouse movement, excessive action rate, and actions issued after the session deadline.

### Immediate stop conditions

Any of the following revokes the session and returns the currently held controls for release:

- Owner presses stop.
- Physical user input/manual override is detected.
- The game loses foreground focus.
- The process identity or window identity changes.
- Owner consent or game permission is revoked.
- The session expires.
- The capture epoch changes or the trusted host reports an unsafe target state.

A stop must not wait for the model. The host owns the stop path and the actual release of controls.

### Trust boundary

The pure gate cannot independently prove that a process is allowlisted, that consent was genuinely granted, or that a game permits automation. Those facts must come from a trusted host service, not model-generated text or viewer chat. The gate must not expose arbitrary shell execution, arbitrary window selection, or OS-level permission changes.

## 6. Verifier-grounded skill evolution: learn from wins and losses without corrupting memory

Primary sources:

- KEEL paper: https://arxiv.org/abs/2610.34043
- KEEL implementation: https://github.com/microsoft/KEEL-TTCL26
- Continual-ARC benchmark: https://github.com/unifyai/continual-arc

KEEL separates reusable expertise (successful procedural behavior) from corrective lessons (mistakes, violated constraints, and recovery strategies). Its key mechanism is claim-level evidence management: verifier outcomes can support, contradict, replace, or retire a skill claim. The paper reports improvements on its SkillFlow benchmark, but those results are not STAR measurements.

Continual-ARC makes a second useful methodological distinction: performance on tasks already seen during learning is not the same as performance on held-out tasks. It compares the learner after a stream of experience with the same learner reset, separating retained knowledge from the base model/harness capability.

### Apply this to STAR's existing skill system

Do not create another memory store. Extend the evidence and evaluation path around the existing GameplaySkillBank / skill-evolution / cross-session-continuity work.

Each reusable game skill should record:

| Field | Purpose |
|---|---|
| game + version | Prevent applying a skill to a changed game build |
| map / mode / seed scope | Record where the skill was actually tested |
| preconditions | State required before the action sequence is valid |
| objective | Exact task the skill attempts to solve |
| action procedure | Bounded, human-readable steps or controller policy |
| expected outcome | What a verifier should observe |
| evidence references | Opaque links to trusted test receipts / replay evidence |
| positive evidence | Which independent checks passed |
| negative evidence | Which checks failed and what they establish |
| confidence / status | Candidate, supported, contradicted, superseded, retired |
| last verified | Age and environment freshness |
| limitations | Known maps, modes, versions, and failure cases |

### Promotion rules

1. A model may propose a skill or corrective lesson from a trajectory.
2. A deterministic validator checks the schema, scope, size, and forbidden instructions.
3. An independent environment verifier checks the actual outcome.
4. Development tasks may be used to refine the candidate.
5. Freeze the candidate before the sealed holdout.
6. Compare baseline and candidate on the same held-out tasks, seeds, and environment.
7. Promote only after the existing paired evaluator reports sufficient coverage and a statistically supported gain without safety or performance regression.
8. Keep promotion owner-reviewed; no automatic weight update or production deployment.
9. New contradictory evidence can demote, replace, or retire a previously supported skill.

A failure is not automatically a corrective lesson: the analyzer must connect the failed verifier check to a behavior in the trajectory. Infrastructure failure, missing evidence, or an inconclusive test must not update the knowledge bank.

### Transfer matrix

Evaluate a skill in increasing order of difficulty:

- Same game, same map, new seed.
- Same game, different map.
- Same game, different mode or difficulty.
- Same mechanics, different game.
- Unrelated game as a negative control.

Record success rate, completion time, action count, failure/recovery rate, observation age, action age, and performance under mixed streaming load. Keep the holdout task roster hidden from the model proposer.

## 7. Natural VTuber presence: game awareness should enrich conversation, not dominate it

Additional research:

- JAVIS: https://arxiv.org/abs/2610.22499
- Realtime-Venus: https://realtime-venus.github.io/
- Existing STAR VTube Studio integration research and frame-pump work: PRs #1159, #1168, #1178, #1180

JAVIS investigates generating speech and facial motion from a shared representation. Its paper reports lower initial latency and improved synchronization in its own experimental setup; this is a research result, not a drop-in Live2D/VTube Studio integration. Realtime-Venus demonstrates the complementary two-loop architecture: one loop keeps live perception and speech responsive while a second performs delegated work and returns results to the same conversation.

### STAR's practical Live2D direction

Keep the current playback-authoritative avatar architecture:

- Mouth/jaw timing follows the actual audio playback cursor.
- Semantic intent and affect choose expression families, gaze, head pose, and gesture intent.
- A bounded StagePlan translates those intents into approved Live2D parameters.
- The latest-wins frame pump coalesces obsolete animation samples.
- An interruption flushes the current playback epoch before neutral pose.
- No generated avatar frame may claim that STAR said a word or expressed an emotion that was not in the actual response.

The new insight from joint audio-visual research is to avoid treating the face as a purely decorative afterthought. Speech intent and facial expression should share one semantic event, while actual playback remains the timing authority.

### Streaming behavior

- Keep natural pauses; do not fill every silence.
- Distinguish direct questions, backchannels, side conversations, corrections, and game events.
- Do not interrupt a viewer or the owner for low-confidence game commentary.
- Use brief, evidence-grounded reactions to visible events.
- Avoid repeating the same reaction template.
- Allow quiet-focus / mention-only / co-host / game-coach modes from Run 30.
- Preserve transparent AI identity; never invent a biological human autobiography, private human experiences, or fake offline memories.

A believable streamer is not one that talks constantly. It is one that notices the right event, responds at the right time, and knows when not to speak.

## 8. General knowledge: reuse the same evidence lifecycle, but keep facts separate from skills

STAR should maintain two distinct knowledge types:

1. **Declarative claims:** facts about a subject, API, event, or world state. Each claim needs a source, source date, scope, freshness, confidence, and contradiction history.
2. **Procedural skills:** a sequence or policy that achieves a verified outcome in a specific environment. Each skill needs preconditions, environment/version scope, verifier evidence, and transfer tests.

A fact is not a skill; a successful game trajectory is not proof of a general factual claim. The same evidence lifecycle can support, contradict, replace, or retire either type, but their verifiers differ.

For general research, preserve:
- source provenance and retrieval date;
- primary vs secondary source distinction;
- contradictory claims;
- stale-source warnings;
- explicit unknowns;
- confidence calibrated to evidence;
- separation between remembered user/project decisions and public factual knowledge.

Viewer chat, donations, and platform identities must never become persistent factual memory by default.

## 9. Speed and mixed-load engineering

The main speed improvement is reducing stale work and avoiding high-cost reasoning on every frame—not blindly loading a larger model.

### Recommended execution shape

- Capture frames into a bounded latest-wins perception slot.
- Run inexpensive visual tracking and HUD/OCR continuously only where needed.
- Trigger larger multimodal reasoning on meaningful scene changes, objective transitions, unexpected failure, or uncertainty.
- Execute short deterministic actions while the strategy model works on the next decision.
- Cancel old plans when the frame, target, game state, or session generation changes.
- Preserve ordered action events and stop/release semantics.
- Admit optional perception and planning through the existing #1140/#1142 resource authority.
- Reserve the RTX 4060's limited VRAM for the most latency-sensitive active workload; benchmark CPU perception and inference alternatives before moving workloads.

### Required mixed-load experiment

Run the same seeded game task under:

1. Game only.
2. Game + screen capture/perception.
3. Game + voice/ASR/TTS.
4. Game + avatar + OBS.
5. Game + voice + avatar + OBS.
6. Full stream plus background research/learning.

Record separately:
- capture-to-observation age;
- observation-to-action decision latency;
- action age at execution;
- action-to-visible-result latency;
- p50/p95/p99 for each;
- game frame-time p50/p95/p99 and 1% lows;
- CPU, RAM, process VRAM, GPU utilization;
- audio callback duration/underruns;
- OBS render skips vs output skips;
- first audible speech latency;
- avatar playback synchronization;
- task success and held-out transfer.

Never subtract unrelated p95 values to claim a critical path. Correlate measurements by the existing trace/run ID and host monotonic clock. Missing, stale, or cross-epoch telemetry is INCONCLUSIVE, not a healthy zero.

## 10. Phased implementation plan

| Phase | Work | Exit evidence |
|---|---|---|
| A — Policy foundation | Add the pure game action freshness/consent gate | Offline tests prove stale, replayed, wrong-process, unfocused, expired, or unapproved actions are rejected |
| B — Windows capture | Build a target-window capture adapter with frame epochs and GPU-resident processing | Hardware capture tests, access-loss recovery, no stale FIFO, privacy crop tests |
| C — Input executor | Add a host-only, per-game permitted control adapter | Foreground verification, short action holds, manual override, immediate stop/release |
| D — Benchmark harness | Integrate GameWorld and Gym-Anything-RT where licensing/terms allow | Separate sandbox, computer-use, live, slowed, and paused scores |
| E — Skill evolution | Connect verifier receipts to skill/lesson claims | Paired held-out transfer, no stale-skill reuse, no automatic promotion |
| F — VTuber/game bridge | Route only high-confidence game events through the existing room host | Natural silence/turn-taking, no duplicate speech, playback-grounded avatar |
| G — Creator completion | Reuse Roblox Studio MCP / StudioTestService and existing creator checks | Complete real-input player journeys, endings, save/reopen, replay after repair |

### Immediate order

1. Land and review the pure action-safety policy.
2. Build the Windows capture adapter.
3. Implement one permitted game input adapter with a hard owner stop.
4. Validate a simple, noncompetitive game before adding complex titles.
5. Measure live-vs-paused performance.
6. Connect verified game events to STAR's existing room and avatar pipeline.
7. Expand to more genres only after the first title passes.

## 11. Acceptance gates for issue #584

The following are required before STAR can be called a real game-playing VTuber:

- [ ] Owner explicitly arms a named, permitted game session.
- [ ] Capture is limited to the approved target.
- [ ] Process identity and foreground focus are verified.
- [ ] Manual physical input immediately preempts STAR.
- [ ] Every action is bound to a fresh observation and a short expiry.
- [ ] Stop/focus loss/session expiry releases all held controls without waiting for a model.
- [ ] No anti-cheat bypass, game-memory inspection, exploit, or unauthorized remote invocation.
- [ ] A real visible screen-to-controller playthrough succeeds.
- [ ] A separate privileged sandbox benchmark is clearly labeled as such.
- [ ] A held-out seed/map test demonstrates improvement beyond the baseline.
- [ ] Cross-game transfer is measured rather than assumed.
- [ ] Streaming remains responsive under the mixed-load matrix.
- [ ] Viewer chat cannot arm game control or invoke tools.
- [ ] STAR's game commentary is grounded in observed events.
- [ ] Avatar motion follows actual playback.
- [ ] AI identity remains transparent.
- [ ] Whole-repo CI, Windows-native acceptance, private rehearsal, and owner approval pass before any public broadcast.

## 12. Research source register

### Real-time game interaction

- Gym-Anything-RT paper: https://arxiv.org/abs/2610.37567
- Gym-Anything-RT code: https://github.com/gym-anything/gym-anything-rt
- GameWorld benchmark: https://gameworld-project.github.io/
- LMGame GamingAgent: https://github.com/lmgame-org/GamingAgent

### Windows capture and input

- Microsoft Desktop Duplication API: https://learn.microsoft.com/en-us/windows/win32/direct3ddxgi/desktop-dup-api
- Microsoft AcquireNextFrame: https://learn.microsoft.com/en-us/windows/win32/api/dxgi1_2/nf-dxgi1_2-idxgioutputduplication-acquirenextframe
- Microsoft ReleaseFrame: https://learn.microsoft.com/en-us/windows/win32/api/dxgi1_2/nf-dxgi1_2-idxgioutputduplication-releaseframe
- Microsoft SendInput: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput
- Microsoft GameInput: https://aka.ms/gameinput
- GameInput 3.4: https://developer.microsoft.com/en-us/games/articles/2026/05/gameinput-update-now-available/

### Continual learning and evidence

- KEEL paper: https://arxiv.org/abs/2610.34043
- KEEL code: https://github.com/microsoft/KEEL-TTCL26
- Continual-ARC: https://github.com/unifyai/continual-arc

### VTuber audio-visual behavior

- JAVIS paper: https://arxiv.org/abs/2610.22499
- Realtime-Venus: https://realtime-venus.github.io/

### Existing STAR acceptance / implementation references

- STAR Creator Studio acceptance: https://github.com/oncoursemail/Star-AI-Project/issues/584
- Existing research integration PR: https://github.com/oncoursemail/Star-AI-Project/pull/1180
- Existing voice callback improvement: https://github.com/oncoursemail/Star-AI-Project/pull/1181
- Existing Game Lab source catalog: https://github.com/oncoursemail/Star-AI-Project/blob/main/star/game_lab_catalog.py

---

## Scope and limitations

- This is a research and policy-foundation run; it does not add a Windows DXGI capture adapter or a live input executor.
- The action gate is a deterministic authorization/freshness primitive, not proof that its host-provided process/consent facts are true.
- No game was launched or controlled in this run.
- No anti-cheat, DRM, protected-content, or game-platform boundary was bypassed.
- No Twitch/YouTube, OBS, VTube Studio, microphone, RTX 4060, Roblox Studio, or physical gameplay acceptance was performed.
- No model weights, inference defaults, resource thresholds, broadcast permissions, or production `main` were changed.
- Research-paper results are not STAR measurements.
- The implementation PR remains draft and must pass exact-head GitHub Actions and owner review before merge.
