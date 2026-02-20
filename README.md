# Protected Azure Container

A world-class protected container setup featuring:
- **VS Code in browser** via [code-server](https://github.com/coder/code-server)
- **TLS termination** with automatic Let's Encrypt certificates via Caddy
- **Azure Key Vault** integration for secrets management
- **Azure Managed Identity** for secure authentication
- **GitHub Actions** CI/CD with OIDC authentication

## Quick Start (Local Development)

```bash
# Copy example environment files
cp env.example .env
cp env.secrets.example .env.secrets
cp env.deploy.example .env.deploy
cp env.deploy.secrets.example .env.deploy.secrets

# Generate a Basic Auth password hash
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'your-password'

# Add the hash to .env.secrets
echo 'BASIC_AUTH_HASH=<paste-hash-here>' >> .env.secrets

# Start the containers
docker compose up --build
```

Open `https://localhost` (accept the self-signed cert warning for local dev).

## Architecture

Two containers in a container group (configuration derived from `docker-compose.yml`):

| Container | Purpose | Ports |
|-----------|---------|-------|
| `protected-container` | code-server (VS Code) | Matches `docker-compose.yml` (default 8080) |
| `tls-proxy` (Caddy) | TLS termination + Basic Auth | 80, 443 |
| `other` (Optional) | Generic additional service | Matches `docker-compose.yml` role |

```
Internet → Caddy (443) → [Basic Auth] → code-server (app_port)
                                      ↘ other (optional)
```

## Docker Compose as Source of Truth

The deployment scripts (`scripts/deploy/`) are designed to read your repository's `docker-compose.yml` file to derive key configuration values. This creates a clear contract using `x-deploy-role`:

1. **App Service**: `x-deploy-role: app`
    - Main application (code-server).

2. **Sidecar Service**: `x-deploy-role: sidecar`
    - Caddy / TLS termination.

3. **Other Service**: (Optional) Service with no special role or explicit `x-deploy-role: other` (implicit).
    - Deployed as a generic sidecar container sharing the workspace volume.

**Example:**

```yaml
services:
  my-app:
    x-deploy-role: app
    # ...
  
  caddy:
    x-deploy-role: sidecar
    # ...
```

If you ever need to override this detection, you can still use the CLI arguments:
```bash
python scripts/deploy/azure_deploy_container.py --compose-app-service my-legacy-app
```

### Precedence

**CLI Arguments > Docker Compose > Defaults**

Explicit arguments (e.g. `--caddy-image foo:bar`) always override values derived from `docker-compose.yml`.

## Documentation

- [Azure Container Deployment](docs/deploy/AZURE_CONTAINER.md) - Deploy to Azure Container Instances
- [code-server Setup](docs/CODE_SERVER.md) - Configuration and customization
- [Env Schema](docs/deploy/ENV_SCHEMA.md) - How to add vars/secrets to the schema
- [Add Your App](docs/deploy/ADD_YOUR_APP.md) - How to bundle and run your own app in this container

## Use This Repo As A Template

If you want to use this project as a base for a new repo that needs a protected Azure container:

### Option A: Pinned submodule + wrappers + hooks (recommended)

Best for repos that **already have their own app** and only need the deployment engine. You get a vendored, updatable copy of the upstream deploy scripts pinned to a specific commit.

**What you get:**

- Stable, repo-local entrypoints (wrappers) under `scripts/deploy/` so users and CI always run *your* scripts
- A single customization surface (`deploy_customizations.py`) that upstream calls at lifecycle points (pre-validate, plan, render, etc.)
- Reproducible builds — your repo records the exact upstream commit via the submodule pointer

#### 1) Vendor upstream as a git submodule

```bash
git submodule add https://github.com/beejones/protected-container scripts/deploy/_upstream
git submodule update --init --recursive
```

To update later:

```bash
git submodule update --remote --merge scripts/deploy/_upstream
```

#### 2) Create repo-local wrapper entrypoints

Create thin wrapper scripts in `scripts/deploy/` that:

1. Verify the submodule exists (fail fast with a helpful message).
2. Put the upstream deploy scripts directory on `sys.path`.
3. Import and invoke the upstream entrypoint with `repo_root_override` pointing to *your* repo:

```python
upstream_engine.main(argv_list, repo_root_override=repo_root)
```

This ensures upstream resolves `.env`, `.env.deploy`, and `docker-compose.yml` from the right place.

If you also use the upstream GitHub Actions helpers, wrap them the same way (e.g. `gh_sync_actions_env.py`, `gh_nuke_secrets.py`).

#### 3) Add a hooks module for customization

Create `scripts/deploy/deploy_customizations.py` in your repo. The upstream engine loads hooks in this precedence order:

1. `--hooks-module <path>`
2. `DEPLOY_HOOKS_MODULE=<path>`
3. `scripts/deploy/deploy_customizations.py` (default convention)

Common hook uses:

- Allowing additional runtime keys beyond the upstream schema
- Translating legacy deploy keys (e.g. `GHCR_IMAGE` → `APP_IMAGE`)
- Post-processing the rendered ACI YAML / Caddyfile (e.g. injecting additional reverse-proxy routes)

#### 4) Ensure CI checks out submodules

```yaml
- uses: actions/checkout@v4
  with:
    submodules: recursive
```

#### 5) Keep env files and compose annotations aligned

At minimum, upstream expects:

- A runtime `.env` (secrets / runtime config)
- A deploy-time `.env.deploy` (Azure + registry configuration)
- A `docker-compose.yml` where the main app service is marked with `x-deploy-role: app`

Start from the upstream examples (`env.example` and `env.deploy.example`), then adapt for your repo.

---

### Option B: GitHub template flow

Use GitHub’s “Use this template” button, or use `gh` with the current repo as the template:

```bash
gh repo create <your-org>/<new-repo> --public --template beejones/protected-container
```

Note: this only works if this repo is marked as a **Template repository** in GitHub settings
(Repo → Settings → General → Template repository). If it isn’t, use Option C.

Note: template-based repos are a snapshot. They do not automatically stay connected to this repo for future updates.

### Option C: Clone and re-init git

```bash
git clone https://github.com/beejones/protected-container.git my-new-repo
cd my-new-repo

# Keep a link to the original repo so you can pull updates later
git remote rename origin upstream

# Point "origin" at your new repo
git remote add origin git@github.com:<your-org>/<new-repo>.git

# Push your new repo
git push -u origin main
```

Later, you can pull changes from this repo with:

```bash
git pull upstream main
```

After that, update the deployment settings in `.env.deploy` and runtime settings in `.env`.

When you need to add new configuration keys, follow the schema guide: [docs/deploy/ENV_SCHEMA.md](docs/deploy/ENV_SCHEMA.md).

## Pre-installed Extensions

- **Roo Code** (`rooveterinaryinc.roo-cline`) - AI coding assistant
- **GitHub Pull Requests** (`GitHub.vscode-pull-request-github`) - PR management

## Environment Variables

This repo uses a strict, schema-driven set of env keys.

- **Runtime Config**: `.env` (non-secret settings)
- **Runtime Secrets**: `.env.secrets` (sensitive keys, uploaded to Key Vault as `env-secrets`)
- **Deploy Config**: `.env.deploy` (deployment settings, e.g. Azure location)
- **Deploy Secrets**: `.env.deploy.secrets` (deployment credentials, e.g. GHCR token)

Deployment loads and merges these files (deploy values override runtime values, secrets override non-secrets).

See env.example and env.deploy.example for the canonical keys.
If you need to add a new key, follow: [docs/deploy/ENV_SCHEMA.md](docs/deploy/ENV_SCHEMA.md).

## Deployment Customization

Downstream consumers can customize the deployment process (e.g., override images, resources, or patch YAML) using **Deployment Hooks**. This prevents the need to maintain a fork with modified core scripts.

See: [docs/deploy/HOOKS.md](docs/deploy/HOOKS.md)

## Debugging deploys: restart policy (ACI)

By default, Azure Container Instances restarts the container group when a container exits non-zero (`restartPolicy: OnFailure`), which can make debugging CrashLoopBackOff noisy.

You can control this via the deploy script:

- Normal (default, restart on failure):

```bash
python3 scripts/deploy/azure_deploy_container.py --restart-policy OnFailure
```

- Debug (do not restart on failure; container stays terminated so you can inspect logs/state):

```bash
python3 scripts/deploy/azure_deploy_container.py --restart-policy Never
```

- Optional: always restart (even on clean exit):

```bash
python3 scripts/deploy/azure_deploy_container.py --restart-policy Always
```

You can also set `ACI_RESTART_POLICY` (or `AZURE_RESTART_POLICY`) in your shell instead of passing the flag.

## Migration Guide

### Renamed Variables (Jan 2026)

To support multiple containers, generic variable names have been updated:

*   **`CONTAINER_IMAGE`** → **`APP_IMAGE`**
*   **`DEFAULT_CPU_CORES`** → **`APP_CPU_CORES`**
*   (CLI) `--cpu` → `--app-cpu` (old flag still works)
*   (CLI) `--memory` → `--app-memory` (old flag still works)

### New Sidecar/Other Variables

*   `CADDY_IMAGE`, `CADDY_CPU_CORES`, `CADDY_MEMORY_GB`
*   `OTHER_IMAGE`, `OTHER_CPU_CORES`, `OTHER_MEMORY_GB` (for generic third container)

## Security Notes

### `other` Container Volume Access

If you deploy an `other` container (e.g., using `OTHER_IMAGE`), it shares the **same workspace volume** (`/home/coder/workspace`) as the main code-server container. This allows for convenient file sharing but implies that the `other` container has full read/write access to your code files. Ensure you trust the image used for the `other` container.

## License

MIT License - see [LICENSE](LICENSE)
