# code-server Setup

This document explains the code-server configuration in protected-container.

## Overview

[code-server](https://github.com/coder/code-server) runs VS Code in the browser. All authentication is handled by the Caddy reverse proxy, so code-server runs with `--auth none`.

## Container Structure

```
docker/
├── Dockerfile        # code-server base image + extensions
├── supervisord.conf  # Runs code-server as a service
├── azure_start.sh    # Fetches secrets from Key Vault
└── Caddyfile         # TLS + Basic Auth configuration
```

## Pre-installed Extensions

| Extension | ID | Purpose |
|-----------|----|---------|\n| Roo Code | `rooveterinaryinc.roo-cline` | AI coding assistant |
| GitHub Pull Requests | `GitHub.vscode-pull-request-github` | PR management |

### Installing Additional Extensions

Add to `docker/Dockerfile`:

```dockerfile
RUN code-server --install-extension publisher.extension-name
```

Or install at runtime within VS Code.

## Configuration

### Workspace Directory

Default: `/home/coder/workspace`

Mount your code here:

```yaml
volumes:
  - ./my-project:/home/coder/workspace
```

### Settings

code-server settings are stored in `/home/coder/.local/share/code-server/`.

Pre-configure settings by adding to the Dockerfile:

```dockerfile
RUN mkdir -p /home/coder/.local/share/code-server/User && \
    echo '{"workbench.colorTheme": "Default Dark+"}' > \
    /home/coder/.local/share/code-server/User/settings.json
```

## Authentication

Authentication is handled by Caddy (not code-server):

1. Caddy receives HTTPS request
2. Caddy prompts for Basic Auth
3. If authenticated, request is proxied to code-server
4. code-server runs with `--auth none` (trusts Caddy)

### Changing Password

1. Generate new hash:
   ```bash
   docker run --rm caddy:2-alpine caddy hash-password --plaintext 'new-password'
   ```

2. Update `.env`:
   ```bash
   BASIC_AUTH_HASH=$2a$14$...new-hash...
   ```

3. Upload to Key Vault (production):
   ```bash
   python scripts/deploy/azure_upload_env.py --vault my-vault --env-file .env
   ```

4. Restart container

## Local Development

```bash
# Start with docker compose
docker compose up --build

# Access at https://localhost (accept self-signed cert)
```

For local dev without TLS, you can access code-server directly on port 8080:

```bash
docker compose up app
# Access at http://localhost:8080 (no auth in dev)
```

## Troubleshooting

### code-server won't start

Check supervisor logs:
```bash
docker compose logs app
```

### Extensions not loading

Verify extensions are installed:
```bash
docker compose exec app code-server --list-extensions
```

### WebSocket errors

Ensure Caddy is configured for WebSocket upgrade (already done in default Caddyfile).
