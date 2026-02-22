# Shared Caddy Routing 

This guide explains how other projects deployed on the same Ubuntu server can leverage the centralized Caddy proxy for automatic HTTPS routing without needing to run their own sidecar proxies.

## How it works

The centralized proxy binds to host ports `80` and `443` and handles all SSL certificates. 
Incoming requests are matched by the domain name in the `docker/proxy/Caddyfile` and routed internally via the external `caddy` Docker network to the appropriate container.

## Steps for Downstream Projects

### 1. Join the Global Network

Update your project's `docker-compose.yml` to ensure your web-facing services connect to the external `caddy` network. Do not publish any host ports (`ports:` block) for your web service unless explicitly needed for direct bypass.

```yaml
services:
  app:
    # Do NOT bind host ports here if Caddy is handling routing
    # ports:
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

### 2. Determine a Safe Container Name

Caddy routes to your service via its Docker container name. To prevent routing collisions, force a specific, collision-free container name in your compose file:

```yaml
services:
  app:
    container_name: my-app-production
```

### 3. Add to the Central Caddyfile

On the server, add your reverse proxy block to `/opt/central-proxy/Caddyfile` (or wherever your `docker/proxy/Caddyfile` is mounted).

Use the exact container name (`my-app-production`) and internal exposed port (`8080`).

```caddy
# -------------------------
# My App Route
# -------------------------
myapp.example.com {
    tls {$ACME_EMAIL}
    header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
    
    # Optional: Basic Auth
    # basicauth /* {
    #     admin JDJhJDE0JH...
    # }
    
    reverse_proxy my-app-production:8080
}
```

### 4. Safely Reload Caddy

Whenever you change the `Caddyfile`, validate the configuration and reload the proxy without downtime.

```bash
# 1. Validate the syntax first
docker exec central-proxy caddy validate --config /etc/caddy/Caddyfile

# 2. If valid, reload the configuration
docker exec central-proxy caddy reload --config /etc/caddy/Caddyfile
```
