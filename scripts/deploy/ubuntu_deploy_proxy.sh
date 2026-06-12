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
TMP_BASE="${TMPDIR:-${REPO_ROOT}/out/tmp}"
mkdir -p "${TMP_BASE}"
PRESERVE_TMP_DIR="$(mktemp -d "${TMP_BASE}/caddy-proxy.XXXXXX")"
cleanup_preserve_tmp() {
  rm -rf "${PRESERVE_TMP_DIR}"
}
trap cleanup_preserve_tmp EXIT

preserve_caddy_routes() {
  local existing_caddyfile="$1"
  local incoming_caddyfile="$2"
  local output_caddyfile="$3"

  if [ -f scripts/deploy/preserve_caddy_routes.py ]; then
    "${PYTHON_BIN:-python3}" scripts/deploy/preserve_caddy_routes.py \
      --existing "${existing_caddyfile}" \
      --incoming "${incoming_caddyfile}" \
      --output "${output_caddyfile}"
    return
  fi

  "${PYTHON_BIN:-python3}" - "${existing_caddyfile}" "${incoming_caddyfile}" "${output_caddyfile}" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path


SITE_HEADER_RE = re.compile(r"^(?!\s*#)\s*(?P<label>[^\s{]+)\s*\{\s*$")


def find_site_blocks(caddyfile_text: str) -> list[tuple[str, str]]:
    lines = caddyfile_text.splitlines(keepends=True)
    blocks: list[tuple[str, str]] = []
    line_index = 0

    while line_index < len(lines):
        line = lines[line_index]
        stripped_line = line.strip()
        match = SITE_HEADER_RE.match(line.rstrip("\r\n"))
        if match is None or stripped_line.startswith(("{", ":")):
            line_index += 1
            continue

        start_index = line_index
        depth = 1
        line_index += 1
        while line_index < len(lines) and depth > 0:
            current_line = lines[line_index].strip()
            if current_line.endswith("{") and not current_line.startswith("#"):
                depth += 1
            if current_line == "}":
                depth -= 1
            line_index += 1

        blocks.append((match.group("label"), "".join(lines[start_index:line_index])))

    return blocks


def preserve_shared_routes(existing_text: str, incoming_text: str) -> str:
    incoming_labels = {label for label, _block_text in find_site_blocks(incoming_text)}
    preserved_blocks = [
        block_text
        for label, block_text in find_site_blocks(existing_text)
        if label not in incoming_labels
    ]
    if not preserved_blocks:
        return incoming_text

    incoming = incoming_text.rstrip() + "\n"
    preserved_text = "\n".join(block_text.strip() for block_text in preserved_blocks)
    return f"{incoming}\n# -------------------------\n# Preserved Shared Routes\n# -------------------------\n{preserved_text}\n"


existing_path = Path(sys.argv[1])
incoming_path = Path(sys.argv[2])
output_path = Path(sys.argv[3])
existing_text = existing_path.read_text(encoding="utf-8") if existing_path.exists() else ""
incoming_text = incoming_path.read_text(encoding="utf-8")
output_path.write_text(
    preserve_shared_routes(existing_text=existing_text, incoming_text=incoming_text),
    encoding="utf-8",
)
PY
}

REMOTE_CADDYFILE="${PRESERVE_TMP_DIR}/Caddyfile.remote"
STAGED_PROXY_DIR="${PRESERVE_TMP_DIR}/proxy"
if ssh "${UBUNTU_SSH_HOST}" "test -f ${PROXY_DIR}/Caddyfile"; then
  echo "[proxy-deploy] 🧩 Preserving existing shared Caddy routes..."
  ssh "${UBUNTU_SSH_HOST}" "cat ${PROXY_DIR}/Caddyfile" > "${REMOTE_CADDYFILE}"
else
  : > "${REMOTE_CADDYFILE}"
fi

rsync -a docker/proxy/ "${STAGED_PROXY_DIR}/"
preserve_caddy_routes "${REMOTE_CADDYFILE}" docker/proxy/Caddyfile "${STAGED_PROXY_DIR}/Caddyfile"
rsync -avz "${STAGED_PROXY_DIR}/" "${UBUNTU_SSH_HOST}:${PROXY_DIR}/"

echo "[proxy-deploy] 🌐 Ensuring external 'caddy' network exists..."
ssh "${UBUNTU_SSH_HOST}" "docker network inspect caddy >/dev/null 2>&1 || docker network create caddy"

echo "[proxy-deploy] 🟢 Starting proxy on remote host..."
# We explicitly pass the environment variables inline to docker compose to ensure they are available
ssh "${UBUNTU_SSH_HOST}" "
  cd ${PROXY_DIR}
  export ACME_EMAIL='${ACME_EMAIL}'
  export PUBLIC_DOMAIN='${PUBLIC_DOMAIN}'
  if docker compose version >/dev/null 2>&1; then
    docker compose up -d --force-recreate --remove-orphans
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose up -d --force-recreate --remove-orphans
  else
    echo '[proxy-deploy] ❌ Error: Docker Compose is not installed on the remote host. Install docker-compose-v2 or docker-compose and retry.' >&2
    exit 1
  fi
  docker exec central-proxy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
"

echo "[proxy-deploy] ✅ Central Caddy Proxy deployed successfully."
