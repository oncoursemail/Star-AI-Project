# STAR Run 42 — Multiparty Social Intelligence, Compositional Learning, and Memory-Aware Local Model Serving

**Research date:** 2026-11-15  
**Scope:** multiparty VTuber interaction, continual learning, agentic retrieval, game/creator skills, local inference, and repository integration.

## Executive decision

Run 42 deliberately does not add another scheduler, room director, memory database, generic model router, or game-control path. STAR already has draft foundations for those responsibilities. The most important new gap is a **dedicated, independently labeled multiparty replay evaluator** that can tell whether STAR understood who was speaking to whom, answered only when appropriate, preserved silence, stopped when a human resolved a request, and produced a correct/appropriate response.

A content-free, signed replay evaluator is added in the companion implementation PR. The other research is mapped onto existing components so that STAR's intelligence improves through better composition and evaluation rather than infrastructure duplication.

## 1. Repository audit and architecture boundaries

The current draft work already supplies relevant foundations:

| Existing work | Existing responsibility | Run 42 decision |
|---|---|---|
| #1178 voice runtime | `RoomTurnDirector`, `RoomStreamHost`, persona and host-only ingress | Extend evaluation; do not add a second room director |
| #1185 conversation index | Bounded, session-local reply/topic context metadata | Reuse after trusted provider/ASR metadata is available |
| #1144 turn-taking evaluator | Causal dyadic pause/endpointing replay | Keep dyadic pause scoring separate from multiparty social scoring |
| #1165/#1166 stream quality and paired variant evaluation | Spoken-task, voice-quality, groundedness, held-out skill and mixed-runtime A/B gates | Reuse for broad paired quality/non-inferiority |
| #1167 inference benchmark | Streaming first-content/token timing | Reuse; add router-specific observations to the manifest |
| #1131 llama.cpp metrics | Read-only inference telemetry | Keep one telemetry parser and exact server revision |
| #1140/#1142 resource admission | Authoritative CPU/RAM/VRAM workload admission | The model router must never become a second resource governor |
| #1121 skill retrieval | Cached BM25 skill retrieval and offline evaluation | Reuse as the skill lookup path |
| #1109/#1117 memory work | Continual-learning evaluation and governed memory consolidation | Reuse; do not add a second persistent memory authority |
| #1182 game control | Fresh-observation/consent/action gate | Preserve the gate; learning/evaluation never grants input permission |
| #1184 active perception | Bounded evidence selection | Keep perception selection separate from capture and compute admission |

The new evaluator imports the existing `RoomAction` enum and accepts only bounded metadata plus independently scored outcomes. It does not call the room director, capture audio, identify speakers, transcribe content, call a model, authorize speech, or control playback.

### Integration-train warning

The repository has many open, stacked draft PRs. A child branch may depend on an unmerged parent. Do not merge a leaf PR directly into `main`, and do not treat a green check on an ancestor commit as validation of a later head. Reconcile duplicate audio/playback implementations and follow the actual PR base chain. Production `main` stays unchanged until the full dependency train, exact-head CI, and Windows acceptance are green.

## 2. New research findings

### 2.1 MP-Bench — multiparty turn-taking and response appropriateness

Paper: https://arxiv.org/abs/2609.13076  
Benchmark catalogue: https://www.fullduplex.ai/benchmarks/mp-bench

MP-Bench evaluates voice agents as active participants in group conversations. It separates turn-taking awareness and response appropriateness, with comprehension questions as a complementary measure. The paper reports that the 12 evaluated voice agents remained near chance on multiparty turn-taking, and real-time agents scored at or below 22% on multiparty comprehension. These are benchmark-specific findings, not STAR scores.

**STAR application:** do not use dyadic endpointing or a generic response-rate metric as a proxy for group-conversation intelligence. Evaluate explicit addressee recognition, appropriate response selection, comprehension, and restraint independently.

### 2.2 Duplex-MPE — explicit vs implicit addressing, silence, and human resolution

Paper: https://arxiv.org/abs/2609.31948  
Benchmark catalogue: https://www.fullduplex.ai/benchmarks/duplex-mpe

Duplex-MPE describes 2,000 scenarios with three or four human speakers and one assistant. Each request is paired across explicit and implicit addressing; the model receives continuous audio without supplied transcripts or turn boundaries. Its four scores cover response initiation, answer accuracy, silence preservation, and stopping when a human resolves a request. The paper abstract and current benchmark catalogue report different counts of evaluated systems, so STAR should pin the paper/data revision rather than copy a moving catalogue count.

**STAR application:** create matched replay pairs where the semantic request is the same but the addressee changes. The correct behavior can change from answer to silence. Include cases where another participant answers while STAR is speaking; STAR should stop only when the resolution is linked to the active request.

### 2.3 AGENTCL — test real learning, not just memory retrieval

Paper: https://arxiv.org/abs/2606.02461

AGENTCL constructs compositional task streams where earlier solutions are intentionally reusable in later tasks, and contrasts them with naive streams that do not guarantee reuse. It finds that naive and held-out settings can hide differences between memory designs and can expose memory-induced degradation.

**STAR application:** build curricula from explicit prerequisite/dependency graphs. Example: learn a reusable Roblox replication test, then use it inside a larger inventory/party system task. Compare the later task with and without the earlier verified skill. Include unrelated tasks and adversarially similar tasks to measure negative transfer. Do not claim continual learning merely because a fact can be retrieved.

### 2.4 AgenticRAG-R1 — fine-grained reasoning, retrieval, and memory actions

Paper: https://aclanthology.org/2026.findings-emnlp.641/

The EMNLP 2026 Findings paper describes stack memory, fine-grained actions across reasoning/retrieval/memory, hierarchical action-aware rewards, and information-aware trajectory rejection for long-horizon agentic RAG.

**STAR application:** represent research as auditable steps: identify a question, retrieve evidence, test source quality, revise a claim when contradicted, and stop when the acceptance condition is met. Store source-linked conclusions and reusable procedures, not private hidden chain-of-thought. Use the existing task ledger and governed memory consolidation.

### 2.5 AgentIF — dense instruction constraints

Benchmark: https://agentif.github.io/

AgentIF covers 50 real-world agentic applications with long instructions and multiple simultaneous constraints. Its October 2026 evaluation update distinguishes reasoning and non-reasoning settings and uses a versioned judge/configuration.

**STAR application:** add constraint coverage to Creator Brain and general-task acceptance. A successful build must satisfy the original requirements, non-goals, file/permission restrictions, output format, and verification steps—not merely produce plausible code. Pin the benchmark setting and judge; do not compare scores across changed configurations.

### 2.6 AITuber OnAir — modular streamer integration reference

Repository: https://github.com/shinshin86/aituber-onair

AITuber OnAir is a modular TypeScript toolkit reference for chat, speech, viewer reactions, memory, and PNG/VRM/Live2D avatars.

**STAR application:** reuse the architectural idea of provider-neutral adapters and independently replaceable avatar/voice/chat providers. Do not import a second voice stack or stage scheduler: STAR already has a Python/React runtime, a room director, and a playback authority. Any code reuse requires a separate license, dependency, security, and architecture review.

### 2.7 llama.cpp router mode — memory-aware model fleet management

Official server documentation: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md

The current router documentation describes `--models-max` and `--models-memory-margin`. With a positive memory margin, the router estimates model memory and unloads idle least-recently-used models until a new model is expected to fit while preserving the configured per-device margin. A model serving a request is not unloaded. The documentation also states that host RAM is assumed unlimited and multimodal projector memory is not included in its model estimates.

**STAR application:** this is a candidate for reducing manual model swapping, not a replacement for STAR's resource admission controller. Keep the interactive model preloaded, reserve memory for game/OBS/audio, and measure cold-load/eviction delay. Do not enable auto-load during a live stream until the full router, GPU-lease, worker-epoch, and mixed-load path has passed Windows tests. Pin the exact llama.cpp commit and record the effective model/context/memory state.

## 3. New implementation — content-free multiparty replay evaluation

Companion PR: `feat/multiparty-room-replay-eval-run42` (draft; stacked on #1178).

New files:
- `star/voice/multiparty_eval.py`
- `tests/test_voice_multiparty_eval.py`

### Input contract

The evaluator accepts:
- Opaque case IDs and scenario SHA-256 digests.
- A split label (`development` or `holdout`).
- A coarse cue category and participant-count bucket.
- Independently prepared expected-response/stop/interrupt labels.
- The actual `RoomAction`.
- Whether an audible response started, its latency, and independently scored correctness/appropriateness.
- An opaque evidence digest and timestamp.
- A host-key HMAC receipt for each outcome.

It rejects duplicate/missing cases, invalid signatures, stale/future evidence, invalid action/label combinations, unbounded values, and roster changes.

It never accepts or stores transcripts, audio, raw speaker names, provider user IDs, chat text, or cross-platform identity links.

### Metrics

- Expected-response audible delivery rate.
- Unwanted response-decision rate.
- Silence preservation for side conversations/backchannels/ambiguous cues.
- Stop-on-human-resolution rate and false-stop rate.
- Urgent-interrupt recall and false-interrupt rate.
- Independently scored answer accuracy.
- Response appropriateness.
- First-audible-response p50/p95.
- Category and participant-count coverage.

### Gate behavior

Only the sealed holdout contributes to acceptance. Development results are reported separately. The result is `INCONCLUSIVE` when the holdout roster, required cue categories, independently scored responses, or latency sample count is insufficient. It is `FAIL` when configured quality thresholds are missed, otherwise `PASS`.

A pass means only that this replay policy passed the supplied thresholds. It does not prove natural human-level conversation, production readiness, or live-platform behavior. It does not promote a policy or change runtime behavior.

## 4. Gamer Brain — compositional, causal, transferable learning

Use the existing GameWorld, GameDevBench, game-control gate, skill retrieval, task ledger, and paired evaluator. Do not create another game controller.

### Curriculum structure

Represent learning as a directed graph:
- Primitive capability: observe an objective, identify a resource, navigate to it.
- Reusable skill: collect a resource with preconditions, action plan, failure modes, and a state verifier.
- Composite task: gather materials, craft an item, and use it to complete an objective.
- Transfer task: same abstract objective in a new map/game with different controls.
- Holdout: unseen seeds/maps/mechanics, never used to tune the skill.

### Causal learning protocol

For a suspected mechanic, use matched starting states and one controlled action difference. Compare state-verifiable outcomes, repeat across seeds, record uncertainty, and avoid changing multiple variables at once. Promote a skill only if the effect repeats on held-out maps and does not regress previously verified tasks.

Keep paused, slowed, and live real-time results separate. A strategy that succeeds when the game is paused is not evidence of real-time mastery.

## 5. Creator Brain — constraint-complete project execution

Use the existing project inspection, task ledger, Studio MCP/StudioTestService research, and visual feedback loop.

Every Creator task manifest should include:
- Goal and non-goals.
- Affected files/systems.
- Dependencies and parallelizable work.
- Performance and compatibility constraints.
- Static checks.
- Runtime/playtest checks.
- Visual acceptance checks.
- Independent final-state verifier.
- Required owner approvals for external publication or irreversible changes.

The final review should compare the resulting project state against the original manifest and list every unsatisfied or unverified requirement.

## 6. General knowledge — evidence-aware retrieval and revision

Apply the new research without creating another memory database:
- Use the existing cached skill retriever for procedures.
- Use source-backed retrieval for factual claims.
- Preserve claim scope, date, provenance, and contradictory evidence.
- Distinguish a factual claim from a procedural skill and from a session event.
- Revise or retire stale claims rather than silently overwriting them.
- Keep a compact evidence summary and next action in the task ledger; do not persist private hidden reasoning.
- For volatile facts (APIs, software versions, game patches, platform rules), revalidate before acting.

## 7. Local inference — model routing and measured speed

### Candidate configuration matrix

On the actual Windows/Vulkan target, compare:
1. Single-model baseline.
2. Router mode with one preloaded interactive model.
3. Router mode with a second deep/background model and a conservative memory margin.
4. Cold and warm model loads.
5. `--models-autoload` enabled vs disabled in a private rehearsal only.
6. One and two parallel slots before trying more.

Record TTFT, first audible output, inter-token latency, p50/p95/p99, queue wait, model-load latency, prompt/decode throughput, VRAM/RAM, game frame-time, OBS lag, and audio underruns.

### Safety and correctness

- The router never bypasses #1140/#1142 resource admission or GPU leases.
- Preserve worker-epoch fencing so output from an unloaded/restarted model cannot reach voice or game control.
- Do not unload an active/serving model.
- Treat missing model-memory estimates and multimodal projector memory as uncertainty; reserve extra margin.
- Do not autoload a large model in response to a live viewer cue.
- A speed improvement is accepted only if task quality, response grounding, game frame-time, OBS output, and audible latency do not regress beyond predeclared limits.

## 8. Human-like streaming — measurable social competence

A believable AI streamer should:
- Track the shared conversation without responding to every utterance.
- Recognize explicit vs implicit addressee cues.
- Let viewers speak to each other.
- Preserve natural silence.
- Stop when another participant has already resolved the active question.
- Handle corrections and genuine barge-in without cutting off ordinary pauses.
- Avoid repetitive filler and forced narration.
- Keep a stable, transparent AI character identity without fabricated human biography.
- Ground laughs, expressions, gaze and gestures in the actual audio/playback and observed game events.
- Keep one playback clock and one avatar parameter writer.

Measure social behavior separately from voice quality: turn-taking, answer correctness, response appropriateness, silence preservation, stop correctness, interruption quality, latency, avatar sync, and long-conversation grounding.

## 9. Run 43 implementation order

1. Finish exact-head CI for #1178, #1180, #1182, #1184, #1185 and this evaluator.
2. Run the multiparty evaluator on a small synthetic fixture, then a privately labeled holdout.
3. Add Duplex-MPE-style explicit/implicit matched cases to private rehearsal.
4. Add AGENTCL-style compositional skill curricula and negative-transfer checks to existing memory/skill evaluation.
5. Run AgentIF-style constraint-complete Creator manifests.
6. Pin a llama.cpp revision and benchmark router mode with model-memory margin on Windows/Vulkan.
7. Verify active-model non-eviction, worker-epoch invalidation, and prewarm behavior.
8. Run a private multi-party voice + game + OBS + avatar rehearsal.
9. Only after acceptance, consider enabling any optional runtime integration.

## Limitations

- Published paper/benchmark results are not STAR results.
- No model was downloaded, trained, or fine-tuned.
- No new external package or benchmark dataset was installed.
- No router configuration, model default, account credential, platform permission, or public stream was enabled.
- The evaluator is offline and policy-independent; it does not prove real microphone diarization, ASR addressee accuracy, TTS naturalness, or live audience comprehension.
- The llama.cpp memory-margin feature is documented but not measured on STAR's hardware.
- The work remains draft until exact-head CI, dependency reconciliation, and Windows acceptance pass.
