import subprocess
from pathlib import Path

import pytest

from scripts.deploy.ubuntu_deploy import (
    _coerce_label_value,
    _should_fallback_to_remote_compose,
    build_compose_config_cmd,
    build_docker_build_cmd,
    build_docker_push_cmd,
    build_remote_compose_deploy_cmd,
    build_rsync_cmd,
    build_ssh_connectivity_cmd,
    build_ssh_cmd,
    collect_storage_manager_registrations,
    extract_stack_images,
    ghcr_images_from_stack,
    parse_boolish,
    prepare_stack_content_for_portainer,
    register_storage_manager_registrations,
    resolve_network_host_from_ssh_target,
    rewrite_rendered_paths_for_remote,
    stack_has_service,
    main,
    read_deploy_key,
    read_deploy_secret_key,
    read_dotenv_key,
)
from scripts.deploy.portainer_helpers import (
    _extract_webhook_token,
    _extract_container_names,
    build_portainer_webhook_urls_from_token,
    build_portainer_webhook_url,
    extract_ssh_hostname,
    is_portainer_access_token_valid,
    portainer_ensure_running_remote_cmd,
)


def test_build_rsync_cmd_basic():
    cmd = build_rsync_cmd(
        sources=[Path("/repo/docker/docker-compose.yml"), Path("/repo/docker")],
        host="user@host",
        remote_dir=Path("/opt/protected-container"),
    )
    assert cmd[0] == "rsync"
    assert "user@host:/opt/protected-container/" in cmd


def test_build_compose_config_cmd_with_multiple_files():
    cmd = build_compose_config_cmd(compose_files=["docker/docker-compose.yml", "docker/docker-compose.ubuntu.yml"])
    assert cmd == [
        "docker",
        "compose",
        "-f",
        "docker/docker-compose.yml",
        "-f",
        "docker/docker-compose.ubuntu.yml",
        "config",
    ]


def test_build_remote_compose_deploy_cmd_contains_compose_variants_and_env_dir():
    cmd = build_remote_compose_deploy_cmd(
        remote_dir=Path("/home/ronny/containers/protected-container"),
        compose_files=["docker/docker-compose.yml", "docker/docker-compose.ubuntu.yml"],
    )

    assert "cd /home/ronny/containers/protected-container" in cmd
    assert "export ENV_DIR=/home/ronny/containers/protected-container" in cmd
    assert "docker compose -f docker/docker-compose.yml -f docker/docker-compose.ubuntu.yml pull" in cmd
    assert "docker compose -f docker/docker-compose.yml -f docker/docker-compose.ubuntu.yml up -d --remove-orphans" in cmd
    assert "docker-compose -f docker/docker-compose.yml -f docker/docker-compose.ubuntu.yml up -d --remove-orphans" in cmd


def test_build_docker_build_and_push_cmds():
    build_cmd = build_docker_build_cmd(
        app_image="ghcr.io/beejones/protected-container:latest",
        dockerfile="docker/Dockerfile",
        context_dir="docker",
    )
    push_cmd = build_docker_push_cmd(app_image="ghcr.io/beejones/protected-container:latest")
    assert build_cmd == [
        "docker",
        "build",
        "-f",
        "docker/Dockerfile",
        "-t",
        "ghcr.io/beejones/protected-container:latest",
        "docker",
    ]
    assert push_cmd == ["docker", "push", "ghcr.io/beejones/protected-container:latest"]


def test_build_ssh_cmd_basic():
    cmd = build_ssh_cmd(host="user@host", remote_command="echo hi")
    assert cmd == ["ssh", "user@host", "echo hi"]


def test_build_ssh_connectivity_cmd_basic():
    cmd = build_ssh_connectivity_cmd(host="user@host")
    assert cmd == ["ssh", "user@host", "echo SSH_OK"]


def test_should_fallback_to_remote_compose_on_portainer_init_timeout():
    assert _should_fallback_to_remote_compose(
        "Portainer /api/endpoints returned an unexpected payload: Administrator initialization timeout"
    ) is True
    assert _should_fallback_to_remote_compose("Portainer access token was rejected") is False


def test_swap_fails_before_stopping_production_when_staging_containers_missing(tmp_path, monkeypatch):
    (tmp_path / ".env.deploy").write_text(
        "\n".join(
            [
                "UBUNTU_SSH_HOST=deploy@example.com",
                "PUBLIC_DOMAIN=prod.example.com",
                "STAGING_PUBLIC_DOMAIN=staging.example.com",
                "UBUNTU_REMOTE_DIR=/srv/prod",
                "STAGING_REMOTE_DIR=/srv/staging",
            ]
        )
        + "\n"
    )

    for key in [
        "UBUNTU_SSH_HOST",
        "PUBLIC_DOMAIN",
        "STAGING_PUBLIC_DOMAIN",
        "UBUNTU_REMOTE_DIR",
        "STAGING_REMOTE_DIR",
        "UBUNTU_COMPOSE_FILES",
    ]:
        monkeypatch.delenv(key, raising=False)

    ssh_commands: list[str] = []

    class DummyResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, *args, **kwargs):
        if cmd == ["ssh", "-G", "deploy@example.com"]:
            return DummyResult()

        if isinstance(cmd, list) and cmd and cmd[0] == "ssh":
            remote_command = str(cmd[-1])
            ssh_commands.append(remote_command)
            if "/srv/staging" in remote_command and "ps -a -q" in remote_command:
                raise subprocess.CalledProcessError(
                    1,
                    cmd,
                    stderr="staging containers have not been created",
                )
            return DummyResult()

        return DummyResult()

    monkeypatch.setattr("scripts.deploy.ubuntu_deploy.subprocess.run", fake_run)

    with pytest.raises(SystemExit):
        main(["--swap"], repo_root_override=tmp_path)

    assert not any("cd /srv/prod" in cmd and " stop;" in cmd for cmd in ssh_commands)


def test_resolve_network_host_from_ssh_target_uses_ssh_g(monkeypatch):
    class DummyResult:
        returncode = 0
        stdout = "host ubuntu-server-01\nhostname 192.168.1.45\nuser ronny\n"

    def fake_run(cmd, check, capture_output, text):
        assert cmd == ["ssh", "-G", "ubuntu-server-01"]
        assert check is False
        assert capture_output is True
        assert text is True
        return DummyResult()

    monkeypatch.setattr("scripts.deploy.ubuntu_deploy.subprocess.run", fake_run)

    assert resolve_network_host_from_ssh_target("ubuntu-server-01") == "192.168.1.45"


def test_resolve_network_host_from_ssh_target_falls_back_to_plain_hostname(monkeypatch):
    class DummyResult:
        returncode = 255
        stdout = ""

    def fake_run(cmd, check, capture_output, text):
        return DummyResult()

    monkeypatch.setattr("scripts.deploy.ubuntu_deploy.subprocess.run", fake_run)

    assert resolve_network_host_from_ssh_target("ronny@ubuntu-server-01") == "ubuntu-server-01"


def test_portainer_ensure_running_remote_cmd_contains_expected_steps():
    out = portainer_ensure_running_remote_cmd(https_port=9943)
    assert "docker network inspect caddy" in out
    assert "docker ps --format '{{.Names}}'" in out
    assert "docker ps -a --format '{{.Names}}'" in out
    assert "docker start portainer" in out
    assert "docker run -d --name portainer" in out
    assert "docker network connect caddy portainer" in out
    assert "-p 9943:9443" in out


def test_extract_ssh_hostname_with_and_without_user():
    assert extract_ssh_hostname("ronny@192.168.1.45") == "192.168.1.45"
    assert extract_ssh_hostname("192.168.1.45") == "192.168.1.45"


def test_build_portainer_webhook_url_from_token():
    out = build_portainer_webhook_url(
        host="ronny@192.168.1.45",
        https_port=9943,
        webhook_token="abc123token",
    )
    assert out == "https://192.168.1.45:9943/api/stacks/webhooks/abc123token"


def test_build_portainer_webhook_urls_from_token_includes_fallback_endpoint():
    out = build_portainer_webhook_urls_from_token(
        host="ronny@192.168.1.45",
        https_port=9943,
        webhook_token="abc123token",
    )
    assert out == [
        "https://192.168.1.45:9943/api/stacks/webhooks/abc123token",
        "https://192.168.1.45:9943/api/webhooks/abc123token",
    ]


def test_is_portainer_access_token_valid_true_on_ok_response(monkeypatch):
    class DummyResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return [{"Id": 1, "Name": "local"}]

    def fake_get(url, headers, verify, timeout):
        assert url == "https://192.168.1.45:9943/api/endpoints"
        assert headers == {"X-API-Key": "token-123"}
        assert verify is True
        assert timeout == 20
        return DummyResponse()

    monkeypatch.setattr("scripts.deploy.portainer_helpers.requests.get", fake_get)

    assert (
        is_portainer_access_token_valid(
            host="ronny@192.168.1.45",
            https_port=9943,
            insecure=False,
            access_token="token-123",
        )
        is True
    )


def test_is_portainer_access_token_valid_false_on_401(monkeypatch):
    class DummyResponse:
        status_code = 401

        def raise_for_status(self):
            return None

        def json(self):
            return []

    def fake_get(url, headers, verify, timeout):
        return DummyResponse()

    monkeypatch.setattr("scripts.deploy.portainer_helpers.requests.get", fake_get)

    assert (
        is_portainer_access_token_valid(
            host="ronny@192.168.1.45",
            https_port=9943,
            insecure=True,
            access_token="expired",
        )
        is False
    )


def test_is_portainer_access_token_valid_surfaces_portainer_message(monkeypatch):
    class DummyResponse:
        status_code = 303

        def raise_for_status(self):
            return None

        def json(self):
            return {"message": "Administrator initialization timeout", "details": "Administrator initialization timeout"}

    def fake_get(url, headers, verify, timeout):
        return DummyResponse()

    monkeypatch.setattr("scripts.deploy.portainer_helpers.requests.get", fake_get)

    try:
        is_portainer_access_token_valid(
            host="ronny@192.168.1.45",
            https_port=9943,
            insecure=True,
            access_token="token-123",
        )
    except SystemExit as exc:
        assert "Administrator initialization timeout" in str(exc)
    else:
        raise AssertionError("Expected SystemExit")


def test_read_deploy_secret_key_reads_token(tmp_path: Path):
    repo_root = tmp_path
    (repo_root / ".env.deploy.secrets").write_text("PORTAINER_WEBHOOK_TOKEN=from_file\n", encoding="utf-8")
    out = read_deploy_secret_key(repo_root=repo_root, key="PORTAINER_WEBHOOK_TOKEN")
    assert out == "from_file"


def test_read_deploy_secret_key_missing_file_returns_empty(tmp_path: Path):
    out = read_deploy_secret_key(repo_root=tmp_path, key="PORTAINER_WEBHOOK_TOKEN")
    assert out == ""


def test_read_deploy_key_reads_ubuntu_host(tmp_path: Path):
    repo_root = tmp_path
    (repo_root / ".env.deploy").write_text("UBUNTU_SSH_HOST=ronny@192.168.1.45\n", encoding="utf-8")
    out = read_deploy_key(repo_root=repo_root, key="UBUNTU_SSH_HOST")
    assert out == "ronny@192.168.1.45"


def test_read_deploy_key_reads_remote_dir(tmp_path: Path):
    repo_root = tmp_path
    (repo_root / ".env.deploy").write_text("UBUNTU_REMOTE_DIR=/home/ronny/containers/protected-container\n", encoding="utf-8")
    out = read_deploy_key(repo_root=repo_root, key="UBUNTU_REMOTE_DIR")
    assert out == "/home/ronny/containers/protected-container"


def test_read_dotenv_key_missing_file_returns_empty(tmp_path: Path):
    out = read_dotenv_key(dotenv_path=tmp_path / "missing.env", key="ANY_KEY")
    assert out == ""


def test_parse_boolish_truthy_falsey_and_default():
    assert parse_boolish("true") is True
    assert parse_boolish("yes") is True
    assert parse_boolish("1") is True
    assert parse_boolish("false") is False
    assert parse_boolish("0") is False
    assert parse_boolish("", default=True) is True
    assert parse_boolish("not-a-bool", default=False) is False


def test_extract_webhook_token_from_common_shapes():
    assert _extract_webhook_token({"Webhook": "abc"}) == "abc"
    assert _extract_webhook_token({"token": "def"}) == "def"
    assert _extract_webhook_token({"data": {"webhookToken": "ghi"}}) == "ghi"
    assert _extract_webhook_token([{"x": 1}, {"WebhookToken": "jkl"}]) == "jkl"


def test_prepare_stack_content_for_portainer_replaces_app_build_with_image():
    stack_content = """
services:
    app:
        build:
            context: /tmp/repo/docker
        environment:
            A: B
    caddy:
        image: caddy:2-alpine
"""
    out = prepare_stack_content_for_portainer(
        stack_content=stack_content,
        app_image="ghcr.io/beejones/protected-container:latest",
    )
    assert "build:" not in out
    assert "image: ghcr.io/beejones/protected-container:latest" in out


def test_prepare_stack_content_for_portainer_errors_on_remaining_build_service():
    stack_content = """
services:
    worker:
        build:
            context: /tmp/repo/worker
"""
    try:
        prepare_stack_content_for_portainer(stack_content=stack_content, app_image="")
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert "services still use build contexts" in str(exc)


def test_extract_container_names_reads_service_container_names():
    stack_content = """
services:
    app:
        container_name: protected-container
    caddy:
        container_name: tls-proxy
    worker:
        image: busybox
"""
    out = _extract_container_names(stack_content)
    assert out == ["protected-container", "tls-proxy"]


def test_rewrite_rendered_paths_for_remote_replaces_local_repo_root():
    stack_content = "volumes:\n  - /home/ronny/dev/protected-azure-container/.env:/home/coder/.env:ro\n"
    out = rewrite_rendered_paths_for_remote(
        stack_content=stack_content,
        local_repo_root=Path("/home/ronny/dev/protected-azure-container"),
        remote_dir=Path("/home/ronny/containers/protected-container"),
    )
    assert "/home/ronny/dev/protected-azure-container" not in out
    assert "/home/ronny/containers/protected-container/.env" in out


def test_collect_storage_manager_registrations_from_mapping_labels():
    stack_content = """
services:
  app:
    labels:
      storage-manager.0.volume: protected-container_logs
      storage-manager.0.path: /
      storage-manager.0.algorithm: remove_before_date
      storage-manager.0.max_age_days: "14"
      storage-manager.0.description: Keep 14 days
      storage-manager.1.volume: camera-footage
      storage-manager.1.path: /recordings
      storage-manager.1.algorithm: max_size
      storage-manager.1.max_bytes: "5368709120"
  worker:
    labels:
      other.label: value
"""
    out = collect_storage_manager_registrations(stack_content=stack_content)
    assert len(out) == 2

    first = out[0]
    assert first["source_service"] == "app"
    assert first["source_index"] == 0
    assert first["volume_name"] == "protected-container_logs"
    assert first["path"] == "/"
    assert first["algorithm"] == "remove_before_date"
    assert first["description"] == "Keep 14 days"
    assert first["params"]["max_age_days"] == 14

    second = out[1]
    assert second["volume_name"] == "camera-footage"
    assert second["path"] == "/recordings"
    assert second["algorithm"] == "max_size"
    assert second["params"]["max_bytes"] == 5368709120


def test_collect_storage_manager_registrations_from_list_labels():
    stack_content = """
services:
  app:
    labels:
      - storage-manager.0.volume=protected-container_logs
      - storage-manager.0.path=/
      - storage-manager.0.algorithm=remove_before_date
      - storage-manager.0.max_age_days=7
"""
    out = collect_storage_manager_registrations(stack_content=stack_content)
    assert len(out) == 1
    assert out[0]["params"]["max_age_days"] == 7


def test_collect_storage_manager_registrations_raises_for_missing_required_fields():
    stack_content = """
services:
  app:
    labels:
      storage-manager.0.volume: protected-container_logs
      storage-manager.0.path: /
"""
    try:
        collect_storage_manager_registrations(stack_content=stack_content)
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert "missing required fields" in str(exc)


def test_register_storage_manager_registrations_posts_to_api_endpoint(monkeypatch):
    calls: list[tuple[str, dict]] = []

    class DummyResponse:
        def __init__(self, status_code: int, text: str = ""):
            self.status_code = status_code
            self.text = text

    def fake_post(url, json, timeout):
        calls.append((url, json))
        assert timeout == 10
        return DummyResponse(201)

    monkeypatch.setattr("scripts.deploy.ubuntu_deploy.requests.post", fake_post)

    register_storage_manager_registrations(
        api_url="https://storage.example.com",
        registrations=[
            {
                "volume_name": "protected-container_logs",
                "path": "/",
                "algorithm": "remove_before_date",
                "params": {"max_age_days": 14},
                "description": "Keep 14 days",
                "source_service": "app",
                "source_index": 0,
            }
        ],
    )

    assert len(calls) == 1
    assert calls[0][0] == "https://storage.example.com/api/register"
    assert calls[0][1]["volume_name"] == "protected-container_logs"
    assert calls[0][1]["params"]["max_age_days"] == 14


def test_register_storage_manager_registrations_raises_on_http_error(monkeypatch):
    class DummyResponse:
        def __init__(self):
            self.status_code = 500
            self.text = "boom"

    def fake_post(url, json, timeout):
        return DummyResponse()

    monkeypatch.setattr("scripts.deploy.ubuntu_deploy.requests.post", fake_post)

    try:
        register_storage_manager_registrations(
            api_url="https://storage.example.com/api/register",
            registrations=[
                {
                    "volume_name": "protected-container_logs",
                    "path": "/",
                    "algorithm": "remove_before_date",
                    "params": {},
                    "source_service": "app",
                    "source_index": 0,
                }
            ],
        )
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert "Storage registration failed" in str(exc)


def test_coerce_label_value_scalar_and_non_scalar_behavior():
    assert _coerce_label_value("true") is True
    assert _coerce_label_value("14") == 14
    assert _coerce_label_value("3.14") == 3.14
    assert _coerce_label_value("null") is None

    assert _coerce_label_value("[1, 2, 3]") == "[1, 2, 3]"
    assert _coerce_label_value("{a: 1}") == "{a: 1}"


def test_extract_stack_images_reads_all_service_images():
        stack_content = """
services:
    app:
        image: ghcr.io/beejones/protected-container:latest
    caddy:
        image: caddy:2-alpine
    worker:
        image: busybox:latest
"""
        out = extract_stack_images(stack_content=stack_content)
        assert out == [
                "ghcr.io/beejones/protected-container:latest",
                "caddy:2-alpine",
                "busybox:latest",
        ]


def test_ghcr_images_from_stack_filters_and_deduplicates():
        stack_content = """
services:
    app:
        image: ghcr.io/beejones/protected-container:latest
    storage-manager:
        image: ghcr.io/beejones/protected-container-storage-manager:latest
    app-copy:
        image: ghcr.io/beejones/protected-container:latest
    caddy:
        image: caddy:2-alpine
"""
        out = ghcr_images_from_stack(stack_content=stack_content)
        assert out == [
                "ghcr.io/beejones/protected-container:latest",
                "ghcr.io/beejones/protected-container-storage-manager:latest",
        ]


def test_stack_has_service_detects_present_and_missing_service():
        stack_content = """
services:
    app:
        image: ghcr.io/beejones/protected-container:latest
    storage-manager:
        image: ghcr.io/beejones/protected-container-storage-manager:latest
"""
        assert stack_has_service(stack_content=stack_content, service_name="storage-manager") is True
        assert stack_has_service(stack_content=stack_content, service_name="missing") is False
