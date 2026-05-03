# Agent App Specific Instructions

## 1. Product Boundary

- This repository is a deployment toolkit first. Its core business logic is how application payloads are packaged, configured, routed, and deployed across local Docker, Ubuntu servers, and Azure.
- `code-server` is the default example payload, not a hardcoded product requirement. Core deploy logic must stay reusable for downstream repos that swap in a different app.
- When changing behavior, prefer strengthening shared deployment contracts over adding repo-specific special cases.

## 2. Docker Compose Is The Source Of Truth

- `docker/docker-compose.yml` and its target-specific overrides define the canonical service shape. Deployment code should derive behavior from Compose, not from duplicated constants.
- Service roles must be inferred from Compose metadata such as `x-deploy-role`, not from hardcoded service names, ports, or legacy assumptions like `CODE_SERVER_PORT`.
- Commands, ports, images, networks, and labels should be read from Compose or adjusted through hooks. Duplicating them in deploy scripts creates parity bugs.
- Local-development bind mounts may exist in Compose, but deploy targets may normalize or ignore unsupported mounts. The deploy engine should translate Compose intent to the target platform rather than pretending all local mounts are portable.

## 3. Runtime Config And Deploy Config Are Separate Domains

- Runtime application config belongs in `.env` and `.env.secrets`.
- Deployment-time infrastructure config belongs in `.env.deploy` and `.env.deploy.secrets`.
- The schema in `scripts/deploy/env_schema.py` is authoritative. Unknown keys, implicit aliases, and silent compatibility shims are configuration bugs.
- When adding a variable or secret, update the schema, the example env files, the docs, and tests together.
- Secrets must stay out of Git history and out of logs. Prefer Key Vault, GitHub Actions secrets, or ignored dotenv secret files.

## 4. Shared Ingress Architecture

- On Ubuntu, the centralized Caddy proxy is the only public ingress and the only service that should bind host ports `80` and `443`.
- Application stacks should join the external `caddy` network and should not publish their own public host ports for normal web traffic.
- Domain routing is a first-class contract. `PUBLIC_DOMAIN`, `WEB_PORT`, and the upstream service/container name must stay aligned so Caddy registration remains deterministic.
- Caddy registration should be automated and idempotent. Manual Caddyfile edits are a debugging fallback, not the normal workflow.

## 5. Portainer Is A Control Plane, Not The Truth Source

- Portainer can orchestrate Ubuntu deployments, but it must not become the authoritative definition of the stack.
- The repo-owned Compose files and env files remain the source of truth for what gets deployed.
- If Portainer is missing, stale, or uninitialized, deployment logic should fail clearly or use a controlled fallback. It should not invent a second deployment model with different behavior.

## 6. Hooks Are The Customization Boundary

- Repo-specific deployment behavior belongs in deployment hooks, not in hardcoded forks of the core deploy scripts.
- `build_deploy_plan` is the preferred place to override images, commands, resources, and storage-registration behavior.
- Hook-based customization should preserve upstream compatibility: extend the plan, do not bypass the shared contracts unless the target platform truly requires it.

## 7. Storage Manager Rules Live In Compose Labels

- Volume cleanup policy is declared by `storage-manager.<n>.*` Compose labels on the owning service.
- Registration data should be derived from those labels, not duplicated in Python constants or out-of-band manual steps.
- If `STORAGE_MANAGER_API_URL` is configured, Ubuntu deploy should register labels through the API. If the storage-manager service is in the same stack, same-stack discovery can be used as the default path.
- Cleanup algorithms and their parameters must stay explicit in labels and API payloads. Hidden cleanup behavior is a business-logic bug.

## 8. Security And Auth Boundaries

- External TLS termination and edge authentication belong at the proxy layer.
- Runtime containers should assume they are behind the configured ingress architecture instead of reimplementing overlapping edge concerns unless the docs explicitly require a second auth layer.
- Azure runtime secret delivery should use Managed Identity plus Key Vault. Ubuntu runtime secret delivery should use synced env files mounted into the container runtime path.

## 9. Cross-Target Parity Matters

- Local Docker, Ubuntu deploy, and Azure deploy are different execution environments but should honor the same Compose-driven service intent wherever possible.
- A change that only works in one deploy path because it hardcodes target-specific assumptions is usually a regression.
- When a target has platform constraints, keep the constraint handling isolated in the renderer or deploy adapter and preserve the shared business contract above it.

## 10. Change Discipline

- When changing deployment logic, update the nearest docs in `docs/` and the relevant planning assumptions if they are no longer true.
- Validate behavior with focused tests whenever the change affects Compose parsing, env resolution, hooks, routing, or deployment orchestration.
- Delete obsolete deployment paths and stale assumptions quickly. This project depends on a small set of explicit contracts staying coherent.
