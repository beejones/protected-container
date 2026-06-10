# Shared Caddy Routing

## Principles

All public routes registered through the centralized Ubuntu Caddy proxy must inherit the same Caddy access gate before traffic is forwarded to an app container. Registration should be deterministic, idempotent, and safe to rerun: missing routes are appended, and stale unprotected routes are repaired instead of being silently treated as healthy.

This guide explains how other projects deployed on the same Ubuntu server can register with the centralized Caddy proxy for automatic HTTPS routing — without needing their own sidecar proxies.

## How it works

The centralized proxy binds to host ports `80` and `443` and handles all SSL certificates.
Incoming requests are matched by domain name in `docker/proxy/Caddyfile` and routed internally via the external `caddy` Docker network to the appropriate container.

Registration is **fully automated** by the `ubuntu_deploy.py` script.  All you need to do is:

1. Prepare your project's `docker-compose.yml` (network + container name).
2. Set the right env vars in `.env.deploy`.
3. Run `ubuntu_deploy.py` — the Caddyfile is updated and Caddy reloaded for you.

The generated site block uses the selected `EDGE_AUTH_MODE` from `.env.deploy`:

- `basic` keeps the centralized proxy `basic_auth` guard using `BASIC_AUTH_USER` and `BASIC_AUTH_HASH` placeholders. This remains the rollback mode.
- `oidc` imports the shared `protected_auth` Caddy snippet, which strips spoofable identity headers, forwards Authentik outpost paths to Authentik, and calls Authentik with Caddy `forward_auth` before proxying to the app.
- `public` registers an intentionally unprotected route and should only be used for routes that must not inherit the shared guard.

App-specific auth such as session login or API keys remains separate defense-in-depth behind that Caddy boundary.

When `EDGE_AUTH_MODE=oidc` is enabled, the central proxy stack must also run the Authentik services from the `oidc` Compose profile:

```bash
docker compose -f docker/proxy/docker-compose.yml --profile oidc up -d
```

Without that profile, Caddy can render OIDC routes but the `authentik-server:9000` forward-auth target will not exist.

## Step-by-step

### 1. Join the `caddy` network in your Compose file

Ensure your web-facing service connects to the external `caddy` network.  **Do not** publish host ports for your web service — Caddy handles external traffic.

```yaml
services:
  app:
    container_name: my-app-production   # explicit name avoids routing collisions
    # ports:                             # let Caddy handle external access
    #   - "8080:8080"
    networks:
      - internal
      - caddy

networks:
  internal:
    driver: bridge
  caddy:
    external: true
    name: caddy
```

> **Tip:** The `container_name` becomes the upstream target in the Caddyfile (`reverse_proxy my-app-production:8080`). Pick a name that is unique across all projects on the server.

### 2. Set env vars in `.env.deploy`

The deploy script derives all Caddy registration parameters from your env files:

| Variable | Purpose | Example |
|----------|---------|---------|
| `PUBLIC_DOMAIN` | The domain Caddy should route to this service | `myapp.example.com` |
| `WEB_PORT` | The port inside the container (default `3000`) | `8080` |
| `PORTAINER_STACK_NAME` | Used as the upstream service name | `my-app-production` |
| `EDGE_AUTH_MODE` | Selected route protection mode | `oidc` |
| `AUTH_POLICY` | Authentik group/policy metadata for the route | `protected-container-users` |

```dotenv
# .env.deploy (relevant keys)
PUBLIC_DOMAIN=myapp.example.com
WEB_PORT=8080
PORTAINER_STACK_NAME=my-app-production
EDGE_AUTH_MODE=oidc
AUTH_POLICY=protected-container-users
```

### 3. Deploy

```bash
source .venv/bin/activate
python scripts/deploy/ubuntu_deploy.py
```

The deploy script automatically:

1. Reads the proxy Caddyfile on the remote host via SSH.
2. Checks whether a site block for `PUBLIC_DOMAIN` already exists (idempotent).
3. If missing, appends a site block for the selected `EDGE_AUTH_MODE` plus `reverse_proxy <service>:<port>`.
4. If an existing domain block is present but stale, unprotected, or still Basic-Auth-only while OIDC mode is selected, rewrites it with the selected route contract.
5. Restarts the `central-proxy` container and validates the config.

No manual SSH or Caddyfile editing required.

## Manual fallback (reference)

The steps below are only needed if you are making ad-hoc changes outside the deploy pipeline, or need to debug a Caddy route.

### Edit the Caddyfile directly

On the server, edit the Caddyfile (typically at `~/containers/protected-container/docker/proxy/Caddyfile`):

```caddy
# -------------------------
# My App Route
# -------------------------
myapp.example.com {
    tls {$ACME_EMAIL}
    header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"

    route {
        import protected_auth
        reverse_proxy my-app-production:8080
    }
}
```

Rollback mode still uses Basic Auth:

```caddy
myapp.example.com {
    tls {$ACME_EMAIL}
    header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"

    basic_auth /* {
        {$BASIC_AUTH_USER} {$BASIC_AUTH_HASH}
    }

    reverse_proxy my-app-production:8080
}
```

### Safe verification

```bash
# Unauthenticated requests must be blocked by the selected Caddy edge-auth mode.
curl -I https://myapp.example.com

# Basic Auth rollback mode only: authenticated requests may then reach the app.
curl -I -u "$BASIC_AUTH_USER:<your-known-password>" https://myapp.example.com
```

### Reload Caddy

The Caddyfile is bind-mounted into the container.  After editing the **host** file, restart the container (a simple `caddy reload` will not pick up the new inode):

```bash
docker restart central-proxy
docker exec central-proxy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```
