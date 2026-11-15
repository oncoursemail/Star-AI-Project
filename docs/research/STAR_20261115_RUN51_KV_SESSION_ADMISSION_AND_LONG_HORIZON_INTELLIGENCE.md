# STAR Run 51 — KV-residency stability, continual learning, game mastery, and natural streaming

**Research snapshot:** 2026-11-15  
**Implementation branch:** `feat/kv-session-admission-20261115-run51`  
**Status:** research + offline policy implementation; no production runtime wiring

## Executive finding

A new November 10, 2026 preprint, *Bursts That Outlast Themselves: Persistent Degradation in Prefix-Cached Agent Serving*, describes a feedback loop in long-running agent serving: a short arrival burst can reduce prefix-cache hits, increase turn latency, increase the number of simultaneously resident sessions, evict more useful prefixes, and keep the service degraded after the burst ends. The authors report a roughly 10% cache-hit regime and less than half throughput in affected vLLM runs; their capacity-based suspension policy recovered all tested collapsed runs, while admission throttling alone recovered only one of seven matched runs. This is a preprint result, not a guarantee about every backend. [Paper, arXiv:2611.13412](https://arxiv.org/abs/2611.13412).

This is directly relevant to STAR's long-running agent workloads, but the implementation must respect the actual current backend: the inspected `star/local_runtime.py` starts llama.cpp with one parallel slot (`-np 1`) and the model router permits one resident model. The preprint's vLLM/SGLang multi-session cache-collapse mechanism is therefore **not established as a current STAR defect**. The new module is a backend-neutral admission planner for a future multi-slot or multi-session adapter. It is not wired into llama.cpp and does not suspend anything.

## Run 51 implementation

### `star/kv_session_budget.py`

A pure, deterministic planner accepts:
- a timestamped backend capacity snapshot;
- a reserved-memory safety margin;
- per-session resident-KV measurements or conservative upper bounds;
- workload priority and last-active monotonic time;
- an explicit host-suspendable flag;
- a proposed session's conservative KV upper bound.

It returns one of:
- `admit`: measured usable capacity is sufficient now;
- `suspend_then_admit`: lower-priority sessions would need to be suspended and a fresh backend measurement taken before admission;
- `defer`: stale telemetry, insufficient capacity, or no safe victims.

Policy properties:
- reserves are never consumed;
- stale telemetry fails closed;
- equal- and higher-priority sessions are never proposed for preemption;
- only explicitly suspendable, lower-priority sessions can be proposed;
- victim selection is deterministic;
- the planner has no backend, process, network, audio, game-control, or permission side effects;
- a proposed suspension is not considered completed until a trusted host acknowledges it and collects a new snapshot.

The default priority order is speech, interactive/gameplay, vision, research, training/render. Deployments may tune this only through a separately reviewed policy and workload-specific acceptance tests. Do not use guessed token counts as KV measurements. A serving adapter should provide measured resident KV bytes/blocks or a conservative upper bound, and should label the measurement source in its own telemetry.

### Why no automatic suspend/resume

The new preprint's result supports capacity-aware control, but STAR does not yet have a backend-neutral way to suspend a live agent session while preserving its exact prefix, tool state, deadline, and user-visible continuity. Automatic suspension could corrupt a conversation or interrupt speech. This PR only proposes plans. A future adapter must:
1. verify that the backend supports safe pause/suspend and restoration;
2. bind the plan to a fresh snapshot/version;
3. stop admission while the action is in progress;
4. acknowledge every suspend;
5. remeasure actual resident KV after each action;
6. resume with hysteresis and a cooldown to prevent oscillation;
7. preserve per-session cache isolation and stable prompt-prefix layout;
8. fall back to deferral if any acknowledgement or measurement is missing.

## Serving research

### 1. Prefix caching is valuable but capacity-sensitive

vLLM's automatic prefix caching stores KV blocks by hashes of token blocks and their preceding prefix. Its documented eviction policy keeps referenced blocks and evicts unreferenced blocks using LRU-like ordering when capacity is exhausted. This is useful for repeated system prompts and multi-turn agent sessions, but cache reuse is not free of capacity and scheduling trade-offs. [vLLM automatic prefix caching](https://docs.vllm.ai/en/stable/design/prefix_caching/).

STAR already has a sound prompt-layout rule in `docs/ARCHITECTURE.md`: keep the system prefix stable, preserve append-only prior turns, and place per-turn retrieval and volatile context after the stable prefix. Preserve this design. Do not move timestamps, retrieved notes, changing tool lists, or stream events into the stable prefix.

### 2. Cache-aware admission should measure working sets, not just GPU utilization

For any future multi-session backend, collect:
- resident KV blocks/bytes by active session;
- total allocatable KV capacity and reserve;
- prefix-cache hit and eviction rates;
- prefill tokens and prefill time;
- decode tokens/sec and inter-token latency;
- queue wait and active-session count;
- per-session context growth and request arrival burstiness;
- suspension/restoration time and correctness.

GPU utilization alone is not a reliable proxy for cache pressure. Keep cache telemetry separate from CPU/GPU utilization and from model throughput.

### 3. Avoid a second control loop

STAR already has a resource advisory layer in `star/stream_budget.py`, a mixed-load evaluator in the open Run 47 work, and a managed local runtime. The new planner is intentionally an offline policy primitive. Before wiring it into the resource host, define one authoritative admission controller and one telemetry schema. Do not let the stream director, model router, and KV budgeter independently suspend or start workloads.

### 4. Local llama.cpp applicability

The inspected development branch uses `-np 1` and `--models-max 1`. That limits concurrent server slots and resident models in the current managed router. The new planner should remain dormant until a backend exposes reliable session-level residency data and safe suspension semantics. The open prompt-cache-isolation work is separate: cache correctness/isolation and cache-capacity stability are distinct problems.

## Intelligence and continual learning research

### AMA-Bench: memory must preserve causal structure

AMA-Bench argues that long-horizon agent trajectories are not ordinary chat logs: they contain machine-generated state, actions, outcomes, and causal transitions. Similarity-only retrieval can miss the objective and causal structure needed for future decisions. Its AMA-Agent adds causal graphs and tool-augmented retrieval. [AMA-Bench, arXiv:2602.22769](https://arxiv.org/abs/2602.22769).

STAR should store a verified experience as:
- initial state and observation provenance;
- action and tool invocation;
- expected effect;
- observed next state;
- independent outcome check;
- causal confidence and alternative explanations;
- task/domain scope;
- model, game, API, and skill versions.

An event should not become a reusable rule merely because it occurred once.

### Governed consolidation: remember well, not just more

The September 26, 2026 preprint *The Epistemics of Agent Memory* frames memory as a governed decision: what to retain, compress, abstract into a skill, or forget. It emphasizes anti-leakage, reversibility, auditability, poison resistance, and evaluation of actual transfer. Its own results also report that one consolidation-quality proxy did not predict transfer accuracy across the final benchmark study. Treat the reported gains as paper-specific, not as a STAR forecast. [Paper, arXiv:2609.33013](https://arxiv.org/abs/2609.33013).

Recommended STAR memory pipeline:
1. retain a bounded, provenance-linked episode;
2. propose a fact, procedure, or causal rule separately;
3. test the candidate on held-out tasks and alternate environments;
4. compare against a no-memory baseline;
5. record negative transfer and counterexamples;
6. promote only after a paired evaluation gate;
7. keep the prior version and rollback path;
8. expire or revalidate version-sensitive skills.

### Memento-Skills: evolve external skills without pretending model weights changed

Memento-Skills describes a read/write loop where a learned router selects task-specific skills and experience can revise the skill library without updating base-model parameters. This is a useful architecture reference for STAR's local-first learning, but every generated skill still needs evaluation and provenance. [Paper, arXiv:2603.18743](https://arxiv.org/abs/2603.18743).

### General knowledge

Build a source-grounded knowledge layer rather than a giant unverified vector store:
- claim-level source and timestamp;
- source quality and primary/secondary classification;
- freshness/expiry policy for volatile facts;
- contradiction sets rather than silently overwriting;
- calibrated uncertainty;
- retrieval evidence attached to the answer;
- separate user preferences from world facts;
- no automatic promotion from generated text to verified knowledge.

## Gamer Brain: learn to act, not just describe games

### SIMA 2

Google DeepMind's SIMA 2 describes a generalist agent that reasons about goals, interprets images and language, acts in multiple 3D worlds, and practices new skills through generated tasks and rewards. This is a research direction, not an available drop-in component for STAR. [DeepMind announcement](https://deepmind.google/blog/sima-2-an-agent-that-plays-reasons-and-learns-with-you-in-virtual-3d-worlds/) · [paper](https://arxiv.org/abs/2512.04797).

Recommended STAR decomposition:
- perception: screen/UI/object/state observations;
- fast controller: low-latency key/button/mouse actions with bounded duration;
- tactical policy: movement, aim, positioning, resource use;
- strategic planner: objective selection and route/strategy;
- skill memory: versioned, tested procedures;
- evaluator: game-state success, death/failure, time, resources, and robustness;
- trainer: randomized practice, curriculum progression, and held-out maps.

Do not call a large language model for every frame. Use event-driven observations and a fast controller for immediate action; use the reasoning model for goals, recovery, and strategy.

### Roblox Creator Brain

Roblox's April 15, 2026 announcement describes a plan/build/test direction, Studio MCP, and a playtesting agent that can inspect code/data model, read logs, and use a test character to validate behavior. [Roblox Studio is Going Agentic](https://about.roblox.com/en-nz/newsroom/2026/04/roblox-studio-going-agentic).

STAR's Creator Brain should use:
- project inspection before edits;
- plan manifests and explicit acceptance criteria;
- isolated parallel tasks with shared project-state locks;
- Luau static analysis and formatting;
- Studio playtests with deterministic resets;
- independent server/client checks;
- visual regression and asset validation;
- repair/replay loops;
- held-out test scenarios.

OpenGameEval is the most directly relevant public Roblox benchmark. Pin its exact upstream revision and distinguish EDIT, PLAY, and joint success; do not conflate leaderboard snapshots. [Roblox OpenGameEval repository](https://github.com/Roblox/open-game-eval) · [paper](https://arxiv.org/abs/2610.02563).

## Human-like streaming: social intelligence, not constant speech

### MP-Bench

The October 2026 MP-Bench paper evaluates active voice agents in group conversations. Across 12 evaluated systems, real-time agents scored at or below 22% on multiparty comprehension and near chance on multiparty turn-taking. This is a major open research gap for a VTuber interacting with chat and voice participants. [MP-Bench, Findings of EMNLP 2026](https://aclanthology.org/2026.findings-emnlp.1437/).

STAR needs:
- addressee and reply-chain tracking;
- speaker diarization with uncertainty;
- conversation-topic and floor ownership;
- interruption and backchannel policy;
- duplicate-question suppression;
- silence as an intentional action;
- priority arbitration between gameplay, owner, chat, and safety;
- playback acknowledgements before committing a spoken event.

### End-of-turn and full-duplex evaluation

LiveKit's EoT-Bench v1.1, updated November 13, 2026, provides 7,342 human-to-agent turns across 14 languages and scores the trade-off between false cutoffs and endpointing delay. Use the Pareto frontier, not a single latency number. [EoT-Bench](https://github.com/livekit/eot-bench).

Full-Duplex-Bench v3 adds real disfluent audio and chained tool-use scenarios; the reported systems show a speed/turn-taking trade-off and weaknesses with self-corrections and harder multi-step requests. [Paper](https://arxiv.org/abs/2604.04847) · [benchmark overview](https://www.fullduplex.ai/benchmarks/fdb-v3).

For STAR's persona, optimize for:
- natural conversational timing;
- contextually appropriate reactions;
- non-forced humor and laughter;
- memory callbacks that are actually supported by events;
- voice prosody synchronized to the avatar;
- interruption recovery;
- comfortable silence;
- consistent character voice and boundaries.

Natural performance should not involve pretending to be a human or inventing private experiences. STAR can be expressive and personable while remaining transparent that she is an AI character.

## Cross-application general intelligence

WindowsWorld contains 181 tasks across 17 applications; its paper reports less than 21% success for evaluated agents on multi-application tasks. WeaveBench evaluates 114 long-horizon workflows combining GUI and CLI. These results show why one-shot GUI macros are insufficient. [WindowsWorld](https://aclanthology.org/2026.findings-acl.750/) · [WeaveBench](https://doi.org/10.18653/2026.emnlp-main.658).

Build a typed task graph:
- preconditions and observable state;
- application-specific actions;
- intermediate verification;
- durable artifact checkpoints;
- rollback/compensation actions;
- explicit human approval for irreversible or externally visible operations.

## Speed: optimize quality-adjusted goodput

Do not optimize tokens/sec alone. Record:
- queue wait;
- TTFT;
- time to first useful content;
- inter-token latency;
- first-audible latency;
- endpointing delay and false-cutoff rate;
- verified task completion;
- prefix-cache hit/eviction rate;
- resident KV working set;
- game frame-time p95/p99;
- audio underruns and speech backlog;
- OBS dropped frames;
- CPU, RAM, VRAM, and thermal/power headroom.

Prioritize stable prompt prefixes, bounded context, cache-aware admission, workload isolation, event-driven vision, and fast/slow model routing. Keep speculative decoding opt-in and benchmark it against the same workload; it can regress speed when draft acceptance is low.

## Acceptance plan

### Offline tests in this PR
- capacity and reserve validation;
- stale/future telemetry rejection;
- strict workload classes;
- no preemption of equal/higher priority work;
- deterministic lower-priority victim selection;
- explicit host-ack requirement;
- no mutation or backend side effects.

### Future host acceptance (not performed here)
1. Capture actual per-session KV telemetry on each supported backend.
2. Run a stable baseline workload.
3. Inject a short burst with identical underlying session arrivals.
4. Compare hit rate, TTFT, throughput, queue growth, and resident KV.
5. Test budgeter recommendations in shadow mode.
6. Add suspend/resume only after backend-specific correctness tests.
7. Run 30-minute and 60-minute game + voice + OBS mixed-load sessions.
8. Verify no audio cutoffs, gameplay frame pacing regressions, context cross-talk, or lost session state.

### Explicit limitations
- The new code is a planner only; it does not connect to llama.cpp, vLLM, SGLang, OBS, VTube Studio, Roblox Studio, or a game controller.
- The recent cache-collapse paper is a preprint and its tested serving stack is not STAR's current one-slot llama.cpp runtime.
- No STAR speedup, intelligence gain, gameplay mastery, or natural-streaming improvement is claimed.
- The existing Run 47/48/49/50 work remains in separate open draft PRs; this PR does not merge or modify them.
- Production main and runtime defaults remain unchanged.
