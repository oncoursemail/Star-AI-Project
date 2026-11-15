# STAR Run 39 — Adaptive Perception, Asynchronous Delegation, and Low-Latency Streaming

**Research date:** 2026-11-15  
**Scope:** architecture and bounded infrastructure; no model, provider, permission, or production default is changed by this document.

## Executive decision

STAR should stop treating every frame, every possible memory, and every background task as equally urgent. The next useful improvement is a **dual-loop, evidence-budgeted runtime**:

- A foreground loop protects live voice, turn-taking, avatar playback, game control, and stream health.
- Background workers perform research, long-horizon reasoning, historical evidence retrieval, game practice, asset generation, and code/test work.
- A small deterministic evidence selector admits only the most useful fresh observations into a reasoning turn.
- One existing task ledger tracks work, one resource-admission authority schedules compute, one room director owns speech turns, and one game-control gate authorizes game actions.

This is an integration design, not a proposal to add another orchestration framework or memory database.

## Repository audit and baseline

The inspected repository is `oncoursemail/Star-AI-Project`, whose default branch is `main`. The current development work is distributed across draft PRs:

- #1180: research and integration blueprint, Runs 24–38.
- #1182: fail-closed game screen-to-action gate and Game Lab catalog.
- #1178: voice/streaming integration and frontier source register.
- #1181: speaker metering and DAC playback-clock work.
- #1121: cached BM25 skill retrieval.
- #1140/#1142: resource admission and pressure-governor composition.
- #1167: streamed inference timing.
- #1177: durable task/communication ledger.

At the start of this run, exact-head GitHub Actions for #1180's research commit, #1182's Game Lab commit, and #1178's source-register commit were successful. That is repository CI evidence, not physical hardware acceptance.

### Existing game-control boundary

The inspected `star/game_control_gate.py` already binds action permits to a fresh observation, exact capture epoch, approved target fingerprint, owner consent, foreground state, allowlisted controls, short action duration, and one action authorization per observation. It also supports manual override and fail-closed stop/release behavior.

Run 39 must not duplicate this authorization gate. Perception selection decides **which evidence request is worth making**; the game-control gate separately decides **whether an action may be issued**.

### Existing voice and streaming boundary

The inspected voice documentation describes a working recorded-audio pipeline and a one-shot `transcribe(pcm)` ASR interface. Partial transcript previews may re-run one-shot transcription over accumulated audio, so this is not yet a true incremental ASR event stream. The documentation also explicitly says real microphone/loudspeaker acceptance has not been completed.

The room host and RoomTurnDirector are the existing boundaries for multiparty source consent, moderation, turn policy, and queueing. Platform adapters must feed that host; they must not create a second social director or independent speech queue.

### Existing performance boundary

The existing resource-admission PRs and inference metrics should remain the only authorities for CPU/GPU/RAM admission and runtime timing. Do not add a second scheduler inside perception, voice, or the game gate. The canonical trace should distinguish queue wait, prefill, time-to-first-token, decode, first TTS chunk, DAC/audible playback, avatar presentation, game frame time, OBS skips, and audio underflows.

## 1. Research: agent-specific speculative decoding

### AgentSpec

Paper: https://arxiv.org/abs/2608.24004  
Microsoft Research publication page: https://www.microsoft.com/en-us/research/publication/agentspec-speculative-decoding-for-batch-inference-of-llm-agents/  
EMNLP 2026.

AgentSpec studies why speculative decoding can lose its advantage on batched agent workloads. It identifies high draft-token rejection and poor use of dynamic token budgets, then proposes structure-isolated drafting and redundancy-aware budget allocation. Its evaluation uses vLLM, five workloads, and four model families.

**STAR implication:** speculation should be scoped to a stable semantic phase, such as drafting a plan or a read-only tool argument, rather than freely speculating across a changing multi-step workflow. A tool call, game action, purchase, publish, credential change, or external message must never execute from an unverified speculative draft.

**Compatibility limit:** the paper evaluates vLLM serving. It is not evidence that AgentSpec can be dropped into STAR's local llama.cpp/Vulkan/8 GB desktop path. Treat it as a Brain 2 or separately budgeted serving experiment only after backend, model, batching, and quality compatibility are established.

### AsymSpec

Paper: https://arxiv.org/abs/2608.26004

AsymSpec studies context-asymmetric speculation: a lightweight drafter receives fuller context while a verifier operates on a compressed view, with a divergence-aware acceptance mechanism. The preprint reports approximately 1.3–1.7× throughput and 0.2–0.3× compute on selected isolated text capabilities; those numbers are paper-specific and must not be transferred to STAR.

**STAR implication:** test whether a compact, task-specific draft can prepare a candidate answer while the authoritative verifier retains the evidence and constraints needed to reject an unsupported answer. The verifier must still see the actual task state, permissions, freshness, and critical evidence. Context compression must never remove safety constraints or the only source supporting a factual claim.

**Adoption gate:** paired full-context versus compressed-context evaluation on the same tasks; measure answer quality, unsupported claims, tool-argument correctness, verifier rejection rate, TTFT, inter-token latency, peak memory, and end-to-end task success. No model default changes until the local results are reproducible.

## 2. Research: KV-cache and context-memory efficiency

### TurboQuant

Official Google Research article: https://research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression/  
Paper: https://arxiv.org/abs/2504.19874

TurboQuant combines PolarQuant-style vector quantization with a one-bit Quantized Johnson–Lindenstrauss residual correction. Google reports large KV-cache memory reductions and up to 8× attention-logit computation speed on H100 hardware in its experiments.

**Critical interpretation:** the H100 attention-logit result is not an 8× end-to-end token-generation speedup, and it is not an RTX 4060 result. A quantized KV cache can also affect retrieval and generation quality depending on implementation, model, context length, and kernel path.

**STAR implication:** first reduce unnecessary context through stable-prefix caching, selective memory retrieval, and evidence budgeting. Then benchmark a compatible KV-cache quantization implementation only if the current serving backend exposes a supported path.

**Benchmark matrix:** context lengths 2K/4K/8K/16K (where supported), warm and cold prefix, batch 1 and realistic concurrency, prompt-prefill time, TTFT, decode tokens/s, p95 inter-token latency, peak VRAM/RAM, cache hit rate, and task-quality regression. Include long-context needle retrieval, code repair, tool-argument grounding, and voice interruption recovery.

Do not import a community implementation into the production runtime merely because it uses the TurboQuant name. Pin the exact implementation, license, commit, kernels, and supported hardware first.

## 3. Research: active perception instead of watching everything

### OmniAgent

Paper: https://arxiv.org/abs/2606.19341  
Official implementation: https://github.com/harryhsing/omniagent  
ICML 2026.

OmniAgent frames long-video understanding as an iterative Observation–Thought–Action process. The agent requests selected frames, audio, or clips when it needs evidence, then consolidates useful observations rather than uniformly processing every frame. The paper reports benchmark-specific gains, including 50.5 versus 47.3 on LVBench for its 7B model against the compared 72B baseline.

**STAR implication:** adopt the active-perception *policy pattern*, not the 7B model as a default. A 7B multimodal checkpoint is not assumed to fit or run responsively alongside STAR's voice, game, avatar, and OBS workloads on an 8 GB GPU.

For a stream or game, the perception planner should ask targeted questions:
- Did the objective or scene state change?
- Is the current frame enough, or is a short clip needed?
- Is audio required to distinguish an event?
- Is historical evidence more useful than another live frame?
- Is the current observation stale by the time reasoning finishes?

### Evidence-budgeted selection

A pure policy layer may rank already-proposed evidence candidates using:
- task relevance,
- uncertainty,
- event novelty,
- urgency,
- freshness,
- media-context cost.

The selector should cap the number of requests and total media units per reasoning turn. It must be deterministic, bounded, and explain why a candidate was selected or rejected.

This is a **context/evidence budget**, not a CPU/GPU scheduler. The existing resource-admission controller remains responsible for compute capacity. The selector does not capture frames, inspect protected content, invoke tools, or authorize game input.

Recommended request classes:
- single frame,
- short clip,
- audio segment,
- historical event lookup.

Historical recall should return timestamped evidence references and provenance, not silently treat an old event as the current state.

## 4. Research: asynchronous delegation without conversational amnesia

### Realtime-Venus

Paper: https://arxiv.org/abs/2609.13814  
Project page: https://realtime-venus.github.io/

Realtime-Venus describes a foreground full-duplex interaction loop alongside asynchronous background reasoning and tool execution. It uses separately trained 9B audio and audio-visual models, so its model configuration is not a local STAR recommendation. The architecture is relevant because the live conversation continues while background work runs and later returns a result to the ongoing interaction.

**STAR implication:** reuse the existing task/communication ledger and room host. A background result should return as a typed completion containing:
- task ID and generation ID,
- original request summary,
- evidence references,
- completion status,
- verifier result,
- creation time and expiry,
- whether the result has been spoken or otherwise delivered.

Before delivery, check whether the task was cancelled, superseded, or made irrelevant by a newer request. A completed task is not the same as a delivered result. A spoken result is not the same as a verified result.

Do not add a second task ledger, second room director, or second speech queue.

## 5. Research: human-appropriate turn timing

### TACT

Paper: https://arxiv.org/abs/2609.27372

TACT evaluates 9,728 episodes (73.2 hours) and conditions turn timing on speaker intent rather than assuming that every pause demands an immediate response. Its intent categories include immediate-answer seeking, reflective pauses, rhetorical turns, floor-holding, cooperative invitations, and turn abandonment. The paper reports stronger agreement with human judgments than binary fixed-window metrics in its evaluated setting.

**STAR implication:** natural streaming is not maximum response frequency. STAR should distinguish:
- a viewer directly asking her something,
- viewers talking to each other,
- a rhetorical comment,
- someone thinking aloud,
- an invitation to finish a sentence,
- a pause that signals reflection,
- a genuine request to interrupt or stop.

Measure false interruptions, missed direct requests, inappropriate takeover, delayed response to urgent requests, and appropriate silence. Keep any speaker-style adaptation session-scoped and privacy-preserving; do not build cross-platform identity profiles or voiceprints.

### Naturalness and responsiveness

EXPRESS study: https://doi.org/10.1177/10949968261471154

The study's virtual-streaming experiments report that responsiveness improves outcomes when response naturalness is high, but not when naturalness is low. Its setting is e-commerce livestreaming, so it is a product-design hypothesis—not direct proof about gaming streams.

A separate 2026 study of anthropomorphic virtual-streamer design reports an interaction between avatar appearance and operation mode across four experiments (N=1,334). It cautions against assuming that more human-like appearance is always better when the driving behavior is visibly AI-operated.

**STAR implication:** optimize conversational fit, continuity, timing, and character consistency rather than simply increasing animation realism or message frequency. Be transparent that STAR is an AI character. Natural silence, grounded reactions, and honest uncertainty are positive behaviors.

## 6. Concrete runtime architecture

### One event spine

Every accepted event should carry:
- session ID,
- monotonically increasing event sequence,
- source kind,
- event time and receive time,
- expiry,
- privacy class,
- correlation/task generation ID,
- provenance reference.

Keep raw audio, viewer text, and media payloads in bounded ephemeral stores. Telemetry should use aggregate counters and opaque IDs by default, not transcripts or raw media.

### Foreground loop

1. Ingest trusted audio/chat/game events.
2. Apply source consent, moderation, deduplication, and TTL.
3. Update the room director and playback state.
4. Decide whether to respond, queue, continue, or remain silent.
5. Protect voice, avatar, game-control, and OBS deadlines.
6. Cancel stale generations immediately.

### Background loop

1. Capture a stable task snapshot.
2. Retrieve only relevant skills and memory.
3. Request bounded evidence through the active-perception policy.
4. Run research, planning, code, or gameplay analysis.
5. Verify the result independently.
6. Return a typed completion to the existing task ledger.
7. Re-check relevance and delivery state before speaking.

### Cancellation and freshness

Use generation IDs for every replaceable request. A newer user request, stop command, stream-session reset, or target-process change invalidates stale work. Cancellation must propagate to inference, tool execution, queued speech, and avatar presentation. A stale result may be retained as an internal artifact only if policy permits; it must not be delivered as the current answer.

## 7. Gaming and learning implications

For Gamer Brain, active perception should request evidence at meaningful state changes rather than blindly sampling every frame. Game skills remain separate from raw action sequences.

Each practice episode should record:
- game and version,
- map/seed and difficulty,
- starting state,
- objective,
- observations requested,
- action sequence,
- outcome and state-verifier evidence,
- failure category,
- resource/time budget,
- whether the skill passed on a held-out seed.

Separate live-speed performance from slowed or paused performance. Report task progress separately from terminal success. Never claim a strategy is mastered from one successful run.

For Creator Brain, use the same inspect/build/play/capture/verify loop. Visual evidence is especially important for UI, animation, materials, lighting, and scene-layout tasks. A successful build or test command is not proof that the game looks or behaves correctly.

## 8. Speed and intelligence measurement plan

Every experiment must compare the same model, prompt, task set, hardware, and concurrency regime.

### Latency
- queue wait,
- prompt prefill,
- TTFT,
- inter-token latency p50/p95/p99,
- first TTS chunk,
- first audible sample,
- interruption-to-silence,
- avatar presentation delay,
- game frame-time impact,
- OBS skipped frames,
- audio underruns.

### Intelligence and capability
- answer correctness,
- evidence-grounded factuality,
- tool-argument correctness,
- task completion,
- whole-workflow completion,
- skill retrieval Recall@k/MRR/nDCG,
- held-out skill transfer,
- game progress and terminal success,
- appropriate-silence and interruption scores,
- result-delivery correctness.

### Resource use
- CPU utilization and throttling,
- process RSS,
- GPU utilization and VRAM,
- model load/unload time,
- KV-cache size and hit rate,
- disk I/O,
- background queue depth.

Do not optimize average tokens/s while p99 voice latency, audio dropouts, or game frame-time regressions get worse. Use paired runs and publish confidence intervals where sample size permits.

## 9. Adoption gates

| Candidate | First experiment | Do not adopt if |
|---|---|---|
| AgentSpec | Isolated Brain 2/vLLM batch comparison | Backend mismatch, tool side effects can escape verification, or quality drops |
| AsymSpec | Full-context versus asymmetric-context paired test | Critical evidence or constraints are lost |
| TurboQuant | Supported backend KV-cache A/B test | No supported kernel, unacceptable retrieval drift, or no local benefit |
| OmniAgent pattern | Deterministic evidence-request policy | It duplicates resource admission or increases stale-frame actions |
| Realtime-Venus pattern | Task-ledger foreground/background integration test | It creates duplicate task or speech authorities |
| TACT | Intent-labelled voice replay evaluation | It rewards forced chatter or violates privacy boundaries |

No paper-reported speedup is a STAR result until measured on STAR's actual hardware and exact model/backend.

## 10. Implementation sequence

1. Land and stabilize the current exact-head PRs without merging automatically.
2. Add a pure, deterministic active-perception candidate selector with media-unit and freshness limits.
3. Add tests for stale, future, expired, duplicate, over-budget, wrong-session, and tie-break cases.
4. Connect only trusted observation adapters; keep the selector separate from capture and game input.
5. Extend the benchmark manifest with perception decisions, selected evidence, media units, and event-to-action timing.
6. Add an incremental ASR interface with partial/committed/final/correction events and cancellation, preserving utterance IDs.
7. Add intent-conditioned turn-taking replay tests based on TACT-style labels.
8. Add generation-aware asynchronous task completion and delivery reconciliation over the existing ledger.
9. Run mixed-load Windows acceptance with voice, avatar, OBS, game capture, and background research together.
10. Evaluate model/quantization/speculation changes only after a stable local baseline exists.

## 11. Required regression tests

- A stale or expired candidate is never selected.
- A future-dated candidate is rejected.
- A candidate from another session is rejected.
- Duplicate event/evidence keys cannot consume the same turn budget twice.
- Media-unit limits are never exceeded.
- Selection is deterministic for equal inputs.
- An urgent direct request can outrank low-value background context.
- A historical lookup is not misrepresented as a fresh observation.
- A cancelled task generation cannot deliver into a newer conversation.
- A completed-but-undelivered task remains owed in the existing ledger.
- Speculative output cannot execute tools or game actions.
- A game action still requires the separate fresh-frame GameControlGate permit.
- Silence is scored as appropriate when the speaker is not addressing STAR.
- Telemetry contains no raw transcripts, audio, viewer text, or secrets by default.

## 12. Limitations and non-claims

- No AgentSpec, AsymSpec, TurboQuant, OmniAgent, or Realtime-Venus model/runtime was installed.
- No model weights were downloaded and no fine-tuning or RL was performed.
- No H100, RTX 4060, or physical Windows performance measurement is claimed by this research.
- No public livestream, Twitch/YouTube OAuth, microphone, OBS, VTube Studio, or live game-control test is claimed.
- No benchmark score is a STAR score.
- No capability is promoted to production from paper results alone.
- All proposed adapters remain opt-in and require license, security, hardware, and acceptance review.

## Primary sources

- AgentSpec (EMNLP 2026): https://aclanthology.org/2026.emnlp-main.585/
- AgentSpec preprint: https://arxiv.org/abs/2608.24004
- AsymSpec: https://arxiv.org/abs/2608.26004
- TurboQuant (Google Research): https://research.google/blog/turboquant-redefining-ai-efficiency-with-extreme-compression/
- TurboQuant paper: https://arxiv.org/abs/2504.19874
- OmniAgent (ICML 2026): https://arxiv.org/abs/2606.19341
- OmniAgent implementation: https://github.com/harryhsing/omniagent
- Realtime-Venus: https://arxiv.org/abs/2609.13814
- TACT: https://arxiv.org/abs/2609.27372
- EXPRESS virtual-streamer study: https://doi.org/10.1177/10949968261471154
- Anthropomorphic virtual-streamer study: https://doi.org/10.1002/cb.70155
