# STAR Run 69 — Mixed-load evidence, generalist game agents, and integration dependencies

**Research date:** 2026-11-16  
**Scope:** offline mixed-load evaluator + research/integration plan  
**Runtime status:** evaluator is not connected to the live scheduler, inference router, microphone, game input, OBS, or VTube Studio.

## Executive decision

STAR's next performance improvement should be measured as **verified useful work under the actual simultaneous workload**, not as isolated tokens/second.

The target experience is one machine running a game, local inference, voice capture/playback, Live2D, OBS, and background tasks without the interactive paths stalling. The current repository has several relevant foundations, but they are distributed across separate open draft PRs. Those branches must be reconciled and tested as one dependency train before the capabilities are described as shipped.

Run 69 adds a pure, bounded evaluator for paired mixed-load measurements. It accepts aggregate numeric samples and reports cold/warm and idle/game/stream/mixed results separately. It intentionally does not inspect hardware, choose model routes, schedule workers, set thresholds, or promote a change.

## 1. Fresh research: generalist game agents

### Gamer — November 13, 2026

Primary source: https://arxiv.org/abs/2611.18397

Gamer describes a generalist vision-language-action agent for long-horizon real-time games. The paper combines visual perception, memory management, multi-step reasoning, continued pretraining on large-scale keyboard/mouse trajectories, sparse-thinking instruction tuning, and multi-turn reinforcement learning. It also describes a cloud-edge inference engine for serving many simulated environments concurrently.

**What STAR should take from it:**

- Long-horizon play needs an explicit memory and state-management strategy; a large prompt alone is not a durable game state.
- Sparse or event-triggered reasoning is a promising way to reduce redundant deliberation during simple control.
- Training and evaluation should use multi-turn trajectories with accumulated-error and delayed-reward cases.
- A fast control policy and a strategic planner should be evaluated together, not as interchangeable agents.

**Limitations:** this is a new research paper, not a drop-in local package. Its cloud-edge serving design and training scale are not evidence that its model can run efficiently on STAR's 8 GB-class desktop GPU. Reproduce the task protocol and architecture ideas before considering a model dependency.

### Generalist game-agent survey — TMLR 2026

Primary collection: https://github.com/THUSI-Lab/Awesome-LFMs-Play-Games  
Publication record: https://openreview.net/forum?id=SDkEq8Fzvl

The living collection separates datasets, models, agent harnesses, and benchmarks, and records work beyond the survey's April 2026 paper cutoff. Its October 21 update lists 210 unique resources and distinguishes recorded-video understanding from closed-loop gameplay.

**STAR application:** use the same four-way classification in STAR's research index. A video-understanding model is not automatically a game-playing agent; a game environment is not itself a player; and a policy is not a complete long-horizon harness. Each entry should record artifact availability, license, hardware, observation/action interface, and whether results were independently reproduced.

### Existing complementary work

- SIMA 2: https://deepmind.google/blog/sima-2-an-agent-that-plays-reasons-and-learns-with-you-in-virtual-3d-worlds/
- NitroGen: https://github.com/MineDojo/NitroGen
- Voyager: https://arxiv.org/abs/2305.16291
- CEGame-Bench: https://arxiv.org/abs/2610.26098
- OpenGameEval: https://arxiv.org/abs/2610.02563

Use these as complementary evidence:
- SIMA 2 for grounded goals and cross-environment interaction.
- NitroGen as a candidate short-horizon visual-action policy, not a complete planner.
- Voyager for curriculum and reusable skill ideas, with executable output kept sandboxed.
- CEGame-Bench and OpenGameEval for task-completion and engine-specific evaluation.

Do not infer mastery from one win or from a model's self-report. Report task distribution, attempts, held-out maps/seeds, success, invalid actions, recovery, and forgetting.

## 2. Fresh inference research: memory hierarchy and cache correctness

### StrataFlux — November 5, 2026

Primary source: https://arxiv.org/abs/2611.08363

StrataFlux studies selective higher-precision refinement streamed from host memory/storage while low-bit weights and KV cache remain the base representation. Its reported experiments include RTX 5090 and unified-memory platforms.

**STAR application:** treat selective precision delivery and overlapped transfer as research ideas for future long-context work. Before considering an implementation, measure the actual transfer path, PCIe traffic, host RAM pressure, SSD latency, and target-model quality on STAR's pinned hardware.

**Limit:** the reported RTX 5090 results do not establish a speedup on an RTX 4060 8 GB desktop. No StrataFlux code or model is installed by this run.

### FlashOffloading — November 5, 2026

Primary source: https://arxiv.org/abs/2611.07542

FlashOffloading reports KV-cache offloading and compute/load overlap on an Ascend 910C deployment integrated with vLLM-Ascend. The reported decode gains are specific to that accelerator and stack.

**STAR application:** use it to identify the relevant bottleneck classes—KV capacity, host/device transfer, cache hotness, and overlap—but do not port its speedup claim to NVIDIA hardware.

### llama.cpp SPEED-Bench

Primary source: https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench

The official server benchmark:
- uses an already-running llama-server;
- recommends matching client concurrency to server slot count;
- saves per-request results and per-category summaries;
- reports prompt throughput, decode throughput, client-observed latency, and draft acceptance;
- compares baseline and speculative runs only when the benchmark, category, output length, and sample limit match.

A STAR benchmark must additionally record the exact llama.cpp commit/build, model file hash, quantization, context, GPU layers, Flash Attention setting, KV types, slot count, prompt-cache state, temperature/seed, and background workload. Keep cold and warm runs separate.

### Cache isolation and stale speculative state

Relevant upstream issue report: https://github.com/ggml-org/llama.cpp/issues/27852

This issue describes an n-gram-cache context persisting across requests on a slot and producing stale draft proposals in the reported build/configuration. It was closed as not planned; it is not evidence that every current llama.cpp build is affected.

**STAR requirement:** on the exact pinned build, run alternating synthetic A/B prompts through reused slots and cache restore. Assert that no unique canary from conversation A appears in conversation B and that speculative state is reset or correctly session-bound. Compare speculation on/off with the same prompt set. Disable the affected speculative/cache path if isolation cannot be demonstrated.

Prompt-prefix reuse is an optimization, not a trust boundary. Cache correctness must never be traded for speed.

## 3. Multi-computer inference: capacity versus single-request latency

Official NVIDIA PAIR documentation: https://docs.nvidia.com/local-ai/nvpair

PAIR can route independent compatible inference requests to a paired node that already has the required model. Its documentation explicitly says it does not pool GPU memory, split one model/request across machines, or move an in-flight request.

**STAR application:**
- keep interactive voice/game inference on the warm local path unless measured otherwise;
- route independent research, summarization, practice, or code-review tasks to a second trusted machine when that reduces total completion time;
- record queue delay, network transfer, remote service time, and result-return time separately;
- use paired-node mutual TLS and explicit node membership;
- reject a remote result if the originating task was cancelled or its context version is stale.

More nodes can increase concurrency. They do not make one generation intrinsically faster.

## 4. Natural VTuber interaction: separate timing, intent, and delivery

Official references:
- LiveKit turn handling: https://docs.livekit.io/agents/logic/turns/
- Adaptive interruption handling: https://docs.livekit.io/agents/logic/turns/adaptive-interruption-handling/
- Turn-taking tuning: https://docs.livekit.io/agents/logic/turns/tuning/
- VTube Studio API: https://github.com/DenchiSoft/VTubeStudio
- OBS WebSocket: https://github.com/obsproject/obs-websocket

LiveKit documents separate stages for end-of-turn detection, interruption handling, preemptive generation, and audio preprocessing. Its adaptive interruption design distinguishes genuine barge-ins from short acknowledgements. Preemptive TTS can reduce latency but may waste compute when the user continues or corrects their thought.

**STAR application:**
1. Keep one existing room/turn authority and one playback owner.
2. Consider bounded text-only precomputation before final turn confirmation only if it is cancellable and the result is revalidated against the final turn.
3. Delay expensive TTS until the turn is sufficiently confirmed; measure wasted generation and cancellation cost.
4. Preserve only the portion of speech that was actually played in conversation history.
5. Distinguish direct address, correction, interruption, backchannel, handoff, and side conversation.
6. Evaluate naturalness through separate metrics: correct addressee, appropriate response, silence compliance, false/missed interruption, follow-through, groundedness, and client-heard latency.

VTube Studio's local API requires the user to enable plugin access and approve the plugin; its token is a secret and must not enter prompts or logs. OBS WebSocket should use authentication and remain local-only unless a separately reviewed remote-control design is approved.

STAR should be expressive and socially natural while remaining transparent that she is an AI character. Do not fabricate human biography or claim perception that the host did not provide.

## 5. New infrastructure in Run 69: paired mixed-load evaluator

### Files

- `star/mixed_load_eval.py`
- `tests/test_mixed_load_eval.py`

### Sample contract

Each row is aggregate numeric metadata for one fixed case and repetition:

- arm: baseline or candidate;
- scenario: idle, game_only, stream_only, or mixed;
- phase: cold or warm;
- case_id and replicate_id: pair identical work across arms;
- TTFT, client-heard latency, task completion latency, decode tokens/sec, game FPS;
- CPU percent, RAM MiB, VRAM MiB;
- audio underruns, OBS dropped frames, avatar dropped frames;
- task success and optional client-heard/task deadlines.

The evaluator:
- caps input at 20,000 rows and stops consuming an oversized iterable at the first excess row;
- validates finite, nonnegative numeric values and bounded counters;
- rejects duplicate sample IDs and duplicate arm rows for a case/repetition/scenario/phase;
- keeps cold/warm and workload scenarios separate;
- reports n, missing count, mean, p50, p95, p99 and max for numeric fields;
- reports counter totals and task-success rates;
- reports deadline eligibility and on-time rates;
- computes candidate-minus-baseline deltas only for explicitly matched repetitions;
- reports unmatched repetitions instead of silently dropping them;
- never stores transcripts, raw media, viewer IDs, machine names, or network payloads;
- emits no composite score or automatic promotion decision.

This module is a measurement layer only. It does not collect telemetry, launch workloads, schedule resources, inspect the GPU, or change runtime behavior.

### How to use it when target-PC telemetry exists

Construct rows from the same scripted workload on the same machine:
- same model and model hash;
- same llama.cpp build and arguments;
- same prompt/task set and context length;
- same game build, scene, map/seed, resolution, and frame cap;
- same OBS scene, encoder, bitrate, and output settings;
- same voice/TTS configuration and audio devices;
- same background workload;
- one candidate variable changed at a time.

Use a randomized or alternating baseline/candidate order to reduce thermal and time-order bias. Run cold-start and warm steady-state trials separately. A small smoke set can catch regressions, but p95 needs a meaningful sample count and p99 needs substantially more. STAR's existing voice metrics use 100 observations as a p95 readiness indicator and 1,000 for p99; keep these as descriptive sample-volume guidance, not universal statistical guarantees.

Only compare client-heard latency when the chosen measurement point actually observes playback. A TTS queue timestamp or PCM submission is not evidence that the user or stream audience heard the audio.

Store the raw trace locally for diagnosis. Commit only an anonymized aggregate report with hardware/software provenance and explicit sample counts; never commit raw voice/video or viewer content.

## 6. Dependency audit: do not build parallel authorities

The GitHub audit on 2026-11-16 found that relevant foundations are split across separate open draft PRs:

| PR | Proposed authority | Dependency/merge note |
|---|---|---|
| #1140 | CPU/RAM/VRAM resource admission | Parent for #1142 |
| #1142 | Compose stream-pressure governor with resource admission | Must be reviewed with #1140 |
| #1178 | Voice room host/director, streaming persona, room behavior | Broad voice integration branch |
| #1181 | Speaker callback isolation and DAC playback telemetry | Stacks on #1178 |
| #1209 | Versioned skill contracts and coverage | Separate skill/learning foundation |
| #1210 | Voice latency metrics and mixed-load acceptance research | Separate metrics branch |
| #1212 | Offline game commentary, voice turn-policy, and mixed-load evaluation | This branch; currently based on main |

These PRs are not all part of production `main`. A source file existing on an open PR branch is not evidence that the public release contains it. Before runtime integration, reconcile the PR dependency graph, rebase in dependency order, and run one exact-head test train.

**Do not add** another scheduler, turn director, memory store, avatar writer, game controller, or model router. Extend the selected existing authority after the dependency train is resolved.

## 7. Ordered implementation plan

### P0 — prove the measurement layer
1. Complete exact-head CI for Run 69.
2. Use synthetic fixtures to verify pairing, missing values, deadlines, and bounded input.
3. Document the evaluator's output schema and keep it versioned.
4. Do not publish a speedup from synthetic data.

### P1 — reconcile the runtime foundations
5. Review #1140 → #1142 as one resource-admission train.
6. Review #1178 → #1181 as one voice/playback train.
7. Reconcile #1209 skill contracts and #1210 voice metrics with the selected base.
8. Rebase #1212 after the dependency order is decided; keep its evaluators independent of live devices.

### P2 — target-PC performance and intelligence
9. Capture a fixed baseline on the actual Windows machine.
10. Run idle, game-only, stream-only, and mixed scenarios with cold/warm phases.
11. Compare one inference variable at a time using llama.cpp SPEED-Bench-compatible settings.
12. Run cache-isolation canaries before enabling new slot/speculative-cache behavior.
13. Measure useful task goodput and verified task success alongside TTFT/decode throughput.
14. Test game-agent skills on held-out maps/seeds and re-test prior tasks for forgetting.
15. Conduct a private VTuber rehearsal with actual audio loopback, VTube Studio, and OBS output.

## 8. Release criteria and claims boundary

A change is not "faster" until a matched target-PC run shows the improvement without unacceptable regressions in:
- task success and factual correctness;
- voice client-heard latency and interruption correctness;
- game frame pacing and action success;
- audio underruns;
- avatar dropped frames and lip-sync error;
- OBS render/output lag;
- memory pressure and crash/recovery behavior.

A change is not "smarter" merely because it uses a larger model or produces longer answers. Require held-out task success, evidence quality, recovery, skill transfer, and regression/forgetting measurements.

Run 69 does not train model weights, install Gamer/StrataFlux/PAIR, change inference routing, connect a microphone, control a game, authorize OBS/VTube Studio, or modify production defaults. The new evaluator is not yet wired to a live telemetry source. Exact-head CI is required before the code is considered validated.
