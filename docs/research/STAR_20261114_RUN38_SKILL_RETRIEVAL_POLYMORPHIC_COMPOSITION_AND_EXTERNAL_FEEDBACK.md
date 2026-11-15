# STAR Run 38 — Skill Retrieval, Polymorphic Composition, and External-Feedback Learning

**Research date:** 2026-11-14 (America/Chicago)  
**Repository:** `oncoursemail/Star-AI-Project`  
**Research branch:** `research/star-run24-integration-blueprint-20261114`  
**Companion catalog branch:** `feat/game-control-gate-20261114-run31`  
**Scope:** scalable skill discovery, reusable cross-domain procedures, continual skill improvement, low-latency routing, Gamer Brain, Creator Brain, and natural VTuber operations.

---

## Executive decision

STAR already has a real skill-retrieval implementation under draft PR #1121, an opt-in embedding router with cache-space validation under #1098, and separate continual-learning and memory-governance evaluators (#1109, #1117, #1136). Run 38 therefore does **not** propose another skill library, vector database, memory store, or agent swarm.

The next useful step is to make the existing skill system more selective, compositional, and evidence-driven:

1. **Retrieve only when a task needs a skill.** Reuse #1121's need-aware gate and cached BM25 path. Keep the common path dependency-free and local.
2. **Separate a skill's semantic goal from its environment-specific implementation.** Use PolySkill's polymorphic abstraction as a design reference: one abstract contract can have different adapters for Roblox Studio, a particular game, Blender, desktop software, or a browser.
3. **Compose verified skills as a typed dependency graph.** A multi-step task should connect explicit preconditions, outputs, and postconditions instead of asking one giant prompt to improvise every step.
4. **Do not let STAR grade her own homework.** SkillLearnBench finds that self-feedback alone can drift; promote skills only with independent environment verifiers, external feedback, and sealed holdouts.
5. **Optimize total task cost and live responsiveness.** Avoid loading every skill body or embedding model into the foreground voice/game path. Use a cheap retrieval cascade and admit expensive reranking only when it can change the decision.
6. **Make the same skill contracts serve streaming, gaming, creation, and general knowledge without merging their trust boundaries.** The room director still owns speech; GameControlGate still owns game-action permits; Studio and desktop adapters retain their own permissions.

This is a research, catalog, and integration update. It does not install a model, benchmark dataset, dependency, or third-party skill; change model routing; grant new permissions; create platform credentials; or enable public streaming.

---

## 1. Repository audit: extend existing work, do not duplicate it

The current development stack already has the major pieces:

| Existing work | Run 38 decision |
|---|---|
| #1121 — cached BM25 skill retrieval and offline evaluation | Keep as the default lexical discovery path. Extend its gold-label evaluation with the new research; do not replace it with a heavyweight embedding model. |
| #1121 — need-aware skill evaluator | Preserve the `required / optional / not_needed` decision as a separate stage from ranking. A high-ranked skill is not automatically needed. |
| #1098 — embedding cache fingerprint validation | Keep embeddings opt-in and reject mixed model spaces. Use semantic retrieval only as a measured fallback for paraphrase/ambiguity. |
| #1109 — continual-learning memory transfer evaluator | Reuse paired memory-off/on and transfer discipline; skill improvements must not be credited to unrelated prompt, model, or memory changes. |
| #1117 — governed reversible memory consolidation | Keep owner review and rollback for persistent knowledge changes. A successful skill run does not authorize permanent memory mutation. |
| #1136 — temporal memory transfer and forgetting evaluator | Reuse stale-evidence, forgetting, and cross-session transfer checks. Retire or revalidate skills when their dependencies change. |
| #1178 — RoomTurnDirector / RoomStreamHost | Keep one audience, floor-control, moderation, and speech-delivery authority. A skill can prepare a candidate result, never grant itself the right to speak. |
| #1140 / #1142 — resource admission and stream-pressure governor | Keep one resource lease/admission authority. Retrieval and skill execution request budgets from it; they do not create a second scheduler. |
| #1182 — GameControlGate | Keep it as the only game-action authorization/permit authority. A skill adapter cannot bypass consent, allowlist, focus, freshness, stop, or release checks. |
| #1180 — research blueprint | Extend this existing reviewable research PR rather than creating another roadmap branch. |

### Important implementation truth

PR #1121 already adds dependency-free BM25 retrieval over STAR's bounded Agent Skills catalog, metadata-only search results, cache invalidation, Tool Workshop integration, and an offline JSONL evaluator. Its evaluator reports Recall@K, MRR@K, nDCG@K, first-query latency, and warm/cold p50/p95. The current implementation is not a semantic retriever and its score is not a calibrated probability.

PR #1098 already addresses a subtle embedding failure: an alias can point to new weights while cached vectors still belong to the old embedding space. Its canary fingerprint is a drift detector, not cryptographic model attestation. The next trusted improvement is an immutable server-side model/weights manifest, not a larger cache.

Run 38 should integrate with these existing PRs in dependency order. Do not merge stacked work or change production defaults automatically.

---

## 2. SkillRet: skill retrieval becomes a first-class intelligence problem

Primary paper: https://arxiv.org/abs/2605.05726  
Official code and dataset documentation: https://github.com/ThakiCloud/SKILLRET  
Dataset: https://huggingface.co/datasets/ThakiCloud/SKILLRET

SkillRet studies how an agent selects a small set of useful skills from a large library under context and latency constraints. The paper's original abstract reports 17,810 public skills, 63,259 training queries, and 4,997 evaluation queries across six categories and 18 subcategories. It reports that task-specific embedding/reranking training improves nDCG@10 over the tested prior and off-the-shelf retrievers.

### Version and corpus discrepancy — do not hide it

The current official code README documents a revised test split with 6,006 test skills, 4,392 test queries, and 7,187 labels. It explicitly says the split changed after the paper's original evaluation and that scores from the two splits are not directly comparable. It also records the original evaluation counts (6,660 / 4,997 / 8,347) and says the train split is unchanged. A reproducible STAR experiment must pin the Hugging Face dataset revision rather than follow the mutable head.

The current official implementation README also documents Python 3.13, CUDA 12.8+, at least one NVIDIA GPU for evaluation, and four GPUs for training; the published training recipes include 0.6B and 8B embedding models plus a 0.6B reranker. These requirements make the upstream training stack inappropriate as a default dependency for STAR's local 8 GB GPU. The correct first experiment is to evaluate STAR's existing BM25 baseline against a pinned, privacy-safe subset—not to install the full training stack.

### STAR application

Use SkillRet as an evaluation methodology and, only if its data license/access terms and revision are reviewed, as an optional offline benchmark. It is not a mandate to download its corpus or fine-tune its models.

Measure:
- Recall@1/3/5/10 and MRR@K.
- nDCG@K and query-level completeness.
- Need-aware precision/recall for `required`, `optional`, and `not_needed`.
- Cold and warm latency, p50/p95.
- Candidate count and skill-body bytes read.
- Context tokens added by the selected skills.
- Final verified task success, not retrieval score alone.

The main question is not “did the retriever return a relevant skill?” It is “did loading this skill improve the independently verified task outcome enough to justify its latency, context, and execution risk?”

---

## 3. PolySkill: separate abstract intent from concrete execution

ICLR 2026 paper: https://proceedings.iclr.cc/paper_files/paper/2026/hash/e350897ed832f9cad6f2e223e7acad6d-Abstract-Conference.html  
Official implementation: https://github.com/simonucl/PolySkill

PolySkill's core idea is to separate **what a skill accomplishes** from **how a particular environment executes it**. Its paper reports better skill reuse and transfer across evaluated websites, including unseen websites. Those are web-agent results; they are not direct evidence of Roblox, desktop, game, or Blender transfer.

The public implementation is an MIT-licensed clean-room re-release built on BrowserGym and LiteLLM. Its README notes that WebArena requires self-hosted sites and Mind2Web evaluation interacts with the live web and uses model/API access. STAR should borrow the abstraction and evaluation design, not run live-web experiments or import its dependencies into production.

### STAR's polymorphic skill contract

A skill should have two layers:

**Abstract contract**
- Semantic goal.
- Preconditions.
- Required evidence.
- Expected state transition.
- Postconditions.
- Failure classes.
- Recovery intent.
- Independent verifier interface.
- Resource and deadline budget.
- Risk and permission requirements.

**Environment adapter**
- Environment and version identity.
- Concrete tool/action mapping.
- Observation schema.
- Input constraints.
- Adapter-specific preconditions.
- Exact verifier implementation.
- Recovery and cleanup behavior.

Example: the abstract skill `collect_resource` can be realized differently in a survival game, a Roblox test fixture, or a crafting simulator. The shared concept is not a universal key sequence. Each adapter must independently prove that the action is permitted and that the resource state actually changed.

### Compositional planning

Represent a complex task as a directed acyclic graph (DAG) of skill contracts:

- Each node declares typed inputs and outputs.
- Edges carry only validated artifacts or state references.
- Preconditions must be satisfied before a node becomes runnable.
- A node's verifier must pass before its output is released to dependents.
- Failed nodes invalidate dependent outputs and trigger bounded recovery.
- Cycles require an explicit iterative controller with a maximum iteration and wall-clock budget.

Do not let the LLM invent hidden dependencies between skill steps. The planner proposes the graph; a deterministic validator checks schema, dependencies, permissions, and resource budgets before execution.

---

## 4. SkillLearnBench: external feedback beats recursive self-approval

Paper: https://arxiv.org/abs/2604.20087  
Official implementation: https://github.com/cxcscmu/SkillLearnBench

SkillLearnBench evaluates 20 skill-dependent tasks across 15 subdomains and 100 verified instances. It evaluates three distinct layers:

1. Skill specification quality.
2. Execution trajectory quality.
3. Final task outcome and efficiency.

Its reported analysis is especially relevant to autonomous self-improvement:
- No continual-learning method wins across all tasks and model backbones.
- Stronger LLM backbones do not consistently produce better skills.
- Repeated iterations with external feedback can improve skills.
- Self-feedback alone can cause recursive drift.

The official repository also documents that trials run in Docker; some tasks require API credentials or additional environment variables. It instructs users to dry-run first and keep worker counts bounded. STAR must not automatically install or execute this benchmark on the live streamer machine.

### STAR rule: self-critique is a hypothesis, not a verifier

A failed run may generate a proposed lesson, but that lesson remains untrusted until checked against:
- A deterministic test or authoritative environment state.
- An independent reviewer or separately generated test.
- A repeated attempt under the same pinned conditions.
- A distinct holdout instance that was not used to write the skill.

The agent that wrote a skill must not be the sole agent that grades it. LLM-as-judge can be a secondary signal, never the only verifier for a consequential skill.

### Skill lifecycle

`candidate → sandboxed → practice-verified → externally-reviewed → sealed-holdout-passed → owner-approved → monitored → retired`

A failure, dependency update, model change, tool schema change, permission change, or verifier revision can demote a skill back to revalidation. Skill promotion is never automatic for external side effects, live account actions, publishing, moderation, or public broadcast control.

---

## 5. Recommended retrieval cascade: faster without making STAR less capable

The live path should use the cheapest reliable stage first:

1. **Intent/need gate:** classify whether a skill is required, optional, or unnecessary. If no skill is needed, skip retrieval.
2. **Cached lexical retrieval:** use #1121's BM25 index over bounded metadata; return a small top-K list only.
3. **Need-aware filtering:** remove skills whose environment, version, permissions, or preconditions do not match.
4. **Optional semantic fallback:** only if lexical candidates are ambiguous or low-confidence; use #1098's cache fingerprint protection and a separately admitted worker.
5. **Optional rerank:** score only a small candidate set. Never send the whole library or every skill body to a large model.
6. **Progressive disclosure:** read only the chosen skill's bounded instructions after the task actually needs them.
7. **Execution plan validation:** verify DAG, preconditions, permission scopes, resource lease, and deadline.
8. **Execute and independently verify:** return only verified outputs to the caller.
9. **Evidence capture:** record compact, content-minimized outcome metadata and artifact hashes for later learning.

### Why this should improve speed

The expected savings come from avoiding unnecessary skill loads, large prompt prefixes, repeated filesystem reads, redundant embedding calls, and failed tool invocations. These are hypotheses to measure, not claimed STAR speedups.

The foreground voice/game loop must never wait for background index rebuilding, dataset evaluation, skill generation, or long-form research. Cache rebuilds and candidate-skill creation run as low-priority background work under the existing resource-admission controller.

### Context budget

Start with a small candidate budget (for example, top 5 metadata results), then use a measured ablation to choose K. The system should not load five full skills by default. It should load only the minimum instructions needed for the chosen task.

---

## 6. Domain applications

### Gamer Brain

Use abstract goals with game-specific adapters:

- Navigate to a visible objective.
- Gather a resource.
- Equip or craft an item.
- Evade a hazard.
- Engage an enemy.
- Heal or recover.
- Complete a checkpoint.
- Coordinate with a teammate.
- Learn a map or mechanic.

Each adapter must bind to a specific game/build, approved process, current session, observation epoch, and allowed control set. It must call the existing GameControlGate immediately before action. The skill contract cannot authorize input.

Learning should use matched starting states when possible, record both success and failure, and validate on unseen maps/seeds or game versions. Report real-time, slowed, and paused performance separately. A memorized route is not general game intelligence.

### Creator Brain

Create reusable abstract workflows with engine-specific adapters:

- Inspect a scene before editing.
- Locate a script or object.
- Make a bounded edit.
- Run static analysis and tests.
- Launch a playtest.
- Capture visual evidence.
- Compare expected and observed state.
- Repair one identified failure.
- Re-run the relevant regression suite.

Roblox Studio, Godot, Unity, and Blender need separate adapters and verifiers. For Roblox, use official Studio tools and StudioTestService where available; keep publishing and live Open Cloud operations behind explicit owner approval. For Blender, verify geometry, materials, rig constraints, and render outputs rather than accepting a text-only success claim.

### General knowledge and research

Keep factual knowledge skills separate from procedural skills. A research skill should cite sources, preserve publication date and scope, detect contradictions, and state freshness. A procedural skill should prove that it can execute a task. Reading an API reference does not prove that STAR can use the API correctly.

### VTuber and streaming

Use the same contracts for bounded internal workflows such as:
- Summarize a verified match.
- Prepare a highlight candidate.
- Check local stream health.
- Recover a disconnected local service.
- Draft a post-stream recap.
- Prepare a viewer-question response.

But:
- The RoomTurnDirector owns whether STAR speaks.
- The delivery ledger owns whether a result was actually announced.
- Viewer chat is untrusted input and cannot invoke skills or tools.
- Moderation, chat writes, publishing, account actions, and public broadcast control remain separately permissioned.
- A skill result can be prepared in the background while the live voice loop continues; it is returned to the same task/conversation and spoken only when the room director permits it.
- Natural presence means context, timing, humor, listening, and appropriate silence—not pretending to be a human or inventing experiences.

---

## 7. Proposed data contracts (design only)

The following is a design sketch, not a new runtime schema committed by this research document.

```yaml
skill_contract:
  id: "domain.intent"
  revision: "immutable-content-digest"
  abstract_goal: "semantic outcome"
  environment:
    family: "game | roblox | blender | desktop | browser | research"
    adapter_id: "specific-adapter"
    version_constraint: "pinned-or-compatible-range"
  inputs:
    - name: "target"
      type: "verified-reference"
  preconditions:
    - "required observation or state predicate"
  expected_postconditions:
    - "independently observable state predicate"
  verifier:
    type: "deterministic | engine-state | independent-visual | reviewed"
    revision: "verifier-digest"
  permissions:
    profile: "read_only | sandbox_write | owner_approved"
    external_side_effects: false
  resources:
    deadline_ms: 0
    max_model_calls: 0
    max_cpu_percent: 0
    max_ram_mib: 0
    max_vram_mib: 0
  recovery:
    max_attempts: 0
    cleanup_contract: "release-controls-and-restore-safe-state"
  provenance:
    source_refs: []
    verified_runs: []
  lifecycle:
    status: "candidate"
    expires_at: null
    revalidate_on:
      - "adapter-change"
      - "tool-schema-change"
      - "environment-version-change"
      - "verifier-change"
```

### Evidence record

Keep evidence separate from the instruction body:

- Opaque run and task IDs.
- Skill ID/revision and adapter revision.
- Environment/build identifier.
- Preconditions observed.
- Verifier identity/revision and result.
- Outcome category and recovery result.
- Monotonic timing and resource summaries.
- Evidence/artifact hashes.
- Holdout cohort reference.
- External-review reference, if any.

Do not store raw viewer chat, private voice transcripts, voiceprints, raw audio/video, credentials, or owner personal files in generic skill evidence.

---

## 8. Evaluation plan

| Layer | Required measurements | Failure that must be visible |
|---|---|---|
| Need gate | Precision/recall, calibration, false-positive load rate | Unneeded skills loaded into simple tasks |
| Retrieval | Recall@K, MRR, nDCG, completeness | Correct skill missed or distractor ranked first |
| Contract quality | Preconditions, postconditions, verifier coverage, safety | Vague or untestable skill |
| Composition | DAG validity, dependency success, artifact typing | Invalid edge or stale upstream output |
| Execution | Step count, time, tool calls, recovery | Skill found but not successfully applied |
| Outcome | Independent success, false-success rate | Agent claims completion without state change |
| Transfer | Unseen environment/map/seed/version | Overfitted skill |
| Continual learning | Retention, forgetting, stale-skill reuse, regression | New skill damages old abilities |
| Streaming | First-audio p95, interruption stop p95, appropriate silence, delivery join | Background skill blocks live interaction |
| Mixed load | CPU/RAM/VRAM, game FPS p95/p99, OBS render/encoder lag | Capability gain harms stream/game stability |

### Required ablations

Compare on the same preregistered tasks and model revision:

- No skills.
- Current cached BM25 only.
- Need gate + BM25.
- Need gate + BM25 + optional embedding fallback.
- Polymorphic contract + environment adapter.
- Composed skills with and without independent verification.
- Self-feedback-only candidate generation versus external-feedback plus holdout.

Use paired tasks, balanced order, independent verifiers, disjoint practice/validation/holdout sets, and exact version manifests. A missing result is inconclusive, not a pass. Report both task quality and latency/cost.

---

## 9. Implementation sequence

1. **Audit #1121 exact head and evaluator inputs.** Keep current BM25 behavior unchanged while adding versioned, private gold-label cases.
2. **Add a pinned SkillRet-compatible retrieval evaluation adapter.** Use a small approved sample or synthetic cases first; do not download the full corpus automatically.
3. **Add PolySkill-inspired contract metadata.** Start with a schema validator and two low-risk adapters; do not import the upstream runtime.
4. **Add composition validation.** Check DAG acyclicity, typed outputs, permission union, resource budgets, and verifier coverage before any node executes.
5. **Add SkillLearnBench-inspired external-feedback evaluation.** Keep skill author and verifier independent; compare self-feedback and external-feedback arms.
6. **Integrate with existing skill promotion and memory governance.** No new permanent memory store and no automatic owner-side effect.
7. **Add domain adapters gradually.** Begin with offline development tasks and deterministic Roblox fixtures, then game practice, then private stream operations.
8. **Run target Windows mixed-load acceptance.** Only after the offline and isolated harnesses pass.

### Suggested first low-risk pilot

Use synthetic and repository-local tasks that do not require network or external credentials:
- Find the correct skill for a Luau debugging request.
- Decide that a simple factual question needs no procedural skill.
- Compose inspect → edit → test for a toy project.
- Execute the same abstract file-organization skill through two disposable fixture adapters.
- Verify that a stale adapter version is rejected.
- Verify that a skill written by one agent cannot self-promote without an independent result.

---

## 10. Acceptance gates

Do not call this complete until:

- Search returns only metadata and never loads unselected skill bodies.
- Need-gate decisions are measured separately from retrieval ranking.
- Dataset and skill-library revisions are pinned.
- Skill contract and adapter versions are explicit.
- The planner rejects cyclic/ill-typed graphs and missing verifiers.
- Permission scopes are checked by the trusted adapter, not by skill text.
- Viewer messages cannot trigger skill execution.
- A self-generated success claim cannot promote a skill.
- Held-out tasks are disjoint and cannot be used for skill writing.
- Stale skill, changed dependency, and changed verifier cases fail closed.
- Foreground voice/game deadlines remain within the measured baseline under background retrieval and evaluation.
- Private Windows rehearsal confirms no regression to game FPS, OBS frame health, audible latency, or interruption behavior.

---

## 11. Source register and limitations

- SkillRet paper: https://arxiv.org/abs/2605.05726
- SkillRet official implementation: https://github.com/ThakiCloud/SKILLRET
- SkillRet dataset: https://huggingface.co/datasets/ThakiCloud/SKILLRET
- PolySkill ICLR 2026 paper: https://proceedings.iclr.cc/paper_files/paper/2026/hash/e350897ed832f9cad6f2e223e7acad6d-Abstract-Conference.html
- PolySkill official implementation: https://github.com/simonucl/PolySkill
- SkillLearnBench paper: https://arxiv.org/abs/2604.20087
- SkillLearnBench official implementation: https://github.com/cxcscmu/SkillLearnBench
- Existing STAR retrieval implementation: https://github.com/oncoursemail/Star-AI-Project/pull/1121
- Existing embedding-cache integrity: https://github.com/oncoursemail/Star-AI-Project/pull/1098
- Existing continual-learning evaluation: https://github.com/oncoursemail/Star-AI-Project/pull/1109
- Existing memory governance: https://github.com/oncoursemail/Star-AI-Project/pull/1117
- Existing temporal-memory evaluation: https://github.com/oncoursemail/Star-AI-Project/pull/1136

Research metrics belong to their original protocols. Website transfer scores are not Roblox/game transfer scores; benchmark retrieval scores are not STAR's retrieval scores; a skill catalog does not prove execution competence. No model weights, gated datasets, third-party skill code, API keys, or benchmark containers were installed. No neural inference speedup, game mastery improvement, human-equivalent behavior, physical Windows acceptance, or public-stream readiness is claimed.

**Run 38 decision:** improve STAR's existing skill retrieval and verification path first. A compact, need-aware, compositional skill system with independent evidence is more valuable—and more compatible with STAR's local hardware and live-stream deadlines—than loading a larger model or adding another agent framework.
