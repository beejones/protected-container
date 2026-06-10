#!/usr/bin/env bash
set -euo pipefail

# Find repo root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

echo "[proxy-deploy] 🔍 Loading environment variables..."
raw_basic_auth_hash=""
if [ -f .env.secrets ]; then
  raw_basic_auth_hash="$(grep -E '^BASIC_AUTH_HASH=' .env.secrets | tail -n1 | cut -d= -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
fi
if [[ "${raw_basic_auth_hash}" == \$2* ]]; then
  echo "[proxy-deploy] ❌ Error: BASIC_AUTH_HASH in .env.secrets must be wrapped in single quotes for Ubuntu/Portainer deploys." >&2
  echo "[proxy-deploy]    Use: BASIC_AUTH_HASH='\$2a\$14\$...'" >&2
  echo "[proxy-deploy]    Raw bcrypt hashes are truncated by Docker Compose/shell interpolation before Caddy sees them." >&2
  exit 1
fi

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

EDGE_AUTH_MODE_LOWER="$(printf '%s' "${EDGE_AUTH_MODE:-basic}" | tr '[:upper:]' '[:lower:]')"
COMPOSE_PROFILE_ARGS=""
if [ "${EDGE_AUTH_MODE_LOWER}" = "oidc" ]; then
  for required_key in AUTHENTIK_PUBLIC_DOMAIN AUTHENTIK_SECRET_KEY AUTHENTIK_POSTGRESQL__PASSWORD; do
    if [ -z "${!required_key:-}" ]; then
      echo "[proxy-deploy] ❌ Error: ${required_key} is required when EDGE_AUTH_MODE=oidc" >&2
      exit 1
    fi
  done
  COMPOSE_PROFILE_ARGS="--profile oidc"
fi

DEFAULT_PROXY_BASE="${UBUNTU_REMOTE_DIR:-~/containers/protected-container}"
PROXY_DIR="${UBUNTU_PROXY_DIR:-${DEFAULT_PROXY_BASE}/docker/proxy}"
REMOTE_ENV_DIR="$(dirname "$(dirname "${PROXY_DIR}")")"

echo "[proxy-deploy] 🚀 Deploying Central Caddy Proxy to ${UBUNTU_SSH_HOST}..."

echo "[proxy-deploy] 📦 Syncing proxy configuration to ${PROXY_DIR}..."
# Create directory in user's home folder (no sudo required)
ssh "${UBUNTU_SSH_HOST}" "mkdir -p ${PROXY_DIR}"
rsync -avz docker/proxy/ "${UBUNTU_SSH_HOST}:${PROXY_DIR}/"

env_paths=()
for env_file in .env .env.secrets .env.deploy .env.deploy.secrets; do
  if [ -f "${env_file}" ]; then
    env_paths+=("${env_file}")
  fi
done
if [ "${#env_paths[@]}" -gt 0 ]; then
  echo "[proxy-deploy] 🔐 Syncing proxy environment files to ${REMOTE_ENV_DIR}..."
  ssh "${UBUNTU_SSH_HOST}" "mkdir -p ${REMOTE_ENV_DIR}"
  rsync -avz "${env_paths[@]}" "${UBUNTU_SSH_HOST}:${REMOTE_ENV_DIR}/"
fi

echo "[proxy-deploy] 🌐 Ensuring external 'caddy' network exists..."
ssh "${UBUNTU_SSH_HOST}" "docker network inspect caddy >/dev/null 2>&1 || docker network create caddy"

echo "[proxy-deploy] 🟢 Starting proxy on remote host..."
# We explicitly pass the environment variables inline to docker compose to ensure they are available
ssh "${UBUNTU_SSH_HOST}" "
  cd ${PROXY_DIR}
  set -a
  [ -f ../../.env ] && . ../../.env || true
  [ -f ../../.env.secrets ] && . ../../.env.secrets || true
  [ -f ../../.env.deploy ] && . ../../.env.deploy || true
  [ -f ../../.env.deploy.secrets ] && . ../../.env.deploy.secrets || true
  set +a
  if docker compose version >/dev/null 2>&1; then
    docker compose ${COMPOSE_PROFILE_ARGS} up -d
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose ${COMPOSE_PROFILE_ARGS} up -d
  else
    echo '[proxy-deploy] ❌ Error: Docker Compose is not installed on the remote host. Install docker-compose-v2 or docker-compose and retry.' >&2
    exit 1
  fi
"

echo "[proxy-deploy] ✅ Central Caddy Proxy deployed successfully."
