# Staging Environment

## Principles

- Staging mirrors the production contract — same Compose files, hooks, and deploy script.
- Only the target parameters differ: domain, remote dir, stack name.
- Default deploy target is **staging** to prevent accidental production deploys.
- Swap is a Caddy routing operation, not a container rebuild (zero-downtime).

## Architecture

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
│  └─────────────────────┘  └──────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

Both stacks are managed by Portainer on the same host. The centralized Caddy proxy routes traffic to each stack based on domain.

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

This deploys using `STAGING_*` overrides for domain, remote dir, and stack name. All other settings (SSH host, compose files, hooks) are shared.

## Deploy to Production

Pass `--prod` to target production:

```bash
source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py --prod
```

A successful production deploy auto-increments `APP_VERSION` patch in `.env`.

## Swap Production ↔ Staging

Swap traffic between staging and production without restarting containers:

```bash
source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py --swap
```

This:
1. Reads the Caddyfile on the remote host
2. Swaps `reverse_proxy` upstreams between the production and staging domains
3. Reloads Caddy (zero-downtime)
4. Logs a `swap` event to the deploy CSV

**Rollback**: Run `--swap` again — it's symmetric.

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

3. **Deploy to staging** (default — no extra flags):
   ```bash
   source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py
   ```

4. **Verify staging works**, then swap traffic:
   ```bash
   source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py --swap
   ```

That's it. No code changes, hook modifications, or Compose file edits are needed. The same `ubuntu_deploy.py`, hooks, and Compose contract are reused — only the env parameters differ.

## Related Docs

- [Ubuntu Server Deployment](UBUNTU_SERVER.md) — base deployment setup
- [Shared Caddy Routing](SHARED_CADDY_ROUTING.md) — how multi-app routing works
- [Hooks](HOOKS.md) — customizing deploy behavior
