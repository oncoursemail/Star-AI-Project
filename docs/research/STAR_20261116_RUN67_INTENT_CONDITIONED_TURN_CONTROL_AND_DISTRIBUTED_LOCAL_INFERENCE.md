# STAR Run 67 — Intent-Aware Voice Control, Transferable Game Skills, and Distributed Local Inference

**Reviewed:** 2026-11-16  
**Scope:** research + offline evaluation infrastructure; no production runtime defaults changed  
**Parent work:** PR #1212 (Run 66), with related research in PR #1211

## Executive decision

Run 67 adds an offline evaluator for the policy above voice activity detection: whether STAR should respond, backchannel, yield the floor, hold for more context, or ignore non-addressed speech. This is separate from the frame-level VAD/endpointer already in star/voice/turn.py and the gameplay event evaluator in star/gameplay_commentary_eval.py.

The research supports five engineering decisions:

1. **Turn-taking must be intent-conditioned.** End-of-speech is not the same as an invitation to speak. The policy must distinguish an addressed request, a takeover, a backchannel, a handoff, side conversation, and uncertainty.
2. **Measure the entire interaction.** Correctly stopping playback is not enough; STAR must resume, answer the actual request, and avoid losing the previous conversation.
3. **A playable game is a completed journey, not a successful build.** Require real input, objective completion, save/reload, and regression checks.
4. **Learning must be selective.** Measure positive transfer, negative interference, and forgetting separately; do not turn every experience into permanent memory.
5. **Use multiple machines for independent work, not imaginary pooled VRAM.** Distributed request routing can increase concurrent capacity, but does not make one in-flight generation faster.

The new code is an evaluator, not a live speech classifier, microphone listener, streamer, game controller, or autonomous runtime.

---

## 1. Repository reality check

The public main README describes STAR v1.0 as a local-first Windows chat application with a local 4B Vulkan model, an optional Linux STAR Server, Roblox-oriented assistance, web search behind opt-in settings, and a 300-task server-side practice loop. It says the bundled lesson file is empty and that the learning loop changes reviewed text lessons and checked examples, not model weights. Basic optional voice calls exist; streaming-grade voice/VTuber integration is still described as coming soon.

Relevant existing foundations:

- **star/voice/turn.py:** frame-level VAD hysteresis, pause/resume/endpointer decisions, barge-in gating, and a simulated energy-based EchoGate.
- **star/voice/call.py:** cancellable reply workers, sentence/TTS chunking, speaker queue control, and conversation history limited to text/audio that was actually played.
- **star/voice/metrics.py:** aggregate per-stage latency accounting; queue submission is not proof of acoustic playback.
- **docs/ARCHITECTURE.md:** stable prompt-prefix layout, append-only conversation history, volatile per-turn context, cache_prompt, and stable slot behavior for owned llama.cpp servers.
- **star/lessons.py and docs/SELF_LEARNING_LOOP.md:** evidence-backed lesson candidates, paired evaluation gates, provisional trials, owner review, and no automatic model-weight updates.

The current voice detector does not itself decide speaker addressee or conversational intent. That is the gap this run measures. The existing gameplay evaluator measures whether a stream event deserves commentary; this new voice evaluator measures how the assistant should manage the conversational floor. Neither is wired into production.

Do not describe research branches as features shipped in the v1.0 installer. The latest Run 66 exact-head GitHub Actions runs completed successfully before Run 67 edits: offline checks #6355 and desktop/Windows build #3402. Run 67 requires its own exact-head checks.

---

## 2. Full-duplex speech: intent before interruption

### HiThink Turn — 2026-09-28

Paper: https://arxiv.org/abs/2609.34096

HiThink Turn separates response intent from semantic completeness and conditions its turn-state prediction on whether the assistant is speaking. It trains on truncated audio prefixes and reports processing in 240 ms audio chunks. On its evaluated Full-Duplex-Bench interruption setting, the paper reports interruption success increasing from 89% to 98% and mean stop latency decreasing by 60.9%.

**Interpretation for STAR:** 240 ms is a chunk size, not an end-to-end latency promise. The valuable idea is the state-conditioned intent decision: the same words mean different things while STAR is speaking versus listening. Reuse the current playback state; do not create another audio clock.

### TurnBench — 2026-09-16

Paper: https://arxiv.org/abs/2608.25218

TurnBench provides a 30-hour hand-labelled dyadic conversation corpus and a standardized evaluation protocol for end-of-turn and interruption detection. This is useful for measuring timing and boundary decisions on human conversation rather than only synthetic pauses.

### TACT — 2026-09-23

Paper: https://arxiv.org/abs/2609.27372

TACT contains 9,728 episodes / 73.2 hours across five dyadic corpora, with dialogue history, speaker profiles, and posterior labels over six intent classes. The paper reports that its best evaluated system reaches 0.47 against a human topline of 0.86, and that its intent-conditioned scoring agrees with human judgements more strongly than binary timing windows (Spearman 0.81 versus 0.46).

**Interpretation:** a single fixed “respond within N milliseconds” metric is not enough. Reflective silence, a backchannel, an interruption, and a request addressed to someone else need different timing expectations.

### Speak or Stay Silent — 2026-03-12

Paper: https://arxiv.org/abs/2603.11409

This work studies multi-party conversation and reports a benchmark with more than 120,000 labelled conversations across three corpora. Its central observation is that pauses are common in group conversation and are not automatically invitations for an assistant to speak. The authors report zero-shot turn-taking weaknesses and improvements from explicit training.

### Full-Duplex-Bench v3 — 2026-04-06

Paper: https://arxiv.org/abs/2604.04847

This benchmark uses real human audio with annotated disfluencies and chained API tasks. Its results show trade-offs between latency, turn-taking, interruption avoidance, and multi-step task accuracy; the fastest configuration is not automatically the best conversational participant.

**Engineering conclusion:** evaluate action correctness, interruption selectivity, addressee recognition, follow-through, grounding, and client-heard latency as separate measures. Do not collapse them into a “human-like” score.

---

## 3. Run 67 implementation: intent-aware turn policy evaluator

New module: **star/voice/turn_policy_eval.py**  
Tests: **tests/test_turn_policy_eval.py**

The evaluator scores five policy actions:

| Action | Intended meaning |
|---|---|
| respond | Take the floor when STAR is listening and a response is appropriate |
| backchannel | Give a short acknowledgement while the other person retains the floor |
| yield | Stop or relinquish STAR's current turn so the other speaker can continue |
| hold | Wait for more context rather than guessing |
| ignore | Do not enter a non-addressed side conversation |

It reports:

- Overall and per-action precision / recall / F1 / confusion.
- Accuracy by intent class and by assistant playback state.
- Missed true yields and false yields on backchannels, side conversations, and uncertain events.
- Follow-through after correctly selected yields.
- Addressee true/false positives and false/missed target rates.
- Decision p50/p95/max, missing timestamps, and deadline success.
- Null for unobserved evidence; no imputation and no composite score.

The evaluator accepts only bounded metadata and synthetic case IDs. It does not accept raw audio, transcripts, platform usernames, speaker IDs, or tool commands. A dataset owner must separately ensure consent, anonymization, speaker-disjoint splits, and licensed evaluation use.

### Integration rule

The future runtime adapter may consume the existing TurnEvent, playback state, and speaker/addressee estimates. It must not replace TurnDetector, CallSession, the speaker queue, or the current action-permission authority.

For any actual runtime integration:

1. Keep microphone capture and audio callbacks bounded and non-blocking.
2. Run ASR / intent estimation away from the real-time callback.
3. Use one monotonic playback clock and explicit response/segment IDs.
4. Cancel unplayed output on a true takeover; never rewrite audio already heard.
5. Retain only the text/audio actually played in conversation history.
6. Reconcile the interrupted request and its follow-up before marking it complete.
7. Fall back to the existing turn behavior if the intent model is missing, slow, or uncertain.

---

## 4. VTuber streaming: design the whole show, not just TTS

A natural AI streamer needs coordinated subsystems, but they must remain subordinate to one conversation/session authority.

### Recommended stream director

Use a priority-and-expiry queue over existing event sources, not a second scheduler:

- **P0 — direct interaction:** a viewer speaking to STAR, a safety issue, or an explicit host instruction.
- **P1 — high-value live event:** a decisive game moment, teammate callout, surprising result, or creator milestone.
- **P2 — audience chat:** selected messages, follow-up questions, and callbacks.
- **P3 — background work:** research summaries, low-priority notifications, and clip candidates.

Each pending item needs an event timestamp, source, confidence, relevance, expiry, and a delivery receipt. Drop stale reactions instead of narrating them after the moment has passed. Never let a P2/P3 event block live audio or controller input.

### Naturalness features worth building

- Addressee-aware conversation and multi-viewer floor control.
- Contextual backchannels, pauses, self-correction, and interruption recovery.
- Topic continuity with explicit unanswered-question tracking.
- Short and long commentary modes based on gameplay intensity.
- Event-triggered commentary plus measured silence compliance.
- Word-timed captions derived from actual TTS output, not guessed token timing.
- One avatar parameter authority; expression blending must not let separate modules fight over eyes, mouth, or body pose.
- A consistent playback clock for audio, captions, and Live2D mouth motion.
- Session recap and clip candidates only after the event is verified.
- Viewer privacy, opt-in retention, rate limits, moderation, and clear disclosure that STAR is an AI character.

“Human-like” should mean fluid timing, useful context, personality, humour, listening, and reliable follow-through—not pretending to be a human or fabricating personal experiences.

### Comparative architecture study: Kira AI

Reference: https://github.com/JonathanDunkleberger/Kira_AI

Its public README describes a multimodal VTuber with local speech perception, Live2D/VTube Studio control, word-synced captions, multi-platform streaming, priority lanes, and a single active-turn arbiter. It also documents a game-specific Pokémon agent using structured game state for decisions and vision for presentation.

Useful patterns to study (not copy):

- One active-turn authority for voice, reactions, and chat.
- Priority lanes and TTL expiry for pending reactions.
- Word-timed captions linked to actual speech output.
- Separate fast triage from deeper reasoning.
- Game-specific state adapters and explicit recovery loops.

**License boundary:** the repository declares AGPL-3.0. Do not copy its code, assets, or substantial implementation into STAR without a separate compatibility/legal review. Its performance and gameplay milestones are project-reported claims, not independent benchmark results.

---

## 5. Gamer Brain: fast control plus verified strategic learning

### Generalist policies

- SIMA 2: https://deepmind.google/blog/sima-2-an-agent-that-plays-reasons-and-learns-with-you-in-virtual-3d-worlds/
- NitroGen: https://nitrogen.minedojo.org/
- NitroGen code: https://github.com/MineDojo/NitroGen

Use these as research candidates for two different levels:

- **Fast policy:** propose low-latency visual/controller actions.
- **Strategic brain:** maintain the objective, world model, route, inventory, team strategy, and recovery plan.

Do not assume a single-frame action policy provides long-horizon planning or self-improvement. NitroGen's own project description distinguishes its released vision-action policy from those higher-level capabilities. Review model/data licensing and target hardware before any download or use.

### Environment adapter contract

For supported games, define a narrow adapter with:

- observe() — stable game state or screenshot plus metadata.
- legal_actions() — actions allowed by the game/test harness.
- act() — bounded controller action.
- reset() — known initial state for repeatable trials.
- snapshot() — stable state for independent verification.
- objective_status() — progress and actual completion.
- save_and_reload_check() — persistence verification where applicable.

Prefer documented APIs, official test harnesses, and game-provided telemetry. For games without a supported state API, use visual perception and verify with observable outcomes. Do not read or alter protected process memory, bypass anti-cheat, or automate online play where prohibited by the game's terms.

### Learning and skill transfer

Track separately:

- First-attempt success.
- Repeated-attempt improvement.
- Time and action count to completion.
- Deaths / resets / recoveries.
- Resource efficiency.
- Team objective contribution.
- Skill transfer to unseen games.
- Regression on previously mastered games.

A reusable skill is a candidate until it passes a new-game holdout. A high score on the same game used for practice is not evidence of transfer.

---

## 6. Creator Brain: complete-game acceptance

### GameASG-Bench — 2026-09-18

Paper: https://arxiv.org/abs/2609.21293

GameASG-Bench defines a pre-generation evaluation interface and combines static source checks with browser-executed semantic checks and real input. Across its 47 tasks, the highest reported mean L2 check pass rate is 93.2%, while the highest strict task success rate is 55.3%. This shows how component-level scores can hide end-to-end failures.

### CEGame-Bench — 2026-10-19

Paper: https://arxiv.org/abs/2610.26098

CEGame-Bench evaluates long-horizon creation across Defold, Godot, Roblox Studio, Unity, and Unreal Engine. It reports runs averaging up to 295 steps and 65 million tokens; only 16% of agent runs reached the game ending in the reported setup. Its Game Completion Boost skill improved execution-based scores by 14.1–24.3 points for three evaluated models.

**STAR acceptance contract:**

1. Parse requirements into observable behaviours and invariants.
2. Inspect the existing project before editing.
3. Build in an isolated test copy/place.
4. Start the game and send real player input.
5. Verify the main loop, objectives, UI, failure/retry, and multiplayer boundaries.
6. Reach the defined ending or completion state.
7. Save, close, reload, and verify persistence.
8. Run regression and performance checks.
9. Preserve screenshots/logs as evidence, excluding secrets and private player data.

A successful compile or generated script is not a completed game.

---

## 7. Memory and general knowledge: selective, evidence-backed learning

### PATH-Bench — 2026-08-02

Paper: https://arxiv.org/abs/2608.01149

PATH-Bench studies how the sequence of helpful and interfering experiences changes forward transfer, backward transfer, and forgetting. It motivates Selective Experience Use rather than blindly injecting all prior experience.

Apply this to STAR's existing lesson and memory authorities:

- Keep source/provenance and timestamp with every learned fact or skill.
- Scope lessons to project, engine, game, or user preference; do not generalize a one-off instruction.
- Retrieve only when relevant to the current task.
- Track counterexamples and expiry.
- Test positive transfer and negative interference.
- Re-test earlier skills after new learning.
- Keep evaluation code and holdouts protected from self-modification.
- Continue using the existing paired gate and owner review; do not add another memory database or automatic weight-training loop.

For general knowledge, keep parametric recall, retrieved sources, project memory, and personal memory distinct. Answers about current facts should include source date and confidence; conflicting evidence should be surfaced, not silently merged. Unknown or stale information should trigger abstention or research rather than confident invention.

---

## 8. Long-horizon recovery

### CUA-Recovery — 2026-10-20

Paper: https://arxiv.org/abs/2610.27645

The benchmark contains 2,250 human-verified erroneous states over 100 tasks and 8.6K recovery trajectories across 377 tasks. The reported agents have difficulty recognizing inherited errors and completing recovery. This reinforces the need for explicit checkpoints.

Use a single recovery protocol across game creation, desktop work, and multi-step research:

OBSERVE → CHECKPOINT → DETECT DIVERGENCE → LOCALIZE CAUSE → REPAIR → VERIFY → RESUME

A failed subtask must not silently mark the parent task complete. Recovery should preserve the last verified state and never repeat an irreversible action blindly.

---

## 9. Faster local inference: what is actually promising

### Preserve STAR's prompt-cache architecture

docs/ARCHITECTURE.md describes a deliberately stable prompt prefix and append-only history to reuse llama.cpp prompt cache. Do not add per-turn status, retrieved memories, timestamps, or stream state to the stable prefix. Keep volatile context at the end. This is one of the most concrete existing performance optimizations and should not be broken by new features.

### MiniLlama-Infra — SC26 workshop paper (2026)

Publication: https://www.computer.org/csdl/proceedings-article/sc-w/2026/122100b191/2lkuESKUzJK

This study reports that naive INT8 GEMV on an RTX 4060 Laptop made a small Llama-3.2-1B kernel slightly slower (289.1 to 298.5 microseconds), while a warp-cooperative mapping reduced that kernel latency to 52.3 microseconds. Its W8A8 decoding measurements report 15.8% gain on the RTX 4060 Laptop and 12.8% on A100.

**Limitations:** custom CUDA engine, one small model, a narrow set of prompts/shapes, ten repetitions per prompt, and laptop RTX 4060 hardware. These are not desktop STAR results and are not evidence that converting STAR's model to INT8 will make it faster. The lesson is to measure kernels, memory traffic, and end-to-end generation together.

### llama.cpp speculative decoding

Official documentation: https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md  
Upstream issue example: https://github.com/ggml-org/llama.cpp/issues/25345

A draft model being loaded does not prove that speculation is active. Upstream reports describe configurations where a draft was resident but no speculative initialization/acceptance occurred. A benchmark must verify draft initialization, accepted draft tokens, target verification, and output quality. Do not pay the VRAM/RAM cost of a draft model when the measured acceptance and end-to-end latency do not improve.

### NVIDIA PAIR — distributed local requests

Official docs: https://docs.nvidia.com/local-ai/nvpair  
Repository: https://github.com/NVIDIA/Personal-AI-Router

PAIR can route independent compatible inference requests to eligible local nodes and encrypt node-to-node traffic with mutual TLS after explicit pairing. It does not pool GPU memory, shard one model across machines, or split an in-flight request. Adding nodes can improve concurrent throughput; it does not make one generation faster.

**STAR recommendation:** evaluate PAIR only as an optional experiment for independent background research, practice, summarization, and sub-agent requests on idle machines. Keep live voice and latency-sensitive gameplay on the warm, local route. Do not install or enable it automatically. Pair only trusted machines on a trusted network; check model/engine compatibility, logs, firewall behavior, and data locality first.

### Matched performance protocol

Run one-factor-at-a-time A/B tests with the same model, quantization, prompt, context, engine build, and concurrency. Record:

- Cold and warm TTFT.
- Prompt tokens/second and decode tokens/second.
- Client-observed first useful token/audio.
- p50 / p95 / p99 latency and queue wait.
- GPU memory peak, CPU RAM, CPU/GPU utilization, thermals, and power.
- Cache hit/prefix reuse and context depth.
- Speculative draft initialization, acceptance, and rejected tokens.
- Game FPS, OBS encode lag, avatar dropped frames, audio underruns.
- Verified task goodput: successful tasks per wall-clock hour.

Test idle, gaming-only, voice-only, streaming-only, and simultaneous mixed-load cases. A faster model configuration that causes audio glitches, frame drops, or worse task accuracy is not an improvement.

For the 8 GB RTX 4060 class, preserve headroom for the game, OBS, voice, and avatar. Do not load a second GPU-resident draft model by default. Benchmark CPU draft or no speculation first; only retain a speculative path if exact-head measurements show a real win.

---

## 10. Run 68 implementation sequence

| Priority | Work | Acceptance evidence |
|---|---|---|
| P0 | Complete Run 67 exact-head CI | All required offline, type, frontend, and Windows jobs green |
| P0 | Review turn-policy evaluator | Synthetic edge cases and no runtime side effects |
| P1 | Add consented, speaker-disjoint turn-taking fixtures | Intent/action coverage and human adjudication |
| P1 | Integrate an optional intent estimator behind existing voice authority | Callback remains non-blocking; fallback to current detector |
| P1 | Playback-grounded caption/avatar synchronization | Captions and mouth motion follow actual playback segments |
| P1 | Stream event queue with priority + TTL | Stale events expire; P0 never blocked by P1–P3 |
| P1 | Game environment adapter contract | Stable snapshots, legal actions, objective oracle, save/reload |
| P1 | Cross-game transfer and forgetting suite | Unseen-game holdouts; report transfer and regression separately |
| P1 | Complete-game creation contract | Real-input completion, persistence, and regression proof |
| P2 | Optional PAIR lab | Independent-request throughput and trust-boundary audit |
| P2 | RTX 4060 mixed-load matrix | Matched baselines and p95/p99 plus FPS/audio/encode metrics |
| P2 | Long private VTuber rehearsal | No lost turns, stale commentary, caption drift, or unrecovered interruption |

## Non-goals / safety boundaries

- No claim of human consciousness or human identity; STAR is an AI character.
- No automatic model-weight updates or self-editing of evaluators/holdouts.
- No automatic installation of research dependencies, models, datasets, or external services.
- No unreviewed AGPL code/assets copied from comparative projects.
- No online-game automation that violates a game's terms or anti-cheat rules.
- No viewer identity or raw conversation retention by these offline evaluators.
- No changes to OBS/VTube Studio, microphone, controller, model routing, permissions, or production defaults in this run.
- No speedup, game mastery, or live-stream success claimed without target-hardware evidence.

## Run 67 changed files

- **star/voice/turn_policy_eval.py** — new offline intent-aware turn-policy evaluator.
- **tests/test_turn_policy_eval.py** — deterministic edge-case and metric tests.
- **docs/research/STAR_20261116_RUN67_INTENT_CONDITIONED_TURN_CONTROL_AND_DISTRIBUTED_LOCAL_INFERENCE.md** — this research and integration plan.
- **docs/research/STAR_RUN67_RESEARCH_MANIFEST.yaml** — source inventory and reproducibility record.
