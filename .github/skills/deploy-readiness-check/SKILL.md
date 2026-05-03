---
name: deploy-readiness-check
description: "Use when: validating deploy readiness before running ubuntu_deploy.py or azure_deploy_container.py, checking compose/env-schema/hook prerequisites, or diagnosing preflight deployment failures."
---

# Deploy Readiness Check

## Principles

- A deployment is only ready when the repo contracts and the target prerequisites agree.
- `docker/docker-compose.yml`, env schema, example env files, and deploy docs must tell the same story.
- Prefer the smallest checks that can fail fast before touching remote or cloud state.
- Readiness checks should produce explicit blockers, not vague confidence.

## When to Use

- Before a first Ubuntu or Azure deployment.
- After changing Compose files, deploy scripts, env keys, hooks, or deployment docs.
- When CI or local deploy fails before real rollout begins.
- When validating that a downstream repo still conforms to this toolkit's contracts.

## Procedure

### Step 1 — Determine The Target Surface

Identify which deployment path is being checked:

- local Docker
- Ubuntu server deploy
- Azure Container Instances deploy
- centralized Caddy / shared routing
- storage-manager integration
- env-schema and GitHub Actions sync

Do not run every possible check by default. Focus on the surfaces affected by the change.

### Step 2 — Validate Repo Contracts

Run the smallest relevant local checks first.

Common checks:

```bash
source .venv/bin/activate && python3 scripts/deploy/validate_env.py
source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py --help
source .venv/bin/activate && python scripts/deploy/azure_deploy_container.py --help
docker compose -f docker/docker-compose.yml config
docker compose -f docker/proxy/docker-compose.yml config
docker compose -f docker/storage-manager/docker-compose.yml config
pytest -q tests/pytests/test_<module>.py
```

Contract checks to confirm explicitly:

- Compose roles and service metadata still match the deploy-engine expectations.
- New env keys exist in `scripts/deploy/env_schema.py` and the example env files.
- Docs under `docs/deploy/` match the current commands, paths, and variables.
- Hook extension points are still the customization boundary when behavior was moved out of core scripts.

### Step 3 — Validate Target-Specific Prerequisites

#### Ubuntu

Check only what applies:

- SSH target resolves and connects.
- Remote Docker and Docker Compose are available.
- Shared `caddy` network and central proxy expectations are satisfied.
- If Portainer is part of the flow, verify whether it is initialized and reachable.

#### Azure

Check only what applies:

- Required Azure deploy keys are present.
- Authentication context and registry requirements are satisfied.
- The compose-driven deploy shape still fits ACI constraints.

#### Shared routing / storage-manager

Check only what applies:

- `PUBLIC_DOMAIN`, `WEB_PORT`, and upstream service naming are aligned.
- Storage-manager labels are complete and consistent with documented algorithms.

### Step 4 — Summarize Readiness

Produce a short summary with:

- checks run
- confirmed-ready surfaces
- blockers found
- exact next action needed to clear each blocker

## Exit Criteria

- All relevant local contract checks passed.
- Target-specific blockers are either cleared or explicitly documented.
- The user has a concrete readiness summary rather than a generic "looks fine" assessment.