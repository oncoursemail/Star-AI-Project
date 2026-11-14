# STAR Run 23 — Evidence-Grounded Skills, Streaming ASR, and Memory-to-Action Intelligence

**Research date:** 2026-11-14  
**Repository:** `oncoursemail/Star-AI-Project`  
**Branch:** `feat/resource-admission-20261113-run21`  
**Scope:** local-first desktop assistant, multiparty VTuber streaming, game-playing, Roblox/game creation, general knowledge, long-horizon autonomy.

## Executive decisions

This pass makes five architecture decisions:

1. **Do not equate a larger model with higher intelligence.** Measure task success, transfer, calibration, and latency under the actual mixed workload.
2. **Keep one resource-admission authority.** Existing PRs #1140 and #1142 remain the scheduling path. ASR, TTS, gameplay, and background agents must request resources through it rather than creating parallel schedulers.
3. **Treat streaming ASR as an event source, not a turn-taking authority.** The existing TurnDetector, RoomTurnDirector, and trusted RoomStreamHost continue to own when STAR speaks, waits, queues, interrupts, or stops.
4. **Turn experience into executable, evidence-linked skills.** A successful trace is only a candidate skill; it must pass isolated tests and held-out transfer checks before promotion.
5. **Use task-adaptive memory.** Retrieve the smallest complementary evidence set that answers the current question; do not stuff every memory store into every prompt.

No model weights, ASR/TTS provider, provider credentials, game controller, OBS/VTube Studio transport, or production defaults are installed or enabled by this research pass.

---

## 1. Streaming speech: compare the right candidates for STAR's hardware

### 1.1 Microsoft VibeVoice-ASR-Streaming

Primary sources:
- [Microsoft Research technical report](https://www.microsoft.com/en-us/research/publication/vibevoice-asr-streaming-technical-report/)
- [Official VibeVoice repository](https://github.com/microsoft/VibeVoice)

The September 2026 report describes chunked, speaker-attributed streaming ASR. It interleaves fixed-size audio chunks, a small lookahead, and previous text so that the model can produce speaker-attributed transcription while audio arrives. The report describes 1.5B and 7B variants and reports strong average WER/CER and speaker-attribution results on its own five evaluation sets.

**STAR assessment:** valuable for evaluating the combined ASR + diarization problem, especially when multiple viewers speak. The 7B model is not a sensible default alongside STAR's main model, Roblox/other game rendering, OBS, and a VTuber avatar on an 8 GB GPU. The 1.5B model still requires a complete mixed-load memory test. Do not infer that a checkpoint's parameter count alone establishes its usable VRAM or RAM footprint.

### 1.2 VibeASR.cpp: a CPU-first candidate

Primary source: [Microsoft VibeASR.cpp](https://github.com/microsoft/VibeASR.cpp)

The upstream project describes a heterogeneous BitNet quantized VibeVoice-ASR runtime with a 1.58 GB model package. Its README reports real-time-factor results on an Intel Core i7-13700 running Windows 11: 0.93 at one thread, 0.56 at two threads, 0.43 at three threads, and 0.37 at four threads. The benchmark excludes one-time model loading and uses a warmed-up approximately 20-second clip. These are upstream results, not STAR measurements.

Important integration constraint: the current build notes say MSVC is unsupported and recommend GCC/Clang with MinGW-w64 on Windows. The visible quick-start demonstrates file inference; it does **not** establish a drop-in incremental streaming API.

**STAR assessment:** benchmark it as a CPU transcription baseline and potential background/after-turn recognizer. Do not label it a streaming replacement until the runtime exposes a supported incremental interface and passes a real microphone test. Include build complexity, thread contention, model warm-up, and CPU usage in the score.

### 1.3 X2Streaming-ASR: an excellent commit-policy reference, not a local default

Primary sources:
- [Official X2Streaming-ASR repository](https://github.com/X-Square-Robot/X2Streaming-ASR)
- [Research paper](https://arxiv.org/abs/2609.08672)

X2 separates **when to commit** from **what text to decode**. Every 80 ms audio token can lead to LISTEN or DECODE. Its output is append-only, and the encoder/KV history is reused rather than recomputing the entire prior audio. The upstream README reports English word-emission latency of 12–85 ms on its test sets.

The same README documents a 4B model and a vLLM multi-session configuration using roughly 40–43 GB on an A800 80 GB system for six sessions. This is plainly not a local 8 GB GPU target.

**STAR assessment:** borrow the commit-policy and no-repeated-re-encoding ideas. Keep the model as a large-GPU research reference unless a separately measured quantized CPU/single-session deployment becomes available.

### 1.4 Keep the existing candidates in the bake-off

The current catalog already contains:
- Moonshine Voice streaming ASR (R117–R119).
- sherpa-onnx online transducer models (R123).

Do not pick a winner from a paper's headline metric. Compare Moonshine Tiny/Small, sherpa-onnx, VibeASR.cpp, and any VibeVoice streaming checkpoint on the same consented audio and the same STAR host path.

### 1.5 Required ASR adapter contract

A provider adapter should consume STAR's existing microphone frames; it must not open a second microphone capture path. Emit typed events with:

- `session_id` and monotonically increasing `generation_id`;
- opaque `utterance_id` and source-local sequence number;
- monotonic arrival timestamp;
- provisional text with a revision number;
- final/committed text with a commit sequence;
- optional session-scoped speaker pseudonym;
- confidence and model/backend metadata.

Rules:
- Provisional text may update captions but must not independently authorize a spoken reply or irreversible tool action.
- A final transcript is evidence, not permission to speak. The existing turn detector and room director decide whether the utterance is complete, directed to STAR, and worth responding to.
- A cancellation or new call generation invalidates late callbacks. Stale ASR output must never enter a later turn.
- Speaker labels are session-scoped pseudonyms. They do not establish real identity, addressee, or permission to retain biometric information.
- Keep one microphone owner, one consent path, and one canonical transcript in the turn history.

---

## 2. Memory that supports action, not just recall

### 2.1 AMA-Bench: agent memory is not ordinary chat history

Primary source: [AMA-Bench, ICML 2026](https://proceedings.mlr.press/v306/zhao26bs.html)

AMA-Bench evaluates trajectories containing observations, actions, state changes, and tool outputs rather than only conversational messages. The authors identify missing causal/objective information and similarity-only retrieval as weaknesses in existing memory systems. Their AMA-Agent uses a causality graph and tool-augmented retrieval; the paper reports 57.22% accuracy and an 11.16-point improvement over its strongest baseline on its benchmark.

**STAR implication:** store what happened, what action changed the environment, what evidence confirmed the change, and what downstream result followed. A vector hit alone is not enough to prove that a prior strategy worked.

### 2.2 MESA: choose a complementary subset of memories

Primary source: [MESA, arXiv:2608.10108](https://arxiv.org/abs/2608.10108)

MESA builds five complementary views of a trajectory:
1. episode summary;
2. temporal/event sequence;
3. entity/relation graph;
4. vector-semantic memory;
5. raw episodic trace.

It selects a query-specific subset rather than always reading all stores or choosing only one. The authors report 65.1% AMA-Bench accuracy, 8.5 points above the strongest prior baseline, while using 41% fewer evidence tokens than the all-structure alternative.

**STAR implication:** route by query type:
- “What did I decide?” → summary + temporal evidence.
- “Why did this feature fail?” → causal graph + raw test trace.
- “Which API name was used?” → exact/lexical retrieval + official documentation.
- “How do I perform this again?” → procedural skill + its validation trace.
- “What happened during the stream?” → temporal events + relevant media/evidence pointers.

Do not add all memory structures to every prompt. Record which sources were selected and whether they actually improved the answer.

### 2.3 UMA: memory needs a maintenance policy

Primary source: [Learning to Remember, EMNLP 2026](https://aclanthology.org/2026.emnlp-main.1299/)  
Implementation: [Unified Memory Agent](https://github.com/ictnlp/unified-memory-agent)

UMA jointly studies memory-bank create/update/delete/reorganize operations and question answering. Ledger-QA tests state tracking where the answer depends on accumulated updates rather than a single retrieved sentence.

**STAR implication:** memory writes need explicit lifecycle decisions:
- create a candidate fact or skill;
- attach source and timestamp;
- update when newer evidence supersedes old evidence;
- preserve contradictory evidence rather than silently overwriting it;
- expire transient state;
- delete according to owner retention policy;
- test retrieval on future questions.

Do not import UMA's training stack as a desktop dependency. Adapt the memory lifecycle and benchmark ideas first.

---

## 3. Continual game learning: turn discoveries into tested skills

### 3.1 Continual Harness

Primary sources:
- [Continual Harness project](https://continual-harness.github.io/)
- [Official ARC-AGI-3 implementation](https://github.com/feng-rrRay/Continual-Harness-ARC-AGI-3)

Continual Harness treats the agent's prompt, memory, reusable skills, and subagents as an editable external world model. It refines those components during a run rather than restarting from scratch. Its public report describes 25 ARC-AGI-3 games and says 62% of its executed actions came from saved skills; its reported 20.54% score used Gemini 3.1 Pro and the benchmark's own protocol.

**STAR implication:** reuse the architecture pattern, not the benchmark score. STAR should retain an explicit model of mechanics and convert confirmed discoveries into callable routines. Every rule needs a confidence/evidence label. An untested guess must never become a trusted skill.

### 3.2 SkillHorizon: test complete workflows, not isolated steps

Primary sources:
- [SkillHorizon paper](https://arxiv.org/abs/2610.14966)
- [Official implementation](https://github.com/KnowComp/SkillHorizon)

SkillHorizon composes dependent skills into long workflows with shared state and programmatic local/whole-task checks. Its paper reports 1,050 tasks and shows local-goal completion falling as workload scales from 64K to 1M reference tokens. This highlights an important failure mode: an agent can perform many valid steps and still fail to complete the overall objective.

**STAR implication:** evaluate complete outcomes. “Created the scripts” is not “finished the game.” “Generated the model” is not “exported and validated the asset.” “Answered a question” is not “completed the requested multi-step task.”

### 3.3 STAR Skill Record schema

Every candidate skill should contain:

- `skill_id`, semantic version, domain, and supported environment versions;
- concise purpose and preconditions;
- required tools and permission scope;
- inputs/outputs with schemas;
- action budget, timeout, and resource estimate;
- procedure or sandboxed executable;
- evidence links to the observations/actions that justify it;
- expected postconditions and independent verifier;
- known failure modes and recovery procedure;
- confidence level and number of independent successful runs;
- holdout tasks and transfer results;
- owner/approval state and rollback target.

Promotion pipeline:

`candidate → replay → isolated test → adversarial test → held-out transfer → approved version → monitor → rollback if regression`

Suggested initial gate: at least three independent successful replays, a clean held-out variant, and no regression on the skill's prior test set. Tune the threshold by domain; three successes are a starting governance rule, not a statistical guarantee.

---

## 4. Gamer Brain and Creator Brain

### Gamer Brain

Use two cooperating control rates:

**Fast controller**
- movement and camera primitives;
- aiming, dodging, jump timing, interaction;
- frame-bounded execution;
- deterministic safety limits and immediate stop.

**Strategic planner**
- goals, exploration, inventory, quest/combat strategy;
- mechanic hypotheses and experiment selection;
- event-triggered replanning after death, objective completion, boss appearance, resource depletion, or repeated failure.

The planner should not call a large model for every frame. It should issue a bounded option such as “navigate to the marked resource,” monitor progress, and replan only when the observed state violates the option's expected outcome.

### Unknown-game learning loop

1. Observe screen and, when available, structured game state.
2. Identify controllable actions and safe no-op/low-risk probes.
3. Form a small number of explicit mechanic hypotheses.
4. Choose experiments that distinguish those hypotheses.
5. Record state-before, action, state-after, cost, and result.
6. Update the world model with confidence and counterexamples.
7. Create a skill only after repeated verification.
8. Test on a different map, difficulty, or seed.
9. Detect drift when the game version or mechanics change.

Use the existing GameWorld (R126–R127) and Roblox OpenGameEval (R110–R111) research as evaluation references. Pin exact benchmark versions and manifests; do not mix leaderboard snapshots or assume external scores are STAR scores.

### Creator Brain

For Roblox, Godot, Unity, Blender, UI, animation, and VFX, use:

`inspect → plan → edit → run → observe → compare → repair → verify`

Acceptance must include:
- static checks and type/lint validation;
- runtime launch;
- scene/gameplay assertions;
- screenshot/video evidence where visuals matter;
- performance/frame-time check;
- regression tests for existing behavior;
- reproducible project diff and rollback.

Use explicit `studio_id` routing for multiple Roblox Studio instances. Never infer the target Studio from whichever window happens to be active.

---

## 5. VTuber presence: one synchronized event timeline

LiViBench is already registered in the catalog (R60–R61). It evaluates livestream understanding across audio, speech, and live comments. Combine its task categories with the existing Full-Duplex-Bench v3 and MP-Bench work (R124–R125 and earlier multiparty sources).

The next architecture should expose one session-scoped event timeline:

`microphone / ASR / chat / game observer / OBS → normalized event → policy → response or action → playback/visual acknowledgement`

Recommended event envelope:
- session and generation ID;
- opaque event ID and source sequence;
- source type and monotonic timestamp;
- provisional/final status;
- evidence pointer and short TTL;
- confidence and classifier version;
- consent and moderation state;
- response-generation ID when an event causes a reply.

Policy:
- Direct speech addressed to STAR gets priority.
- Viewer-to-viewer conversation is usually observed, not interrupted.
- Chat is coalesced and moderated; do not let chat volume drown out speech.
- Game events are commentary candidates, not commands to execute.
- Low-value repeated events are summarized or dropped.
- A stale event cannot trigger a new response after its TTL.
- The room director remains the only floor-control authority.
- The avatar follows actual played audio and explicit playback acknowledgements, not text that was merely generated.
- Keep raw audio ephemeral by default; store only the minimum event metadata needed for session continuity.

Naturalness is not achieved by adding fake laughs or a random reaction to every turn. It comes from accurate attention, proportionate responses, conversational timing, memory of the current topic, and being comfortable with silence. Keep STAR transparently identified as an AI character; do not fabricate human biography or lived experience.

---

## 6. Performance plan for the actual local machine

STAR's local target includes an 8 GB GPU shared with the main model, game rendering, OBS, and avatar work. Treat CPU/RAM as the first place to test secondary workloads, but do not assume CPU is free: Roblox/Unity builds, OBS encoding, and other background jobs also compete for CPU and memory bandwidth.

Keep the existing #1140/#1142 resource-admission path as the only scheduler. Candidate workload policy:

| Workload | First benchmark placement | Reason |
|---|---|---|
| Main reasoning model | Existing configured backend | Preserve current stable path |
| VAD/audio framing | CPU | Small deterministic work |
| Streaming ASR | CPU-first candidate bake-off | Protect shared VRAM |
| Speaker attribution | CPU or separate bounded worker | Do not load a large model by default |
| TTS | Current Kokoro path; benchmark CPU/GPU alternatives | Avoid extra VRAM contention |
| Game perception | Event-driven sampling | Avoid processing every frame with a large VLM |
| Background research/build agents | Deferred, checkpointed | Preserve interactive latency |

Do not blindly add speculative decoding, KV compression, RAM offload, or a second inference server. Each must pass a paired benchmark on the exact model/backend and mixed workload.

### Required performance metrics

Collect p50/p95/p99 for:
- microphone capture to partial transcript;
- capture to committed transcript;
- end-of-turn to first model token;
- first model token to first sentence;
- sentence to first generated audio;
- first audio to actual client-heard audio;
- interruption request to silence;
- event arrival to avatar expression;
- game observation to action;
- background task completion and checkpoint time.

Also collect:
- ASR WER/CER by scenario;
- TTS real-time factor and intelligibility;
- queue drops, device under/overflows;
- CPU/RAM/VRAM peaks and sustained pressure;
- GPU utilization and model-load time;
- game frame-time p95/p99;
- OBS skipped/lagged frames;
- response correctness, addressee precision, false interruptions;
- skill replay success and held-out transfer;
- retrieved evidence tokens and answer accuracy.

Measure at the client output when possible. A server-side queue timestamp is not proof that a viewer heard the audio.

### Mixed-load experiment matrix

Run each candidate under:
1. idle desktop;
2. voice conversation only;
3. game only;
4. OBS + avatar only;
5. voice + game + OBS + avatar;
6. all interactive workloads plus one background research/build agent;
7. thermal/long-session soak.

Use the same consented audio clips, prompts, game seed, resolution, encoder settings, and model versions. Report hardware, OS, backend, quantization, thread count, warm/cold state, and commit hash. A single best run is not a performance claim.

---

## 7. Actual infrastructure hardening in this run

The room host maintained a bounded per-speaker rate table, but when it reached `max_speakers`, it evicted the least-recently-used entry even if that speaker's rate window was still active. A stream that rotated opaque speaker IDs could therefore erase active per-speaker rate history.

The host now:
- reclaims only speaker windows that have fully expired;
- rejects a new speaker ID with `room_speaker_capacity` if all bounded slots are still active;
- exposes `rejected_speaker_capacity` in aggregate host stats;
- preserves the source-wide limit as a separate aggregate guard.

A synthetic-clock regression test covers ID churn, preservation of the original speaker's active limit, and slot recovery after expiry. This hardens the trusted host ingress; it does not implement diarization or identify people.

---

## 8. Phased implementation plan

### Phase A — Establish trustworthy baselines
- Run the current branch's exact-head CI.
- Run physical microphone/speaker tests on the target Windows machine.
- Capture a consented 30–60 minute test set covering names, game jargon, accents, code-switching, overlap, interruptions, and silence.
- Record current ASR, first-audible, frame-time, and resource baselines.

### Phase B — CPU ASR bake-off
- Integrate Moonshine through STAR's existing microphone frames behind an opt-in provider switch.
- Add sherpa-onnx as a comparable local baseline.
- Evaluate VibeASR.cpp as a CPU transcription candidate; first resolve MinGW/Clang packaging and whether its interface can support incremental chunks.
- Evaluate VibeVoice streaming diarization separately; keep X2 as a large-GPU design reference.
- Promote only if accuracy, latency, CPU cost, and mixed-load performance all improve.

### Phase C — Memory-to-skill learning
- Add evidence-linked skill records to the existing learning lab.
- Add causal state/action/outcome links to episodic memory.
- Add query-adaptive memory selection across temporal, causal, semantic, procedural, and raw evidence.
- Create held-out tasks for cross-map, cross-game, cross-project, and cross-role transfer.
- Keep candidate changes isolated and rollbackable.

### Phase D — Real streamer rehearsal
- Connect authenticated provider adapters only after explicit owner consent.
- Add event TTL, dedupe, moderation, and source-specific rate limits.
- Test multiparty speech and viewer-to-viewer hard negatives.
- Connect OBS/VTube Studio with least privilege and credential-store handling.
- Rehearse mixed load before enabling public streaming.

---

## 9. Non-negotiable acceptance gates

A capability is not “implemented” because a package is installed or a prompt mentions it.

- **ASR:** committed transcript accuracy and p95 latency pass on the same held-out audio set; stale generations are discarded.
- **Turn-taking:** direct-address precision is measured; false interruptions and wrong-speaker replies remain below the agreed threshold.
- **TTS:** first audible latency, intelligibility, voice consistency, cancellation, and long-session drift are tested.
- **VTuber:** mouth movement and expression follow actual playback; avatar events are cancelled with the matching response generation.
- **Gaming:** success is checked from game state, not the agent's self-report; new-map transfer is measured.
- **Creator:** project launches, playtests, visual checks, and regression checks pass.
- **Memory:** every promoted fact/skill has provenance, confidence, and an expiry/update rule.
- **Self-improvement:** candidate changes pass isolated tests and sealed holdouts before promotion; rollback is available.
- **Autonomy:** routine tasks can run within granted scope; irreversible/external actions remain owner-approved.

## 10. Source register additions

New catalog entries R132–R144:
- X2Streaming-ASR implementation and paper.
- Microsoft VibeVoice-ASR-Streaming report and implementation.
- Microsoft VibeASR.cpp CPU runtime.
- AMA-Bench.
- MESA.
- UMA paper and implementation.
- Continual Harness project and implementation.
- SkillHorizon paper and implementation.

Existing sources reused rather than duplicated: Moonshine (R117–R119), sherpa-onnx (R123), Full-Duplex-Bench v3 (R124–R125), GameWorld (R126–R127), vLLM/SGLang/llama.cpp (R128–R131), LiViBench (R60–R61), and Roblox OpenGameEval (R110–R111).

## Final engineering conclusion

The next meaningful intelligence gain is not simply a larger model. It is a tighter loop from **observe → remember evidence → form a hypothesis → act → verify → distill a reusable skill → test transfer**.

The next meaningful streaming gain is not simply faster TTS. It is one low-latency, generation-safe event pipeline where audio, chat, gameplay, speech, and avatar playback share timestamps and cancellation semantics.

All research results above are external results. STAR's own performance must be measured on its exact hardware, code commit, model versions, and mixed workload.
