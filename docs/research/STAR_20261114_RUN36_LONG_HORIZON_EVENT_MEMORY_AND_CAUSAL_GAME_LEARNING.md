# STAR Run 36 — Long-Horizon Event Memory and Causal Game Learning

**Research date:** 2026-11-14 (America/Chicago)  
**Repository:** `oncoursemail/Star-AI-Project`  
**Research branch:** `research/star-run24-integration-blueprint-20261114`  
**Scope:** hour-scale audiovisual continuity, event-centric memory, causal action-effect learning, proactive VTuber behavior, cooperative game planning, and integration discipline.

---

## Executive decision

STAR does not need another giant prompt, another parallel memory database, or another always-on vision-model call. The next meaningful improvement is to make her continuous experience **selectively observable, temporally searchable, causally useful, and cheap enough to coexist with live audio and gameplay**.

Run 36 makes six decisions:

1. **Adopt a two-speed multimodal runtime.** A small foreground loop handles current audio, current gameplay, direct owner controls, and urgent stage events. Background workers build event memory, search historical evidence, and learn from completed sessions.
2. **Represent experience as timestamped events with evidence anchors.** Do not continuously append raw video or transcripts to the language-model context.
3. **Treat event memory as an evidence index, not a new memory authority.** Existing task/delivery ledgers, governed memory promotion, procedural skills, and semantic knowledge remain authoritative.
4. **Learn game mechanics through controlled action-effect experiments.** Compare actions from equivalent simulator states, retain measured transitions, and test on held-out seeds before promoting a reusable skill.
5. **Use proactive commentary only when evidence and social timing justify it.** STAR should react to verified events, not hallucinated visual details or every frame.
6. **Consolidate the existing draft PR train before adding more runtime authorities.** There are already separate implementations for scheduling, task continuity, audio playback, OBS telemetry, avatar frame transport, inference measurement, multiparty voice, and game-action authorization.

This is a research and integration plan. It does not install models, change production routing, create platform credentials, or enable public streaming.

---

## 1. Repository audit: preserve the authorities already being built

The current repository already contains or has draft work for the following capabilities:

| Area | Existing work | Run 36 integration rule |
|---|---|---|
| Workload admission | #1140 and #1142 | Keep one CPU/RAM/VRAM admission authority. |
| OBS observation | #1149 and #1150 | Reuse the read-only OBS stats/status parsers; do not add another OBS monitor. |
| Trusted host telemetry | #1152 and #1153 | Reuse coherent, epoch-bound host samples. |
| Task and delivery continuity | #1154–#1158 and #1177 | Keep one task lifecycle and one delivery/outbox authority. |
| Voice turn policy | #1171–#1178 | Keep one RoomTurnDirector / RoomStreamHost path. |
| Audio playback evidence | #1151 and #1181 | Reconcile overlapping playback-clock and speaker-meter work before merging either branch. |
| Avatar frame transport | #1159 | Keep the existing latest-wins frame pump; connect it to one authoritative playback clock. |
| Inference measurement | #1167 | Use streamed first-content/token measurements instead of tokens-per-second claims alone. |
| Paired quality evaluation | #1165 and #1166 | Use matched holdouts to ensure speed changes do not silently reduce task quality. |
| Game action authorization | #1182 | Keep GameControlGate as the only action-permit authority. |
| Research blueprint | #1180 | Extend the current research branch rather than creating another disconnected roadmap. |

### Integration risks found

- #1181 is stacked on the large voice/resource branch #1178. #1151 contains overlapping playback-clock and audio-meter work on a separate OBS/runtime train. These must be compared and reconciled; blindly merging both can duplicate callbacks, clocks, or telemetry.
- #1182 is an independent main-based policy PR. It authorizes a bounded action from a fresh observation, but it is not yet a Windows DXGI capture adapter or input executor.
- #1159 provides a latest-wins avatar frame sender, but actual playback-to-avatar and device-level lip-sync acceptance still requires the single reconciled playback clock.
- #1167 measures streamed inference, but its numbers must be paired with the actual owner machine, model revision, scheduler load, audio latency, game frame time, and OBS output.
- The repository has many stacked draft branches. New feature branches should not be created for another scheduler, task ledger, audio clock, room director, memory authority, or action gate.

**Merge policy:** keep all work in reviewable draft PRs; inspect the complete dependency graph and exact branch heads; require exact-head Linux and Windows CI; then perform target-machine acceptance. Do not auto-merge a large stacked train.

---

## 2. New research: StreamArena and the hour-scale continuity problem

### StreamArena

Paper: https://arxiv.org/abs/2608.05703  
Project: https://github.com/palsure/StreamMind-LiveQA

StreamArena is a useful new evaluation reference because it tests continuous streams rather than only short clips. The paper describes:

- 243 full-length videos averaging 88.8 minutes.
- 3,646 validated open-ended questions.
- Separate query timestamps and supporting evidence timestamps.
- Four capability areas: real-time perception, historical retrospection, proactive interaction, and multimodal tool use.
- Multi-turn questions that preserve continuity over the same stream.

The paper's StreamMind design separates latency-critical foreground interaction and proactive monitoring from asynchronous workers that construct persistent multimodal memory, retrieve historical evidence, and perform external search.

In its same-backbone comparison using Qwen3.5-397B-A17B, the paper reports a weighted 66.2% query-to-answer latency reduction (81.4 seconds to 27.5 seconds) while retaining 89.7% of pooled accuracy. This is a result from the authors' benchmark and very large model environment, not a STAR speedup or a prediction for an 8 GB local GPU. The authors also report remaining long-horizon recall degradation.

Primary paper sections: benchmark design, online response latency, and future-work discussion.

### What STAR should take from it

The strongest idea is **do expensive historical preparation before a question arrives**.

For STAR:
- Keep the live path small: current frame, current audio turn, active game objective, active chat topic, and urgent stage state.
- Build event summaries and evidence links asynchronously.
- On a question such as “what happened to the boss earlier?”, retrieve the relevant event cards and original evidence anchors rather than replaying the entire stream through the model.
- When the stream is quiet, consolidate only eligible event summaries through the existing governed memory process.
- When the stream is busy, reduce background indexing before degrading audio, game-control, or owner-stop responsiveness.

The system should be able to answer both “what is happening now?” and “what happened twenty minutes ago?” without carrying twenty minutes of raw frames in every prompt.

---

## 3. EventMemAgent: turn continuous video into searchable event evidence

Paper: https://arxiv.org/abs/2602.15329

EventMemAgent proposes a hierarchical approach for online video:
- A short-term memory detects event boundaries and uses event-granular reservoir sampling to keep a bounded working set.
- A long-term layer stores event-centric records containing captions, visual anchors, and change logs.
- A multi-granular toolkit can search memory and request more detailed perception, such as object detection.
- The agent can iteratively collect evidence instead of relying only on a passive similarity lookup.

The paper says its code will be released; this run does not assume that a maintained, license-cleared implementation is available.

### Proposed STAR Event Memory

Build an additive evidence index that references existing media/session storage and governed memory. It must not become a second task ledger or a replacement for semantic knowledge.

**A. Hot observation window**
- Fixed-capacity ring buffer for recent frames, audio event markers, and permitted chat cue metadata.
- Latest-wins replacement for ordinary visual samples.
- Never drop owner stop/mute, moderation tombstones, task completion, action-permit revocation, or other non-replaceable control events.
- Store opaque evidence references and monotonic timestamps, not raw transcripts in diagnostics.

**B. Event boundary detector**
Candidate boundaries include:
- Scene or map transition.
- Objective or quest change.
- Score, health, inventory, or round-state change.
- Boss phase, death, respawn, victory, defeat, or checkpoint.
- New speaker, explicit mention, question, reply, or topic shift.
- STAR starts/stops speaking or is interrupted.
- A task becomes blocked, completed, or awaiting delivery.
- OBS enters reconnecting, inactive, or degraded state.

A cheap detector should run first. Expensive vision or reasoning is triggered only when a high-value change, uncertainty, or user question warrants it.

**C. Event card**
Each event card should carry bounded, typed fields:

| Field | Meaning |
|---|---|
| event_id | Opaque unique event identifier |
| session_id | Source-scoped session identifier |
| source_kind | Game, screen, audio, chat, avatar, OBS, or task |
| start_at / end_at | Monotonic event interval and clock epoch |
| event_kind | Controlled event taxonomy |
| summary | Short, evidence-grounded description |
| evidence_refs | Screenshot/audio/log references with source hashes |
| game_state_ref | Optional state snapshot or verifier reference |
| speaker_ref | Session-scoped pseudonym only, when permitted |
| topic_ref | Short-lived conversation topic identifier |
| confidence_by_field | Separate confidence for classification, transcription, and evidence |
| moderation_state | Visible, held, deleted, or unknown where applicable |
| retention_class | Ephemeral, session, owner-approved, or non-retained |
| expires_at | Explicit expiry for ephemeral data |

Do not collapse all confidence into one number. A strong event classification does not prove that the caption is correct, and a clear transcript does not prove that a message is permitted to be spoken.

**D. Evidence anchors**
- Keep a timestamped frame reference for visual claims.
- Keep the source event or verifier reference for gameplay claims.
- Keep audio playback evidence separate from TTS queue submission.
- If the original evidence is unavailable, say that the event is uncertain rather than reconstructing details from a summary.
- Historical answers should expose the time window and evidence used in internal traces.

**E. Retrieval**
Use a staged retrieval process:
1. Filter by session, time range, source, and retention permission.
2. Retrieve candidate event cards.
3. Select the most relevant event anchors.
4. Reinspect the original frame/audio/log only if needed.
5. Verify the answer against the retrieved evidence.
6. Abstain when the evidence is missing, contradictory, expired, or too weak.

This avoids embedding every frame or full transcript into every request.

---

## 4. Causal game learning: learn what an action actually changes

### OnlineWM

Paper: https://arxiv.org/abs/2609.23753  
Project page: https://onlinewm.github.io/

OnlineWM argues that static offline data can miss the model's current predictive weaknesses and that a world model can learn spurious correlations instead of action-effect causality.

Its two central ideas are:
- Actively query a simulator for new trajectories where the current model is weak.
- Compare different actions from equivalent states so the model learns which changes were caused by the action rather than by the environment continuing to evolve.

This is an arXiv preprint and a research candidate, not a reason to train STAR's foundation model online.

### STAR's safer first implementation: an Action-Effect Notebook

Before training a learned world model, create a small, deterministic experiment record in the existing game-learning/evidence system.

For each experiment:
1. Record game version, mode, map/seed, objective, and an exact starting-state fingerprint.
2. Capture a baseline observation and identify the relevant state variables.
3. Reset or reproduce the same starting state.
4. Execute one bounded action or one small action sequence.
5. Record the verified state change, reward/objective result, time-to-effect, and any side effects.
6. Repeat with a contrasting action from the same initial state.
7. Repeat across multiple seeds or equivalent scenarios.
8. Compare results and uncertainty.
9. Test the candidate strategy on untouched maps/seeds.
10. Promote only through the existing skill/evidence gate.

Example: if STAR is learning whether to dodge left or right, do not compare two unrelated fights. Compare matched trials with the same enemy phase, distance, health, and starting position. Record whether the action avoided damage, preserved line of sight, or caused a collision.

### Active experiment selection

Prioritize experiments that:
- Have high uncertainty.
- Affect an important objective.
- Are cheap to reproduce.
- Can be safely reset.
- Distinguish competing hypotheses.
- Have a reliable verifier.

Do not spend the practice budget repeating a strategy that already has stable evidence. Do not use public viewer suggestions as trusted experiment commands.

### Skill promotion contract

A reusable skill should contain:
- Preconditions and game/version scope.
- State features needed to recognize the situation.
- Candidate action and duration.
- Expected effect and verifier.
- Observed success/failure counts.
- Failure modes and recovery behavior.
- Held-out seed/map results.
- Last verified date and source revision.

A skill should be invalidated or re-evaluated when the game version changes, the preconditions no longer match, or repeated failures contradict its expected effect.

**Important:** begin with a state table or small local predictor. A learned neural world model is a later experiment only if the simpler method demonstrably fails.

---

## 5. Cooperative games: joint actions require joint evaluation

### MA-WAM

Paper: https://arxiv.org/abs/2609.31281  
Project page: https://ma-wam.github.io/

MA-WAM studies test-time scoring of candidate joint actions in offline multi-agent reinforcement-learning settings. Its paper reports mean relative gains of 22.0% over direct execution and 25.6% over uniform action selection across 30 settings, with 12.1 ms added under its A100 evaluation protocol.

These results are not evidence that a visual desktop agent will gain the same benefit. The experiments use specific offline MARL settings and a trained/frozen policy and world model.

### Possible STAR application

Keep this research-only until STAR has a deterministic cooperative-game harness.

For a supported co-op game:
- Represent each STAR-controlled teammate's proposed action in one shared time window.
- Evaluate joint plans rather than assuming that each player's best individual move is also best for the team.
- Execute only the first short action, then observe the real state and replan.
- Preserve human teammates' control and never infer consent from chat.
- Compare against the same frozen policy without joint-plan ranking.

Potential uses include coordinated target assignment, role coverage, synchronized switches, and avoiding teammates blocking one another.

---

## 6. Natural VTuber behavior from event memory

A believable streamer needs continuity, not constant commentary.

Use the event index to support:
- “We tried that route earlier” with a real event reference.
- Remembering the current boss phase and objective.
- Returning to an unanswered viewer question when the floor is open.
- Acknowledging a verified win, loss, death, discovery, or funny mishap.
- Avoiding repeated reactions to the same event.
- Knowing when she is focused on a difficult gameplay segment.
- Summarizing what happened during a long stream.
- Producing a highlight candidate with the exact source time range.

### Stage decision

The existing room director remains the sole speech/floor authority. Event memory supplies evidence; it does not grant permission to speak.

A stage candidate should include:
- Triggering event ID.
- Relevance to the active topic/game objective.
- Evidence freshness.
- Urgency.
- Whether STAR or another participant currently has the floor.
- Whether the event was already acknowledged.
- Whether the event is suitable for public commentary.

Possible outcomes remain: speak, short acknowledgement, queue, wait, yield, resume an owed task, or ignore.

The same event may be useful for a private memory but inappropriate for public commentary. Moderation state and privacy policy must be checked before any speech.

### Avatar behavior

- Keep the existing latest-wins VTube frame pump for replaceable pose samples.
- Keep the reconciled playback clock as the timing source for mouth motion.
- Let verified event kind and conversational intent choose expression/gaze/gesture.
- Do not animate a laugh merely because a model emitted “haha”; use the selected voice/audio event and stage state.
- On owner mute, playback cancellation, or stale event, stop or neutralize the corresponding animation promptly.

---

## 7. Faster runtime: reduce unnecessary work before increasing model size

The combined StreamArena/EventMemAgent direction suggests a practical speed strategy:

1. Capture cheaply and continuously.
2. Detect changes with lightweight logic.
3. Retain a bounded recent window.
4. Run high-cost perception only on event boundaries or questions.
5. Build historical event records in background workers.
6. Retrieve only the relevant event and original evidence.
7. Keep the current conversation/game loop independent from background indexing.

### Resource policy

Reuse the existing workload-admission controller. Suggested lane behavior:

| Lane | Policy |
|---|---|
| Owner stop/mute/manual override | Highest priority; never queued behind model work |
| Audio callback and active playback | Protected |
| Current game observation/action | Protected, deadline-bound |
| Current room turn and urgent response | Protected, cancellable |
| Avatar pose sample | Latest-wins; stale samples coalesced |
| Event indexing | Background, bounded, pause under pressure |
| Historical visual retrieval | On-demand, bounded |
| Game experiments | Background and resettable |
| Model/skill training | Offline or explicitly scheduled; never on the live critical path |

### Speed metrics

Measure on the actual Windows target:
- Capture-to-event latency.
- Event boundary precision/recall.
- Frame sampling rate and dropped/coalesced samples.
- Event-card write and retrieval p50/p95/p99.
- Historical question accuracy at 1, 5, 15, 30, and 60 minutes.
- Evidence-anchor correctness.
- First ASR partial, final transcript, first token, first TTS chunk, first non-empty PCM callback, estimated DAC time, and cancellation-to-stop.
- CPU/RAM/VRAM per process.
- Game FPS and frame-time p10/p50/p95/p99.
- OBS render lag, encoder lag, and output state.
- Background-worker pause/recovery time.

A speed change is accepted only if it improves the end-to-end task without worsening speech correctness, interruption behavior, game control, or stream stability.

---

## 8. General knowledge: do not confuse event recall with factual truth

Event memory answers questions such as “what happened during the last match?” It is not a replacement for the existing source-grounded knowledge system.

For general knowledge:
- Store source, author/publisher, publication date, retrieval date, version, and exact evidence span.
- Preserve contradictory sources instead of silently overwriting them.
- Distinguish stable facts from time-sensitive facts.
- Keep procedural skills separate from factual claims.
- Require an evidence source for technical API claims and a real outcome verifier for procedural skills.
- Use spaced review for learned concepts, but do not treat repeated exposure as verification.
- Route a question to the smallest useful memory store.

This lets STAR learn broadly across science, history, programming, art, game design, Roblox, Blender, and everyday knowledge without turning a remembered stream event into an unsupported fact.

---

## 9. Privacy, safety, and retention

- Raw video/audio is ephemeral by default; persistent recording remains a separate, explicit owner-controlled function.
- Viewer messages are short-lived and moderation-filtered; deleted/held messages must not be spoken or promoted into memory.
- Do not create cross-platform identity graphs between Twitch, YouTube, Discord, and real-world accounts.
- Do not store voiceprints or infer sensitive traits from viewer audio/video.
- Persist only the minimum event metadata and evidence references needed for the approved feature.
- Respect source, game, platform, and dataset licenses before importing any benchmark or media.
- Never allow viewer text or model-generated event descriptions to authorize tools, game input, file access, account actions, or public broadcasts.
- Game experiments must use permitted, resettable environments. Do not bypass anti-cheat, DRM, access controls, or platform restrictions.
- No live chat, private recordings, or personal data may be used for model training without a separately reviewed lawful basis and explicit authorization.
- Expired or deleted source evidence must invalidate dependent event summaries and retrieval indexes.

---

## 10. STAR evaluation plan

Build small synthetic fixtures first. External datasets are optional references and require license/data-use review.

| Evaluation | Test | Required evidence |
|---|---|---|
| Live event detection | Known scene/objective/game-state transitions | Timestamped precision, recall, detection latency |
| Long-horizon recall | Ask about events 1–60 minutes earlier | Correct answer plus exact evidence anchor |
| Proactive commentary | Event occurs during active viewer conversation | Appropriate-silence rate, false interruption, missed useful reaction |
| Event retrieval | Same entity/event across different time windows | Retrieval precision, recall, latency, source-scope isolation |
| Causal game learning | Matched starting states with contrasting actions | Action-effect accuracy, uncertainty calibration, verifier result |
| Skill transfer | Unseen map/seed/version | Success delta against fixed baseline, manual interventions |
| Co-op planning | Joint-action scenarios with deterministic outcomes | Team objective success vs frozen reactive baseline |
| Mixed-load stream | Game + ASR + LLM + TTS + avatar + OBS + event indexing | No owner-control delay; audio/OBS/game p95/p99 within measured baseline |
| Retention/privacy | Expiry, deletion, moderation, session reset | No stale/deleted/held evidence in retrieval or speech |

### Statistical discipline

- Freeze the scenario set and evaluator before comparing candidates.
- Separate development seeds from sealed holdout seeds.
- Group trials by game session/map/seed; do not treat every frame as an independent sample.
- Report trial counts and confidence intervals.
- Keep baseline and candidate on the same hardware, model, prompt, and workload.
- Do not promote a skill based on one lucky run or a model-generated explanation.
- Never let the candidate modify the evaluator or holdout set.

---

## 11. Implementation sequence

| Priority | Work | Acceptance gate |
|---|---|---|
| P0 | Reconcile #1151/#1181 audio clock and meter overlap | One callback/clock implementation; exact-head Linux + Windows CI |
| P0 | Audit draft dependency graph | No duplicate scheduler, task ledger, room director, playback clock, or action gate |
| P1 | Define metadata-only EventRecord and bounded hot window | Schema, expiry, epoch, source-scope, moderation, and eviction tests |
| P1 | Add synthetic event stream fixture | Reproducible game, voice, chat, avatar, and OBS event timelines |
| P1 | Add event retrieval/evidence verifier | Historical answers cite correct time/evidence or abstain |
| P2 | Add event-driven proactive trigger | Appropriate silence and no duplicate reactions on holdouts |
| P2 | Add matched action-effect experiment harness | Same-state contrasting actions and independent outcome verifier |
| P2 | Add held-out skill transfer report | Improvement over fixed baseline on unseen seeds/maps |
| P3 | Evaluate compact learned predictor only if needed | Beats the deterministic baseline under equal compute |
| P3 | Add cooperative joint-action ranking | Only after a deterministic co-op harness exists |
| P4 | Full private Windows mixed-load rehearsal | Voice, gameplay, event memory, avatar, and OBS coexist without regressions |

---

## 12. Source register

**R145 — StreamArena: Toward Continuous, Interactive, and Long-Horizon Agentic Streaming Video Understanding**  
https://arxiv.org/abs/2608.05703  
Benchmark and two-tier architecture for hour-scale streaming, historical recall, proactive interaction, and multimodal tool use. Paper inspected; benchmark data are not bundled.

**R146 — EventMemAgent: Hierarchical Event-Centric Memory for Online Video Understanding with Adaptive Tool Use**  
https://arxiv.org/abs/2602.15329  
Event-boundary detection, event-granular short-term sampling, event-centric long-term records, and active evidence retrieval. Paper inspected; implementation/license availability not assumed.

**R147 — OnlineWM: Causality-Aware Active Online Learning for Effective World Modeling**  
https://arxiv.org/abs/2609.23753  
Active simulator queries and counterfactual action comparisons from equivalent states. arXiv preprint; no foundation-model training or dependency adoption.

**R148 — MA-WAM: Multi-Agent World-Action Model for Test-Time Planning**  
https://arxiv.org/abs/2609.31281  
Joint-action candidate scoring for offline cooperative MARL settings. arXiv preprint; not treated as proof of visual real-time game performance.

Additional evaluation references:
- GameWorld: https://arxiv.org/abs/2604.07429
- SkillLearnBench: https://arxiv.org/abs/2604.20087
- Roblox Studio MCP: https://create.roblox.com/docs/studio/mcp
- Roblox StudioTestService: https://create.roblox.com/docs/reference/engine/classes/StudioTestService
- OpenTelemetry semantic conventions: https://opentelemetry.io/docs/concepts/semantic-conventions/

---

## Final decision

The highest-value next step for STAR is not a bigger model or more agents. It is a compact event-memory and evidence-retrieval layer that lets her maintain hour-scale continuity while keeping the live interaction loop fast, plus a controlled action-effect experiment harness that turns gameplay experience into verified transferable skills.

This should be integrated with the existing authorities and tested under a real mixed workload. Until the Windows target-machine rehearsal is complete, research and GitHub CI must not be described as proof that STAR can already stream, play arbitrary games, or learn autonomously in production.
