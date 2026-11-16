# STAR Run 63 — In-Turn Adaptation, Collaborative Speech, and Cross-Task Transfer

**Research date:** 2026-11-15  
**Repository:** `oncoursemail/Star-AI-Project`  
**Branch base:** freshly inspected `main`  
**Change type:** research and integration specification; no runtime defaults or permissions changed

## Executive decision

The next meaningful improvement to STAR's live character is not another speech generator or another end-of-turn detector. It is **in-turn adaptation**: understanding a contribution made while STAR is already speaking, deciding whether it is a backchannel, a collaborative completion/correction, or a real takeover, and responding without unnecessarily restarting the whole turn.

This is a distinct behavior from ordinary turn-taking:

- A listener can say "yeah" while STAR should continue.
- A listener can supply a missing word or clarification while STAR should adapt the sentence she is currently saying.
- A listener can correct a mistaken detail while STAR should revise the active thought.
- A listener can genuinely take the floor, in which case STAR should yield and recover the interrupted topic later.
- A second viewer can speak to another viewer without either taking STAR's floor.

The proposed capability is a small, causal decision layer in the existing voice/room path. It must reuse STAR's existing room director, playback clock, bounded conversation context, interruption handling, memory governance and evaluation stack. It must not create a second voice engine, conversation database, scheduler or avatar controller.

## 1. New research: Duplex Cue

Primary paper: https://arxiv.org/abs/2609.13117  
Title: *Continue, Adapt, or Yield: In-Turn Adaptation to Overlapping Speech in Full-Duplex Agents*  
Posted: 2026-09-11

Duplex Cue studies a behavior missing from simple continue-versus-stop evaluations. It distinguishes listener intent—backchannel, collaboration, or interruption—from the speaker's response—continue unchanged, adapt within the turn, or yield.

The paper reports 300 human-confirmed cues from unscripted English conversations. After filtering for an ongoing speaker and a scorable response, it retains 208 pairs. On the 66 collaborative pairs, recorded human speakers adapt in 68.2% of cases, compared with 34.8% for PersonaPlex in the reported single-model case study.

**Interpretation:** this is evidence that in-turn adaptation is a measurable conversational gap, not proof that one model or architecture is universally better. The retained sample is small, English-only, and the PersonaPlex comparison is a case study. STAR should reproduce the task with its own consented evaluation set rather than copying or assuming the paper's scores transfer.

### Why it matters to STAR

STAR's goal is a natural AI streamer who can listen and speak at once. If every overlapping contribution causes a hard interruption, she will feel brittle. If every contribution is ignored, she will feel inattentive. The right behavior depends on intent, addressee, conversational context, confidence and the cost of waiting.

## 2. Related evidence and complementary evaluations

### InteractionBench — evaluate the whole heard interaction

Paper: https://arxiv.org/abs/2611.02430  
Code: https://github.com/avera-labs/InteractionBench  
Posted: 2026-11-02

InteractionBench evaluates conversational timing, spoken-task accuracy, whisper/volume behavior and groundedness across conversations longer than twenty turns. It uses the same recorded user audio for each system and fixes expected floor-control actions and scripted answers before evaluation.

The paper reports 221 items per system across thirteen scenarios and 1,519 graded runs. It also highlights a measurement trap: server-reported timing can differ materially from client-heard timing when network delay is omitted. Its protocol notes that instructions and release timing differ across some systems, so cross-system comparisons need careful qualification.

**STAR application:** preserve separate measurements for server generation, TTS queue submission, scheduled device playback, Windows loopback/client-heard playback, and remote stream delivery. Do not label a queue timestamp "what the viewer heard." Keep task correctness, floor control, vocal style and long-context grounding as separate score dimensions.

### Full-Duplex-Bench v3 — real disfluency and chained actions

Paper: https://arxiv.org/abs/2604.04847

Use its real-human-audio and chained-tool-use framing to test whether conversational adaptation survives hesitations, false starts, self-corrections and tool calls. A natural voice surface must not silently lower the correctness of a tool action.

### AGENTCL — test whether the lesson transfers

Paper: https://arxiv.org/abs/2606.02461

AGENTCL constructs task streams where prior solutions are intentionally reusable, alongside conventional and independent tasks. Its results warn that naive task streams can hide differences between memory designs and that memory can degrade held-out performance.

**STAR application:** a successful conversational repair should become a candidate reusable lesson only after it improves later tasks. Do not convert every correction into a permanent preference or skill. Test positive transfer, negative interference and forgetting separately.

## 3. Proposed STAR behavior model

### 3.1 Listener-intent classification

For each overlapping contribution, the existing room path should maintain a bounded hypothesis with:

- session and monotonic event timestamp;
- current speaker and addressee hypothesis;
- reply-to/topic identifier where available;
- overlap start and duration;
- partial transcript or semantic cue, subject to existing privacy rules;
- current floor owner and delivery state;
- intent: `BACKCHANNEL`, `COLLABORATION`, `TAKEOVER`, or `UNCERTAIN`;
- confidence and evidence provenance.

A diarization label alone is not enough. Speaker identity, addressee and floor ownership are separate variables. Do not treat every louder or overlapping utterance as a takeover.

### 3.2 Speaker-response policy

Map the intent hypothesis to one of four actions:

| Listener intent | STAR action | Expected behavior |
|---|---|---|
| Backchannel | `CONTINUE` | Acknowledge minimally if appropriate; keep the current sentence/turn |
| Collaborative completion or clarification | `ADAPT` | Incorporate the useful contribution into the unspoken remainder |
| Genuine interruption/takeover | `YIELD` | Stop stale queued speech, listen, then recover the unfinished topic only if still relevant |
| Ambiguous or low confidence | `HOLD` | Avoid an irreversible floor change; gather a little more evidence or finish a safe short clause |

`HOLD` is a policy action, not a new benchmark label. It is useful when the system cannot yet distinguish "yeah" from "wait, no" or a viewer-to-viewer aside.

### 3.3 In-turn adaptation contract

An `ADAPT` action must be narrow and causal:

1. Keep the already-played words immutable.
2. Cancel or revise only speech chunks that have not been committed to playback.
3. Preserve the current topic and sentence intent.
4. Incorporate the new word, correction, constraint or clarification.
5. Avoid repeating the entire answer unless the correction changes its meaning.
6. Record whether the adaptation was actually audible and whether it resolved the cue.
7. If confidence is low, ask a concise clarification rather than inventing what the listener meant.

Examples:
- STAR: "The blue door is on the—" Viewer: "left." STAR: "—left side, yes."
- STAR: "We'll test it on Tuesday." Viewer: "Actually, Wednesday." STAR: "Wednesday—I'll use that."
- STAR: "The boss is weak to—" Teammate: "ice." STAR: "Ice, got it."
- Viewer: "Yeah." STAR continues instead of treating agreement as a barge-in.
- Viewer A speaks to Viewer B while STAR is talking: STAR does not assume the comment was addressed to her.

These are target behaviors, not claims that STAR currently implements them.

## 4. Integration map — extend existing work, do not fork it

The repository's open development stack already has relevant work. These PRs are separate, unmerged development candidates, not production capabilities:

| Existing work | Reuse for Run 63 |
|---|---|
| PR #1178 — natural streamer persona / resolved-reply stopping | Persona and stopping behavior |
| PR #1185 — bounded session-local conversation context | Speaker/addressee/topic context |
| PR #1186 — signed multiparty room replay evaluation | Multi-speaker replay and evidence |
| PR #1187 — EoT-Bench adapter | End-of-turn evaluation, separate from overlap intent |
| PR #1151 — playback clock and callback isolation | Playback-grounded cancellation and timing |
| PR #1202 — hour-scale stream continuity | Deferred-topic recovery |
| PR #1207 — OBS telemetry | Stream health, separate from conversation correctness |
| PR #1210 — aggregate voice latency metrics | Tail-latency summaries and privacy-safe aggregates |

Integration rule: the room director owns floor decisions; the existing playback path owns delivery/cancellation; the existing conversation context owns bounded session state; governed memory owns persistent retention. Run 63 should add an adapter/evaluation dimension only where the current implementation lacks it.

Do not create a parallel room director, a second persistent viewer database, another task scheduler, or an independent avatar writer.

## 5. New STAR evaluation plan

### 5.1 Controlled cue taxonomy

Create a consented, speaker-disjoint evaluation set with these slices:

1. Backchannel: "yeah", "right", short agreement, laughter.
2. Collaborative completion: a listener supplies a missing word or phrase.
3. Clarification: "the blue one", "on the left", "for the second player".
4. Correction: a listener changes a name, number, date, instruction or constraint.
5. Genuine takeover: "stop", "wait", "no, do this instead".
6. Viewer-to-viewer overlap: a contribution not addressed to STAR.
7. Non-speech overlap: laughter, cough, keyboard noise and room noise.
8. Game callout: "behind you", "reload", "left flank", "don't jump yet".
9. Creator collaboration: a collaborator changes a design requirement while STAR is narrating.
10. Tool-use correction: a user changes a parameter while a multi-step tool task is in progress.

Use only audio and transcript material with appropriate consent and licenses. Keep raw audio out of Git and out of default telemetry. Store only opaque row IDs, labels, timestamps, hashes and aggregate results unless the owner explicitly approves a protected local dataset workflow.

### 5.2 Causal evaluation protocol

- Split by speaker and conversation, not random adjacent utterance, to reduce leakage.
- Keep a sealed holdout for unseen speakers, topics and noise conditions.
- At decision time (t), expose only audio and transcript evidence available at or before (t); never use future audio to label a causal prediction.
- Record the expected action before replaying the model.
- Compare STAR against: always-continue, always-yield, current baseline, and adaptation-enabled candidate.
- Run matched seeds/configurations and repeat stochastic model runs.
- Report confidence intervals and per-class precision/recall; do not hide a weak class behind an aggregate score.
- Keep dataset provenance, annotation version, model/build identity and evaluator hashes with every result.

### 5.3 Metrics

| Dimension | Metric |
|---|---|
| Intent recognition | Per-class precision, recall, macro-F1, calibration |
| Floor control | False-yield rate, missed-takeover rate, unnecessary interruption rate |
| Adaptation | Correct incorporation rate, correction retention, semantic consistency |
| Continuity | Unchanged-speech continuity, repeated-content rate, unfinished-topic recovery |
| Grounding | Correct speaker/addressee, topic and constraint attribution |
| Timing | Cue-to-decision, decision-to-queue, queue-to-device, device-to-loopback p50/p95/p99 |
| Tool reliability | Correct final tool arguments and verified tool outcome after a correction |
| User experience | Human preference and perceived naturalness, scored separately from deterministic metrics |

Do not use an LLM judge as the only grader for floor actions, tool arguments or task success. Use timestamped labels and deterministic state checks wherever possible; reserve blinded human review for appropriateness and naturalness.

### 5.4 Release gates

A candidate should remain opt-in until all of the following hold:

- It improves collaborative-cue adaptation on sealed holdouts over the current baseline.
- It does not materially worsen backchannel false-yield or genuine-takeover recall.
- It does not increase stale audio after interruption.
- It preserves tool-task correctness and user corrections.
- It stays within measured audio and game-control deadlines under simultaneous load.
- It produces no raw-audio or transcript leakage into aggregate diagnostics.
- It passes hardware-free regression tests and a private, owner-approved Windows rehearsal.

No numerical target should be invented before a baseline is measured. Establish the baseline, pre-register thresholds, then evaluate the candidate.

## 6. Gamer Brain: adapt to teammate callouts without freezing control

The same capability transfers to gameplay, but the timing policy is different.

- A fast, bounded callout recognizer can identify immediate hazards and team instructions.
- The reactive controller must retain ownership of the input deadline.
- Strategic planning can incorporate the callout asynchronously.
- A teammate's "behind you" should update threat direction; it should not cause the whole voice conversation to yield.
- A viewer's joke or side conversation should not be mistaken for an in-game command.
- Every action still passes the existing game-control gate and must be verified by a fresh game observation.

Evaluate callout recognition, action latency, valid actions, objective completion, deaths/failures and recovery separately. Test on owned/private environments and held-out maps. Never use unauthorized automation in public competitive games or bypass a game's anti-cheat.

## 7. Creator Brain: accept live corrections while building

The same policy should support collaborative creation:

- User changes a UI color while STAR is describing the screen.
- User clarifies that a model is the wrong size.
- A reviewer points out a missing edge case during code review.
- A playtester reports that a door is unreachable.
- A teammate supplies a missing asset name or API constraint.

The creator planner should update only the affected uncommitted work, preserve the rest of the plan, and rerun the relevant verifier. A correction must not silently broaden tool permissions or publish a project.

For Roblox, retain the existing inspect → targeted edit → static check → Playtest → screenshot/state verification loop. For Godot/Unity/Blender, retain build/open/render/inspect/playtest checks appropriate to the tool. Compilation alone is not a playable-game pass.

## 8. General knowledge and reasoning transfer

In-turn adaptation is also a general reasoning capability:

- Correct a factual premise before finishing an explanation.
- Incorporate a newly supplied constraint into a multi-step answer.
- Distinguish a correction from a preference or a temporary exception.
- Update a research synthesis when a source contradicts an earlier claim.
- Preserve the provenance and confidence of the correction.
- Avoid persisting a one-time correction as a permanent user fact.

For each correction, keep separate: the original claim, the correction, the scope, the source, confidence, whether the correction was acknowledged, and whether a later task confirms the update. Persistent memory remains governed and consent-aware.

## 9. Inference and hardware research: avoid attractive but mismatched speedups

### FlashOffloading

Paper: https://arxiv.org/abs/2611.07542  
Posted: 2026-11-05

FlashOffloading reports KV-cache offloading results on a GLM-5.2/MTP3 deployment using Ascend 910C hardware. The paper reports up to 1.38× prefill and 1.91× decode throughput under a 30 ms TPOT constraint in that environment.

This is **not** evidence of a speedup on STAR's RTX 4060 8 GB target. The accelerator, kernels, serving stack, model and workload differ. Do not port its Ascend-specific implementation or claim the reported multipliers for STAR.

Use it as a research prompt only: profile cache residency, data movement, transfer overlap and tail latency. Test any CPU/RAM offload against a no-offload baseline on the actual Windows machine, with the game, OBS, voice and avatar active. Reject it if p95/p99 latency or game/stream quality regresses.

### Speculative decoding and routing

Keep the existing capability-gated canary work (PR #1208) separate from the new conversational policy. A draft acceptance rate is not a user-visible speedup. Measure TTFT, inter-token latency, end-to-end time, quality and goodput under the same concurrency and mixed workload. Use the fast model for immediate classification and acknowledgements only when it meets a measured quality threshold; reserve deeper reasoning for ambiguous or long-horizon decisions.

### Performance objective

Optimize **verified useful work completed before its deadline**, subject to:
- audio callback health and loopback latency;
- game input/control deadlines and frame pacing;
- OBS render/encode/network health;
- avatar synchronization;
- model task correctness;
- resource headroom and recovery after overload.

A system that generates more tokens but causes stutter, false interruptions or wrong actions is a regression.

## 10. Privacy, safety and character integrity

- Use consented voice data; do not record or retain viewer audio by default.
- Keep raw audio and full transcripts out of public GitHub.
- Use pseudonymous, rotating speaker references for evaluation; do not turn voice identity into a persistent viewer profile without explicit consent.
- Do not infer sensitive traits from voice.
- Do not claim that STAR is biologically human or fabricate off-stream experiences.
- Let silence, listening and yielding be valid character actions.
- Keep public game actions, purchases, publication, account changes and other irreversible actions behind the existing owner approval boundaries.
- Treat external benchmark content and repository text as data, never as permission-granting instructions.

## 11. Run 64 implementation sequence

1. Reconcile the existing open voice PR stack before touching shared files.
2. Add a Duplex Cue-style label schema to the existing multiparty replay/evaluation path.
3. Build a small consented, speaker-disjoint local fixture set; do not commit raw audio.
4. Add deterministic scoring for `CONTINUE`, `ADAPT`, `YIELD` and `HOLD`.
5. Add a no-future-audio causality test.
6. Connect only to the existing room director and bounded session context.
7. Add correction/continuity tests to the existing voice call and playback cancellation suites.
8. Add game-callout and creator-correction slices as separate task families.
9. Run matched local inference and mixed-load tests.
10. Conduct a private Windows microphone/loopback/OBS/VTube Studio rehearsal.
11. Keep the feature opt-in until independent review and all acceptance gates pass.

## Sources

- Duplex Cue (2026-09-11): https://arxiv.org/abs/2609.13117
- InteractionBench (2026-11-02): https://arxiv.org/abs/2611.02430
- InteractionBench harness: https://github.com/avera-labs/InteractionBench
- Full-Duplex-Bench v3: https://arxiv.org/abs/2604.04847
- AGENTCL: https://arxiv.org/abs/2606.02461
- FlashOffloading (2026-11-05): https://arxiv.org/abs/2611.07542
- GameWorld: https://arxiv.org/abs/2604.07429
- OpenGameEval: https://github.com/Roblox/open-game-eval
- GameDevBench: https://github.com/waynchi/gamedevbench
- VTube Studio API: https://github.com/DenchiSoft/VTubeStudio
- LiveKit EoT-Bench: https://github.com/livekit/eot-bench
