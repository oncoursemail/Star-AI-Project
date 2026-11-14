# STAR Run 25 — Coordination, Heartbeat Thinking, Game Transfer, and General Knowledge

**Research date:** 2026-11-14  
**Repository:** `oncoursemail/Star-AI-Project`  
**Branch:** `research/star-run24-integration-blueprint-20261114`  
**Parent blueprint:** `STAR_20261114_RUN24_INTEGRATION_BLUEPRINT_AND_CAPABILITY_GATES.md`  
**Scope:** new research findings and integration decisions for realtime streaming, asynchronous work, game learning, livestream understanding, general knowledge, and inference stability.

---

## Executive decision

The next capability jump should come from making STAR's existing systems coordinate correctly under changing input and mixed load. Do not add another resource scheduler, task ledger, event clock, ASR policy engine, or paired evaluator. The repository already has draft trains for those responsibilities.

This addendum contributes six decisions:

1. **Add a coordinator over the existing task ledger.** A live utterance may create, refine, pause, cancel, or supersede a background task. Model output proposes a typed operation; host code validates task ID, generation, version, state, and permission before applying it.
2. **Use heartbeat-style speculative preparation carefully.** Work that is safe and useful may continue across transcript revisions, but every result must be revalidated against the final utterance and current task generation before execution or speech.
3. **Evaluate streaming as an interaction, not an ASR/TTS demo.** Timing, task accuracy, acoustic delivery, conversational grounding, avatar synchronization, and stream stability must be reported separately.
4. **Measure game learning as a curve plus transfer.** A higher score on the practiced map is not evidence of a reusable skill; test held-out variants and both inference-paused and real-time clocks.
5. **Build general knowledge around claims and provenance.** Search quality, factuality, expert knowledge, and real-world tool completion are different capabilities and need separate evaluations.
6. **Protect cache and realtime budgets against bursts.** Cache hit rate, active working set, tail latency, and recovery behavior matter; a cache optimization can become a persistent throughput failure under overload.

No model weights, packages, credentials, datasets, provider integrations, production defaults, or permissions are installed or changed by this document.

---

## 1. Coordination is a first-class runtime responsibility

### 1.1 Jarvis: typed coordination between the fast and slow brains

The October 16, 2026 Jarvis paper argues that a realtime front model and an asynchronous slow agent have incomplete views of the same user intent. The front model knows the conversation but may not know the state of background work; a worker knows its task but may not know that the user just changed or cancelled it.

Jarvis introduces a coordinator that reads both the current utterance and versioned task state. A model selects among operations prepared by the runtime; code validates and applies the operation. Plans are checked before execution, results are checked before speaking, and delivery is complete only after the user has heard the response.

Reported results are specific to the authors' harness and tasks: the paper reports 192/278 task successes versus 29/278 for its QAA comparison, and 69% Pass@1 on Full-Duplex-Bench v3 for Jarvis-Audio. These are not predictions of STAR performance.

**STAR decision**

Use the existing task ledger and add a thin coordinator contract around it:

- `CREATE(task_spec)`
- `REFINE(task_id, expected_generation, expected_version, patch)`
- `PAUSE(task_id, expected_generation, expected_version)`
- `RESUME(task_id, expected_generation, expected_version)`
- `CANCEL(task_id, expected_generation, expected_version)`
- `DELIVER(task_id, expected_generation, expected_version, evidence_refs)`

The runtime must prepare the allowed operation set. A model must never invent a task ID, generation, file path, permission, or tool target and have the host trust it.

Before an operation is applied, compare-and-swap against the current ledger state. A stale generation is a no-op with an explicit stale-operation result. Before a worker executes a plan, revalidate its task generation and capability scope. Before a result is spoken, revalidate that it still answers the current task version and that its evidence has not expired. Mark communication delivered only after the playback acknowledgement contract reports the required audio was actually played.

This is a coordinator over the existing #1177 ledger, not a second ledger.

### 1.2 Heartbeat Thinking: preserve useful work across partial speech updates

The October 19, 2026 Heartbeat Thinking paper addresses a common latency problem. A speculative thinker may begin while the user is speaking, but conventional systems often interrupt that work whenever a new partial transcript arrives. This can repeatedly truncate tool-call arguments before they are complete.

Heartbeat Thinking instead starts additional thinker invocations using the latest partial transcript and a shared record of completed reasoning and tool results, while allowing existing invocations and dispatched tools to finish. At speech end, a responder receives the final request and completed preparation, reuses only applicable results, and performs remaining work.

The authors report a 16-percentage-point increase in speculative tool coverage and a 36.4% reduction in mean final-response latency on their FDBench v3 setup. The paper also reports that 4.0% of recordings produced answers using erroneous or outdated results despite correct tool-call arguments. Its authors note benchmark-dependent task-quality effects and limitations around fixed scheduling intervals and late results.

**STAR decision**

Implement this only as a bounded, cancellable preparation lane:

1. A stable partial transcript can trigger a read-only thinker.
2. A newer transcript revision starts a new thinker but does not automatically kill already-dispatched safe work.
3. Completed retrieval results and reasoning notes enter a bounded, task-generation-scoped preparation record.
4. Only read-only or explicitly idempotent operations may run speculatively. Purchases, messages, account changes, file writes, game actions with external consequences, and other side effects wait for final intent and normal permission checks.
5. At final transcript, freeze the request revision, cancel unfinished speculative work, and pass completed preparation to the responder.
6. The responder checks every result against the final request, current task generation, evidence timestamp, and source trust before use.
7. A late result cannot silently revise a response already being played; it becomes a new task update or is discarded.

Do not interpret a partial transcript as consent, final intent, or permission. The existing #1160 stable-prefix policy remains the gate for speculative reasoning; the task ledger remains the authority for long-running work.

---

## 2. Streaming evaluation: measure what the audience experiences

### 2.1 InteractionBench adds missing quality dimensions

InteractionBench (arXiv:2611.02430, submitted November 2, 2026) evaluates four dimensions on the same recorded input:

- conversational timing and floor control;
- spoken-task accuracy;
- acoustic behavior such as whispering and volume adaptation;
- groundedness across conversations longer than twenty turns.

The paper describes 221 items per system across thirteen scenarios and 1,519 graded runs. It fixes expected floor-control actions before evaluation and scores whispering from the audio signal rather than relying only on an LLM judge. The authors report a rank correlation of 0.83 between timing and spoken-task accuracy among the six full-duplex systems they tested. Hosted-system groundedness results were materially higher than those of the evaluated open full-duplex models, but the paper also documents timing-protocol and network-delay caveats.

**STAR decision**

Keep the current paired evaluator as the authority and add an InteractionBench-inspired private rehearsal matrix. Report these lanes independently:

| Lane | Example measurements | Failure examples |
|---|---|---|
| Timing | user-end to first audible audio; backchannel delay; interruption-to-silence; false interruption rate | speaks over a pause; answers too late |
| Task accuracy | correct answer; correct tool; exact arguments; task completion | hears the request but does the wrong thing |
| Acoustic delivery | volume ratio; speaking-rate stability; clipping; underruns; voice consistency | says “whisper” but speaks normally |
| Grounding | facts retained across 20+ turns; correction handling; source-backed claims | forgets a constraint or invents a prior agreement |
| Avatar sync | audio-to-mouth offset; stale-frame age; expression transition latency | mouth moves before sound or keeps talking after interruption |
| Broadcast health | OBS dropped frames; audio discontinuities; encoder lag | conversation is correct but the stream is visibly broken |

Use identical recorded inputs and a single host monotonic timeline. Preserve the distinction between text generated, audio queued, audio started, audio played, and audio acknowledged. A model's self-rating is not the primary ground truth for its own timing, acoustic behavior, or task completion.

### 2.2 Natural streamer behavior is a floor-control problem, not just a prompt

The Social Director should combine:
- acoustic speech detection;
- transcript stability;
- semantic completion;
- session-local speaker attribution;
- addressee estimation (STAR, another participant, group, unclear);
- response intent;
- current floor owner;
- active task state;
- actual playback state.

The model may suggest a conversational action, but the host decides whether STAR can speak, interrupt, backchannel, or remain quiet. Viewer chat and game observations are untrusted content, never tool authorization.

For naturalness, evaluate:
- proportionate reactions instead of constant narration;
- varied openings without repetitive catchphrases;
- short acknowledgements when appropriate;
- silence while viewers talk to one another;
- recovery after interruptions;
- no repeated answer after another person resolves the question;
- consistent persona over long sessions;
- transparency that STAR is an AI character, without fabricated human biography or experiences.

### 2.3 LiViBench: livestream context requires audio, video, and comments together

LiViBench is an AAAI 2026 benchmark for interactive livestream understanding. Its 24 tasks combine video, audio, speech, and real-time comments; the work also proposes Video-to-Comment Retrieval (VCR) to retrieve relevant comments for a current video segment.

**STAR decision**

Use a timestamped multimodal stream timeline. A visual observation should be aligned with:
- audio segment and transcript revision;
- current game state;
- recent viewer comments;
- relevant earlier stream events;
- the active task or topic.

Retrieve only comments relevant to the current scene or conversation rather than injecting the full chat backlog into every model request. Preserve message timestamps and source boundaries so a joke from ten minutes ago is not mistaken for the current event.

**Dataset/licensing boundary:** the published LiViBench dataset card identifies CC BY-NC 4.0. Do not bundle or redistribute it, and do not use it for a commercial training pipeline without separate rights review. STAR can implement the architecture and build owner-created rehearsal scenarios without copying benchmark media.

---

## 3. Gamer Brain: measure learning, stability, and transfer

### 3.1 OmniGameArena: a useful new transfer protocol

OmniGameArena is a unified Unreal Engine 5.5 benchmark with twelve games and sixty maps: one original map plus four variants per game. Its tasks cover solo, PvP, and cooperative play, including visual perception, navigation, reaction, memory, planning, adversarial interaction, and cooperation.

Its protocol separates:
1. **Cold start:** performance before learning a game-specific skill.
2. **Improvement Dynamics Curve:** repeated play, diagnosis, validation, and skill revision over up to ten rounds.
3. **Transfer:** the best learned skill is tested on pre-fixed variants.

The project reports that 42 of 72 learning curves had a best round more than 0.1 above cold start. The average gain was 0.19 on the practiced game but only 0.03 on its variants; ten of the 42 improving curves ended more than 0.1 below their own best round. The result is important: practice can improve the known map while failing to produce a stable, transferable skill.

OmniGameArena also distinguishes a latency-free mode, where the game pauses while the model thinks, from a latency-charged mode, where inference time consumes game time.

**STAR decision**

Every learned game skill needs:
- a cold-start baseline;
- a per-round learning curve;
- a best-round score;
- a final-round score;
- held-out variant transfer;
- regression/forgetting checks;
- wall-clock and in-game time;
- action latency and game frame-time.

Run both paused and real-time protocols. The paused mode measures decision quality without reaction-time cost; the real-time mode measures the playable system the audience actually sees. Do not combine the two into one score.

A skill should not be promoted because one map score improved. Require transfer to at least one held-out variant and a no-harm test on an unrelated task.

### 3.2 EmbodiedCLBench: compositional generalization

EmbodiedCLBench evaluates whether an agent can learn simple embodied tasks and recombine the resulting skills for complex, unseen tasks. Its authors report that experience on basic tasks improves advanced-task performance, but more samples do not produce proportional gains; current agents can fail to extract meaningful information from additional experience.

**STAR decision**

Build a skill dependency graph:
- primitives (move, jump, aim, inspect, interact);
- reusable mechanics (timed dodge, target tracking, inventory transfer);
- compositions (complete an objective, win a round, navigate a multi-stage level);
- game-specific wrappers (controls, camera, physics, cooldowns).

Test each skill in dependent, independent, and conflicting task streams. Measure positive transfer, negative transfer, correction accuracy, and delayed retention. Keep a skill's evidence, game/version constraints, preconditions, failure modes, and last-verified date attached to it.

### 3.3 Keep benchmark domains separate

- **OpenGameEval** remains the Roblox Studio/scene-and-playtest evaluation route.
- **GameDevBench** remains the Godot multimodal game-creation benchmark.
- **OmniGameArena** is an Unreal Engine 5 game-playing and transfer benchmark.
- **EmbodiedCLBench** is a compositional continual-learning reference.

Do not compare raw scores across these benchmarks as though they measured the same environment or capability. Pin the exact commit, environment build, task manifest, controller, model, and evaluation clock.

### 3.4 The STAR gameplay loop

`Observe → Orient → Choose → Act → Verify → Diagnose → Update Skill`

Use two rates:
- a fast controller for movement, aiming, dodging, camera, and immediate interactions;
- a slower planner for objectives, strategy, resource management, exploration, and skill updates.

The planner should be event-triggered (death, objective change, new mechanic, repeated failure, resource shortage, level transition) rather than invoked for every frame. The controller must expose confidence and failure signals so the planner knows when its current skill is no longer reliable.

---

## 4. General knowledge: build a source-grounded research workbench

General knowledge is not one benchmark or one model setting. Separate at least four capabilities:

| Capability | Evaluation reference | What it measures |
|---|---|---|
| Everyday factuality | SimpleQA | Short, verifiable fact-seeking answers |
| Multi-step real-world assistance | GAIA | Browsing, files, multimodal understanding, tool use |
| Difficult research retrieval | BrowseComp | Persistent search, query reformulation, multi-source synthesis |
| Expert academic knowledge | Humanity's Last Exam (HLE) | Broad, difficult academic questions across many disciplines |

GAIA contains 466 real-world assistant tasks and emphasizes tool use, multimodality, browsing, and reasoning. BrowseComp contains 1,266 difficult browsing questions designed so answers are hard to find but comparatively easy to verify. HLE contains 2,500 expert-level questions across dozens of subjects. SimpleQA focuses on short factual answers with evidence. None of these alone measures all-purpose intelligence, and benchmark contamination or licensing restrictions must be considered before running or training on any dataset.

**STAR decision: claim ledger**

For research answers, store an internal evidence record per material claim:

- normalized claim text;
- source URL and publisher;
- source publication date and retrieval time;
- source type (primary paper, official docs, dataset card, secondary report);
- exact supporting excerpt or local citation span;
- whether the source is current, superseded, or disputed;
- confidence and unresolved contradictions;
- task/session ID and retention class.

Retrieval should be query-adaptive:
1. identify the user's actual question and time sensitivity;
2. search primary sources first;
3. broaden to independent corroboration where needed;
4. compare conflicting dates, versions, and definitions;
5. answer only what the evidence supports;
6. state what remains uncertain;
7. retain only useful, source-linked knowledge under the existing memory governance rules.

Do not confuse a plausible synthesis with verified knowledge. A source's existence is not proof that it supports the adjacent claim.

### 4.1 Programmable retrieval: learn how to search, not only what to retrieve

Meta's October 20, 2026 Retrieval Program Learning (RPL) research treats retrieval as a small program composed from search primitives, local state, and control flow rather than a fixed retrieve-then-answer pipeline. It uses grammar-constrained program mutation and execution verification to explore better search strategies. The authors report improvements on open-domain QA and corpus-level reasoning, including a 4B RPL-trained model outperforming their tested 8B baselines; those are paper-specific results, not expected STAR results.

**STAR decision**

Build a declarative, allowlisted retrieval plan—not arbitrary generated Python:

- `SEARCH(query, source_scope, freshness_window)`
- `FILTER(source_type, date, trust, license)`
- `EXTRACT(claim_schema)`
- `FOLLOW(entity_or_reference)`
- `COMPARE(claim_set)`
- `VERIFY(independent_source_count)`
- `STOP(answerability, budget, diminishing_returns)`

The plan executor should enforce maximum search calls, time, tokens, domains, and document size. Intermediate results remain in a bounded local state store; only selected evidence enters the final model context. Every primitive emits provenance and an execution trace. A search program may be proposed or mutated only in a sandbox, then evaluated against held-out questions with answer accuracy, evidence coverage, retrieval turns, context tokens, latency, and cost. Never promote a search strategy because the same model says it looks good.

This is a strong fit for STAR's general-knowledge workbench: a compact model can learn better retrieval procedures without needing every source or every intermediate document in its context.

### Useful general-knowledge features

- research plans with explicit subquestions and stopping conditions;
- source credibility and freshness scoring;
- contradiction detection and correction history;
- citation coverage for factual claims;
- uncertainty-aware answers and calibrated abstention;
- file, image, audio, and video understanding;
- knowledge maps for science, technology, history, arts, games, and practical subjects;
- tutorial generation followed by exercises and external grading;
- personal knowledge notebooks with user-controlled retention;
- periodic refresh of facts likely to change (APIs, software versions, prices, current events);
- reusable research skills (compare products, audit code, read papers, trace a bug, inspect a game).

---

## 5. Inference speed and cache stability under mixed load

### 5.1 Prefix-cache overload can be persistent

The November 10, 2026 preprint *Bursts That Outlast Themselves* reports a metastable failure mode in prefix-cached agent serving. A short burst can enlarge the active session working set beyond the KV pool, reduce prefix-cache hits, increase recomputation, and leave the server degraded after the burst ends. In the reported experiments, throttling new admissions often failed to recover a collapsed run, while suspending already admitted sessions against a capacity-based KV limit recovered all tested collapsed runs.

This is a preprint and its vLLM/SGLang serving results are not automatically transferable to STAR's local llama.cpp path. It is nevertheless a valuable failure hypothesis for long-lived sessions and multi-agent workloads.

**STAR decision**

The single resource supervisor should eventually account for:
- active model sessions and context lengths;
- resident KV demand where the backend exposes it;
- prefix-cache hit/query ratio where available;
- prefill and decode latency separately;
- queue age and active-worker count;
- CPU RSS, system RAM, GPU VRAM, and disk I/O;
- time to recover after a burst.

A scheduler that only limits CPU/RAM/VRAM at process start may miss a growing per-session KV working set. If a backend does not expose reliable KV telemetry, do not invent it; mark the field unavailable and use conservative measured concurrency limits.

### 5.2 External NVMe KV cache is not a default speed switch

The py-kvcache study shows that GPU/CPU/NVMe KV movement can improve long-context prefill when transfer is overlapped with compute, but recomputation can be faster for short prefixes or a fast GPU. The break-even point depends on workload shape, transfer granularity, staging memory, and schedule timing.

**STAR decision**

Do not add NVMe KV offload simply because STAR has RAM or SSD space. Benchmark:
- cold prefill;
- warm prefix hit;
- short and long context;
- repeated turns;
- concurrent sessions;
- burst arrival and recovery;
- GPU-only versus CPU/NVMe tiers.

Adopt only if it improves end-to-end p95 latency and throughput without worsening answer quality, tail latency, or memory pressure on the actual STAR host.

### 5.3 Speed is a multi-objective measurement

For each candidate inference or scheduling change, report:
- first non-empty content chunk;
- first audible playback;
- inter-token latency and output tokens/second;
- full response completion;
- p50/p95/p99 request latency;
- task success and factual groundedness;
- CPU/RAM/VRAM and cache behavior;
- audio underruns and dropped input frames;
- game frame-time p95/p99;
- OBS dropped frames and output health.

A candidate is not faster if it merely produces a quick first token and then stalls, speaks over the user, drops game frames, or lowers task accuracy.

---

## 6. Integration sequence against existing STAR work

Do not fork competing implementations. Integrate the existing draft dependency trains:

| Existing work | Use it for |
|---|---|
| #1140 + #1142 | The single resource-admission and stream-pressure authority |
| #1159 | Latest-wins Live2D frame transport (avatar samples only) |
| #1160 | Stable-prefix, revision-aware speculative thinking policy |
| #1166 + #1167 | Paired capability comparison and streamed inference measurements |
| #1177 | Durable task/communication ledger, generations, leases, checkpoints, playback obligations |
| #1178 | Natural streamer persona, room floor control, resolved-reply stopping, audio freshness and callback hardening |
| #1180 | Integration blueprint and capability gates |

Recommended sequence:

**Phase A — Integration correctness**
- Confirm dependency order and exact-head CI for every stacked PR.
- Choose one event clock, task ledger, resource supervisor, and paired evaluator.
- Add coordinator operations over the existing task ledger.
- Test task refinement/cancellation races and stale-result suppression.

**Phase B — Streaming quality**
- Add InteractionBench-inspired private rehearsal cases.
- Add bounded heartbeat preparation behind #1160's stable-prefix gate.
- Revalidate every speculative result at finalization and before speech.
- Verify audible playback acknowledgements and VTube Studio epoch synchronization.

**Phase C — Gamer and Creator**
- Run cold-start, improvement-curve, and held-out transfer trials.
- Use both paused and real-time clocks.
- Keep Roblox, Godot, and UE5 results separate.
- Promote skills only after external verification and held-out transfer.

**Phase D — General knowledge**
- Add a claim/evidence ledger and source freshness policy.
- Evaluate factuality, multi-step assistance, difficult browsing, and expert knowledge separately.
- Keep benchmark data, user data, and durable memory in distinct retention classes.

**Phase E — Mixed-load rehearsal**
- Run conversation + viewer chat + avatar + OBS + game control + background research together.
- Protect the foreground deadlines.
- Inject bursts and verify the runtime recovers without manual restart.
- Compare baseline and candidate on the same private scenarios before any default change.

---

## 7. Acceptance gates

| Area | Minimum acceptance evidence |
|---|---|
| Coordination | stale generation cannot execute, overwrite, or be spoken |
| Speculative work | partial transcript never grants side-effect permission; final request revalidates every result |
| Voice timing | first-audible p50/p95 and interruption latency measured from one host timeline |
| Conversation | 20+ turn groundedness, correction handling, and natural silence |
| Acoustic behavior | volume, clipping, underrun, and voice consistency measured from audio |
| Avatar | mouth follows played audio; stale frame epochs are rejected |
| Game learning | cold-start baseline, improvement curve, held-out transfer, and no-harm test |
| Game creation | engine execution plus visual/structured verification, not compilation alone |
| General knowledge | claim-level sources, freshness, contradiction handling, and calibrated uncertainty |
| Inference | paired p50/p95/p99, task quality, resource use, and burst recovery |
| Streaming | no background workload may starve speech, avatar, or game-control deadlines |
| Governance | explicit opt-in, revocable platform permissions, bounded retention, and manual promotion |

---

## 8. Limits and non-claims

- This is a research and integration specification, not a runtime implementation.
- No new model or provider was installed, downloaded, enabled, or made the default.
- No benchmark dataset or livestream recording was downloaded or copied into STAR.
- LiViBench's CC BY-NC 4.0 dataset license is not cleared for commercial reuse.
- OmniGameArena's environment package is Apache-2.0, but its multi-gigabyte UE5 build still requires hardware, disk, and runtime testing before adoption.
- The KV-cache collapse work is a preprint and must be validated against STAR's actual inference backend.
- No local RTX 4060, microphone, OBS, VTube Studio, Roblox Studio, Godot, UE5, or public livestream test was performed.
- No speedup, general-intelligence gain, game mastery, human equivalence, or production readiness is claimed.
- Draft PRs and CI artifacts are not features in the released installer. No auto-merge is authorized.

---

## 9. Source register

### Coordination and streaming
1. Heartbeat Thinking (arXiv, 2026-10-19): https://arxiv.org/abs/2610.26233
2. Jarvis (arXiv, 2026-10-16): https://arxiv.org/abs/2610.23804
3. Jarvis official implementation: https://github.com/AmphionTeam/Jarvis
4. InteractionBench (arXiv, 2026-11-02): https://arxiv.org/abs/2611.02430
5. InteractionBench project: https://avera-labs.github.io/InteractionBench/
6. Full-Duplex-Bench v3: https://arxiv.org/abs/2604.04847

### Livestream understanding
7. LiViBench, AAAI 2026: https://ojs.aaai.org/index.php/AAAI/article/view/39859
8. LiViBench dataset card: https://huggingface.co/datasets/Xiaodong/LiViBench

### Game learning and creation
9. OmniGameArena project: https://mxlin043.github.io/OmniGameArena/
10. OmniGameArena official code: https://github.com/mxlin043/OmniGameArena
11. OmniGameArena environment card: https://huggingface.co/datasets/mxlin043/OmniGameArena
12. EmbodiedCLBench (arXiv, 2026-10-09): https://arxiv.org/abs/2610.13021
13. EmbodiedCLBench official implementation: https://github.com/PKU-VaLuE-Lab/EmbodiedCLBench
14. GameDevBench (ICML 2026): https://github.com/waynchi/gamedevbench
15. Roblox OpenGameEval: https://github.com/Roblox/open-game-eval

### General knowledge and research
16. GAIA, Meta / ICLR: https://ai.meta.com/research/publications/gaia-a-benchmark-for-general-ai-assistants/
17. BrowseComp, OpenAI: https://openai.com/index/browsecomp/
18. SimpleQA, OpenAI: https://openai.com/index/introducing-simpleqa/
19. Humanity's Last Exam, Nature (2026): https://www.nature.com/articles/s41586-025-09962-4

### Inference and serving
20. Bursts That Outlast Themselves (arXiv, 2026-11-10): https://arxiv.org/abs/2611.13412
21. py-kvcache (arXiv, 2026-09-10): https://arxiv.org/abs/2609.11744
22. py-kvcache official implementation: https://github.com/atlarge-research/py-kvcache
23. vLLM metrics documentation: https://docs.vllm.ai/en/v0.32.0/design/metrics/

**Source quality note:** papers and official project/dataset documentation are preferred. Preprints are labeled as such. Reported benchmark numbers are copied only with their benchmark scope and protocol; they are not STAR measurements.
