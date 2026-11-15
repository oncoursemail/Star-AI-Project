# STAR Run 32 — Task Continuity, Intent-Aware Streaming, CPU Speculation, and Visual Creator Loops

**Research date:** 2026-11-14  
**Status:** Research and engineering handoff; no production-default changes  
**Companion implementation:** [PR #1182](https://github.com/oncoursemail/Star-AI-Project/pull/1182)  
**Existing acceptance contract:** [Issue #584](https://github.com/oncoursemail/Star-AI-Project/issues/584)

## Executive finding

STAR's next capability jump is not another independent model or another scheduler. It is reliable coordination across three clocks:

1. **The conversation clock:** partial speech, addressee, playback, interruption, and turn-taking.
2. **The work clock:** tools, research, game tasks, completion, cancellation, and results that still need to be reported.
3. **The environment clock:** fresh frames, game state, action execution, and the next observation.

A strong agent must preserve obligations when those clocks overlap. It must know not only what it is doing, but what it has completed, what it has actually communicated, and what remains owed. It must also refuse to act on stale observations.

Run 32 adds a source-linked research plan and a small safety refinement to the existing game-control gate. It does not add a new conversation host, task ledger, inference scheduler, ASR model, or platform adapter.

---

## 1. New research: full-duplex conversation must preserve work obligations

### 1.1 Joi-Bench-Task (November 9, 2026)

Paper: https://arxiv.org/abs/2611.12118

Joi-Bench-Task evaluates coordination between live conversation and long-running tool work. Its interactive simulator injects request changes and interruptions while tools execute or results are being spoken. It asks whether the agent tracks:

- what has been requested;
- what has started;
- what has completed;
- what has already been communicated;
- what still needs to be reported.

The paper reports that the highest result-completion rate under request changes was 55% among its five evaluated agents. Four of five had average information-omission rates of at least 23% after interruption. These are results for the paper's tested agents and scenarios, not STAR measurements.

**Design implication:** a task can be complete internally while its result is not yet delivered. STAR must never equate `tool_completed` with `user_informed`.

The benchmark currently focuses on English and controlled, noise-free audio. STAR should extend the methodology to game audio, viewer chat, overlapping speakers, and multilingual sessions rather than treating the published scores as universal.

### 1.2 Add a delivery-obligation projection to the existing task ledger

Reuse the existing task/communication ledger in PR #1177. Do not create a second task authority.

Each task should have an explicit lifecycle:

- `requested`
- `accepted`
- `running`
- `blocked`
- `completed`
- `cancelled`
- `superseded`
- `reported`

Keep work state separate from communication state. A completed result can have one of:

- `not_announced`
- `announcement_started`
- `partially_delivered`
- `delivered`
- `delivery_cancelled`

A compact delivery record should reference opaque IDs and contain:

- task ID and parent request ID;
- current task state and revision;
- result reference and verifier reference;
- ordered announcement segment IDs;
- the last segment known to have reached playback;
- remaining segment IDs;
- whether the user changed, cancelled, or superseded the request;
- a monotonic event sequence and clock epoch.

Do not store raw microphone audio, viewer chat, or full spoken transcripts in performance telemetry. The task ledger may retain only the content required by its existing, explicitly governed memory policy.

### 1.3 Interruption and request-change algorithm

1. On a new request, create or update an obligation without deleting unrelated obligations.
2. When a tool starts, record its opaque run ID and current status.
3. When a tool finishes, store its result reference and verifier outcome.
4. When speech starts, record the exact announcement segment IDs queued for playback.
5. Advance the delivery cursor only from the authoritative playback callback/cursor—not when text is generated or submitted to TTS.
6. On interruption, stop or pause the current output, preserve undelivered segments, and classify the new utterance.
7. If the request changes, update only affected tasks; retain unrelated completed work and pending reports.
8. Before resuming, reconcile the user's latest intent, current task states, and what has actually been heard.
9. Deliver the smallest useful continuation without repeating already-heard material.
10. Close an obligation only after the result is either delivered, explicitly cancelled, or superseded.

This is the foundation for a streamer who can answer a viewer, return to a coding task, handle a correction, and later report the finished result without losing the thread.

---

## 2. New research: intent-aware turn-taking, not just end-of-speech detection

### 2.1 HiThink Turn

Paper: https://arxiv.org/abs/2609.34096

HiThink Turn separates response intent from semantic completeness and conditions its decisions on the system's playback state. It uses partial audio chunks and minimal intent-sufficient prefixes rather than waiting only for a complete utterance.

The paper reports 240 ms chunk-wise inference, a 0.933 Full-Duplex-Bench interaction-rate score, a 0.735 non-target-speech playback-resume rate, and an increase in interruption success from 89% to 98% with a reported 60.9% reduction in mean stop latency. Those figures belong to the paper's Qwen3-ASR-1.7B/LoRA setup and evaluated benchmarks; they are not STAR's latency or accuracy.

### 2.2 Model Interruption Bench (EMNLP 2026)

Paper: https://aclanthology.org/2026.emnlp-main.2349/

MIB separates offline error detection from the ability to interrupt at the correct moment. In its math-correction task, several systems detected 59–67% of errors in turn-based conditions but achieved below 10% mid-speech true-positive rates when required to interrupt in real time.

**Design implication:** understanding an event does not prove STAR can act on it at the right time. Detection, decision, stop, and resume are separate stages and must be measured separately.

### 2.3 Proposed STAR turn-state controller

Reuse the existing RoomTurnDirector and RoomStreamHost from PR #1178. Feed them trusted, classified events from the existing ASR/diarization/provider adapters.

The controller should consider:

- partial transcript and its stability;
- speaker identity and confidence;
- whether the speaker is addressing STAR;
- speech intent versus utterance completeness;
- current playback state and segment cursor;
- active task obligations;
- game-event urgency;
- whether the event came from a human, platform chat, game audio, or STAR herself.

Possible decisions:

- `WAIT`
- `BACKCHANNEL`
- `RESPOND`
- `INTERRUPT`
- `STOP`
- `RESUME`
- `IGNORE_NON_TARGET`

Use 240 ms only as a benchmark candidate, not a fixed universal chunk size. Benchmark 80/160/240/320/560 ms windows against STAR's actual CPU budget and microphone. A smaller window can reduce reaction delay but may increase false interruptions and compute overhead.

Do not let ordinary viewer chat, game audio, or an uncertain partial transcript interrupt an owner conversation. Require source-aware thresholds and an explicit priority policy.

### 2.4 Required streaming metrics

- partial-ASR-to-turn-decision p50/p95/p99;
- decision-to-playback-stop p50/p95/p99;
- interruption success and missed-interruption rate;
- false interruption rate on non-target speech;
- playback resume success;
- duplicate/repeated announcement rate;
- information-omission rate after interruption;
- result-completion rate after request changes;
- time from tool completion to first audible result;
- delivery-cursor correctness against actual playback.

A natural streamer should not interrupt every silence or every viewer message. Appropriate silence, brief backchannels, and deferred answers are valid positive outcomes.

---

## 3. New inference research: CPU speculative decoding is a candidate, not a guaranteed upgrade

### SubTernary

Paper: https://arxiv.org/abs/2610.28671

SubTernary investigates CPU speculative decoding with a unified execution graph, a persistent thread pool, and transactional KV-cache isolation. The paper reports 1.35x throughput over its llama.cpp speculative baseline and 3.99x over its autoregressive baseline in one Llama-3.2 3B/1B configuration. It reports a smaller 1.15x gain over llama.cpp speculative decoding for a Qwen 3.5 4B/2B pair.

The published evaluation uses an eight-vCPU virtualized Intel Xeon Gold 5218 system, AVX2, Ubuntu 24.04.1, GCC 13.3, and five-run averages. The authors state that other microarchitectures remain future work. The paper does not link a public implementation in the inspected source.

**STAR decision:** research-only. Do not copy paper speedup numbers into STAR's performance claims or replace llama.cpp. First require a reproducible implementation, pinned model pair, exact CPU feature detection, and paired tests on the owner's Windows hardware.

### Adaptive speculative-decoding gate

The useful systems idea is not merely “always speculate.” Speculative decoding can lose when the draft model's token acceptance rate collapses.

For every candidate pair, record:

- target and draft model hashes;
- quantization and tokenizer compatibility;
- proposal length;
- accepted/proposed token ratio;
- target verification cost;
- rollback cost;
- end-to-end tokens per second;
- first-content latency;
- CPU time, RAM, and thread contention;
- task quality on a paired holdout.

Use a moving acceptance window. If speculative decoding does not beat the autoregressive baseline by a preregistered margin—or if acceptance drops below a validated threshold—fall back to the baseline. Re-enable only after enough fresh samples show recovery.

Do not assume the paper's 30% threshold is correct for STAR. Calibrate it on STAR's models and workloads.

### CPU-first routing for STAR's constrained GPU

Keep the live audio, game, and avatar workloads protected. The 8 GB RTX 4060 should not be saturated by background experiments.

Benchmark separate routes for:

- fast conversational response;
- deeper coding/research reasoning;
- lightweight speech/vision perception;
- background indexing and summarization;
- game-state interpretation;
- creator build/test analysis.

Choose routes using measured task quality and p95 latency under concurrent streaming—not parameter count or isolated tokens/second.

---

## 4. Creator Brain: visual feedback must be part of the development loop

### GameDevBench (current repository release)

Repository: https://github.com/waynchi/gamedevbench

The current repository describes 333 Godot tasks spanning:

- 2D graphics and animation;
- 3D graphics and animation;
- user interfaces;
- gameplay logic.

Its README reports that visual feedback mechanisms improved one evaluated GPT-5.4 configuration from 41.1% to 52.0%, while the best listed result remains below 71%. These are benchmark-specific results, not STAR results. The project is Apache-2.0; review task assets and benchmark terms before importing any data.

**Design implication:** code-only acceptance is insufficient for game creation. STAR must inspect the scene and output, compare it to a task-specific visual rubric, and rerun after changes.

### Proposed Creator Brain loop

1. Convert the request into a task manifest with explicit acceptance criteria.
2. Inspect the project, engine version, assets, and current scene before editing.
3. Generate a small, reversible patch.
4. Run static checks and project-specific tests.
5. Launch a controlled playtest.
6. Capture screenshots/video and structured logs.
7. Compare results with the acceptance criteria.
8. Diagnose whether the failure is code, asset, lighting, camera, animation, UI, physics, or performance.
9. Repair only the failing area.
10. Repeat until all required gates pass.
11. Run untouched holdouts to detect overfitting to the example scene.
12. Save the verified skill with the exact engine/version and evidence.

For Roblox, reuse the official Studio MCP server and the existing Luau analysis/test tooling. The official Studio MCP guide documents a local stdio server that can inspect the DataModel, read/edit scripts, execute Luau, and playtest. Roblox warns that connected clients can read and modify open places, so only trusted clients should be connected.

Official docs:
- https://create.roblox.com/docs/studio/mcp
- https://create.roblox.com/docs/reference/engine/classes/StudioTestService

StudioTestService supports one server plus up to eight simulated clients in a multiplayer test session, with one multiplayer session at a time per Studio instance. Use it for deterministic party, lobby, matchmaking, replication, join/leave, and disconnect tests. Do not confuse Studio-simulated clients with real production players.

### Third-party Roblox MCP candidate

https://github.com/Chrrxs/robloxstudio-mcp

This MIT-licensed community project advertises runtime server/client Luau evaluation, multiplayer playtests, logs, screenshots, memory reports, and profiler captures. It also exposes powerful editing and experience-management operations.

Recommendation: compare it with the built-in official Studio MCP server, inspect its source and network boundary, and begin with its inspector/read-only variant if evaluated. Do not give it broad Open Cloud keys or monetization permissions by default. Do not install it automatically.

### Creator acceptance matrix

Score separately:

- gameplay logic correctness;
- server-authority and exploit resistance;
- multiplayer synchronization;
- UI layout and readability;
- 2D/3D asset quality;
- animation timing and rig integrity;
- lighting/material quality;
- performance and memory;
- accessibility and input support;
- visual similarity to the authored reference;
- reproducible build and rollback.

A game is not “finished” merely because scripts compile or a screenshot looks plausible.

---

## 5. Gamer Brain: one fresh observation, one authorized decision

Run 31 introduced `GameControlGate` as a host-side freshness and consent boundary. A further review found that the same observation could authorize several distinct action IDs before a new frame arrived. Although each permit was one-use and short-lived, several decisions could still be queued from one stale visual state.

### Run 32 safety refinement in companion PR #1182

The gate now permits only one action authorization per accepted observation sequence. A new fresh observation resets that frame's action budget. This makes the control loop explicitly:

`capture → perceive → decide once → execute → capture again`

The existing per-action limits, one-use permit, short hold duration, foreground check, owner consent, process fingerprint, capture epoch, manual override, and stop behavior remain in place.

This is intentionally conservative. If the future capture loop cannot supply fresh frames quickly enough, optimize the capture path; do not silently permit a backlog of actions based on an old screenshot.

### Required live-game acceptance

- measure capture-to-action age;
- report dropped and rejected observations;
- report action rejection reasons;
- verify the host rechecks foreground/process identity immediately before OS input;
- ensure focus loss and manual override release every held control;
- compare live, slowed, and paused performance separately;
- test unseen maps/seeds and unseen games;
- never bypass anti-cheat, DRM, protected content, or game rules.

The policy module itself does not capture frames or inject input. Those remain separate, trusted host adapters.

---

## 6. Integration map: extend the systems already in progress

| Existing work | Run 32 decision |
|---|---|
| #1177 task/communication ledger | Add delivery-obligation projection; keep one task authority |
| #1160 incremental thinking | Use partial speech for early intent; keep speculative side effects gated |
| #1165 voice quality/groundedness | Add request-change and interruption-omission scenarios |
| #1166 paired evaluation | Reuse paired holdouts for turn policy, model routes, and game skills |
| #1167 streaming inference benchmark | Add draft acceptance/fallback and first-audible latency where available |
| #1140 / #1142 resource admission | Keep one admission controller and one host lease authority |
| #1151 playback clock/audio work | Preserve DAC-time telemetry; reconcile with #1181 before merging |
| #1178 room host/director | Feed trusted platform/ASR cues into this existing ingress |
| #1181 speaker callback isolation | Do not create a second RMS worker |
| #1182 game control gate | Add one-action-per-observation rule and current regression fixes |
| #584 Creator Studio acceptance | Use as the end-to-end production gate |

### Dependency warning

The current repository has several stacked draft trains. Examples include #1151 based on an earlier OBS/stream-status branch, #1181 based on #1178, and #1142 based on #1140. A PR that is mergeable by GitHub is not necessarily independently ready to merge into `main`.

Before merging, create an explicit dependency order, reconcile duplicate files/implementations, rerun CI on the final rebased heads, and validate the full parent chain. Do not merge overlapping audio implementations just because their individual tests pass.

---

## 7. Natural, transparent VTuber behavior

The desired result is a convincing AI streamer—not a scripted chatbot that reacts to every event.

Implement and evaluate:

- natural pauses and actual quiet-focus periods;
- contextual laughter and expressions tied to events;
- addressee-aware conversation;
- memory of the current stream session without permanent retention of every viewer;
- short acknowledgements when appropriate;
- fewer repetitive phrases;
- game-focused commentary when gameplay is demanding;
- the ability to resume an unfinished explanation after interruption;
- calibrated uncertainty when she does not know;
- consistent character voice and boundaries across long sessions.

The avatar should follow the actual audio playback cursor. Generated text, queued TTS, and audible playback are different events. Expressions may be selected from semantic intent, but mouth timing must remain grounded in the audio actually emitted.

STAR should remain transparent that she is an AI character. Naturalness must not depend on fabricated human experiences, fake memories, or pretending to be a human streamer.

---

## 8. Run 32 implementation and verification record

### Companion code changes

PR #1182 now contains:

- one action authorization per observed frame;
- a regression test proving a second distinct action ID is rejected until a new frame arrives;
- a regression test proving a new frame restores the next action budget;
- a corrected stale-action test that distinguishes an action that is too old from an action that predates its observation;
- additional research-only catalog entries for HiThink Turn, Joi-Bench-Task, Model Interruption Bench, SubTernary, GameDevBench, and the community Roblox Studio MCP.

### CI finding

The previous PR #1182 workflow exposed a test mismatch: the fixture used an action timestamp earlier than its observation, so the gate correctly returned `action_predates_observation` while the test expected `stale_action`. The fixture now uses a post-observation action with a deliberately shorter action-age budget, testing the intended branch. A separate existing test continues to cover action-before-observation rejection.

The updated branch has triggered new CI. Do not claim the repair passes until the new exact-head workflows complete.

### Explicit limitations

- No SubTernary implementation was installed; it remains a preprint candidate without a linked implementation in the inspected paper.
- No ASR model, model weights, quantization, routing default, prompt, or inference engine was changed.
- No live microphone, RTX 4060, OBS, VTube Studio, Roblox Studio, or public stream test was run.
- No Twitch/YouTube credentials or permissions were added.
- No Windows screen-capture or input-executor adapter was implemented.
- No game mastery, human-equivalence, measured speedup, or production readiness is claimed.
- Production `main` and public broadcast permissions remain unchanged.

---

## 9. Prioritized next steps

1. Finish the current #1182 CI repair and run all exact-head Linux/Windows suites.
2. Reconcile #1151 and #1181 into one audio implementation with one playback clock and one speaker-meter worker.
3. Add delivery-obligation and partial-announcement scenarios to the existing voice rehearsal evaluator.
4. Add HiThink-style intent-prefix and playback-state evaluation to the existing turn director.
5. Add request-change, interruption, and resume tests inspired by Joi-Bench-Task.
6. Add correction timing and false-interruption tests inspired by MIB.
7. Benchmark CPU speculative decoding only if a reproducible implementation becomes available.
8. Integrate official Roblox Studio MCP under least-privilege, owner-approved tool scopes.
9. Build visual Creator Brain task manifests and screenshot/verifier loops.
10. Complete Windows DXGI capture and permitted controller execution behind the existing gate.
11. Run mixed-load acceptance: live voice + avatar + OBS + gameplay + background learning.
12. Promote only revisions that improve paired holdouts without violating real-time resource budgets.

## Source register

- HiThink Turn: https://arxiv.org/abs/2609.34096
- Joi-Bench-Task: https://arxiv.org/abs/2611.12118
- Model Interruption Bench: https://aclanthology.org/2026.emnlp-main.2349/
- SubTernary: https://arxiv.org/abs/2610.28671
- GameDevBench: https://github.com/waynchi/gamedevbench
- Roblox Studio MCP: https://create.roblox.com/docs/studio/mcp
- Roblox StudioTestService: https://create.roblox.com/docs/reference/engine/classes/StudioTestService
- Community Roblox Studio MCP candidate: https://github.com/Chrrxs/robloxstudio-mcp
