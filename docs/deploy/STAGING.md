# Staging Environment

## Principles

- Staging mirrors the production contract — same Compose files, hooks, and deploy script.
- Only the target parameters differ: domain, remote dir, stack name.
- Default deploy target is **staging** to prevent accidental production deploys.
- Staging containers share production volumes but are **not started** on deploy.
- Only one stack (production or staging) runs at a time to avoid volume conflicts.
- Swap = stop active stack + start inactive stack + swap Caddy routing.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Ubuntu Host                                                 │
│                                                              │
│  ┌──────────────┐                                            │
│  │ Central Caddy │──► production.domain → active containers  │
│  │  (ports 80,  │──► staging.domain    → active containers  │
│  │   443)       │                                            │
│  └──────────────┘                                            │
│                                                              │
│  ┌─────────────────────────┐  ┌────────────────────────────┐ │
│  │ production stack        │  │ staging stack              │ │
│  │ (running OR stopped)    │  │ (stopped OR running)       │ │
│  │ Shared production       │  │ Shared production          │ │
│  │ volumes                 │  │ volumes                    │ │
│  └─────────────────────────┘  └────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

Both stacks are managed by Portainer on the same host. Only one runs at a time. The centralized Caddy proxy routes traffic to whichever stack is active.

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

## Deploy to Staging

Staging is the default target:

```bash
source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py
```

This deploys using `STAGING_*` overrides for domain, remote dir, and stack name. Containers are **created but not started** — they're ready to be activated via `--swap`. All other settings (SSH host, compose files, hooks) are shared.

## Deploy to Production

Pass `--prod` to target production:

```bash
source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py --prod
```

This starts production containers and stops any running staging containers. A successful production deploy auto-increments `APP_VERSION` patch in `.env`.

## Swap Production ↔ Staging

Swap the active stack — stops the currently running containers and starts the other set:

```bash
source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py --swap
```

This:
1. Stops the production containers
2. Starts the staging containers (using the same shared volumes)
3. Swaps Caddy `reverse_proxy` upstreams so the production domain serves staging containers
4. Reloads Caddy
5. Logs a `swap` event to the deploy CSV

If the Caddy swap fails, the script automatically rolls back: stops staging, restarts production.

**Rollback**: Run `--swap` again — it's symmetric (stops staging, starts production, swaps Caddy back).

## Deploy Tracking CSV

Every deploy appends a row to `out/deploy/deploy_log.csv`:

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

**Rollback from CSV**: Find the last `production` + `success` row, use `git_ref` to checkout that commit, redeploy with `--prod`.

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

5. **Verify staging works**, then swap traffic:
   ```bash
   source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py --swap
   ```

That's it. No code changes, hook modifications, or Compose file edits are needed. The same `ubuntu_deploy.py`, hooks, and Compose contract are reused — only the env parameters differ.

## Related Docs

- [Ubuntu Server Deployment](UBUNTU_SERVER.md) — base deployment setup
- [Shared Caddy Routing](SHARED_CADDY_ROUTING.md) — how multi-app routing works
- [Hooks](HOOKS.md) — customizing deploy behavior
