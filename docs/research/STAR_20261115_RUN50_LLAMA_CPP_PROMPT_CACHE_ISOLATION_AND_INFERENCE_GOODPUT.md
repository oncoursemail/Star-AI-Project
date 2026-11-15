# STAR Run 50 — llama.cpp Prompt-Cache Isolation, Safe Inference Throughput, and General Intelligence

**Date:** 2026-11-15  
**Target:** `star/next`  
**Status:** Draft engineering candidate; no runtime binary or model was executed in this run.

## Executive finding

A high-value infrastructure issue emerged while reviewing STAR's actual local runtime. STAR launches a user-supplied `llama-server.exe` from `star/local_runtime.py`. Both the single-model and router paths previously inherited upstream defaults for the shared RAM prompt cache and idle-slot snapshots.

An open upstream llama.cpp issue documents stale prompt/KV state crossing unrelated conversation boundaries in some server configurations. This is a correctness and confidentiality concern, not merely a speed regression: a response can look fluent while containing another request's old context.

Run 50 changes STAR's managed local launch arguments to disable the shared cross-slot RAM cache and idle-slot snapshots, while leaving ordinary same-slot prefix caching enabled. It adds regression assertions and updates the architecture guide. This is a conservative mitigation based on reported reproductions, not a claim that every llama.cpp version is vulnerable or that the upstream defect is fixed.

## 1. Upstream prompt-cache findings

### llama.cpp issue #27148 — cross-conversation contamination reports

[Issue #27148](https://github.com/ggml-org/llama.cpp/issues/27148), opened 2026-08-15 and with additional reports through 2026-11-06, describes stale content from one request appearing in an unrelated request's output. Reports include both sequential and concurrent request patterns, and more than one backend.

The issue describes the RAM-backed cross-slot cache and idle-slot snapshot behavior. Its reporters found that:

- With non-unified KV configurations, both `--no-cache-idle-slots` and `--cache-ram 0` together were needed in their reproduced setup.
- With unified KV in other reported setups, either flag alone was sufficient.
- `cache_prompt: false` in a request did not reliably mitigate the issue.
- A corrupted response could report zero cached tokens, so that counter alone is not a leak detector.
- The two flags together preserved same-slot continuation reuse in the reporter's tested workload, while avoiding the shared cross-slot cache path.

These are issue-reporter experiments, not an upstream guarantee or formal security advisory. They are nevertheless sufficient reason not to rely on the shared pool in STAR's default local runtime.

### llama.cpp issue #30961 — failed RAM-cache restore / prefill regression

[Issue #30961](https://github.com/ggml-org/llama.cpp/issues/30961), opened 2026-10-22 with follow-up reports through 2026-11-09, describes prompt-cache restore failures when a unified KV cache is under pressure. The practical symptom is a full prompt re-read instead of a short cached continuation.

This matters for STAR's speed strategy: a cache can both increase correctness risk and fail to deliver the intended latency improvement. The right answer is not "enable every cache." It is to measure cache correctness, cache hit behavior, and end-to-end goodput under STAR's actual concurrency pattern.

## 2. Actual STAR runtime change

### File changed

- `star/local_runtime.py`

Both `Runtime.arguments()` and `Runtime.router_arguments()` now append:

- `--no-cache-idle-slots`
- `--cache-ram 0`

The request layer's ordinary `cache_prompt` setting is not disabled. This keeps same-slot prefix reuse available while turning off the shared RAM cache/idle-slot snapshot path implicated in the reports.

The router already limits itself to one resident model and explicitly sets `-np 1`. The single-model launch does not hard-code a parallel-slot count, so the same conservative flags are applied there too.

### Regression coverage

- Existing single-model argument test checks both flags and ensures `--no-cache-prompt` is absent.
- Existing router test checks both flags.
- A new paired test checks both launch modes use the safe flags and preserve per-slot cache behavior.
- Projector-path assertion was updated because the cache flags now follow the model/projector arguments.

### Documentation

- `docs/ARCHITECTURE.md` now explains the cache isolation boundary, why request-level `cache_prompt: false` is insufficient for the reported bug, and the canary required before re-enabling cross-slot reuse.

## 3. Performance and intelligence implications

Disabling cross-slot RAM cache can increase prompt-prefill work when a conversation moves to a different slot or when a different client uses a slot. It should not be described as a speed improvement. The expected benefit is avoiding stale context and unreliable cross-slot restores; same-slot prefix reuse remains enabled.

The next benchmark should compare the old and mitigated configurations with identical fixed workloads:

- TTFT p50/p95/p99.
- Time to first non-reasoning output.
- Inter-token latency p50/p95/p99.
- Request latency and prefill throughput.
- Prompt tokens processed versus reused within the same slot.
- Completed requests per second meeting the TTFT/ITL SLO (goodput).
- Exact-answer and evidence-grounded task success.
- Foreign-marker leakage count (must remain zero).
- CPU, RAM, VRAM, game frame-time, audio underruns, and OBS dropped frames.

NVIDIA AIPerf defines goodput as completed requests per second that satisfy specified metric constraints. Its metric reference distinguishes TTFT from steady-state inter-token latency. STAR should use both; a high tokens/sec number can hide a poor first-response delay or a correctness failure.

Sources:
- [NVIDIA AIPerf goodput tutorial](https://docs.nvidia.com/aiperf/tutorials/metrics-analysis/benchmark-goodput-with-ai-perf)
- [NVIDIA AIPerf metrics reference](https://docs.nvidia.com/aiperf/reference/ai-perf-metrics-reference)

## 4. Wider STAR intelligence roadmap

### General knowledge

- Keep source, publication date, version, and evidence with factual claims.
- Track contradictions and stale facts instead of averaging them into false certainty.
- Separate facts from procedural skills, game experience, and persona memories.
- Answer with uncertainty or abstain when sources disagree or the source is out of date.

### Gaming intelligence

- Use a fast, bounded observation/controller loop for immediate movement and a slower strategic planner for goals.
- Learn from state/action/state-delta receipts, not from narration alone.
- Use deterministic resets, randomized experiments, independent holdouts, and causal evidence before promoting a skill.
- Keep practice separate from live public play; obey each game's rules and anti-cheat restrictions.

### Roblox Creator Brain

- Use Studio's inspect/plan/build/run/observe/fix loop.
- Record requirements in a structured manifest with expected game-state changes.
- Verify client and server behavior, multiplayer state, UI, physics, performance, and logs in a real play session.
- Evaluate on untouched scenarios; a generated place file or screenshot is not proof of a working game.

### Human-like VTuber streaming

- Keep the existing turn director and playback authority as the only speech scheduler.
- Improve addressee and reply-to understanding before increasing response frequency.
- Use historical memory only when a moderated question or event makes it relevant.
- Preserve comfortable silence, natural pauses, grounded reactions, and interruption recovery.
- Measure first audible latency, false cutoffs, endpointing delay, audio backlog, avatar synchronization, and viewer-response appropriateness.

## 5. Local baseline context

The existing `docs/STAR_VOICE_CALLS.md` records a historical local Qwen3.5-4B Vulkan run at about 57 tokens/s and roughly 1.05 seconds from push-to-talk release to first sound, with 6.08 GB VRAM in that particular setup. A separate CPU-server run under load recorded 11.3 seconds to first token and 3.8–4.6 tokens/s. These measurements are hardware/configuration-specific and are not re-benchmarked by Run 50.

The new cache flags may change prefill and cross-slot reuse. Measure them on the actual Windows PC before changing context size, model quantization, GPU layers, or speculative decoding. Do not sacrifice the 8 GB GPU's game/OBS/audio headroom for a higher isolated token rate.

## 6. Canary protocol before considering cache re-enablement

1. Pin the exact llama.cpp build, command line, model, context size, KV type, slot count, and backend.
2. Start with a clean server process.
3. Send unrelated requests containing unique random canaries in their own prompts.
4. Run sequential, concurrent, and slot-eviction rounds.
5. Check every response for its own canary and every other request's canary; do not trust only server cache counters.
6. Repeat with short, long, tool-bearing, multimodal, and mixed-model requests.
7. Require zero cross-request markers, zero foreign content, and stable exact-task accuracy.
8. Compare TTFT, ITL, prefill tokens, same-slot cache reuse, and goodput.
9. Re-enable shared caching only after a pinned upstream fix and a repeatable clean soak test; keep an emergency rollback to the two isolation flags.

## 7. Verification boundaries

This PR changes launch arguments and adds unit assertions. It does not run the actual llama-server executable, inspect the installed Windows engine version, benchmark the GPU, or prove that an upstream bug is present on the user's current binary. Exact-head CI and a Windows canary are required.

No model weights, external inference provider, keys, raw conversations, transcripts, user data, OBS/VTuber integration, game-control permissions, or production defaults outside the managed local runtime are added.
