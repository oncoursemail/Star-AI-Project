# STAR Run 68 — Generalist capability gates, grounded knowledge, and real-time reliability

**Research date:** 2026-11-16  
**Status:** research + evaluator hardening; no production runtime, model, permission, or routing default changed.

## Executive decision

STAR should grow through **verified capabilities**, not an ever-growing collection of disconnected agents and toggles.

The current repository already has useful foundations:

- `star/agent.py` owns the model/tool loop and untrusted-tool-result boundary.
- `star/context_layout.py` keeps stable system/project context ahead of append-only history and volatile per-turn context so llama.cpp can reuse a prompt prefix.
- `star/local_runtime.py` launches an explicitly selected llama.cpp server on loopback and currently limits the managed router to one resident model.
- `star/evals.py`, `star/eval_runner.py`, `star/eval_checks.py`, `star/eval_gate.py`, and `star/eval_stats.py` define and gate evidence-backed improvements.
- `star/voice/turn.py` provides deterministic frame-level VAD/endpointer state transitions.
- Existing memory, lesson, policy, Studio, and play/learn code should remain the authorities for their domains.

Runs 66–67 add offline evaluators for gameplay commentary and higher-level voice turn policy. This run hardens one evaluator's input boundary and specifies how to connect capability evaluation to the existing system without creating parallel schedulers, memory stores, voice engines, or permission authorities.

## 1. Concrete infrastructure repair in Run 68

### Bounded iterable consumption

The gameplay-commentary evaluator previously called `list(observations)` before enforcing `MAX_OBSERVATIONS`. A large or unbounded iterable could therefore consume unbounded time and memory before the limit was checked.

The evaluator now:
1. consumes observations incrementally;
2. rejects the first item beyond the configured maximum;
3. validates the row type before retaining it; and
4. stops consuming the generator immediately after the limit is exceeded.

A deterministic regression test lowers the module limit to three and proves that a generator's fourth item triggers rejection while the remaining tail is never consumed.

This is an offline-evaluation reliability fix. It does not change STAR's live stream behavior or action policy.

## 2. General intelligence: measure useful work, not eloquence

A general assistant must combine retrieval, reasoning, tool use, multimodal interpretation, and verification. No single benchmark captures all of those.

### GAIA — general assistant tool-use

Primary source: https://arxiv.org/abs/2311.12983

GAIA tasks combine reasoning, multimodal handling, web browsing, and tool use. Use a licensed/available benchmark split to measure end-to-end completion, not just answer style.

STAR should record:
- task success and exact evaluator evidence;
- tool calls and unnecessary calls;
- recovery after failed tools;
- answer abstention when evidence is insufficient;
- wall-clock and token cost;
- whether a result was actually opened/read rather than merely named.

### BrowseComp — persistent research

Primary source: https://openai.com/index/browsecomp/

BrowseComp contains 1,266 difficult, short-answer browsing problems designed to test persistent search and evidence assembly. Its authors emphasize that browsing alone is insufficient: the agent must plan search pivots, evaluate factuality, and combine scattered evidence.

STAR research workflow:
1. translate the request into answerable claims;
2. search broadly, then pivot based on evidence;
3. open primary sources and inspect relevant passages;
4. track conflicting and stale claims;
5. require independent support for important conclusions;
6. answer with claim-level citations or explicitly abstain;
7. preserve a compact research trace with source dates and provenance.

Do not expose or copy benchmark canaries/held-out answers into training or retrieval memory. Use a protected evaluation split.

### FACTS Grounding and LongFact/SAFE — factuality

Primary sources:
- https://deepmind.google/blog/facts-grounding-a-new-benchmark-for-evaluating-the-factuality-of-large-language-models/
- https://deepmind.google/research/publications/85420/

FACTS Grounding separates answer eligibility from whether claims are supported by the supplied document. LongFact/SAFE breaks long answers into individual claims and checks them against search evidence.

STAR should measure separately:
- relevance/completeness;
- supported-claim precision;
- important-claim coverage;
- citation correctness;
- unsupported specificity;
- correct uncertainty/abstention.

Never turn an LLM judge's score into ground truth. Calibrate judges against human-reviewed samples and preserve disagreement.

## 3. Cross-application and desktop intelligence

### OSWorld

Primary source: https://os-world.github.io/

OSWorld supplies reproducible real-computer tasks with initial state setup and execution-based evaluation. Its published 369-task benchmark illustrates the gap between fluent descriptions and reliable GUI execution.

### WindowsWorld

Primary source: https://arxiv.org/abs/2604.27776

WindowsWorld focuses on multi-application workflows: 181 tasks across 17 desktop apps, with most tasks requiring multiple applications. The paper reports leading agents below 21% success on its multi-app tasks.

STAR application:
- express a workflow as a graph of verifiable state transitions;
- checkpoint after every irreversible or high-cost step;
- store artifact IDs and app state, not a long unstructured click transcript;
- re-observe after window changes, dialogs, focus loss, or unexpected results;
- resume from the last verified checkpoint after failure;
- require a final artifact/state verifier before declaring completion.

Use disposable environments for automated evaluation. Keep the existing owner permission gates for real machine actions.

## 4. Gamer Brain: generalist policy plus game-specific state

Primary sources:
- SIMA 2: https://deepmind.google/blog/sima-2-an-agent-that-plays-reasons-and-learns-with-you-in-virtual-3d-worlds/
- NitroGen: https://nitrogen.minedojo.org/
- NitroGen repository: https://github.com/MineDojo/NitroGen
- Voyager: https://arxiv.org/abs/2305.16291
- Voyager code: https://github.com/MineDojo/Voyager

These projects point to complementary roles:

- **Strategic planner:** goals, subgoals, map, inventory, opponent/team model, and recovery.
- **Fast visual-action policy:** short-horizon movement or controller proposals.
- **Game adapter:** legal actions, state observations, reset, snapshot, and task-specific success conditions.
- **Experience/skill library:** reusable procedures with preconditions, effects, provenance, version, and test history.
- **Independent verifier:** proves whether the expected state change occurred.

NitroGen's official repository explicitly describes the released 500M model as a fast-reacting, latest-frame policy, not a long-horizon planner, end-to-end player, or self-improving system. Treat it as a research candidate for a reflex layer only.

Voyager's skill-library pattern is valuable, but executable skills must never become trusted just because an LLM generated them. Store a declarative skill contract first; execute only inside an isolated, disposable environment with bounded tools and verified postconditions. Reuse the repository's existing skill-contract work when integrated rather than introducing a second schema.

### Game learning protocol

For each new game:
1. identify the game/version and available observation/action interface;
2. inspect controls and legal actions;
3. run low-risk mechanic probes from repeatable states;
4. infer candidate mechanics and confidence;
5. test candidate mechanics with matched starts and controlled interventions;
6. create short skills with preconditions and postconditions;
7. practice against held-out seeds/maps/opponents;
8. record wins, losses, invalid actions, time, damage/resources, and stuck loops;
9. retain only verified skill revisions;
10. re-test old games to detect negative transfer or forgetting.

Do not claim mastery from one successful run. Report sample count, task distribution, confidence intervals, and held-out performance.

## 5. Creator Brain: prove the game is playable

Primary source: https://arxiv.org/abs/2610.26098

CEGame-Bench evaluates long-horizon complete-game creation across Defold, Godot, Roblox Studio, Unity, and Unreal Engine. The paper reports that only 16% of agent runs reached the ending in its evaluated setup, despite substantial integration progress. Its Game Completion Boost approach emphasizes requirement-driven playtesting and repair.

Use the same acceptance contract for STAR-created games:

`inspect → requirements contract → build → launch → real input → objective verification → save → reload → regression`

For Roblox:
- use a disposable Studio place;
- inspect scene/script state before editing;
- validate server/client boundaries and RemoteEvent inputs;
- test with actual simulated player input;
- verify scene and gameplay outcomes separately.

For Godot/Unity/Unreal/Blender:
- pin engine and tool versions;
- keep adapters isolated;
- verify import/build/run separately;
- test real interactions and save/load;
- capture reproducible failure artifacts.

A successful code-generation call, file write, or clean compile is not a completed game.

## 6. VTuber: natural conversation is a real-time systems problem

Primary references:
- LiveKit turn detection: https://docs.livekit.io/agents/logic/turns/
- LiveKit adaptive interruption: https://docs.livekit.io/agents/logic/turns/adaptive-interruption-handling/
- LiveKit tuning: https://docs.livekit.io/agents/logic/turns/tuning/
- VTube Studio API: https://github.com/DenchiSoft/VTubeStudio
- OBS WebSocket: https://github.com/obsproject/obs-websocket

LiveKit's documentation distinguishes end-of-turn detection from interruption detection and describes adaptive handling that can distinguish true barge-ins from short backchannels. It also documents false-interruption recovery and turn-boundary cooldowns. These are architectural references, not a requirement to adopt LiveKit or its cloud services.

STAR should keep:
- one existing turn/session authority;
- one monotonic playback clock;
- one audio output owner;
- one avatar parameter writer;
- bounded priority/expiry for stream events;
- explicit generated/queued/started/played/interrupted/discarded states;
- actual played audio—not generated text—as the source of conversation-history truth.

### Stream behavior targets

- Recognize whether speech is addressed to STAR or between viewers.
- Distinguish questions, corrections, backchannels, jokes, urgent callouts, and side conversations.
- Use a short acknowledgment when appropriate without seizing the floor.
- Stop unplayed audio on a true interruption, but never rewrite audio already heard.
- Resume the original question after an interruption when appropriate.
- React to important game events and remain silent during low-value moments.
- Keep captions and Live2D mouth motion synchronized to actual playback timing.
- Use contextual callbacks only when the relevant memory is approved and still in scope.
- Identify STAR clearly as an AI VTuber; do not fabricate human experiences or private feelings.

VTube Studio's local WebSocket API requires plugin access and user authorization. OBS WebSocket should use authentication and remain local-only unless a separately reviewed remote-control design is approved. Never put tokens/passwords in logs, prompts, or repository files.

## 7. Local inference: optimize the real bottleneck

Primary references:
- llama.cpp speculative decoding: https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md
- llama.cpp server documentation: https://github.com/ggml-org/llama.cpp/tree/master/tools/server
- reported prompt-cache contamination issue: https://github.com/ggml-org/llama.cpp/issues/27148
- reported cache restore capacity issue: https://github.com/ggml-org/llama.cpp/issues/30961
- NVIDIA PAIR docs: https://docs.nvidia.com/local-ai/nvpair

### Measurement protocol

Benchmark a fixed, versioned prompt/task set and report:
- prefill tokens/sec;
- decode tokens/sec;
- time-to-first-token;
- first-audio and client-heard latency separately;
- p50/p95/p99 with sample counts;
- GPU/CPU/RAM peak and steady-state usage;
- KV-cache hit/reuse and memory pressure;
- speculative draft acceptance and verified active state;
- task success and useful completed work per minute;
- game frame pacing, audio underruns, avatar drops, and OBS encoding lag under simultaneous load.

Use one-variable-at-a-time paired A/B tests. Keep the model, prompt, context, quantization, thread count, server commit, GPU layers, and concurrency fixed except for the tested variable. Report warm and cold runs separately.

### Cache isolation is a correctness boundary

Upstream llama.cpp issue reports describe prompt/KV-cache failures under concurrent slots, including a report of stale content being restored into an unrelated request. These are issue reports, not proof that every release is affected. They are enough to justify a pinned-build canary:

- two synthetic conversations with unique canary strings;
- alternate and interrupt requests across slots;
- restart/restore cached slots;
- assert no canary from conversation A appears in conversation B;
- repeat with different adapters/personas if used;
- fail closed by disabling the affected cache path if isolation cannot be demonstrated.

Never trade conversation isolation for a prompt-cache hit.

### Hardware-aware strategy

On the documented 8 GB VRAM-class target:
- preserve the current one-resident-model default;
- keep the stable prompt prefix and volatile context ordering;
- protect headroom for game rendering, OBS, voice, and avatar;
- prefer small context-local/speculative canaries before loading a second model;
- route independent background tasks to a trusted second node only if it lowers total completion time;
- do not claim that multi-node request routing pools VRAM or accelerates one in-flight generation.

NVIDIA PAIR is a candidate for independent requests, not model sharding or single-request acceleration.

## 8. Learning and self-improvement

Use the existing paired evaluation/promotion gate and governed lesson store.

For every proposed skill or lesson:
- preserve the task and evidence provenance;
- separate training, calibration, and protected holdout tasks;
- measure both target-skill gain and regression on prior skills;
- test transfer to a new game/project/domain;
- measure negative transfer and forgetting;
- keep model-weight updates separate from lesson/skill updates;
- never allow the agent to edit its own grader, protected holdout, or promotion gate.

A self-generated episode is a candidate example, not a verified lesson. It must pass an independent environment/state check and held-out evaluation before retention.

## 9. Ordered implementation plan

### P0 — reliability and proof
1. Complete exact-head CI for PR #1212 after Run 68 changes.
2. Keep the bounded evaluator regression test.
3. Add cache-isolation canaries against the exact pinned llama.cpp build before enabling cross-slot prompt/KV reuse.
4. Keep current voice/game action gates and fail-safe fallbacks.

### P1 — capability integration
5. Connect the Run 67 turn-policy evaluator to an offline replay harness using consented, speaker-disjoint data.
6. Add event TTL and delivery-state checks to the existing stream director; do not add a second scheduler.
7. Connect captions/avatar motion to the existing playback clock and measure actual device/OBS output.
8. Add game-adapter conformance tests and matched mechanic-probe tasks.
9. Add game-completion contracts and real-input playthroughs to Creator Brain.

### P2 — intelligence and speed
10. Add protected GAIA/BrowseComp-style research tasks and FACTS/LongFact-style claim verification.
11. Evaluate a reflex-policy candidate on one owner-approved disposable game.
12. Evaluate skill transfer/forgetting on held-out games and old tasks.
13. Run paired inference A/Bs and mixed-load tests on the actual target PC.
14. Consider independent background inference on a second trusted machine only after a measured routing win.

## 10. Release criteria

Do not mark a capability shipped until all applicable evidence exists:

- exact-head automated tests and static checks pass;
- the target Windows package starts and shuts down cleanly;
- permissions and cancellation behave as designed;
- no cross-session prompt/context leakage is observed in concurrency canaries;
- voice/audio/avatar/OBS remain stable under simultaneous load;
- game tasks are completed with state-based evidence, not an LLM self-report;
- research claims have primary-source citations and dates;
- regressions on protected prior tasks remain within the existing promotion gate.

## Sources and limitations

This document links to public papers, official project pages, and upstream documentation. It does not download benchmark datasets, install third-party agents, change model weights, enable cloud routing, or grant new machine/game/broadcast permissions.

Research results from external papers are not STAR measurements. Open-source project claims must be independently reproduced on STAR's pinned environment before they become performance or capability claims.

**Run 68 code change:** bounded iterable handling in `star/gameplay_commentary_eval.py`, with a regression test proving the generator tail is not consumed after the limit is exceeded.
