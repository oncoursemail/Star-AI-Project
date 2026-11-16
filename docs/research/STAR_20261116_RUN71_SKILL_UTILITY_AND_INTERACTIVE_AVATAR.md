# STAR Run 71 — Skill Utility, Continual Learning, Real-Time Avatar Interaction, and Capability Economics

**Research date:** 2026-11-16  
**Scope:** source review, paired skill-utility evaluation, continual-learning design, coding/generalist benchmarks, real-time VTuber interaction, and local inference experiments  
**Runtime status:** the new evaluator is offline-only. It does not load skills, change routing, train weights, access media, control an avatar, or promote a candidate.

## Executive decisions

Run 71 addresses a gap between having a large skill library and proving that those skills improve STAR.

1. Every injected skill must earn its prompt-token, latency, and maintenance cost on matched tasks.
2. Continual learning must measure transfer and forgetting, not just improvement on the examples that created a skill.
3. A natural VTuber is an end-to-end synchronized interaction system: turn-taking, task accuracy, groundedness, prosody, audio playback, avatar motion, and interruption recovery all matter.
4. Faster inference must be benchmarked on the exact model, llama.cpp build, backend, context, and mixed workload. Research results from H100, Ascend, or other accelerators do not establish an RTX 4060 speedup.
5. STAR should keep its existing authorities: one skill registry/router, one learning/promotion gate, one voice/playback authority, one avatar writer, one resource-admission authority, and one permission gate.

## 1. Repository baseline — important product reality

The public main README describes STAR v1.0 as a Windows 11 local-first chat and Roblox-development app. The default local model is a 4B-class GGUF on a Vulkan GPU with about 8 GB VRAM; a user-operated Linux server and hosted providers are opt-in. The README explicitly says the v0.9-to-v1.0 answer-quality change was inconclusive and labels full Studio Lab and the newer voice-streaming system as coming soon.

The root AGENTS.md says:
- star/orchestration.py is a dependency/ownership planner, not yet a live multi-agent scheduler.
- Night school changes governed lessons and worked examples, not model weights.
- The model/self-builder cannot edit graders, holdout fixtures, policy, or promotion code.
- Core policy and authentication changes need an independently controlled review gate.
- The self-builder's write scope is deliberately narrow.

Therefore, the right claim for this run is new offline evaluation infrastructure and research, not that STAR has acquired new model weights, autonomous gameplay, or a production VTuber runtime.

## 2. New implementation: paired skill utility evaluator

Added:
- star/skill_utility_eval.py
- tests/test_skill_utility_eval.py

The evaluator compares skill-off and skill-on trials only when they share:
- skill ID, task/case, replicate, and split;
- model ID and exact model revision;
- harness revision;
- dataset and task revisions;
- hash of the base prompt/context before the optional skill is injected;
- deadline policy.

It reports train, validation, and holdout separately:
- matched-pair coverage and unpaired counts;
- skill-off and skill-on task success;
- candidate wins, regressions, ties, and net wins;
- success-rate delta;
- paired p50/p95/p99 latency delta;
- input/output token overhead;
- deadline success.

Unpaired samples are counted but excluded from the paired comparison. Mismatched provenance is rejected. A task cannot occur in more than one split. Inputs are bounded at 100,000 trials. The evaluator emits no scalar utility score and cannot automatically enable, rewrite, or promote a skill.

### Why this matters

SWE-Skills-Bench (March 16, 2026) evaluates 49 skills across approximately 565 requirement-driven task instances on pinned repositories. Its preprint reports that 39/49 skills produced zero pass-rate improvement, average improvement was +1.2%, only seven specialized skills showed meaningful gains (up to +30%), and three caused regressions (up to -10%). It also reports token overhead as high as +451% without pass-rate improvement. These are preliminary benchmark results, not a universal law, but they make a strong case for paired, task-specific measurement.

STAR decision: keep a skill available without enabling it by default; require a measured task-family benefit, no material holdout regression, and an explicit review before changing defaults. Measure prompt cost and latency alongside quality.

## 3. Continual learning: skill evolution must generalize

### Memento-Skills — March 19, 2026

Paper: https://arxiv.org/abs/2603.18743  
Code: https://github.com/Memento-Teams/Memento-Skills

Memento-Skills treats reusable skills as structured, evolving memory and uses a read/write reflective loop: route to a relevant skill, then refine the skill using experience. It reports benchmark gains on GAIA and Humanity's Last Exam in its own setup. Its important architectural lesson is that an agent can adapt via externalized procedures and prompts without updating the base model weights.

STAR application: use versioned procedural memory with immutable evidence, a skill changelog, explicit provenance, and reversible promotion. The skill itself is not evidence that it works; paired execution on new tasks is.

### AFTER — June 22, 2026

Paper: https://arxiv.org/abs/2606.23127

AFTER evaluates 382 enterprise tasks across six roles and 22 skills, including local improvement, cross-task transfer, cross-role transfer, and cross-model generalization. Its abstract reports 3.7–6.7 point aggregate improvement after one refinement round and 73.1% cross-model test accuracy for skills evolved from diverse multi-model traces. It also warns that narrow experience can overfit and hurt held-out transfer.

STAR application: store the source domain and intended transfer domain for every skill. Evaluate:
- same-task improvement;
- paraphrase and parameter variation;
- cross-project transfer;
- cross-engine transfer where semantics genuinely match;
- cross-model transfer;
- retention of earlier skills after a new skill is added.

### SkillLearnBench — April 22, 2026

Paper: https://arxiv.org/abs/2604.20087

SkillLearnBench contains 20 verified skill-dependent tasks across 15 subdomains and 100 instances. It evaluates skill quality, execution trajectory, and final task outcome. The authors report that no continual-learning method wins across every task/model, and that self-feedback alone can drift while external feedback helps stabilize revisions.

STAR decision: separate the skill author from the evaluator. Use independent tests, teacher/owner feedback where available, and a protected holdout. Never let the skill-generating agent grade its own candidate or rewrite the grader.

## 4. Coding and Creator Brain: evaluate whole-system work

### SWE Atlas v1.1 — November 2026

https://labs.scale.com/leaderboard/swe-atlas

The November 2026 release describes 284 tasks across 15 production repositories and six languages, covering codebase comprehension, test writing, and refactoring in containerized repositories. It is single-turn, so it is useful as one diagnostic but not a complete long-running agent benchmark.

### E2E-SWE — September 29, 2026

https://arxiv.org/abs/2609.38335  
https://github.com/facebookresearch/E2E-SWE

E2E-SWE evaluates 186 whole-repository generation tasks across 11 languages using hidden tests and implementation-independent specifications. The paper reports pass@1 ranging from 11.7% to 67.7% across 13 evaluated models.

STAR application: maintain three complementary coding evaluations:
1. codebase understanding and targeted repair;
2. test creation/refactoring on real repositories;
3. end-to-end project creation from a specification.

For games, keep CEGame-Bench/OpenGameEval-style actual launch, player-input, objective, ending, restart, and save/reload checks. A clean compile is only an intermediate event.

## 5. VTuber interaction: optimize the experience heard and seen by viewers

### InteractionBench — November 2, 2026

https://arxiv.org/abs/2611.02430

InteractionBench measures four dimensions on the same recorded conversations: conversational timing, spoken-task accuracy, whisper/volume control, and groundedness in conversations longer than twenty turns. The reported setup has 221 items per system across 13 scenarios and 1,519 graded runs. It also shows why server-side timing is not enough: client-heard timing includes network delay, and excluding that delay can change a system's ranking.

STAR application: measure timestamps at the viewer/client boundary:
- input speech end / pause onset;
- end-of-turn decision;
- model first token;
- first generated audio;
- playback start;
- first audible response;
- interruption/cancellation;
- last audible sample.

Keep endpointing delay, model latency, TTS generation, audio queue delay, and client-heard latency separate. Evaluate multi-turn task accuracy and groundedness, not only how quickly STAR speaks.

### AVTR-1 — September 19, 2026

https://arxiv.org/abs/2609.22913  
https://github.com/avaturn-live/avtr-1

AVTR-1 describes an open real-time avatar stack with a 153M-parameter streaming motion generator conditioned on both participants' audio. The paper emphasizes continuous scheduling of chunked audio/video, synchronization with an external voice agent, and interruption handling. The project releases components under component-specific licenses.

STAR application: borrow the scheduling principles, not an assumption that STAR should replace her approved Live2D character with a generated talking-head model. Keep:
- one audio playback clock;
- one avatar-parameter writer;
- bounded timestamped motion/expression events;
- cancellation epochs so interrupted speech cannot continue animating;
- interpolation for late or missing animation frames;
- neutral/listening fallback when no valid event is available;
- explicit lip-sync offset and dropped-frame measurements.

A more human-feeling stream also needs social judgment: identify STAR as an AI VTuber, avoid fabricated human biography, acknowledge uncertainty, remember only consented/relevant viewer context, moderate chat, and avoid speaking over people.

## 6. Inference speed: benchmark before changing the engine

### llama.cpp SPEED-Bench and speculative decoding

- https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench
- https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md

SPEED-Bench measures prompt throughput, decode throughput, latency, and draft acceptance against an already-running server. Speculative decoding helps only when draft work is cheap and enough tokens are accepted. A draft model can increase memory use and make generation slower on workloads with low acceptance.

STAR decision: benchmark target-only versus each draft/speculation mode using the exact model, backend, seed, context, output length, and workload. Record acceptance rate and end-to-end client latency, not just server tokens/sec. Keep speculation behind the existing canary and resource-admission work.

### TurboQuant — March 24, 2026

Google Research: https://research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression/

TurboQuant combines PolarQuant and QJL to reduce KV-cache memory. Google's reported results are research results on its tested models/hardware; a third-party summary describes H100 attention-logit speedups. Neither proves a speedup on STAR's Vulkan/RTX 4060 path.

STAR decision: treat it as a research candidate. Before adoption, require a compatible implementation and paired tests for retrieval accuracy, long-context coding, tool-call correctness, cache isolation, prefill/decode latency, memory, and mixed gaming/streaming load. Do not hand-roll a quantized KV cache inside STAR.

### Hardware-specific risk

A llama.cpp issue report describes a Vulkan speculative-decoding checkpoint/replay livelock on a particular build/configuration. This is an issue report, not proof all Vulkan builds are affected. It is enough reason to add a watchdog, bounded generation deadline, and target-backend soak test before enabling a new speculation path.

STAR decision: preserve the known-good baseline, pin llama.cpp builds, keep a rollback path, and canary one optimization at a time. Do not load a second large model while the game and OBS are using VRAM.

## 7. Unified capability architecture

Keep three timescales separate:

- Reflex: audio buffering, VAD, endpointing, game input, avatar frame scheduling. Strict deadlines; no large planning loop.
- Reasoning: model calls, tool selection, research, multi-step game plans, code changes. Can run asynchronously against a versioned context snapshot.
- Learning: replay, skill proposals, evaluation, transfer, retention, and promotion. Offline or low-priority; never blocks live interaction.

For every background result, capture a context revision, task ID, game/session ID, deadline, and cancellation epoch. When it returns, discard it if the conversation, game, or interruption state has changed. Only the existing turn/playback authority may speak.

For multi-computer operation, route independent background jobs to trusted nodes; do not assume separate machines pool VRAM or accelerate one in-flight token stream. Keep live voice and fast game control on the measured warm local route.

## 8. Run 72 implementation sequence

1. Connect the paired skill evaluator to existing docs/evals.md evidence export without modifying the grader or promotion gate.
2. Add real skill-on/off experiments for current default packs and a sealed holdout.
3. Add cross-task and cross-model transfer matrices for skills.
4. Add a skill lifecycle record: source, version, intended domain, provenance, evidence, expiry, rollback.
5. Connect voice endpointing and interaction metrics to the actual playback clock.
6. Add client-heard audio and avatar sync instrumentation.
7. Add a Live2D event adapter that only writes through the existing avatar authority.
8. Add a disposable Roblox Studio/game adapter that emits trustworthy trajectory events.
9. Run target-PC mixed-load tests and a long-duration soak.
10. Test speculative decoding and KV-cache candidates only as reversible, exact-build canaries.

## 9. Acceptance and safety gates

- No default skill is enabled solely because it exists or because an LLM says it is useful.
- No holdout task is used to write or tune a skill.
- No self-generated grader or automatic promotion.
- No model-weight retraining is implied by external skill-memory updates.
- No public game publishing or live player interaction from research code.
- No microphone, OBS, avatar, or controller activation without the existing explicit owner-controlled switch and permission path.
- No viewer memory without privacy/retention rules.
- No secret, raw conversation, raw audio/video, model weights, or private user data committed to GitHub.
- Every performance claim identifies exact hardware, backend, model/build, context, workload, and client-observed latency.

## Source register

- SWE-Skills-Bench, 2026-03-16: https://arxiv.org/abs/2603.15401
- Memento-Skills, 2026-03-19: https://arxiv.org/abs/2603.18743
- SkillLearnBench, 2026-04-22: https://arxiv.org/abs/2604.20087
- AFTER procedural memory benchmark, 2026-06-22: https://arxiv.org/abs/2606.23127
- E2E-SWE, 2026-09-29: https://arxiv.org/abs/2609.38335
- AVTR-1, 2026-09-19: https://arxiv.org/abs/2609.22913
- InteractionBench, 2026-11-02: https://arxiv.org/abs/2611.02430
- SWE Atlas v1.1, November 2026: https://labs.scale.com/leaderboard/swe-atlas
- Google TurboQuant, 2026-03-24: https://research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression/
- llama.cpp SPEED-Bench: https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench
- llama.cpp speculative decoding: https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md
- llama.cpp Vulkan speculative replay issue: https://github.com/ggml-org/llama.cpp/issues/28060

## Explicit limitations

- The new evaluator is metadata-only and offline.
- No skill was enabled or rewritten.
- No model weights were trained or changed.
- No llama.cpp build, model router, scheduler, microphone, OBS, VTube Studio, or game controller was changed.
- No target-PC speedup or public-stream acceptance is claimed.
