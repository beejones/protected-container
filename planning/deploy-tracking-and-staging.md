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

After a swap, Caddy routes change but containers and their volumes do NOT move:
- Production domain → staging containers (with **staging volumes**)
- Staging domain → production containers (with **production volumes**)

This creates two risks:
1. **Data loss**: Production traffic writes to staging's volume. If staging volumes are smaller, ephemeral, or subject to aggressive cleanup, production data could be lost.
2. **Storage-manager cleanup**: If storage-manager cleanup rules are running on the "now demoted" production containers (which still have production volumes), those cleanup algorithms could delete production data.

### Design Constraints

- Volumes are named by stack/compose project. Production stack has `protected-container_*` volumes; staging has `protected-container-staging_*` volumes.
- Storage-manager labels declare cleanup policy per service. After swap, the labels stay with the container — they don't follow the traffic.
- The swap is purely a Caddy routing change. Containers, mounts, and labels are unchanged.

### Required Behavior

1. **Before swap**: The swap script should verify that staging volumes contain a compatible data state (or are empty/disposable). This is the operator's responsibility, but the script should warn.
2. **After swap**: The storage-manager cleanup on the newly-demoted stack (old production containers now receiving staging traffic) should be paused or its retention policy should be extended to avoid premature cleanup.
3. **Volume promotion strategy**: If production data must persist after swap, the recommended approach is:
   - Deploy to staging (new code, fresh volumes or copied data)
   - Verify staging works
   - Swap traffic (zero-downtime)
   - The old production containers (now on staging domain) retain their volumes intact as a rollback safety net
   - Only after confirming the swap is stable, optionally prune old volumes

### Checkable Tasks

- [ ] Add `--swap` pre-flight warning: "After swap, production traffic will use staging container volumes. Ensure staging data state is ready."
- [ ] Add `--swap --confirm` flag to suppress the warning (for automation)
- [ ] Document volume behavior in `docs/deploy/STAGING.md`: which volumes stay where after swap
- [ ] Investigate storage-manager pause mechanism:
  - Option A: Set a `storage-manager.pause=true` label on the demoted stack after swap
  - Option B: Temporarily increase retention on demoted stack via API call
  - Option C: Do nothing — cleanup only runs on labeled volumes and staging volumes are separate from production volumes (simplest if volume names are stack-scoped)
- [ ] Decide whether to support volume migration (copy prod volumes → staging before swap) or document it as an operator responsibility
- [ ] Add deploy message improvements: show target environment and version in "Prepared deployment plan" and "Done" messages

### Resolution Note

If production and staging stacks use **separate Docker volumes** (scoped by compose project name), then after a swap:
- Production data stays in `protected-container_*` volumes attached to prod containers (now receiving staging traffic)
- Staging data stays in `protected-container-staging_*` volumes attached to staging containers (now receiving production traffic)

In this case, storage-manager cleanup is safe because it operates on the volume names it was configured for — not on the traffic the container happens to receive. **No special pause is needed if volumes are stack-scoped.** The key question is whether the staging container has enough data/state to serve production traffic.
