# Ubuntu Server Deployment Target — protected-container (upstream)

This plan covers the work to be done in this repo (`protected-container`, to be renamed
`protected-container`) to support Ubuntu server as a first-class deployment target alongside
Azure ACI.

Stock-dashboard-specific work is tracked separately in
`stock-dashboard/planning/UBUNTU_SERVER_DEPLOYMENT.md`.

---

## Task Checklist

- [ ] **Phase 0** — Rename repo & review existing docs
- [ ] **Phase 1** — `ubuntu_start.sh` plain entrypoint
- [ ] **Phase 2** — `ubuntu_deploy.py` SSH deploy engine script
- [ ] **Phase 3** — Generic `build_push.sh` local build+push helper
- [ ] **Phase 4** — Multi-app Caddy routing (Caddyfile template)
- [ ] **Phase 5** — Documentation (`docs/deploy/UBUNTU_SERVER.md`)
- [ ] **Phase 6** — Verification

---

## Phase 0 — Rename Repo & Review Existing Docs

### Rename

Rename `protected-container` → `protected-container` on GitHub
(`Settings → General → Repository name`).

GitHub automatically redirects the old URL. Existing submodule references continue to work,
but downstream repos should update their submodule URL at their next update:

```bash
git submodule set-url scripts/deploy/_upstream https://github.com/beejones/protected-container
```

Update all internal references:
- `README.md` — repo name, clone URLs
- `docs/deploy/AZURE_CONTAINER.md` — references to repo name
- `.github/` workflow files — any hardcoded repo references

### Review existing docs

- Read through `docs/deploy/AZURE_CONTAINER.md`, `COMPOSE_CONTRACT.md`, `HOOKS.md` for
  accuracy and anything that mentions "azure" where it should be target-agnostic.
- Check for obsolete planning files in `planning/`.
- Ensure `docker-compose.yml` comments are still correct.

**Exit criteria:** Repo renamed; GitHub redirect working; no stale doc contradictions;
all internal references updated.

---

## Phase 1 — `ubuntu_start.sh` Plain Entrypoint

**File:** `docker/ubuntu_start.sh`

A trimmed-down sibling of `azure_start.sh` — no Azure CLI, no Key Vault. Sources `.env`
and `.env.secrets` from a configurable path on the host (default `/opt/<app>/`), then
hands off to the app command via `exec "$@"`.

```bash
#!/bin/bash
# Ubuntu server startup script for protected container.
# Sources .env and .env.secrets from the host directory, then starts the app.

set -e

ENV_DIR="${ENV_DIR:-/opt/app}"

echo "[ubuntu_start] Starting container..."

for f in "$ENV_DIR/.env" "$ENV_DIR/.env.secrets"; do
    if [ -f "$f" ]; then
        echo "[ubuntu_start] Sourcing $f"
        set -a
        # shellcheck disable=SC1090
        . "$f"
        set +a
    fi
done

echo "[ubuntu_start] Starting application..."
exec "$@"
```

- `ENV_DIR` env var lets downstream apps override the secrets path without changing the script.
- Baked into the Docker image via `Dockerfile` alongside `azure_start.sh`.
- `Dockerfile` entry: `COPY docker/ubuntu_start.sh /usr/local/bin/ubuntu_start.sh`

**Exit criteria:** Container started with `entrypoint: ["ubuntu_start.sh"]` reads `.env`
vars correctly; gracefully skips missing files.

---

## Phase 2 — `ubuntu_deploy.py` SSH Deploy Engine Script

**File:** `scripts/deploy/ubuntu_deploy.py`

The Ubuntu-target parallel to `azure_deploy_container.py`. Reads the repo's
`docker-compose.yml` (same `x-deploy-role` contract) and deploys via SSH.

Steps performed:
1. Parse args: `--host`, `--remote-dir`, `--compose-files`, `--sync-secrets`.
2. (Optional `--sync-secrets`) rsync `.env` + `.env.secrets` to `REMOTE_DIR` via SSH.
3. Rsync `docker/` to `REMOTE_DIR/docker/` on the server.
4. Run on server via SSH:
   ```bash
   docker compose -f <base> -f <ubuntu-override> pull
   docker compose -f <base> -f <ubuntu-override> up -d --remove-orphans
   ```

Downstream repos wrap this with a thin script (same as `azure_deploy_container.py` pattern).

**Exit criteria:** `python scripts/deploy/ubuntu_deploy.py --host user@server` deploys a
working stack; `docker compose ps` shows all services `running`.

---

## Phase 3 — Generic `build_push.sh` Local Build+Push Helper

**File:** `scripts/deploy/build_push.sh`

A simple script for manually pushing a new image to any registry without waiting for CI.
Reads `REGISTRY` and `IMAGE_NAME` from env or `.env.deploy`.

```bash
#!/bin/bash
# Build and push a Docker image to the registry.
# Usage: ./scripts/deploy/build_push.sh [tag]  (default: latest)
#
# Reads from env or .env.deploy:
#   REGISTRY     e.g. ghcr.io
#   IMAGE_NAME   e.g. beejones/my-app
#   DOCKERFILE   e.g. docker/Dockerfile (default)
set -e

[ -f .env.deploy ] && set -a && . .env.deploy && set +a

REGISTRY="${REGISTRY:-ghcr.io}"
IMAGE_NAME="${IMAGE_NAME:?IMAGE_NAME must be set}"
DOCKERFILE="${DOCKERFILE:-docker/Dockerfile}"
TAG="${1:-latest}"
FULL_IMAGE="$REGISTRY/$IMAGE_NAME:$TAG"

echo "[build-push] Building $FULL_IMAGE..."
docker build -f "$DOCKERFILE" -t "$FULL_IMAGE" .

echo "[build-push] Pushing $FULL_IMAGE..."
docker push "$FULL_IMAGE"

echo "[build-push] Done."
```

Requires `docker login $REGISTRY` with a PAT (`write:packages` for GHCR).

**Exit criteria:** `./scripts/deploy/build_push.sh` builds and pushes a correctly tagged
image; image is visible in the registry.

---

## Phase 4 — Multi-App Caddy Routing (Caddyfile Template)

When multiple stacks run on the same Ubuntu server, each needs its own subdomain routed
to its internal port. Update the `docker/caddy/Caddyfile` template to support this pattern.

**Option A — One Caddy per stack (current default):**
Each stack runs its own Caddy. Works out of the box but requires unique host ports per stack
(only one process can bind 80/443). Suitable for a single-app server or if each app uses
a unique external port.

**Option B — Single shared Caddy for the server (recommended for multi-app):**
One Caddy container bound to 80/443, routing to all app containers by hostname. Each app
stack runs without a Caddy sidecar:

```
{$ACME_EMAIL:?required}

dashboard.example.com {
    reverse_proxy stock-dashboard:{$WEB_PORT:-3000}
}

trader.example.com {
    reverse_proxy trader-app:{$TRADER_PORT:-4000}
}
```

Document both options in Phase 5. The compose template stays as-is (Option A default);
Option B is documented as a multi-app override pattern.

**Exit criteria:** Two stacks reachable simultaneously at distinct subdomains over HTTPS;
TLS auto-provisioned by Caddy for both hostnames.

---

## Phase 5 — Documentation (`docs/deploy/UBUNTU_SERVER.md`)

New doc covering:

| Section | Content |
|---|---|
| Architecture | Diagram: Internet → Caddy → container; Portainer for management |
| Prerequisites | Docker + Compose, `systemctl enable docker`, Portainer CE install |
| Auto-start on reboot | How `restart: unless-stopped` + systemd covers all stacks |
| Secrets | SSH-copy `.env` + `.env.secrets`; `ENV_DIR` override |
| First deploy | `ubuntu_deploy.py` + wrapper usage |
| Portainer setup | Registry credential (GHCR PAT), stack creation, webhook config |
| Image updates | `build_push.sh` → CI → Portainer webhook → auto-redeploy flow |
| Multi-app routing | Option A vs Option B Caddy patterns |
| Monitoring | `docker logs`, Portainer log viewer |
| SSH hardening | Key-only auth, Tailscale recommendation, no port 22 open |

**Exit criteria:** A developer unfamiliar with the server can follow the doc end-to-end and
have the app running.

---

## Phase 6 — Verification

### Automated
- `docker compose -f docker-compose.yml -f docker/docker-compose.ubuntu.yml config` exits 0.
- Existing test suite passes unchanged.

### Manual

| Check | Expected |
|---|---|
| `ubuntu_start.sh` sources `.env` | Env vars visible in running container |
| `ubuntu_start.sh` missing files | Graceful skip, no crash |
| `ubuntu_deploy.py --host user@server` | All containers `running` |
| `build_push.sh` | Image appears in GHCR with correct tag |
| Portainer webhook triggered | Stack redeploys with new image |
| Two stacks on same server | Each reachable at its own subdomain via HTTPS |
| Server reboot | All containers back up automatically (`systemctl is-enabled docker` = enabled) |

**Exit criteria:** All checks pass on a fresh Ubuntu 24.04 LTS server.
