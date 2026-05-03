---
name: deploy-rollout-adoption
description: "Use when: rolling out a validated deployment-contract change across code, docs, env examples, workflows, and template surfaces, or deciding whether a new deploy behavior should replace the old default."
---

# Deploy Rollout / Adoption

## Principles

- A deployment change is not adopted until code, docs, examples, and workflows all reflect the new contract.
- Defaults should be explicit. If behavior changed, either remove the old path or document the compatibility boundary clearly.
- Example files must be updated with structure, names, and comments only; never with real secrets.
- Rollout should reduce ambiguity, not leave multiple contradictory deploy stories behind.

## When to Use

- After validating a new deploy behavior that should become the repo default.
- When changing env keys, Compose roles, deploy scripts, hook contracts, routing conventions, or template guidance.
- When replacing a legacy path with a compose-driven or hook-driven path.
- When a downstream-facing doc or example still describes superseded behavior.

## Procedure

### Step 1 — Decide The Adoption Boundary

Make the decision explicit:

- What behavior is now the default?
- What older behavior remains supported, if any?
- What should be deprecated or deleted?
- What migration note does a downstream user need?

Do not start editing until that boundary is clear.

### Step 2 — Update All External Contract Surfaces

Touch the relevant outward-facing surfaces together:

- `README.md`
- `docs/deploy/`
- `env.example`
- `env.deploy.example`
- `env.secrets.example`
- `env.deploy.secrets.example`
- `.github/workflows/`
- `planning/` files that still describe the old behavior
- `AGENT_APP_SPECIFIC.md` when the project principles changed

If the change affects deploy customization, make sure hooks and their docs still describe the intended extension point.

### Step 3 — Remove Or Isolate Obsolete Paths

- Delete truly obsolete commands, docs sections, examples, and compatibility shims.
- If a fallback must remain, document when it is used and why.
- Avoid leaving duplicate instructions that drift apart over time.

### Step 4 — Validate The New Story

Run the smallest set of checks that proves the adopted contract is coherent.

Common validations:

```bash
source .venv/bin/activate && python3 scripts/deploy/validate_env.py
source .venv/bin/activate && pytest -q tests/pytests/test_<module>.py
source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py --help
source .venv/bin/activate && python scripts/deploy/azure_deploy_container.py --help
docker compose -f docker/docker-compose.yml config
```

Validate explicitly that:

- docs commands exist and still make sense
- example env keys are legal under the schema
- workflow steps call current scripts
- template guidance matches the current repo contract

### Step 5 — Write The Adoption Summary

Record:

- what became the default
- what was removed or deprecated
- which docs/examples/workflows changed
- any remaining migration risk or manual follow-up

## Exit Criteria

- The new deployment behavior is reflected consistently across code, docs, examples, and workflows.
- Obsolete or conflicting guidance has been removed or clearly isolated.
- Validation confirms the adopted contract is coherent.