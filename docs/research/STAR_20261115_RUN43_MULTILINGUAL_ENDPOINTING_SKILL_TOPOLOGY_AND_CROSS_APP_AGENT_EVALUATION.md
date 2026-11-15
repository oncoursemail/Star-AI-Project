# STAR Run 43 — Multilingual Endpointing, Skill Topology, and Cross-Application Intelligence

**Research date:** 2026-11-15  
**Scope:** real multilingual end-of-turn behavior, evidence-grounded skill evolution, meta-memory policies, long-horizon cross-application work, gaming-to-creator transfer, and measurable latency.  
**Status:** research plus a metadata-only EoT-Bench adapter in a companion stacked draft PR. No model weights, live audio devices, production defaults, or desktop permissions are changed.

## Executive decision

Run 43 closes a specific evaluation gap and identifies two capability bottlenecks that affect almost every ambitious STAR workflow:

1. **Voice endpointing needs to be evaluated on right-censored turns, not only turns with a known final pause.** The LiveKit EoT-Bench short-turn cohort contains turns that end at a mid-turn pause with no observed EoT. STAR's previous turn evaluator required exactly one final span per turn, so it could not include these examples without either discarding useful HOLD evidence or inventing an endpoint label.
2. **Skill learning needs a searchable topology, not a flat pile of documents.** Contrastive success/failure evidence and task-specific sub-skill routing can improve learning quality while reducing irrelevant prompt tokens.
3. **General computer use needs cross-application process verification.** A task that alternates between a game's visible state, source code, logs, a browser and build tools must be judged from its trajectory and artifacts, not from a plausible final message.

The implementation preserves STAR's existing authorities: the turn evaluator remains the endpointing policy scorer; the room director remains the social floor-control authority; skill evolution remains governed by independent evaluators and protected holdouts; the task ledger remains the long-running work authority; and the resource-admission controller remains the only compute governor.

---

## 1. Repository audit and non-duplication decisions

The current development branches already contain substantial foundations:

| Existing work | Responsibility | Run 43 decision |
|---|---|---|
| #1144 causal turn-taking evaluator | HOLD/EOT pause scoring, threshold/delay/timeout sweeps and Pareto frontier | Extend its input semantics with explicitly enabled right-censored turns; preserve the strict default |
| #1145–#1147 turn-policy validation | Grouped calibration/holdout, one-use holdout ledger and session-cluster uncertainty | Keep these validation layers; the new adapter does not bypass them |
| #1165/#1166 streaming rehearsal and paired variants | Spoken-task quality, groundedness, whisper/volume controls and mixed-runtime A/B evaluation | Reuse for audible response quality and non-inferiority |
| #1186 multiparty replay evaluator | Who is addressed, response appropriateness, silence and stopping after human resolution | Keep distinct from EoT: endpointing answers when a speaker is done; multiparty reasoning answers whether STAR should take the floor |
| #1121 skill retrieval | Existing skill search and retrieval benchmark | Add topology-aware experiments on top of this path; do not add a second registry |
| #1109 continual-learning evaluation | Held-out skill retention and transfer | Reuse for skill-evolution comparisons and negative-transfer checks |
| #1121/#1180 skill evolution research | Candidate skill generation and independent holdout review | Add contrastive evidence and sub-skill topology; never let a proposer grade itself |
| #1140/#1142 resource admission | Authoritative CPU/RAM/VRAM workload admission | Keep model and skill routing subordinate to this controller |
| #1167 streaming inference benchmark | First content, completion time and usage metadata | Keep model latency separate from conversational endpointing delay |
| #1182 game-control gate | Fresh observation, target and consent binding for future input adapters | Learning and benchmark evaluation never grants game-control permission |
| #1184 active perception | Bounded evidence selection | Reuse its observation budget; do not add a second capture or compute scheduler |

The new EoT adapter is metadata-only and does not capture audio, transcribe speech, call a model, identify speakers, control playback, or authorize a response.

---

## 2. LiveKit EoT-Bench — multilingual, causal endpointing

Primary references:

- Repository: https://github.com/livekit/eot-bench
- Dataset: https://huggingface.co/datasets/livekit/eot-bench-data
- Benchmark guide: https://livekit.com/benchmarks/eot-bench

### 2.1 What the benchmark measures

EoT-Bench evaluates the actual production decision at each pause: should the assistant take the floor now, or keep listening? It uses complete turns with causal silence spans rather than isolated clips.

The public dataset covers 14 languages: Arabic, Chinese, Dutch, English, French, German, Hindi, Indonesian, Italian, Japanese, Korean, Portuguese, Spanish and Turkish.

Each turn includes silence spans of at least 100 ms. A span is labeled HOLD when the user is pausing mid-thought and EOT when the user has actually finished.

Version 1.1 adds two useful English cohorts:

- accented: 800 turns of accented English.
- short_turns: 1,088 short replies. Half end at the end of the turn; the other half stop at a mid-turn pause and therefore contain no observed EOT span.

This is important for STAR's VTuber voice. Short acknowledgements such as "yes", "okay", or a brief partial phrase are precisely where a pause-only policy can either cut someone off or leave unnecessary dead air.

### 2.2 Separate conversational delay from model latency

EoT-Bench exposes three policy controls:

1. threshold: minimum EOT confidence.
2. action_delay: minimum silence duration before a score may trigger.
3. timeout: maximum wait before the policy ends the turn.

Its main comparison is the tradeoff between false cutoffs and endpointing delay. The benchmark also includes a silence-only VAD baseline and reports operating points/Pareto frontiers.

**Endpointing delay is not model inference latency.** A model may return its score quickly while the turn policy deliberately waits to avoid interrupting the speaker. STAR must therefore keep these measurements separate:

| Measurement | Meaning |
|---|---|
| Endpointing latency | Dead air after the human has actually finished |
| False-cutoff rate | Fraction of mid-turn HOLD pauses that trigger an assistant response |
| First-content latency | Time from model request to first non-empty generated content |
| First-audible latency | Time until the listener hears STAR |
| Inter-token latency | Spacing between generated tokens/chunks |
| Playback/queue delay | Time spent waiting for TTS, audio output, or the speaking floor |

Never claim a faster model based only on lower endpointing delay, or a more natural streamer based only on lower TTFT.

### 2.3 Right-censored turns are not failed turns

The EoT-Bench short-turn cohort contains rows whose final observed silence is still a HOLD. There is no observed final user-turn boundary.

STAR's previous stream_turntaking_eval contract required exactly one END_OF_TURN span for every turn. That is correct for complete private rehearsal turns, but too strict for a benchmark containing intentionally censored short-turn observations.

The companion implementation adds an opt-in allow_censored_turns mode:

- A complete turn still has exactly one EOT span.
- A censored turn may have zero EOT spans.
- No turn may have more than one EOT span.
- The dataset must still contain at least one complete turn, because endpointing latency and missed-final rate cannot be estimated from an all-HOLD dataset.
- HOLD spans from censored turns remain in the false-cutoff denominator.
- Censored turns do not create fabricated missed-final events or fabricated endpointing latency.
- The default remains strict (allow_censored_turns=False), so existing private rehearsal behavior does not silently change.

This lets STAR use the short-turn cohort without biasing the results by dropping its HOLD pauses or pretending an unobserved final turn occurred.

### 2.4 Metadata-only adapter

New module: star/eot_bench_adapter.py  
Tests: tests/test_eot_bench_adapter.py  
Companion implementation: draft PR #1187, stacked on #1144.

The adapter accepts the benchmark's normalized span_set and predictions records. It does not load raw Hugging Face audio or message text.

It:

- Converts source row IDs to opaque SHA-256-derived turn/span references.
- Hashes language/cohort into a bounded environment reference.
- Verifies the prediction language and label match the source span.
- Verifies timestamp is aligned with start + silence_dur.
- Rejects duplicate span rows, unknown prediction spans and duplicate score timestamps.
- Rejects invalid, non-finite or out-of-range probabilities.
- Preserves missing scores as missing evidence; it does not invent a score.
- Mirrors the upstream policy-metric HOLD filter by default: 200–5,000 ms.
- Always retains EOT spans, even when they are shorter than the HOLD filter.
- Records filtered HOLD counts, censored-turn counts, missing-score spans and score-point counts.
- Returns no raw dataset IDs, transcripts, audio or provider identities.

The caller should first use the upstream span_set.parquet and predictions.parquet artifacts, then pass their mapping records to the adapter. A DataFrame can be converted with to_dict("records"). The adapter adds no third-party runtime dependency.

### 2.5 Split and cohort discipline

Run each language/cohort as a separate evaluation slice where possible. Pin:

- Dataset revision and split.
- EoT-Bench harness revision.
- Model/provider adapter revision.
- Inference interval.
- Transcript lag.
- HOLD duration filter.
- Threshold, action-delay and timeout grids.
- Silence-only baseline configuration.

The public schema exposes turn IDs, language, spans, optional cohort, messages and words; it does not promise a stable conversation/session grouping key. Use the upstream train/validation/test split and do not claim session-independent holdout guarantees unless the selected dataset revision supplies an explicit grouping key.

---

## 3. SkillCAT — contrastive, assessed, topology-aware skill evolution

Paper: https://arxiv.org/abs/2606.13317

SkillCAT separates skill evolution into three useful ideas:

1. **Contrastive Causal Extraction:** sample multiple trajectories for the same task and compare successful and failed attempts to identify evidence that explains the outcome difference.
2. **Assessment-Augmented Evolution:** replay each candidate skill patch on source-task clones and keep only patches that improve or preserve verified outcomes before merging.
3. **Topology-Aware Task Execution:** compile skills into a routable sub-skill topology so inference loads only the capability nodes relevant to the current task.

The paper reports up to 40.40% average improvement over its evaluated baselines. That is a benchmark-specific paper result, not a STAR result and not a promised gain on Roblox, Windows or streaming tasks.

### STAR application

STAR already has a bounded skill evolution lab and skill retrieval. The next improvement should be a stronger lifecycle around them:

1. Collect multiple attempts for the same task seed or a matched seed family.
2. Obtain an independent task outcome, not the model's self-assessment.
3. Pair successful and failed attempts.
4. Extract only differences supported by the action/evidence trace.
5. Propose a small candidate skill patch.
6. Replay the candidate on source-task clones.
7. Run regression tasks and unrelated tasks to detect negative transfer.
8. Freeze the candidate before sealed holdout evaluation.
9. Route the candidate through owner review and the existing promotion/rollback path.

### Topology-aware skill retrieval

Represent skills as a dependency graph rather than a flat prompt bundle.

Example for a Roblox inventory task:

- Roblox project inspection
  - Luau typing and API verification
  - server/client replication
  - data validation
  - inventory data model
  - UI rendering
  - multiplayer test harness
  - persistence and recovery

At inference time, retrieve the smallest subgraph needed for the current task. Dependencies are included only when the task plan requires them. A task about UI layout should not load unrelated Blender rigging, game economy, or server operations instructions.

Measure the benefit rather than assuming it:

- Recall@k and MRR for required skill nodes.
- Number of irrelevant nodes loaded.
- Prompt tokens p50/p95.
- Skill retrieval latency p50/p95.
- Task success and verifier agreement.
- Held-out transfer.
- Negative-transfer rate.
- Time-to-first-content under the same inference server.

This is both an intelligence improvement and a potential speed improvement: better retrieval can reduce context size without reducing the evidence required to solve a task.

---

## 4. MemSkill — learn how to remember, not only what to remember

Repository: https://github.com/ViktorAxelsen/MemSkill

MemSkill makes an important distinction: its evolving skills are **meta-memory policies**, not the stored facts or experiences themselves.

They describe what information should be extracted from an event, what deserves long-term retention, how to retrieve information for a task, what should remain short-lived, when an old memory is no longer useful, and how to refine memory construction from hard cases.

### STAR application

Use memory-policy candidates to improve task-conditioned memory selection:

- A game session may need a compact strategy and verified control mapping.
- A Roblox debugging session may need the exact failing API, reproduction steps and tested fix.
- A research task may need source-linked claims, confidence and contradictions.
- A livestream may need a short topic/reply context, not a permanent transcript.

The memory policy must remain separate from memory content. A learned policy may propose what to preserve, but it must not directly delete, rewrite or export persistent user memory. STAR's existing governed consolidation, provenance and retention rules remain authoritative.

Evaluate memory policies on task outcomes and tool choices, not only on whether a question can retrieve a fact. Include stale, contradictory, irrelevant and privacy-sensitive memories. Test rollback of the policy independently from rollback of stored memory.

---

## 5. SkillLearnBench — evaluate the whole skill-to-outcome chain

Benchmark: https://cxcscmu.github.io/SkillLearnBench/

SkillLearnBench contains 20 skill-dependent tasks across 15 sub-domains and 100 verified instances. It separates three levels:

1. **Skill quality:** coverage, executability and safety of the generated skill.
2. **Trajectory:** whether the agent actually invokes the skill and follows the useful procedure.
3. **Task outcome:** whether an independent verifier accepts the final result.

Its paper reports that continual learning does not improve every task uniformly, stronger foundation models do not guarantee better generated skills, and self-feedback alone can drift recursively. Multiple iterations with external feedback are more reliable than ungrounded self-critique in the evaluated setting.

### STAR application

Every skill experiment should answer three separate questions:

- Is the skill itself accurate, complete and safe?
- Did STAR actually use it correctly?
- Did using it improve the verified result?

A skill that looks excellent but is never retrieved is not useful. A skill that is retrieved but ignored by the planner is not useful. A skill that is followed but produces a failing project should not be promoted.

---

## 6. WindowsWorld and WeaveBench — real cross-application intelligence

Primary references:

- WindowsWorld: https://aclanthology.org/2026.findings-acl.750/
- WeaveBench: https://arxiv.org/abs/2606.09426
- WindowsWorld code: https://github.com/HITsz-TMG/WindowsWorld

### 6.1 WindowsWorld

WindowsWorld contains 181 tasks across 17 desktop applications, averaging five sub-goals per task; 78% of tasks are inherently multi-application. Its paper reports that evaluated agents achieved less than 21% success on multi-application tasks and struggled especially with conditional workflows spanning three or more applications.

This exposes a gap between "can click an app" and "can complete a real workflow across apps."

### 6.2 WeaveBench

WeaveBench contains 114 long-horizon tasks across eight domains. Tasks interleave GUI observations/actions with CLI and code operations in one trajectory. Its trajectory-aware judge inspects deliverables, files, screenshots, logs and action traces, and looks for shortcut behavior such as fabricated visual evidence or hard-coded metrics.

The paper reports a best pass rate of 41.2% for the evaluated model/runtime pairings and finds that outcome-only grading can overestimate agent performance. Those are paper results, not STAR results.

### 6.3 STAR application: Creator Brain and general computer use

A representative STAR workflow should be:

1. Open a game project in its editor.
2. Inspect the rendered game and reproduce a visual/gameplay defect.
3. Capture an approved screenshot or structured observation.
4. Inspect source code, build logs and test output.
5. Make the smallest relevant patch.
6. Rebuild or reload the project.
7. Replay the same reproduction case.
8. Verify the original defect is gone.
9. Verify unrelated behavior did not regress.
10. Produce the changed-file list, test results and artifact manifest.

The evaluation must inspect the action trace and final artifacts. A final assistant message claiming "fixed" is not proof.

Run cross-app benchmark tasks only in disposable VMs with synthetic accounts and fixtures. Never use the owner's logged-in desktop, personal browser profile, real project secrets or production credentials as benchmark data.

---

## 7. Gaming and game-development capability expansion

GameWorld and Gym-Anything-RT are already present in the Game Lab catalog. Run 43 connects them to the cross-app workflow research rather than adding another game-control system.

### Gamer Brain

Measure separately:

- Paused reasoning performance.
- Slowed-environment performance.
- True real-time performance.
- State-verified task success.
- Partial progress.
- Invalid actions.
- Observation age at action time.
- Recovery after a failed attempt.
- Held-out map/seed transfer.
- Strategy reuse across different games.

A memorized key sequence is not general gameplay intelligence. Require unfamiliar seeds and environment changes.

### Creator Brain

Use the same skill graph to compose game design and progression, engine-specific implementation, Luau/GDScript/C#/C++ programming, UI and accessibility, animation/rigging/VFX, asset import and material setup, multiplayer and replication, performance profiling, and build/test/playtest.

The final result must be a working project with reproducible tests and visible in-engine verification, not merely generated source code.

---

## 8. Human-feeling VTuber streaming

Run 43 complements the existing multiparty evaluator and room director.

These are separate decisions:

- **Endpointing:** has the current speaker finished?
- **Addressee/social intent:** is STAR being addressed or invited to speak?
- **Floor arbitration:** is it appropriate for STAR to take the floor now?
- **Playback:** can the voice actually begin without interrupting another active output?
- **Avatar synchronization:** do expressions and mouth movement follow the actual audio playback clock?

A more natural STAR should respond quickly when directly addressed without cutting off mid-thought, let viewers talk to one another without answering every message, recognize when another participant has already resolved a question, preserve meaningful silence, use contextual acknowledgements rather than repetitive filler, vary prosody and pacing while retaining a consistent voice identity, align facial expressions with audible delivery and interruption state, and remain transparent that she is an AI character.

Do not optimize for speaking time. Optimize for correct floor decisions, low false interruptions, grounded answers, natural timing and viewer experience.

---

## 9. Faster inference without sacrificing intelligence

Run 43 adds a more precise speed hypothesis: **reduce irrelevant context before increasing model size or adding parallel workers.**

The skill topology experiment should compare flat retrieval against task-specific subgraph retrieval using identical tasks, model, prompt policy and hardware.

Measure:

- Prompt tokens p50/p95.
- Prefill time p50/p95.
- First-content latency p50/p95.
- Inter-token latency p95.
- Decode tokens/s under matched output lengths.
- Retrieval Recall@k/MRR.
- Verified task success.
- Escalation rate to the deep model.
- Queue wait and CPU/RAM/VRAM during mixed voice/game/OBS load.

Keep these constraints:

1. The fast model handles only tasks within its validated quality envelope.
2. The deep model receives the same evidence and constraints when escalation occurs.
3. Background research yields to the foreground voice/game deadlines.
4. The existing resource-admission controller owns compute budgets.
5. Speculative decoding is tested only with a supported model/backend and exact pinned build.
6. A speed improvement is accepted only if task quality and stream quality remain non-inferior.

Do not use benchmark results from H100, multi-GPU or different operating systems as predictions for STAR's local 8 GB GPU.

---

## 10. Benchmark manifest additions

The companion Run 43 manifest update records:

- Exact EoT dataset and harness revisions.
- Language and cohort filters.
- Minimum silence span and HOLD duration bounds.
- Inference interval and transcript lag.
- Threshold/action-delay/timeout grids.
- Whether right-censored turns were enabled.
- Retained HOLD/EOT counts and censored-turn counts.
- False-cutoff, missed-final and endpointing-latency metrics.
- Model first-content and inter-token metrics separately.
- Skill topology revision, retrieval quality, prompt-token reduction and negative transfer.
- Cross-app benchmark revision, VM image, app count, workflow checkpoints, artifact manifest and trajectory digest.
- Explicit flags proving raw audio, transcripts and personal files were not retained.

A benchmark result must identify its dataset, code, model, prompt, adapter, environment and verifier revisions. Otherwise it is not reproducible.

---

## 11. Acceptance criteria

### EoT-Bench integration
- Import public span_set and predictions records without loading raw audio.
- Preserve HOLD-only short turns as censored evidence.
- Reject duplicate/unknown spans, label/language mismatches and noncausal timestamps.
- Keep the strict evaluator default unchanged.
- Report the silence-only baseline and policy Pareto frontier.
- Separate endpointing latency from model inference latency.
- Run English general/accented/short-turn cohorts first; add other languages only when the chosen model supports them.
- Keep dataset split and cohort results explicit.

### Skill topology
- Compare flat and topology-aware retrieval on matched tasks.
- Show retrieval recall and prompt-token changes.
- Require independent task verifiers.
- Test held-out compositions and negative transfer.
- Keep protected holdouts sealed from the skill proposer.
- Require owner review before promotion.

### Cross-application intelligence
- Use a disposable VM and synthetic data.
- Require intermediate checkpoints and final-state verification.
- Preserve a content-free trajectory digest and artifact hashes.
- Reject fabricated screenshots, hard-coded success and missing logs.
- Test failure recovery and cancellation.

### VTuber and gaming
- Replay endpointing and multiparty cases independently.
- Measure false interruption and missed direct-request rates.
- Keep paused, slowed and real-time game scores separate.
- Verify voice, avatar, game and OBS under one mixed-load rehearsal.
- Do not enable new live permissions by default.

---

## 12. Implementation and review status

Run 43 adds three reviewable workstreams:

- **Research PR #1180:** this Run 43 document and the benchmark manifest update, based on main.
- **Game Lab PR #1182:** five additional reviewed research sources and regression assertions, based on main.
- **Voice implementation PR #1187:** metadata-only EoT-Bench adapter plus opt-in right-censored turn evaluation, stacked on the existing causal turn-taking PR #1144.

PR #1187 must not be merged ahead of its parent #1144. The research and catalog branches are independent of that voice implementation chain. No PR in this run is merged into production main.

---

## 13. Next engineering priorities

1. Finish exact-head CI for the current parent/child PR chain.
2. Run the EoT-Bench adapter against pinned public span-set and prediction artifacts.
3. Add language/cohort reports and confidence intervals without exposing raw IDs.
4. Compare the current flat skill router with a topology-aware subgraph router.
5. Build paired success/failure skill-evolution replay with independent task verifiers.
6. Add a WeaveBench-style synthetic cross-app workflow suite for game debugging and creator tasks.
7. Run local inference A/B tests with the exact llama.cpp build and target GPU.
8. Complete a Windows mixed-load rehearsal: voice, game observation/control, OBS, avatar and background research.

## Final decision

STAR's next meaningful intelligence improvement is not a larger prompt or another agent swarm. It is a tighter learning-and-verification loop:

**observe the right evidence → retrieve the right sub-skills → act through the correct authority → verify the actual outcome → preserve only the reusable lesson → test transfer on unseen tasks.**

That same loop should govern how STAR plays games, creates games, researches general knowledge, operates desktop applications and participates in livestream conversations.
