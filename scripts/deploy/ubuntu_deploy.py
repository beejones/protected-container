#!/usr/bin/env python3
"""Deploy this repo to an Ubuntu server over SSH.

This is the Ubuntu-target parallel to `azure_deploy_container.py`.

It does NOT require Azure CLI or Key Vault. It syncs deployment files to the
remote host, ensures Portainer is running, and triggers a Portainer stack
webhook for deployment.

Security note: this script shells out to `ssh` and `rsync`.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import dotenv_values
import sys
import urllib3
import yaml

sys.path.append(str(Path(__file__).parent))

import caddy_register
import deploy_hooks
import deploy_log
import portainer_helpers


ENV_PUBLIC_DOMAIN = "PUBLIC_DOMAIN"
ENV_WEB_PORT = "WEB_PORT"
ENV_APP_IMAGE = "APP_IMAGE"
ENV_STORAGE_MANAGER_IMAGE = "STORAGE_MANAGER_IMAGE"
ENV_DOCKERFILE = "DOCKERFILE"
ENV_STORAGE_MANAGER_DOCKERFILE = "STORAGE_MANAGER_DOCKERFILE"
ENV_GHCR_USERNAME = "GHCR_USERNAME"
ENV_GHCR_TOKEN = "GHCR_TOKEN"
ENV_UBUNTU_SSH_HOST = "UBUNTU_SSH_HOST"
ENV_UBUNTU_REMOTE_DIR = "UBUNTU_REMOTE_DIR"
ENV_UBUNTU_COMPOSE_FILES = "UBUNTU_COMPOSE_FILES"
ENV_UBUNTU_BUILD_PUSH = "UBUNTU_BUILD_PUSH"
ENV_UBUNTU_SYNC_SECRETS = "UBUNTU_SYNC_SECRETS"
ENV_PORTAINER_HTTPS_PORT = "PORTAINER_HTTPS_PORT"
ENV_PORTAINER_WEBHOOK_INSECURE = "PORTAINER_WEBHOOK_INSECURE"
ENV_PORTAINER_WEBHOOK_URL = "PORTAINER_WEBHOOK_URL"
ENV_PORTAINER_WEBHOOK_TOKEN = "PORTAINER_WEBHOOK_TOKEN"
ENV_PORTAINER_ACCESS_TOKEN = "PORTAINER_ACCESS_TOKEN"
ENV_PORTAINER_STACK_NAME = "PORTAINER_STACK_NAME"
ENV_PORTAINER_ENDPOINT_ID = "PORTAINER_ENDPOINT_ID"
ENV_CADDY_PROXY_DIR = "CADDY_PROXY_DIR"
ENV_STORAGE_MANAGER_API_URL = "STORAGE_MANAGER_API_URL"
ENV_DEPLOY_HOOKS_MODULE = "DEPLOY_HOOKS_MODULE"
ENV_DEPLOY_HOOKS_SOFT_FAIL = "DEPLOY_HOOKS_SOFT_FAIL"
ENV_STAGING_PUBLIC_DOMAIN = "STAGING_PUBLIC_DOMAIN"
ENV_STAGING_REMOTE_DIR = "STAGING_REMOTE_DIR"
ENV_STAGING_PORTAINER_STACK_NAME = "STAGING_PORTAINER_STACK_NAME"


_STORAGE_MANAGER_LABEL_PATTERN = re.compile(r"^storage-manager\.(\d+)\.(.+)$")


def _subprocess_error_text(exc: subprocess.CalledProcessError) -> str:
    stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else str(exc.stderr or "")
    stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or "")
    text = (stderr.strip() or stdout.strip() or "").strip()
    return text


def _ssh_failure_hint(error_text: str) -> str:
    lowered = error_text.lower()
    if "no route to host" in lowered:
        return "No route to host. Check VPN/LAN reachability and UBUNTU_SSH_HOST."
    if "connection timed out" in lowered:
        return "SSH timed out. Verify the server is online and port 22 is reachable."
    if "connection refused" in lowered:
        return "SSH connection refused. Confirm SSH daemon is running and port 22 is open."
    if "permission denied" in lowered:
        return "SSH authentication failed. Verify SSH key access for the configured user."
    if "could not resolve hostname" in lowered:
        return "Host resolution failed. Check UBUNTU_SSH_HOST for typos/DNS issues."
    return ""


def _run(cmd: list[str], *, check: bool = True, action: str | None = None) -> None:
    try:
        subprocess.run(cmd, check=check)
    except subprocess.CalledProcessError as exc:
        action_text = action or f"Command failed: {' '.join(cmd)}"
        detail = _subprocess_error_text(exc)
        message = f"{action_text} (exit code {exc.returncode})."
        if detail:
            message = f"{message} {detail}"
        if cmd and cmd[0] == "ssh":
            hint = _ssh_failure_hint(detail)
            if hint:
                message = f"{message} {hint}"
        raise SystemExit(message)


def build_rsync_cmd(*, sources: list[Path], host: str, remote_dir: Path) -> list[str]:
    srcs = [str(p) for p in sources]
    # Trailing slash on remote_dir ensures rsync copies into the dir.
    dest = f"{host}:{str(remote_dir)}/"
    return ["rsync", "-az", "--mkpath", *srcs, dest]


def build_ssh_cmd(*, host: str, remote_command: str) -> list[str]:
    return ["ssh", host, remote_command]


def build_ssh_connectivity_cmd(*, host: str) -> list[str]:
    return build_ssh_cmd(host=host, remote_command="echo SSH_OK")


def resolve_network_host_from_ssh_target(host: str) -> str:
    raw_host = str(host).strip()
    if not raw_host:
        return ""

    fallback_host = portainer_helpers.extract_ssh_hostname(raw_host).strip()
    try:
        result = subprocess.run(["ssh", "-G", raw_host], check=False, capture_output=True, text=True)
    except OSError:
        return fallback_host

    if result.returncode != 0:
        return fallback_host

    for line in str(result.stdout or "").splitlines():
        if not line.startswith("hostname "):
            continue
        resolved_host = line.split(None, 1)[1].strip()
        if resolved_host:
            return resolved_host

    return fallback_host


def _hostname_from_urlish(value: str) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""

    if "://" in raw_value:
        parsed = urlparse(raw_value)
        raw_value = parsed.hostname or raw_value

    raw_value = raw_value.split("/", 1)[0]
    if "@" in raw_value:
        raw_value = raw_value.rsplit("@", 1)[1]
    if raw_value.count(":") == 1:
        raw_value = raw_value.split(":", 1)[0]
    return raw_value.strip().strip("[]")


def _is_ipv4_host(host: str) -> bool:
    parts = host.split(".")
    return len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts)


def derive_portainer_host_from_public_domain(public_domain: str) -> str:
    hostname = _hostname_from_urlish(public_domain).lower()
    if not hostname or hostname == "localhost" or _is_ipv4_host(hostname):
        return ""

    labels = [label for label in hostname.split(".") if label]
    if len(labels) < 2:
        return ""
    if labels[0] == "portainer":
        return hostname
    if len(labels) == 2:
        return f"portainer.{hostname}"
    return "portainer." + ".".join(labels[1:])


def resolve_portainer_api_host(*, repo_root: Path, ssh_host: str) -> str:
    public_domain = str(os.getenv(ENV_PUBLIC_DOMAIN) or "").strip()
    if not public_domain:
        public_domain = read_deploy_key(repo_root=repo_root, key=ENV_PUBLIC_DOMAIN)

    derived_portainer_host = derive_portainer_host_from_public_domain(public_domain)
    if derived_portainer_host:
        return derived_portainer_host

    return resolve_network_host_from_ssh_target(ssh_host)


def default_portainer_https_port(*, portainer_host: str, ssh_host: str) -> int:
    portainer_hostname = _hostname_from_urlish(portainer_host)
    ssh_hostname = _hostname_from_urlish(portainer_helpers.extract_ssh_hostname(ssh_host))
    if portainer_hostname and ssh_hostname and portainer_hostname != ssh_hostname:
        return 443
    return 9943


def resolve_deploy_target(*, prod: bool, swap: bool) -> str:
    if prod or swap:
        return "production"
    return "staging"


def build_docker_build_cmd(*, app_image: str, dockerfile: str, context_dir: str) -> list[str]:
    return ["docker", "build", "-f", dockerfile, "-t", app_image, context_dir]


def build_docker_push_cmd(*, app_image: str) -> list[str]:
    return ["docker", "push", app_image]


def build_compose_config_cmd(*, compose_files: list[str]) -> list[str]:
    cmd = ["docker", "compose"]
    for compose_file in compose_files:
        cmd.extend(["-f", compose_file])
    cmd.append("config")
    return cmd


def build_remote_compose_deploy_cmd(*, remote_dir: Path, compose_files: list[str]) -> str:
    quoted_remote_dir = shlex.quote(str(remote_dir))
    compose_args = " ".join(f"-f {shlex.quote(str(compose_file))}" for compose_file in compose_files)
    return (
        f"cd {quoted_remote_dir} && "
        f"export ENV_DIR={quoted_remote_dir} && "
        "if docker compose version >/dev/null 2>&1; then "
        f"docker compose {compose_args} pull && docker compose {compose_args} up -d --remove-orphans; "
        "elif command -v docker-compose >/dev/null 2>&1; then "
        f"docker-compose {compose_args} pull && docker-compose {compose_args} up -d --remove-orphans; "
        "else "
        "echo '[ubuntu-deploy] Docker Compose is not installed on the remote host. Install docker-compose-v2 or docker-compose and retry.' >&2; "
        "exit 1; "
        "fi"
    )


def _should_fallback_to_remote_compose(error_text: str) -> bool:
    lowered = str(error_text).lower()
    return "administrator initialization timeout" in lowered


def render_compose_stack_content(*, repo_root: Path, compose_files: list[str]) -> str:
    cmd = build_compose_config_cmd(compose_files=compose_files)
    result = subprocess.run(cmd, cwd=str(repo_root), check=False, capture_output=True, text=True)
    if result.returncode != 0:
        err = str(result.stderr or "").strip() or str(result.stdout or "").strip()
        raise SystemExit(f"Failed to render compose config for Portainer stack creation: {err}")
    content = str(result.stdout or "").strip()
    if not content:
        raise SystemExit("Failed to render compose config for Portainer stack creation: empty output")
    return content


def rewrite_rendered_paths_for_remote(*, stack_content: str, local_repo_root: Path, remote_dir: Path) -> str:
    local_root = str(local_repo_root.resolve())
    remote_root = str(remote_dir)
    return stack_content.replace(local_root, remote_root)


def prepare_stack_content_for_portainer(*, stack_content: str, app_image: str) -> str:
    payload = yaml.safe_load(stack_content)
    if not isinstance(payload, dict):
        raise SystemExit("Rendered compose config is not a valid mapping")

    services = payload.get("services")
    if not isinstance(services, dict):
        return stack_content

    remaining_build_services: list[str] = []
    app_image_value = app_image.strip()

    for service_name, service_payload in services.items():
        if not isinstance(service_payload, dict):
            continue
        if "build" not in service_payload:
            continue

        if service_name == "app" and app_image_value:
            service_payload.pop("build", None)
            service_payload["image"] = app_image_value
            continue

        remaining_build_services.append(str(service_name))

    if remaining_build_services:
        raise SystemExit(
            "Portainer stack creation requires image-based services. "
            f"These services still use build contexts: {remaining_build_services}. "
            "Set APP_IMAGE and/or adjust compose files for image-based deployment."
        )

    return yaml.safe_dump(payload, sort_keys=False)


def rewrite_staging_container_names_for_portainer(*, stack_content: str, stack_name: str) -> str:
    """Rewrite explicit container_name values so a staging stack can coexist with production."""
    payload = yaml.safe_load(stack_content)
    if not isinstance(payload, dict):
        raise SystemExit("Rendered compose config is not a valid mapping")

    services = payload.get("services")
    if not isinstance(services, dict):
        return stack_content

    resolved_stack_name = stack_name.strip()
    if not resolved_stack_name:
        return stack_content

    for service_name, service_payload in services.items():
        if not isinstance(service_payload, dict):
            continue
        existing_name = str(service_payload.get("container_name") or "").strip()
        if not existing_name:
            continue
        deploy_role = str(service_payload.get("x-deploy-role") or "").strip()
        if service_name == "app" or deploy_role == "app":
            service_payload["container_name"] = resolved_stack_name
        else:
            service_payload["container_name"] = f"{resolved_stack_name}-{service_name}"

    return yaml.safe_dump(payload, sort_keys=False)


def extract_stack_images(*, stack_content: str) -> list[str]:
    payload = yaml.safe_load(stack_content)
    if not isinstance(payload, dict):
        return []

    services = payload.get("services")
    if not isinstance(services, dict):
        return []

    images: list[str] = []
    for service_payload in services.values():
        if not isinstance(service_payload, dict):
            continue
        image = str(service_payload.get("image") or "").strip()
        if image:
            images.append(image)
    return images


def ghcr_images_from_stack(*, stack_content: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for image in extract_stack_images(stack_content=stack_content):
        if not image.startswith("ghcr.io/"):
            continue
        if image in seen:
            continue
        seen.add(image)
        out.append(image)
    return out


def stack_has_service(*, stack_content: str, service_name: str) -> bool:
    payload = yaml.safe_load(stack_content)
    if not isinstance(payload, dict):
        return False

    services = payload.get("services")
    if not isinstance(services, dict):
        return False

    return service_name in services




def portainer_ensure_running_remote_cmd(*, https_port: int) -> str:
    return (
        "if docker ps --format '{{.Names}}' | grep -Fxq portainer; then "
        "echo '[ubuntu-deploy] Portainer already running'; "
        "elif docker ps -a --format '{{.Names}}' | grep -Fxq portainer; then "
        "echo '[ubuntu-deploy] Starting existing Portainer container'; "
        "docker start portainer >/dev/null; "
        "else "
        "echo '[ubuntu-deploy] Creating Portainer container'; "
        "docker volume create portainer_data >/dev/null && "
        f"docker run -d --name portainer --restart=unless-stopped -p 8000:8000 -p {https_port}:9443 "
        "-v /var/run/docker.sock:/var/run/docker.sock -v portainer_data:/data "
        "portainer/portainer-ce:latest >/dev/null; "
        "fi"
    )


def ghcr_login_pull_remote_cmd(*, image: str, username: str, token: str) -> str:
    return (
        f"printf %s {shlex.quote(token)} | docker login ghcr.io -u {shlex.quote(username)} --password-stdin >/dev/null "
        f"&& docker pull {shlex.quote(image)} >/dev/null"
    )


def docker_login_local(*, registry: str, username: str, token: str) -> None:
    subprocess.run(
        ["docker", "login", registry, "-u", username, "--password-stdin"],
        input=token,
        text=True,
        check=True,
    )


def build_and_push_local_image(*, repo_root: Path, app_image: str, dockerfile: str, allow_missing_dockerfile: bool = False) -> bool:
    dockerfile_path = repo_root / dockerfile
    if not dockerfile_path.exists():
        if allow_missing_dockerfile:
            return False
        raise SystemExit(f"Dockerfile not found for build/push: {dockerfile_path}")
    context_dir = str(Path(dockerfile).parent)
    if context_dir == "":
        context_dir = "."
    build_cmd = build_docker_build_cmd(app_image=app_image, dockerfile=dockerfile, context_dir=context_dir)
    push_cmd = build_docker_push_cmd(app_image=app_image)
    subprocess.run(build_cmd, cwd=str(repo_root), check=True)
    subprocess.run(push_cmd, cwd=str(repo_root), check=True)
    return True




def read_dotenv_key(*, dotenv_path: Path, key: str) -> str:
    if not dotenv_path.exists():
        return ""
    raw = dotenv_values(dotenv_path)
    return str(raw.get(key) or "").strip()


def read_deploy_key(*, repo_root: Path, key: str) -> str:
    return read_dotenv_key(dotenv_path=repo_root / ".env.deploy", key=key)


def read_deploy_secret_key(*, repo_root: Path, key: str) -> str:
    return read_dotenv_key(dotenv_path=repo_root / ".env.deploy.secrets", key=key)


def parse_boolish(value: str, *, default: bool = False) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return default
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _normalize_compose_labels(labels: Any) -> dict[str, str]:
    if isinstance(labels, dict):
        return {str(k): str(v) for k, v in labels.items()}

    out: dict[str, str] = {}
    if isinstance(labels, list):
        for item in labels:
            text = str(item or "")
            if "=" not in text:
                continue
            key, value = text.split("=", 1)
            out[str(key).strip()] = str(value).strip()
    return out


def _coerce_label_value(value: Any) -> Any:
    """Coerce compose label values into scalar Python types.

    Values are parsed with ``yaml.safe_load`` to support convenient label syntax
    such as ``"14" -> 14`` and ``"true" -> True`` for algorithm params.
    Non-scalar YAML values fall back to the original string input.
    """
    if not isinstance(value, str):
        return value
    parsed = yaml.safe_load(value)
    if isinstance(parsed, (str, int, float, bool)) or parsed is None:
        return parsed
    return value


def collect_storage_manager_registrations(*, stack_content: str) -> list[dict[str, Any]]:
    payload = yaml.safe_load(stack_content)
    if not isinstance(payload, dict):
        return []

    services = payload.get("services")
    if not isinstance(services, dict):
        return []

    registrations_by_service: list[tuple[str, int, dict[str, Any]]] = []

    for service_name, service_payload in services.items():
        if not isinstance(service_payload, dict):
            continue

        normalized_labels = _normalize_compose_labels(service_payload.get("labels"))
        buckets: dict[int, dict[str, Any]] = {}

        for label_key, label_value in normalized_labels.items():
            match = _STORAGE_MANAGER_LABEL_PATTERN.match(label_key)
            if not match:
                continue

            index = int(match.group(1))
            key = str(match.group(2)).strip()
            if not key:
                continue

            if index not in buckets:
                buckets[index] = {}

            buckets[index][key] = _coerce_label_value(label_value)

        for index, values in buckets.items():
            required = ["volume", "path", "algorithm"]
            missing = [field for field in required if not values.get(field)]
            if missing:
                missing_fields = ", ".join(missing)
                raise SystemExit(
                    "Invalid storage-manager label registration in service "
                    f"'{service_name}' index {index}: missing required fields: {missing_fields}"
                )

            params = {
                key: value
                for key, value in values.items()
                if key not in {"volume", "path", "algorithm", "description"}
            }

            registration: dict[str, Any] = {
                "volume_name": str(values["volume"]),
                "path": str(values["path"]),
                "algorithm": str(values["algorithm"]),
                "params": params,
                "source_service": str(service_name),
                "source_index": index,
            }
            if values.get("description") is not None:
                registration["description"] = str(values["description"])

            registrations_by_service.append((str(service_name), index, registration))

    registrations_by_service.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in registrations_by_service]


def _storage_manager_register_url(api_url: str) -> str:
    base = str(api_url or "").strip().rstrip("/")
    if base.endswith("/api/register"):
        return base
    return f"{base}/api/register"


def register_storage_manager_registrations(
    *,
    api_url: str,
    registrations: list[dict[str, Any]],
    timeout_seconds: int = 10,
) -> None:
    endpoint = _storage_manager_register_url(api_url)

    for item in registrations:
        payload: dict[str, Any] = {
            "volume_name": item["volume_name"],
            "path": item["path"],
            "algorithm": item["algorithm"],
            "params": item.get("params") or {},
        }
        if item.get("description"):
            payload["description"] = item["description"]

        response = requests.post(endpoint, json=payload, timeout=timeout_seconds)
        if response.status_code < 200 or response.status_code >= 300:
            detail = str(response.text or "").strip()
            source_service = str(item.get("source_service") or "unknown")
            source_index = str(item.get("source_index") or "?")
            raise SystemExit(
                f"Storage registration failed for {source_service}[{source_index}] via {endpoint}: "
                f"HTTP {response.status_code} {detail}"
            )


def _build_ubuntu_deploy_hook_plan(
    *,
    stack_name: str,
    public_domain: str,
    app_image: str,
    web_port: str,
    compose_files: list[str],
    storage_manager_api_url: str,
    storage_registrations: list[dict[str, Any]],
) -> deploy_hooks.DeployPlan:
    parsed_web_port = int(str(web_port or "3000"))
    return deploy_hooks.DeployPlan(
        name=stack_name,
        location="ubuntu",
        dns_label=public_domain,
        deploy_mode="ubuntu",
        compose_service_name="app",
        deploy_role="app",
        app_image=app_image,
        caddy_image="",
        other_image=None,
        app_cpu=0.0,
        app_memory=0.0,
        caddy_cpu=0.0,
        caddy_memory=0.0,
        other_cpu=0.0,
        other_memory=0.0,
        public_domain=public_domain,
        app_port=parsed_web_port,
        app_ports=[parsed_web_port],
        web_command=None,
        extra_env={},
        service_mode="app",
        ftp_passive_range=None,
        extra_metadata={
            "compose_files": list(compose_files),
            "storage_manager_api_url": storage_manager_api_url,
            "storage_registrations": list(storage_registrations),
            "enable_default_storage_registration": True,
        },
    )


def main(argv: list[str] | None = None, repo_root_override: Path | None = None) -> None:
    parser = argparse.ArgumentParser(description="Deploy to Ubuntu server via Portainer stack webhook")
    parser.add_argument(
        "--host",
        default=None,
        help="SSH target in the form user@host. Resolution: CLI -> UBUNTU_SSH_HOST env var -> .env.deploy",
    )
    parser.add_argument(
        "--remote-dir",
        default=None,
        help=(
            "Remote directory to sync files into. "
            "Resolution: CLI --remote-dir -> UBUNTU_REMOTE_DIR env var -> .env.deploy -> /opt/protected-container"
        ),
    )
    parser.add_argument(
        "--compose-files",
        default=None,
        help=(
            "Comma-separated compose files relative to repo root. "
            "Resolution: CLI -> UBUNTU_COMPOSE_FILES env var -> .env.deploy -> built-in default"
        ),
    )
    parser.add_argument(
        "--sync-secrets",
        action="store_true",
        help="Sync .env and .env.secrets to the remote dir before triggering Portainer stack deploy (overrides UBUNTU_SYNC_SECRETS)",
    )
    parser.add_argument(
        "--portainer-webhook-url",
        default=None,
        help=(
            "Portainer stack webhook URL. "
            "Resolution: CLI -> PORTAINER_WEBHOOK_URL env var -> .env.deploy.secrets/.env.deploy"
        ),
    )
    parser.add_argument(
        "--portainer-webhook-token",
        default=None,
        help=(
            "Portainer stack webhook token (last URL segment). "
            "Resolution order: CLI flag -> PORTAINER_WEBHOOK_TOKEN env var -> .env.deploy.secrets"
        ),
    )
    parser.add_argument(
        "--portainer-https-port",
        type=int,
        default=None,
        help="Portainer HTTPS port (resolution: CLI/env/.env.deploy -> 443 for portainer.<PUBLIC_DOMAIN base>, else 9943)",
    )
    parser.add_argument(
        "--portainer-webhook-insecure",
        action="store_true",
        help="Pass -k to curl when triggering Portainer webhook",
    )
    parser.add_argument(
        "--skip-build-push",
        action="store_true",
        help="Skip default local docker build+push before deployment",
    )
    parser.add_argument(
        "--hooks-module",
        default=None,
        help=(
            "Optional hooks module path or import path for ubuntu deploy customizations. "
            "Resolution: CLI -> DEPLOY_HOOKS_MODULE env var -> default scripts/deploy/deploy_customizations.py"
        ),
    )
    parser.add_argument(
        "--hooks-soft-fail",
        action="store_true",
        help=(
            "When set, hook failures are logged and deployment continues. "
            "Resolution precedence: CLI flag, else DEPLOY_HOOKS_SOFT_FAIL env var."
        ),
    )
    parser.add_argument(
        "--storage-manager-api-url",
        default=None,
        help=(
            "Storage Manager API base URL (e.g. https://storage.example.com or https://storage.example.com/api/register). "
            "Resolution: CLI -> STORAGE_MANAGER_API_URL env var -> .env.deploy"
        ),
    )
    parser.add_argument(
        "--prod",
        action="store_true",
        help="Deploy to production (uses PUBLIC_DOMAIN, UBUNTU_REMOTE_DIR, PORTAINER_STACK_NAME). Default is staging.",
    )
    parser.add_argument(
        "--swap",
        action="store_true",
        help="Promote the staged stack to production, keep PUBLIC_DOMAIN routed to production, then stop staging.",
    )

    args = parser.parse_args(argv)

    if args.prod and args.swap:
        parser.error("--prod and --swap are mutually exclusive")

    swap_requested = bool(args.swap)
    deploy_target = resolve_deploy_target(prod=bool(args.prod), swap=swap_requested)

    step_number = 0
    step_color = "\033[95m"
    color_reset = "\033[0m"

    def log_step(message: str, *, icon: str = "🚀") -> None:
        nonlocal step_number
        step_number += 1
        print(f"{step_color}[ubuntu-deploy] {icon} Step {step_number}: {message}{color_reset}")

    def log_info(message: str, *, icon: str = "ℹ️") -> None:
        print(f"[ubuntu-deploy] {icon} {message}")

    repo_root = repo_root_override or Path(__file__).resolve().parents[2]
    resolved_hooks_module = str(args.hooks_module or "").strip() or str(os.getenv(ENV_DEPLOY_HOOKS_MODULE) or "").strip() or None
    resolved_hooks_soft_fail = bool(args.hooks_soft_fail)
    if not resolved_hooks_soft_fail:
        resolved_hooks_soft_fail = parse_boolish(str(os.getenv(ENV_DEPLOY_HOOKS_SOFT_FAIL) or "").strip(), default=False)

    hooks = deploy_hooks.load_hooks(
        repo_root=repo_root,
        module_path=resolved_hooks_module,
        soft_fail=resolved_hooks_soft_fail,
    )
    hook_ctx = deploy_hooks.DeployContext(repo_root=repo_root, env=os.environ, args=args)
    hooks.call("pre_validate_env", hook_ctx)

    resolved_host = str(args.host or "").strip()
    if not resolved_host:
        resolved_host = str(os.getenv(ENV_UBUNTU_SSH_HOST) or "").strip()
    if not resolved_host:
        resolved_host = read_deploy_key(repo_root=repo_root, key=ENV_UBUNTU_SSH_HOST)
    if not resolved_host:
        raise SystemExit("Missing SSH host: provide --host, set UBUNTU_SSH_HOST, or add UBUNTU_SSH_HOST to .env.deploy")
    resolved_portainer_host = resolve_portainer_api_host(repo_root=repo_root, ssh_host=resolved_host)

    resolved_remote_dir = str(args.remote_dir or "").strip()
    if not resolved_remote_dir:
        # Staging overrides: use STAGING_REMOTE_DIR when deploying to staging
        if deploy_target == "staging":
            resolved_remote_dir = str(os.getenv(ENV_STAGING_REMOTE_DIR) or "").strip()
            if not resolved_remote_dir:
                resolved_remote_dir = read_deploy_key(repo_root=repo_root, key=ENV_STAGING_REMOTE_DIR)
            if not resolved_remote_dir:
                raise SystemExit(
                    f"[ubuntu-deploy] ❌ STAGING_REMOTE_DIR is not set. "
                    f"Staging deploys require a separate directory from production. "
                    f"Set STAGING_REMOTE_DIR in .env.deploy (e.g. /home/user/containers/staging-myapp)."
                )
        if not resolved_remote_dir:
            resolved_remote_dir = str(os.getenv(ENV_UBUNTU_REMOTE_DIR) or "").strip()
        if not resolved_remote_dir:
            resolved_remote_dir = read_deploy_key(repo_root=repo_root, key=ENV_UBUNTU_REMOTE_DIR)
    if not resolved_remote_dir:
        resolved_remote_dir = "/opt/protected-container"
    remote_dir = Path(resolved_remote_dir)

    resolved_compose_files_raw = str(args.compose_files or "").strip()
    if not resolved_compose_files_raw:
        resolved_compose_files_raw = str(os.getenv(ENV_UBUNTU_COMPOSE_FILES) or "").strip()
    if not resolved_compose_files_raw:
        resolved_compose_files_raw = read_deploy_key(repo_root=repo_root, key=ENV_UBUNTU_COMPOSE_FILES)

    resolved_app_image = str(os.getenv(ENV_APP_IMAGE) or "").strip()
    if not resolved_app_image:
        resolved_app_image = read_deploy_key(repo_root=repo_root, key=ENV_APP_IMAGE)

    resolved_storage_manager_image = str(os.getenv(ENV_STORAGE_MANAGER_IMAGE) or "").strip()
    if not resolved_storage_manager_image:
        resolved_storage_manager_image = read_deploy_key(repo_root=repo_root, key=ENV_STORAGE_MANAGER_IMAGE)
    if not resolved_storage_manager_image:
        resolved_storage_manager_image = "ghcr.io/beejones/protected-container-storage-manager:latest"

    resolved_dockerfile = str(os.getenv(ENV_DOCKERFILE) or "").strip()
    if not resolved_dockerfile:
        resolved_dockerfile = read_deploy_key(repo_root=repo_root, key=ENV_DOCKERFILE)
    if not resolved_dockerfile:
        resolved_dockerfile = "docker/Dockerfile"

    resolved_storage_manager_dockerfile = str(os.getenv(ENV_STORAGE_MANAGER_DOCKERFILE) or "").strip()
    if not resolved_storage_manager_dockerfile:
        resolved_storage_manager_dockerfile = read_deploy_key(repo_root=repo_root, key=ENV_STORAGE_MANAGER_DOCKERFILE)
    if not resolved_storage_manager_dockerfile:
        resolved_storage_manager_dockerfile = "docker/storage-manager/Dockerfile"

    resolved_build_push_enabled = not bool(args.skip_build_push) and not swap_requested
    if resolved_build_push_enabled:
        build_push_raw = str(os.getenv(ENV_UBUNTU_BUILD_PUSH) or "").strip()
        if not build_push_raw:
            build_push_raw = read_deploy_key(repo_root=repo_root, key=ENV_UBUNTU_BUILD_PUSH)
        resolved_build_push_enabled = parse_boolish(build_push_raw, default=True)

    resolved_portainer_https_port_raw = str(args.portainer_https_port or "").strip()
    if not resolved_portainer_https_port_raw:
        resolved_portainer_https_port_raw = str(os.getenv(ENV_PORTAINER_HTTPS_PORT) or "").strip()
    if not resolved_portainer_https_port_raw:
        resolved_portainer_https_port_raw = read_deploy_key(repo_root=repo_root, key=ENV_PORTAINER_HTTPS_PORT)
    resolved_portainer_https_port = int(
        resolved_portainer_https_port_raw
        or str(default_portainer_https_port(portainer_host=resolved_portainer_host, ssh_host=resolved_host))
    )

    resolved_sync_secrets = bool(args.sync_secrets)
    if not resolved_sync_secrets:
        sync_secrets_raw = str(os.getenv(ENV_UBUNTU_SYNC_SECRETS) or "").strip()
        if not sync_secrets_raw:
            sync_secrets_raw = read_deploy_key(repo_root=repo_root, key=ENV_UBUNTU_SYNC_SECRETS)
        resolved_sync_secrets = parse_boolish(sync_secrets_raw, default=True)

    resolved_portainer_webhook_insecure = bool(args.portainer_webhook_insecure)
    if not resolved_portainer_webhook_insecure:
        webhook_insecure_raw = str(os.getenv(ENV_PORTAINER_WEBHOOK_INSECURE) or "").strip()
        if not webhook_insecure_raw:
            webhook_insecure_raw = read_deploy_key(repo_root=repo_root, key=ENV_PORTAINER_WEBHOOK_INSECURE)
        resolved_portainer_webhook_insecure = parse_boolish(webhook_insecure_raw, default=False)

    if resolved_portainer_webhook_insecure:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    resolved_portainer_webhook_url = str(args.portainer_webhook_url or "").strip()
    if not resolved_portainer_webhook_url:
        resolved_portainer_webhook_url = str(os.getenv(ENV_PORTAINER_WEBHOOK_URL) or "").strip()
    if not resolved_portainer_webhook_url:
        resolved_portainer_webhook_url = read_deploy_secret_key(repo_root=repo_root, key=ENV_PORTAINER_WEBHOOK_URL)
    if not resolved_portainer_webhook_url:
        resolved_portainer_webhook_url = read_deploy_key(repo_root=repo_root, key=ENV_PORTAINER_WEBHOOK_URL)

    resolved_portainer_token = str(args.portainer_webhook_token or "").strip()
    if not resolved_portainer_token:
        resolved_portainer_token = str(os.getenv(ENV_PORTAINER_WEBHOOK_TOKEN) or "").strip()
    if not resolved_portainer_token:
        resolved_portainer_token = read_deploy_secret_key(repo_root=repo_root, key=ENV_PORTAINER_WEBHOOK_TOKEN)

    resolved_portainer_access_token = str(os.getenv(ENV_PORTAINER_ACCESS_TOKEN) or "").strip()
    if not resolved_portainer_access_token:
        resolved_portainer_access_token = read_deploy_secret_key(repo_root=repo_root, key=ENV_PORTAINER_ACCESS_TOKEN)

    resolved_portainer_stack_name = ""
    if deploy_target == "staging":
        resolved_portainer_stack_name = str(os.getenv(ENV_STAGING_PORTAINER_STACK_NAME) or "").strip()
        if not resolved_portainer_stack_name:
            resolved_portainer_stack_name = read_deploy_key(repo_root=repo_root, key=ENV_STAGING_PORTAINER_STACK_NAME)
        if not resolved_portainer_stack_name:
            raise SystemExit(
                f"[ubuntu-deploy] ❌ STAGING_PORTAINER_STACK_NAME is not set. "
                f"Staging deploys require a separate stack name from production. "
                f"Set STAGING_PORTAINER_STACK_NAME in .env.deploy (e.g. staging-myapp)."
            )
    if not resolved_portainer_stack_name:
        resolved_portainer_stack_name = str(os.getenv(ENV_PORTAINER_STACK_NAME) or "").strip()
    if not resolved_portainer_stack_name:
        resolved_portainer_stack_name = read_deploy_key(repo_root=repo_root, key=ENV_PORTAINER_STACK_NAME)
    if not resolved_portainer_stack_name:
        resolved_portainer_stack_name = remote_dir.name

    resolved_portainer_endpoint_id = str(os.getenv(ENV_PORTAINER_ENDPOINT_ID) or "").strip()
    if not resolved_portainer_endpoint_id:
        resolved_portainer_endpoint_id = read_deploy_key(repo_root=repo_root, key=ENV_PORTAINER_ENDPOINT_ID)

    resolved_storage_manager_api_url = str(args.storage_manager_api_url or "").strip()
    if not resolved_storage_manager_api_url:
        resolved_storage_manager_api_url = str(os.getenv(ENV_STORAGE_MANAGER_API_URL) or "").strip()
    if not resolved_storage_manager_api_url:
        resolved_storage_manager_api_url = read_deploy_key(repo_root=repo_root, key=ENV_STORAGE_MANAGER_API_URL)

    hooks.call("post_validate_env", hook_ctx)

    resolved_ghcr_username = str(os.getenv(ENV_GHCR_USERNAME) or "").strip()
    if not resolved_ghcr_username:
        resolved_ghcr_username = read_deploy_key(repo_root=repo_root, key=ENV_GHCR_USERNAME)

    resolved_ghcr_token = str(os.getenv(ENV_GHCR_TOKEN) or "").strip()
    if not resolved_ghcr_token:
        resolved_ghcr_token = read_deploy_secret_key(repo_root=repo_root, key=ENV_GHCR_TOKEN)

    if resolved_build_push_enabled:
        if not resolved_app_image:
            raise SystemExit("APP_IMAGE is required when build/push is enabled")
        needs_ghcr_auth = resolved_app_image.startswith("ghcr.io/") or resolved_storage_manager_image.startswith("ghcr.io/")
        if needs_ghcr_auth:
            if not resolved_ghcr_username or not resolved_ghcr_token:
                raise SystemExit(
                    "GHCR_USERNAME and GHCR_TOKEN are required to build/push GHCR images. "
                    "Set them in .env.deploy/.env.deploy.secrets or use --skip-build-push."
                )
            log_step("Logging into GHCR for local build/push", icon="🔐")
            docker_login_local(registry="ghcr.io", username=resolved_ghcr_username, token=resolved_ghcr_token)

        log_step("Building and pushing APP_IMAGE locally", icon="🏗️")
        build_and_push_local_image(
            repo_root=repo_root,
            app_image=resolved_app_image,
            dockerfile=resolved_dockerfile,
        )

        log_step("Building and pushing STORAGE_MANAGER_IMAGE locally", icon="🏗️")
        storage_manager_built = build_and_push_local_image(
            repo_root=repo_root,
            app_image=resolved_storage_manager_image,
            dockerfile=resolved_storage_manager_dockerfile,
            allow_missing_dockerfile=True,
        )
        if not storage_manager_built:
            log_info(
                (
                    f"{resolved_storage_manager_dockerfile} is missing; "
                    "skipping local STORAGE_MANAGER_IMAGE build/push."
                ),
                icon="⚠️",
            )

    has_portainer_api_auth = bool(resolved_portainer_access_token)

    if not (resolved_portainer_webhook_url or resolved_portainer_token or has_portainer_api_auth):
        raise SystemExit(
            "Provide Portainer webhook URL/token or Portainer access token (PORTAINER_ACCESS_TOKEN)"
        )
    if resolved_portainer_https_port < 1 or resolved_portainer_https_port > 65535:
        raise SystemExit("--portainer-https-port must be in range 1-65535")

    compose_files = (
        [s.strip() for s in resolved_compose_files_raw.split(",") if s.strip()]
        if resolved_compose_files_raw
        else ["docker/docker-compose.yml", "docker/docker-compose.ubuntu.yml"]
    )

    # Validate required local files exist.
    required_paths: list[Path] = [repo_root / cf for cf in compose_files] + [repo_root / "docker"]
    missing = [str(p) for p in required_paths if not p.exists()]
    if missing:
        raise SystemExit(f"Missing required files: {missing}")

    stack_file_content_raw = render_compose_stack_content(repo_root=repo_root, compose_files=compose_files)
    stack_file_content_remote = rewrite_rendered_paths_for_remote(
        stack_content=stack_file_content_raw,
        local_repo_root=repo_root,
        remote_dir=remote_dir,
    )
    stack_file_content = prepare_stack_content_for_portainer(
        stack_content=stack_file_content_remote,
        app_image=resolved_app_image,
    )
    if deploy_target == "staging":
        stack_file_content = rewrite_staging_container_names_for_portainer(
            stack_content=stack_file_content,
            stack_name=resolved_portainer_stack_name,
        )
    stack_includes_storage_manager = stack_has_service(
        stack_content=stack_file_content,
        service_name="storage-manager",
    )
    ghcr_images_in_stack = ghcr_images_from_stack(stack_content=stack_file_content)
    if ghcr_images_in_stack and (not resolved_ghcr_username or not resolved_ghcr_token):
        raise SystemExit(
            "GHCR_USERNAME and GHCR_TOKEN are required for GHCR images in the Portainer stack. "
            f"Detected GHCR images: {ghcr_images_in_stack}. "
            "Set GHCR_USERNAME in .env.deploy and GHCR_TOKEN in .env.deploy.secrets."
        )
    storage_registrations = collect_storage_manager_registrations(stack_content=stack_file_content)

    hook_public_domain = str(os.getenv(ENV_PUBLIC_DOMAIN) or "").strip()
    if not hook_public_domain:
        hook_public_domain = read_deploy_key(repo_root=repo_root, key=ENV_PUBLIC_DOMAIN)

    hook_web_port = str(os.getenv(ENV_WEB_PORT) or "").strip()
    if not hook_web_port:
        hook_web_port = read_deploy_key(repo_root=repo_root, key=ENV_WEB_PORT)
    if not hook_web_port:
        hook_web_port = "3000"

    hook_plan = _build_ubuntu_deploy_hook_plan(
        stack_name=resolved_portainer_stack_name,
        public_domain=hook_public_domain,
        app_image=resolved_app_image,
        web_port=hook_web_port,
        compose_files=compose_files,
        storage_manager_api_url=resolved_storage_manager_api_url,
        storage_registrations=storage_registrations,
    )
    hooks.call("build_deploy_plan", hook_ctx, hook_plan)

    hook_storage_api_url = str(hook_plan.extra_metadata.get("storage_manager_api_url") or "").strip()
    hook_storage_registrations_raw = hook_plan.extra_metadata.get("storage_registrations")
    if isinstance(hook_storage_registrations_raw, list):
        storage_registrations = [item for item in hook_storage_registrations_raw if isinstance(item, dict)]
    resolved_storage_manager_api_url = hook_storage_api_url or resolved_storage_manager_api_url
    default_storage_registration_enabled = bool(hook_plan.extra_metadata.get("enable_default_storage_registration", True))

    deploy_log_settings = deploy_log.default_deploy_log_settings(repo_root)
    hooks.call("configure_deploy_log", hook_ctx, hook_plan, deploy_log_settings)
    if not deploy_log_settings.versioning_enabled:
        log_info("Deploy log versioning disabled by deploy hook.", icon="🪝")
    deploy_log.require_version_record_for_deploy(
        repo_root=repo_root,
        settings=deploy_log_settings,
        status="success",
    )

    log_step(f"Prepared deployment plan [{deploy_target.upper()}]", icon="🧭")
    log_info(f"Target environment: {deploy_target}")
    log_info(f"Version: {deploy_log._read_app_version(repo_root)}")
    log_info(f"Host: {resolved_host}")
    if resolved_portainer_host and resolved_portainer_host != portainer_helpers.extract_ssh_hostname(resolved_host):
        log_info(f"Portainer API host: {resolved_portainer_host}")
    log_info(f"Remote dir: {remote_dir}")
    log_info(f"Compose files: {compose_files}")
    if storage_registrations:
        log_info(f"Detected {len(storage_registrations)} storage-manager label registration(s)", icon="🧹")

    log_step("Checking SSH connectivity", icon="🔌")
    try:
        subprocess.run(
            build_ssh_connectivity_cmd(host=resolved_host),
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        raise SystemExit(
            "SSH connectivity check timed out after 15s. "
            "Verify the server is online and reachable on port 22."
        )
    except subprocess.CalledProcessError as exc:
        detail = _subprocess_error_text(exc)
        message = "SSH connectivity check failed before deployment."
        if detail:
            message = f"{message} {detail}"
        hint = _ssh_failure_hint(detail)
        if hint:
            message = f"{message} {hint}"
        raise SystemExit(message)

    # Ensure remote dir exists.
    log_step("Ensuring remote deployment directory exists", icon="📁")
    _run(
        build_ssh_cmd(host=resolved_host, remote_command=f"mkdir -p {shlex.quote(str(remote_dir))}"),
        action="Failed to create remote deployment directory over SSH",
    )

    # Sync compose files and docker/ directory.
    log_step("Syncing compose files and docker assets", icon="📦")
    sync_paths: list[Path] = [repo_root / cf for cf in compose_files] + [repo_root / "docker"]
    _run(
        build_rsync_cmd(sources=sync_paths, host=resolved_host, remote_dir=remote_dir),
        action="Failed to sync compose files and docker assets",
    )

    if resolved_sync_secrets:
        env_paths: list[Path] = []
        for name in [".env", ".env.secrets", ".env.deploy", ".env.deploy.secrets"]:
            p = repo_root / name
            if p.exists():
                env_paths.append(p)
            else:
                log_info(f"Skipping missing {p}", icon="⚠️")
        if env_paths:
            log_step("Syncing environment files", icon="🔐")
            _run(
                build_rsync_cmd(sources=env_paths, host=resolved_host, remote_dir=remote_dir),
                action="Failed to sync environment files",
            )
        else:
            log_info("No env files to sync")

    log_step("Ensuring Portainer is running on remote host", icon="🛡️")
    _run(
        build_ssh_cmd(
            host=resolved_host,
            remote_command=portainer_helpers.portainer_ensure_running_remote_cmd(https_port=resolved_portainer_https_port),
        ),
        action="Failed to ensure Portainer is running on the remote host",
    )

    if ghcr_images_in_stack and resolved_ghcr_username and resolved_ghcr_token:
        for image in ghcr_images_in_stack:
            log_step(f"Logging into GHCR and pre-pulling {image} on remote host", icon="🔐")
            _run(
                build_ssh_cmd(
                    host=resolved_host,
                    remote_command=ghcr_login_pull_remote_cmd(
                        image=image,
                        username=resolved_ghcr_username,
                        token=resolved_ghcr_token,
                    ),
                ),
                action=f"Failed remote GHCR login/pull for image {image}",
            )

    log_step("Ensuring Central Caddy Proxy is running", icon="🌐")
    # Check if the global proxy container exists
    caddy_check_cmd = build_ssh_cmd(
        host=resolved_host,
        remote_command="docker ps -a --format '{{.Names}}' | grep -Fxq central-proxy"
    )
    result = subprocess.run(caddy_check_cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        log_info("Central proxy missing. Deploying via ubuntu_deploy_proxy.sh...")
        proxy_script = repo_root / "scripts" / "deploy" / "ubuntu_deploy_proxy.sh"
        if proxy_script.exists():
            try:
                subprocess.run(["bash", str(proxy_script)], check=True)
            except subprocess.CalledProcessError as exc:
                detail = _subprocess_error_text(exc)
                message = "Failed to deploy central proxy via ubuntu_deploy_proxy.sh"
                if detail:
                    message = f"{message}: {detail}"
                raise SystemExit(message)
        else:
            log_info(f"Warning: {proxy_script} not found. Cannot auto-deploy proxy.", icon="⚠️")
    else:
        log_info("Central proxy is already running.")

    used_remote_compose_fallback = False

    if has_portainer_api_auth:
        log_step("Testing Portainer access token", icon="🔑")
        try:
            token_valid = portainer_helpers.is_portainer_access_token_valid(
                host=resolved_portainer_host,
                https_port=resolved_portainer_https_port,
                insecure=resolved_portainer_webhook_insecure,
                access_token=resolved_portainer_access_token,
            )
        except SystemExit as exc:
            error_text = str(exc)
            if _should_fallback_to_remote_compose(error_text):
                log_info(
                    "Portainer is reachable but not initialized; falling back to direct Docker Compose deployment over SSH.",
                    icon="⚠️",
                )
                used_remote_compose_fallback = True
                token_valid = False
            else:
                raise
        if not used_remote_compose_fallback and not token_valid:
            raise SystemExit(
                "Portainer access token is invalid or expired. "
                "Update PORTAINER_ACCESS_TOKEN in .env.deploy.secrets and retry. "
                "If you intentionally want webhook-only deploys, remove PORTAINER_ACCESS_TOKEN."
            )

    staging_stack_name_for_stop = ""
    if deploy_target == "production":
        staging_stack_name_for_stop = str(os.getenv(ENV_STAGING_PORTAINER_STACK_NAME) or "").strip()
        if not staging_stack_name_for_stop:
            staging_stack_name_for_stop = read_deploy_key(repo_root=repo_root, key=ENV_STAGING_PORTAINER_STACK_NAME)
        if staging_stack_name_for_stop:
            if not has_portainer_api_auth:
                raise SystemExit(
                    "PORTAINER_ACCESS_TOKEN is required for --prod when STAGING_PORTAINER_STACK_NAME is set "
                    "because staging lifecycle is managed through the Portainer API."
                )
            if swap_requested and not used_remote_compose_fallback:
                log_step("Verifying staged containers exist", icon="🔎")
                staging_containers = portainer_helpers.list_portainer_stack_containers(
                    host=resolved_portainer_host,
                    https_port=resolved_portainer_https_port,
                    insecure=resolved_portainer_webhook_insecure,
                    endpoint_id=resolved_portainer_endpoint_id,
                    access_token=resolved_portainer_access_token,
                    stack_name=staging_stack_name_for_stop,
                )
                if not staging_containers:
                    raise SystemExit(
                        "Staging containers are not ready for swap. "
                        "Run `source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py` first."
                    )
                log_info(f"Staged Portainer stack: {staging_stack_name_for_stop} ({len(staging_containers)} containers)")
        elif swap_requested:
            raise SystemExit(
                "[ubuntu-deploy] ❌ STAGING_PORTAINER_STACK_NAME is not set. "
                "Swap requires the staging Portainer stack name."
            )

    if used_remote_compose_fallback:
        if deploy_target == "staging":
            raise SystemExit(
                "Staging deploy requires Portainer API access. "
                "Set PORTAINER_ACCESS_TOKEN so the script can create and stop staging containers through Portainer."
            )
        log_step("Deploying stack directly with Docker Compose over SSH", icon="🐳")
        _run(
            build_ssh_cmd(
                host=resolved_host,
                remote_command=build_remote_compose_deploy_cmd(remote_dir=remote_dir, compose_files=compose_files),
            ),
            action="Failed direct Docker Compose deployment on the remote host",
        )
    elif has_portainer_api_auth:
        log_step("Deploying stack through Portainer API", icon="🌐")
        try:
            resolved_portainer_webhook_url = portainer_helpers.resolve_portainer_webhook_url_via_api(
                host=resolved_portainer_host,
                https_port=resolved_portainer_https_port,
                insecure=resolved_portainer_webhook_insecure,
                stack_name=resolved_portainer_stack_name,
                endpoint_id=resolved_portainer_endpoint_id,
                access_token=resolved_portainer_access_token,
                stack_file_content=stack_file_content,
                ssh_run_fn=lambda remote_command: _run(build_ssh_cmd(host=resolved_host, remote_command=remote_command)),
            )
        except requests.HTTPError as exc:
            status_code = int(getattr(getattr(exc, "response", None), "status_code", 0) or 0)
            if status_code == 401:
                raise SystemExit(
                    "Portainer access token was rejected (401 Unauthorized). "
                    "Update PORTAINER_ACCESS_TOKEN in .env.deploy.secrets and retry. "
                    "If you intentionally want webhook-only deploys, remove PORTAINER_ACCESS_TOKEN."
                )
            else:
                raise

    if used_remote_compose_fallback:
        log_step("Stack deployed directly over SSH; skipping Portainer webhook trigger", icon="✅")
    elif has_portainer_api_auth and not resolved_portainer_webhook_url:
        log_step("Stack deployed via Portainer API; webhook token not returned, skipping webhook trigger", icon="✅")
    else:
        webhook_urls = (
            [resolved_portainer_webhook_url]
            if resolved_portainer_webhook_url
            else portainer_helpers.build_portainer_webhook_urls_from_token(
                host=resolved_portainer_host,
                https_port=resolved_portainer_https_port,
                webhook_token=resolved_portainer_token,
            )
        )

        log_step("Triggering Portainer webhook", icon="🪝")
        portainer_helpers.trigger_portainer_webhook(
            urls=webhook_urls,
            insecure=resolved_portainer_webhook_insecure,
            has_api_auth=has_portainer_api_auth,
        )

    if deploy_target == "production" and staging_stack_name_for_stop and not used_remote_compose_fallback:
        log_step("Stopping staging containers (production is running)", icon="⏹️")
        staging_containers = portainer_helpers.list_portainer_stack_containers(
            host=resolved_portainer_host,
            https_port=resolved_portainer_https_port,
            insecure=resolved_portainer_webhook_insecure,
            endpoint_id=resolved_portainer_endpoint_id,
            access_token=resolved_portainer_access_token,
            stack_name=staging_stack_name_for_stop,
        )
        if staging_containers:
            stopped = portainer_helpers.set_portainer_stack_containers_state(
                host=resolved_portainer_host,
                https_port=resolved_portainer_https_port,
                insecure=resolved_portainer_webhook_insecure,
                endpoint_id=resolved_portainer_endpoint_id,
                access_token=resolved_portainer_access_token,
                stack_name=staging_stack_name_for_stop,
                action="stop",
            )
            log_info(f"Stopped via Portainer stack {staging_stack_name_for_stop}: {', '.join(stopped)}")
        else:
            log_info("No staging containers to stop (not deployed yet).")

    # --- Post-deploy: stop staging containers (staging deploys create but don't run) ---
    if deploy_target == "staging" and not used_remote_compose_fallback:
        log_step("Stopping staging containers (staging is pre-deployed, not started)", icon="⏹️")
        stopped = portainer_helpers.set_portainer_stack_containers_state(
            host=resolved_portainer_host,
            https_port=resolved_portainer_https_port,
            insecure=resolved_portainer_webhook_insecure,
            endpoint_id=resolved_portainer_endpoint_id,
            access_token=resolved_portainer_access_token,
            stack_name=resolved_portainer_stack_name,
            action="stop",
        )
        log_info(f"Stopped via Portainer stack {resolved_portainer_stack_name}: {', '.join(stopped)}")

    # --- Post-deploy: register with centralized Caddy proxy ----------------
    resolved_public_domain = ""
    if deploy_target == "staging":
        resolved_public_domain = str(os.getenv(ENV_STAGING_PUBLIC_DOMAIN) or "").strip()
        if not resolved_public_domain:
            resolved_public_domain = read_deploy_key(repo_root=repo_root, key=ENV_STAGING_PUBLIC_DOMAIN)
    if not resolved_public_domain:
        resolved_public_domain = str(os.getenv(ENV_PUBLIC_DOMAIN) or "").strip()
    if not resolved_public_domain:
        resolved_public_domain = read_deploy_key(repo_root=repo_root, key=ENV_PUBLIC_DOMAIN)

    resolved_web_port = str(os.getenv(ENV_WEB_PORT) or "").strip()
    if not resolved_web_port:
        resolved_web_port = read_deploy_key(repo_root=repo_root, key=ENV_WEB_PORT)
    if not resolved_web_port:
        resolved_web_port = "3000"

    resolved_caddy_proxy_dir = str(os.getenv(ENV_CADDY_PROXY_DIR) or "").strip()
    if not resolved_caddy_proxy_dir:
        resolved_caddy_proxy_dir = read_deploy_key(repo_root=repo_root, key=ENV_CADDY_PROXY_DIR)

    if resolved_public_domain:
        # Derive service name from the Portainer stack name (which matches the
        # primary compose service name by convention).
        service_name = resolved_portainer_stack_name or remote_dir.name

        # The proxy Caddyfile lives in the proxy stack's repo on the same host.
        # Default convention: sibling path under protected-container.
        # Override with CADDY_PROXY_DIR when downstream layout differs.
        proxy_repo_dir = Path(resolved_caddy_proxy_dir) if resolved_caddy_proxy_dir else (remote_dir.parent / "protected-container")
        caddyfile_path = str(proxy_repo_dir / "docker" / "proxy" / "Caddyfile")

        log_step("Registering with centralized Caddy proxy", icon="🔒")
        try:
            caddy_register.ensure_caddy_registration(
                ssh_host=resolved_host,
                domain=resolved_public_domain,
                service=service_name,
                port=resolved_web_port,
                caddyfile_path=caddyfile_path,
            )

            is_registered = caddy_register.is_domain_registered(
                ssh_host=resolved_host,
                domain=resolved_public_domain,
                caddyfile_path=caddyfile_path,
            )
            if is_registered:
                log_info(
                    f"Caddy registration verified for {resolved_public_domain}.",
                    icon="✅",
                )
            else:
                log_info(
                    (
                        f"Caddy registration could not be verified for {resolved_public_domain}. "
                        f"Checked Caddyfile: {caddyfile_path}. "
                        "Deployment continues, but HTTPS routing may be unavailable."
                    ),
                    icon="⚠️",
                )
        except Exception as exc:
            log_info(f"Caddy registration failed: {exc}", icon="⚠️")
            log_info(
                "Deployment completed, but public HTTPS routing may be unavailable until Caddy is fixed.",
                icon="⚠️",
            )
    else:
        log_info("PUBLIC_DOMAIN not set — skipping Caddy registration.", icon="⚠️")

    if storage_registrations:
        if default_storage_registration_enabled:
            if resolved_storage_manager_api_url:
                log_step("Registering storage-manager labels via API", icon="🧹")
                register_storage_manager_registrations(
                    api_url=resolved_storage_manager_api_url,
                    registrations=storage_registrations,
                )
            else:
                if stack_includes_storage_manager:
                    log_info(
                        "Storage-manager labels detected; STORAGE_MANAGER_API_URL not set. Registration remains active via storage-manager Docker label auto-discovery (no action required).",
                        icon="ℹ️",
                    )
                else:
                    log_info(
                        "Storage-manager labels were detected but STORAGE_MANAGER_API_URL is not set; skipping registration.",
                        icon="⚠️",
                    )
        else:
            log_info("Default storage registration disabled by deploy hook.", icon="🪝")

    hooks.call(
        "post_deploy",
        hook_ctx,
        hook_plan,
        {
            "storage_registration_count": len(storage_registrations),
            "storage_manager_api_url": resolved_storage_manager_api_url,
            "default_storage_registration_enabled": default_storage_registration_enabled,
        },
    )

    # --- Version log CSV ----------------------------------------------------
    deploy_log.append_deploy_record_with_settings(
        repo_root=repo_root,
        settings=deploy_log_settings,
        target="swap" if swap_requested else deploy_target,
        stack_name=resolved_portainer_stack_name,
        domain=resolved_public_domain,
        image=resolved_app_image,
        status="success",
    )

    version_str = deploy_log._read_app_version(repo_root)
    if deploy_target == "staging":
        print(f"[ubuntu-deploy] ✅ Done. Staged to {deploy_target} (v{version_str}). Containers created and stopped — use --swap to promote to production.")
    elif swap_requested:
        print(f"[ubuntu-deploy] ✅ Done. Promoted staging to production (v{version_str}). Production is running; staging is stopped.")
    else:
        print(f"[ubuntu-deploy] ✅ Done. Deployed to {deploy_target} (v{version_str}).")


if __name__ == "__main__":
    main()
