# STAR Run 24 — Integration Blueprint for a Continuous VTuber, Gamer, Creator, and Learning Agent

**Research date:** 2026-11-14  
**Repository:** `oncoursemail/Star-AI-Project`  
**Branch:** `research/star-run24-integration-blueprint-20261114`  
**Base:** `main` at `d9b0876d6af2c9e2068ddba6286ff97204313d8f`  
**Scope:** architecture consolidation, real-time streaming, game-playing, game creation, general knowledge, continual learning, local inference, and release governance.

---

## Executive decision

STAR's next major capability jump should come from **integration quality**, not from indiscriminately adding larger models or more independent agents.

The repository already has substantial draft work for resource admission, event timelines, full-duplex voice, multiparty turn-taking, memory governance, game evaluation, streamed inference measurement, and avatar transport. The highest risk is now fragmentation: two schedulers, two event clocks, two memory authorities, or several overlapping evaluators can make the combined system slower and less trustworthy even if each isolated prototype looks good.

This blueprint makes six decisions:

1. **One host-owned event spine.** Every audio, chat, game, tool, speech-playback, avatar, and OBS event must have an epoch, monotonic sequence, source, trust class, and freshness boundary.
2. **One resource-admission authority.** Realtime speech, game control, avatar output, interactive tools, and background work must share the existing lease-based admission path. Do not add another scheduler.
3. **Two coordinated execution loops.** The foreground loop preserves conversation and game-control deadlines; the background loop researches, learns, builds, and verifies without starving the foreground.
4. **Evidence before learning.** A successful episode creates a candidate memory or skill, not an automatically promoted fact. External checks and held-out transfer are required.
5. **One paired evaluation protocol.** A faster candidate is not an improvement if it reduces answer quality, turn-taking, game success, frame rate, or audio reliability.
6. **Explicit platform consent.** OBS, VTube Studio, microphones, game input, and external accounts remain separately permissioned. AI-generated content never grants itself additional authority.

No model, package, dataset, provider, credential, or production default is installed or enabled by this document.

---

## 1. Repository reality check — what is already underway

This audit was made against GitHub on 2026-11-14, rather than assuming that previous research notes had already shipped.

### Production baseline

- `main` currently points to `d9b0876d6af2c9e2068ddba6286ff97204313d8f`.
- The public v1.0 release and production branch are distinct from draft PRs and CI artifacts.
- A passing draft-branch workflow does not mean the feature is in the installer or available to users.

### Relevant open draft work

| PR | Current purpose | Dependency / integration note |
|---|---|---|
| #1177 | Durable task and communication ledger | Stacks on the stream-host session work; provides task generations, leases, checkpoints, and playback-acknowledged report obligations. |
| #1178 | Natural streamer persona and resolved-reply stopping | Stacks on #1177; latest inspected head was `0fb5d5e75c41be8e509c924d4f75863fcf8351d4`. It is open, draft, and unmerged. |
| #1140 | Lease-based resource admission for realtime work | Foundational scheduler path; leases must remain reserved until the host confirms worker termination. |
| #1142 | Compose stream-pressure governor with resource admission | Builds on #1140; this is the intended single admission authority. |
| #1143 / #1144 | Paired speed-versus-quality evaluation and causal turn-taking evaluation | Dependent evaluation train; preserve paired task/environment evidence and conversation-disjoint holdouts. |
| #1107 | Multiparty floor evidence | Separates speaker distinction from addressee/response-intent decisions. |
| #1108 | Paired GameDevBench creator evaluation | Stacks on the multiparty floor branch; keep engine-specific results separate. |
| #1109 / #1117 | Continual memory transfer and governed consolidation | Evaluate utility separately from whether a proposed memory change is safe and reversible. |
| #1159 | Latest-wins Live2D/VTube Studio frame pump | Avatar samples may be coalesced; speech, task events, and acknowledgements may not be silently dropped. |
| #1166 | Paired realtime revision evaluator | Compares quality, latency, game/stream stability, and resource use with host-signed trial evidence. |
| #1167 | Streamed first-content and token timing | Independent branch from `main`; keep first-content, inter-token, and full-response timing distinct. |

The inspected #1178 head has successful exact-head GitHub Actions runs #6128 (offline checks) and #3222 (desktop checks). Those are CI results for that draft head, not a merge, release, or physical microphone/OBS/VTube Studio acceptance test.

### Integration risks identified

- Several feature trains are intentionally stacked. Do not cherry-pick a child branch onto `main` while omitting its required parent contract.
- Do not create a second resource scheduler beside #1140/#1142.
- Do not create a second authoritative stream event timeline beside the event-timeline work.
- Do not let a model-generated transcript, diarization label, screenshot, or game event authorize tools or TTS by itself.
- Do not duplicate the paired evaluation logic already being developed in #1143/#1166.
- Keep model/provider experiments opt-in until paired hardware measurements exist.
- The shared frontier-source catalog is deliberately not modified in this standalone research branch because multiple active draft trains also append to it. The source list below is self-contained; reconcile it into the central catalog after the concurrent catalog changes are reviewed.

**Architecture implication:** the next step is to integrate and verify the existing dependency trains, not to create another parallel implementation of their core responsibilities.

---

## 2. Research findings that materially change STAR's roadmap

### 2.1 Continual learning: measure transfer and interference, not memory volume

**AGENTCL** introduces controlled task streams in which earlier tasks may be compositionally reusable, unrelated, or intentionally independent. It finds that naive task streams can hide differences between memory designs, while held-out or unrelated tasks can expose memory-induced degradation. Its MemProbe approach explicitly examines interactions, insights, and skills while filtering unreliable experiences.

- Paper: https://arxiv.org/abs/2606.02461

**SkillLearnBench** evaluates skill quality, execution trajectories, and task outcomes across 20 verified skill-dependent tasks and 15 subdomains (100 verified instances in the public project). The paper reports that repeated improvement with external feedback can help, while self-feedback alone can produce recursive drift; no single continual-learning method wins across all tasks and models.

- Paper: https://arxiv.org/abs/2604.20087
- Official code: https://github.com/cxcscmu/SkillLearnBench

**STAR decision**

Use three separate task-stream classes:

1. **Dependent/compositional:** a later task can reuse an earlier verified sub-skill.
2. **Independent:** no meaningful reuse should occur.
3. **Revision/conflict:** a later task changes a fact, API, project state, or prior assumption.

Measure:
- transfer gain on dependent tasks;
- no-harm / negative transfer on independent tasks;
- correction and update accuracy on revision tasks;
- retention after a delay;
- stale-skill rejection;
- confidence calibration;
- evidence-token and retrieval cost.

A skill is promoted only after an external verifier or deterministic environment check confirms it and a held-out task demonstrates transfer. A model grading its own output is not sufficient evidence.

### 2.2 Game creation: visual feedback is part of the reasoning loop

**GameDevBench** is an ICML 2026 benchmark for game-development agents in Godot. The camera-ready project contains 333 tasks across 2D graphics/animation, 3D graphics/animation, UI, and gameplay logic. Its repository reports that the best evaluated agent/method solved 63.7% overall in the reported snapshot, with materially lower performance on graphics-heavy work. The authors show that image/video feedback can improve task success; one reported GPT-5.4 configuration increased from 41.1% to 52.0% with visual feedback.

- Official project and task suite: https://github.com/waynchi/gamedevbench
- Project paper page: https://sethkarten.ai/papers/gamedevbench.html

An earlier 132-task description is not the same benchmark snapshot as the 333-task camera-ready release. STAR must pin the exact upstream commit, task manifest, engine version, and grader version before comparing scores.

**OpenGameEval** is the complementary Roblox Studio-native evaluation framework. Its current paper/repository describes 84 human-curated core tasks, 13 evaluated models, and 16 attempts per task, with executable checks on both edited scenes and simulated play sessions. Observation tools are separated from edit tools so exploration can be measured. The paper reports that inspecting all relevant objects before acting correlates with better success: +13.4 percentage points on scene-only tasks and +9.8 points on script-only tasks in the reported comparison.

- Official repository: https://github.com/Roblox/open-game-eval
- Paper: https://arxiv.org/abs/2610.02563

**STAR decision**

A creator agent must use this loop:

`Inspect → Plan → Edit → Run → Observe → Compare → Repair → Verify`

It must capture both structured engine state and visual evidence. Compilation alone does not prove that a game works. A Roblox scene change, a client/server interaction, an animation, and a visual UI task need different validators.

Keep GameDevBench/Godot and OpenGameEval/Roblox scores separate. They measure related but non-identical capabilities.

### 2.3 Full-duplex conversation: turn-taking is more than silence detection

**Full-Duplex-Bench v3** evaluates streaming speech agents with human-recorded requests, disfluencies, chained tool calls, response latency, and turn-taking. Its published scope is 100 requests across 79 scenarios and 12 speakers in four domains. This is a better model for STAR's real stream than measuring only offline transcription accuracy.

- Benchmark: https://www.full-duplex.ai/benchmarks/fdb-v3
- Official code: https://github.com/DanielLin94144/Full-Duplex-Bench

**MP-Bench** evaluates multi-party voice interaction rather than ordinary two-person conversation. Its benchmark page reports that evaluated realtime agents remain at or below 22% on multi-party comprehension and near chance on turn-taking. This demonstrates that recognizing words or assigning speaker IDs does not solve the social-floor problem.

- Benchmark: https://www.full-duplex.ai/benchmarks/mp-bench

**Realtime-Venus** demonstrates a useful architectural pattern: a low-latency interaction path continues listening while the assistant speaks, while longer tasks are delegated asynchronously. It also evaluates audio-visual understanding and whether the agent continues through non-interrupting backchannels or background speech.

- Project and technical report: https://realtime-venus.github.io/

**STAR decision**

Separate these signals in the host:

- voice activity: is speech present?
- transcript stability: which words are committed?
- semantic completion: has the thought ended?
- speaker attribution: which session-local acoustic source spoke?
- addressee: STAR, another participant, the group, or unclear?
- response intent: is a reply expected?
- floor control: speak, backchannel, listen, queue, interrupt, or remain silent?
- playback state: thinking, queued, submitted, started, played, interrupted, or failed.

A diarization label is not a person's identity and is not proof that the speaker addressed STAR. A transcript is content, not permission to invoke a tool. A generated response is not proof that it was audible.

### 2.4 Avatar and broadcast APIs: use official local transports and explicit consent

**VTube Studio's official API** exposes a local WebSocket interface (default port 8001), authentication, explicit user permission, events, hotkeys, Live2D parameters, and item/model operations. Event subscriptions are preferable to high-frequency polling where an event is available.

- Official API development page: https://github.com/DenchiSoft/VTubeStudio

**OBS WebSocket** is included in OBS Studio 28 and later. The official project recommends password protection. Its v5 protocol uses a WebSocket handshake, authentication, requests, responses, and events; STAR should use events for state changes and query only when necessary.

- Official project: https://github.com/obsproject/obs-websocket
- Protocol: https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md

**NVIDIA Audio2Face-3D** can generate 3D facial performance and blendshape/mesh-driving output from audio. It is a candidate for a separate 3D-avatar route, not a drop-in replacement for STAR's existing Live2D/VTube Studio path.

- Official repository: https://github.com/NVIDIA/Audio2Face-3D

**STAR decision**

- Keep VTube Studio and OBS endpoints loopback-only by default.
- Store API tokens/passwords in the OS credential store, never in source, logs, prompts, or model-visible configuration.
- Require the user to approve VTube Studio plugin access and each sensitive permission class.
- Do not expose OBS WebSocket or VTube Studio API ports to the LAN or public internet.
- Treat reconnects, model changes, scene changes, and API revocation as explicit state transitions.
- Tie mouth motion to audio actually played, not text merely generated.
- Keep Live2D and 3D facial-animation adapters separate behind one avatar-intent contract.

---

## 3. Target architecture: one intelligence, two loops, one event spine

### 3.1 Host-owned event envelope

Every event crossing a subsystem boundary should carry:

| Field | Purpose |
|---|---|
| `event_id` | Globally unique event identity within the host's bounded event namespace |
| `session_epoch` | Invalidates stale events after reconnect, call restart, or stream reset |
| `sequence` | Monotonic sequence within the source/session |
| `captured_monotonic_ns` | Source capture time on the host's monotonic clock, where available |
| `received_monotonic_ns` | Host receipt time |
| `source` | Microphone, chat, game, tool, TTS, avatar, OBS, or background worker |
| `trust_class` | Trusted host metadata vs untrusted content |
| `payload_ref` | Bounded reference to content held in its appropriate store |
| `expires_at_monotonic_ns` | Freshness/deadline boundary |
| `correlation_id` | Links one user turn/task to its derived work |

Do not compare timestamps from different machines or clock domains without a measured offset and uncertainty. Wall-clock time is for display and audit; monotonic time is for deadlines, freshness, and ordering.

### 3.2 Foreground loop — keep the stream alive

`Capture → VAD → Incremental ASR → Turn/Intent/Floor Director → Fast Reasoning → Streaming TTS → Playback Acknowledgement → Avatar Update`

Requirements:
- bounded audio and event queues;
- explicit partial vs committed transcript events;
- cancellation bound to exact session and generation IDs;
- no stale audio or transcript can enter a later turn;
- first-audio and first-audible are distinct measurements;
- playback acknowledgements advance the conversation history only for audio actually played;
- a human interruption or exact human resolution can stop the active generation;
- backchannels can update avatar/listening state without forcing spoken commentary.

### 3.3 Background loop — deepen capability without blocking the stream

Background work includes:
- research and source verification;
- memory consolidation proposals;
- skill extraction and held-out evaluation;
- game practice and replay analysis;
- game building, asset creation, and test execution;
- long-form general-knowledge research;
- project maintenance and reports.

Background tasks must have:
- explicit task IDs and generations;
- bounded checkpoints;
- deadlines and cancellation;
- resource leases;
- artifact/evidence references;
- host-confirmed process termination before a lease is released;
- a resumable state that survives process restart.

The foreground loop may preempt or defer background work. Background work must never silently consume the reserve needed for speech, game control, or avatar output.

### 3.4 One resource authority

Use the existing #1140/#1142 lease-based scheduler and pressure governor as the intended single path. The host owns actual resource observations and worker lifecycle; the model may request a workload but cannot invent free RAM/VRAM or release its own lease.

The supervisor should account for:
- CPU capacity and contention;
- available RAM and committed memory;
- GPU VRAM and renderer headroom;
- model context/KV-cache footprint;
- audio callback/queue health;
- game frame-time p95/p99;
- OBS skipped frames and output state;
- TTS/ASR worker memory;
- background worker count and cancellation latency.

A model's declared resource estimate is a hint, not a measurement. Admission must use trusted host telemetry and conservative margins.

---

## 4. Intelligence design: route by capability, verify by evidence

### 4.1 Capability-aware model routing

Do not select a model only by parameter count or a general leaderboard rank.

Define capability classes:
- fast conversation and simple factual answers;
- complex reasoning and planning;
- code/Luau and tool use;
- vision and screenshot understanding;
- audio transcription and speech understanding;
- game-state planning;
- creative asset and game design;
- long-context research and synthesis.

For each candidate, pin:
- model identifier and exact weight hash;
- quantization;
- backend/build and compiler flags;
- context length;
- prompt/template hash;
- tool schema/version;
- sampling configuration;
- host hardware/driver;
- warm-up and cache state.

Use the smallest model that reliably meets the task's quality gate. Escalate to a stronger reasoning path only when uncertainty, task complexity, or verifier failure justifies it. Keep stable system/policy prefixes cache-friendly.

### 4.2 Test-time compute should be selective

Use best-of-N or multi-agent review only for tasks where independent candidates can be checked. Parallel generation without independent verification simply multiplies cost.

A good pattern is:
1. generate a small candidate set;
2. run deterministic/static checks;
3. run the candidate in an isolated environment;
4. compare output against a task-specific verifier;
5. use a stronger model only to diagnose unresolved failures;
6. return the best verified result, not the most persuasive explanation.

For routine chat, use the fast path. For code edits, security-sensitive changes, and game creation, spend more compute on testing and repair.

### 4.3 General knowledge should be evidence-grounded

For open-book questions:
- retrieve primary sources first;
- store source URL, publication date, retrieval date, and relevant excerpt digest;
- identify conflicting sources;
- distinguish fact, inference, and uncertainty;
- cite claims that depend on external research;
- mark facts that can become stale.

For closed-book skill checks, hide retrieval and test recall separately. A high open-book score does not prove retained knowledge.

STAR's general-knowledge domains should include science, mathematics, history, geography, literature, computing, game design, art, audio, video, and practical reasoning. Use separate task sets so a strong coding score cannot conceal weak science or factual calibration.

---

## 5. Gamer Brain: learn mechanics, not just imitate button sequences

Use a two-timescale controller.

### Fast controller
- movement and camera;
- aim and dodge;
- jump and interaction timing;
- immediate threat response;
- cooldown and resource checks;
- safe, rate-limited input dispatch.

### Strategic planner
- objective selection;
- map understanding;
- route planning;
- combat and resource strategy;
- adaptation after failure;
- mission progression;
- deciding when to practice, ask for help, or change strategy.

The strategic model should issue compact goals and constraints. A bounded reactive controller handles the high-frequency actions.

### Learning loop

1. Observe a consented game environment.
2. Build a state estimate from game telemetry and visual observations.
3. Identify legal available actions.
4. Form a testable mechanic hypothesis.
5. Run a bounded experiment in a safe environment.
6. Measure the game-state outcome, not the model's self-report.
7. Compare against a baseline strategy.
8. Save a candidate skill with preconditions, action sequence, expected state transition, failure cases, and evidence.
9. Test on a different map/seed/scenario.
10. Promote only if the skill transfers and does not regress unrelated tasks.

### Gaming acceptance metrics

- objective completion rate;
- progress per minute;
- deaths/failures per task;
- action efficiency;
- route quality;
- recovery after unexpected events;
- performance on held-out maps/seeds;
- input-to-observation latency;
- game frame-time p50/p95/p99;
- CPU/GPU contention during voice and OBS activity.

Do not treat a lucky win, replayed result, or model-generated success narrative as proof of mastery. Do not automate cheating, harassment, purchases, or actions against other players without explicit owner authorization.

---

## 6. Creator Brain: build games through observable iteration

The creator system should unify Roblox, Godot, Unity, Blender, UI, animation, VFX, audio, and level design behind engine-specific adapters.

### Required workflow

1. Inspect the current project and identify relevant files/objects.
2. Produce a concise plan and expected changes.
3. Edit in an isolated worktree or test place.
4. Run formatters, static analyzers, and API checks.
5. Launch the engine in a controlled test environment.
6. Capture structured state plus screenshots/video.
7. Compare the result to task acceptance criteria.
8. Repair failures and rerun the affected tests.
9. Run regression tests for existing behavior.
10. Save an evidence-linked project checkpoint.

For Roblox, preserve server/client trust boundaries, DataModel context, remote validation, and actual multiplayer test behavior. For Godot, include image/video feedback because graphics and animation tasks cannot be fully graded by source-code inspection.

### Creator acceptance metrics

- exact requirement coverage;
- compile/import success;
- scene and object assertions;
- runtime/playtest success;
- client/server behavior;
- visual similarity or human visual review;
- animation timing and rig correctness;
- frame-time and memory cost;
- regression rate;
- repair iterations and total wall time.

A feature is not finished because its script exists. It is finished when the intended behavior is demonstrated in the target engine.

---

## 7. VTuber Social Director: natural presence without fabricated humanity

The goal is a coherent, expressive AI character that feels attentive and socially aware while remaining transparent about being an AI.

### Conversation behavior

- respond to direct questions without monopolizing the stream;
- recognize when viewers are talking to each other;
- use short, context-appropriate backchannels;
- remain quiet when a response is unnecessary;
- handle self-corrections and unfinished thoughts;
- stop when a human has already resolved the exact question;
- vary openings and avoid repeating catchphrases;
- preserve a stable personality across long sessions;
- use humor and excitement proportionate to what actually happened;
- avoid fabricated human biography, memories, or sensory claims.

### Avatar behavior

Map host-confirmed states to expressive avatar intents:
- listening;
- thinking;
- speaking;
- amused;
- surprised;
- excited;
- disappointed;
- focused on gameplay;
- quiet/idle;
- interrupted or reconnecting.

The avatar controller should consume playback and stream events, not raw model prose. Use latest-wins coalescing only for replaceable visual samples. Do not coalesce speech, task completions, or state transitions.

### Long-session naturalness evaluation

Run multi-hour rehearsals with:
- direct viewer questions;
- viewer-to-viewer conversations;
- overlap and background speech;
- backchannels;
- silence;
- self-corrections;
- repeated questions;
- game events;
- interruption/resolution;
- reconnects;
- long gaps between topics.

Human reviewers should rate relevance, timing, warmth, variety, interruption quality, listening behavior, and consistency. Do not optimize for constant speech volume or engagement at any cost.

---

## 8. Speed and stability: optimize the complete workload

A local model's isolated tokens/second is not the user's experience.

Measure the whole system under a matched workload:

| Stage | Measurement |
|---|---|
| Audio capture | capture-to-host receipt and queue age |
| ASR | partial/final latency, real-time factor, WER on consented test audio |
| Turn detection | endpoint delay, false cutoff, missed final turn |
| Social floor | addressee accuracy, response precision/recall |
| LLM | time-to-first-token, inter-token latency, tokens/sec |
| TTS | first audio latency, real-time factor, chunk gap |
| Playback | queued vs started vs actually played time |
| Avatar | audio-to-mouth skew, stale frame drops |
| OBS | output state, skipped frames, reconnect events |
| Game | input latency, frame-time p95/p99, task success |
| Host | CPU, RAM, VRAM, GPU utilization, worker lifecycle |

### Inference optimization rules

- Prefix/KV caching primarily saves repeated prefill; it does not automatically accelerate decode.
- Speculative decoding is useful only when draft overhead is offset by accepted tokens on the exact target model/backend.
- CPU/RAM offload may prevent out-of-memory failures but can slow generation through transfer and memory-bandwidth costs.
- Quantization must be evaluated for both speed and task quality.
- A fast small model can handle routine turns; deep reasoning should be reserved for tasks that need it.
- Keep context windows compact through task-adaptive retrieval and explicit memory summaries rather than continually replaying the entire history.

### Required paired experiment

For each candidate:
1. Pin the exact model, backend, prompt, tools, and hardware.
2. Warm up both baseline and candidate equally.
3. Randomize paired trial order.
4. Run the same task roster and workload mix.
5. Record first-content, first-audible, inter-token, full-turn, game frame-time, audio underruns, OBS skips, and CPU/RAM/VRAM.
6. Grade task quality independently using deterministic checks or held-out human labels.
7. Report p50/p95, paired deltas, uncertainty, failures, and contaminated trials.
8. Reject speed gains that violate quality or stream-stability guardrails.

No default should change because of a single best run or a paper's hardware-specific headline number.

---

## 9. Memory-to-skill lifecycle

Use separate but connected stores:

| Store | Contents | Retention rule |
|---|---|---|
| Episodic | What happened in a task/session | Short-lived unless useful evidence is retained |
| Semantic | Verified facts and relationships | Provenance, timestamp, contradiction handling |
| Procedural | Reusable workflows and skills | Preconditions, version, tests, evidence |
| Temporal | How facts and project state changed | Append-only history with explicit supersession |
| Task ledger | Current objective, checkpoint, owner, lease, result | Durable until terminal state and retention policy |
| Evidence ledger | Test logs, source references, artifact digests | Immutable references; revalidate before reuse |

A memory proposal should record:
- source and provenance;
- confidence and uncertainty;
- creation/update time;
- scope and expiry;
- contradictions;
- evidence references;
- candidate vs approved state;
- rollback/supersession relation.

Memory consolidation must be reversible. Never silently convert a model inference into an owner preference, a permission, or a permanent fact.

---

## 10. Release and safety gates

A capability is eligible for an opt-in pilot only when:

- unit and integration tests pass;
- exact-head CI passes;
- the host adapter has been tested with fake and real transports;
- failure, timeout, cancellation, reconnect, and stale-event paths are covered;
- paired evaluation shows no unacceptable quality or stream-stability regression;
- model/data/provider licensing is reviewed;
- secrets are held outside the repository;
- privacy and retention behavior is documented;
- owner approval is obtained for external actions and default changes.

Keep these categories separate in status reports:

1. **Research documented**
2. **Prototype implemented**
3. **Unit tests passed**
4. **GitHub CI passed**
5. **Local hardware tested**
6. **Integrated rehearsal passed**
7. **Opt-in pilot released**
8. **Default production capability**

Never collapse these into a single "done" label.

---

## 11. Prioritized implementation sequence

### P0 — Integrate existing foundations
- Resolve dependency order for the event timeline, stream host, task/communication ledger, resource admission, and pressure governor.
- Keep one event epoch/clock and one resource supervisor.
- Review PRs as dependency trains; do not merge a child before its parent contracts.
- Establish a single status dashboard showing draft, CI, hardware, rehearsal, and release state.

### P1 — Complete the live interaction path
- Integrate incremental ASR behind the existing adapter contract.
- Keep partial transcripts provisional and non-authoritative.
- Connect semantic endpointing and multiparty floor evidence.
- Connect streamed TTS to actual playback acknowledgements.
- Synchronize avatar frames to audible playback.
- Verify OBS/VTube Studio reconnect and permission-revocation behavior.

### P2 — Prove mixed-load performance
- Rehearse voice + game + OBS + avatar + background task on the target Windows machine.
- Calibrate trusted CPU/RAM/VRAM resource vectors.
- Tune queue sizes, priorities, and model routing from measurements.
- Record frame-time p99, audio underruns, OBS skipped frames, and first-audible latency.

### P3 — Prove learning and creation
- Run controlled dependent/independent/revision task streams.
- Evaluate Roblox with OpenGameEval and STAR's own task suite.
- Evaluate Godot with a pinned GameDevBench roster.
- Promote skills only after external verification and held-out transfer.
- Keep memory utility and memory governance as separate gates.

### P4 — Expand general knowledge and hobbies
- Add domain-specific practice/evaluation packs for science, math, history, geography, art, audio, video, and game design.
- Track factual calibration and source freshness.
- Support creative projects, drawing, music/audio workflows, and learning new tools.
- Let STAR propose interests and projects, but keep external side effects behind host permissions.

---

## 12. Source register

The following primary sources informed this blueprint. Benchmark claims are tied to the source's stated version and evaluation protocol; they are not STAR performance claims.

1. **AGENTCL — continual learning in language agents**: https://arxiv.org/abs/2606.02461
2. **SkillLearnBench — continual agent-skill generation**: https://arxiv.org/abs/2604.20087
3. **SkillLearnBench official code**: https://github.com/cxcscmu/SkillLearnBench
4. **GameDevBench — official 333-task project**: https://github.com/waynchi/gamedevbench
5. **GameDevBench paper/project page**: https://sethkarten.ai/papers/gamedevbench.html
6. **OpenGameEval — official Roblox Studio benchmark**: https://github.com/Roblox/open-game-eval
7. **OpenGameEval paper**: https://arxiv.org/abs/2610.02563
8. **Full-Duplex-Bench v3**: https://www.full-duplex.ai/benchmarks/fdb-v3
9. **Full-Duplex-Bench official implementation**: https://github.com/DanielLin94144/Full-Duplex-Bench
10. **MP-Bench — multiparty voice interaction**: https://www.full-duplex.ai/benchmarks/mp-bench
11. **Realtime-Venus — full-duplex audio/visual interaction and delegation**: https://realtime-venus.github.io/
12. **VTube Studio official API**: https://github.com/DenchiSoft/VTubeStudio
13. **OBS WebSocket official project**: https://github.com/obsproject/obs-websocket
14. **OBS WebSocket v5 protocol**: https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md
15. **NVIDIA Audio2Face-3D official repository**: https://github.com/NVIDIA/Audio2Face-3D
16. **Roblox Studio agentic workflows**: https://about.roblox.com/en-nz/newsroom/2026/04/roblox-studio-going-agentic

---

## Explicit limits of this research pass

- This is an integration blueprint and research handoff, not a claim that the listed capabilities are all implemented.
- No model weights, benchmark datasets, ASR/TTS providers, OBS/VTube Studio credentials, or external service accounts were installed or enabled.
- No private audio, viewer data, game telemetry, or owner project data was collected.
- No live stream, microphone, RTX 4060, Roblox Studio, Godot, OBS, or VTube Studio hardware rehearsal was performed.
- The open draft PRs cited above remain unmerged unless their live GitHub status changes.
- The shared source catalog was left untouched to avoid overwriting concurrent draft updates; this document contains its own source register.
- No measured speedup, intelligence gain, human-equivalence, game mastery, or production readiness is claimed.

**Bottom line:** STAR should become one coordinated, evidence-driven intelligence with a responsive foreground presence and a persistent background learning/creation loop. The path to a more natural streamer and a more capable gamer is a unified event spine, reliable resource admission, incremental perception, playback-aware expression, verifiable skills, and paired quality/speed evaluation—not simply more models running at once.
