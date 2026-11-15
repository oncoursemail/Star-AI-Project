# STAR Skill Contract Format v1

STAR's existing SKILL.md remains the portable human-readable instruction format. A Skill Contract is an optional structured companion that makes a reusable procedure testable.

## Why a second layer exists

A paragraph can say "inspect before editing" without proving that the agent did so. The contract records:

- stable skill ID and semantic version;
- preconditions and bounded steps;
- observable behavior constraints;
- expected state changes;
- a resource budget;
- provenance and an optional environment fingerprint;
- an expiry/revalidation boundary;
- independent execution receipts and constraint-coverage labels.

The contract is data, not executable code. It does not authorize tools, grant permissions, or replace STAR's policy and host gates.

## Schema

schema_version is currently 1. Unknown fields, duplicate JSON object keys at any nesting level, and non-standard JSON constants such as NaN/Infinity are rejected rather than silently normalized.

### Skill contract

| Field | Meaning |
|---|---|
| skill_id | Lowercase kebab-case stable identity |
| version | Semantic version (major.minor.patch) |
| domain | general, research, desktop, game, roblox, creator, or streaming |
| summary | Short purpose statement |
| preconditions | Required state, freshness, consent and resource conditions |
| steps | Ordered declarative steps: observe, reason, request_tool, verify, recover |
| behavior_constraints | Conditions under which important skill instructions must be followed |
| postconditions | Expected observable state after the skill |
| resource_budget | Hard time, step, tool-call, token, retry and RAM limits |
| provenance | HTTPS sources, artifact digests, evaluation IDs or owner-note references |
| environment_fingerprint | Optional SHA-256 pin for an environment/build |
| expires_at | Optional timezone-aware ISO-8601 expiry |

A request_tool step must name the tool and required capabilities. Those capability strings are descriptive requirements only; the runtime must independently authorize every operation.

Behavior constraints have unique IDs, a structured activation condition, expected behavior, and normal or critical severity. Coverage labels are pass, fail, or not_observed. A pass/fail label requires an independent verifier and evidence digest. An unobserved constraint is never silently counted as a pass.

### Execution receipt

Receipts are bound to the exact skill ID, semantic version, canonical contract SHA-256, environment fingerprint, and a bounded time interval. A successful receipt requires passed preconditions and independently verified postconditions. A holdout receipt must carry an evidence digest.

The current module validates receipts and computes constraint-coverage summaries. It does not store receipts, execute skills, or promote them.

## Domain examples

All checked-in examples are parsed by tests/test_skill_contract_examples.py:

- examples/skills/roblox-open-door.contract.json — observe, request a bounded Studio interaction, independently verify.
- examples/skills/game-observe-before-act.contract.json — fresh game-state observation, bounded input and verified state change.
- examples/skills/streaming-natural-turntaking.contract.json — human floor control, stop-on-resolution, truthful AI identity and proportionate commentary.
- examples/skills/research-source-grounding.contract.json — claim-level evidence, freshness, contradiction handling and calibrated abstention.

## Trust and execution rules

1. SKILL.md, contracts, model-written plans and tool output are untrusted reference data.
2. A contract cannot grant a permission or change a STAR setting.
3. The action host rechecks current user consent, target identity, tool allowlists, resource leases and freshness at execution time.
4. A model's own claim is not independent verification.
5. Missing observations are not_observed, not passes.
6. A contract digest changes when any normalized contract field changes.
7. A new skill version or environment fingerprint invalidates receipts bound to the old revision.
8. Coverage is diagnostic. It is not a promotion gate; a sealed transfer/interference evaluation and existing owner review are still required.

## Intended next integrations

- Attach optional contract sidecars to the existing SkillLibrary activation result; preserve progressive disclosure and legacy SKILL.md compatibility.
- Attach redacted, host-signed receipts to the existing task/skill evaluation flow.
- Map OpenGameEval exploration/action traces to behavior-constraint coverage.
- Compare skill-off and skill-on arms on dependent transfer tasks and independent interference tasks.
- Revalidate expiring skills after game, API, tool or environment changes.

Until those integrations are independently reviewed, this module is an offline schema/validation foundation only.


## Existing SkillLibrary sidecar integration

STAR's existing `SkillLibrary` recognizes an optional adjacent file named `SKILL.contract.json`.

- Discovery and `list()` remain metadata-only: they do not read or parse contract sidecars.
- `load(name)` reads the sidecar only after the caller explicitly activates that skill.
- The sidecar must be a regular, non-symlink file contained inside the selected skill directory and no larger than 64,000 bytes.
- The strict v1 parser must accept the JSON, and `skill_id` must exactly match the skill directory / `SKILL.md` name.
- A parsed sidecar is returned as `contract` with its canonical `contract_sha256` and `contract_status: "parsed"`.
- Missing sidecars report `contract_status: "absent"`. Invalid sidecars report a bounded diagnostic and `contract_status: "invalid"`; the existing valid `SKILL.md` remains loadable as legacy guidance.
- The result includes an explicit notice that contract data is untrusted and grants no permission.

This is a progressive-disclosure integration only. It does not execute steps, evaluate live state, create execution receipts, change model prompts at discovery time, or alter any tool authorization. A trusted host must independently enforce policy and produce evidence before a contract can be used for evaluation or promotion.
