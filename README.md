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
cp env.deploy.example .env.deploy

# Generate a Basic Auth password hash
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'your-password'

# Add the hash to .env
echo 'BASIC_AUTH_USER=admin' >> .env
echo 'BASIC_AUTH_HASH=<paste-hash-here>' >> .env

# Start the containers
docker compose up --build
```

Open `https://localhost` (accept the self-signed cert warning for local dev).

## Architecture

Two containers in a container group (configuration derived from `docker-compose.yml`):

| Container | Purpose | Ports |
|-----------|---------|-------|
| `protected-azure-container` | code-server (VS Code) | Matches `docker-compose.yml` (default 8080) |
| `tls-proxy` (Caddy) | TLS termination + Basic Auth | 80, 443 |

```
Internet → Caddy (443) → [Basic Auth] → code-server (app_port)
```

```
Internet → Caddy (443) → [Basic Auth] → code-server (app_port)
```

## Docker Compose as Source of Truth

The deployment scripts (`scripts/deploy/`) are designed to read your repository's `docker-compose.yml` file to derive key configuration values. This ensures that your local development environment and your Azure production deployment stay in sync.

### Service Discovery via `x-deploy-role`

The deploy script discovers which service is which by looking for the `x-deploy-role` extension field in `docker-compose.yml`. This creates a clear, explicit contract that doesn't rely on guessing names.

1. **App Service**: Must have `x-deploy-role: app`
    - The script uses this service to determine the port and build context.

2. **Sidecar Service**: Must have `x-deploy-role: sidecar`
    - The script uses this service to identify the image to deploy as the TLS proxy.

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

### Option A: GitHub template flow (recommended)

Use GitHub’s “Use this template” button, or use `gh` with the current repo as the template:

```bash
gh repo create <your-org>/<new-repo> --public --template beejones/protected-azure-container
```

Note: this only works if this repo is marked as a **Template repository** in GitHub settings
(Repo → Settings → General → Template repository). If it isn’t, use Option B.

Note: template-based repos are a snapshot. They do not automatically stay connected to this repo for future updates.

### Option B: Clone and re-init git

```bash
git clone https://github.com/beejones/protected-azure-container.git my-new-repo
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

- Runtime config lives in `.env` (and is uploaded to Key Vault as a single secret).
- Deploy-time config lives in `.env.deploy`.
- Deployment reads `.env` first, then `.env.deploy` on top (deploy-time overrides).

See env.example and env.deploy.example for the canonical keys.
If you need to add a new key, follow: [docs/deploy/ENV_SCHEMA.md](docs/deploy/ENV_SCHEMA.md).

## License

MIT License - see [LICENSE](LICENSE)
