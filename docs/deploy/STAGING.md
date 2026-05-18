# Staging Environment

## Principles

- Staging mirrors the production contract — same Compose files, hooks, and deploy script.
- Only the target parameters differ: domain, remote dir, stack name.
- Default deploy target is **staging** to prevent accidental production deploys.
- Staging containers share production volumes but are **not started** on deploy.
- Public traffic always routes to the production stack via `PUBLIC_DOMAIN`.
- Swap = promote the staged Compose/image configuration into the production stack, start production, then stop staging.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Ubuntu Host                                                 │
│                                                              │
│  ┌──────────────┐                                            │
│  │ Central Caddy │──► production.domain → production stack   │
│  │  (ports 80,  │──► staging.domain    → staging stack       │
│  │   443)       │                                            │
│  └──────────────┘                                            │
│                                                              │
│  ┌─────────────────────────┐  ┌────────────────────────────┐ │
│  │ production stack        │  │ staging stack              │ │
│  │ (running)               │  │ (stopped after deploy/swap)│ │
│  │ Shared production       │  │ Shared production          │ │
│  │ volumes                 │  │ volumes                    │ │
│  └─────────────────────────┘  └────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

Both stacks are managed by Portainer on the same host. The centralized Caddy proxy keeps `PUBLIC_DOMAIN` pointed at the production stack. When a staging stack is rendered for Portainer, explicit `container_name` values are rewritten to avoid collisions with production (for example, `protected-container` becomes the staging stack name). Staging is stopped after staging deploys and after swaps so it never remains the active runtime.

## Environment Setup

Add these keys to `.env.deploy`:

```bash
# Required: Production domain (already exists)
PUBLIC_DOMAIN=your-app.example.com

# Staging environment
STAGING_PUBLIC_DOMAIN=staging-your-app.example.com
STAGING_REMOTE_DIR=/home/your-user/containers/protected-container-staging
STAGING_PORTAINER_STACK_NAME=protected-container-staging
```

Ensure DNS records exist for both `PUBLIC_DOMAIN` and `STAGING_PUBLIC_DOMAIN` pointing to the same server.

Portainer API calls use the SSL-enabled Portainer host derived from `PUBLIC_DOMAIN`. For example, `PUBLIC_DOMAIN=protected-container.zenia.eu` resolves Portainer API calls to `portainer.zenia.eu` on HTTPS port `443` unless `PORTAINER_HTTPS_PORT` is set.

## Deploy to Staging

Staging is the default target:

```bash
source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py
```

This deploys using `STAGING_*` overrides for domain, remote dir, and stack name. Containers are **created and then stopped via Portainer API**. All other settings (SSH host, compose files, hooks) are shared.

## Deploy to Production

Pass `--prod` to target production:

```bash
source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py --prod
```

This updates and starts production containers, then stops any staging containers. A successful production deploy auto-increments `APP_VERSION` patch in `.env`.

## Promote Staging to Production

Promote the staged build into the production stack while keeping public routing on `PUBLIC_DOMAIN`:

```bash
source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py --swap
```

This:
1. Verifies the staging Portainer stack has containers
2. Renders the production stack from the same Compose contract and configured images
3. Updates/starts the production Portainer stack
4. Stops staging containers via Portainer API
5. Keeps Caddy routing on `PUBLIC_DOMAIN` → production stack
6. Logs a `swap` event to the deploy CSV without incrementing `APP_VERSION`

Rollback uses a normal production deploy from the desired `git_ref` recorded in the deploy log.

## Deploy Tracking CSV

Every deploy writes a row to `out/deploy/deploy_log.csv`. The latest record appears directly under the header:

| Column | Example |
|--------|---------|
| `timestamp` | `2026-05-18T14:30:00Z` |
| `git_ref` | Full 40-char SHA |
| `version` | `1.2.3` from `APP_VERSION` |
| `target` | `staging` / `production` / `swap` |
| `stack_name` | Portainer stack name |
| `domain` | Public domain for this deploy |
| `image` | Container image deployed |
| `status` | `success` / `failed` |

`APP_VERSION` is recorded in the `version` column for every deploy. Successful production deploys increment `APP_VERSION` after the row is written. `swap` records do not increment `APP_VERSION`; they record the version associated with the staged promotion.

**Rollback from CSV**: Find the latest `production` or `swap` + `success` row, use `git_ref` to checkout that commit, redeploy with `--prod`.

## Mutual Exclusion

`--prod` and `--swap` cannot be combined:

```bash
# This errors:
python scripts/deploy/ubuntu_deploy.py --swap --prod
# error: --prod and --swap are mutually exclusive
```

## Adopting Staging in a Downstream Project

Projects that use this toolkit as their deployment base inherit staging support with minimal effort:

1. **Add DNS record** for your staging domain (e.g. `staging-myapp.example.com`) pointing to the same server as production.

2. **Add staging keys to `.env.deploy`**:
   ```bash
   STAGING_PUBLIC_DOMAIN=staging-myapp.example.com
   STAGING_REMOTE_DIR=/home/deploy/containers/myapp-staging
   STAGING_PORTAINER_STACK_NAME=myapp-staging
   ```

3. **Add APP_VERSION=0.2.1 to `.env`**:
   ```bash
   APP_VERSION=0.2.1
   ```

4. **Deploy to staging** (default — no extra flags):
   ```bash
   source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py
   ```

5. **Verify staging works**, then promote it to production:
   ```bash
   source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py --swap
   ```

That's it. No code changes, hook modifications, or Compose file edits are needed. The same `ubuntu_deploy.py`, hooks, and Compose contract are reused — only the env parameters differ.

## Related Docs

- [Ubuntu Server Deployment](UBUNTU_SERVER.md) — base deployment setup
- [Shared Caddy Routing](SHARED_CADDY_ROUTING.md) — how multi-app routing works
- [Hooks](HOOKS.md) — customizing deploy behavior
