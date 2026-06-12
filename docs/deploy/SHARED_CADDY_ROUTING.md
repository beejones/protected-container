# Shared Caddy Routing 

## Principles

All public routes registered through the centralized Ubuntu Caddy proxy must inherit the same Caddy access gate before traffic is forwarded to the intended app container. Registration should be deterministic, idempotent, and safe to rerun: missing routes are appended, and stale routes are repaired when they are unprotected or point at the wrong upstream service/port instead of being silently treated as healthy.

This guide explains how other projects deployed on the same Ubuntu server can register with the centralized Caddy proxy for automatic HTTPS routing — without needing their own sidecar proxies.

## How it works

The centralized proxy binds to host ports `80` and `443` and handles all SSL certificates.
Incoming requests are matched by domain name in `docker/proxy/Caddyfile` and routed internally via the external `caddy` Docker network to the appropriate container.

Registration is **fully automated** by the `ubuntu_deploy.py` script.  All you need to do is:

1. Prepare your project's `docker-compose.yml` (network + container name).
2. Set the right env vars in `.env.deploy`.
3. Run `ubuntu_deploy.py` — the proxy Caddyfile is synced, `central-proxy` is recreated so stale routes are dropped, and app routes are registered for you.

The generated site block includes the centralized proxy `basic_auth` guard using the existing `BASIC_AUTH_USER` and `BASIC_AUTH_HASH` placeholders and a `reverse_proxy <service>:<port>` upstream derived from `PORTAINER_STACK_NAME` and `WEB_PORT`. App-specific auth such as session login or API keys remains separate defense-in-depth behind that Caddy boundary.

## Portainer Through Caddy

Portainer is part of the shared Ubuntu control plane and is routed through the same central Caddy proxy. Use `https://portainer.<base-domain>` for the Portainer UI, API, and stack webhooks. Do not expose or target direct host ports `9000` or `9443` for normal deployments.

`ubuntu_deploy.py` derives the Portainer host from `PUBLIC_DOMAIN`. For example, `PUBLIC_DOMAIN=myapp.example.com` resolves Portainer API calls to `https://portainer.example.com` on port `443`. Keep `PORTAINER_HTTPS_PORT=443` unless you have intentionally changed the Caddy HTTPS listener.

Portainer API auth is Portainer-native, not Caddy Basic Auth. Create an access token in the Portainer UI and place the token value in `.env.deploy.secrets`:

```env
PORTAINER_ACCESS_TOKEN=<portainer-api-token>
```

The deploy helpers send that token as Portainer's `X-API-Key` header over the Caddy TLS route. Use this token when deploy automation needs to resolve endpoints, find stacks, create or repair webhooks, stop staging containers, or run swap flows.

If you already have a stack webhook and do not need API lookup, store only the webhook token tail in `.env.deploy.secrets`:

```env
PORTAINER_WEBHOOK_TOKEN=<token-tail-only>
```

The corresponding webhook URL should still point at the Caddy route, for example `https://portainer.example.com/api/stacks/webhooks/<token>`.

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

```dotenv
# .env.deploy (relevant keys)
PUBLIC_DOMAIN=myapp.example.com
WEB_PORT=8080
PORTAINER_STACK_NAME=my-app-production
```

### 3. Deploy

```bash
source .venv/bin/activate
python scripts/deploy/ubuntu_deploy.py
```

The deploy script automatically:

1. Syncs the repo-owned proxy files to the remote host.
2. Recreates `central-proxy` so Caddy mounts the latest Caddyfile and drops stale routes from earlier experiments.
3. Reads the proxy Caddyfile on the remote host via SSH.
4. Checks whether a literal site block for `PUBLIC_DOMAIN`, or a matching `{$PUBLIC_DOMAIN}` placeholder block, already exists with both `basic_auth` and the expected `reverse_proxy <service>:<port>` upstream.
5. If missing, appends a protected site block with `basic_auth` plus `reverse_proxy <service>:<port>`.
6. If an existing domain or placeholder block is unprotected or points at a stale upstream, rewrites it with the standard `basic_auth` guard and expected upstream.
7. Restarts the `central-proxy` container and validates the config after route changes.

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

  basic_auth /* {
    {$BASIC_AUTH_USER} {$BASIC_AUTH_HASH}
  }

    reverse_proxy my-app-production:8080
}
```

### Safe verification

```bash
# Unauthenticated requests must be blocked by Caddy.
curl -I https://myapp.example.com

# Authenticated requests may then reach the app, which can still apply its own login/API auth.
curl -I -u "$BASIC_AUTH_USER:<your-known-password>" https://myapp.example.com
```

### Reload Caddy

The Caddyfile is bind-mounted into the container.  After editing the **host** file, restart the container (a simple `caddy reload` will not pick up the new inode):

```bash
docker restart central-proxy
docker exec central-proxy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```
