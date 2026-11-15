# STAR Run 56 — Skill Contract Sidecars, Evidence-Grounded Generalist Intelligence, and Long-Horizon VTuber Runtime

**Date:** 2026-11-15  
**Status:** research + optional SkillLibrary integration on draft PR #1209  
**Related acceptance:** #584

## Executive result

Run 56 closes one explicit gap from Run 54: the versioned Skill Contract parser is now discoverable through STAR's existing `SkillLibrary`, rather than remaining a standalone offline schema.

A skill may contain:

```text
skill-name/
  SKILL.md
  SKILL.contract.json   # optional, structured and declarative
  references/
  assets/
```

The existing Agent Skills discovery path remains metadata-only. The sidecar is read only after a skill is explicitly loaded. Legacy skills continue to work without a sidecar. An invalid or mismatched sidecar is reported as invalid and is never passed to the model as a contract.

This is deliberately not a second skill store, executor, scheduler, memory database, permission system, or promotion authority.

## 1. Research: preserve progressive disclosure

The Agent Skills specification defines a directory with a required `SKILL.md` and permits additional files and directories. Its client guidance separates discovery metadata, activated instructions, and on-demand resources.

STAR should preserve that low-context-cost design:

1. **Catalog:** name, description, source only.
2. **Activation:** the selected `SKILL.md` body and optional `SKILL.contract.json`.
3. **On-demand evidence:** references, assets, benchmark traces, and verifier artifacts only when needed.

The contract sidecar is a STAR extension, not a change to the portable Agent Skills format. Other Agent Skills clients can ignore it and continue using `SKILL.md`.

Security boundary:
- The sidecar is untrusted data.
- `required_capabilities` are descriptive requirements, never grants.
- Contract steps are not executable scripts or tool arguments.
- The host must recheck consent, target identity, permissions, freshness, resource leases, and policy at action time.
- Only independently verified, host-originated evidence may support a pass/fail label.
- A valid JSON document is not a trusted skill.

Primary sources:
- Agent Skills specification: https://agentskills.io/specification
- Agent Skills reference implementation: https://github.com/agentskills/agentskills
- Client implementation guidance: https://github.com/agentskills/agentskills/tree/main/docs/client-implementation

## 2. Research: game-playing intelligence must separate progress, control and completion

### GameWorld

GameWorld provides 34 browser games and 170 tasks across runner, arcade, platformer, puzzle and simulation genres. It supports both computer-use and semantic/generalist interfaces and evaluates outcomes from serialized game state rather than asking an LLM to judge screenshots.

Its August 2026 Fine-Control Protocol adds higher-frequency interaction and 400-step episodes. This is relevant to STAR because real-time game control and slower strategic reasoning should not be measured as if they were the same workload.

STAR implications:
- Keep a fast observation/action loop for movement and timing.
- Keep a slower strategic loop for objectives, routes, inventory and adaptation.
- Use only observations available to the acting agent; reserve hidden state for the independent evaluator.
- Report normalized progress and binary task completion separately.
- Record resets, action budgets, build/seed, observation age and evaluator version.
- Test recovery after mistakes and transfer to unseen maps/seeds.
- Never call a partial-progress run a win.

Sources:
- Project: https://gameworld-project.github.io/
- Code: https://github.com/gameworld-project/gameworld
- Paper: https://arxiv.org/abs/2604.07429

### Roblox Creator Brain and cross-engine creation

Keep the existing Roblox-specific OpenGameEval work (#1200) and causal mechanic experiments (#1199). Keep GameDevBench (#1108) as a separate Godot/general creator lane. Do not collapse game creation into game playing.

Creator acceptance should independently inspect:
- source/code correctness;
- scene/DataModel structure;
- saved project integrity;
- visual result at multiple viewports;
- actual playable behavior;
- performance and regression.

A screenshot is visual evidence, not proof of hidden scene structure. A successful build is not proof of a playable task.

Sources:
- OpenGameEval: https://github.com/Roblox/open-game-eval
- GameDevBench: https://github.com/waynchi/gamedevbench

## 3. Research: general computer-use intelligence needs long-horizon process evaluation

### OSWorld 2.1

As of this research date, the OSWorld-V2 repository identifies `osworld-v2.1` as its recommended active release. Its code, task files, gated assets, website, public assets and provider images must be pinned to matching release references. The 2.1 release includes updated task/evaluation workflows and task/asset snapshots.

Do not mix task files from one release with assets, websites or VM images from another. A benchmark run with incomplete gated assets or a mismatched website is not comparable.

STAR should start with a small, owner-approved, disposable Windows/Linux VM smoke set, not a full cloud campaign. Record the exact release manifest, image digest, task roster, evaluator, agent revision, action limit and environment snapshot. Any gated dataset access, cloud spend, credential, network exposure or provider provisioning needs separate owner approval.

Sources:
- OSWorld-V2: https://github.com/xlang-ai/OSWorld-V2
- OSWorld 2.1 release: https://github.com/xlang-ai/OSWorld-V2/releases/tag/osworld-v2.1
- Evaluation guidelines: https://github.com/xlang-ai/OSWorld-V2/blob/main/docs/PUBLIC_EVALUATION_GUIDELINE_v2.1.md

### WindowsWorld

WindowsWorld studies professional cross-application workflows: 181 tasks across 17 desktop apps, with 78% requiring multiple applications. Its reported agents struggled especially with workflows involving conditional decisions across three or more applications.

STAR implications:
- Evaluate complete workflows, not just isolated clicks.
- Add intermediate checkpoints after each consequential subgoal.
- Verify state in the destination app before moving on.
- Maintain a task ledger with dependencies, deadlines, partial completion and recovery.
- Keep per-app permissions and data scopes separate.
- Use synthetic accounts and disposable environments for evaluation.

Source: https://arxiv.org/abs/2604.27776

## 4. Research: streaming memory needs actor and version semantics

### EverMemBench

EverMemBench studies long-horizon, multi-party and multi-group conversations with interleaved topics, role-conditioned participants and information that changes over time. Its analysis highlights failures in multi-party attribution, temporal updates, and retrieval of implicitly relevant evidence.

STAR implications:
- Keep speaker and addressee references source-scoped and session-scoped.
- Never merge identical opaque IDs across audio, Twitch, YouTube or other platforms.
- Model changing facts as versioned assertions with provenance and validity, not as a single mutable string.
- Preserve the evidence event that supports a memory update.
- Distinguish "what was said", "what is currently believed", and "what was later corrected".
- Test multi-hop attribution and temporal updates on holdout sessions.
- Keep moderation/deletion and retention policy authoritative.

### Evidence-grounded propose / verify / commit

EGMEMORY proposes separating persistent message-level evidence from an active state, and using an evidence-grounded propose-verify-commit protocol for memory updates. It reports promising results on multi-actor memory benchmarks, but is a preprint; its numbers should not be treated as transferable STAR performance.

STAR should adapt the *protocol*, not create another memory database:
1. Append source-bound evidence to the existing governed ledger.
2. Propose a candidate state update with the exact evidence references.
3. Check contradictions, temporal validity, actor attribution and source trust.
4. Commit only through the existing trusted memory policy.
5. Preserve superseded assertions for audit where retention policy permits.
6. Abstain when evidence is incomplete or ambiguous.

Sources:
- EverMemBench: https://arxiv.org/abs/2602.01313
- EGMEMORY: https://arxiv.org/abs/2609.23465
- LongMemEval: https://arxiv.org/abs/2410.10813

## 5. Research: natural VTuber behavior is a control problem, not just a persona prompt

LiveKit's current turn-taking documentation separates user activity detection, interruption handling, preemptive generation, and audio preprocessing. This decomposition is important for STAR's live voice path.

Recommended state model:
- listening;
- waiting for a genuine turn end;
- preparing a response;
- permitted to speak;
- speaking;
- interrupted;
- stopped because a human resolved the question;
- silent / no response warranted.

Rules:
- Keep the existing RoomTurnDirector and actual playback owner as the sole authorities for speech and interruption.
- Preemptive generation may prepare privately, but it must not leak audio before the floor is granted.
- A new human turn, moderation hold, owner stop, or human resolution must cancel the exact pending generation.
- Do not confuse VAD silence, semantic endpointing, model TTFT, first audible PCM, playback queue delay and avatar presentation delay.
- Silence is a valid action.
- Commentary should be relevant to current gameplay and viewer context, not a constant narration stream.
- Avatar expressions should be derived from the same playback/scene intent that drives speech, with stale frames coalesced rather than queued.

Sources:
- LiveKit turn-taking tuning: https://docs.livekit.io/agents/logic/turns/tuning/
- Adaptive interruption handling: https://docs.livekit.io/agents/logic/turns/adaptive-interruption-handling/
- STAR existing work: #1105, #1106, #1178, #1186, #1159.

### Avatar control and believable motion

VTube Studio's official API supports user-approved plugins and custom Live2D parameters. Plugin access is a real control grant: STAR must request the documented permission and respect denial/revocation. Custom parameters are injected through the API; a parameter should have one clear writer, and values sent by a plugin must be refreshed at least once per second to remain active. The API documentation also warns against repeatedly requesting the full parameter list at 60+ FPS.

STAR implications:
- Keep one explicit owner-approved VTube Studio plugin identity and local endpoint.
- Register only the small set of custom parameters STAR's approved model actually needs.
- Use one parameter writer per parameter; arbitrate face tracking and STAR-authored motion rather than allowing competing writers.
- Drive mouth, cheek, head, shoulder and hair response from the same actual playback clock/PCM envelope as the audible speech.
- Bind every frame to a playback epoch and audible cursor; drop stale frames, and flush the current epoch on interruption before returning to a neutral pose.
- Use latest-wins coalescing for animation samples only. Never coalesce speech segments, game actions or durable events.
- Keep idle motion subtle and low-frequency; do not invent random gestures or facial emotion unrelated to the current scene.
- Treat custom parameter registration, API permission, connection readiness and model-loaded state as separate health signals.

Sources:
- VTube Studio API development page: https://github.com/DenchiSoft/VTubeStudio
- Plugin permissions and authentication: https://github.com/DenchiSoft/VTubeStudio/wiki/Plugins
- Existing STAR latest-wins frame pump: PR #1159.

## 6. Research: local inference speed and cache correctness

The llama.cpp issue #30961 reports a specific failure mode with unified KV cache, RAM prompt cache and two or more slots: restoring a cached prompt before idle-slot cells are cleared can fail, dropping the cache entry and forcing a full prefill. This is an upstream issue report, not evidence that STAR's current one-slot router is affected.

STAR's current direction should remain conservative:
- preserve the current one-resident-model / one-slot local-router limit until measured otherwise;
- retain conversation isolation from #1204;
- test prompt-cache hit/miss, prefill and decode separately;
- do not increase parallel slots without a targeted cache-restore regression;
- pair every speed experiment with voice/game/OBS guardrails;
- optimize verified task goodput, not tokens/sec alone.

The #1204 draft specifically disables shared cross-slot RAM prompt cache and idle-slot snapshots while preserving ordinary same-slot prefix caching. The #1205 planner is dormant until a backend exposes reliable residency and safe suspend/restore semantics.

Source:
- llama.cpp issue #30961: https://github.com/ggml-org/llama.cpp/issues/30961
- llama.cpp server and benchmark docs: https://github.com/ggml-org/llama.cpp/tree/master/tools/server

## 7. STAR capability scorecard

Do not compress all intelligence into one self-reported number. Keep separate versioned, evidence-backed lanes:

| Domain | Primary metrics |
|---|---|
| General knowledge | accuracy, source grounding, freshness, calibration, contradiction handling |
| Research | claim provenance, source diversity, reproducibility, uncertainty |
| Desktop/computer use | end-state success, checkpoint success, recovery, actions, time |
| Game playing | progress, task completion, control latency, recovery, held-out transfer |
| Game creation | build validity, scene correctness, visual quality, playability, performance |
| Memory | actor attribution, temporal updates, evidence retrieval, abstention, forgetting |
| Skill learning | skill-on uplift, dependent transfer, independent interference, repair rate |
| VTuber conversation | false cutoffs, missed turns, addressee accuracy, appropriateness, silence preservation |
| Voice/avatar | first audible latency, underruns, sync offset, stale/coalesced frame rate |
| Inference | TTFT, first-content, ITL, prefill/decode throughput, queue wait, CPU/RAM/VRAM |
| Whole system | verified tasks per hour under game + voice + avatar + OBS mixed load |

Every score must pin the task roster, benchmark version, agent/model/prompt/tool revisions, environment fingerprint, sample size, evidence source and holdout split. Missing evidence is inconclusive, not a pass.

## 8. Implementation delivered in Run 56

### `star/agent_skills.py`

- Adds optional adjacent `SKILL.contract.json` discovery at skill activation.
- Uses a lazy import of the standard-library-only contract parser, preserving the existing catalog/startup path.
- Requires a regular, non-symlink file contained within the selected skill directory.
- Enforces the existing 64,000-byte file bound.
- Requires the contract's `skill_id` to match the skill directory.
- Returns parsed contract data and canonical SHA-256 when valid.
- Returns `absent` or `invalid` diagnostics without breaking legacy SKILL.md loading.
- Explicitly marks the contract as untrusted reference data, never a permission grant.

### Tests

`tests/test_agent_skill_contracts.py` covers:
- legacy skills without sidecars;
- metadata-only catalog discovery;
- valid sidecar parsing and digest binding;
- malformed JSON;
- mismatched skill identity;
- oversized files;
- symlink rejection.

### Compatibility

- No bundled skill is modified or enabled by this change.
- No default skill list, prompt, model route, scheduler, memory store, tool permission, game controller, voice path, OBS setting or VTube Studio setting is changed.
- No code in a sidecar is executed.
- No skill is automatically promoted.

## 9. Next engineering sequence

1. Run exact-head CI on the updated #1209 branch.
2. Connect trusted host observations to contract behavior constraints; never accept model self-attestation as a verifier.
3. Add signed, replay-protected skill execution receipts using the existing host signing boundary.
4. Add SkillFlow-style matched skill-off/skill-on experiments with dependent transfer and independent interference tasks.
5. Map GameWorld fine-control tasks to STAR's permitted sandbox game controller; keep hidden state evaluator-only.
6. Pin OSWorld 2.1 as a separate optional disposable-VM benchmark campaign; request approval for gated assets or cloud infrastructure.
7. Extend existing memory evaluation with actor/version semantics from EverMemBench and evidence-grounded propose/verify/commit.
8. Finish the private Windows rehearsal across gameplay, voice, avatar, OBS, task ledger and memory.
9. Change no production defaults until paired holdout and mixed-load guardrails pass.

## 10. Limitations

This run implemented optional sidecar discovery and tests. It did not run OSWorld, GameWorld, WindowsWorld, EverMemBench, a live game, a Windows machine, a GPU benchmark, OBS, microphone, VTube Studio, or a public stream. It does not claim a measured intelligence gain, speedup, game mastery, or human-equivalent behavior.

Production `main` remains unchanged. PR #1209 remains draft and requires exact-head CI and owner review.
