# STAR Run 53 — Safe Speculative Decoding Canaries for Local Inference

**Date:** 2026-11-15  
**Scope:** Local llama.cpp inference speed, low-VRAM operation, and safe measurement under gaming/streaming load.

## Executive decision

STAR should evaluate speculative decoding as an **opt-in, capability-gated canary**, not turn it on globally. The first experiments should use context-local n-gram modes (`ngram-simple`, then `ngram-map-k`) because they do not require loading a second draft model. Keep ordinary decoding as the baseline and leave every runtime default unchanged.

The implementation in this run adds `star/speculative_decode.py`, a pure argument planner that builds a shell-free argv fragment only when the selected `llama-server --help` explicitly advertises every required flag and mode. It does not launch a process, download a model, modify `Runtime`, or enable speculation.

## Research findings

### 1. Speculative decoding is not one technique

The current upstream llama.cpp documentation lists several distinct methods: auxiliary draft models, EAGLE-3, DFlash-family drafts, MTP, n-gram cache, `ngram-simple`, `ngram-map-k`, and `ngram-mod`. The common idea is to propose multiple tokens and let the target model verify them in a batch. It helps only when proposal generation is cheap enough and enough tokens are accepted.

Source: https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md

### 2. Start with context-local n-gram modes on constrained machines

The upstream docs describe `ngram-simple` as finding a matching n-gram in the current token history and reusing the following m-gram. `ngram-map-k` tracks repeated continuations and uses a minimum-hit threshold. The docs specifically identify source-code rewriting as a use case for n-gram matching.

For STAR's owner machines, which have been described as 8 GB VRAM-class systems, an auxiliary draft model can compete with the target model, KV cache, game, OBS, and avatar for scarce memory. Therefore the first canary should avoid a second model and test n-gram methods only. This is a research prioritization, not a claim that either method will be faster on the owner's hardware.

The initial values in the manifest (`draft_max=8`, n=12, m=24, map-k minimum hits=2) are deliberately conservative **starting points**, not tuned recommendations. Test a small sweep (for example draft_max 4/8/12 and n-gram size variants) only after the first smoke test is stable.

### 3. Do not use cross-slot shared n-gram state in the first privacy-sensitive canary

The upstream docs say `ngram-mod` maintains a hash pool shared across server slots. That design may be useful for repeated patterns across requests, but it creates cross-slot state and needs a separate privacy/isolation review before STAR uses it for multiple chats or viewers. This run does not expose `ngram-mod`, `ngram-cache`, experimental k4v, or draft-model modes in the planner.

### 4. Use the upstream SPEED-Bench workflow rather than invented speed claims

The official llama.cpp SPEED-Bench client reports category-level prompt/prefill throughput, decode throughput, end-to-end latency, and draft acceptance. Its README says client concurrency should usually match the server's `--np` slot count. It also requires identical benchmark/category/output-length/limit settings for baseline and speculative runs, and provides a compare script that computes decode and latency speedup.

Source: https://github.com/ggml-org/llama.cpp/tree/master/tools/server/bench/speed-bench

STAR should run the official harness in a disposable local environment with a fixed model build, model hash, quantization, context, slot count, thread count, GPU-layer count, prompt set, temperature, output length, and power profile. Randomize baseline/candidate order or use repeated paired sessions so thermal drift and background load do not systematically favor one arm.

### 5. Agent-serving KV research is relevant, but not a llama.cpp drop-in

Two recent research directions matter to STAR's future server fleet:

- **Penelope / KV eviction:** the October 30, 2026 preprint proposes preserving shared prefixes while evicting an earlier portion of the remaining history and retaining the cached suffix. Its SGLang evaluation reports up to 60% lower mean TTFT and 37% lower job completion time with GPU-only cache, and larger improvements with a two-tier GPU/CPU cache. These are paper results on its tested Qwen3/SGLang setup, not expected STAR gains.  
  Source: https://arxiv.org/abs/2611.00391
- **PEEK / queue-aware cache scheduling:** the May 10, 2026 preprint uses pending-queue prefix structure to coordinate admission and cache eviction in vLLM/SGLang. It reports large gains on its tested multi-H100 workloads, but the method requires engine-level integration and is not a command-line tuning knob for STAR's current llama.cpp desktop runtime.  
  Source: https://arxiv.org/abs/2607.02525

These papers support future evaluation of a dedicated high-concurrency Brain server, not immediate changes to STAR's single-slot local runtime.

## STAR architecture audit and integration boundary

The inspected `main` branch already has:

- `star/local_runtime.py` — explicit local llama-server process management and fixed loopback arguments.
- `star/context_layout.py` — stable system/history ordering intended to preserve same-slot prefix reuse.
- `scripts/measure_first_token.py` — cold/warm first-token and prompt-cache measurements through STAR's request path.
- `star/brain_router.py` and `star/instant_route.py` — deterministic fast/deep routing.
- `star/model_fleet.py` — conservative one-resident-model policy for constrained local hardware.
- `star/eval_gate.py` — regression-aware and paired-session promotion gate.

The new module is intentionally separate from `star/local_runtime.py`. Existing open PRs already modify the runtime and live-stream infrastructure; this change avoids overlapping those unmerged branches and does not create a second launcher or scheduler.

### Runtime integration contract for a later PR

1. An owner selects a speculative profile in a local-only advanced setting; default remains `none`.
2. The host obtains help output from the exact selected executable and calls `build_speculative_args`.
3. Unsupported or mismatched flags produce a clear refusal and fall back to the ordinary no-speculation launch; never guess flags from a version string.
4. Only the returned argv elements are appended to the already validated local command. Never use a shell string.
5. Record the exact executable hash/version, model hash, config, server slot count, and benchmark manifest.
6. Keep speculative decoding disabled in cloud/LAN providers unless a separate provider contract explicitly supports it.

## Recommended experiment matrix

| Arm | Profile | Purpose |
|---|---|---|
| A | `none` | Required baseline |
| B | `ngram-simple`, draft max 8 | Low-overhead repeated-pattern canary |
| C | `ngram-map-k`, draft max 8, min hits 2 | Require repeated continuations before drafting |

Run at least these workload strata separately:

- short conversational responses;
- long reasoning / explanation;
- Luau and Python code generation;
- repeated structured edits / refactors;
- summarization;
- tool-using agent turns.

For every run, record:

- prompt/prefill tokens per second;
- effective decode tokens per second;
- TTFT and inter-token latency p50/p95;
- end-to-end latency p50/p95;
- generated/drafted/accepted tokens and acceptance rate;
- CPU, RAM, VRAM, GPU utilization, power/temperature if available;
- exact output and deterministic task score (where the task permits it);
- errors, truncations, and context-window failures.

Then repeat under STAR's real mixed workload: game foreground, voice capture/playback, avatar, OBS, and background tasks. Add the existing STAR mixed-load guardrails: game frame-time p95/p99, audio underruns, first-audible latency, speech backlog, OBS render/output drops, and verified task quality.

## Promotion rules

A speculative profile remains disabled unless all of these hold:

- exact binary help confirms all required options;
- no output correctness regression on deterministic/golden tasks;
- a paired, same-hardware comparison shows a repeatable positive decode-throughput effect;
- TTFT, p95 end-to-end latency, CPU/RAM/VRAM, game frame time, voice latency, audio underruns, and OBS drops remain within preregistered guardrails;
- no new cross-session state or cache-isolation concern is introduced;
- the owner reviews the benchmark artifact before any default changes.

Do not promote based only on acceptance rate or average tokens/sec. A high draft acceptance rate can still lose overall if drafting overhead is too high; a decode gain can still be a bad trade if it delays the first audible response or harms the game.

## VTuber, gaming, and Creator Brain implications

The goal is not merely faster text generation. STAR's latency budget is end-to-end:

- game observation and action controller must retain their real-time budget;
- voice endpointing, speech planning, TTS, and playback must remain responsive;
- avatar motion must stay synchronized to actually audible PCM;
- OBS/game telemetry must remain healthy;
- background research, memory consolidation, and code agents should yield when foreground quality is threatened.

Speculative decoding is only one candidate optimization in the inference slice. It must be measured alongside the full stream, not in isolation and then assumed safe.

For Creator Brain, Roblox's official agentic workflow reinforces the Plan → Build → Test loop, with Studio's playtesting agent checking code/data model/logs and running a test character. STAR should continue to evaluate actual Studio outcomes rather than infer quality from code generation alone.

Source: https://about.roblox.com/newsroom/2026/04/roblox-studio-going-agentic

## What this run did and did not do

**Implemented:** a pure, bounded, help-capability-gated argument planner for two context-local n-gram profiles; 25 offline tests pass in an isolated Python harness.

**Not implemented:** live Runtime wiring, UI settings, automatic model downloads, auxiliary draft models, server process launch, benchmark execution, Windows/GPU acceptance, OBS/VTube Studio integration, game-control changes, or automatic profile promotion.

**Not claimed:** any STAR speedup, intelligence gain, game mastery improvement, human-like streaming improvement, or production readiness. All defaults remain unchanged.
