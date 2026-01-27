# Azure Container Deployment (ACI)

Deploy **protected-azure-container** to **Azure Container Instances (ACI)** with:

- **code-server** (VS Code in browser) as the main interface
- **Caddy** sidecar for **TLS** with automatic Let's Encrypt certificates
- **Basic Auth** protection
- **Azure Key Vault** + **Managed Identity** for secrets
- **Azure Files** persistence for workspace and config

## Architecture

ACI container group with 2 containers (configuration derived from `docker-compose.yml`):

| Container | Purpose | Ports |
|-----------|---------|-------|
| `protected-azure-container` | code-server | Matches `docker-compose.yml` (default 8080) |
| `tls-proxy` (Caddy) | TLS + Basic Auth | 80, 443 (public) |

```
Internet → Caddy (:443) → [TLS + Basic Auth] → code-server (:app_port)
```

## Prerequisites

- Azure CLI: `az login`
- Docker image pushed to GHCR/ACR
- `.env` file with Basic Auth credentials (runtime)
- `.env.deploy` file with Azure + deploy configuration (deploy-time)

Deployment reads `.env` first, then `.env.deploy` on top (deploy-time overrides).

## Step 1 — Create Azure Resources

The deploy script auto-creates resources if they don't exist:

```bash
python scripts/deploy/azure_deploy_container.py \
  --resource-group protected-azure-container-rg \
  --location westeurope
```

Creates:
- Resource group
- Managed Identity
- Storage account + file shares
- Key Vault (RBAC enabled)

## Step 2 — Configure Authentication

### Generate Basic Auth Hash

```bash
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'your-password'
```

Add to `.env`:

```bash
BASIC_AUTH_USER=admin
BASIC_AUTH_HASH=$2a$14$...your-hash...
```

### Upload to Key Vault

```bash
python scripts/deploy/azure_upload_env.py \
  --vault protected-azure-container-rg-kv \
  --env-file .env
```

## Step 3 — Deploy to ACI

```bash
python scripts/deploy/azure_deploy_container.py \
  --resource-group protected-azure-container-rg \
  --image ghcr.io/your-user/protected-azure-container:latest \
  --public-domain your-domain.com \
  --acme-email you@your-domain.com \
  --env-file .env.deploy
```

## Step 4 — DNS Setup

Point your domain CNAME to the ACI FQDN:

```bash
az container show \
  --name protected-azure-container \
  --resource-group protected-azure-container-rg \
  --query ipAddress.fqdn -o tsv
```

Result: `<dns-label>.<location>.azurecontainer.io`

## Access

- **VS Code**: `https://your-domain.com/`
- **Health check**: `https://your-domain.com/healthz`

## Troubleshooting

### ACI `command` Overrides Docker `ENTRYPOINT`

Azure Container Instances treats a container `command:` as an **override** for the image's Docker `ENTRYPOINT`.
This repo relies on the image entrypoint (`/usr/local/bin/azure_start.sh`) to fetch Key Vault runtime env and then `exec` the application.

If your `docker-compose.yml` defines an app `command`, the deploy YAML generator will automatically prefix it with `/usr/local/bin/azure_start.sh` so the Key Vault fetch still runs.

If you're debugging a deployment where Key Vault logs are missing, check the app container's rendered YAML `command:` list includes `/usr/local/bin/azure_start.sh` as the first element.

### View Logs

```bash
# code-server container
az container logs --resource-group protected-azure-container-rg \
  --name protected-azure-container --container-name protected-azure-container

# Caddy container
az container logs --resource-group protected-azure-container-rg \
  --name protected-azure-container --container-name tls-proxy
```

### Common Issues

| Issue | Solution |
|-------|----------|
| 502 Bad Gateway | Check code-server is running in app container |
| TLS cert error | Verify domain DNS points to ACI IP |
| Auth not working | Verify BASIC_AUTH_HASH is valid bcrypt |

## GitHub Actions

See [.github/workflows/deploy.yml](../.github/workflows/deploy.yml) for automated deployment.
Triggers on: **Workflow Dispatch** (Manual)

### Required Setup

1. **Environment**: Create an environment named `production` in GitHub Settings.
2. **Secrets** (Environment or Repo):
   - `RUNTIME_ENV_DOTENV`: The **full content** of `.env` (excluding comments is fine).
   - `BASIC_AUTH_HASH`: The bcrypt hash for Basic Auth.
3. **Variables** (Environment or Repo):
   - `AZURE_CLIENT_ID` (OIDC App ID)
   - `AZURE_TENANT_ID`
   - `AZURE_SUBSCRIPTION_ID`
   - `AZURE_RESOURCE_GROUP` (e.g. `protected-azure-container-rg`)
   - `AZURE_CONTAINER_NAME` (e.g. `protected-azure-container`)
   - `AZURE_PUBLIC_DOMAIN` (e.g. `your-domain.com`)
   - `AZURE_ACME_EMAIL`
   - `BASIC_AUTH_USER`

### Resetting GitHub Secrets

If you need to clear all secrets and variables (e.g. to fix stale environment overrides or reset completely):

**Option 1: Integrated Flag (Recommended)**
Runs before syncing new values:
```bash
python scripts/deploy/azure_deploy_container.py --nuke-github-secrets
```

**Option 2: Standalone Script**
```bash
python scripts/deploy/gh_nuke_secrets.py
```

*Note: You will be asked to type `DELETE` to confirm unless you run in non-interactive mode.*
