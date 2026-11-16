# STAR Run 62 — Full-Duplex Social Control, Avatar Scheduling, Continual Learning, and Hardware-Realistic Acceptance

**Research date:** 2026-11-15  
**Repository:** oncoursemail/Star-AI-Project  
**Branch:** research/run60-integration-gates-long-horizon-20261115-star-next  
**Base:** star/next  
**Purpose:** extend the Run 60–61 integration plan with newly published 2026 research and repair the exact-head test contract exposed by CI.

## Executive decision

STAR should become a more capable gamer, creator, researcher, and live character by improving the coordination and evidence quality of systems that already exist. Do not add another room director, voice engine, avatar writer, memory database, game controller, or resource scheduler.

Run 62 makes two concrete decisions:

1. Keep the existing Live2D/VTuber rig as STAR's default avatar path. Use new avatar-generation research to improve scheduling, interruption, audio/video synchronization, and evaluation—not as a reason to replace the established rig with a heavy neural video generator.
2. Evaluate natural conversation as a set of distinct interaction actions (yield, hold, backchannel, take turn, interrupt, recover, initiate, and remain silent) with both timing and follow-through. A system that merely detects speech or produces a fluent sentence is not yet a good live co-host.

This run also fixes a compatibility failure in the existing voice-latency tests: the Run 61 summary deliberately added mean, p99, and sample-readiness fields, while an older test still asserted the pre-Run 61 exact dictionary shape.

## 1. New research findings

### 1.1 DuplexAct — interaction behavior, not just transcription

Primary paper: https://arxiv.org/abs/2610.17738  
Date: 2026-10-13

DuplexAct defines eight interaction actions under 24 conditions. It evaluates 4,691 instances, including 2,531 derived from real conversational recordings, and scores both immediate execution and subsequent follow-through.

STAR application:

- Measure whether a backchannel occurs at the appropriate moment, not merely whether the words are semantically relevant.
- Distinguish yielding from selective interruption.
- Test whether an interruption is followed by a coherent recovery, not just whether playback stopped.
- Test proactive initiation separately from ordinary replies.
- Treat active silence as a valid action when the viewer is still speaking or the conversation does not require a response.
- Preserve timing and content as separate score dimensions.

### 1.2 MultiPartyTurnBench — group conversation floor control

Primary paper: https://arxiv.org/abs/2610.20172  
Date: 2026-10-14

MultiPartyTurnBench contains 240 channel-separated synthetic conversations with two to five speakers and six interaction types. It separates end-of-turn detection from interruption/floor-takeover detection. The paper reports that turn-entry performance can be strong while selective interruption remains close to chance for evaluated systems.

STAR application:

- Represent speaker, addressee, reply-to, topic/thread, floor owner, overlap, and delivery state as separate metadata.
- Do not interpret every overlapping utterance as a takeover.
- Do not yield to every backchannel.
- Use a bounded, session-local conversation index and the existing room director/task ledger.
- Keep an unanswered viewer question pending while gameplay takes priority.
- Add explicit recovery tests: stop stale audio, acknowledge the new speaker, preserve the interrupted topic, and resume only when appropriate.

The benchmark is synthetic and channel-separated. It is useful for controlled floor-control tests, but it does not replace live room rehearsal with real microphones, room acoustics, or Discord.

### 1.3 AVTR-1 — synchronized avatar motion and speech delivery

Paper: https://arxiv.org/abs/2609.22913  
Official repository: https://github.com/avaturn-live/avtr-1  
Model card: https://huggingface.co/avaturn-live/avtr-1

AVTR-1 describes a 153M-parameter motion generator conditioned on both participants' audio. Its surrounding stack adapts variable-size speech fragments to fixed-size motion windows, schedules frames for playback, synchronizes audio and video, and handles interruptions. The paper's central engineering lesson is that model inference speed alone does not create a responsive avatar: queueing, frame scheduling, committed playback windows, and cancellation semantics are part of user-visible latency.

**Important hardware finding for STAR:** the official model card reports 5-frame chunk latency of 232 ms on an RTX 4060, against 200 ms of video at 25 fps. That is a reported real-time factor of 0.86×, below the required rate. The same table reports 166 ms on an RTX 4060 Ti (1.2×) and 206 ms on an RTX 3060 Ti (0.97×). These are upstream published measurements, not STAR measurements, and do not include STAR's simultaneous game/OBS/voice load. Do not assume AVTR-1 will sustain 25 fps on the owner's RTX 4060 8 GB.

**Licensing gate:** the AVTR-1 repository describes separate licenses for the model, renderer, and streamer. The renderer and streamer are PolyForm Noncommercial with additional notices/patent terms; bundled InsightFace pretrained detector/landmark weights are also called out as non-commercial research use. The model card's community license is not a blanket license for every component. Do not vendor or deploy the complete stack for a monetized stream without reviewing every component license and obtaining any required commercial rights or replacing restricted dependencies.

STAR decision:

- Retain the existing Live2D rig as the default low-cost avatar path.
- Borrow AVTR-1's architectural ideas: explicit speech/frame segment IDs, bounded queues, one playback clock, committed-window semantics, interruption epochs, and stale-frame dropping.
- Keep mouth movement tied to actual playback/loopback timing, not merely text generation or TTS submission.
- Evaluate paired-audio responsiveness and interruption recovery; do not equate facial motion quality with social understanding.
- Treat AVTR-1 as a separately licensed research candidate, not an automatic dependency.

### 1.4 PATH-Bench — memory can help or interfere depending on history

Primary paper: https://arxiv.org/abs/2608.01149  
Date: 2026-08-02

PATH-Bench evaluates lifelong agents under controlled helpful and interfering task histories. It measures forward transfer, backward transfer, average performance, and forgetting. The authors find that the usefulness of memory depends on its representation and on the path by which experience accumulates. Their Selective Experience Use approach classifies retrieved experience as preserve, abstract, or ignore.

STAR application:

- Reuse the existing governed memory and skill systems; do not create a parallel store.
- Before injecting a retrieved memory, assess task relevance, provenance, freshness, conflict, and scope.
- Preserve exact evidence for concrete project facts; abstract reusable causal lessons for cross-task workflows; ignore irrelevant or contradictory items.
- Run probe tasks after positive and negative history sequences.
- Measure both forward transfer and forgetting.
- Keep private viewer memories separate from public/general skill memories.
- Never promote a memory or skill merely because it was retrieved frequently.

### 1.5 Continual AutoResearch — persistence improves efficiency, not necessarily final quality

Primary paper: https://arxiv.org/abs/2611.05108  
Date: 2026-11-03

Continual AutoResearch compares persistent and reset agents on matched task streams across nine task families. It reports that persistent state improved research efficiency for all five evaluated agents, but those process gains did not consistently produce better final held-out results.

STAR application:

- Measure time/cost to first valid solution separately from final held-out quality.
- Compare persistent-memory and reset baselines on the same ordered task stream.
- Keep a record of experiments, failed hypotheses, environment revisions, and artifact hashes.
- Require independent holdout evaluation before claiming a self-improvement.
- A faster research loop is not automatically a smarter model.
- External memory/skills improve access and procedure; they do not mean the foundation model's weights were retrained.

### 1.6 GameWorld — state-verifiable game outcomes

Primary paper: https://arxiv.org/abs/2604.07429  
Project: https://gameworld-project.github.io/

GameWorld evaluates 34 games and 170 tasks with state-verifiable progress and success. It emphasizes latency, valid actions, sparse feedback, long-horizon planning, and a separate real-time interaction challenge.

STAR application:

- Keep normalized progress separate from verified task completion.
- Keep paused/inference-friendly results separate from real-time results.
- Reuse STAR's existing FastLoop/SlowLoop split.
- Use deterministic game APIs where supported; otherwise use fresh visual observations and bounded input.
- Practice only in owned, offline, private, or explicitly permitted environments.
- Evaluate on held-out maps/seeds and report action validity, completion, recovery, and performance under real-time deadlines.

## 2. STAR-specific architecture decisions

### 2.1 One source of truth per responsibility

Retain the existing authorities documented in the STAR handoff:

- Room director / conversation-turn authority.
- Task and delivery ledger.
- Voice playback clock.
- Resource admission and host scheduling.
- GameControlGate and action receipts.
- Governed memory and skill promotion.
- Avatar frame pump / parameter arbitration.

New integrations should be adapters or measurements around these authorities, not competing owners.

### 2.2 Stream-event timeline

Add only missing metadata to the existing room/event path:

- monotonic event timestamp and session ID;
- speaker ID and resolved addressee;
- reply-to/topic ID where available;
- event kind (speech, backchannel, game event, moderator action, tool result);
- floor state (hold, yield, take, interrupt, recover);
- delivery state (queued, started, interrupted, completed, expired);
- pending question/task ID.

Keep the index bounded and session-scoped. Do not store raw audio, full transcripts, or viewer identifiers in performance telemetry by default. Persistent memory must still pass the existing memory-governance rules.

### 2.3 Avatar timing and interruption

For the existing Live2D path:

1. TTS/audio chunks receive a monotonically increasing segment ID.
2. Mouth/viseme envelopes and expression cues reference that segment ID and playback clock.
3. A barge-in increments an interruption epoch and cancels all not-yet-committed chunks from the previous epoch.
4. Only a short, explicit present window may remain committed; no unbounded stale audio or animation backlog.
5. Late avatar frames are dropped/coalesced; do not play old expressions after the conversation has moved on.
6. Idle motion is low-priority and yields to speech, gameplay reactions, and user-selected expressions.
7. Device loopback or a calibrated playback callback is required before claiming audible synchronization.

For a Live2D mascot, layered mouth assets/visemes and parameter arbitration are preferable to replacing the character with generated photorealistic video. Preserve the approved character design and user-controlled avatar settings.

### 2.4 Gamer Brain and Creator Brain

Keep immediate controls outside the deep LLM loop. The fast controller handles bounded movement/action primitives; the slower planner chooses goals, strategies, and recovery. The verifier checks actual game state or authoritative task completion.

For game creation, preserve the inspect → plan → edit → build → run → screenshot → playtest → repair → verify loop. A successful code-generation step is not proof of a playable game. Keep Roblox, Godot, Unity, Blender, and general computer-use scores separate.

### 2.5 General knowledge and research

Use claim-level evidence records with source URL, publication/retrieval time, scope, support/contradiction links, and confidence. Separate:

- parametric recall;
- retrieved factual claims;
- current web research;
- document-grounded answers;
- procedural skills;
- verified project state.

Use source freshness and contradiction checks for current facts. If evidence is missing, STAR should say that it does not know rather than silently converting a guess into memory.

## 3. Performance plan for the 8 GB VRAM class

Preserve the existing stable prompt-prefix layout and fast/deep model split. Do not load an additional draft model by default. The upstream llama.cpp speculative-decoding documentation lists multiple methods, but each method must be tested against the exact selected backend/model build.

Required paired tests:

- baseline vs candidate with identical model, prompt, context, slot count, seed, and load;
- prefill and decode measured separately;
- first-token latency and inter-token latency;
- draft acceptance and end-to-end response time for speculative methods;
- cache hit/reuse and restore correctness;
- quality/behavior non-inferiority on fixed holdouts;
- idle, voice-only, game-only, OBS-only, and simultaneous game+voice+avatar+OBS;
- game frame-time p50/p95/p99, audio underruns, OBS dropped frames, VRAM peak, queue age, and verified task goodput.

Do not copy benchmark numbers from a 32 GB or datacenter GPU to an RTX 4060 8 GB. Do not adopt KV-cache quantization, expert offload, or a draft model solely because a microbenchmark is faster. Reject optimizations that make voice, input, rendering, or OBS less stable.

Official upstream reference: https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md

## 4. Exact-head CI finding and compatibility repair

The latest inspected Run 61 offline workflow (run 6334, commit ca18c71474e26990cdcba7c8e09ae5e137bc986c) completed with:

- React UI compile/tests: success;
- Pyright basic/baseline gate: success;
- offline Python regression suite: failure;
- desktop workflow: skipped by changed-scope/runner policy.

The offline suite reported **2 failed, 16,543 passed, 427 skipped, and 686 subtests passed**. Both failures were in tests/test_voice_latency_summary.py, not the new metrics implementation:

1. test_nearest_rank_percentiles_and_excluded_errors still expected the old exact result shape without mean_ms, p99_ms, p95_sample_ready, or p99_sample_ready.
2. test_no_data_means_unknown_not_fast had the same stale exact-shape expectation for an empty sample.

Run 61 intentionally added those fields. The correct repair is to update the legacy test expectations to the new documented schema, not remove the new metrics or weaken the tests. The updated test should continue asserting that missing data is unknown, not zero latency, and that p99 remains unavailable below its sample-readiness guidance.

A separate PytestUnhandledThreadExceptionWarning appeared in a scripted voice test because its test double supplied a bare object where the acknowledgement worker expected a TTS object with synthesize. It was a warning, not one of the two failing assertions. Track it separately; do not conflate it with the latency-summary failures.

## 5. Acceptance matrix

| Domain | Minimum evidence before claiming success |
|---|---|
| Voice timing | Exact-head tests; real playback/loopback clock; enough samples for stated tail metrics |
| Full-duplex interaction | DuplexAct-style action + follow-through; false cutoff and missed interruption cohorts |
| Multiparty room | 2–5 speaker replay, overlapping backchannels, selective floor takeover, pending-question recovery |
| Avatar | playback-grounded mouth/viseme timing, interruption epoch, no stale frame backlog |
| Gaming | state-verified outcome, separate real-time track, held-out map/seed, action validity |
| Roblox creation | inspect/edit separation, scene checks, multiplayer/play checks, artifact hash |
| General knowledge | source-grounded factuality, contradiction handling, freshness, abstention |
| Continual learning | matched reset/persistent streams, positive/negative transfer, forgetting, sealed holdout |
| Inference | paired baseline/candidate under matched conditions and simultaneous load |
| Windows release | installed build, actual mic/speaker/virtual cable/OBS/VTube Studio, recovery and sustained rehearsal |

## 6. Run 63 engineering order

1. Repair the stale legacy latency-summary assertions and rerun exact-head offline tests.
2. Inspect the acknowledgement worker's test double and replace the bare object with a minimal typed fake; keep this a separate test-only fix if it is still noisy.
3. Connect aggregate latency summaries to the existing local diagnostics without persisting transcript/audio content.
4. Add DuplexAct-style action/follow-through cases to the existing voice-room evaluation.
5. Add MultiPartyTurnBench-inspired synthetic floor-control replays to the existing room director.
6. Add segment/epoch assertions to the existing avatar frame pump; keep one writer and one playback clock.
7. Add PATH-Bench-style helpful/interfering history sequences to the existing skill/memory evaluation.
8. Add matched persistent/reset task streams to STAR's research/evaluation harness.
9. Add GameWorld real-time held-out evaluation to the existing Gamer Brain; keep it distinct from Roblox Studio evaluation.
10. Run actual target-PC acceptance before changing production defaults or claiming speed/quality gains.

## 7. Scope and safety

This Run 62 change set is limited to research documentation, a research manifest, and a test compatibility correction. It does not:

- change model weights or model/provider routing;
- enable a new model or speculative-decoding mode;
- install AVTR-1 or its dependencies;
- change microphone, VAD, TTS, OBS, VTube Studio, or game-control settings;
- grant new tool permissions or expand autonomous action scope;
- change production defaults or merge into star/next.

No hardware speedup, general-intelligence gain, game mastery, live microphone/OBS acceptance, or public VTuber broadcast is claimed.
