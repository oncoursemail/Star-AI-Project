# STAR Run 35 — Multiparty Social Intelligence, Active Memory Routing, and Deadline-Aware Runtime

**Research date:** 2026-11-14 (America/Chicago)  
**Repository:** `oncoursemail/Star-AI-Project`  
**Research branch:** `research/star-run24-integration-blueprint-20261114`  
**Scope:** real multi-party streaming, active use of long-term memory, inference scheduling, Gamer Brain, Creator Brain, and cross-system acceptance.

---

## Executive decision

STAR's next meaningful intelligence improvement is not another persona prompt, another swarm of agents, or a larger model loaded beside the existing one. It is the ability to **select the right context, take the right turn, meet the right deadline, and verify that an action actually accomplished its purpose**.

Run 35 makes five architecture decisions:

1. **Treat a livestream as a multi-party social environment, not a sequence of private dyadic chats.** Model who is speaking, who is being addressed, what topic is active, who currently has the floor, and whether STAR has a useful reason to enter.
2. **Measure memory by whether it improves actions, not only whether STAR can repeat remembered facts.** Route among the existing task ledger, episodic history, procedural skills, and factual knowledge. Do not create a second memory authority.
3. **Schedule by deadline and user-visible impact.** Voice playback, turn decisions, direct owner controls, and current game actions must not wait behind research, embeddings, asset generation, or long prompt prefill.
4. **Use evidence-backed skills and claim-level knowledge.** Successful behavior is a candidate until independently verified; failures and contradictions must be retained as learning evidence.
5. **Prove combined behavior under mixed load.** A fast isolated model is not a faster streamer if OBS, audio callbacks, gameplay, or memory retrieval become unstable.

This document is a research and integration plan. It does not install models, change production routing, create credentials, or enable public streaming.

---

## 1. Repository audit and integration boundaries

The current development train contains three relevant draft PRs:

| PR | Purpose | Integration rule |
|---|---|---|
| #1180 | Research Runs 24–34 | Extend the existing source-linked architecture blueprint. |
| #1181 | Audio callback isolation and DAC playback evidence | Preserve the existing playback clock and speaker meter; do not add another audio clock. |
| #1182 | Fail-closed screen-to-action gate and Game Lab catalog | Extend the existing catalog and exact-observation permit policy. |

The production baseline remains separate from these draft branches. CI on a documentation-only PR does not validate runtime code, and CI on a pure Python gate does not prove DXGI, physical input, a GPU model, OBS, or VTube Studio works on the target Windows machine.

The existing Creator Studio acceptance issue is #584. Its acceptance list already covers original art and rig QA, licensed voice, real PCM-driven animation, owner-authorized read-only platform chat, actual screen-to-controller gameplay, verified held-out game improvement, non-destructive video editing, power-loss recovery, and a private rehearsal before any public stream.

**Do not duplicate existing authorities:**

- RoomStreamHost / RoomTurnDirector remain the audience and conversational-turn authority.
- The durable task/communication ledger remains the authority for unfinished work and delivery obligations.
- The existing resource-admission controller remains the only CPU/GPU admission authority.
- PlaybackSnapshot remains the local PortAudio playback evidence source; it is not proof of acoustic or remote-viewer playback.
- GameControlGate remains the action-permit authority; this document does not add another input policy.
- The existing governed memory-consolidation path remains the authority for persistent memory promotion.

---

## 2. New finding: multi-party conversation is a different problem

### MP-Bench

The 2026 Findings of EMNLP paper introduces MP-Bench, an evaluation of voice agents as active participants in group conversation. It measures turn-taking awareness and response appropriateness, with comprehension questions as a complementary task.

The authors evaluated 12 voice agents and report that real-time agents stayed at or below 22% on multi-party comprehension and performed near chance on multi-party turn-taking in their benchmark.

Source:
- https://aclanthology.org/2026.findings-emnlp.1437/
- https://arxiv.org/abs/2609.13076

### Why this matters for STAR

A Twitch or YouTube stream is not simply a queue of independent messages. Viewers reply to each other, joke with each other, answer questions before STAR does, change topic, mention a co-host, and sometimes address nobody in particular.

A system that answers every message will feel less natural, not more natural. A system that only detects STAR's username will miss context and interrupt conversations that do not need her.

### Repository-specific gap found during this run

I inspected the actual `star/voice/room.py` and `star/voice/room_host.py` implementation on the current #1178 development branch. The existing `RoomCue` already carries an opaque `speaker_id`, a boolean `addressed_to_star`, intent, confidence, timing, overlap, and event-resolution metadata. This is a useful privacy-minimizing baseline, but it does not yet preserve a distinct addressee ID, reply-to event link, or topic/thread ID. Consequently, the deterministic director can distinguish a direct-to-STAR cue from a side conversation, but it cannot itself reconstruct a multi-person reply graph or topic continuity.

**Recommended additive contract:** introduce optional, bounded, session-scoped `addressee_id`, `reply_to_event_id`, and `topic_id` metadata in the trusted adapter/cue boundary, plus a small TTL- and capacity-bounded metadata-only conversation index. Keep `addressed_to_star` as a derived, validated convenience flag for the current decision path; do not let raw chat text or an untrusted viewer choose tool permissions. The index should retain opaque IDs and event relationships only, expire on session reset, and never merge identities across Twitch, YouTube, Discord, or real-world accounts. Add tests for replies to another viewer, replies to STAR, missing/expired parent events, cycles, duplicate IDs, bounded eviction, topic changes, and session reset before wiring it into response-context selection.

This is a newly identified implementation gap, not a completed code change in #1178. The current room director remains the sole floor/interrupt policy authority until a reviewed additive change is accepted.

### Proposed multi-party social state

Reuse the existing RoomTurnDirector and represent the following as short-lived, session-scoped state:

- **Speaker:** current source-scoped pseudonym and confidence; never infer a real-world identity.
- **Addressee:** STAR, another viewer, a co-host, the whole group, or unknown.
- **Topic:** current conversational thread and recent topic transitions.
- **Floor:** who currently has the conversational floor; whether it is held, yielded, or open.
- **Intent:** question, answer, joke, correction, invitation, reaction, command-like text, or unclear.
- **Relevance:** whether STAR has unique information or a useful action to contribute.
- **Moderation:** visible, held, deleted, timed out, or unknown. Anything not approved for display must not be spoken.
- **Delivery:** queued, selected, speaking, interrupted, delivered, or expired.

Do not use a single confidence score for all these dimensions. Addressee confidence, transcription confidence, topic confidence, and moderation state have different meanings and different failure costs.

### Turn-selection policy

Before speaking, the director should answer:

1. Was STAR explicitly addressed?
2. Is the message a reply to STAR or to another viewer?
3. Has another participant already answered?
4. Is the topic still active?
5. Would speaking interrupt someone who currently has the floor?
6. Is the information useful, accurate, and within STAR's permissions?
7. Is the answer still timely?
8. Is silence the better action?

The output should be one of: `SPEAK`, `SHORT_ACK`, `QUEUE`, `WAIT`, `YIELD`, `RESUME_TASK`, or `IGNORE`. A decision to wait or ignore should be logged as a policy outcome, not treated as a model failure.

### Human-presence behavior

The goal is a believable AI streamer with a stable character, not a system pretending to be a human. Natural presence comes from:

- Not responding to every line.
- Letting viewers talk to one another.
- Using short backchannels only when they do not steal the floor.
- Remembering the topic and returning to an unfinished answer at a natural point.
- Showing focused gameplay attention during difficult moments.
- Reacting to verified game events rather than hallucinated events.
- Laughing only when the context supports it; no forced laugh loop.
- Distinguishing uncertainty from confidence.
- Maintaining consistent preferences and style without fabricating human memories or biography.

---

## 3. New finding: test whether memory changes the action

### Mem2ActBench

Mem2ActBench evaluates whether an agent actively applies long-term conversational memory to tool selection and parameter grounding. Its authors describe 2,029 synthesized sessions and 400 memory-dependent tool-use tasks; human evaluation found 91.3% of the tasks strongly depended on memory.

Sources:
- https://aclanthology.org/2026.acl-long.370/
- https://arxiv.org/abs/2601.19935
- https://github.com/Cantaloupe-M/Mem2ActBench

The key distinction is between:

- **Passive recall:** STAR can answer “what preference did the user mention?”
- **Active use:** STAR silently applies the relevant preference, project state, constraint, or prior decision to the correct tool arguments and execution plan.

STAR needs the second capability.

### Heterogeneous memory routing

Two further research directions support routing rather than one universal memory substrate:

- **MemAgent** studies task-aware routing among heterogeneous memory providers. Its preprint reports that no single memory method generalizes across all evaluated tasks and proposes content-aware probing, short-term memory gating, and selective storage. https://arxiv.org/abs/2609.32521
- **Harness the Memory** compares multiple memory substrates under a common evaluation harness. It reports that no substrate consistently dominates and that excessive retrieval can distract sequential decision-making. https://arxiv.org/abs/2608.15008

### STAR memory router

Route to the smallest useful memory source:

| Memory class | Use | Existing authority |
|---|---|---|
| Current conversational state | Recent speakers, topic, active floor, current request | Room/session state |
| Task and delivery state | Running, blocked, completed, still owed, communicated | Existing task/communication ledger |
| Episodic memory | What happened in a past project/session and its outcome | Existing governed memory path |
| Procedural skills | Verified steps for Roblox, games, Blender, OBS, coding, etc. | Existing skill system |
| Semantic knowledge | Facts, docs, API behavior, dates, provenance, contradictions | Existing knowledge/retrieval path |

A query should first classify the task and identify required parameters, then retrieve only the relevant memory class. Avoid injecting the entire user history into every prompt.

### Conflict and revision policy

Every persistent memory item should preserve:

- Stable identifier.
- Claim or preference.
- Source and evidence.
- Scope (project, session, platform, or global).
- Valid-time range and recorded-time range.
- Confidence and verification state.
- Supersedes / contradicted-by links.
- Privacy classification.
- Last revalidation date.

A newer preference may supersede an older one within a specific project without erasing the historical fact that the earlier preference existed. A failed tool action must not silently rewrite the user's preference. If memory is ambiguous, ask or abstain rather than guess.

### Active-memory acceptance

Create synthetic, privacy-safe conversations where the user establishes a constraint, changes topic, interrupts, and later asks for an action that depends on the original constraint. Score:

- Correct memory source selected.
- Correct tool selected.
- Correct parameter grounding.
- Correct handling of changed or superseded constraints.
- Correct task/delivery state.
- Unnecessary memory retrieval.
- Incorrect cross-project memory leakage.
- Latency and token cost added by retrieval.

Use Mem2ActBench as a reference only after reviewing its license, task format, and evaluation protocol. Do not copy private conversations into a public benchmark.

---

## 4. Faster intelligence: deadline-aware scheduling, not indiscriminate parallelism

### vLLM disaggregated prefill research

The vLLM documentation describes experimental disaggregated prefill, where prompt prefill and token decode run in separate instances. The stated motivation is to tune time-to-first-token (TTFT) and inter-token latency separately and control tail inter-token latency.

Source:
- https://docs.vllm.ai/en/v0.20.0/features/disagg_prefill/

This is a useful architecture reference for a future multi-machine deployment. It is **not** a recommendation to install vLLM disaggregated serving on STAR's local 8 GB GPU. It adds distributed infrastructure and KV-cache transfer complexity, and the feature is explicitly experimental.

### STAR's two-level execution contract

Reuse the existing resource-admission authority and split work by deadline:

**Foreground, deadline-sensitive**
- Audio callback and PCM output.
- Current ASR partials and turn-state updates.
- Direct owner mute/stop/manual override.
- Active conversation response.
- Current game-control observation and permit.
- Avatar parameters required for current playback.
- Local stream-health events.

**Background, interruptible**
- Web research.
- Embedding and index maintenance.
- Large code generation.
- Asset and video generation.
- Game-world exploration.
- Long-running game tests.
- Skill consolidation and memory compaction.
- Non-urgent analytics.

### Scheduling rules

- Use deadline and queue age, not only FIFO order.
- Reserve a bounded foreground capacity before admitting background work.
- Cancel or expire work whose deadline has passed; do not replay stale viewer questions or stale game actions.
- Coalesce replaceable state (latest avatar pose, latest screenshot, current telemetry sample).
- Never coalesce non-replaceable events (owner stop, moderation tombstone, task completion, tool side-effect result).
- Require explicit acknowledgement that a worker has stopped before releasing its resource lease.
- Apply per-class queue caps and backpressure.
- Keep one model warm where practical rather than thrashing VRAM through repeated unload/reload.
- Use CPU ASR only if paired mixed-load tests show that it reduces GPU pressure without starving the CPU and game render thread.
- Benchmark speculative decoding by accepted draft tokens and end-to-end latency, not by a paper's advertised multiplier.

### Required speed measurements

For each user-visible interaction, record:

- Queue wait.
- Prompt prefill duration and throughput.
- Time to first token.
- Decode inter-token p50/p95/p99.
- Cancellation-to-stop latency.
- First ASR partial.
- Final transcript commit time.
- First TTS chunk.
- First PCM callback with non-empty audio.
- Estimated DAC playback time.
- Avatar frame age at playback.
- CPU/GPU/RAM/VRAM/thermal state.
- Game FPS p10/p50 and frame-time spikes.
- OBS render and encode lag.

Do not record prompts, transcripts, raw audio, viewer messages, secrets, or private file contents in ordinary telemetry. OpenTelemetry's GenAI agent span conventions are marked Development; pin the exact schema revision before instrumenting production.

Sources:
- https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md
- https://opentelemetry.io/docs/concepts/semantic-conventions/

---

## 5. Gamer Brain: transfer skills, not memorized button sequences

STAR's gaming ability should be measured as a learning curve and transfer ability.

### Skill representation

Each candidate game skill should contain:

- Game title/version and permitted environment.
- Objective and success verifier.
- Preconditions and game mode.
- Observation features used.
- Action policy and action duration.
- Expected effect.
- Failure modes.
- Recovery policy.
- Trials, successes, failures, and manual interventions.
- Held-out map/seed results.
- Last validation date.

### Learning cycle

1. Observe the current game and identify the objective.
2. Establish a baseline with a fixed number of attempts.
3. Form a small hypothesis about a mechanic or strategy.
4. Test one controlled change.
5. Verify the result from game state, score, objective completion, or an independent harness.
6. Save the trial as evidence, not as a permanent skill.
7. Test on a different map, seed, or scenario.
8. Promote only if held-out performance improves.
9. Revalidate after game updates or repeated failures.

### Live streaming constraints

The live game loop must not wait for a long research task. Use a fast perception/control path for current actions and a strategic planner for larger objectives. Keep action permits bound to the exact observation and expire them when the source observation is too old, evicted, or from a different capture epoch.

Start with owner-approved offline/sandbox games and games whose rules permit automation. Do not bypass anti-cheat, DRM, access controls, or game/platform restrictions.

---

## 6. Creator Brain: build, test, inspect, and prove

Roblox's official StudioTestService allows plugins to automate Test and Run mode, start server/client multiplayer sessions, add players, pass test arguments, and trigger client disconnections.

Source:
- https://create.roblox.com/docs/reference/engine/classes/StudioTestService
- https://create.roblox.com/docs/studio/mcp
- https://create.roblox.com/docs/studio/testing-modes

Use the built-in Studio MCP server as the preferred bridge. Use StudioTestService for deterministic multi-client cases; a single-client playtest is not proof of multiplayer correctness.

### Creator test matrix

| Dimension | Example cases |
|---|---|
| Server/client count | 1, 2, 4, and supported maximum |
| Network | Normal, delay, loss, disconnect, reconnect |
| Device | Desktop, phone, tablet, controller |
| Session | New player, returning player, party member |
| Game state | Lobby, match start, active match, death, respawn, match end |
| Security | Invalid RemoteEvent arguments, unauthorized client state changes |
| Performance | Increasing players, asset streaming, memory growth, frame time |

For each generated feature:

1. Inspect the current project and establish a clean baseline.
2. Define observable acceptance conditions before editing.
3. Make the smallest coherent change.
4. Run static analysis and engine-native tests.
5. Launch a disposable test session.
6. Capture screenshots and logs.
7. Verify client and server outcomes.
8. Repair the failing case.
9. Re-run the original and at least one held-out scenario.
10. Save the source revision and test evidence.

Do not report a generated game as complete because scripts were written or the project opened successfully.

---

## 7. VTuber stage intelligence: one coherent presence

STAR should have one stage director that consumes verified events from the game, room, playback, avatar, and OBS systems.

### Stage state

- `LISTENING`
- `FOCUSED_GAMEPLAY`
- `THINKING`
- `SPEAKING`
- `REACTING`
- `WAITING_FOR_VIEWER`
- `ANSWERING_QUESTION`
- `CREATING`
- `RECOVERING`
- `OWNER_PAUSED`

Stage state is not an emotion label. It describes what STAR is doing and which behavior budget is appropriate.

### Expression and playback

- The audio playback cursor is authoritative for mouth movement.
- Semantic intent selects expression, gaze, and gesture.
- Use a latest-wins channel for replaceable pose samples.
- Preserve speech start/stop, interruption, owner mute, and task-delivery events.
- If playback telemetry is unavailable, fall back to a conservative animation rather than claiming precise lip sync.
- Smooth and clamp only parameters STAR's approved VTube Studio plugin owns.
- Require user-approved plugin authentication and explicit model parameter mapping.

### OBS

- Localhost/loopback by default.
- Authenticated WebSocket handshake.
- Allowlisted scene, recording, and status operations.
- Owner confirmation for public broadcast start, stream destination, stream-key changes, and account-level actions.
- A desktop restart may restore local services, but must never silently resume a public stream.

Sources:
- https://github.com/DenchiSoft/VTubeStudio
- https://github.com/obsproject/obs-websocket

---

## 8. New evaluation suite for STAR

Build small, deterministic, privacy-safe internal tasks before importing large external datasets.

| Suite | Core question | Required metrics |
|---|---|---|
| Multiparty stream | Does STAR know who is talking to whom and when to speak? | Addressee accuracy, turn-taking, response appropriateness, duplicate-answer rate, false interruption, missed opportunity, appropriate silence |
| Active memory | Does memory improve the action? | Tool choice, parameter accuracy, stale-memory error, retrieval overhead, cross-project leakage |
| Task continuity | Does STAR finish and communicate interrupted work? | Completion rate, delivery rate, duplicate delivery, omission rate, resume latency |
| Inference | Is the complete response faster? | TTFT, ITL p50/p95/p99, first-audio, cancellation latency, resource pressure |
| Gamer Brain | Does she improve on unseen conditions? | Success, progress, held-out transfer, recovery, manual intervention, action age |
| Creator Brain | Does the game actually work? | Static tests, client/server assertions, visual checks, held-out scenarios |
| VTuber mixed load | Can she do all of it at once? | Audio underflows, avatar frame age, game FPS, OBS lag, voice latency, task completion |

Every benchmark result must pin:
- STAR commit.
- Model/provider and model revision.
- Prompt/skill version.
- Hardware and OS.
- Game/engine version.
- Dataset or scenario version.
- Number of trials and confidence interval.
- Foreground/background workload.
- Whether the test was offline, slowed, real-time, or physical.

Do not compare scores from different benchmark versions or different evaluation modes as if they were directly comparable.

---

## 9. Implementation sequence

| Priority | Work | Acceptance evidence |
|---|---|---|
| P0 | Finish exact-head Windows CI for #1181 and #1182 | Both Windows test shards and packaged build pass |
| P0 | Preserve one audio clock and one callback authority | No duplicate meter/playback implementation; hardware-free regressions |
| P1 | Add MP-Bench-inspired synthetic group-conversation harness | Deterministic multi-speaker scenarios and turn-taking report |
| P1 | Add active-memory routing evaluation over existing stores | Memory-dependent tool tasks pass with correct parameter grounding |
| P1 | Add deadline/queue-age metrics to the existing resource scheduler | p95/p99 and cancellation measurements under mixed load |
| P1 | Complete VTube Studio playback-to-parameter adapter | Mouth follows playback; owner mute works during stalled inference |
| P1 | Complete OBS authenticated loopback adapter | Private recording rehearsal; no public stream starts automatically |
| P2 | Complete DXGI capture and permitted input executor | Focus loss, access loss, manual override, and release tests pass |
| P2 | Connect Gamer Brain to outcome verifiers and held-out skill tests | Measured improvement over fixed baseline |
| P2 | Integrate Roblox Studio MCP and StudioTestService | Multi-client and device test matrix with visual evidence |
| P3 | Full private mixed-load rehearsal | Game + ASR + LLM + TTS + avatar + OBS + synthetic chat at once |

---

## 10. Source register

1. MP-Bench, Findings of EMNLP 2026 — https://aclanthology.org/2026.findings-emnlp.1437/
2. MP-Bench preprint — https://arxiv.org/abs/2609.13076
3. Mem2ActBench, ACL 2026 — https://aclanthology.org/2026.acl-long.370/
4. Mem2ActBench code/data landing page — https://github.com/Cantaloupe-M/Mem2ActBench
5. MemAgent — https://arxiv.org/abs/2609.32521
6. Harness the Memory — https://arxiv.org/abs/2608.15008
7. vLLM disaggregated prefill (experimental) — https://docs.vllm.ai/en/v0.20.0/features/disagg_prefill/
8. OpenTelemetry GenAI agent spans (Development status) — https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md
9. OpenTelemetry semantic conventions — https://opentelemetry.io/docs/concepts/semantic-conventions/
10. Roblox StudioTestService — https://create.roblox.com/docs/reference/engine/classes/StudioTestService
11. Roblox Studio MCP — https://create.roblox.com/docs/studio/mcp
12. Roblox Studio testing modes — https://create.roblox.com/docs/studio/testing-modes
13. VTube Studio API — https://github.com/DenchiSoft/VTubeStudio
14. OBS WebSocket — https://github.com/obsproject/obs-websocket
15. Full-Duplex-Bench v3 — https://arxiv.org/abs/2604.04847

---

## Explicit limitations

- MP-Bench, Mem2ActBench, MemAgent, and Harness the Memory results are source-reported research, not STAR measurements.
- The vLLM disaggregated-prefill feature is experimental and is not recommended as the default local 8 GB GPU runtime.
- This document does not install models, download benchmark datasets, create OAuth credentials, or enable any provider.
- No physical Windows audio, GPU, DXGI, game input, Roblox Studio, VTube Studio, OBS, Twitch, YouTube, or public-stream test is claimed.
- No human-equivalence, game mastery, intelligence gain, or speedup is claimed.
- Do not expose prompts, transcripts, audio, viewer messages, private memories, or credentials in telemetry.
- Keep #1180, #1181, and #1182 draft until exact-head CI, dependency review, and the acceptance issue's owner-controlled gates are satisfied.
- Production `main` remains unchanged.
