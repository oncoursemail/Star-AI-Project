# STAR Run 65 — Complete-Game Reliability, Full-Duplex Tool Use, Cross-App Recovery, and Mixed-Load Streaming

**Research date:** 2026-11-16  
**Repository:** `oncoursemail/Star-AI-Project`  
**Branch:** `research/run63-duplex-cue-in-turn-adaptation-20261115`  
**Change type:** source-linked research, read-only catalog expansion, regression-test isolation; no model, hardware, permission, or production default changes.

## Executive decision

The next large capability gain for STAR should be measured as **complete verified outcomes under live mixed workloads**, not as more generated code, more tokens per second, more tool calls, or more agent instances.

Three newly reviewed results sharpen that direction:

1. **CEGame-Bench** exposes the artifact-to-play gap: an agent can build a project that integrates yet still fail to deliver a game that a player can finish and resume.
2. **WindowsWorld** exposes the cross-application gap: agents that handle isolated GUI tasks still struggle when a workflow requires conditional decisions and intermediate state across multiple apps.
3. **Full-Duplex-Bench v3** exposes the speech-to-action gap: natural disfluencies and self-corrections can invalidate an action plan while a spoken agent is already using tools.

For STAR, these are one engineering problem: preserve a trustworthy task state while voice, game, desktop, and background-learning activities overlap.

## 1. New research findings

### 1.1 CEGame-Bench: prove that the game is playable, completable, and resumable

Primary paper: https://arxiv.org/abs/2610.26098  
Submitted: 2026-10-19

CEGame-Bench evaluates long-horizon complete-game creation across Defold, Godot, Roblox Studio, Unity, and Unreal Engine. Tasks start from an empty project and a design document used as a contract. The hidden evaluator accepts the artifact through real-input play, rather than treating successful compilation or integration as game completion.

The paper reports runs averaging up to 295 steps and 65 million tokens. Under its evaluated scaffolds, agents often earned integration points but less than half of gameplay points; only 16% of runs reached the ending. Its Game Completion Boost skill improved execution-based scores by 14.1–24.3 points for three evaluated models. These are paper-specific results, not STAR measurements.

**STAR decision:** introduce a completion contract for every Creator Brain deliverable:

- project opens in the pinned engine/version;
- required scene and assets load;
- player can start from a clean state;
- required controls work with real input;
- critical objectives can be completed;
- failure/restart paths work;
- save state persists and reloads;
- no required asset or script is missing;
- performance and visual budgets are checked;
- evidence is attached to each passed requirement.

A build-success signal is necessary but never sufficient. For Roblox, use an unpublished disposable place and a deterministic simulated-play harness; never publish as part of a benchmark.

Related benchmarks:
- OpenGameEval: https://arxiv.org/abs/2610.02563
- GameDevBench: https://github.com/waynchi/gamedevbench
- GameWorld: https://gameworld-project.github.io/

OpenGameEval's observation/edit separation is especially useful: measure whether STAR inspected the objects and scripts it would change before editing. GameDevBench adds visual feedback for Godot tasks. GameWorld distinguishes progress from state-verifiable completion and has a separate real-time track. Do not collapse these into one score.

### 1.2 WindowsWorld: intermediate checkpoints are essential for computer intelligence

Primary paper: https://aclanthology.org/2026.findings-acl.750/  
Published: Findings of ACL 2026

WindowsWorld contains 181 tasks across 17 desktop applications, averaging about five sub-goals and five intermediate checkpoints per task. Approximately 78% are multi-application workflows. The paper reports that leading agents remained below 21% success on multi-app tasks in its evaluation.

**STAR decision:** expand computer-use acceptance from single-action success to checkpointed workflow correctness:

- record the intended state transition before an action;
- verify each critical intermediate state;
- bind file operations to the user-selected workspace;
- preserve the last known-good artifact;
- detect inherited errors before continuing;
- recover from the last verified checkpoint;
- compare the final artifact with the original request.

Use a disposable Windows profile and resettable application fixtures. Benchmark task completion, checkpoint accuracy, recovery rate, time/step budget, and unintended side effects separately.

### 1.3 CUA-Recovery: error recognition is not recovery

Primary paper: https://arxiv.org/abs/2610.27645

CUA-Recovery describes verified failure states and recovery trajectories across desktop tasks. Its results show that recognizing an inherited error and successfully completing the recovery are separate abilities.

**STAR decision:** use a bounded recovery protocol:

`DETECT → STOP → SNAPSHOT → DIAGNOSE → REPAIR → VERIFY → RESUME`

A failed verification must not be silently treated as success. Recovery must retain the original request and evidence, avoid repeating irreversible actions, and resume only from a verified state. Generated repair scripts remain untrusted until they pass the existing policy and sandbox gates.

### 1.4 Full-Duplex-Bench v3: speech corrections must update action state

Primary paper: https://arxiv.org/abs/2604.04847  
Submitted: 2026-04-06

Full-Duplex-Bench v3 evaluates spoken agents on real human audio containing fillers, pauses, hesitations, false starts, and self-corrections, paired with chained mock-API tasks. It measures tool-use accuracy, latency, and turn-taking. The paper highlights self-correction and dynamic state updates as recurring failure modes. Reported model comparisons are tied to its own audio, tasks, and configurations.

**STAR decision:** connect Run 63's CONTINUE / ADAPT / YIELD / HOLD policy to a versioned pending-action state:

- a correction before dispatch updates the pending arguments;
- a correction after dispatch marks the result stale and triggers a fresh read;
- a correction after a consequential action requires the existing confirmation/compensation policy;
- an utterance addressed to another viewer does not mutate STAR's task;
- uncertain overlap holds the action rather than guessing.

Every tool call must carry a task revision and idempotency key where supported. A result from an older revision must not overwrite newer intent. Never attempt to "undo" a real-world side effect without an explicit, supported compensation action.

Related:
- LiveKit EoT-Bench: https://github.com/livekit/eot-bench
- AdaptDuplex: https://arxiv.org/abs/2609.29217
- InteractionBench: https://arxiv.org/abs/2611.02430

## 2. Unified streaming and task-state architecture

Reuse STAR's existing room director, voice clock, FastLoop/SlowLoop, avatar rig, task/action gates, and governed memory. Do not add a parallel scheduler, voice engine, avatar writer, or memory database.

The shared event envelope should carry only bounded metadata:

- monotonic timestamp and event ID;
- conversation/session ID;
- speaker and addressee when known;
- floor state and confidence;
- active task ID and revision;
- game/desktop event type and source;
- delivery state (queued, submitted, played, cancelled);
- evidence reference, not raw transcript by default.

The room director chooses CONTINUE, ADAPT, YIELD, or HOLD. The strategic planner can reason asynchronously; it must not block microphone capture, playback, or the fast gameplay controller.

### Speech and avatar invariants

- Already-played audio is immutable.
- Only uncommitted TTS segments may be revised or cancelled.
- Each speech segment has a monotonically increasing generation/epoch ID.
- A late TTS or avatar result from an old epoch is dropped.
- The avatar has one writer for each overridden Live2D parameter.
- Lip-sync follows the audible playback clock, not text generation time.
- The stream director may suppress commentary during high-focus gameplay.
- A viewer question remains pending until answered, explicitly deferred, or expired by a transparent policy.

### OBS and VTube Studio integration boundaries

OBS WebSocket 5.x is an RPC/event protocol: https://github.com/obsproject/obs-websocket

The official project recommends password protection. STAR's integration should remain local-only, authenticate, redact secrets, and separate read-only telemetry from state-changing commands. Scene changes, recording start/stop, and streaming actions require their own owner-approved capabilities. Do not expose the OBS WebSocket port to the public internet.

VTube Studio API: https://github.com/DenchiSoft/VTubeStudio/wiki/Plugins

Use explicit plugin authorization, a revocable token stored in the OS secret store, event subscriptions where available, and a single parameter arbiter. Do not poll the entire parameter list at high frequency. New avatar expressions or custom parameters must be checked against the actual model's supported parameter IDs.

## 3. Gamer Brain and Creator Brain acceptance

### Gamer Brain

Keep immediate control and strategic planning separate:

- FastLoop: bounded movement, aiming, camera, jump, dodge, and interaction actions.
- SlowLoop: objectives, map knowledge, strategy, resource management, and replanning.
- Perception: timestamped game-state observations.
- Experience learner: session-separated recordings and reviewed skills.
- Verifier: objective and terminal-state checks.

Report, at minimum:
- task completion and win rate;
- progress separately from completion;
- invalid-action rate;
- deaths/failures and recovery success;
- time and action budget;
- held-out seed/map performance;
- cross-game transfer and negative transfer;
- real-time controller latency and missed deadlines.

Split recordings by session/player/seed, not adjacent frames, to prevent train/validation leakage. Only consented recordings may enter training. Keep a frozen holdout set and compare candidate policies with paired seeds. Promotion and rollback stay in the existing learner gate.

### Creator Brain

Use CEGame-Bench's contract-and-play principle without assuming its scores transfer to STAR. Each project needs:
- a pinned engine/toolchain manifest;
- a machine-readable acceptance contract;
- build/import validation;
- deterministic launch instructions;
- real-input playthrough;
- save/reload verification;
- screenshot/video evidence;
- performance and regression report.

A game that compiles but cannot be completed is a failed deliverable. A scene that looks correct but cannot be interacted with is also a failed deliverable.

## 4. General knowledge and learning quality

Use separate tracks for:
- closed-book parametric recall;
- current web research;
- source-grounded document answers;
- multimodal interpretation;
- multi-hop tool research;
- skill transfer.

Every factual claim used in an important answer should retain provenance, observation time, source freshness, and uncertainty. Contradictory sources should be surfaced rather than silently blended. A correction from a viewer is not automatically a permanent fact or personal memory.

Evaluate:
- factual accuracy;
- citation support;
- freshness;
- calibration/abstention;
- retrieval precision;
- contradiction handling;
- transfer to held-out tasks;
- forgetting and negative interference.

Relevant evaluation references:
- FACTS: https://www.kaggle.com/benchmarks/google/facts
- GAIA: https://arxiv.org/abs/2311.12983
- BrowseComp: https://openai.com/index/browsecomp/
- AgentOdyssey: https://agentodyssey.github.io/
- AGENTCL: https://arxiv.org/abs/2606.02461

## 5. Inference speed: optimize the actual STAR workload

References:
- llama.cpp SPEED-Bench: https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench
- DualDecoder: https://arxiv.org/abs/2607.26475
- FlashOffloading: https://arxiv.org/abs/2611.07542

DualDecoder reports up to 2.62x decode throughput in its evaluated sparse host-memory KV retrieval system. FlashOffloading reports up to 1.91x decode throughput in an Ascend 910C deployment. Neither result is a drop-in optimization for STAR's NVIDIA RTX 4060 8 GB target.

The first STAR optimization campaign should be a reproducible A/B matrix, not a speculative dependency upgrade:

1. Pin model hash, quantization, context, server version, GPU offload layers, CPU threads, batch sizes, slot count, and prompt fixture.
2. Keep the stable system-prefix layout and same-slot request reuse.
3. Do not enable shared cross-conversation KV state or alter cache isolation without dedicated contamination tests.
4. Compare context-local speculative methods before considering a second draft model on 8 GB VRAM.
5. Run cold-start and warm-prefix trials separately.
6. Match concurrency to server slots and repeat each workload.
7. Run mixed-load trials with the game, OBS, voice, avatar, and inference active together.

Measure:
- prompt processing and decode throughput;
- client-observed TTFT and TPOT p50/p95;
- voice end-of-turn to client-heard audio;
- queue wait and cancellation age;
- peak VRAM, system RAM, CPU use;
- game FPS/frame-time and missed control deadlines;
- avatar frame drops;
- audio underruns and OBS render/encode lag;
- verified task success and recovery rate.

An optimization is accepted only when task quality and streaming safety do not regress. Higher tokens/second alone is not a release criterion.

## 6. Run 65 repository changes

- Added four reviewed, HTTPS, research-only Game Lab entries: CEGame-Bench, Full-Duplex-Bench v3, WindowsWorld, and the official OBS WebSocket protocol.
- Added catalog regression tests for discoverability, caveats, category routing, and local-API security wording.
- Isolated the cold-start warm-up test from process-global `turn_memory` state. The previous Windows shard failure showed that another test could leave a prior request shape for the same project; the test now explicitly models a cold start instead of depending on test order.
- No new runtime dependencies, network clients, permissions, model routes, scheduler, memory store, or production defaults were introduced.

### CI finding that motivated the test repair

Workflow run #43814711224 had successful React desktop assets, successful Windows packaging/install smoke test, and a successful first Windows offline shard. The second Windows offline shard had 4,878 passed, 99 skipped, and one failure:

`tests/test_knowledge_bank.py::test_real_and_warmup_prefixes_include_the_same_bank`

The mismatch was caused by the test assuming a cold plain-chat request while process-global `turn_memory` could retain a previous request shape. The repair mocks only the shape lookup for this cold-start test; production warm-up behavior is unchanged.

Linux offline checks and Pyright passed on the preceding head. The new exact-head workflows must complete before the repair is called verified.

## 7. Run 66 acceptance sequence

1. Confirm the new catalog and warm-up test pass on Linux and Windows.
2. Run the full Python suite and React suite on the exact commit.
3. Add a deterministic Full-Duplex-Bench-inspired mock harness for spoken corrections and stale action revisions; do not import raw benchmark audio without license/consent review.
4. Add checkpointed WindowsWorld-style tasks to a disposable Windows test profile.
5. Add CEGame-Bench-inspired completion contracts to a small, licensed internal Roblox/Godot fixture set.
6. Evaluate held-out gameplay policies with fixed seeds and state-based terminal conditions.
7. Integrate client-heard audio timing, avatar epochs, and OBS event timestamps into the existing telemetry path.
8. Run a target-PC mixed-load rehearsal only with owner-approved devices and local integrations.
9. Require human review of any OBS scene/recording/stream control capability.
10. Keep all new behavior disabled or research-only until acceptance evidence is recorded.

## Sources reviewed

- CEGame-Bench, 2026-10-19: https://arxiv.org/abs/2610.26098
- OpenGameEval, 2026-10-01: https://arxiv.org/abs/2610.02563
- GameDevBench: https://github.com/waynchi/gamedevbench
- GameWorld: https://gameworld-project.github.io/
- WindowsWorld, Findings of ACL 2026: https://aclanthology.org/2026.findings-acl.750/
- CUA-Recovery, 2026-10-20: https://arxiv.org/abs/2610.27645
- Full-Duplex-Bench v3, 2026-04-06: https://arxiv.org/abs/2604.04847
- LiveKit EoT-Bench: https://github.com/livekit/eot-bench
- AdaptDuplex: https://arxiv.org/abs/2609.29217
- InteractionBench: https://arxiv.org/abs/2611.02430
- OBS WebSocket: https://github.com/obsproject/obs-websocket
- VTube Studio API: https://github.com/DenchiSoft/VTubeStudio/wiki/Plugins
- llama.cpp SPEED-Bench: https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench
- DualDecoder: https://arxiv.org/abs/2607.26475
- FlashOffloading, 2026-11-05: https://arxiv.org/abs/2611.07542
- FACTS: https://www.kaggle.com/benchmarks/google/facts
- GAIA: https://arxiv.org/abs/2311.12983
- BrowseComp: https://openai.com/index/browsecomp/
- AgentOdyssey: https://agentodyssey.github.io/
- AGENTCL: https://arxiv.org/abs/2606.02461
