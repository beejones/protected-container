# Agent App specific Instructions

This file adds repo-specific rules on top of AGENT.md. This repository is a deployment toolkit for running a protected container payload, not an application business-logic repo. The current default payload is code-server, with deployment flows for Ubuntu servers and Azure Container Instances.

## 1. Project Shape

- Treat this repository as infrastructure-first. Most changes belong in `docker/`, `scripts/deploy/`, `docs/deploy/`, and `planning/`.
- The current local/default app shape is the `app` service in `docker/docker-compose.yml`. It runs code-server, mounts `../workspace` at `/home/coder/workspace`, mounts the repo runtime env read-only, and persists logs in the `logs` volume.
- On Ubuntu, the app is expected to sit behind the centralized Caddy proxy on the external `caddy` Docker network. Do not add direct host-port publishing for the app service unless the task explicitly changes the deployment architecture.
- When a task is about adding a different payload, preserve the protected-container deployment model unless the task or a planning file explicitly says to replace it.

## 2. Hardcoding

- Do not hardcode env key strings in deploy scripts. Add keys to `scripts/deploy/env_schema.py` and reference `VarsEnum` or `SecretsEnum`. `tests/pytests/test_no_raw_env_keys.py` protects this rule.
- Do not hardcode service names, roles, commands, ports, or image behavior in Azure deploy logic when Compose metadata or hooks should define them.
- Use Docker Compose as the source of truth for deploy shape. Prefer `x-deploy-role`, compose `command`, compose ports, and compose environment over repo-specific assumptions baked into deploy scripts.
- Avoid fallback aliases for config keys. Unknown or legacy keys should fail fast rather than being silently translated.

## 3. Docker Compose Contract

- Keep `docker/docker-compose.yml` and deploy logic aligned. If you change compose roles, commands, ports, or environment, update the helpers and tests that depend on that contract.
- Compose role detection should go through `scripts/deploy/docker_compose_helpers.py`, not ad-hoc parsing.
- If a service is meant to be deployed by Azure tooling, it should be discoverable by `x-deploy-role`.
- Compose string commands should remain deployable as normalized shell commands; list commands should stay list commands.
- Do not assume local bind mounts can be reproduced in Azure. The docs and plans explicitly treat many bind mounts as local-dev only.

## 4. Env and Secret Boundaries

- Keep the split between runtime config and deploy-time config:
	- `.env` and `.env.secrets` are runtime inputs.
	- `.env.deploy` and `.env.deploy.secrets` are deploy-time inputs.
- The schema in `scripts/deploy/env_schema.py` is the single source of truth for allowed keys, defaults, targets, and required values.
- Unknown keys should fail validation. Empty values should be treated as missing when validation cares about presence.
- GitHub Actions sync must follow schema targets instead of heuristics.
- If you add a new key, update the schema, the relevant example env files, and the corresponding docs in `docs/deploy/ENV_SCHEMA.md`.

## 5. Deploy Hooks Boundary

- Prefer the hook layer for deployment customization instead of forking core deploy logic. The supported customization surface is `scripts/deploy/deploy_hooks.py` plus an optional `scripts/deploy/deploy_customizations.py`.
- Respect the hook loader contract:
	- explicit `--hooks-module` or `DEPLOY_HOOKS_MODULE` import failures are hard errors;
	- the default hooks file is optional, but if it exists and is broken, that is still a hard error;
	- soft-fail is opt-in through `--hooks-soft-fail` or `DEPLOY_HOOKS_SOFT_FAIL=true`.
- Preferred customization points are `pre_validate_env`, `post_validate_env`, `build_deploy_plan`, and `post_render_yaml`. Do not introduce one-off customization paths when an existing hook point is sufficient.

## 6. Ubuntu Deployment Rules

- `scripts/deploy/ubuntu_deploy.py` is the canonical remote deploy path for self-hosted Ubuntu servers.
- The Ubuntu model assumes one centralized Caddy proxy owning ports `80` and `443`. App stacks should join the external `caddy` network and let Caddy route by domain.
- `ubuntu_deploy.py` is also responsible for automatic Caddy registration and Portainer-oriented stack deployment. Preserve that automation rather than replacing it with manual server steps in code.
- If a web-facing service is deployed on Ubuntu, keep `container_name`, `PUBLIC_DOMAIN`, and the internal web port coherent with the shared-routing docs.

## 7. Storage Manager Integration

- Storage cleanup is a first-class feature of this repo. Do not treat `docker/storage-manager/` as sample code.
- For Ubuntu-hosted apps that produce persistent data, prefer storage-manager registration through compose labels or the registration API instead of app-specific cleanup logic.
- Label format is indexed as `storage-manager.<n>.*` and should remain stable.
- If deployment code touches storage-manager registration, keep `scripts/deploy/ubuntu_deploy.py`, `docs/deploy/STORAGE_MANAGER.md`, and related tests aligned.

## 8. Planning and Docs

- Treat `planning/` as the design direction for refactors that are in flight, especially the compose-driven Azure deploy rewrite, env-schema hardening, deploy customization hooks, and storage-manager roadmap.
- Treat `docs/deploy/*.md` as the operator-facing contract. If code changes behavior, update the matching doc in the same change.
- When changing deploy behavior, check whether the change affects all of these surfaces together:
	- compose helpers and deploy scripts
	- env examples and schema docs
	- tests under `tests/pytests/`
	- the relevant planning file if the implementation meaningfully advances or changes a planned phase

## 9. Verification Bias

- Prefer narrow tests that protect this repo's deployment invariants, especially:
	- env schema tests
	- no-raw-env-key tests
	- compose detection tests
	- deploy hooks integration tests
- When you change deployment contracts, update or add tests before widening scope.

