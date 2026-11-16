# STAR Run 61 — Verified Capability Growth, Real-Time Streaming, and Mixed-Load Performance

**Research date:** 2026-11-15  
**Repository:** `oncoursemail/Star-AI-Project`  
**Branch:** `research/run60-integration-gates-long-horizon-20261115-star-next`  
**Base:** `star/next`  
**Status:** implementation + research; exact-head CI and native acceptance are required

## Executive decision

STAR already contains substantially more capability infrastructure than the v1.0 public product description alone suggests. The `star/next` handoff documents separate packages for hearing and speaking, fast/slow game control, learning from recorded gameplay, desktop computer use, a VTuber camera/rig, social rules, inner-life memory, and human-likeness evaluation.

The main gap is not a lack of ideas. It is **end-to-end integration and real acceptance on the target Windows PC**. Many components were tested with fakes, synthetic signals, or a development PC; their notes explicitly say that the real microphone, RTX 4060, Roblox/Minecraft sessions, Discord camera, and full stream were not accepted.

This run makes one bounded runtime improvement to voice measurement, then defines a shared evidence and acceptance strategy for the existing subsystems. It does not add a second scheduler, voice engine, memory database, game controller, or avatar writer.

## 1. Repository reality: what already exists

The current handoff and source map describe the following. These are code-presence statements, not claims that every feature is installed, enabled, or accepted on the owner's PC.

| Area | Existing source in `star/next` | Current evidence boundary |
|---|---|---|
| Local model/runtime | `star/agent.py`, `star/context_layout.py`, `star/local_runtime.py`, `star/brain_setup.py` | Stable prompt-prefix layout and first-token measurement exist; hardware A/B is still required |
| Voice/hearing | `star/senses/`, `star/voice/` | Loopback/mic capture, echo reference/cancellation, VAD, streaming transcript, playback buffer, acknowledgements and speculative reply paths are documented; prior work used synthetic/fake engines |
| Voice measurement | `star/voice/metrics.py` | Per-turn stage stamps existed; this run adds tail statistics and first-response/acknowledgement measurements |
| Gameplay | `star/play/` | FastLoop/SlowLoop, capture/perception, Roblox obby controller, Minecraft transport/skills and a bounded planner are documented; real game sessions are not established by the notes |
| Gameplay learning | `star/play/learn/` | Consent-based recording, session-level splits, imitation policy, paired candidate evaluation and rollback receipts exist; real owner gameplay data is still needed |
| Creator/game development | Roblox Studio, Luau checks, Blender and Studio Lab plans | Studio editing is opt-in and starts read-only; generated game quality still requires real scene and play checks |
| VTuber camera | `star/vtuber/` | Layered rig, pose events, lip-sync timeline, camera loop and VMC/virtual-camera sinks are documented; Discord device acceptance is outstanding |
| Desktop use | `star/computer/` | UI Automation, visual grounding, foreground checks, STOP checks and artifact verification are documented; broad cross-app acceptance is incomplete |
| Social/persona | `star/social/`, `star/emotion*.py`, `star/human_evals.py` | Social rules, persona checks, agency scenarios and blind comparison harness exist; full live A/B remains distinct from grader self-tests |
| Inner memory | `star/inner/` | SQLite episodes/cards/opinions/reflection and governance are documented; chat recall hooks and proactive outreach are gated/off where noted |
| Orchestration | `star/orchestration.py` | Dependency/ownership planning is documented as a pure planner, not a live multi-agent scheduler |

### Important product and acceptance distinctions

- The public v1.0 release is not the same thing as the richer `star/next` development tree.
- A package existing in a branch does not prove that the installer contains it.
- Fake-device tests do not prove microphone, speaker, virtual camera, or Discord compatibility.
- Synthetic gameplay does not prove that a policy can play Roblox or Minecraft well.
- A scene that passes static checks is not necessarily a playable game.
- A human-likeness grader self-test does not prove that viewers experience a natural live stream.
- A prompt, memory, or skill change does not prove that model weights became smarter.

Keep these distinctions visible in release notes and run reports.

## 2. New implementation: privacy-safe voice tail-latency summaries

### Why

A mean or median can conceal the slowest and most disruptive voice turns. Live conversation needs separate visibility into endpointing, transcription, model first-token, TTS/queue, acknowledgement, and first-audio submission. The existing `TurnMetrics` clock stamps already contain most of these stages, so a new telemetry subsystem is unnecessary.

### Change in `star/voice/metrics.py`

The updated `latency_summary()` now:

- Reports mean, p50, p95, p99, and maximum for each stage where samples exist.
- Marks p95 sample readiness at 100 samples and p99 readiness at 1,000 samples. The flags are conservative descriptive sample-volume guidance, not automatic release gates.
- Reports the number of samples for every stage independently.
- Separates first generated audio submission from the first response submission, which may be an acknowledgement clip.
- Adds first-sentence/TTS handoff stage measurements.
- Keeps valid partial-stage observations when a later stage is missing.
- Counts errored, incomplete, and invalid-clock turns separately.
- Rejects non-finite timestamps and impossible primary ordering rather than allowing them to improve tail metrics.
- Returns aggregate timings and counts only; it does not return user or assistant transcript text.

**Measurement limitation:** `first_audio_at` means a PCM chunk was submitted to the speaker queue. It does not prove the audio reached the physical output device or was heard by a person. The later acceptance path must add a device-loopback or playback-clock measurement if actual acoustic start is required.

### Regression coverage added

`tests/test_voice_metrics.py` now covers:

- Nearest-rank p50/p95/p99 on a deterministic 1,000-turn sample.
- p99 withheld until the 1,000-sample guidance threshold.
- Acknowledgement-first perceived response.
- Partial pipeline stages on an incomplete turn.
- Non-finite clock rejection.
- Transcript privacy in the summary.

The code is measurement-only. It does not change VAD thresholds, turn-taking, model routing, TTS, voice settings, or any default.

## 3. Research findings and STAR-specific decisions

### 3.1 Natural streaming: endpointing is a separate problem from inference

**LiveKit EoT-Bench** provides real human-to-agent turns in 14 languages and labels silence pauses of at least 100 ms as either hesitation or true end-of-turn. Its evaluation exposes the trade-off between false cutoffs and endpointing delay. The benchmark explicitly distinguishes endpointing latency from model inference latency.

Sources:
- https://github.com/livekit/eot-bench
- https://livekit.com/benchmarks/eot-bench

STAR decisions:

1. Keep false-cutoff rate and endpointing delay together on a Pareto curve.
2. Measure endpointing, ASR, model TTFT, TTS first packet, speaker-queue submission, and actual playback start separately.
3. Retain short-turn/HOLD-only examples as censored evidence; never fabricate an end timestamp.
4. Evaluate accented English, short replies, hesitation, multilingual turns, background speech, and interruptions as separate cohorts.
5. Add a distinct multiparty room evaluation: speaker identity, addressee, overlap, turn ownership, unanswered-question carryover, and interruptions are not fully measured by a single-speaker endpointing benchmark.

For the VTuber experience, one room/event timeline should carry timestamps and speaker/addressee IDs through the existing room director. A gameplay event may defer a viewer reply, but the question must remain in the task/turn ledger until answered, explicitly declined, or expired. Do not make the model re-read a long transcript to recover it.

### 3.2 Roblox Creator Brain: inspect before editing, and verify the play session

**OpenGameEval** evaluates 84 stateful Roblox Studio tasks with repeated attempts. It separates observation tools from editing tools and checks both the edited scene and a simulated play session. Its paper reports that runs inspecting relevant objects before editing performed better in matched analyses. The published model results are external benchmark results, not STAR results.

Sources:
- https://arxiv.org/abs/2610.02563
- https://github.com/Roblox/open-game-eval

STAR decisions:

- Pin benchmark, plugin, task roster, place files, evaluator, model, prompt, and attempt count.
- Report pass@1 and repeated-attempt consistency separately.
- Preserve observation coverage and EDIT/PLAY evidence.
- Require scene checks and play-session checks; a scene-only pass is not a completed game.
- Keep development, validation, and sealed holdout places/seeds separate.
- Use the external suite as an adapter, not as a replacement for STAR's own Roblox cases.

### 3.3 Gamer Brain: separate game mastery from game creation

**GameWorld** evaluates 34 games and 170 tasks. It reports both normalized progress and binary success from serialized game state. Its GameWorld-RT track keeps the environment running during inference, exposing latency-sensitive control.

Source: https://gameworld-project.github.io/

STAR decisions:

- Keep progress and state-verified success as different metrics.
- Add a real-time track where the game does not pause for model inference.
- Use the existing FastLoop/reflex controller for immediate actions and the SlowLoop/planner for objectives and strategy.
- Use game-specific APIs where legitimately available (for example, a supported Minecraft bot interface); use visual perception and bounded input only when no API exists.
- Measure action validity, reaction latency, completion, deaths/failures, recovery, and held-out-map transfer.
- Do not use automation to bypass anti-cheat or gain unfair advantage in public competitive games. Start with owned, offline, private, or explicitly permitted environments.

A general GameWorld result must not be described as Roblox performance, and a Roblox Studio result must not be described as general game-playing ability.

### 3.4 Creator Brain: visual feedback is part of correctness

**GameDevBench**, published in PMLR's ICML 2026 proceedings, contains 333 Godot game-development tasks across 2D graphics/animation, 3D, UI, and gameplay. The paper reports that visual feedback improved one evaluated configuration from 41.1% to 52.0%.

Sources:
- https://proceedings.mlr.press/v306/chi26a.html
- https://github.com/waynchi/gamedevbench

STAR decisions:

- Add screenshot/video inspection after a build, not just code review.
- Grade gameplay, scene structure, visual specification, asset correctness, UI interaction, and performance separately.
- Keep Godot benchmark results separate from Roblox/Studio results.
- Require at least one independent playtest and a holdout check before calling a generated game complete.
- Preserve editable source assets; do not flatten Roblox UI or rig/animation work into a screenshot.

### 3.5 General computer intelligence: intermediate checkpoints beat click counts

**WindowsWorld** contains 181 tasks across 17 desktop applications, averaging five subgoals per task; 78% are multi-application. The paper reports that evaluated agents performed poorly on multi-app tasks and struggled with conditional reasoning across three or more applications.

Sources:
- https://aclanthology.org/2026.findings-acl.750/
- https://github.com/HITsz-TMG/WindowsWorld

STAR decisions:

- Evaluate end-to-end workflows across multiple apps, not just isolated clicks.
- Grade intermediate state and final artifacts.
- Test focus loss, dialogs, restarts, missing files, unavailable apps, and blocked authentication.
- Include infeasible tasks where correct abstention is the expected result.
- Use a disposable VM and synthetic data for benchmark execution.
- Verify every important external side effect; a click acknowledgement is not task completion.

### 3.6 Continual learning: controlled transfer and interference

**AGENTCL** constructs task streams with known relationships so that positive transfer and interference can be measured. It warns that naive task streams and ordinary held-out scores can obscure what a memory design actually learned.

Source: https://arxiv.org/abs/2606.02461

STAR decisions:

- Pair skill-on and skill-off runs from the same initial state.
- Use compositional streams where an earlier workflow should help a later related task.
- Include unrelated streams to detect negative transfer.
- Keep sealed holdouts inaccessible to the candidate generator.
- Measure task success, repeated-run consistency, tool calls, token cost, time, and regressions.
- Promote only when independent evaluation shows a reliable gain; memory/skill writes must not edit graders, fixtures, permissions, or the promotion gate.

### 3.7 Inference speed: measure the serving path under matched conditions

The official llama.cpp SPEED-Bench client evaluates an already-running `llama-server`, reporting category throughput, latency, and speculative-draft acceptance. Its instructions recommend matching client concurrency to the server's slot count when throughput is the target.

Source: https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench

STAR decisions:

- Record the exact llama.cpp commit/build, model and quantization, context, GPU offload, cache settings, slot count, prompt set, output length, warmup, and concurrency.
- Compare baseline and candidate with identical prompts and settings.
- Measure prefill and decode separately; report TTFT, inter-token latency, output tokens/s, queue age, and end-to-end task goodput.
- Treat speculative decoding as a canary: draft acceptance and end-to-end latency both matter.
- Do not enable a new KV quantizer/cache format merely because a paper reports compression; verify support in the pinned backend and check output quality.
- Run a second mixed-load test with game, voice, avatar, and OBS active.

No benchmark result from another GPU/model can be transferred to STAR's RTX 4060.

### 3.8 General knowledge: separate parametric recall, grounded answers, search, and tool use

A broad "general knowledge" score hides several different failure modes. STAR should maintain separate evaluation tracks rather than treating a single trivia set as intelligence.

**FACTS Benchmark Suite** separates four factuality tasks: parametric knowledge (closed-book facts), search-assisted retrieval and synthesis, multimodal image questions, and grounding to supplied documents. The suite includes public and held-out private examples; its leaderboard is updated independently from STAR. This separation is useful because a model may remember a fact but fail to cite it, or search successfully but misread the source.

Sources:
- https://deepmind.google/blog/facts-benchmark-suite-systematically-evaluating-the-factuality-of-large-language-models/
- https://www.kaggle.com/benchmarks/google/facts/leaderboard

**SimpleQA Verified** provides 1,000 short-form factual prompts with additional de-duplication, topic balancing, and source reconciliation intended to reduce label noise in the original SimpleQA-style evaluation.

Source: https://arxiv.org/abs/2509.07968

**GAIA** evaluates real-world assistant tasks requiring combinations of reasoning, multimodal understanding, browsing, and tool use. It is more suitable for measuring whether the assistant can combine capabilities than for measuring isolated recall.

Source: https://arxiv.org/abs/2311.12983

**BrowseComp** contains 1,266 difficult browsing questions designed around hard-to-find, multi-hop information with short, verifiable answers. It tests search strategy and persistence, not ordinary conversational knowledge. Keep its evaluation examples and canary data out of training, public docs, and generated skill examples to reduce contamination.

Source: https://openai.com/index/browsecomp/

STAR decisions:

- Build a broad topic matrix: science, math, history, geography, languages, programming, art/design, games, practical software, and current events.
- Separate closed-book, document-grounded, web-search, multimodal, and multi-tool tasks.
- Score answer correctness, claim-to-source entailment, source freshness, contradiction handling, confidence calibration, and abstention separately.
- Store a compact evidence ledger for researched answers: claim, source, retrieval time, source type, support status, and expiry/freshness class. Keep raw user/private documents in the existing local knowledge store, not public telemetry.
- Require at least one primary or authoritative source for high-impact/current claims and independent corroboration when sources conflict.
- Treat retrieved pages, game chat, OCR, and tool outputs as untrusted data, never as instructions or permission grants.
- Preserve sealed holdouts; do not train STAR on public examples and then claim an uncontaminated score on the same examples.
- Use retrieval to improve access to current knowledge, but do not claim that retrieval has retrained or improved the model's parametric weights.

## 4. Shared runtime integration design

Use the existing authorities and add only the missing adapters/measurements.

### One task/run envelope

Every meaningful task should be attributable to a compact run record:

- run ID and parent run ID;
- domain: voice, game, creator, desktop, research, or knowledge;
- build/commit and model/runtime fingerprint;
- environment fingerprint (game version, place, application set, device class);
- start/deadline/cancel reason;
- resource budget and observed usage;
- tool/action references and authorization decision IDs;
- checkpoint outcomes;
- final verifier result and evidence references;
- whether the result is measured, inferred, simulated, or manually accepted.

Do not store raw viewer audio, video, full transcripts, passwords, or private project content in shared telemetry. Keep detailed local artifacts under the user's data directory with explicit retention.

### Priority and deadline policy

The single resource-admission authority should reserve capacity in this order:

1. Audio capture/playback callbacks and cancellation handling (never block these on model work).
2. Active game control deadlines and current conversation turn.
3. TTS generation and avatar frame delivery.
4. User-requested foreground coding/research.
5. Background practice, reflection, indexing, and speculative experiments.

The exact order between game control and a live voice turn must be scenario-aware, but background work must never starve either. Use bounded queues, deadlines, cancellation propagation, and stale-work dropping. Never accumulate avatar frames or game actions that are already obsolete.

### Domain-specific fast/slow loops

- **Voice:** deterministic VAD/turn logic and streaming ASR/TTS around the model; no second large-model call just to decide whether to interrupt.
- **Gaming:** fast perception/reflex/controller plus slower strategic planner. The LLM is not the 20 Hz motor controller.
- **Creator:** inspect → plan → edit → run → screenshot/state inspect → playtest → repair → verify.
- **Desktop:** accessibility/UIA first, visual grounding fallback, checkpoint after each meaningful state transition, explicit risk gate for irreversible actions.
- **Knowledge/research:** retrieval with source provenance, freshness, contradiction detection, and calibrated abstention.
- **Memory:** use existing stores; retrieve only task-relevant facts and preserve source/age/confidence. Do not create a second memory database.

### VTuber persona and social quality

STAR's existing human-evaluation suite already covers naturalness, consistency, warmth, personality, agency, mood fit, memory, AI truthfulness, and safety. Use it as a starting point, then add a live-room track with actual timing, speaker/addressee accuracy, interruption recovery, question carryover, avatar/audio sync, and viewer-rated comfort.

The target is a consistent, expressive AI character with natural pacing, humor, callbacks, opinions, and the ability to say no when context warrants it. Keep truthful AI disclosure when sincerely asked, age/safety rules, consent, and anti-manipulation checks. Do not optimize a benchmark by making STAR falsely claim human experiences or conceal that she is an AI.

Avatar-specific gap: the documented `starface` asset pack has painted mouths, so it cannot produce full phoneme mouth shapes without a separately approved layered avatar asset. The current rig's fake-sink frame rate is not evidence that Discord/OBS/Unity Capture works on the target PC.

## 5. System acceptance scorecard

| Domain | Primary outcome | Guardrail / failure measure | Required evidence |
|---|---|---|---|
| Voice | time to first response and natural turn-taking | false cutoffs, interrupted speech, audio underruns | real mic/speaker loopback, timestamped turns |
| VTuber | synchronized expressive avatar and room continuity | lip-sync drift, stale frames, dropped camera frames | real avatar + call/OBS rehearsal |
| Gamer | state-verified objective/win rate | invalid actions, frame-time loss, unsafe input | game state + action log + held-out map |
| Creator | playable, visually correct game | scene-only false pass, regression, multiplayer break | build artifact + scene/play checks |
| Desktop | cross-app task completion | irreversible misclicks, partial-state loss | checkpoint trace + final artifacts |
| Knowledge | grounded correct answers | unsupported claims, stale facts, bad abstention | claim/source ledger + freshness check |
| Memory | useful recall and transfer | irrelevant injection, contradiction, privacy leak | paired skill/memory-on/off evaluation |
| Inference | useful task goodput | p95/p99 latency, VRAM/CPU pressure | paired baseline/candidate load test |
| Long horizon | success and recovery over longer tasks | reliability decay, duplicate actions, false completion | repeated episodes at 1/4/8/16/32+ steps |

Do not collapse these into one opaque "intelligence score." Keep per-domain outcomes, confidence intervals, task counts, and evidence provenance visible.

## 6. Ordered engineering plan

### Phase 0 — establish the real baseline
- Inspect the current `star/next` head and exact open-PR dependencies before each integration.
- Run the human-evaluation grader self-test, voice benchmark, gameplay fake suite, creator evaluation, and existing general foundation suite.
- Capture one hardware inventory and model/runtime fingerprint on the actual STAR PC.
- Do not run heavy jobs while the owner is active; respect the existing PC guard and night-school schedule.

### Phase 1 — observability and reliability
- Land and CI-verify the tail-latency summary in this run.
- Connect summaries to the existing local diagnostic/report path without transcript retention.
- Add run IDs, deadline/cancel reason, and checkpoint references to the existing task ledger where the field is missing.
- Add tests for cancellation, stale queue eviction, idempotent retries, and process restart recovery.

### Phase 2 — VTuber acceptance
- Run the exact EoT-Bench adapter on a pinned v1.1 dataset revision.
- Run live microphone, virtual cable, speaker loopback, and acoustic-start tests.
- Connect the actual audible speaker clock to lip-sync; test interruption fade/cancel and audio/avatar drift.
- Verify Discord and OBS camera enumeration on the target Windows PC.
- Run a private 30-minute rehearsal with a small consenting audience before any public stream.

### Phase 3 — game mastery and creation
- Run GameWorld-RT in an approved sandbox and OpenGameEval in disposable Roblox Studio places.
- Record owner gameplay only with explicit consent and game-window-only capture.
- Evaluate imitation policies against held-out maps/seeds and compare against the incumbent.
- Add GameDevBench as a separate Godot adapter; keep Roblox grading separate.
- Require actual play-session and visual verification for generated games.

### Phase 4 — generalist desktop and knowledge
- Add WindowsWorld-style cross-app tasks with intermediate checkpoints and infeasible/abstention cases.
- Add source-grounded general-knowledge tasks with freshness, contradiction, and calibration checks.
- Test memory/skill transfer with controlled compositional streams and negative-transfer holdouts.

### Phase 5 — performance
- Run matched SPEED-Bench baseline/candidate trials on the exact local model/server build.
- Benchmark prompt prefill, decode, queue wait, first audible response, and task goodput.
- Repeat with the game, avatar, voice, and OBS simultaneously active.
- Promote only optimizations that improve useful throughput without violating voice, FPS, audio, VRAM, or quality guardrails.

## 7. What this run changed and did not change

### Changed
- `star/voice/metrics.py`: tail percentiles, sample-readiness flags, acknowledgement-first response timing, additional stage metrics, partial-stage accounting, and invalid-clock rejection.
- `tests/test_voice_metrics.py`: deterministic tests for p99/sample readiness, privacy, acknowledgements, incomplete turns, and non-finite clocks.
- This research document and its source manifest.

### Not changed
- No model weights, provider, model route, prompt, VAD threshold, TTS engine, microphone device, OBS setting, VTube Studio setting, game controller, permission, scheduler, memory store, or production default.
- No new dependency or dataset download.
- No generated skill execution or automatic promotion.
- No benchmark dataset was executed in this documentation/connector run.
- No physical RTX 4060, microphone, virtual cable, Discord, OBS, VTube Studio, Roblox Studio, Minecraft, or public-stream acceptance is claimed.

## 8. Primary references

- LiveKit EoT-Bench: https://github.com/livekit/eot-bench
- OpenGameEval paper: https://arxiv.org/abs/2610.02563
- OpenGameEval code: https://github.com/Roblox/open-game-eval
- GameWorld: https://gameworld-project.github.io/
- GameDevBench paper: https://proceedings.mlr.press/v306/chi26a.html
- GameDevBench code: https://github.com/waynchi/gamedevbench
- WindowsWorld paper: https://aclanthology.org/2026.findings-acl.750/
- WindowsWorld code: https://github.com/HITsz-TMG/WindowsWorld
- AGENTCL: https://arxiv.org/abs/2606.02461
- llama.cpp SPEED-Bench: https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench
- STAR working agreement: https://github.com/oncoursemail/Star-AI-Project/blob/star/next/AGENTS.md
- STAR architecture map: https://github.com/oncoursemail/Star-AI-Project/blob/star/next/docs/ARCHITECTURE.md
- STAR Run 60 integration plan: https://github.com/oncoursemail/Star-AI-Project/blob/research/run60-integration-gates-long-horizon-20261115-star-next/docs/research/STAR_20261115_RUN60_INTEGRATION_GATES_AND_LONG_HORIZON_RELIABILITY.md
