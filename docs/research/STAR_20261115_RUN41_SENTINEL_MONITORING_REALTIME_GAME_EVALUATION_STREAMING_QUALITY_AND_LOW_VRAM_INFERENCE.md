# STAR Run 41 — Monitoring Intelligence, Real-Time Game Evaluation, Streaming Quality, and Low-VRAM Inference

**Research date:** 2026-11-15  
**Repository:** `oncoursemail/Star-AI-Project`  
**Scope:** long-running monitoring, verifiable game learning, full-duplex VTuber quality, Live2D transport, Roblox plan/build/test, and local inference performance.

---

## Executive decision

Run 41 shifts the next improvement from "add more agents" to **make STAR observe less wastefully, wait intelligently, act only when useful, and prove that the whole task succeeded**.

The repository already has draft foundations for a room director, task ledger, delivery recovery, resource admission, playback clock, game-action gate, active perception, skill retrieval, paired evaluation, and local inference measurement. The highest-value next work is to connect those authorities and evaluate them under real-time load.

Run 41 makes seven decisions:

1. **Waiting is a first-class agent action.** Long-running monitoring should be event-driven and resource-bounded, not a loop of repeated refreshes or model calls.
2. **Game mastery must be state-verified.** Report task success separately from partial progress, and report paused and live real-time tracks separately.
3. **VTuber quality is multi-dimensional.** Task accuracy, turn timing, interruption handling, paralinguistic control, groundedness, and appropriate silence must remain separate metrics.
4. **Avatar updates must follow one clock.** Preserve the existing playback/DAC clock and latest-wins Live2D sender; do not create a second animation scheduler.
5. **Inference tuning starts with measurement.** Pin llama.cpp, match benchmark concurrency to server slots, and test cache/batching/speculation one variable at a time.
6. **Roblox development should be plan/build/test.** Use an editable task manifest, independent tasks for parallel work, and Studio playtests/logs/state checks against the original plan.
7. **Learning remains evidence-gated.** Experience may propose skills and strategies; only independent verification and held-out tests can promote them.

No foundation-model weight update is required for this plan.

## Repository truth and authority map

The public `main` branch is still the local-first STAR v1.0 baseline described in README: Windows desktop, local approximately 4B Vulkan inference, optional CPU STAR Server, Roblox documentation/Studio opt-ins, and a reviewed lesson loop. The README explicitly says the v1.0 lesson bundle is empty and the release comparison did not establish a model-quality improvement. Advanced voice, game control, active perception, conversation threading, and benchmark work remains in draft PRs.

The current development work to preserve includes:

- **#1177** — durable task and communication ledger.
- **#1178** — room host/director, voice/persona and resource-admission integration.
- **#1181** — speaker-meter isolation and DAC playback clock.
- **#1182** — fail-closed screen-to-action GameControlGate.
- **#1184** — bounded ActivePerceptionPolicy.
- **#1185** — session-local ConversationContextIndex.
- **#1166/#1167** — paired variant evaluation and streamed inference measurement.
- **#1140/#1142** — authoritative resource admission and stream-pressure composition.
- **#1117 and the existing promotion path** — governed memory and skill promotion.

These are draft-branch foundations, not shipped production capabilities. No public stream, real game-control session, Windows GPU acceptance, or hardware speedup is claimed.

### One authority per responsibility

| Responsibility | Authority to retain |
|---|---|
| Platform/audio/chat/game event ingress | RoomStreamHost and trusted source adapters |
| Speak / wait / queue / interrupt decisions | RoomTurnDirector |
| Actual audible playback and stop completion | CallSession / trusted playback host |
| Long-running tasks and delivery obligations | TaskCoordination and delivery ledger |
| CPU/RAM/VRAM admission | Existing resource-admission controller and stream governor |
| Game input authorization | GameControlGate |
| Evidence selection | ActivePerceptionPolicy |
| Session-local reply/topic context | ConversationContextIndex |
| Skill and memory promotion | Existing independent evaluation and owner-review gate |
| Performance and quality measurement | Existing trace, inference benchmark and paired evaluator |

Do not add a second room director, playback queue, task database, GPU scheduler, action gate, or general memory store.

---

## 1. SentinelBench — learning when to wait

**Paper:** https://arxiv.org/abs/2606.05342  
**Official environment:** https://github.com/microsoft/sentinel_environments  
**Microsoft Research overview:** https://www.microsoft.com/en-us/research/articles/sentinelbench-a-benchmark-for-long-running-monitoring-agents/

SentinelBench contains 100 tasks across ten evolving synthetic web applications. It evaluates monitoring behavior where the environment can change independently of the agent. Tasks include passive detection, active monitoring, absolute/relative conditions, and no-operation cases. The benchmark measures task completion, reaction time, and resource use.

The important lesson is that an agent should not keep calling tools simply because it is waiting. It should maintain a bounded watch condition, wait for meaningful state change, re-check the condition, and act only when the condition is actually satisfied. No-op tasks are valuable because they penalize agents that notify or act when nothing happened.

### STAR application

Use the existing TaskCoordination ledger and delivery ledger:

1. Store a structured, owner-authorized watch condition as a task.
2. Record the source adapter, condition predicate, deadline, and cancellation generation.
3. Prefer push/event subscriptions when the source supports them.
4. If polling is unavoidable, use bounded backoff, jitter, and a maximum observation budget.
5. Wake the task only on a new source event, scheduled check, or explicit user request.
6. Re-evaluate the condition against fresh source state.
7. Deliver one verified result; suppress duplicate or stale notifications.
8. Keep the task cancellable and visible to the owner.

Do not create a second scheduler. Do not treat an LLM's statement that a condition is true as evidence. Do not poll private accounts or connected services without the owner's explicit connection and permission.

### New STAR evaluations

- Detection precision and recall.
- Reaction latency after the true condition.
- False notification rate.
- No-op false-action count.
- Tool calls and tokens consumed while waiting.
- CPU/RAM/network use during idle monitoring.
- Cancellation latency and stale-result suppression.
- Recovery after source disconnect/reconnect.

### Feature opportunities

- **Watch mode:** "tell me when this build finishes", "watch CI for a regression", or "notify me when the stream encoder drops frames."
- **Service sentinel:** monitor STAR's own server, local model process, storage, queue depth, and restart state.
- **Game objective watcher:** monitor a verified in-game objective or boss phase without repeatedly asking the reasoning model to inspect unchanged frames.
- **Research watch:** monitor a user-authorized source for a specific new release or paper, then summarize only when a meaningful change appears.

These are proposed capabilities; no account watcher or service monitor is enabled by this research.

---

## 2. GameWorld — prove game progress and task completion

**Project:** https://gameworld-project.github.io/  
**Paper:** https://arxiv.org/abs/2604.07429

GameWorld evaluates multimodal game agents across 34 browser games and 170 tasks in five genres: runner, arcade, platformer, puzzle, and simulation. Its important methodological choice is to read serialized game state for success and normalized progress instead of relying only on screenshots or an LLM judge. The project also distinguishes the normal paused evaluation from GameWorld-RT, where the environment continues running while the agent reasons.

### STAR application

Every gameplay evaluation should record at least:

- Exact game build, task, seed, and environment revision.
- Interface type: screen/control or trusted structured state.
- Paused, slowed, or real-time mode.
- Verified task success (binary).
- Normalized partial progress.
- Invalid/unauthorized action count.
- Action-to-observation freshness.
- Recovery after a failed action.
- Time to first useful action.
- Completion time and resource cost.

**Never combine paused and real-time scores into one headline number.** A strategy that succeeds when the game is frozen may fail when the world continues moving during model inference.

### STAR's game-learning loop

1. Parse the objective and constraints.
2. Identify the game-specific action adapter.
3. Build a short-horizon plan.
4. Observe only when new information is useful.
5. Authorize each action against the exact fresh observation through GameControlGate.
6. Verify state change and task progress.
7. Record a structured success/failure trace.
8. Update a candidate strategy or skill.
9. Test on held-out seeds/maps before promotion.

For visual-only environments, use screenshots and independent observable outcomes. For Roblox Studio, use test-only structured state, server/client assertions, logs, and screenshots where available. A benchmark's state API must not be assumed available in arbitrary retail games.

### Skill transfer tests

- Same objective, new seed.
- Same mechanic, different map.
- Same abstract skill, different game adapter.
- Live-speed evaluation after paused practice.
- Regression tests on previously mastered tasks.
- Human/manual baseline on a small owner-reviewed subset.

This tests whether STAR learned a mechanic rather than memorizing a route or button sequence.

---

## 3. Full-Duplex-Bench v3 and InteractionBench — evaluate a natural VTuber

**Full-Duplex-Bench v3:** https://arxiv.org/abs/2604.04847  
**Benchmark catalogue:** https://www.fullduplex.ai/benchmarks/fdb-v3  
**InteractionBench:** https://avera-labs.github.io/InteractionBench/

Full-Duplex-Bench v3 uses 100 human-recorded spoken requests across 79 scenarios and 12 speakers. It includes natural speech disfluencies and chained mock-API tool calls. It reports task Pass@1, tool-call F1, latency, and turn-taking.

InteractionBench evaluates 13 scenarios and 221 items across seven systems. It separates four dimensions: conversational timing, spoken-task accuracy, paralinguistic control (such as whisper and relative volume), and grounding across long conversations.

These benchmarks expose an important design rule: a system can sound smooth but fail the task, or complete the task but interrupt people unnaturally. One aggregate "human-like" score would hide these failures.

### STAR streaming quality scorecard

Report each dimension independently:

**Conversation**
- Appropriate silence rate.
- False interruption rate.
- Missed direct-request rate.
- Backchannel continuation rate.
- Turn-taking latency.
- Stop latency after a true interruption.
- Resume correctness after a false interruption.

**Task execution**
- Spoken instruction accuracy.
- Tool-call precision/recall.
- Multi-step task completion.
- Result-delivery accuracy.
- Stale or cancelled result suppression.

**Voice and persona**
- Requested whisper/volume compliance.
- Prosody consistency.
- Speech naturalness judged on blind paired samples.
- Repetition and canned-reaction rate.
- Long-conversation groundedness.
- Correctly admitting uncertainty or tool failure.

**Live experience**
- First audible response latency.
- Audio underruns.
- Queue wait.
- OBS render/encoder lag.
- Game FPS impact.
- CPU/RAM/VRAM under combined load.

Appropriate silence is a positive result when STAR is listening, focused on gameplay, or when people are talking to one another. Do not optimize for maximum speech frequency.

### Natural stream behavior

- Recognize when a comment is directed to STAR versus another viewer.
- Avoid answering every side conversation.
- Acknowledge a short backchannel without cancelling a valid response.
- Interrupt only when a high-confidence new request or urgent event warrants it.
- Stop only the exact active response generation.
- Resume the previous task after a false interruption.
- Keep background research and tool execution separate from what STAR has actually said aloud.
- Use a consistent character persona while being transparent that she is an AI.

Keep raw viewer messages/audio out of long-term telemetry by default. Use session-scoped pseudonyms and do not merge identities across Twitch, YouTube, Discord, or voice sources.

---

## 4. VTube Studio — one playback clock and a bounded parameter pump

**Official API:** https://github.com/DenchiSoft/VTubeStudio

The official VTube Studio API supports local WebSocket plugins, Live2D parameter injection, hotkeys, model/item events, and other integrations. Plugin API access must be enabled by the user and authentication approved. Injected parameters must be refreshed at least once per second to remain active; an optional weight can blend injected values with tracking, and only one API plugin can write a parameter at a time.

### STAR integration decision

Reuse the existing playback-clock and latest-wins Live2D frame-pump work:

- The audible playback cursor is authoritative for mouth-open timing.
- A single sender owns API parameter writes.
- Coalesce stale animation updates rather than building a FIFO backlog.
- Refresh controlled parameters at a measured interval below the one-second expiry.
- Do not let face tracking, another plugin, and STAR fight over the same parameter.
- Keep expressions and gestures semantic (laugh, surprised, thinking, focused), not random.
- Reset parameters and clear the pending frame on interruption, session end, or disconnect.
- Keep the API on loopback; do not expose the local WebSocket port to a network.
- Require explicit user enablement and plugin authentication.

### Acceptance

- No mouth motion when no audio is audible.
- Mouth motion follows actual played audio, not generated text.
- Parameter refresh gap p95/p99 remains below the chosen safety margin.
- No stale frame is applied after an interruption or model change.
- Reconnect requires the expected authenticated session.
- Manual tracking and owner controls remain available.

No VTube Studio connection or API authorization was performed by Run 41.

---

## 5. llama.cpp — low-VRAM speed without guessing

**Official server documentation:** https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md  
**Speculative decoding:** https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md  
**SPEED-Bench:** https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench

The current llama-server documentation describes continuous batching, parallel slots, prompt caching, cache reuse, metrics endpoints, and several speculative-decoding families. These are capabilities of the upstream server; exact flags and supported kernels vary by pinned build and backend.

### Recommended experimental order

Do not change production defaults. Establish a baseline, then change one variable at a time:

1. **Baseline:** exact current model, quantization, context, Vulkan build, prompt template, and one request at a time.
2. **Prompt stability:** keep the system prompt and tool schemas stable; move volatile turn data to the end of the prompt.
3. **Prompt cache:** compare cold and warm identical-prefix requests.
4. **Cache reuse:** test the supported cache-reuse setting only with prompt caching enabled.
5. **Continuous batching:** compare one and two slots; keep total context and sample workload explicit.
6. **Speculative decoding:** compare supported n-gram or draft methods; record draft acceptance and actual end-to-end latency.
7. **KV cache types:** test only types supported by the exact backend; compare answer quality and VRAM, not just memory.
8. **CPU/GPU split:** compare Vulkan offload profiles with the CPU/RAM server path; do not assume more GPU offload is always faster when the GPU is also rendering the game and OBS.

Match SPEED-Bench client concurrency to server slot count. Keep model revision, prompt, input length, output length, sampling, benchmark split, and warm/cold cache state identical between baseline and candidate.

### Metrics that matter

- Queue wait p50/p95/p99.
- Prefill tokens/second.
- Time to first token.
- Inter-token latency / time per output token.
- End-to-end completion latency.
- Output tokens/second.
- Prompt-cache hit/reuse rate.
- Speculative draft acceptance.
- CPU and RAM peak.
- VRAM peak and allocation failures.
- Voice first-audio latency during concurrent load.
- OBS render/encoder lag and game frame time.

### Low-VRAM decision

For STAR's local 8 GB Vulkan GPU target, keep a small fast local path and a CPU/RAM or second-machine path for heavier work. Do not run multiple large ASR, TTS, vision, and reasoning models on the same 8 GB GPU simultaneously. Use the existing resource-admission controller to reserve headroom for game rendering, audio, and OBS.

A published CUDA/H100 speedup, a vLLM speculative-decoding result, or a server benchmark from another backend is not an RTX/Vulkan STAR result. No speedup is claimed until measured on the target machine.

---

## 6. Roblox Studio — plan, build, test against one manifest

**Roblox announcement (2026-04-15):** https://about.roblox.com/newsroom/2026/04/roblox-studio-going-agentic  
**StudioTestService:** https://create.roblox.com/docs/reference/engine/classes/StudioTestService  
**Built-in MCP announcement:** https://devforum.roblox.com/t/assistant-updates-studio-built-in-mcp-server-and-playtest-automation/4474643

Roblox describes a plan/build/test direction: editable multi-step plans and task manifests, parallel work, procedural generation, and playtesting against the original plan. StudioTestService supports scripted test/run modes and multiplayer test scenarios; the built-in Studio MCP provides a separate agent-facing editor/playtest interface.

### STAR Creator Brain workflow

1. Inspect the existing project and capture its current architecture.
2. Create an editable plan manifest with requirements, non-goals, affected systems, dependencies, and acceptance checks.
3. Split only independent tasks across agents.
4. Keep shared-file edits serialized or isolated in separate worktrees.
5. Implement in a disposable test place/project.
6. Run static Luau analysis and formatting.
7. Start Studio playtests through the official opt-in adapter.
8. Run deterministic multiplayer tests for server/client replication, joins/leaves, parties, and matchmaking.
9. Inspect logs, state assertions, and screenshots.
10. Compare the result to the original manifest.
11. Produce a reviewable diff and evidence bundle; do not publish automatically.

The task manifest should become the common context for planning, parallel execution, testing, and final review. It should be stored through the existing task/project context infrastructure, not another memory database.

---

## 7. General knowledge and proactive research

Use the same evidence discipline across all domains:

- **Factual knowledge:** source, publication date, scope, and contradictions.
- **Conceptual knowledge:** explanation plus examples and known limits.
- **Procedural knowledge:** a versioned skill with preconditions and verification.
- **Episodic knowledge:** what happened in a particular session, with expiry and source.
- **Strategic knowledge:** when a method is appropriate and when to abstain.

A new source should not silently overwrite an older fact. Preserve revisions and scope. Revalidate facts that depend on fast-changing APIs, software releases, prices, game patches, or platform policy.

### Additional feature roadmap

| Feature | Description | Evidence gate |
|---|---|---|
| Watch mode | User-authorized long-running conditions | Sentinel-style no-op and reaction tests |
| Stream health sentinel | Watch audio, OBS, model and queue health | Fault injection and restart recovery |
| Game replay analyst | Find meaningful moments and explain decisions | Timestamped replay plus outcome evidence |
| Self-directed practice | Choose a next task at the edge of current ability | Curriculum coverage and held-out skill gain |
| Strategy comparison | Compare two gameplay strategies from matched starts | Paired seeds and state verifier |
| Creator project memory | Preserve project intent and task manifest | Revision provenance and stale-context tests |
| Knowledge freshness | Recheck volatile facts and APIs | Source date and contradiction tests |
| Co-host mode | Optional second character with one audible-floor arbiter | No-overlap and handoff replay tests |
| Stream recap | Produce clips/chapters/summary after stream | Source timestamps and owner approval |
| General desktop skills | Use supported applications through permissioned adapters | Disposable VM and state verification |

---

## 8. Run 41 implementation

Run 41 adds a small optional improvement to the existing ActivePerceptionPolicy rather than another perception subsystem.

### Deadline-aware evidence ranking

The current policy already validates session, freshness, deduplication, evidence age, request count, and media-unit budget. It also carried a deadline timestamp, but deadlines affected ordering only when scores tied.

Run 41 adds:

- `deadline_urgency_weight` (default `0.0`).
- `deadline_horizon_ms` (default `1000`).
- A bounded multiplicative urgency bonus for candidates with a deadline inside the configured horizon.
- Validation for non-finite, boolean, negative, or out-of-range settings.

The default weight is zero, so existing selection behavior is unchanged. The feature is opt-in and must be evaluated on paired replay traces before a runtime configuration enables it. It is not compute admission, action authorization, or a guarantee that the evidence can be processed before the deadline.

### Game Lab catalog correction

The Game Lab catalog had a validation-message mismatch: the configured maximum was 80, but the error message still said 70. Run 41 corrects the message and adds six reviewed sources for monitoring, voice evaluation, inference runtime, VTube Studio, and Roblox's plan/build/test direction.

### Research register

The shared frontier register receives R169–R175 for SentinelBench, GameWorld, Full-Duplex-Bench v3, InteractionBench, llama.cpp server documentation, VTube Studio API, and Roblox Studio agentic workflows.

No external packages, models, datasets, credentials, API permissions, or platform integrations were installed or enabled.

---

## 9. Required validation before promotion

### Code and policy

- Exact-head offline Python, Ruff, Pyright, React, and Windows desktop workflows.
- Active-perception default-zero regression proves old ordering is unchanged.
- Deadline bonus tests prove monotonic bounded urgency.
- Invalid configuration fails closed.
- Game Lab catalog count, unique IDs, categories, and max limit are verified.
- JSON source register parses and has unique IDs.

### Real-time performance

- Run matched SPEED-Bench baseline/candidate workloads.
- Record 1-slot and 2-slot concurrency separately.
- Compare cold/warm prompt cache.
- Record TTFT, ITL, p95/p99, CPU/RAM/VRAM and game/OBS frame-time impact.
- Repeat during a private voice + game + OBS rehearsal.

### Game intelligence

- State-verifiable task completion and normalized progress.
- Separate paused, slowed, and live real-time tracks.
- Held-out seeds/maps and new game adapters.
- Invalid action and stale-observation rejection.
- Manual override and emergency stop.

### VTuber experience

- Full-Duplex-Bench v3 replay subset.
- InteractionBench-style timing/task/paralinguistic/grounding dimensions.
- Natural silence, side-conversation handling, false interruption and resume.
- Playback-locked mouth motion and VTube Studio parameter refresh.
- No overlapping speech or stale avatar updates.

### Monitoring

- Passive, active and no-op scenarios.
- False-action rate and reaction latency.
- Idle CPU/token/tool-call cost.
- Source disconnect/reconnect and cancellation.
- Duplicate and stale notification suppression.

---

## 10. Run 42 priority order

1. Finish exact-head CI for the existing draft PRs.
2. Integrate ActivePerceptionPolicy with trusted capture adapters and measure evidence-selection latency.
3. Connect conversation context to the room host only after adapter metadata is trustworthy.
4. Add Sentinel-style watch conditions to the existing task ledger, with push events first and bounded backoff otherwise.
5. Run the first matched local llama.cpp baseline on the target Windows/Vulkan machine.
6. Run GameWorld-compatible browser tasks and separate live-speed tests.
7. Connect the official Roblox Studio MCP and StudioTestService in a disposable test place.
8. Add full-duplex replay scoring to the existing rehearsal evaluator.
9. Verify VTube Studio parameter injection and playback-clock synchronization in a private rehearsal.
10. Run a mixed-load acceptance test before changing defaults.

## Limitations

- Paper and benchmark results are not STAR results.
- The new deadline score is a heuristic candidate, default-disabled.
- No real hardware benchmark was run in this research-only execution.
- No model weights were downloaded or trained.
- No VTube Studio, OBS, Twitch, YouTube, Roblox Studio, microphone, or game-control session was started.
- No production defaults, account permissions, or publishing permissions changed.
- All advanced work remains in draft branches until exact-head CI and owner-appropriate acceptance pass.
