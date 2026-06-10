# App Container OIDC Migration

## Principles

- The app container is the reference migration path for other Ubuntu-deployed containers.
- Caddy owns the public edge-auth decision; application containers should not publish public web ports.
- `EDGE_AUTH_MODE=oidc` changes the Caddy route from Basic Auth to the shared Authentik `protected_auth` guard.
- Route registration must be verified before a deploy is considered successful.
- Removing Basic Auth from Caddy is not the same as completing Authentik app/provider configuration.

## Protected Container Use Case

The default protected-container stack is the first app-container migration target. It proves the reusable pattern for downstream app containers that need to move from Caddy Basic Auth to centralized OIDC edge auth.

Before migration, the public route can look like this in the central proxy Caddyfile:

```caddy
protected-container.example.com {
    tls {$ACME_EMAIL}
    encode gzip
    header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"

    basic_auth /* {
        {$BASIC_AUTH_USER} {$BASIC_AUTH_HASH}
    }

    reverse_proxy protected-container:8080
}
```

After migration, the route must import the shared OIDC guard:

```caddy
protected-container.example.com {
    tls {$ACME_EMAIL}
    encode gzip
    header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"

    route {
        import protected_auth
        reverse_proxy protected-container:8080
    }
}
```

The generated route may also use the `{$PUBLIC_DOMAIN}` placeholder. That is valid when the running `central-proxy` container resolves `PUBLIC_DOMAIN` to the app domain and the route imports `protected_auth`.

## Required App-Container Settings

Set these non-secret deploy keys for the app container:

```dotenv
PUBLIC_DOMAIN=protected-container.example.com
PORTAINER_STACK_NAME=protected-container
EDGE_AUTH_MODE=oidc
AUTH_POLICY=protected-container-users
AUTH_PROOF_LEVEL=headers
AUTHENTIK_PUBLIC_DOMAIN=auth.example.com
```

Set these secret deploy keys in the ignored deploy secret file or the chosen secret store:

```dotenv
AUTHENTIK_SECRET_KEY=<generated-secret>
AUTHENTIK_POSTGRESQL__PASSWORD=<generated-password>
```

Do not commit real values. The secret file is synced to the Ubuntu host by the deploy scripts when `--sync-secrets` or `UBUNTU_SYNC_SECRETS=true` is used.

## Compose Requirements

The web-facing app service must be reachable only through the shared `caddy` network:

```yaml
services:
  app:
    container_name: protected-container
    expose:
      - "8080"
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

For another app container, replace `protected-container` with a unique production container or stack name and set `PUBLIC_DOMAIN` to that app's domain. The app port can be declared through `WEB_PORT`, Compose `expose`, Compose `ports`, or an app-service environment value such as `CODE_SERVER_PORT`.

## Deployment Flow

Run the normal Ubuntu deploy path:

```bash
source .venv/bin/activate
python scripts/deploy/ubuntu_deploy.py --prod --sync-secrets
```

For a staged build that is ready to promote:

```bash
source .venv/bin/activate
python scripts/deploy/ubuntu_deploy.py --swap
```

When `EDGE_AUTH_MODE=oidc`, the deploy path:

1. Syncs the app Compose files and env files.
2. Refreshes the central proxy stack with the `oidc` Compose profile.
3. Starts or updates `central-proxy` and the Authentik PostgreSQL, server, and worker services. Depending on Compose project naming, the Authentik containers may appear as names such as `proxy-authentik-server-1`.
4. Rewrites stale Basic-Auth-only Caddy routes for the selected app domain.
5. Verifies the route matches the selected edge-auth mode before treating the deploy as successful.

If Caddy registration cannot be verified, the deploy fails. This is intentional: a successful app update with a stale Basic Auth route is not a valid OIDC migration.

## Verification

On the Ubuntu host, check the route and container state without printing secrets:

```bash
docker ps --format '{{.Names}}\t{{.Status}}' | grep -E '(central-proxy|authentik|protected-container)'
grep -nE 'protected_auth|basic_auth|protected-container|PUBLIC_DOMAIN' ~/containers/protected-container/docker/proxy/Caddyfile
docker exec central-proxy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

From a client, anonymous requests should no longer return a browser Basic Auth challenge:

```bash
curl -k -sS -D - -o /dev/null https://protected-container.example.com | sed -n '1,24p'
```

A successful edge-route migration has no `WWW-Authenticate: Basic` header. If the response is from Authentik, the Caddy route is no longer Basic Auth. A `404` from Authentik means the route reached Authentik but the Authentik provider/application/outpost configuration is not complete yet.

## Downstream Container Checklist

Use this checklist when migrating another container:

- [ ] The app service has no public host port for normal web traffic.
- [ ] The app service joins the external `caddy` network.
- [ ] `PUBLIC_DOMAIN` points to the app's public domain.
- [ ] `PORTAINER_STACK_NAME` or the app container name is unique on the host.
- [ ] `EDGE_AUTH_MODE=oidc` is set for the app deploy.
- [ ] Authentik required secrets are present in ignored secret config or secret storage.
- [ ] The central proxy stack is running the `oidc` profile.
- [ ] The app route imports `protected_auth` and no longer contains a live `basic_auth` directive.
- [ ] Anonymous browser access no longer shows the Basic Auth prompt.
- [ ] Authentik app/provider/outpost configuration exists for the public domain.
- [ ] Approved users can reach the app through the Authentik flow.
- [ ] Spoofed `X-Auth-*` and `X-Authentik-*` headers are stripped before the app sees the request.

## Rollback

Basic Auth remains the rollback mode. Set:

```dotenv
EDGE_AUTH_MODE=basic
```

Then rerun the Ubuntu deploy path. The registration step rewrites the app route back to the Basic Auth guard and verifies the selected route contract.

## Related Docs

- [Shared Caddy Routing](SHARED_CADDY_ROUTING.md)
- [Upstream Auth Contract](UPSTREAM_AUTH_CONTRACT.md)
- [Ubuntu Server Deployment](UBUNTU_SERVER.md)
- [Environment Schema](ENV_SCHEMA.md)