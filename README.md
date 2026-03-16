# Protected Container

A production-ready deployment toolkit for running containerised application payloads behind automatic HTTPS, with a schema-driven secrets pipeline that keeps credentials out of your Git history.

## Why this exists

Small teams and solo operators often need the same things large enterprises get from managed platforms: TLS certificates, secrets management, CI/CD, and a repeatable deploy story — without the cost or lock-in. This repo gives you that in a single, opinionated toolkit you can fork, extend, and own.

## Self-hosted servers (VPS / bare-metal)

If you run your own Ubuntu VPS, Hetzner box, or any Linux server with Docker, this repo provides an end-to-end deploy pipeline:

By default, this repository deploys **code-server** as the example application payload behind the centralized Caddy proxy.

- **One centralized [Caddy](https://caddyserver.com/) proxy** binds ports 80/443, handles Let's Encrypt certificates, and routes traffic by domain name to any number of containers on the same host.
- **[Portainer](https://www.portainer.io/)** provides a lightweight management UI and webhook-based stack deploys — no Kubernetes required.
- **`ubuntu_deploy.py`** is the single deploy command. It builds and pushes your image, syncs compose files and env vars to the remote host via SSH, triggers Portainer, and automatically registers your domain with the Caddy proxy.
- **Multiple projects on one server** simply join the shared `caddy` Docker network. There is no need to expose different app host ports (only `80` and `443` on centralized Caddy). Set the required `.env` / `.env.deploy` constants and run `scripts/deploy/ubuntu_deploy.py`; each deploy auto-registers its own route — see [Shared Caddy Routing](docs/deploy/SHARED_CADDY_ROUTING.md).

This approach is ideal for self-hosters and small enterprises who want full control over their infrastructure at a fraction of the cost of managed cloud services.

Start here: [Ubuntu Server Deployment](docs/deploy/UBUNTU_SERVER.md)

## Storage Manager

Containers that produce data over time (camera footage, logs, exports) can fill up Docker volumes silently. The **Storage Manager** is a lightweight sidecar service that runs in the central proxy stack and keeps volumes under control automatically.

- **Self-service registration** — app containers register volumes to monitor via a REST API (`POST /api/register`) or via Docker Compose labels. No manual intervention or cron jobs required.
- **Pluggable cleanup algorithms** — choose the strategy that fits each volume:

  | Algorithm | What it does |
  |-----------|-------------|
  | **Max Size** | Deletes oldest (or largest) files until total size is within the configured limit. |
  | **Remove Before Date** | Removes all files older than a fixed date or a rolling age window (e.g. 30 days). |
  | **Keep N Latest** | Retains only the N most recent files and removes the rest. |

- **Observable** — exposes `/api/health` and `/api/volumes` endpoints for Portainer dashboards and alerting.
- **Persistent** — registrations are stored in SQLite so they survive container restarts.

Start here: [Storage Manager](docs/deploy/STORAGE_MANAGER.md) · Planning: [planning/STORAGE_MANAGER.md](planning/STORAGE_MANAGER.md)

## Azure Container Instances

For teams already invested in Azure, the repo includes a parallel deploy path targeting Azure Container Instances (ACI):

- **`azure_deploy_container.py`** renders a multi-container YAML from your `docker-compose.yml`, deploys to ACI, and wires up a Caddy sidecar for TLS.
- **GitHub Actions CI/CD** with OIDC federation — no long-lived Azure credentials stored anywhere.
- **Azure Key Vault** integration for secrets at runtime (Managed Identity, no passwords).

Start here: [Azure Container Deployment](docs/deploy/AZURE_CONTAINER.md)

## Keeping secrets secure

Secrets management is a first-class concern, not an afterthought:

| Layer | How it works |
|-------|-------------|
| **Schema-driven validation** | Every env key is declared in a strict schema ([`env_schema.py`](scripts/deploy/env_schema.py)). Unknown keys fail validation — no accidental leaks. |
| **Split env files** | Non-sensitive config lives in `.env` / `.env.deploy`. Credentials go into `.env.secrets` / `.env.deploy.secrets`, which are git-ignored by default. |
| **Azure Key Vault** | On ACI deploys, runtime secrets are uploaded as a single Key Vault secret and injected at container start via Managed Identity. |
| **GitHub Actions sync** | `gh_sync_actions_env.py` pushes vars and secrets to GitHub Actions from the schema, so CI never reads raw dotenv files. |
| **No secrets in Git** | Example files (`env.example`, `env.secrets.example`) document every key without containing real values. The deploy scripts validate completeness before shipping anything. |

See [Env Schema](docs/deploy/ENV_SCHEMA.md) for the full guide on adding variables and secrets.

## Deployment methods

This repository supports three deployment methods depending on your target environment:

1. **Local (Docker Compose)**
  - Best for development and quick testing on your machine.
  - Uses `docker/docker-compose.yml`.
  - Start here: [Docker / Local Development Guide](docs/DOCKER.md)

2. **Ubuntu Server (Portainer-based remote deploy)**
  - Best for self-hosted Linux servers (for example your LAN/VPS host).
  - Uses `scripts/deploy/ubuntu_deploy.py` with SSH + Portainer stack deployment.
  - Start here: [Ubuntu Server Deployment](docs/deploy/UBUNTU_SERVER.md)

3. **Azure Container Instances (ACI)**
  - Best for managed cloud deployment with Azure services.
  - Uses `scripts/deploy/azure_deploy_container.py` and optional GitHub Actions OIDC.
  - Start here: [Azure Container Deployment](docs/deploy/AZURE_CONTAINER.md)

## Quick Start (Local Development)

```bash
# Copy example environment files
cp env.example .env
cp env.deploy.example .env.deploy

# Generate a Basic Auth password hash
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'your-password'

# Add the hash to .env
echo 'BASIC_AUTH_USER=admin' >> .env
echo 'BASIC_AUTH_HASH=<paste-hash-here>' >> .env

# Start the containers
docker compose -f docker/docker-compose.yml up --build
```

Open `https://localhost` (accept the self-signed cert warning for local dev).

## Architecture

Two containers in a container group:

| Container | Purpose | Ports |
|-----------|---------|-------|
| `protected-container` | code-server (VS Code) | Matches `docker/docker-compose.yml` (default 8080) |
| `tls-proxy` (Caddy) | TLS termination + Basic Auth | 80, 443 |

```
Internet → Caddy (443) → [Basic Auth] → code-server (8080)
```

## Documentation

- [Azure Container Deployment](docs/deploy/AZURE_CONTAINER.md) - Deploy to Azure Container Instances
- [Ubuntu Server Deployment](docs/deploy/UBUNTU_SERVER.md) - Deploy to a standalone Ubuntu server (SSH + Docker Compose)
- [code-server Setup](docs/CODE_SERVER.md) - Configuration and customization
- [Env Schema](docs/deploy/ENV_SCHEMA.md) - How to add vars/secrets to the schema
- [Add Your App](docs/deploy/ADD_YOUR_APP.md) - How to bundle and run your own app in this container
- [Shared Caddy Routing](docs/deploy/SHARED_CADDY_ROUTING.md) - Register other containers with the centralized Caddy proxy
- [Storage Manager](docs/deploy/STORAGE_MANAGER.md) - Automated volume cleanup for app containers

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

This ensures upstream resolves `.env`, `.env.deploy`, and `docker/docker-compose.yml` from the right place.

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
- A `docker/docker-compose.yml` where the main app service is marked with `x-deploy-role: app`

Start from the upstream examples (`env.example` and `env.deploy.example`), then adapt for your repo.

---

### Option B: GitHub template flow

Use GitHub’s “Use this template” button, or use `gh` with the current repo as the template:

```bash
gh repo create <your-org>/<new-repo> --public --template beejones/protected-container
```

Note: this only works if this repo is marked as a **Template repository** in GitHub settings
(Repo → Settings → General → Template repository). If it isn’t, use Option B.

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

## License

MIT License - see [LICENSE](LICENSE)
