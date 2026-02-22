#!/usr/bin/env bash
set -euo pipefail

# Find repo root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

echo "[proxy-deploy] 🔍 Loading environment variables..."
set -a
[ -f .env ] && source .env || true
[ -f .env.secrets ] && source .env.secrets || true
[ -f .env.deploy ] && source .env.deploy || true
[ -f .env.deploy.secrets ] && source .env.deploy.secrets || true
set +a

if [ -z "${UBUNTU_SSH_HOST:-}" ]; then
  echo "[proxy-deploy] ❌ Error: UBUNTU_SSH_HOST is not set in .env.deploy"
  exit 1
fi

if [ -z "${ACME_EMAIL:-}" ]; then
  echo "[proxy-deploy] ❌ Error: ACME_EMAIL is not set in .env or .env.secrets"
  exit 1
fi

if [ -z "${PUBLIC_DOMAIN:-}" ]; then
  echo "[proxy-deploy] ❌ Error: PUBLIC_DOMAIN is not set in .env or .env.deploy"
  exit 1
fi

DEFAULT_PROXY_BASE="${UBUNTU_REMOTE_DIR:-~/containers/protected-container}"
PROXY_DIR="${UBUNTU_PROXY_DIR:-${DEFAULT_PROXY_BASE}/docker/proxy}"

echo "[proxy-deploy] 🚀 Deploying Central Caddy Proxy to ${UBUNTU_SSH_HOST}..."

echo "[proxy-deploy] 📦 Syncing proxy configuration to ${PROXY_DIR}..."
# Create directory in user's home folder (no sudo required)
ssh "${UBUNTU_SSH_HOST}" "mkdir -p ${PROXY_DIR}"
rsync -avz docker/proxy/ "${UBUNTU_SSH_HOST}:${PROXY_DIR}/"

echo "[proxy-deploy] 🌐 Ensuring external 'caddy' network exists..."
ssh "${UBUNTU_SSH_HOST}" "docker network inspect caddy >/dev/null 2>&1 || docker network create caddy"

echo "[proxy-deploy] 🟢 Starting proxy on remote host..."
# We explicitly pass the environment variables inline to docker compose to ensure they are available
ssh "${UBUNTU_SSH_HOST}" "
  cd ${PROXY_DIR}
  export ACME_EMAIL='${ACME_EMAIL}'
  export PUBLIC_DOMAIN='${PUBLIC_DOMAIN}'
  docker compose up -d
"

echo "[proxy-deploy] ✅ Central Caddy Proxy deployed successfully."
