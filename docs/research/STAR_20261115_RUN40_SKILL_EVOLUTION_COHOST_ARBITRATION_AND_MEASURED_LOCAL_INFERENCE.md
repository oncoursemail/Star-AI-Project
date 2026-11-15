# STAR Run 40 — Skill Evolution, Co-Host Stage Arbitration, and Measured Local Inference

**Research date:** 2026-11-15  
**Repository:** oncoursemail/Star-AI-Project  
**Scope:** evidence-backed skill evolution, multi-party VTuber presence, local inference performance, game learning, creator workflows, and general knowledge. This document does not change model weights, production defaults, credentials, or account permissions.

---

## Executive decision

STAR's next useful capability jump should come from **closing the loop between experience, verified skills, social context, and measured runtime performance**.

The repository already contains substantial work in draft branches for task continuity, memory governance, resource admission, game-action authorization, full-duplex voice, playback delivery, inference measurement, and paired evaluation. The next risk is not a shortage of frameworks. It is that these pieces may remain isolated or compete for authority.

Run 40 makes five decisions:

1. **Evolve skills, not unrestricted agent code.** Use experience to propose a better skill, test it in isolation, compare it against the current version, and promote only through STAR's existing independent evaluation and owner-review rules.
2. **Give streaming a bounded conversation map.** A live multi-person stream needs reply-to, addressee, and topic continuity in addition to speaker and intent. Keep this metadata session-local; do not create viewer profiles or merge identities across platforms.
3. **Keep one voice floor.** One host-owned room policy and one actual playback authority decide when speech starts, stops, and finishes. Co-hosts must never race separate queues or talk over one another.
4. **Tune inference with the real serving stack.** Use matched llama.cpp SPEED-Bench runs and consistent TTFT/ITL definitions. A benchmark from vLLM, H100, or another model is not an RTX 4060 result.
5. **Promote outcomes, not model confidence.** A skill, game strategy, creator workflow, or factual claim becomes reusable only with external evidence, a verifier, freshness, and held-out evaluation.

No new foundation model is required for this plan.

## Repository truth and existing authorities

The inspected public main branch is still the STAR v1.0 local-first desktop baseline. Its README describes a Windows 11 desktop app, a local approximately 4B model path, an optional CPU STAR Server, a Roblox Studio integration, and a lesson-based learning loop. The README explicitly reports that answer quality was approximately the same as v0.9.0 in its cited release comparison; the learning loop does not update model weights.

The canonical architecture document also describes a stable-prefix prompt layout for llama.cpp prompt-cache reuse. It warns that chat slot pinning can cause two STAR clients to wait on the same slot; STAR_SERVER_SLOT_PINNING=off is the documented opt-out when multiple clients share a server.

The advanced streaming, game-control, inference, and skill systems discussed below are distributed across **unmerged draft PRs**, not shipped main features. The audited work includes:

- #1177 — durable task and communication ledger.
- #1178 — voice room, room host, natural streamer persona, and research register.
- #1181 — speaker-meter isolation and DAC playback-clock work.
- #1182 — fail-closed screen-to-action GameControlGate.
- #1140/#1142 — resource admission and pressure-governor composition.
- #1166 — paired stream-variant evaluation.
- #1167 — streamed inference timing.
- #1184 — bounded active-perception evidence selection.

These are useful building blocks, but each still needs exact-head CI, integration review, and the appropriate Windows/hardware acceptance. Do not describe a draft contract as a live microphone, OBS, game-controller, or public-stream feature.

### Preserve one authority per responsibility

| Responsibility | Existing authority to preserve |
|---|---|
| Room ingress and moderation | RoomStreamHost |
| Speak / queue / continue / interrupt / stop policy | RoomTurnDirector |
| Actual voice session and playback | CallSession and its trusted playback host |
| Long-running work and report obligations | TaskCoordination / delivery ledger |
| CPU/RAM/VRAM admission | StreamWorkloadRuntime over the existing admission controller |
| Game input authorization | GameControlGate |
| Learning and skill promotion | Existing protected evaluation and promotion gates |
| Model and stream measurements | Existing inference benchmark, trace, and paired-variant evaluator |
| New bounded conversation relationships | Run 40 ConversationContextIndex; metadata only, not a director |

Do not add a second task database, room director, speech queue, GPU scheduler, game-action gate, or general memory store.

---

## 1. Memento-Skills — deployment-time skill evolution

**Paper:** https://arxiv.org/abs/2603.18743  
**Official project:** https://github.com/Memento-Teams/Memento-Skills  
**Project research page:** https://www.memento.run/research/skills/

Memento-Skills treats reusable skills as persistent, evolving agent memory. Its central cycle is:

**Read → Execute → Reflect → Write**

The system retrieves a relevant skill, executes it, reflects on the outcome, and proposes an updated or newly composed skill. The paper describes parameter-free continual adaptation through externalized skill memory rather than requiring foundation-model weight updates.

The public repository is more than a paper diagram: its current README describes a skill-centric runtime with a router, execution, reflection, replanning, guarded skill repair, static/unit/synthetic gates, atomic deployment, audit history, and rollback. Its skill-creator workflow also calls for quantitative evaluations, qualitative review, variance analysis, and expansion of the test set before a skill is treated as complete.

### What STAR should adopt

Use the method, not a second agent runtime:

1. Attribute a failure to a specific skill or missing capability using the actual execution trace.
2. Preserve the exact baseline skill revision.
3. Generate a candidate in a disposable worktree or sandbox.
4. Run static checks, unit tests, and deterministic synthetic cases.
5. Compare baseline and candidate on the same paired practice/validation cases.
6. Run a sealed holdout that the candidate author and grader cannot edit.
7. Require owner review for promotion into active skills.
8. Activate atomically, record the evidence, and retain a one-step rollback.
9. Monitor post-promotion regressions and expire/revalidate skills whose tools, APIs, or environments change.

### What STAR must not copy blindly

- The paper's GAIA and Humanity's Last Exam improvements are paper-specific, not STAR scores.
- A generated skill description is not proof that the skill works.
- A model-written synthetic test is not an independent verifier.
- A skill must not edit its own grader, protected evaluation set, policy gate, or promotion logic.
- A failed trace can have causes outside the skill: stale observation, wrong tool adapter, missing permission, resource starvation, or an environment change.
- Review the upstream Apache-2.0 license and third-party notices before copying code or bundled assets.

### STAR mapping

Reuse the current skill-pack retrieval, lesson candidates, protected-path guard, paired evaluation, SkillPromotionGate, and gameplay skill bank. Memento-Skills is a reference for improving the **candidate authoring and reflection loop**, not a reason to replace STAR's learning controls.

### New evaluations

- Skill trigger precision and recall.
- Correct skill selected for the task.
- Candidate-vs-baseline task success on paired seeds.
- Verifier agreement and false-success rate.
- Held-out transfer to another map, project, or app.
- Regression rate on previously mastered tasks.
- Cost and latency per verified completion.
- Rollback success after a deliberate bad candidate.

---

## 2. Lumi_Nox — practical VTuber stage orchestration patterns

**Official repository:** https://github.com/MIO-456/Lumi_Nox  
**Architecture document:** https://github.com/MIO-456/Lumi_Nox/blob/main/docs/ARCHITECTURE.md  
**Game integrations:** https://github.com/MIO-456/Lumi_Nox/tree/main/games

Lumi_Nox is an open-core reference for two AI characters sharing one live show. Its architecture separates:

- An event bus and global state machine.
- A speaker scheduler that selects who receives the next turn.
- A speech-output arbiter that owns the single audible floor.
- Character-specific dialogue and voice paths.
- Cross-character history mirroring.
- Game-specific adapters and isolated workers.

The most useful idea is the distinction between **who should speak next** and **whether any new audio may start now**. The arbiter's queue/drop/interrupt policies and its use of actual audio completion as the floor-release event are good patterns to study. The game directory also demonstrates that each game needs its own bridge and state semantics; a generic LLM prompt is not a game controller.

### Important limitations in the upstream project

Its own architecture document says the public host uses non-streaming chat and speech adapters that return complete PCM audio. It also says the public host does not automatically wire the separate realtime ASR, memory, game modules, production broadcast platform, OBS, or full director. Its README describes the project as daily-stream-tested, but that self-description is not an independent performance audit.

The scheduler's substring-based name matching and platform-specific paid-message priority policy are implementation choices, not universal social-intelligence rules. STAR should not copy those blindly.

### STAR adaptation

Keep STAR's existing RoomStreamHost, RoomTurnDirector, CallSession, task ledger, playback owner, and resource admission path. The missing piece is richer **conversation relationship metadata**, not another social director.

For a future owner-enabled multi-character show:

- Each character has a separate character ID, persona prompt, voice route, avatar route, and conversation history.
- A shared stage plan selects one character for a response.
- A single playback owner holds the floor until actual playback completion or a valid interruption.
- A handoff is explicit; the next character receives a bounded stage note rather than inheriting the previous character's words as its own memory.
- Viewer-to-viewer conversation remains valid even when STAR says nothing.
- Co-host banter is opt-in and must not manufacture dialogue when the room is quiet.
- Cross-character context is a temporary stage note; it is not permission to merge private memories.

---

## 3. Run 40 implementation — bounded conversation context index

The existing RoomCue contains a speaker reference and a boolean addressed_to_star, but it does not carry distinct addressee, reply-to, or topic/thread references. That limits STAR's ability to follow a multi-person discussion without repeatedly asking who a comment was aimed at.

Run 40 adds:

- star/voice/conversation_index.py
- tests/test_voice_conversation_index.py

The new ConversationContextIndex is deliberately **not** a new room director. It stores only final classified metadata:

- Opaque event and session IDs.
- Source and intent categories.
- A per-session speaker pseudonym.
- Optional addressee pseudonym.
- Optional reply-to event ID.
- Optional topic reference.
- Monotonic host-observation time and sequence.
- A bounded classification confidence value.

It returns a limited reply chain, same-topic events, and recent events for the current event. Missing or evicted reply parents are reported explicitly instead of being guessed.

### Privacy and bounds

- A new index is created for each stream session.
- Speaker references must be generated by the trusted adapter for that source and session.
- Audio and chat identities must never be joined across platforms.
- No transcript, audio, viewer message, provider account ID, voiceprint, or model-generated summary is stored.
- Partial ASR cues are not retained.
- Event count, age, reply depth, topic count, participant count, and dedupe history are bounded.
- Stale, future, wrong-session, duplicate, out-of-order, invalid, and post-close events fail closed.
- close() clears all retained references.

The component is not yet wired to provider diarization, chat adapters, ASR, RoomStreamHost, or the model prompt. That is intentional: a trusted adapter must first supply reliable addressee/reply/topic metadata. The index itself must not infer identity or decide who gets the floor.

### Required integration tests

- Two people discussing a topic while STAR remains quiet.
- A viewer replies to another viewer rather than STAR.
- A direct mention of STAR inside an existing thread.
- A topic changes while an older reply arrives late.
- A referenced parent has expired or been evicted.
- Chat and audio sources use separate session pseudonyms.
- A source reconnects and starts a new session epoch.
- The room closes and all ephemeral references are erased.

---

## 4. Faster local inference — use the official llama.cpp workload benchmark

**llama.cpp SPEED-Bench client:** https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench  
**Benchmark README:** https://github.com/ggml-org/llama.cpp/blob/master/tools/server/bench/speed-bench/README.md  
**NVIDIA AIPerf metric definitions:** https://docs.nvidia.com/aiperf/reference/ai-perf-metrics-reference

The official llama.cpp SPEED-Bench client targets an already-running llama-server. Its documented measurements include prompt prefill throughput, predicted/decode throughput, client-observed request latency, and speculative draft acceptance. It supports comparing ordinary decoding with supported draft-model, n-gram, MTP, and EAGLE3 configurations.

A crucial operational detail in the official README: **match benchmark client concurrency to the server's parallel slot count (--np)** when measuring throughput. Baseline and candidate runs must use the same benchmark split, category, output length, sample limit, and concurrency.

### STAR experiment matrix

Start with the exact backend and hardware STAR will actually use. Record the server build, model file hash, tokenizer, quantization, GPU driver, context size, batch/ubatch sizes, slot count, prompt-cache settings, and draft method.

| Experiment | Baseline | Candidate |
|---|---|---|
| Prompt cache | Cold request | Warm stable prefix |
| Context | 2K / 4K | 8K / 16K if supported |
| Slots | 1 | 2, then 4 only if memory and tail latency permit |
| Concurrency | 1 | Match the tested server slot count |
| Speculation | Off | Each backend-supported draft method separately |
| Workload | Coding | Math, RAG, reasoning, humanities, roleplay |
| Model quantization | Current release quant | One alternate quant at a time |
| GPU offload | Current layer split | One measured alternate split |

Do not change multiple server parameters at once. Run a warm-up, then matched baseline/candidate samples. Save per-request results and exact configuration. Use the server's own --help output for the pinned build because flags and defaults evolve.

### Metrics that matter

NVIDIA AIPerf defines TTFT as time from request submission to the first non-empty content response, including queueing, network, prompt processing, and first-token generation. Inter-token latency measures the spacing between generated tokens; end-to-end latency measures the complete request. Tools differ in definitions, so only compare aligned metrics.

For STAR, record:

- Queue wait p50/p95/p99.
- Prompt prefill tokens/s.
- TTFT p50/p95/p99.
- ITL/TPOT p50/p95/p99.
- Decode tokens/s and total request latency.
- First TTS chunk and first audible playback.
- Interruption-to-stop latency.
- Peak VRAM/RAM and CPU utilization.
- Cache reuse and speculative acceptance.
- Task success, verifier agreement, and answer-quality regression.
- Game frame-time p95/p99, OBS render/encoder lag, and audio underruns during mixed load.

### Hardware-specific recommendation

The local 8 GB GPU is shared by the model, desktop compositor, game, OBS, and potentially vision/avatar work. Do not optimize token throughput in isolation.

- Protect audio, game control, voice, and avatar deadlines first.
- Defer research, training, large vision jobs, and asset generation when a live game/stream is active.
- Do not keep several heavy models resident in VRAM merely to avoid a reload unless the measured memory budget proves that safe.
- Keep stable system instructions and tool ordering in the prompt prefix; put per-turn retrieval and changing state after the stable prefix.
- Disable shared slot pinning when multiple STAR clients would contend for the same pinned slot.
- Treat H100, vLLM, and paper-only speculative speedups as research evidence, not RTX 4060 measurements.
- TurboQuant or another KV-cache method is only a candidate if the pinned backend actually supports it and paired long-context retrieval tests remain stable.

The target is not the highest isolated tokens/second. It is the best **verified task quality at the lowest interactive tail latency under voice + game + OBS load**.

---

## 5. Gamer Brain — learn mechanics, not button sequences

Keep the existing GameControlGate as the only game-action authorization boundary. Keep capture, target identity, owner consent, focus, freshness, action limits, manual override, and emergency stop in the trusted host.

For every new game:

1. Identify the game's rules, controls, objective, and observable state.
2. Start in a resettable, permitted practice environment.
3. Record the initial state and exact game/version/map/seed.
4. Try one bounded action or a small controlled action sequence.
5. Observe the resulting state change.
6. Compare the outcome against an independent verifier.
7. Store a candidate strategy with preconditions and failure cases.
8. Test it on unseen maps, seeds, or task variants.
9. Report live-speed, slowed, and paused results separately.

A scripted game-side test, a browser benchmark, and screen-driven play are different capabilities. Do not report one as proof of another.

### Roblox Creator Brain

Use Roblox Studio's built-in MCP and StudioTestService for inspection, playtest, and deterministic server/multi-client tests. Keep tests in a disposable unpublished place. Use server/client assertions for lobby, matchmaking, replication, disconnect, join/leave, and remote-event validation.

The workflow should remain:

**Inspect → Plan → Edit → Run → Capture → Verify → Repair → Re-test**

A screenshot is useful visual evidence, but not a substitute for a state assertion. A successful script execution is not proof that the complete game feature works.

---

## 6. General knowledge and practical learning

STAR should keep distinct records for:

- **Factual knowledge:** claims with sources, dates, scope, supporting and contradicting evidence.
- **Conceptual knowledge:** explanations and relationships between ideas.
- **Procedural skills:** verified instructions for doing something.
- **Episodic evidence:** what actually happened in a specific game, stream, or project.
- **Strategic knowledge:** when a method is appropriate and when it is not.

A skill success must not silently become a universal factual claim. A factual answer must not become a procedure without a tested execution. Old evidence must not be presented as current state.

For research and general knowledge, report uncertainty, source freshness, contradictions, and the boundary between retrieved facts and STAR's inference.

---

## 7. Natural VTuber behavior — measurable, not theatrical

Natural presence is not constant talking, forced laughter, random catchphrases, or pretending to have a human biography. STAR is an AI character and should remain transparent about that.

The highest-value behavior changes are:

- Know whether a comment is addressed to STAR, another viewer, a co-host, or nobody in particular.
- Follow reply chains and topics without answering the wrong person.
- Allow viewer-to-viewer conversation to continue.
- Use actual playback state for mouth movement and interruption.
- Do not repeat a response after a human has already resolved the question.
- Keep game commentary tied to verified events, not invented observations.
- Resume a background task only when its result is still relevant.
- Preserve separate character voices and histories if an owner-enabled co-host mode is introduced.
- Treat silence as a valid social action.

### Replay metrics

Measure direct-mention precision/recall, addressee accuracy, reply-chain accuracy, topic continuity, false interruptions, missed direct requests, appropriate silence, speech overlap, stale-result delivery, and time from audible end-of-turn to next appropriate response.

Use recorded and synthetic replay scenarios first. Do not connect public chat or broadcast accounts as part of a benchmark.

---

## 8. Run 40 implementation and review status

### Implemented in the companion code PR

- New metadata-only ConversationContextIndex.
- Bounded per-session event history.
- Reply-chain, topic, and recent-event context.
- Strict sequence, freshness, session, capacity, and dedupe checks.
- Explicit missing-parent reporting.
- Session-close erasure.
- 12 focused offline regression tests.

### Research and catalog updates

- Memento-Skills.
- Lumi_Nox.
- llama.cpp SPEED-Bench.
- NVIDIA AIPerf metrics.

### Not implemented or claimed

- No ASR diarization or addressee classifier is wired to the new index.
- No new speech scheduler or output arbiter is added.
- No provider OAuth, Twitch/YouTube connection, public chat ingestion, OBS broadcast, or VTube Studio connection is enabled.
- No model weights, datasets, emulator, or benchmark assets are installed.
- No fine-tuning or reinforcement-learning run is performed.
- No local GPU speedup, game mastery, or human-equivalence result is claimed.
- The code PR is a standalone contract foundation; full provider and Windows integration remains a separate acceptance step.

---

## 9. Recommended implementation order

| Priority | Work | Acceptance |
|---|---|---|
| 1 | Finish exact-head CI for the current PR stack | All required checks green on exact heads |
| 2 | Add trusted addressee/reply/topic metadata at room ingress | Source/session validation and no raw content in index |
| 3 | Build recorded multiparty replay suite | Correct addressee, thread, topic, and silence metrics |
| 4 | Integrate context packet into the existing voice prompt builder | No duplicate director or speech queue |
| 5 | Add skill-attribution and candidate-repair workflow | Isolated worktree, protected paths, independent grader |
| 6 | Run paired skill evolution tests | Held-out improvement and rollback proof |
| 7 | Run llama.cpp SPEED-Bench on the actual local/server build | Same samples, slots, model, and environment |
| 8 | Run mixed-load Windows rehearsal | Voice, game, avatar, and OBS tail latency remain within budget |
| 9 | Run Roblox StudioTestService and screen-driven game acceptance | Separate game-side and visual-control scores |
| 10 | Private VTuber rehearsal | Owner-approved voice, avatar, social behavior, and stop controls |

**Final principle:** STAR becomes more capable by learning verified procedures, maintaining the right context, and spending compute where it changes the outcome—not by adding more uncoordinated agents or loading every model at once.
