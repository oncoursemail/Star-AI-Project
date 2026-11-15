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

schema_version is currently 1. Unknown fields are rejected rather than silently ignored.

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

## Example

See examples/skills/roblox-open-door.contract.json.

The example deliberately separates observing the target, requesting a named capability-labelled tool, and independently verifying the resulting state.

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

- Add optional contract discovery beside star/agent_skills.py, preserving progressive disclosure and existing SKILL.md compatibility.
- Attach redacted, host-signed receipts to the existing task/skill evaluation flow.
- Map OpenGameEval exploration/action traces to behavior-constraint coverage.
- Compare skill-off and skill-on arms on dependent transfer tasks and independent interference tasks.
- Revalidate expiring skills after game, API, tool or environment changes.

Until those integrations are independently reviewed, this module is an offline schema/validation foundation only.
