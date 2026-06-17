# Ubuntu Server Deployment

This document describes how to deploy the `protected-container` alongside a central Caddy proxy and Portainer administrator panel on a standalone Ubuntu server.

## Architecture

This setup uses a **Centralized Proxy** approach:
- A single **Caddy** instance binds to host ports `80` and `443`.
- All other containers (like `portainer` and `protected-container`) bind no host ports.
- Caddy acts as the TLS terminator and routes incoming traffic to the appropriate containers via an external Docker network named `caddy`.

## Platform Contract

The Ubuntu host is expected to provide a shared deployment control plane. `ubuntu_deploy.py` may create, recreate, or refresh these shared platform resources so the host stays in the documented shape:
- Docker network: external bridge network named `caddy`.
- Proxy container: `central-proxy`, owned by `docker/proxy/docker-compose.yml`, binding host ports `80` and `443`.
- Admin container: `portainer`, using image `portainer/portainer-ce:latest`, attached to the `caddy` network, with no host port bindings.
- Admin data volume: `portainer_data`, preserved when the `portainer` container is recreated.

This control-plane convergence does **not** rewrite unrelated upstream application containers. App stacks are still deployed through their configured Compose/Portainer stack flow, and each web-facing app container is responsible for the shared Caddy ingress contract: join the external `caddy` network, use a unique container name, listen on the configured internal `WEB_PORT`, and avoid publishing public host ports for normal web traffic.

## Ubuntu Platform Prerequisites

- Ubuntu 24.04 LTS (recommended)
- Docker Engine + Docker Compose plugin (`docker compose`)
- SSH access to the server (key-based auth recommended), using an account that can run `docker` commands without an interactive password prompt
- `rsync` installed locally and on the server
- `curl`, `bash`, and the Docker CLI available on the server
- DNS records for the Portainer domain and each app domain pointing at the Ubuntu host before Caddy requests certificates
- **Firewall**: Ensure your server's firewall allows inbound TCP traffic on ports `80` and `443` ONLY. Do not expose `9000` or `9443` directly.

After the first successful platform setup or deploy, the expected server state is:
- `docker network inspect caddy` succeeds.
- `docker ps --filter name=central-proxy` shows the central proxy running with host ports `80` and `443`.
- `docker ps --filter name=portainer` shows Portainer running on the `caddy` network with no published host ports.
- `https://portainer.<your-domain>` reaches Portainer through Caddy, not through direct `9000` or `9443` exposure.

## Initial Server Setup

Follow these steps once on a fresh Ubuntu server.

### 0. Configure DNS

Before deploying Caddy, you must configure your DNS provider so Let's Encrypt can issue certificates:

Create two `A` records (or `CNAME` records) pointing to your Ubuntu server's public IP address:
- `portainer.your-domain.com` (for the admin panel)
- `protected-container.your-domain.com` (for the actual app)

*If your DNS is not propagated, Caddy will fail to get SSL certificates and will return 502 Bad Gateway errors.*

### 1. Stand up Centralized Caddy

The proxy configuration lives in `docker/proxy/docker-compose.yml` and `docker/proxy/Caddyfile`.
Instead of manually copying and starting it, you can use the built-in deployment script which reads the host and domains from your `.env` files.

Ensure your `.env` or `.env.secrets` has:
```env
ACME_EMAIL=your-email@example.com
```
And your `.env.deploy` has at minimum:
```env
UBUNTU_SSH_HOST=ronny@<server-ip>
PUBLIC_DOMAIN=example.com
```

Then run the bash script:

```bash
# On your local machine, from the repository root:
bash scripts/deploy/ubuntu_deploy_proxy.sh
```

*(This script syncs `docker/proxy/`, recreates the `central-proxy` container so the latest Caddyfile is mounted, validates the active config, and ensures the external `caddy` docker network is created on the remote host.)*

### 2. Stand up Portainer (Admin UI)

Deploy Portainer and attach it to the `caddy` network. **Notice we do not publish any ports (`-p`)**.

```bash
# On the server:
docker volume create portainer_data

docker run -d \
  --name portainer \
  --restart=unless-stopped \
  --network caddy \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v portainer_data:/data \
  portainer/portainer-ce:latest
```

Wait a moment, then securely access Portainer via Caddy at `https://portainer.example.com`.
Set up your initial admin password.

## Deploying the Protected Container

Now that the infrastructure is ready, deploy the `protected-container`.

### Automatic Deployment (Recommended)

By default, the deployment script runs in **SSH-free mode** (`UBUNTU_NO_SSH=true`). This interacts with Portainer strictly over the HTTP/HTTPS API to create or update the stack and does not require SSH credentials, connectivity, or `rsync` sync transfers.

To use SSH-free mode, ensure you have configured:
- `PORTAINER_ACCESS_TOKEN`: The Portainer API token in `.env.deploy.secrets`.
- `PORTAINER_API_HOST`: (Optional) The Portainer API host name, otherwise derived automatically from `PUBLIC_DOMAIN`.

If you need the script to manage the remote server lifecycle over SSH (e.g. creating/checking remote directories, syncing `.env` files, ensuring Portainer itself is running, pre-pulling GHCR images, or automatically refreshing the central Caddy proxy), you can enable the SSH mode by setting `UBUNTU_NO_SSH=false` in `.env.deploy`.

**Configure `.env.deploy.secrets` locally:**
```env
PORTAINER_WEBHOOK_TOKEN=<token-tail-only>
PORTAINER_ACCESS_TOKEN=<your-portainer-api-token>
```

**Deploy:**
```bash
source .venv/bin/activate
python scripts/deploy/ubuntu_deploy.py
```

This builds/pushes the image, then deploys the stack through the Portainer API using the repository-owned docker-compose files as the single source of truth. If SSH mode is enabled (`UBUNTU_NO_SSH=false`), it will also check SSH connectivity, sync compose and environment files via `rsync`, ensure Portainer and Caddy are running on the host, and execute pre-pull commands.

## Troubleshooting Caddy

If certificates fail to provision or routes return 502, inspect Caddy's logs:

```bash
docker logs central-proxy
```

Common issues:
- **Rate Limits**: Let's Encrypt limits failed validations. Double-check your DNS points to the correct IP.
- **Container Not Found**: Caddy resolves upstream targets by their container name (e.g., `reverse_proxy portainer:9000`). If the container is not on the `caddy` network or its name differs, Caddy will return a 502 error.

## Adding Other Projects to Caddy

If you have additional services on the same server that need HTTPS routing through the centralized proxy, see [Shared Caddy Routing](SHARED_CADDY_ROUTING.md).

## Staging and Production Promotion

For predeploying staging as stopped containers, promoting that staged build into the production stack with `--swap`, and keeping `PUBLIC_DOMAIN` routed to production, see [Staging Environment](STAGING.md).

