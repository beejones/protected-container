# Deploy Tracking CSV & Staging Environment

## Principles

- **Deploy history is observable**: Every successful deploy appends a row to a CSV log so operators can trace exactly what was deployed and when.
- **Staging mirrors production contract**: Staging uses the same Compose files, hooks, and deploy script as production — only the target parameters differ (domain, remote dir, stack name).
- **Swap is a traffic operation, not a re-deploy**: Switching between staging and production is a Caddy routing change, not a container rebuild.
- **No hardcoded staging logic in core scripts**: Staging is expressed through env profiles and a lightweight swap utility, not a parallel deploy code path.
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

---

## Checkable Task Overview

### Phase 0 — Cleanup
- [ ] Audit `scripts/deploy/ubuntu_deploy.py` for dead code, unused imports, or stale references relevant to the touched surface
- [ ] Audit `scripts/deploy/env_schema.py` for commented-out keys or stale patterns
- [ ] Remove any dead code found
- [ ] Verify existing tests pass after cleanup (`pytest -q`)

### Phase 1 — Deploy Tracking CSV (`out/deploy/deploy_log.csv`)
- [ ] Create `scripts/deploy/deploy_log.py` with:
  - `append_deploy_record(repo_root, git_ref, version, target, extra_metadata)` → appends a row
  - CSV columns: `timestamp,git_ref,version,target,stack_name,domain,status`
  - Auto-creates `out/deploy/` directory if missing
  - Reads git ref from `git rev-parse --short HEAD` when not provided
  - Version sourced from a `VERSION` file or git tag (fallback: git ref)
- [ ] Integrate `append_deploy_record` call at end of `ubuntu_deploy.py` main() after `"✅ Done"` message
- [ ] Add `out/deploy/` to `.gitignore` (tracking CSV is local state, not committed)
- [ ] Write unit tests for `deploy_log.py` (CSV creation, append, column integrity)

### Phase 2 — Staging Environment Support
- [ ] Add optional env keys to `env_schema.py`:
  - `DEPLOY_ENV` — value `production` or `staging` (default: `production`)
  - `STAGING_PUBLIC_DOMAIN` — staging domain
  - `STAGING_REMOTE_DIR` — staging remote directory
  - `STAGING_PORTAINER_STACK_NAME` — staging stack name
- [ ] Add `--env` / `--deploy-env` CLI flag to `ubuntu_deploy.py` (values: `production`, `staging`)
  - When `staging`: override `PUBLIC_DOMAIN`, `UBUNTU_REMOTE_DIR`, `PORTAINER_STACK_NAME` with staging equivalents
  - All other resolution logic unchanged
- [ ] Update `env.deploy.example` with commented staging examples
- [ ] Include `DEPLOY_ENV` value in the CSV log `target` column

### Phase 3 — Environment Swap Utility
- [ ] Create `scripts/deploy/swap_environment.py`:
  - Reads current Caddy routing for both production and staging domains
  - Swaps the upstream targets: production domain → staging container, staging domain → production container
  - Uses `caddy_register.py` helpers over SSH to rewrite Caddyfile entries
  - Validates both services are healthy before swapping (docker ps check over SSH)
  - Appends a `swap` event to the deploy CSV
- [ ] Add `--swap` flag or sub-command to `ubuntu_deploy.py` as a convenience alias
- [ ] Write integration tests for swap logic (mock SSH + Caddy register calls)

### Phase 4 — Documentation
- [ ] Create `docs/deploy/STAGING.md`:
  - Architecture overview (same host, two stacks, shared Caddy)
  - Environment setup (which env keys to set)
  - Deploy to staging workflow
  - Swap production ↔ staging workflow
  - Rollback (swap back)
- [ ] Update `docs/deploy/UBUNTU_SERVER.md` with a cross-reference to staging docs
- [ ] Update `env.deploy.example` header comment to mention staging keys

### Phase 5 — Validation
- [ ] All new and existing tests pass (`pytest`)
- [ ] `ubuntu_deploy.py --help` shows new `--deploy-env` flag
- [ ] `swap_environment.py --help` runs without error
- [ ] `validate_env.py` passes with and without staging keys set
- [ ] CSV file is created correctly after a dry-run or mocked deploy

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
timestamp,git_ref,version,target,stack_name,domain,status
2026-05-18T14:30:00Z,abc1234,1.2.0,production,protected-container,protected-container.zenia.eu,success
2026-05-18T15:00:00Z,abc1234,1.2.0,staging,protected-container-staging,staging.zenia.eu,success
2026-05-18T15:05:00Z,abc1234,1.2.0,swap,protected-container,protected-container.zenia.eu,success
```

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
