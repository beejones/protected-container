# Ubuntu Server Deployment

This document describes how to run this repository on a standalone Ubuntu server using Docker Compose, without Azure.

## Overview

- You deploy the same `docker/docker-compose.yml`, plus a small Ubuntu override file: `docker/docker-compose.ubuntu.yml`.
- The Ubuntu override swaps the app entrypoint to `ubuntu_start.sh`, which sources `.env` and `.env.secrets` from a host directory.

## Prerequisites

- Ubuntu 24.04 LTS (recommended)
- Docker Engine + Docker Compose plugin (`docker compose`)
- SSH access to the server (key-based auth recommended)
- `rsync` installed locally and on the server

## Entrypoint: ubuntu_start.sh

The image includes `/usr/local/bin/ubuntu_start.sh`. On Ubuntu deployments, the compose override sets:

- `entrypoint: ["/usr/local/bin/ubuntu_start.sh"]`
- `command: ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]`

The script reads:

- `${ENV_DIR:-/opt/app}/.env`
- `${ENV_DIR:-/opt/app}/.env.secrets` (optional)

## First Deploy (SSH)

Use the Ubuntu deploy engine:

```bash
source .venv/bin/activate
python scripts/deploy/ubuntu_deploy.py \
  --remote-dir /opt/protected-container \
  --sync-secrets
```

`--host` is optional if `UBUNTU_SSH_HOST` is set (resolution order: CLI `--host` → env var `UBUNTU_SSH_HOST` → `.env.deploy`).
`--remote-dir` is optional if `UBUNTU_REMOTE_DIR` is set (resolution order: CLI `--remote-dir` → env var `UBUNTU_REMOTE_DIR` → `.env.deploy` → `/opt/protected-container`).

`python scripts/deploy/ubuntu_deploy.py` can run with no args when defaults are present in `.env.deploy` / `.env.deploy.secrets`.

This copies:

- `docker/docker-compose.yml`
- `docker/docker-compose.ubuntu.yml`
- `docker/`
- optionally `.env` + `.env.secrets` + `.env.deploy.secrets`

Then triggers the configured Portainer stack webhook.

## Updating

Re-run the deploy command after pushing a new image or changing compose configuration.

## Optional: Portainer on Ubuntu

If you want to manage containers and stacks from a UI, run Portainer CE on the server.

Valid ports are `1-65535`; use host port `9943` (not `99443`) mapped to Portainer's internal `9443`.

```bash
docker volume create portainer_data

docker run -d \
  --name portainer \
  --restart=unless-stopped \
  -p 8000:8000 \
  -p 9943:9443 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v portainer_data:/data \
  portainer/portainer-ce:latest
```

Then open:

- `https://<server-ip>:9943`

If UFW is enabled, allow:

```bash
sudo ufw allow 9943/tcp
```

### Portainer stack for this repo

- Single-app server (per-stack Caddy):
  - `docker/docker-compose.yml`
  - `docker/docker-compose.ubuntu.yml`
- Multi-app server with shared Caddy:
  - `docker/docker-compose.yml`
  - `docker/docker-compose.ubuntu.yml`
  - `docker/docker-compose.shared-caddy.yml`

For shared-Caddy mode, create the external network once:

```bash
docker network create caddy
```

### Deploy via Portainer webhook

To keep the app registered under a Portainer stack, let Portainer perform the deploy.

Use the Ubuntu deploy script:

```bash
export PORTAINER_WEBHOOK_TOKEN=<token-tail-only>

python scripts/deploy/ubuntu_deploy.py \
  --remote-dir /home/ronny/containers/protected-container \
  --sync-secrets
```

Notes:

- Portainer webhook deployment is the only deployment mode.
- `PORTAINER_WEBHOOK_TOKEN` is only the **last token segment** from the webhook URL, not the full URL.
- Token resolution order is: `--portainer-webhook-token` → `PORTAINER_WEBHOOK_TOKEN` env var → `.env.deploy.secrets`.
- Webhook URL resolution order is: `--portainer-webhook-url` → `PORTAINER_WEBHOOK_URL` env var → `.env.deploy.secrets` → `.env.deploy`.
- Additional defaults from `.env.deploy`: `UBUNTU_COMPOSE_FILES`, `UBUNTU_SYNC_SECRETS`, `PORTAINER_HTTPS_PORT`, `PORTAINER_WEBHOOK_INSECURE`.
- Portainer API auth is access-token only: use `PORTAINER_ACCESS_TOKEN` in `.env.deploy.secrets`.
- The script automatically ensures Portainer is running on the server (creates or starts `portainer` container).
- Use `--portainer-https-port` to change the auto-created Portainer host port (default `9943`).
- Use `--portainer-webhook-insecure` if your webhook URL uses a self-signed TLS certificate.
- Optional override: pass `--portainer-webhook-url` if you prefer using the full webhook URL directly.

## Troubleshooting (Ubuntu)

Use this checklist when `python scripts/deploy/ubuntu_deploy.py` does not complete successfully.

### 1) SSH key auth fails

Symptoms:

- `Permission denied (publickey,password)`
- deploy script fails before file sync

Fix:

```bash
bash scripts/install_ssh_public_key.sh ronny@192.168.1.45 ~/.ssh/id_ed25519.pub
ssh -o PreferredAuthentications=publickey -o PasswordAuthentication=no ronny@192.168.1.45
```

### 2) Remote path/permission errors

Symptoms:

- `Permission denied` writing to remote deploy directory

Fix:

- Use a writable user-owned path, for example:
  - `UBUNTU_REMOTE_DIR=/home/<user>/containers/protected-container`
- Re-run deploy.

### 3) Portainer webhook 404

Symptoms:

- webhook trigger returns 404

Fix:

- Set `PORTAINER_ACCESS_TOKEN` in `.env.deploy.secrets` so the script can resolve/create stack webhook details via API.
- Ensure `PORTAINER_HTTPS_PORT` matches your Portainer host port (default `9943`).
- If using self-signed TLS, set `PORTAINER_WEBHOOK_INSECURE=true`.

### 4) "Stack deployed via Portainer API; webhook token not returned"

This is a successful path, not an error.

- It means the stack was deployed through Portainer API directly.
- Webhook trigger was skipped because Portainer did not return a webhook token.

### 5) Wrong env key name for Portainer port

Use this key:

- `PORTAINER_HTTPS_PORT=9943`

Do not rely on older/non-standard aliases.

## Quick Verify (After Deploy)

Run these checks after `python scripts/deploy/ubuntu_deploy.py`:

```bash
# 1) SSH connectivity
ssh <user>@<host> "echo SSH_OK"

# 2) Portainer is running
ssh <user>@<host> "docker ps --format '{{.Names}}' | grep -Fx portainer"

# 3) Stack containers are running
ssh <user>@<host> "docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'protected-container|tls-proxy|caddy'"

# 4) Portainer UI reachable
curl -k -I https://<host>:<port>/

# 5) App endpoint reachable (replace with your domain if configured)
curl -k -I https://<host>/
```

Use `-k` only when testing against a self-signed certificate. Omit `-k` for valid public certificates.

If step 3 returns nothing, open Portainer and inspect the stack logs/events.

## Notes

- For multi-app servers, you typically want a single shared Caddy instance bound to 80/443, and each app stack runs without its own Caddy sidecar.

### Multi-app: Shared Caddy Pattern

The default compose in this repo is **one Caddy per stack** (good for a single-app server). For multi-app, use the provided override:

- [docker/docker-compose.shared-caddy.yml](../../docker/docker-compose.shared-caddy.yml)

This override:

- Adds the app stack to an external Docker network named `caddy`.
- Puts the repo’s `caddy` sidecar behind a non-default profile so it does **not** start unless explicitly enabled.

On the server, create the shared network once:

```bash
docker network create caddy
```

Then deploy the app stack using the extra override file:

```bash
python scripts/deploy/ubuntu_deploy.py \
  --remote-dir /home/ronny/containers/protected-container \
  --compose-files docker/docker-compose.yml,docker/docker-compose.ubuntu.yml,docker/docker-compose.shared-caddy.yml
```

For the shared Caddy instance itself, use a Caddyfile that contains *multiple* host blocks, for example:

- [docker/Caddyfile.multiapp.example](../../docker/Caddyfile.multiapp.example)
