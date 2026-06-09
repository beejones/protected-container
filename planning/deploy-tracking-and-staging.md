# Version Log CSV & Staging Environment

## Principles

- **Deploy history is observable**: Every successful deploy writes a row to a CSV log so operators can trace exactly what was deployed and when. The newest row appears directly below the header.
- **Git commit is the rollback anchor**: The CSV records the **full 40-char commit SHA** (`git rev-parse HEAD`) so you can always `git checkout <sha>` to reproduce exactly what was deployed.
- **Version lives in `.env` as `APP_VERSION`**: Format `x.y.z` (semver). `/changelog` bumps it for main-bound merges and writes the matching `CHANGELOG.md` entry. The deploy script reads that prepared version, logs it to the CSV for the first successful deploy record of a new git ref, and requires the matching changelog entry. Later staging, production, or swap records for the same git ref reuse the logged version.
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
- **Swap is a production promotion operation**: `--swap` promotes the staged build into the production stack, keeps `PUBLIC_DOMAIN` routed to production, and stops staging afterward.
- **No hardcoded downstream logic in core scripts**: Staging is expressed through env profiles and existing Portainer/Caddy contracts, not downstream-specific branching.
- **Default deploy target is staging**: Running `ubuntu_deploy.py` without flags deploys to **staging**. To deploy directly to production, pass `--prod`. This prevents accidental production deploys.
- **Swap is `ubuntu_deploy.py --swap`** (production promotion through Portainer):
  1. Run `python scripts/deploy/ubuntu_deploy.py --swap`
  2. Script verifies the staging Portainer stack exists as the staged candidate
  3. Updates/starts the production Portainer stack from the Compose/image contract
  4. Stops staging containers via Portainer API
  5. Keeps Caddy routing on `PUBLIC_DOMAIN` → production stack
  6. Logs a `swap` event to the version CSV, reusing the staged version when staging already recorded the same git ref

  **Why not route production to staging?** Staging must remain stopped after deploy and after swap. Promoting into production preserves the stable public route while keeping staging as a stopped predeploy candidate.

  **Rollback**: Use the deploy-log `git_ref`, checkout that commit, and redeploy production.
- **Existing deploy contracts preserved**: ubuntu_deploy.py remains the single entry point; staging vs production is a parameter concern.

---

## Affected Surfaces

- `scripts/deploy/ubuntu_deploy.py` — post-deploy CSV logging
- `scripts/deploy/` — `deploy_log.py` helper (newest-first CSV write logic)
- `scripts/deploy/env_schema.py` — new optional deploy keys for staging
- `env.deploy.example` — staging key examples
- `docs/deploy/` — new `STAGING.md` documenting the staging workflow and swap mechanism
- Local Docker: no impact (staging is an ubuntu-deploy concern)
- Azure deploy: no impact initially (can be extended later)
- Hooks: `post_deploy` hook already exists; CSV logging fires after it
- `docs/deploy/STAGING.md` — **primary reference for downstream/relying projects**: explains how to configure staging, deploy to it, promote staging to production, and read the deploy CSV. Written for operators who clone this toolkit into their own project.
---

## Checkable Task Overview

### Phase 0 — Cleanup
- [x] Audit `scripts/deploy/ubuntu_deploy.py` for dead code, unused imports, or stale references relevant to the touched surface
- [x] Audit `scripts/deploy/env_schema.py` for commented-out keys or stale patterns
- [x] Remove any dead code found
- [x] Verify existing tests pass after cleanup (`pytest -q`)

### Phase 1 — Version Log CSV (`out/deploy/version_log.csv`)
- [x] Add `APP_VERSION=0.1.0` to `.env` (runtime config, read at deploy time)
- [x] Add `APP_VERSION` to `env_schema.py` RUNTIME_SCHEMA (optional, default `0.0.0`)
- [x] Create `scripts/deploy/deploy_log.py` with:
  - `append_deploy_record(...)` / `append_deploy_record_with_settings(...)` → writes newest row below the header
  - CSV columns: `timestamp,git_ref,local_branch,version,target,stack_name,domain,image,status`
  - Auto-creates `out/deploy/` directory if missing
  - `git_ref` = full 40-char SHA from `git rev-parse HEAD`
  - `local_branch` = checked-out deploy branch, with legacy rows backfilled as `main`
  - `version` = read from `.env` key `APP_VERSION`
  - After the first successful deploy record for a new git ref: record the current `.env` `APP_VERSION` so each git ref gets one release version, but only if `CHANGELOG.md` already has the matching version entry from `/changelog`
  - Repeated staging, production, and swap deploys for the same git ref: log current version but do NOT increment
- [x] Integrate `append_deploy_record` call at end of `ubuntu_deploy.py` main()
- [x] Add `out/deploy/` to `.gitignore` (tracking CSV is local state, not committed)
- [x] Write unit tests for `deploy_log.py` (CSV creation, newest-first ordering, column integrity, version increment)

### Phase 2 — Staging Environment Support
- [x] Add optional env keys to `env_schema.py`:
  - `STAGING_PUBLIC_DOMAIN` — staging domain
  - `STAGING_REMOTE_DIR` — staging remote directory
  - `STAGING_PORTAINER_STACK_NAME` — staging stack name
- [x] Change `ubuntu_deploy.py` default behavior:
  - **Default (no flag)**: deploy to staging (uses `STAGING_*` env keys)
  - **`--prod` flag**: deploy to production (uses existing `PUBLIC_DOMAIN`, `UBUNTU_REMOTE_DIR`, `PORTAINER_STACK_NAME`)
  - **`--swap` flag**: promote the staged build into the production stack, keep `PUBLIC_DOMAIN` routed to production, then stop staging
  - Mutually exclusive: `--prod` and `--swap` cannot be combined
- [x] Update `env.deploy.example` with commented staging examples
- [x] Include target (`staging` / `production` / `swap`) in the CSV log `target` column

### Phase 3 — Swap via `--swap` Flag
- [x] Implement `--swap` handler in `ubuntu_deploy.py`:
  - Verifies the staging Portainer stack exists as the staged candidate
  - Updates/starts the production Portainer stack from the Compose/image contract
  - Keeps Caddy routing on `PUBLIC_DOMAIN` → production stack
  - Stops staging containers via Portainer API
  - Writes a `swap` event to the version CSV, reusing the staged version when staging already recorded the same git ref
  - Fails clearly if staging has not been deployed yet
- [x] Write integration tests for swap promotion logic (mock SSH + Portainer calls)

### Phase 4 — Documentation
- [x] Create `docs/deploy/STAGING.md`:
  - Architecture overview (same host, two stacks, shared Caddy)
  - Environment setup (which env keys to set)
  - Deploy to staging workflow
  - Promote staging to production workflow
  - Rollback from deploy-log `git_ref`
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
| 2 | Default staging deploy resolves staging overrides correctly; schema valid; tests green |
| 3 | Swap promotion updates production, stops staging, records `swap`, and tests green |
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

1. Verify the staging Portainer stack exists as the staged candidate
2. Render the production stack from the same Compose contract and configured image refs
3. Update/start the production Portainer stack
4. Stop staging containers through the Portainer API
5. Keep Caddy routing on `PUBLIC_DOMAIN` → production stack
6. Log a `swap` event to CSV, reusing the staged version when staging already recorded the same git ref

This is a **promotion swap**: public traffic always routes to production, and staging is stopped after staging deploys and after swaps.

---

## Follow-up: Volume Safety During Swap (Phase 6)

### Problem

### Revised Design: Shared Volumes + Production Promotion

Instead of two independent stacks with separate volumes, staging and production share the same volumes. Public traffic always routes to the production stack. The swap is a **promotion operation**: update/start production from the staged Compose/image configuration, then stop staging.

**How it works:**

1. **Default deploy (staging)**: Deploy the staging stack to the same remote dir, referencing the **production volumes**. Do NOT start the staging containers. This allows the staging image/code to be ready without serving traffic or touching data.

2. **`--prod`**: Update/start the production containers. If the staging containers exist, stop them after production is running. Production serves traffic on the production domain.

3. **`--swap`**: Promote the staged build into the production stack, keep Caddy routing on `PUBLIC_DOMAIN`, then stop staging. The deploy log records target `swap` and does not increment `APP_VERSION` again when staging already recorded the same git ref.

```
Before swap:
  prod domain  -> prod containers (running, prod volumes)
  staging containers (stopped, same prod volumes)

After swap:
  prod domain  -> prod containers (running promoted build, prod volumes)
  staging containers (stopped, same prod volumes)
```

### Key Differences From Previous Design

| Aspect | Previous (separate volumes) | New (shared volumes) |
|--------|---------------------------|---------------------|
| Volumes | Stack-scoped, separate | Shared — staging uses prod volumes |
| Staging state | Independent data | Real production data |
| Swap | Caddy-only routing | Promote to production + stop staging |
| Rollback | Swap again (instant) | Checkout deploy-log `git_ref` and deploy production |
| Risk during swap | Brief downtime during container stop/start | Same |
| Storage-manager | No concern (separate volumes) | Only one set of containers runs cleanup |

### Checkable Tasks

- [x] Modify staging deploy to mount production volumes (same volume names in compose)
- [x] Staging deploy should leave containers stopped via Portainer API lifecycle
- [x] `--prod` should start prod containers and stop staging containers if running
- [x] `--swap` should:
  1. Verify staging exists as the staged candidate
  2. Promote the staged configuration to the production stack
  3. Keep Caddy routing on `PUBLIC_DOMAIN` → production stack
  4. Stop staging containers
  5. Log swap event to CSV, reusing the staged version when staging already recorded the same git ref
- [x] Rollback uses the deploy-log `git_ref` and a production deploy
- [x] Storage-manager only runs on the active stack — no cleanup conflict
- [x] Update `docs/deploy/STAGING.md` with the shared-volume model
- [x] Add deploy message: show which containers are being stopped/started
- [x] Tests for stop/start lifecycle logic
- [x] Latest `out/deploy/version_log.csv` record is written directly below the header
- [x] Version log includes APP_VERSION in the `version` column for staging, production, and swap records
- [x] Version log includes the checked-out branch in the `local_branch` column
