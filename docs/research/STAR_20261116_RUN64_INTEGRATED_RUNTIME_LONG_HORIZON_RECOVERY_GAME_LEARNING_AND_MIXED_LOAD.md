# STAR Run 64 — Integrated Runtime, Long-Horizon Recovery, Game Learning, and Mixed-Load Performance

**Research date:** 2026-11-16  
**Repository:** `oncoursemail/Star-AI-Project`  
**Branch:** `research/run63-duplex-cue-in-turn-adaptation-20261115`  
**Change type:** research, read-only catalog expansion, and regression coverage  
**Runtime policy:** no new executor, scheduler, permission authority, or production default

## Executive decision

STAR should evolve as one coordinated, deadline-aware digital character, not as a collection of independently competing agents.

Run 64 combines four research directions that are especially relevant to STAR's stated goals:

1. **Long-horizon learning:** acquire world knowledge and reusable skills through interaction, while measuring transfer, forgetting, and cost.
2. **Error awareness and recovery:** detect when an earlier action corrupted the current task, stop compounding the error, and recover from a verified checkpoint.
3. **Closed-loop game creation and play:** inspect before editing, run the game, measure state-based outcomes, and use real-time control separately from strategic reasoning.
4. **Mixed-load real-time operation:** protect voice, avatar, game input, rendering, and OBS from background research and inference contention.

The implementation in this run is deliberately bounded: the existing Game Lab catalog gains reviewed, research-only sources and regression coverage. The larger architecture below is an engineering plan, not a claim that the proposed capabilities are already implemented.

## 1. New research findings

### 1.1 AgentOdyssey — test-time continual learning in generated worlds

Primary source: https://agentodyssey.github.io/  
Code and paper links are provided by the project page. The project identifies itself as a NeurIPS 2026 work.

AgentOdyssey procedurally generates open-ended text games to evaluate agents that learn while they are deployed. It separates several abilities that are often collapsed into one completion score:

- exploration of new locations, entities, and actions;
- acquisition of world knowledge;
- episodic memory of what happened and where;
- procedural skill learning;
- long-horizon planning;
- model and interaction cost.

The project reports that stronger base models help, but even the strongest evaluated agent remains below human performance. It also reports that short-term memory benefits multiple agent paradigms. This is not evidence that a large, indiscriminate memory dump is best.

**STAR application:** use procedurally generated, low-risk practice worlds to test whether a skill learned in one episode helps with a later, related episode. Score task progress, actual completion, exploration, memory usefulness, action diversity, and cost separately. Keep held-out world rules and task compositions sealed.

### 1.2 CUA-Recovery — learning to notice and repair an earlier mistake

Primary paper: https://arxiv.org/abs/2610.27645  
Code: https://github.com/xu-hu-2002/CUA-Recovery  
Posted: 2026-10-20

CUA-Recovery studies error detection and recovery in long, multi-application computer-use workflows. Its human-verified test suite contains 2,250 erroneous states across 100 tasks; its training suite contains 8.6K recovery trajectories across 377 tasks. Across the evaluated agents, error awareness and complete recovery remained difficult. The reported fine-tuning gains belong to the paper's Qwen3.5-35B-A3B experiment and must not be represented as STAR results.

**STAR application:** record a compact, trusted action/evidence lineage for long tasks. At each checkpoint, compare expected state with observed state. If a mismatch appears:

1. stop issuing dependent actions;
2. identify the earliest unverified or incorrect step;
3. preserve unaffected work;
4. restore or repair only the affected state;
5. rerun the relevant verifier;
6. continue only from a verified checkpoint.

This should extend STAR's existing desktop and project checkpoint/recovery mechanisms, not create a second transaction manager.

### 1.3 OpenGameEval — Roblox creation must include exploration and play verification

Primary paper: https://arxiv.org/abs/2610.02563  
Official project: https://github.com/Roblox/open-game-eval  
Posted: 2026-10-01

OpenGameEval runs agents in reproducible Roblox Studio sessions. It separates observation tools from editing tools and checks both the resulting scene and a simulated play session. The paper evaluates 84 human-curated tasks, 13 models, and 16 attempts per task. The best reported single-attempt success is 51.7%; the best five-out-of-five consistency is 39.4%. These are benchmark results, not STAR scores.

A particularly useful result is that inspecting every relevant object before editing was associated with higher pass rates: 13.4 percentage points on scene-only tasks and 9.8 points on script-only tasks in the paper's matched analysis.

**STAR application:** make inspect-before-edit an explicit behavior to evaluate. Record which objects, scripts, properties, and dependencies were inspected before a patch. Then verify the actual scene and play behavior. A syntactically valid Luau script is not proof that a game feature works.

### 1.4 GameWorld — separate progress, completion, and real-time control

Primary paper: https://arxiv.org/abs/2604.07429  
Project: https://gameworld-project.github.io/

GameWorld covers 34 browser games and 170 tasks. It uses serialized game state to score both binary success and normalized progress. It also defines a real-time track in which the game continues while the agent reasons; that track is distinct from the paused environment.

**STAR application:** keep three measures separate:

- **Progress:** how much of the objective has been achieved?
- **Success:** did the authoritative game state satisfy the goal?
- **Real-time competence:** did the agent act correctly while the environment continued to evolve?

Never report progress as a win. Never use paused benchmark performance as evidence of live reaction speed.

### 1.5 InteractionBench and EoT-Bench — evaluate what the viewer actually experiences

InteractionBench: https://arxiv.org/abs/2611.02430  
LiveKit EoT-Bench: https://github.com/livekit/eot-bench  
Full-Duplex-Bench v3: https://arxiv.org/abs/2604.04847

InteractionBench evaluates conversational timing, spoken-task accuracy, whisper/volume behavior, and grounding in conversations longer than twenty turns. Its protocol measures timing at the client-heard point and warns that server-side timestamps can omit network delay. Its published evaluation includes 221 items per system across thirteen scenarios and 1,519 graded runs.

EoT-Bench provides real human-to-agent turns in fourteen languages and annotates pauses so systems can be tested on whether a pause is a hesitation or the end of a turn.

**STAR application:** report separate timestamps for:
- microphone speech end;
- end-of-turn decision;
- transcript availability;
- first model token;
- first TTS chunk;
- audio queue submission;
- actual local loopback playback;
- remote stream/client-heard playback when available.

A PCM queue timestamp is not proof that a viewer heard the audio. Voice quality, floor-control correctness, answer correctness, and delivery latency must remain separate metrics.

### 1.6 Video InteractionBench — know when not to comment

Primary paper: https://arxiv.org/abs/2610.05775  
Posted: 2026-10-05

This is a separate benchmark from the voice InteractionBench paper above. It evaluates a streaming-video assistant's decision to speak only when an event warrants a response and to remain silent otherwise. The benchmark covers 1,060 interactions over 812 videos, including negative streams and counted-event/near-miss pairs. It scores content accuracy, timing accuracy, and silence compliance on the video clock.

**STAR application:** game commentary should be event-driven, not frame-driven. Add temporal confirmation for important events, near-miss negative examples, and a silence policy that suppresses low-value commentary. Evaluate false commentary on negative streams separately from missed important events. Do not use an offline video benchmark as evidence of live capture latency.

### 1.7 AdaptDuplex — adapt the thinking/speaking window to the moment

Primary paper: https://arxiv.org/abs/2609.29217  
Posted: 2026-09-24

AdaptDuplex studies adaptive full-duplex dialogue rather than one fixed response policy. Its design includes a compact token-level protocol, bounded text lead over speech, explicit behavioral decision tokens, dynamically selected window durations, and non-blocking cognitive consolidation / external reasoning. The paper reports results on Full-Duplex-Bench and HumDial-FDBench, including a 72.9 Final score on the latter for its evaluated configuration.

**STAR application:** do not run a large reasoning pass on every audio frame. Let the existing room/voice path choose short or longer response windows based on cue confidence, urgency, current floor ownership, and available latency budget. Deep reasoning and memory consolidation should run asynchronously and must not block capture, playback, or immediate game control. Compare the adaptive policy against a fixed-window baseline on the same speaker-disjoint test set.

The reported benchmark score is not a STAR score and does not establish that the paper's model or training recipe fits STAR's current local hardware.

### 1.8 DualDecoder and FlashOffloading — useful memory research, not drop-in RTX 4060 optimizations

DualDecoder: https://arxiv.org/abs/2607.26475  
FlashOffloading: https://arxiv.org/abs/2611.07542

DualDecoder studies predictive prefetch for sparse host-memory KV retrieval and reports up to 2.62x decoding throughput in its evaluated long-context serving setup. FlashOffloading studies host-DRAM-centric KV offload and reports gains on an Ascend 910C prefill/decode deployment under a stated time-per-output-token constraint.

These results are hardware- and serving-stack-specific. They do not establish that either system can be used by STAR's current llama.cpp setup, nor do they predict speedups on the documented RTX 4060 8 GB target.

**STAR application:** retain these as research candidates. First profile prompt prefill, decode, KV residency, host-to-device transfer, context length, and concurrency on the actual supported backend. Only prototype an optimization when its runtime support is verified and a matched baseline exists.

## 2. Integrated STAR runtime design

The recommended design has five cooperating planes. It is an integration model over existing STAR subsystems, not a proposal for five new autonomous schedulers.

### 2.1 Real-time interaction plane

Owns microphone capture, VAD, turn detection, interruption, playback, avatar segment timing, and immediate game-control deadlines.

Requirements:
- bounded queues with explicit overflow behavior;
- monotonic timestamps and sequence IDs;
- cancellation epochs so stale audio or actions cannot be delivered after an interruption;
- no slow research, model loading, or bulk memory retrieval on the audio callback path;
- allow adaptive response-window duration, but keep the audio capture/playback cadence independent of model reasoning;
- local playback measurement through loopback, with remote client timing reported separately;
- one authoritative playback clock and one avatar parameter authority.

### 2.2 Strategic reasoning plane

Owns task decomposition, deeper reasoning, research planning, code architecture, and long-horizon game strategy.

Requirements:
- asynchronous work with deadlines and cancellation;
- explicit task state and evidence references;
- concise summaries passed to the real-time plane;
- no direct bypass of tool authorization;
- independent verification for high-impact claims and generated artifacts.

### 2.3 Skill and memory plane

Keep memory types distinct:
- episodic: what happened in a particular session;
- semantic: stable, source-backed facts;
- procedural: verified ways to perform a task;
- project: decisions and state for a named project;
- social/session: bounded conversational context and viewer preferences governed by existing policy.

A retrieved memory is evidence, not an instruction and not permission. Record provenance, confidence, freshness, scope, and expiry. Measure memory-on versus memory-off performance on paired cases. Track positive transfer, negative interference, and forgetting.

### 2.4 Environment and creator plane

For games and creative applications:
- observe before editing;
- build a structured scene/object map;
- plan a small patch;
- apply an idempotent change;
- run static checks;
- launch in an isolated test environment;
- capture the actual result;
- run gameplay or interaction checks;
- preserve a rollback point.

For Roblox, use Studio inspection and play sessions. For Godot/Unity, use editor and test-runner evidence. For Blender, verify the scene, rig, materials, animation, and exported artifact rather than relying on a text description.

### 2.5 Resource and health plane

Extend the existing resource-admission authority. Do not create another scheduler.

Inputs should include:
- CPU and system RAM pressure;
- GPU VRAM and utilization;
- model load state and KV-cache residency;
- game frame time and dropped frames;
- audio callback health and queue depth;
- avatar frame age and queue depth;
- OBS render/encode lag;
- task deadline, priority, and cancellation state.

Admission policy:
1. protect capture, playback, avatar presentation, and game input;
2. allow strategic reasoning only within measured headroom;
3. pause or reduce background learning before interactive quality degrades;
4. avoid model swaps during a live stream unless the current route explicitly supports a safe handoff;
5. log every admission, deferral, cancellation, and resource-pressure reason.

## 3. Human-like streaming without deceptive identity claims

STAR should feel attentive and expressive while remaining transparent that she is an AI character.

Recommended behavior:
- stable persona and consistent voice;
- natural pacing and varied prosody;
- brief acknowledgements that do not steal the floor;
- backchannel versus takeover distinction;
- multiparty speaker and addressee tracking;
- in-turn correction and collaborative completion;
- recovery of unanswered questions after gameplay;
- context-aware humor and callbacks;
- quiet periods when there is nothing useful to add;
- measure silence compliance separately from timing and answer accuracy;
- use event-triggered commentary with near-miss negative streams so STAR does not narrate every visual change;
- emotion/expression driven by the current interaction, not a fabricated claim of human experience.

Avatar requirements:
- one playback clock;
- segment IDs shared by audio and expression events;
- interruption epoch invalidation;
- bounded animation/audio queues;
- drop stale animation frames rather than accumulate latency;
- never let independent plugins write conflicting mouth/eye/expression parameters;
- test the actual Live2D/VTube Studio path on the target PC.

## 4. Gamer Brain: learn, practice, and prove competence

Keep fast control separate from slow strategy.

**Fast controller**
- short-horizon movement and camera actions;
- aiming, jumping, dodging, and button timing;
- deterministic safety limits and fresh-observation requirements.

**Strategic planner**
- objectives, route selection, resource management, enemy patterns, and replanning.

**Learner**
- stores successful and failed episodes;
- extracts candidate skills;
- tests skills in new levels or seeds;
- compares performance with and without retrieved skills;
- rejects skills that improve one task but damage unrelated tasks.

**Verifier**
- uses authoritative game state when available;
- checks objectives, score, inventory, checkpoints, and win conditions;
- distinguishes invalid actions, progress, failure, and completion.

Practice ladder:
1. deterministic tutorial tasks;
2. fixed-seed replay;
3. held-out seeds;
4. altered mechanics and distractors;
5. longer sessions with interruptions;
6. real-time sessions under measured latency;
7. multiplayer teammate callouts with consent.

Do not bypass anti-cheat, DRM, platform rules, or protected game processes. Use supported APIs, approved automation, and isolated/private test environments.

## 5. Creator Brain: build playable things, not just code

Use a repeatable build/verify cycle:

1. inspect project files and scene hierarchy;
2. identify the authoritative scripts and assets;
3. write a short implementation plan;
4. make the smallest coherent change;
5. run formatters, type checks, static analysis, and unit tests;
6. launch the game/editor;
7. inspect screenshots or structured scene state;
8. playtest the actual feature;
9. run multiplayer and performance checks where relevant;
10. save a checkpoint and report verified limitations.

Feature directions:
- Roblox mechanic and UI authoring;
- Blender asset, rig, and animation pipeline;
- Godot/Unity scene and gameplay generation;
- visual regression testing;
- NPC and enemy behavior authoring;
- audio/VFX integration;
- level design and procedural content;
- multiplayer and network-condition testing;
- performance profiling and regression detection;
- asset licensing and provenance tracking.

## 6. General knowledge and research intelligence

Build a source-grounded knowledge workflow:
- identify the exact question and required freshness;
- retrieve primary sources first;
- separate facts, estimates, hypotheses, and opinions;
- record source date and retrieval date;
- reconcile disagreements;
- cite the claim that each source supports;
- use a verifier or deterministic calculation for numeric claims;
- keep benchmark holdouts out of skill-generation prompts.

General knowledge should span science, history, geography, mathematics, programming, languages, art, game systems, practical computer use, and current events. The system must state uncertainty rather than fabricate a citation or convert a stale memory into a current fact.

## 7. Performance methodology

Use a matched baseline/candidate protocol on the same machine, model, quantization, context, prompt, concurrency, and power profile.

Measure separately:
- cold model load;
- warm model load;
- prompt prefill tokens/second;
- time to first token;
- inter-token latency;
- decode tokens/second;
- peak VRAM and system RAM;
- KV-cache hit/residency behavior;
- CPU/GPU utilization;
- voice end-of-turn to first audible sample;
- client-heard p50/p95/p99;
- avatar frame age;
- game FPS and frame-time percentiles;
- OBS render/encode lag;
- task success, recovery rate, and verified useful task goodput.

Optimization order:
1. remove redundant context and repeated prompt construction;
2. preserve stable prompt prefixes and cache-compatible ordering;
3. route simple tasks to the fast path and reserve deep reasoning for tasks that benefit;
4. profile model load, prefill, decode, and queueing independently;
5. test supported speculative decoding with acceptance and latency reported;
6. test KV-cache quantization/offload only when the backend supports it;
7. schedule background learning around interactive headroom;
8. retain only changes that improve useful task goodput without harming voice, game, avatar, or OBS quality.

For the official llama.cpp SPEED-Bench client, keep the server running separately, match client concurrency to the llama-server slot count, and keep the benchmark split, category, output length, and sample limit identical between baseline and candidate. Preserve the raw JSON and compare per-category prompt throughput, decode throughput, client latency, and draft acceptance. Do not compare runs with different prompts or server-slot settings.

Do not infer a STAR speedup from a paper's different GPU, accelerator, model, batch size, or server.

## 8. Additional feature backlog

### Streaming and social
- co-host mode with a human creator;
- game-event-aware commentary;
- viewer question queue with topic recovery;
- stream chapter and highlight suggestions;
- consent-based speaker profiles;
- moderation assistance with human review for consequential actions;
- expressive idle behaviors and scene-aware avatar reactions.

### Gaming
- replay coach that explains mistakes;
- adaptive practice plans;
- map and objective memory;
- teammate callout understanding;
- strategy comparison across attempts;
- accessibility-aware control mapping;
- private training worlds and seeded challenges.

### Creation
- one-click project snapshot before edits;
- asset provenance and license checker;
- scene graph explorer;
- automatic visual regression capture;
- playable prototype generator;
- build-size and frame-time budget advisor.

### General assistant
- cross-application task recovery;
- research notebooks with source freshness;
- study and language practice;
- personal project continuity;
- document/spreadsheet/presentation creation;
- visual explanation and diagram generation;
- local knowledge packs with provenance.

## 9. Safety, privacy, and autonomy boundaries

- Viewer chat is untrusted input and cannot grant desktop, file, game, or account permissions.
- Model-generated tool arguments must pass the existing trusted action gates.
- High-impact external, financial, account, deletion, and irreversible actions retain owner approval.
- Keep raw audio, transcripts, viewer identifiers, API keys, and private project data out of public research files.
- Use synthetic or consented evaluation audio with speaker-disjoint splits.
- Do not auto-promote a skill, memory, model route, or policy based on one successful run.
- Keep new integrations and feature flags disabled until individually reviewed and tested.
- Preserve rollback, audit evidence, and an emergency stop.

## 10. Acceptance gates for the next engineering phase

| Area | Required evidence |
|---|---|
| Voice | Client-heard timing, false-yield/missed-takeover rates, task correctness |
| Avatar | Actual VTube Studio connection, lip-sync drift, stale-frame and interruption tests |
| Gaming | State-verifiable completion, invalid-action rate, held-out transfer, real-time track |
| Roblox creation | Inspect-before-edit traces, scene checks, simulated play, repeated attempts |
| Computer use | Error awareness, root-cause localization, recovery, persistent-state verification |
| Memory | Paired memory-on/off transfer, interference, retention, privacy |
| Knowledge | Evidence accuracy, freshness, calibration, source reconciliation |
| Performance | Matched baseline and mixed-load p50/p95/p99, task goodput, stream health |
| Reliability | Crash/restart recovery, checkpoint integrity, cancellation and rollback |

No numeric release threshold should be invented before a baseline is collected on the target machine. Set thresholds from repeated baseline distributions and the actual stream/game service-level objectives.

## 11. Primary references

- AgentOdyssey: https://agentodyssey.github.io/
- CUA-Recovery: https://arxiv.org/abs/2610.27645
- CUA-Recovery code: https://github.com/xu-hu-2002/CUA-Recovery
- OpenGameEval paper: https://arxiv.org/abs/2610.02563
- OpenGameEval code: https://github.com/Roblox/open-game-eval
- GameWorld: https://arxiv.org/abs/2604.07429
- GameWorld project: https://gameworld-project.github.io/
- InteractionBench (voice): https://arxiv.org/abs/2611.02430
- Video InteractionBench: https://arxiv.org/abs/2610.05775
- EoT-Bench: https://github.com/livekit/eot-bench
- Full-Duplex-Bench v3: https://arxiv.org/abs/2604.04847
- AdaptDuplex: https://arxiv.org/abs/2609.29217
- DualDecoder: https://arxiv.org/abs/2607.26475
- FlashOffloading: https://arxiv.org/abs/2611.07542
- llama.cpp: https://github.com/ggml-org/llama.cpp
- VTube Studio API: https://github.com/DenchiSoft/VTubeStudio

## 12. Run 64 change and validation boundary

This run adds reviewed source metadata to STAR Game Lab and tests that the entries remain research-only and discoverable. It does not install third-party code, download benchmark datasets, connect to VTube Studio, change model weights, alter permissions, or change production defaults.

The new architecture is a prioritized engineering plan. Exact-head CI must validate the catalog and tests. Hardware, microphone, OBS, avatar, Roblox Studio, and live gameplay acceptance remain separate target-PC tasks.
