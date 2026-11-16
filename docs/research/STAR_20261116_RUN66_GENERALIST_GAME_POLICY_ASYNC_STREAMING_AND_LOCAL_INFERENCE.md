# STAR Run 66 — Generalist game policy, asynchronous streaming intelligence, and local inference

**Research date:** 2026-11-16  
**Status:** research + offline evaluation infrastructure; no runtime adapter, model, permission, or default changed.

## Executive finding

The next useful step is not to bolt another large model onto STAR. It is to make the existing local-first app coordinate three different time horizons without letting them compete:

1. **Reflex horizon:** low-latency perception and bounded input control.
2. **Reasoning horizon:** goals, planning, tool use, research, and recovery.
3. **Learning horizon:** replay, skill extraction, retention, transfer, and held-out evaluation.

For streaming, use the same separation:

- a real-time loop owns capture, turn-taking, audio playback, and avatar timing;
- an asynchronous work loop researches, plans, or calls skills against a captured context snapshot;
- only the playback owner may speak, and a result must still be relevant when it returns.

This document audits the current repository and open work, reviews new primary research, and specifies an integration order. It does **not** claim that any unmerged PR or research prototype is shipped.

## 1. Current STAR baseline — verified from the repository

The current main README describes STAR as a Windows 11, local-first chat and Roblox development app. It supports a local 4B model on a Vulkan graphics card with about 8 GB VRAM, or an owner-operated Linux server; hosted providers are opt-in and there is no silent cloud fallback. The README says the model-quality change from v0.9 to v1.0 was inconclusive, so this plan does not claim that the current model is already smarter.

Relevant source architecture:

- **star/agent.py**: model/tool loop and request context.
- **star/context_layout.py**: stable system prefix, append-only history, and volatile per-turn context.
- **star/local_runtime.py**: explicit llama-server.exe launch, loopback binding, and one resident model (--models-max 1).
- **star/evals.py**, **star/eval_runner.py**, **star/eval_checks.py**, **star/eval_gate.py**, **star/eval_stats.py**: task definitions, execution, scoring, and paired statistical promotion gate.
- **star/knowledge.py**, **star/memory.py**, **star/lessons.py**: project-scoped knowledge and governed learning.
- **star/orchestration.py**: dependency/ownership planning; the root AGENTS.md explicitly says this is not yet a live multi-agent scheduler.
- **star/policy.py**, **star/studio.py**, and **star/studio_loop.py**: capability enforcement and scoped Roblox Studio interaction.

The current docs/SELF_LEARNING_LOOP.md is explicit: night school changes lessons/worked examples, not model weights. A lesson must carry evidence and pass a protected paired comparison; the model cannot edit the grader, evaluation suite, or promotion gate.

The current README labels Studio Lab, end-to-end Blender, and voice streaming upgrades as coming soon or opt-in rather than generally shipped. Keep those distinctions in release notes and UI.

## 2. Open work to integrate rather than duplicate

As inspected on 2026-11-16, the repository has several open draft PRs that already cover major parts of the requested direction. They are not in main and must not be described as shipped:

| PR | Existing work | Integration concern |
|---|---|---|
| #1178 | Voice runtime, persona, bridge, and natural-streamer research | One playback/voice authority; don't add a second persona or audio engine |
| #1182 | Fail-closed screen-to-controller game gate | Every gameplay policy must pass this gate |
| #1184 | Bounded active-perception evidence selection | Reuse one frame/evidence budget |
| #1185 | Session-local conversation context index | Reuse one context owner |
| #1186 | Multiparty room replay evaluator | Keep conversational turn metrics separate from game-event commentary |
| #1192 | Memory-to-tool-parameter grounding evaluator | Test whether recalled facts actually improve actions |
| #1199 | Randomized causal game-mechanic probe evaluator | Use matched start states and independent game-state outcomes |
| #1200 | OpenGameEval result/exploration adapter | Preserve observation/edit separation and task identity |
| #1201 | Paired mixed-load streaming performance evaluator | Use as the release-facing performance gate |
| #1202 | Hour-scale stream continuity memory and host | Preserve bounded, governed memory and expiry |
| #1204 | Prompt/KV cache isolation across conversations | Never trade cross-chat isolation for cache reuse |
| #1205 | KV-residency admission planner | Respect VRAM headroom under concurrent game/OBS load |
| #1207 | Authenticated local OBS WebSocket telemetry | Keep OBS control/telemetry on loopback with explicit auth |
| #1208 | Capability-gated speculative decoding canaries | Benchmark only; no unconditional draft-model loading |
| #1211 | Runs 63–65 research and Game Lab catalog expansion | Review its source links and exact-head validation before integration |

The Run 66 work adds a distinct gameplay-commentary evaluation surface; it does not edit files already changed by those PRs.

## 3. New game-agent research and what STAR should take from it

### 3.1 SIMA 2 — generalist goal reasoning and cross-game transfer

Primary source: [Google DeepMind — SIMA 2](https://deepmind.google/blog/sima-2-an-agent-that-plays-reasons-and-learns-with-you-in-virtual-3d-worlds/) (2025-11-13).

DeepMind describes an agent that combines language-level goal reasoning with visual interaction in 3D games. Its report discusses more than 600 learned language-following skills in the earlier SIMA system, held-out game evaluation in ASKA and MineDojo, transfer of concepts such as mining to harvesting, and self-directed play that produces experience for later training generations. The same report is candid about remaining limits: long-horizon task completion and verification, short interaction memory under low-latency constraints, precise keyboard/mouse actions, and robust visual understanding.

**STAR application:**

- Keep a strategic planner that converts a natural-language goal into observable subgoals.
- Keep a separate low-level controller; do not make the large reasoning model emit every frame's input.
- Represent transferable skills as small, typed capabilities (navigate, inspect, gather, craft, build, interact, defend), each with game-specific preconditions and verified effects.
- Require the game adapter to prove that a concept maps to the target game's mechanics; never assume that similar words mean identical actions.
- Save only episodes with verified state transitions and provenance.
- Train on owner-approved, rights-cleared data; use self-play as candidate experience, not automatic truth.

SIMA 2 is a research preview, not a dependency STAR can simply install. Treat its architecture and evaluation lessons as research.

### 3.2 NitroGen — a possible fast visual-action policy, not a complete gamer

Primary sources: [NitroGen paper](https://arxiv.org/abs/2601.02427), [official MineDojo repository](https://github.com/MineDojo/NitroGen), [project page](https://nitrogen.minedojo.org/).

The paper describes a 500M-parameter vision/action model trained on roughly 40,000 hours of gameplay video across more than 1,000 games, with a reported up-to-52% relative improvement over from-scratch models on the paper's unseen-game tasks. The official repository is unusually clear about the current model's limits: it sees only the latest frame, is a fast-reacting system 1 policy, and does not itself provide long-horizon planning, end-to-end game completion, continual self-improvement, or reliable play in completely unseen games. Its current runner targets Windows games.

**STAR application:**

- Evaluate NitroGen as an optional reflex-policy candidate on one disposable, owner-selected game.
- Put it behind the existing screen-to-action permission gate and an explicit controller lease.
- Let STAR's planner set the goal and allowed action budget; the reflex policy only proposes bounded controller actions.
- Use a state verifier to detect progress, failure, stuck loops, and completion.
- Stop or fall back to manual control on stale frames, focus changes, unexpected dialogs, policy uncertainty, or resource pressure.
- Review the exact code, checkpoint, dataset, and dependency licenses before downloading or distributing anything. The paper's scale is not a license grant for arbitrary third-party gameplay footage.
- Do not install NitroGen or its weights automatically. The repo labels it research-only and says the current model is not a full end-to-end agent.

The important architectural lesson is **fast policy + slow planner + external verifier**, not "replace STAR's brain with NitroGen."

### 3.3 GameWorld — make gameplay progress objectively verifiable

Primary source: [GameWorld paper](https://arxiv.org/abs/2604.07429), [project page](https://gameworld-bench.github.io/).

GameWorld contains 34 games and 170 tasks, with state-verifiable progress/outcome metrics and separate computer-use and semantic-action interfaces. It also studies real-time interaction, context-memory sensitivity, and action validity.

**STAR application:** report task completion separately from exploration, action validity, and time-to-completion. Use randomized starts, repeated attempts, held-out games, and state-based success rather than an LLM judge alone. The open OpenGameEval and causal-probe PRs should supply Roblox-specific and mechanic-learning evaluation.

### 3.4 Creator Brain — complete, playable games

Use the already-researched [GameDevBench](https://github.com/waynchi/gamedevbench) and [CEGame-Bench](https://arxiv.org/abs/2610.26098) as complementary task families. The acceptance path should be:

**inspect project → define completion contract → edit → build → launch → apply real input → verify objective → save/reload → regression test**

For Roblox, use disposable Studio places and the existing read-only-first access model. For Godot/Unity/Unreal/Blender, keep each engine adapter version-pinned and separately sandboxed. A successful file write or clean compile is not proof of a playable game.

## 4. Streaming research — one conversation, two loops

### 4.1 Realtime-Venus: asynchronous delegation

Primary source: [Realtime-Venus project and report](https://realtime-venus.github.io/) (technical report arXiv:2609.13814, 2026-09-12).

Its architecture separates a live perception/speech loop from a background delegation loop. A request captures the context available at arrival, work is routed to a multimodal model, general model, or skill, and the result returns to the same conversation. The frontend still decides when to speak, and playback tracking verifies delivery. It also retrieves selected, relevant/novel frames for long-video context rather than retaining every frame.

**STAR application:**

- Snapshot a bounded context when a background job is created: conversation/session revision, current game, relevant event IDs, task, deadline, and cancellation epoch.
- Run research, strategy, clip analysis, or game-planning asynchronously.
- On completion, discard stale results if the session revision, task, game, or interruption epoch changed.
- Route every proposed utterance through the existing turn director and playback owner.
- Track "generated", "queued", "started", "played", "interrupted", and "discarded" as distinct states.
- Never let a background worker write directly to the audio device or avatar parameters.

The reported model is 9B and its reported benchmark numbers are from its own September 2026 manuscript; they are not STAR results and the model is not a realistic default for an 8 GB gaming GPU.

### 4.2 InteractiveAvatar: long/short visual memory and intent-aware reaction

Primary source: [InteractiveAvatar — ECCV 2026](https://sqymu.github.io/InteractiveAvatar/).

The work combines short-term visual context with dynamically selected long-term keyframes and a reasoning/reaction module for intent-aware avatar behavior. Its research direction is useful, but its video-generation architecture should not be assumed to fit STAR's current hardware or character pipeline.

**STAR application:** retain the approved Live2D character and use a light-weight visual-state memory: current expression, current speaker/addressee, active topic, recent game event, current animation, and a few high-value keyframe/scene summaries. Use one avatar-parameter writer and one playback clock. Do not add a diffusion-video engine to the default 8 GB VRAM path.

### 4.3 Human-like streaming without deception

A natural persona is a combination of stable identity, listening skill, timing, memory, humor, expressive delivery, and good judgement—not a claim that the system is biologically human or has private human feelings.

Recommended audience-facing behavior:

- identify STAR as an AI VTuber;
- maintain a consistent character voice and visual style;
- use contextual reactions and silence rather than constant narration;
- remember consented, relevant audience context without turning viewer identity into a public memory dump;
- acknowledge uncertainty and correct mistakes naturally;
- avoid inventing personal experiences, offline activities, or feelings as factual claims;
- apply chat moderation, anti-harassment, and escalation policies before responding;
- make stream/record/publish actions explicit and reversible.

## 5. Local inference and speed plan for the 8 GB class

Primary source: [llama.cpp SPEED-Bench server harness](https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench).

SPEED-Bench measures prompt throughput, decode throughput, client-observed latency, and speculative draft acceptance. Its documentation says benchmark concurrency should usually match the server's configured slots (--np), and fixed input-length splits can be used to compare batch/ubatch settings. That is the right discipline for STAR: matched workload, fixed context, same model/build, same concurrency, and the same output limit.

### Measurement contract

Record, separately:

- prompt tokens and prompt-processing tokens/sec;
- time to first token;
- decode tokens/sec;
- client-observed end-to-end latency;
- first audio submitted and first audio actually played (never conflate them);
- endpointing/ASR/TTS/playback stages;
- p50/p95/p99 and sample count;
- GPU/CPU/RAM/VRAM peak and queue wait;
- game frame-time p95/p99, audio underruns, avatar dropped frames;
- OBS render/encode lag and dropped frames;
- verified task success and recovery rate.

Use a matched A/B design and preserve an untouched holdout. A faster model that loses gameplay accuracy, produces false commentary, or drops audio is not a speed win.

### Safe tuning sequence

1. Capture a known baseline with the exact llama.cpp build, model hash, quantization, prompt, context, GPU layer count, -np, and workload.
2. Preserve the stable prompt-prefix layout in star/context_layout.py; do not move per-turn volatile content into the stable system prefix.
3. Sweep one variable at a time: GPU offload layers, context length, batch/ubatch, and server slots.
4. Test flash attention and supported KV cache types only when the installed backend reports the intended kernel path; verify logs so a silent CPU fallback does not masquerade as a quality/performance result.
5. Evaluate Q8 KV cache before more aggressive compression. Any Q4 or asymmetric K/V setup needs task-quality and backend-correctness checks on the exact model/build.
6. Keep one resident model on the 8 GB local runtime unless measured memory headroom proves another arrangement safe. Do not load a draft model by default; evaluate the existing speculative-decoding canary work.
7. Run the same workload with the game, OBS, voice, and avatar active. The useful objective is **verified task goodput under mixed load**, not isolated tokens/sec.

Do not apply unrelated accelerator results (Ascend, H100, RTX 5090, or another backend) as predicted RTX 4060 speedups. No new runtime flags or model routes are enabled by this research.

## 6. General knowledge and research quality

The Knowledge Brain should distinguish four evidence types:

1. **Parametric knowledge:** what the model may know without retrieval.
2. **Retrieved source:** external material with URL, publication/update date, and fetch time.
3. **Project memory:** owner-approved, project-scoped facts and decisions.
4. **Inference:** a derived conclusion with explicit assumptions and confidence.

For current or high-impact facts, retrieve sources, compare independent evidence, record conflicts, and expire stale facts. Keep web snippets and tool outputs untrusted. Do not let a source update permissions, write code, or become a permanent memory by itself.

Recommended capability areas: programming, science, maths, history, geography, language, art/design, game mechanics, engine APIs, audio/video, computer operation, and practical planning. Evaluate factual correctness, citation support, tool success, and calibration separately.

## 7. New offline infrastructure in this change

star/gameplay_commentary_eval.py provides a small, dependency-free evaluator for the decision layer that chooses among:

- comment
- acknowledge
- silence
- yield

It reports separate action confusion/precision/recall/F1, silence precision/recall, false speech on labelled negative controls, independently reviewed speech grounding, and event-to-decision latency/deadline performance.

It deliberately does **not** produce one blended "human-like" score. The tests cover empty inputs, missing evidence, negative controls, false commentary, missed events, late speech, invalid clocks, duplicate IDs, and malformed labels.

This is an offline evaluation primitive only. It is not wired to voice, OBS, VTube Studio, game capture, a controller, or a public stream. It stores no media, transcript, viewer ID, or runtime telemetry.

## 8. Integration order

### P0 — exact-head correctness and merge hygiene
- Keep each existing feature PR isolated; do not merge a stack out of order.
- Require exact-head CI, protected-path checks, and the appropriate reviewer.
- Resolve duplicate research references only after inspecting the actual merged source.
- Do not call unmerged voice/OBS/game features shipped.

### P1 — streaming control
- Integrate the voice bridge, room turn director, queue, playback owner, continuity memory, OBS telemetry, and persona in dependency order.
- Add context snapshot IDs, cancellation epochs, stale-result discard, and playback-confirmed delivery to asynchronous delegated jobs.
- Run negative-control streams to measure silence compliance and false commentary.

### P2 — generalist game pilot
- Use one owner-selected, disposable Windows game and a rights-cleared model/data set.
- Evaluate a fast visual-action policy (NitroGen candidate) behind the existing screen-to-action gate.
- Keep the strategic planner, policy, state verifier, and safety gate separate.
- Add state-verifiable goals, randomized starts, repeated trials, and held-out levels before adding another game.

### P3 — Creator Brain
- Add completion contracts to Roblox/engine projects.
- Verify build, launch, real input, goal completion, save/reload, and regression.
- Keep generated code untrusted until sandboxed and separately reviewed.

### P4 — hardware and sustained rehearsal
- Run matched local inference benchmarks at baseline and candidate settings.
- Run 30-minute, 2-hour, and longer private rehearsals with game + OBS + avatar + voice active.
- Report dropped frames, underruns, turn timing, false commentary, task success, and resource headroom.
- Only then consider changing default model/runtime settings.

## 9. Acceptance gates

| Capability | Minimum evidence before calling it working |
|---|---|
| Natural voice | Real microphone/playback, barge-in, backchannels, late ASR, no stale queued speech |
| Multiparty streaming | Speaker-disjoint replay, selective interruption, addressee accuracy, false-cutoff rate |
| Game commentary | Negative controls, groundedness review, silence precision/recall, deadline latency |
| Gamer Brain | Repeated state-verified tasks, held-out levels/games, action validity, recovery |
| Creator Brain | Build + real input + completion + save/reload + regression |
| General knowledge | Source-backed answer accuracy, freshness, conflict handling, calibration |
| Local speed | Matched SPEED-Bench-style A/B plus mixed-load p95/p99 and task goodput |
| Self-improvement | Protected paired gate, sealed holdout, regression canaries, no self-edit of graders |
| Human-like persona | Human-rated naturalness plus factual transparency, moderation, privacy and consent |

## 10. Sources

- [SIMA 2 — Google DeepMind](https://deepmind.google/blog/sima-2-an-agent-that-plays-reasons-and-learns-with-you-in-virtual-3d-worlds/)
- [NitroGen paper](https://arxiv.org/abs/2601.02427)
- [NitroGen official code](https://github.com/MineDojo/NitroGen)
- [NitroGen project page](https://nitrogen.minedojo.org/)
- [GameWorld paper](https://arxiv.org/abs/2604.07429)
- [GameWorld benchmark](https://gameworld-bench.github.io/)
- [GameDevBench](https://github.com/waynchi/gamedevbench)
- [CEGame-Bench](https://arxiv.org/abs/2610.26098)
- [Realtime-Venus report](https://arxiv.org/abs/2609.13814)
- [Realtime-Venus project](https://realtime-venus.github.io/)
- [InteractiveAvatar — ECCV 2026](https://sqymu.github.io/InteractiveAvatar/)
- [llama.cpp SPEED-Bench server harness](https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench)
- [llama.cpp issue #28455](https://github.com/ggml-org/llama.cpp/issues/28455): quantized KV + flash-attention can fall back to a CPU path on some builds; verify the actual backend path before comparing speed or quality

## Verification record

- Repository audit: current main README, AGENTS.md, architecture, self-learning loop, evaluator, local runtime, and open PR list inspected on 2026-11-16.
- New evaluator: pure Python; no model, network, device, or external package.
- Unit tests: added, not yet run in GitHub Actions at document creation.
- Model weights, third-party code, gameplay datasets, API keys, local telemetry, and media: not downloaded or committed.
- Runtime defaults, permissions, model routing, OBS/VTube Studio, Roblox publication, and stream state: unchanged.
