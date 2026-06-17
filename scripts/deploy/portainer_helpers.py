"""Helper functions for interacting with Portainer."""

from __future__ import annotations

import shlex
import time
from typing import Callable, Literal

import requests

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


def _format_portainer_api_error(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""

    message = str(payload.get("message") or "").strip()
    details = str(payload.get("details") or "").strip()
    if message and details and details != message:
        return f"{message}: {details}"
    return message or details


def _portainer_base_url(*, host: str, https_port: int) -> str:
    hostname = extract_ssh_hostname(host).strip()
    return f"https://{hostname}:{https_port}"


def resolve_portainer_endpoint_id(
    *,
    host: str,
    https_port: int,
    insecure: bool,
    endpoint_id: str,
    access_token: str,
) -> str:
    """Resolve the Portainer endpoint id, preferring the configured value."""
    desired_endpoint = endpoint_id.strip()
    if desired_endpoint:
        return desired_endpoint

    headers = _portainer_auth_headers(access_token=access_token)
    if not headers:
        raise SystemExit("PORTAINER_ACCESS_TOKEN is required to resolve Portainer endpoint id")

    base_url = _portainer_base_url(host=host, https_port=https_port)
    endpoints_resp = requests.get(f"{base_url}/api/endpoints", headers=headers, verify=not insecure, timeout=20)
    endpoints_resp.raise_for_status()
    endpoints_payload = endpoints_resp.json()
    if not isinstance(endpoints_payload, list) or not endpoints_payload:
        error_text = _format_portainer_api_error(endpoints_payload)
        if error_text:
            raise SystemExit(f"Portainer /api/endpoints returned an unexpected payload: {error_text}")
        raise SystemExit("No Portainer endpoints found")

    for endpoint in endpoints_payload:
        if not isinstance(endpoint, dict):
            continue
        endpoint_name = str(endpoint.get("Name") or endpoint.get("name") or "").strip().lower()
        endpoint_url = str(endpoint.get("URL") or endpoint.get("url") or "").strip().lower()
        if endpoint_name == "local" or endpoint_url.startswith("unix://"):
            local_endpoint_id = str(endpoint.get("Id") or endpoint.get("id") or "").strip()
            if local_endpoint_id:
                return local_endpoint_id

    first_endpoint = endpoints_payload[0]
    if isinstance(first_endpoint, dict):
        first_endpoint_id = str(first_endpoint.get("Id") or first_endpoint.get("id") or "").strip()
        if first_endpoint_id:
            return first_endpoint_id

    raise SystemExit("Unable to determine Portainer endpoint id; set PORTAINER_ENDPOINT_ID")


def _container_belongs_to_stack(container_payload: object, stack_name: str) -> bool:
    if not isinstance(container_payload, dict):
        return False
    labels = container_payload.get("Labels") or container_payload.get("labels") or {}
    if not isinstance(labels, dict):
        labels = {}

    label_values = {
        str(labels.get("com.docker.compose.project") or "").strip(),
        str(labels.get("com.docker.stack.namespace") or "").strip(),
        str(labels.get("io.portainer.stack.name") or "").strip(),
    }
    if stack_name in label_values:
        return True

    names = container_payload.get("Names") or container_payload.get("names") or []
    if isinstance(names, list):
        normalized_names = [str(name).strip().lstrip("/") for name in names]
        return any(name == stack_name or name.startswith(f"{stack_name}-") or name.startswith(f"{stack_name}_") for name in normalized_names)

    return False


def list_portainer_stack_containers(
    *,
    host: str,
    https_port: int,
    insecure: bool,
    endpoint_id: str,
    access_token: str,
    stack_name: str,
) -> list[dict[str, object]]:
    """List containers belonging to a Portainer stack via Docker proxy API."""
    resolved_endpoint_id = resolve_portainer_endpoint_id(
        host=host,
        https_port=https_port,
        insecure=insecure,
        endpoint_id=endpoint_id,
        access_token=access_token,
    )
    headers = _portainer_auth_headers(access_token=access_token)
    base_url = _portainer_base_url(host=host, https_port=https_port)
    resp = requests.get(
        f"{base_url}/api/endpoints/{resolved_endpoint_id}/docker/containers/json",
        headers=headers,
        params={"all": "true"},
        verify=not insecure,
        timeout=20,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, list):
        error_text = _format_portainer_api_error(payload)
        if error_text:
            raise SystemExit(f"Portainer Docker container list returned an unexpected payload: {error_text}")
        raise SystemExit("Unexpected Portainer Docker container list response format")

    return [container for container in payload if _container_belongs_to_stack(container, stack_name)]


def set_portainer_stack_containers_state(
    *,
    host: str,
    https_port: int,
    insecure: bool,
    endpoint_id: str,
    access_token: str,
    stack_name: str,
    action: Literal["start", "stop"],
) -> list[str]:
    """Start or stop all containers belonging to a Portainer stack."""
    containers = list_portainer_stack_containers(
        host=host,
        https_port=https_port,
        insecure=insecure,
        endpoint_id=endpoint_id,
        access_token=access_token,
        stack_name=stack_name,
    )
    if not containers:
        raise SystemExit(f"No containers found for Portainer stack '{stack_name}'")

    resolved_endpoint_id = resolve_portainer_endpoint_id(
        host=host,
        https_port=https_port,
        insecure=insecure,
        endpoint_id=endpoint_id,
        access_token=access_token,
    )
    headers = _portainer_auth_headers(access_token=access_token)
    base_url = _portainer_base_url(host=host, https_port=https_port)
    names: list[str] = []

    for container in containers:
        container_id = str(container.get("Id") or container.get("ID") or "").strip()
        if not container_id:
            continue
        raw_names = container.get("Names") or []
        name = container_id[:12]
        if isinstance(raw_names, list) and raw_names:
            name = str(raw_names[0]).strip().lstrip("/") or name
        names.append(name)
        response = requests.post(
            f"{base_url}/api/endpoints/{resolved_endpoint_id}/docker/containers/{container_id}/{action}",
            headers=headers,
            verify=not insecure,
            timeout=20,
        )
        if int(response.status_code) not in {204, 304}:
            details = str(response.text or "").strip().replace("\n", " ")[:300]
            raise SystemExit(f"Failed to {action} container {name}: {response.status_code} {details}")

    return names


def extract_ssh_hostname(host: str) -> str:
    return host.split("@", 1)[1] if "@" in host else host


def resolve_portainer_webhook_url_via_api(
    *,
    host: str,
    https_port: int,
    insecure: bool,
    stack_name: str,
    endpoint_id: str,
    access_token: str,
    stack_file_content: str,
    ssh_run_fn: Callable[[str], None] | None = None,
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
        error_text = _format_portainer_api_error(stacks_payload)
        if error_text:
            raise SystemExit(f"Portainer /api/stacks returned an unexpected payload: {error_text}")
        raise SystemExit("Unexpected Portainer /api/stacks response format")

    desired_name = stack_name.strip()

    endpoints_resp = requests.get(f"{base_url}/api/endpoints", headers=headers, verify=not insecure, timeout=20)
    endpoints_resp.raise_for_status()
    endpoints_payload = endpoints_resp.json()
    if not isinstance(endpoints_payload, list) or not endpoints_payload:
        error_text = _format_portainer_api_error(endpoints_payload)
        if error_text:
            raise SystemExit(f"Portainer /api/endpoints returned an unexpected payload: {error_text}")
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

    cleanup_names = _extract_container_names(stack_file_content)
    if ssh_run_fn:
        for container_name in cleanup_names:
            ssh_run_fn(f"docker rm -f {shlex.quote(container_name)} >/dev/null 2>&1 || true")
    else:
        for container_name in cleanup_names:
            del_url = f"{base_url}/api/endpoints/{desired_endpoint}/docker/containers/{container_name}?force=true"
            try:
                requests.delete(del_url, headers=headers, verify=not insecure, timeout=20)
            except Exception:
                pass

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


def is_portainer_access_token_valid(
    *,
    host: str,
    https_port: int,
    insecure: bool,
    access_token: str,
    retry_count: int = 6,
    retry_delay_seconds: float = 5.0,
) -> bool:
    """Return whether the provided Portainer access token is currently valid.

    A 401 means the token is invalid/expired. Other non-2xx responses are treated
    as hard failures because they indicate connectivity or server-side issues.
    """

    headers = _portainer_auth_headers(access_token=access_token)
    if not headers:
        return False

    hostname = extract_ssh_hostname(host).strip()
    base_url = f"https://{hostname}:{https_port}"

    attempts = max(1, int(retry_count))
    transient_status_codes = {502, 503, 504}
    last_transient_error = ""

    for attempt_index in range(attempts):
        try:
            resp = requests.get(f"{base_url}/api/endpoints", headers=headers, verify=not insecure, timeout=20)
        except requests.RequestException as exc:
            last_transient_error = str(exc)
            if attempt_index < attempts - 1:
                time.sleep(retry_delay_seconds)
                continue
            raise SystemExit(f"Portainer API did not become ready after {attempts} attempt(s): {last_transient_error}")

        status_code = int(resp.status_code)
        if status_code == 401:
            return False
        if status_code in transient_status_codes:
            details = str(getattr(resp, "text", "") or "").strip().replace("\n", " ")[:200]
            last_transient_error = f"HTTP {status_code}" + (f": {details}" if details else "")
            if attempt_index < attempts - 1:
                time.sleep(retry_delay_seconds)
                continue
            raise SystemExit(f"Portainer API did not become ready after {attempts} attempt(s): {last_transient_error}")

        resp.raise_for_status()

        payload = resp.json()
        if not isinstance(payload, list):
            error_text = _format_portainer_api_error(payload)
            if error_text:
                raise SystemExit(f"Portainer /api/endpoints returned an unexpected payload: {error_text}")
            raise SystemExit("Unexpected Portainer /api/endpoints response format")
        return True

    raise SystemExit(f"Portainer API did not become ready after {attempts} attempt(s): {last_transient_error}")


def build_portainer_webhook_urls_from_token(*, host: str, https_port: int, webhook_token: str) -> list[str]:
    hostname = extract_ssh_hostname(host).strip()
    token = webhook_token.strip()
    return [
        f"https://{hostname}:{https_port}/api/stacks/webhooks/{token}",
        f"https://{hostname}:{https_port}/api/webhooks/{token}",
    ]


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
                "Portainer webhook returned 404 for all known endpoints and no Portainer access token is configured. "
                "Set PORTAINER_ACCESS_TOKEN in .env.deploy.secrets "
                "so the script can auto-resolve/create the correct stack webhook."
            )
        raise SystemExit(
            "Portainer webhook returned 404 for all known endpoints even after access-token-assisted resolution. "
            "Verify PORTAINER_STACK_NAME/PORTAINER_ENDPOINT_ID and ensure the stack exists in Portainer."
        )
    if last_error:
        raise SystemExit(last_error)
    raise SystemExit("Portainer webhook trigger failed")


def _extract_container_names(stack_content: str) -> list[str]:
    import yaml
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
        "set -e; "
        "docker network inspect caddy >/dev/null 2>&1 || docker network create caddy >/dev/null; "
        "docker volume create portainer_data >/dev/null; "
        "docker pull portainer/portainer-ce:latest >/dev/null; "
        "desired_image_id=$(docker image inspect --format '{{.Id}}' portainer/portainer-ce:latest); "
        "portainer_on_caddy() { "
        "docker inspect --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' portainer 2>/dev/null | grep -Fxq caddy; "
        "}; "
        "portainer_has_host_ports() { "
        "[ \"$(docker inspect --format '{{len .HostConfig.PortBindings}}' portainer 2>/dev/null || echo 0)\" != \"0\" ]; "
        "}; "
        "run_portainer() { "
        "docker run -d --name portainer --restart=unless-stopped --network caddy "
        "-v /var/run/docker.sock:/var/run/docker.sock -v portainer_data:/data "
        "portainer/portainer-ce:latest >/dev/null; "
        "}; "
        "if docker ps -a --format '{{.Names}}' | grep -Fxq portainer; then "
        "existing_image_id=$(docker inspect --format '{{.Image}}' portainer 2>/dev/null || true); "
        "if [ \"$existing_image_id\" != \"$desired_image_id\" ]; then "
        "echo '[ubuntu-deploy] Updating Portainer to latest image'; "
        "docker rm -f portainer >/dev/null; "
        "run_portainer; "
        "elif ! portainer_on_caddy; then "
        "echo '[ubuntu-deploy] Recreating Portainer on caddy network'; "
        "docker rm -f portainer >/dev/null; "
        "run_portainer; "
        "elif portainer_has_host_ports; then "
        "echo '[ubuntu-deploy] Recreating Portainer without host port bindings'; "
        "docker rm -f portainer >/dev/null; "
        "run_portainer; "
        "elif docker ps --format '{{.Names}}' | grep -Fxq portainer; then "
        "echo '[ubuntu-deploy] Portainer already running with latest image'; "
        "else "
        "echo '[ubuntu-deploy] Starting existing Portainer container'; "
        "docker start portainer >/dev/null; "
        "fi; "
        "else "
        "echo '[ubuntu-deploy] Creating Portainer container'; "
        "run_portainer; "
        "fi; "
        "portainer_on_caddy"
    )
