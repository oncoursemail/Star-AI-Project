# STAR Run 44 — Active Memory-to-Action Grounding, Capability Retrieval, and Verified Autonomy

**Research date:** 2026-11-15  
**Implementation:** `star/memory_action_eval.py`  
**Status:** content-free paired evaluator; no tool execution, model training, memory writes, or automatic policy promotion.

## Executive findings

The next intelligence bottleneck is not simply remembering more. It is using the right remembered information to make a correct decision when the current request is underspecified.

STAR already has separate foundations for:
- skill retrieval and need-aware loading (#1121);
- continual-learning transfer and retention (#1109);
- governed memory consolidation (#1117);
- task/communication persistence (#1177);
- state-consistent execution traces (research in #1109);
- room-level turn-taking and multiparty context (#1178, #1185, #1186);
- resource admission and streaming pressure (#1140/#1142);
- screen-to-action authorization (#1182);
- verified game and creator evaluation (existing Game Lab and Studio work).

Run 44 deliberately does not add another memory store, skill registry, scheduler, room director, game controller, or promotion authority.

It adds one missing measurement: **does memory improve actual tool selection and parameter grounding, without causing irrelevant memory to leak into unrelated actions?**

## 1. Mem2ActBench — active memory use, not passive recall

Primary sources:
- ACL 2026 paper: https://aclanthology.org/2026.acl-long.370/
- Official code/data: https://github.com/Cantaloupe-M/Mem2ActBench
- arXiv: https://arxiv.org/abs/2601.19935

Mem2ActBench studies persistent assistants where a user mentions preferences and task state in earlier, interrupted sessions, then later makes a short request that expects those facts to be applied implicitly.

The paper reports 2,029 synthesized sessions, averaging 12 user–assistant–tool turns, and 400 memory-dependent tool-use tasks. Human evaluation found 91.3% of those tasks strongly memory-dependent. The key failure is not only choosing the wrong tool; it is grounding the wrong arguments from historical context.

### STAR-specific examples

- Earlier: the user establishes a preferred project workspace and test place. Later: "Run the usual checks" should select the correct workspace and test target.
- Earlier: a project records its target engine and version. Later: "Add the new interaction" should use the correct API family rather than inventing a version.
- Earlier: a stream rehearsal establishes a quiet/mention-only mode. Later: a viewer message arrives; STAR should apply the active room policy without treating the viewer message as permission to change it.
- Earlier: a game session learns a verified mechanic. Later: a similar game task should retrieve the skill only if the current mechanic and environment match.

Memory is not authority. A stored preference cannot grant file, account, game-control, broadcast, spending, or publishing permission. Those remain in the trusted permission systems.

## 2. New implementation: Memory Action Grounding evaluator

New module: `star/memory_action_eval.py`  
Tests: `tests/test_memory_action_eval.py`

The evaluator consumes two paired arms over the same preregistered task cases:
- `memory_off`: no persistent-memory evidence is injected.
- `memory_on`: the existing memory policy may retrieve a bounded set of evidence IDs.

The model, runner, grader, prompt template, tool policy, context budget, output budget, and task roster are pinned. Only the memory policy digest differs.

### What is measured

- Exact action success: expected tool plus exact normalized argument digest.
- Tool-selection accuracy.
- Argument-grounding accuracy.
- Required-memory retrieval recall.
- Required-memory precision among retrieved evidence.
- Irrelevant-memory injection on independent tasks.
- Memory-on versus memory-off accuracy.
- Dependent-task gain and independent-task interference.
- Retrieval latency and paired elapsed-time overhead.
- Session-level direction using sessions—not individual correlated cases—as the sign-test unit.

Every session includes both memory-dependent and memory-independent cases. First-arm order is balanced across sessions.

### Trust and privacy boundary

The evaluator:
- stores no prompts, transcripts, memory values, raw arguments, viewer IDs, or account identifiers;
- accepts only host-HMAC-signed receipts;
- binds receipts to the exact manifest, case, session, arm, run, evidence digest, and timestamp;
- rejects replayed evidence, duplicate case/arm receipts, stale/future timestamps, unapproved memory IDs, memory-off activity, and budget overruns;
- treats infrastructure errors as campaign contamination, not model failure;
- keeps the holdout answer manifest outside model/tool context.

The host must independently grade the proposed tool and normalized arguments before signing. The evaluator does not execute tools and cannot prove that a dishonest host reported truthfully.

A positive holdout verdict is only `manual_review_recommended`. It does not write memory, alter retrieval policy, or promote a model.

## 3. How this complements continual learning

The open #1109 draft evaluator asks whether memory causes transfer, retention, or interference across task streams. Run 44 is a standalone companion: it asks whether the memory that is actually retrieved is applied to the parameters of a concrete tool action, without importing or depending on #1109's branch.

Keep both:
- #1109 answers: "Did experience improve later capability?"
- Run 44 answers: "Did retrieved historical evidence ground the action correctly?"

A complete evaluation should use the same pinned backbone/runner and independently graded task families, then correlate:
1. memory retrieval recall;
2. memory incorporation into the active context;
3. correct tool selection;
4. correct parameter grounding;
5. successful tool outcome;
6. later retention and transfer.

Do not treat a high retrieval score as proof of correct memory use.

## 4. Skill Retrieval Augmentation — retrieve capabilities, not entire libraries

Primary sources:
- Findings of EMNLP 2026: https://aclanthology.org/2026.findings-emnlp.1955/
- Official SR-Agents toolkit: https://github.com/oneal2000/SR-Agents
- Research portal: https://sr-agents.github.io/

SRA-Bench contains 5,400 capability-intensive instances, 636 gold skills, and a 26,262-skill corpus. It separates three stages: retrieval, incorporation, and application. Its reported findings warn that agents can retrieve a gold skill yet fail to load or use it appropriately; distractors and need-aware loading matter.

STAR already has a cached BM25/need-aware skill path in #1121. The next step is not a second retriever. Add an evaluation matrix to that path:
- retrieval recall@k and nDCG@k;
- skill-load precision (was the skill actually needed?);
- context tokens added;
- time to retrieve and incorporate;
- end-task success with/without the skill;
- distractor sensitivity;
- stale skill/version rejection;
- held-out transfer to a new project or game.

Progressive disclosure should be the default experiment: retrieve metadata first, load the smallest relevant skill section, and fetch additional detail only when the task proves it is needed. This reduces irrelevant prompt tokens without sacrificing the option to deepen reasoning.

## 5. General intelligence and verified computer use

Use Mem2Act-style memory-grounded action cases across:
- Roblox Studio project/workspace selection;
- Blender scene and export settings;
- code repository, branch, test target, and runtime selection;
- research source and citation selection;
- local model/provider selection;
- game session and learned mechanic selection.

For cross-application work, use a trajectory and artifact verifier, not a plausible final response. Keep the owner’s real accounts/files out of benchmark runs; use disposable workspaces and synthetic identities.

For Roblox, the official Studio MCP and playtest workflow now support a plan/build/test loop. Roblox's April 15, 2026 announcement describes editable task manifests, parallel work, and a playtesting agent that checks behavior against the original plan:
https://about.roblox.com/newsroom/2026/04/roblox-studio-going-agentic

STAR should:
1. inspect the project and current Studio state;
2. create a reviewable task manifest;
3. edit in a disposable test place;
4. run deterministic tests and playtests;
5. inspect logs and actual state;
6. verify each original requirement;
7. retain only evidence-backed reusable skills.

No publishing, game input, or permission escalation follows from a benchmark result.

## 6. Gamer Brain — learn strategies and transfer them to new games

GameWorld currently provides 34 browser games and 170 tasks across runner, arcade, platformer, puzzle, and simulation genres. It uses serialized game state to verify success and normalized progress rather than relying only on screenshots or an LLM judge:
https://gameworld-project.github.io/

Its published page reports that evaluated agents remain well below the novice-player progress baseline and have low task-success rates. That is a useful warning against equating partial progress with mastery.

STAR should track three independent tracks:
- paused reasoning;
- slowed control;
- real-time control while the environment continues running.

For every learned game skill, record:
- exact game/build and control mapping;
- state/action preconditions;
- strategy and expected effect;
- success/failure evidence;
- recovery path;
- latency budget;
- held-out map/seed transfer;
- expiration or invalidation conditions.

Do not reuse a strategy merely because two games look similar. Confirm mechanic equivalence through controlled probes and outcome verification.

## 7. Faster local inference — measure goodput, not only tokens/second

NVIDIA AIPerf's current metrics distinguish TTFT, time to first output token, inter-token latency, inter-chunk latency, prefill throughput, output throughput, cache reads/writes, speculative acceptance, request latency, and goodput:
https://docs.nvidia.com/aiperf/reference/ai-perf-metrics-reference

For STAR, the useful unit is **verified useful work per second under the real mixed workload**, not peak decode speed in isolation.

Benchmark:
- cold and warm prompt/cache paths;
- retrieval and prompt assembly time;
- prefill, TTFT, ITL/TPOT, first-audio and audible latency;
- task success and argument correctness;
- CPU/RAM/VRAM;
- game frame-time and OBS dropped frames;
- audio underflows and endpointing delay;
- foreground latency while background learning runs.

AIPerf is a measurement reference, not a claim that STAR should replace llama.cpp. Keep the existing llama.cpp server and resource-admission authority; use a compatible load generator or export adapter only after verifying the actual backend and metric semantics.

The existing 8 GB GPU budget means streaming, game rendering, avatar rendering, and audio must have reserved capacity before optional vision/reasoning workers are admitted. Do not run several large models concurrently just to maximize agent count.

## 8. Human-like VTuber behavior — integrate, do not duplicate

The existing voice PRs already separate endpointing, multiparty addressee reasoning, room floor control, playback, and avatar transport. Keep these authorities.

Run 44 recommends a cross-session continuity test that combines:
- a previously established topic;
- a new live message;
- a current room mode;
- another viewer resolving the question;
- a memory-retrieved fact that is relevant but not permission;
- a deadline-sensitive game event.

Expected behavior:
- recognize the addressee and reply chain;
- use relevant memory without exposing it unnecessarily;
- stop if a human has already answered;
- preserve silence when STAR is not addressed;
- prioritize a genuine gameplay hazard over low-priority chat;
- keep mouth/face animation synchronized to actual playback;
- never let viewer text trigger privileged tools or change room permissions.

Naturalness should be scored separately from task accuracy: interruption precision/recall, false cutoffs, response delay, addressee accuracy, silence preservation, voice prosody, avatar sync error, and long-session grounding. Do not collapse these into a single subjective "human" score.

## 9. Run 44 acceptance gates

1. Full tests, Ruff, Pyright and exact-head GitHub Actions pass.
2. A host adapter emits signed receipts from synthetic cases only.
3. At least eight independent holdout sessions span three domains.
4. The memory-on and memory-off arms use identical model, runner, prompt, tool policy, grader, and task roster.
5. The holdout manifest and argument digests never enter model/tool context.
6. Required memory recall, exact argument accuracy, and independent-task interference are reported separately.
7. Retrieval and elapsed-time overhead are measured alongside accuracy.
8. A positive result remains a manual-review recommendation.
9. No production memory policy, model default, desktop permission, game-control permission, or broadcast behavior changes automatically.

## 10. Explicit limitations

This PR adds an evaluator, not a memory database, retriever, tool executor, model trainer, game controller, voice model, or streaming integration. It does not download the Mem2ActBench dataset or import upstream code. No STAR intelligence gain, speedup, gameplay mastery, or human-like streaming acceptance is claimed until actual paired runs are completed on sealed tasks and target hardware.
