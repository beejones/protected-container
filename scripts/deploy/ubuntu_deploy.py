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
import shlex
import subprocess
from pathlib import Path

import requests
from dotenv import dotenv_values
import urllib3
import yaml


ENV_APP_IMAGE = "APP_IMAGE"
ENV_DOCKERFILE = "DOCKERFILE"
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


def _run(cmd: list[str], *, check: bool = True) -> None:
    subprocess.run(cmd, check=check)


def build_rsync_cmd(*, sources: list[Path], host: str, remote_dir: Path) -> list[str]:
    srcs = [str(p) for p in sources]
    # Trailing slash on remote_dir ensures rsync copies into the dir.
    dest = f"{host}:{str(remote_dir)}/"
    return ["rsync", "-az", "--mkpath", *srcs, dest]


def build_ssh_cmd(*, host: str, remote_command: str) -> list[str]:
    return ["ssh", host, remote_command]


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


def extract_container_names_from_stack_content(stack_content: str) -> list[str]:
    payload = yaml.safe_load(stack_content)
    if not isinstance(payload, dict):
        return []
    services = payload.get("services")
    if not isinstance(services, dict):
        return []

    names: list[str] = []
    for service_payload in services.values():
        if not isinstance(service_payload, dict):
            continue
        container_name = str(service_payload.get("container_name") or "").strip()
        if container_name:
            names.append(container_name)
    return names


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


def build_and_push_local_image(*, repo_root: Path, app_image: str, dockerfile: str) -> None:
    dockerfile_path = repo_root / dockerfile
    if not dockerfile_path.exists():
        raise SystemExit(f"Dockerfile not found for build/push: {dockerfile_path}")
    context_dir = str(Path(dockerfile).parent)
    if context_dir == "":
        context_dir = "."
    build_cmd = build_docker_build_cmd(app_image=app_image, dockerfile=dockerfile, context_dir=context_dir)
    push_cmd = build_docker_push_cmd(app_image=app_image)
    subprocess.run(build_cmd, cwd=str(repo_root), check=True)
    subprocess.run(push_cmd, cwd=str(repo_root), check=True)


def _extract_webhook_token(payload: object) -> str:
    if isinstance(payload, dict):
        for key in ["Webhook", "webhook", "token", "Token", "webhookToken", "WebhookToken"]:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for value in payload.values():
            token = _extract_webhook_token(value)
            if token:
                return token
    if isinstance(payload, list):
        for item in payload:
            token = _extract_webhook_token(item)
            if token:
                return token
    return ""


def _portainer_auth_headers(*, access_token: str) -> dict[str, str]:
    if access_token.strip():
        return {"X-API-Key": access_token.strip()}
    return {}


def resolve_portainer_webhook_url_via_api(
    *,
    host: str,
    https_port: int,
    insecure: bool,
    stack_name: str,
    endpoint_id: str,
    access_token: str,
    stack_file_content: str,
) -> str:
    hostname = extract_ssh_hostname(host).strip()
    base_url = f"https://{hostname}:{https_port}"
    headers = _portainer_auth_headers(access_token=access_token)
    if not headers:
        return ""

    stacks_resp = requests.get(f"{base_url}/api/stacks", headers=headers, verify=not insecure, timeout=20)
    stacks_resp.raise_for_status()
    stacks_payload = stacks_resp.json()
    if not isinstance(stacks_payload, list):
        raise SystemExit("Unexpected Portainer /api/stacks response format")

    desired_name = stack_name.strip()

    endpoints_resp = requests.get(f"{base_url}/api/endpoints", headers=headers, verify=not insecure, timeout=20)
    endpoints_resp.raise_for_status()
    endpoints_payload = endpoints_resp.json()
    if not isinstance(endpoints_payload, list) or not endpoints_payload:
        raise SystemExit("No Portainer endpoints found")

    desired_endpoint = endpoint_id.strip()
    if not desired_endpoint:
        local_endpoint_id = ""
        for endpoint in endpoints_payload:
            if not isinstance(endpoint, dict):
                continue
            endpoint_name = str(endpoint.get("Name") or endpoint.get("name") or "").strip().lower()
            endpoint_url = str(endpoint.get("URL") or endpoint.get("url") or "").strip().lower()
            if endpoint_name == "local" or endpoint_url.startswith("unix://"):
                local_endpoint_id = str(endpoint.get("Id") or endpoint.get("id") or "").strip()
                if local_endpoint_id:
                    break
        if local_endpoint_id:
            desired_endpoint = local_endpoint_id
        else:
            first_endpoint = endpoints_payload[0]
            desired_endpoint = str(first_endpoint.get("Id") or first_endpoint.get("id") or "").strip()
    if not desired_endpoint:
        raise SystemExit("Unable to determine Portainer endpoint id; set PORTAINER_ENDPOINT_ID")

    matching_stacks: list[dict[str, object]] = []
    for stack in stacks_payload:
        if not isinstance(stack, dict):
            continue
        candidate_name = str(stack.get("Name") or stack.get("name") or "").strip()
        if candidate_name != desired_name:
            continue
        if desired_endpoint:
            candidate_endpoint = str(stack.get("EndpointId") or stack.get("endpointId") or "").strip()
            if candidate_endpoint != desired_endpoint:
                continue
        matching_stacks.append(stack)

    for stack in matching_stacks:
        stack_id = str(stack.get("Id") or stack.get("id") or "").strip()
        if not stack_id:
            continue
        stack_endpoint = str(stack.get("EndpointId") or stack.get("endpointId") or "").strip() or desired_endpoint
        delete_url = f"{base_url}/api/stacks/{stack_id}?endpointId={stack_endpoint}"
        delete_resp = requests.delete(delete_url, headers=headers, verify=not insecure, timeout=20)
        if not delete_resp.ok and int(delete_resp.status_code) != 404:
            details = str(delete_resp.text or "").strip().replace("\n", " ")[:300]
            raise SystemExit(f"Failed to remove existing Portainer stack '{desired_name}': {delete_resp.status_code} {details}")

    cleanup_names = extract_container_names_from_stack_content(stack_file_content)
    for container_name in cleanup_names:
        _run(
            build_ssh_cmd(
                host=host,
                remote_command=f"docker rm -f {shlex.quote(container_name)} >/dev/null 2>&1 || true",
            )
        )

    create_url = f"{base_url}/api/stacks/create/standalone/string?endpointId={desired_endpoint}"
    create_payload = {
        "Name": desired_name,
        "StackFileContent": stack_file_content,
        "Env": [],
        "FromAppTemplate": False,
    }
    create_resp = requests.post(
        create_url,
        headers=headers,
        json=create_payload,
        verify=not insecure,
        timeout=30,
    )

    if not create_resp.ok:
        status_code = int(create_resp.status_code)
        details = str(create_resp.text or "").strip().replace("\n", " ")[:300]
        raise SystemExit(f"Failed to create Portainer stack '{desired_name}': {status_code} {details}")

    created_payload = create_resp.json()
    created_stack_id = str(created_payload.get("Id") or created_payload.get("id") or "").strip()
    created_webhook_token = _extract_webhook_token(created_payload)
    if created_webhook_token:
        return build_portainer_webhook_url(host=host, https_port=https_port, webhook_token=created_webhook_token)
    if created_stack_id:
        webhook_resp = requests.post(
            f"{base_url}/api/stacks/{created_stack_id}/webhooks?endpointId={desired_endpoint}",
            headers=headers,
            verify=not insecure,
            timeout=20,
        )
        if webhook_resp.ok:
            created_token = _extract_webhook_token(webhook_resp.json())
            if created_token:
                return build_portainer_webhook_url(host=host, https_port=https_port, webhook_token=created_token)

        return ""


def build_portainer_webhook_urls_from_token(*, host: str, https_port: int, webhook_token: str) -> list[str]:
    hostname = extract_ssh_hostname(host).strip()
    token = webhook_token.strip()
    return [
        f"https://{hostname}:{https_port}/api/stacks/webhooks/{token}",
        f"https://{hostname}:{https_port}/api/webhooks/{token}",
    ]


def extract_ssh_hostname(host: str) -> str:
    return host.split("@", 1)[1] if "@" in host else host


def build_portainer_webhook_url(*, host: str, https_port: int, webhook_token: str) -> str:
    return build_portainer_webhook_urls_from_token(host=host, https_port=https_port, webhook_token=webhook_token)[0]


def trigger_portainer_webhook(*, urls: list[str], insecure: bool, has_api_auth: bool) -> None:
    saw_404 = False
    last_error = ""
    for url in urls:
        try:
            response = requests.post(url, verify=not insecure, timeout=20)
        except requests.RequestException as exc:
            last_error = str(exc)
            continue

        if response.ok:
            return

        if int(response.status_code) == 404:
            saw_404 = True
            last_error = f"HTTP 404 from {url}"
            continue

        details = str(response.text or "").strip().replace("\n", " ")[:200]
        raise SystemExit(f"Portainer webhook trigger failed ({response.status_code}) at {url}: {details}")

    if saw_404:
        if not has_api_auth:
            raise SystemExit(
                "Portainer webhook returned 404 for all known endpoints and no Portainer API auth is configured. "
                "Set PORTAINER_ACCESS_TOKEN in .env.deploy.secrets "
                "so the script can auto-resolve/create the correct stack webhook."
            )
        raise SystemExit(
            "Portainer webhook returned 404 for all known endpoints even after API-assisted resolution. "
            "Verify PORTAINER_STACK_NAME/PORTAINER_ENDPOINT_ID and ensure the stack exists in Portainer."
        )
    if last_error:
        raise SystemExit(last_error)
    raise SystemExit("Portainer webhook trigger failed")


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
        help="Host HTTPS port for Portainer when auto-creating container (resolution: CLI/env/.env.deploy -> 9943)",
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

    args = parser.parse_args(argv)

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

    resolved_host = str(args.host or "").strip()
    if not resolved_host:
        resolved_host = str(os.getenv(ENV_UBUNTU_SSH_HOST) or "").strip()
    if not resolved_host:
        resolved_host = read_deploy_key(repo_root=repo_root, key=ENV_UBUNTU_SSH_HOST)
    if not resolved_host:
        raise SystemExit("Missing SSH host: provide --host, set UBUNTU_SSH_HOST, or add UBUNTU_SSH_HOST to .env.deploy")

    resolved_remote_dir = str(args.remote_dir or "").strip()
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

    resolved_dockerfile = str(os.getenv(ENV_DOCKERFILE) or "").strip()
    if not resolved_dockerfile:
        resolved_dockerfile = read_deploy_key(repo_root=repo_root, key=ENV_DOCKERFILE)
    if not resolved_dockerfile:
        resolved_dockerfile = "docker/Dockerfile"

    resolved_build_push_enabled = not bool(args.skip_build_push)
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
    resolved_portainer_https_port = int(resolved_portainer_https_port_raw or "9943")

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

    resolved_portainer_stack_name = str(os.getenv(ENV_PORTAINER_STACK_NAME) or "").strip()
    if not resolved_portainer_stack_name:
        resolved_portainer_stack_name = read_deploy_key(repo_root=repo_root, key=ENV_PORTAINER_STACK_NAME)
    if not resolved_portainer_stack_name:
        resolved_portainer_stack_name = remote_dir.name

    resolved_portainer_endpoint_id = str(os.getenv(ENV_PORTAINER_ENDPOINT_ID) or "").strip()
    if not resolved_portainer_endpoint_id:
        resolved_portainer_endpoint_id = read_deploy_key(repo_root=repo_root, key=ENV_PORTAINER_ENDPOINT_ID)

    resolved_ghcr_username = str(os.getenv(ENV_GHCR_USERNAME) or "").strip()
    if not resolved_ghcr_username:
        resolved_ghcr_username = read_deploy_key(repo_root=repo_root, key=ENV_GHCR_USERNAME)

    resolved_ghcr_token = str(os.getenv(ENV_GHCR_TOKEN) or "").strip()
    if not resolved_ghcr_token:
        resolved_ghcr_token = read_deploy_secret_key(repo_root=repo_root, key=ENV_GHCR_TOKEN)

    if resolved_build_push_enabled:
        if not resolved_app_image:
            raise SystemExit("APP_IMAGE is required when build/push is enabled")
        if resolved_app_image.startswith("ghcr.io/"):
            if not resolved_ghcr_username or not resolved_ghcr_token:
                raise SystemExit(
                    "GHCR_USERNAME and GHCR_TOKEN are required to build/push APP_IMAGE to ghcr.io. "
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

    has_portainer_api_auth = bool(resolved_portainer_access_token)

    if not (resolved_portainer_webhook_url or resolved_portainer_token or has_portainer_api_auth):
        raise SystemExit(
            "Provide Portainer webhook URL/token or API auth (PORTAINER_ACCESS_TOKEN)"
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

    log_step("Prepared deployment plan", icon="🧭")
    log_info(f"Target: {resolved_host}")
    log_info(f"Remote dir: {remote_dir}")
    log_info(f"Compose files: {compose_files}")

    # Ensure remote dir exists.
    log_step("Ensuring remote deployment directory exists", icon="📁")
    _run(build_ssh_cmd(host=resolved_host, remote_command=f"mkdir -p {shlex.quote(str(remote_dir))}"))

    # Sync compose files and docker/ directory.
    log_step("Syncing compose files and docker assets", icon="📦")
    sync_paths: list[Path] = [repo_root / cf for cf in compose_files] + [repo_root / "docker"]
    _run(build_rsync_cmd(sources=sync_paths, host=resolved_host, remote_dir=remote_dir))

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
            _run(build_rsync_cmd(sources=env_paths, host=resolved_host, remote_dir=remote_dir))
        else:
            log_info("No env files to sync")

    log_step("Ensuring Portainer is running on remote host", icon="🛡️")
    _run(
        build_ssh_cmd(
            host=resolved_host,
            remote_command=portainer_ensure_running_remote_cmd(https_port=resolved_portainer_https_port),
        )
    )

    if resolved_app_image and resolved_app_image.startswith("ghcr.io/") and resolved_ghcr_username and resolved_ghcr_token:
        log_step("Logging into GHCR and pre-pulling APP_IMAGE on remote host", icon="🔐")
        _run(
            build_ssh_cmd(
                host=resolved_host,
                remote_command=ghcr_login_pull_remote_cmd(
                    image=resolved_app_image,
                    username=resolved_ghcr_username,
                    token=resolved_ghcr_token,
                ),
            )
        )

    if has_portainer_api_auth:
        log_step("Deploying stack through Portainer API", icon="🌐")
        resolved_portainer_webhook_url = resolve_portainer_webhook_url_via_api(
            host=resolved_host,
            https_port=resolved_portainer_https_port,
            insecure=resolved_portainer_webhook_insecure,
            stack_name=resolved_portainer_stack_name,
            endpoint_id=resolved_portainer_endpoint_id,
            access_token=resolved_portainer_access_token,
            stack_file_content=stack_file_content,
        )

    if has_portainer_api_auth and not resolved_portainer_webhook_url:
        log_step("Stack deployed via Portainer API; webhook token not returned, skipping webhook trigger", icon="✅")
        print("[ubuntu-deploy] ✅ Done.")
        return

    webhook_urls = (
        [resolved_portainer_webhook_url]
        if resolved_portainer_webhook_url
        else build_portainer_webhook_urls_from_token(
            host=resolved_host,
            https_port=resolved_portainer_https_port,
            webhook_token=resolved_portainer_token,
        )
    )

    log_step("Triggering Portainer webhook", icon="🪝")
    trigger_portainer_webhook(
        urls=webhook_urls,
        insecure=resolved_portainer_webhook_insecure,
        has_api_auth=has_portainer_api_auth,
    )

    print("[ubuntu-deploy] ✅ Done.")


if __name__ == "__main__":
    main()
