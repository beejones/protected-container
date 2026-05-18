# Deploy Tracking CSV & Staging Environment

## Principles

- **Deploy history is observable**: Every successful deploy appends a row to a CSV log so operators can trace exactly what was deployed and when.
- **Git commit is the rollback anchor**: The CSV records the **full 40-char commit SHA** (`git rev-parse HEAD`) so you can always `git checkout <sha>` to reproduce exactly what was deployed.
- **Version lives in `.env` as `APP_VERSION`**: Format `x.y.z` (semver). The deploy script reads it, logs it to the CSV, and optionally auto-increments the patch (`z`) after a successful production deploy. Staging deploys log the version but do NOT auto-increment.
- **CSV columns and their purpose**:
  | Column | Value | Why |
  |--------|-------|-----|
  | `timestamp` | ISO 8601 UTC (`2026-05-18T14:30:00Z`) | When the deploy happened |
  | `git_ref` | Full SHA (`a1b2c3d4e5f6...`) | Exact code state — use for rollback checkout |
  | `version` | `1.2.3` from `.env` `APP_VERSION` | Human-readable release label |
  | `target` | `production` / `staging` / `swap` | Which environment was affected |
  | `stack_name` | Portainer stack name | Which stack was deployed |
  | `domain` | Public domain for this deploy | Which URL serves this release |
  | `image` | `ghcr.io/.../...:latest` | Exact container image deployed |
  | `status` | `success` / `failed` | Outcome | 
- **Staging mirrors production contract**: Staging uses the same Compose files, hooks, and deploy script as production — only the target parameters differ (domain, remote dir, stack name).
- **Portainer manages both stacks**: Staging is a second Portainer stack on the same host (e.g. `protected-container-staging`). Portainer UI shows both stacks side-by-side. The deploy script creates/updates the staging stack via the same Portainer API path — just with different `PORTAINER_STACK_NAME` and `UBUNTU_REMOTE_DIR`. You can also inspect, restart, or roll back individual stacks directly from the Portainer web UI.
- **Swap is a traffic operation, not a re-deploy**: Switching between staging and production is a Caddy routing change, not a container rebuild.
- **No hardcoded staging logic in core scripts**: Staging is expressed through env profiles and a lightweight swap utility, not a parallel deploy code path.
- **Default deploy target is staging**: Running `ubuntu_deploy.py` without flags deploys to **staging**. To deploy directly to production, pass `--prod`. This prevents accidental production deploys.
- **Swap is `ubuntu_deploy.py --swap`** (Caddy routing operation, not Portainer):
  1. Run `python scripts/deploy/ubuntu_deploy.py --swap`
  2. Script SSHs into the host, verifies both stacks are healthy via `docker ps`
  3. Rewrites the Caddyfile: production domain → staging container upstream, staging domain → production container upstream
  4. Reloads Caddy (`docker exec central-proxy caddy reload`)
  5. Logs a `swap` event to the deploy CSV
  
  **Why not Portainer for the swap?** Portainer manages container lifecycle, but traffic routing lives in Caddy. Swapping in Portainer would mean redeploying both stacks with different domains — slower, riskier, causes downtime. The Caddy rewrite is instant and zero-downtime.
  
  **Rollback**: Run the swap script again — it's symmetric. Or manually edit the Caddyfile via SSH if something goes wrong.
- **Existing deploy contracts preserved**: ubuntu_deploy.py remains the single entry point; staging vs production is a parameter concern.

---

## Affected Surfaces

- `scripts/deploy/ubuntu_deploy.py` — post-deploy CSV logging
- `scripts/deploy/` — new `deploy_log.py` helper (CSV append logic) + new `swap_environment.py` utility
- `scripts/deploy/env_schema.py` — new optional deploy keys for staging
- `env.deploy.example` — staging key examples
- `docs/deploy/` — new `STAGING.md` documenting the staging workflow and swap mechanism
- Local Docker: no impact (staging is an ubuntu-deploy concern)
- Azure deploy: no impact initially (can be extended later)
- Hooks: `post_deploy` hook already exists; CSV logging fires after it
- `docs/deploy/STAGING.md` — **primary reference for downstream/relying projects**: explains how to configure staging, deploy to it, swap traffic, and read the deploy CSV. Written for operators who clone this toolkit into their own project.
---

## Checkable Task Overview

### Phase 0 — Cleanup
- [x] Audit `scripts/deploy/ubuntu_deploy.py` for dead code, unused imports, or stale references relevant to the touched surface
- [x] Audit `scripts/deploy/env_schema.py` for commented-out keys or stale patterns
- [x] Remove any dead code found
- [x] Verify existing tests pass after cleanup (`pytest -q`)

### Phase 1 — Deploy Tracking CSV (`out/deploy/deploy_log.csv`)
- [x] Add `APP_VERSION=0.1.0` to `.env` (runtime config, read at deploy time)
- [x] Add `APP_VERSION` to `env_schema.py` RUNTIME_SCHEMA (optional, default `0.0.0`)
- [x] Create `scripts/deploy/deploy_log.py` with:
  - `append_deploy_record(repo_root, git_ref, version, target, stack_name, domain, image, status)` → appends a row
  - CSV columns: `timestamp,git_ref,version,target,stack_name,domain,image,status`
  - Auto-creates `out/deploy/` directory if missing
  - `git_ref` = full 40-char SHA from `git rev-parse HEAD`
  - `version` = read from `.env` key `APP_VERSION`
  - After successful **production** deploy: auto-increment patch in `.env` (`1.2.3` → `1.2.4`) so next deploy gets a new version
  - Staging deploys: log current version but do NOT increment
- [x] Integrate `append_deploy_record` call at end of `ubuntu_deploy.py` main() after `"✅ Done"` message
- [x] Add `out/deploy/` to `.gitignore` (tracking CSV is local state, not committed)
- [x] Write unit tests for `deploy_log.py` (CSV creation, append, column integrity, version increment)

### Phase 2 — Staging Environment Support
- [x] Add optional env keys to `env_schema.py`:
  - `STAGING_PUBLIC_DOMAIN` — staging domain
  - `STAGING_REMOTE_DIR` — staging remote directory
  - `STAGING_PORTAINER_STACK_NAME` — staging stack name
- [x] Change `ubuntu_deploy.py` default behavior:
  - **Default (no flag)**: deploy to staging (uses `STAGING_*` env keys)
  - **`--prod` flag**: deploy to production (uses existing `PUBLIC_DOMAIN`, `UBUNTU_REMOTE_DIR`, `PORTAINER_STACK_NAME`)
  - **`--swap` flag**: swap Caddy routing between staging and production (no deploy, just traffic switch)
  - Mutually exclusive: `--prod` and `--swap` cannot be combined
- [x] Update `env.deploy.example` with commented staging examples
- [x] Include target (`staging` / `production`) in the CSV log `target` column

### Phase 3 — Swap via `--swap` Flag
- [x] Implement `--swap` handler in `ubuntu_deploy.py`:
  - SSHs into host, checks both prod and staging containers are healthy (`docker ps`)
  - Reads current Caddy upstream mappings for both domains
  - Rewrites Caddyfile: production domain → staging container, staging domain → production container
  - Reloads Caddy (`docker exec central-proxy caddy reload`)
  - Appends a `swap` event to the deploy CSV
  - Fails clearly if either stack is unhealthy
- [x] Extract swap logic into a helper function (testable without CLI)
- [x] Write integration tests for swap logic (mock SSH + Caddy register calls)

### Phase 4 — Documentation
- [x] Create `docs/deploy/STAGING.md`:
  - Architecture overview (same host, two stacks, shared Caddy)
  - Environment setup (which env keys to set)
  - Deploy to staging workflow
  - Swap production ↔ staging workflow
  - Rollback (swap back)
- [x] Update `docs/deploy/UBUNTU_SERVER.md` with a cross-reference to staging docs
- [x] Update `env.deploy.example` header comment to mention staging keys

### Phase 5 — Validation
- [x] All new and existing tests pass (`pytest`)
- [x] `ubuntu_deploy.py --help` shows `--prod` and `--swap` flags
- [x] `ubuntu_deploy.py --swap --prod` errors with mutual exclusion message
- [x] `validate_env.py` passes with and without staging keys set
- [x] CSV file is created correctly after a dry-run or mocked deploy

---

## Phase Exit Criteria

| Phase | Exit Criteria |
|-------|--------------|
| 0 | No dead code in touched modules; tests green |
| 1 | CSV helper works standalone; integrated into deploy; tests green |
| 2 | `--deploy-env staging` resolves staging overrides correctly; schema valid; tests green |
| 3 | Swap utility rewrites Caddy config; health check guards swap; tests green |
| 4 | Docs exist, commands match code, cross-references valid |
| 5 | Full test suite passes; CLI help correct; end-to-end CSV verified |

---

## Design Notes

### CSV Format

```csv
timestamp,git_ref,version,target,stack_name,domain,image,status
2026-05-18T14:30:00Z,a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2,1.2.3,production,protected-container,protected-container.zenia.eu,ghcr.io/beejones/protected-container:latest,success
2026-05-18T15:00:00Z,a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2,1.2.3,staging,protected-container-staging,staging.zenia.eu,ghcr.io/beejones/protected-container:latest,success
2026-05-18T15:05:00Z,a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2,1.2.3,swap,protected-container,protected-container.zenia.eu,,success
```

**Reading the CSV for rollback**: Find the last `production` + `success` row, use `git_ref` to checkout that exact commit, redeploy.

### Staging Architecture

```
┌────────────────────────────────────────────────────────┐
│  Ubuntu Host                                           │
│                                                        │
│  ┌──────────────┐                                      │
│  │ Central Caddy │──► production.domain → prod stack   │
│  │  (ports 80,  │──► staging.domain    → staging stack │
│  │   443)       │                                      │
│  └──────────────┘                                      │
│                                                        │
│  ┌─────────────────────┐  ┌──────────────────────────┐ │
│  │ protected-container │  │ protected-container-stg  │ │
│  │ (production stack)  │  │ (staging stack)          │ │
│  │ remote_dir: /home/  │  │ remote_dir: /home/       │ │
│  │  .../protected-     │  │  .../protected-          │ │
│  │  container          │  │  container-staging       │ │
│  └─────────────────────┘  └──────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

### Swap Mechanism

1. Verify both stacks are healthy (containers running)
2. Read current Caddy upstream mappings
3. Rewrite: `production.domain` → staging container, `staging.domain` → production container
4. Reload Caddy
5. Log swap event to CSV

This is a **zero-downtime traffic swap** — no containers are restarted. Rollback = swap again.

---

## Follow-up: Volume Safety During Swap (Phase 6)

### Problem

After a Caddy-only swap, containers and their volumes do NOT move. This means the staging container has different (potentially empty) volumes from production. We need staging to use production data so it can be validated with real state.

### Revised Design: Shared Volumes + Container Start/Stop

Instead of two independent stacks with separate volumes, staging and production share the same volumes. Only one stack is running at a time. The swap is a **container lifecycle operation** (stop one, start the other) combined with a Caddy routing change.

**How it works:**

1. **Default deploy (staging)**: Deploy the staging stack to the same remote dir, referencing the **production volumes**. Do NOT start the staging containers. This allows the staging image/code to be ready without serving traffic or touching data.

2. **`--prod`**: Start the production containers (if not already running). If the staging containers are running, stop them first. Production serves traffic on the production domain.

3. **`--swap`**: Stop the production containers, start the staging containers (which use the same volumes), then swap Caddy routing so the production domain points to the staging containers. The staging containers now serve production traffic with production data.

### Architecture After Swap

```
Before swap:
  prod domain  → prod containers (running, prod volumes)
  staging containers (stopped, same prod volumes)

After swap:
  prod domain  → staging containers (running, prod volumes)  
  prod containers (stopped, same prod volumes)
```

### Key Differences From Previous Design

| Aspect | Previous (separate volumes) | New (shared volumes) |
|--------|---------------------------|---------------------|
| Volumes | Stack-scoped, separate | Shared — staging uses prod volumes |
| Staging state | Independent data | Real production data |
| Swap | Caddy-only routing | Stop prod + start staging + Caddy swap |
| Rollback | Swap again (instant) | Stop staging + start prod + Caddy swap |
| Risk during swap | Brief downtime during container stop/start | Same |
| Storage-manager | No concern (separate volumes) | Only one set of containers runs cleanup |

### Checkable Tasks

- [x] Modify staging deploy to mount production volumes (same volume names in compose)
- [x] Staging deploy should NOT start containers (`docker compose up --no-start` or equivalent via Portainer)
- [x] `--prod` should start prod containers and stop staging containers if running
- [x] `--swap` should:
  1. Stop production containers
  2. Start staging containers (same volumes)
  3. Swap Caddy routing (production domain → staging containers)
  4. Log swap event to CSV
- [x] Rollback (`--swap` again) reverses: stop staging, start prod, swap Caddy back
- [x] Storage-manager only runs on the active stack — no cleanup conflict
- [x] Update `docs/deploy/STAGING.md` with the shared-volume model
- [x] Add deploy message: show which containers are being stopped/started
- [x] Tests for stop/start lifecycle logic
