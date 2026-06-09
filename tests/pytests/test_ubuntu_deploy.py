import subprocess
from pathlib import Path

import pytest

from scripts.deploy import deploy_log
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
    default_portainer_https_port,
    extract_stack_images,
    ghcr_images_from_stack,
    parse_boolish,
    prepare_stack_content_for_portainer,
    register_storage_manager_registrations,
    resolve_portainer_api_host,
    resolve_deploy_target,
    resolve_network_host_from_ssh_target,
    rewrite_rendered_paths_for_remote,
    rewrite_staging_container_names_for_portainer,
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
    list_portainer_stack_containers,
    portainer_ensure_running_remote_cmd,
    set_portainer_stack_containers_state,
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


def test_resolve_deploy_target_treats_swap_as_production_promotion():
    assert resolve_deploy_target(prod=False, swap=True) == "production"


def test_resolve_portainer_api_host_derives_portainer_subdomain_from_public_domain(tmp_path, monkeypatch):
    (tmp_path / ".env.deploy").write_text("PUBLIC_DOMAIN=protected-container.zenia.eu\n")
    monkeypatch.delenv("PUBLIC_DOMAIN", raising=False)

    assert resolve_portainer_api_host(repo_root=tmp_path, ssh_host="ronny@192.168.1.241") == "portainer.zenia.eu"


def test_default_portainer_https_port_uses_443_for_public_portainer_domain():
    assert default_portainer_https_port(portainer_host="portainer.zenia.eu", ssh_host="ronny@192.168.1.241") == 443


def test_swap_promotes_to_production_stack_and_stops_only_staging(tmp_path, monkeypatch):
    (tmp_path / "docker").mkdir()
    (tmp_path / "docker" / "docker-compose.yml").write_text("services: {}\n")
    (tmp_path / "docker" / "docker-compose.ubuntu.yml").write_text("services: {}\n")
    (tmp_path / ".env.deploy").write_text(
        "\n".join(
            [
                "UBUNTU_SSH_HOST=deploy@example.com",
                "UBUNTU_REMOTE_DIR=/srv/prod",
                "PUBLIC_DOMAIN=protected-container.zenia.eu",
                "STAGING_PUBLIC_DOMAIN=staging-protected-container.zenia.eu",
                "APP_IMAGE=example/app:staged",
                "PORTAINER_STACK_NAME=protected-container",
                "PORTAINER_ENDPOINT_ID=1",
                "STAGING_PORTAINER_STACK_NAME=staging-protected-container",
            ]
        )
        + "\n"
    )
    (tmp_path / ".env.deploy.secrets").write_text("PORTAINER_ACCESS_TOKEN=token-123\n")

    for key in [
        "UBUNTU_SSH_HOST",
        "UBUNTU_REMOTE_DIR",
        "PUBLIC_DOMAIN",
        "STAGING_PUBLIC_DOMAIN",
        "APP_IMAGE",
        "PORTAINER_STACK_NAME",
        "PORTAINER_ENDPOINT_ID",
        "STAGING_PORTAINER_STACK_NAME",
        "PORTAINER_ACCESS_TOKEN",
        "PORTAINER_WEBHOOK_URL",
        "PORTAINER_WEBHOOK_TOKEN",
        "UBUNTU_COMPOSE_FILES",
    ]:
        monkeypatch.delenv(key, raising=False)

    class DummyHooks:
        def call(self, hook_name, *args, **kwargs):
            if hook_name == "configure_deploy_log":
                settings = args[2]
                settings.versioning_enabled = False
                settings.csv_path = Path("out/custom/deploy_log.csv")
            return None

    class DummyResult:
        returncode = 0
        stdout = "hostname 192.168.1.241\n"
        stderr = ""

    def fake_run(*args, **kwargs):
        return DummyResult()

    def fake_render_compose_stack_content(*, repo_root, compose_files):
        return "services:\n  app:\n    image: example/app:staged\n"

    deployed_stack_names: list[str] = []
    state_calls: list[tuple[str, str]] = []

    def fake_resolve_portainer_webhook_url_via_api(**kwargs):
        deployed_stack_names.append(kwargs["stack_name"])
        return ""

    def fake_list_portainer_stack_containers(**kwargs):
        if kwargs["stack_name"] == "staging-protected-container":
            return [{"Id": "staging123", "Names": ["/staging-protected-container"]}]
        return []

    def fake_set_portainer_stack_containers_state(**kwargs):
        state_calls.append((kwargs["stack_name"], kwargs["action"]))
        return [kwargs["stack_name"]]

    monkeypatch.setattr("scripts.deploy.ubuntu_deploy.deploy_hooks.load_hooks", lambda **kwargs: DummyHooks())
    monkeypatch.setattr("scripts.deploy.ubuntu_deploy.subprocess.run", fake_run)
    monkeypatch.setattr("scripts.deploy.ubuntu_deploy._run", lambda *args, **kwargs: None)
    monkeypatch.setattr("scripts.deploy.ubuntu_deploy.render_compose_stack_content", fake_render_compose_stack_content)
    monkeypatch.setattr("scripts.deploy.ubuntu_deploy.portainer_helpers.is_portainer_access_token_valid", lambda **kwargs: True)
    monkeypatch.setattr("scripts.deploy.ubuntu_deploy.portainer_helpers.resolve_portainer_webhook_url_via_api", fake_resolve_portainer_webhook_url_via_api)
    monkeypatch.setattr("scripts.deploy.ubuntu_deploy.portainer_helpers.list_portainer_stack_containers", fake_list_portainer_stack_containers)
    monkeypatch.setattr("scripts.deploy.ubuntu_deploy.portainer_helpers.set_portainer_stack_containers_state", fake_set_portainer_stack_containers_state)
    monkeypatch.setattr("scripts.deploy.ubuntu_deploy.caddy_register.ensure_caddy_registration", lambda **kwargs: None)
    monkeypatch.setattr("scripts.deploy.ubuntu_deploy.caddy_register.is_domain_registered", lambda **kwargs: True)
    deploy_record_targets: list[str] = []
    deploy_record_settings: list[deploy_log.DeployLogSettings] = []

    def fake_append_deploy_record_with_settings(
        *,
        repo_root: Path,
        settings: deploy_log.DeployLogSettings,
        target: str,
        stack_name: str,
        domain: str,
        image: str,
        status: str,
    ) -> Path:
        deploy_record_targets.append(target)
        deploy_record_settings.append(settings)
        return repo_root / "deploy_log.csv"

    monkeypatch.setattr(
        "scripts.deploy.ubuntu_deploy.deploy_log.append_deploy_record_with_settings",
        fake_append_deploy_record_with_settings,
    )
    monkeypatch.setattr("scripts.deploy.ubuntu_deploy.deploy_log._read_app_version", lambda repo_root: "1.2.3")

    main(["--swap"], repo_root_override=tmp_path)

    assert deployed_stack_names == ["protected-container"]
    assert state_calls == [("staging-protected-container", "stop")]
    assert deploy_record_targets == ["swap"]
    assert deploy_record_settings[0].versioning_enabled is False
    assert deploy_record_settings[0].csv_path == Path("out/custom/deploy_log.csv")


def test_main_requires_changelog_entry_before_remote_work(tmp_path, monkeypatch):
    (tmp_path / "docker").mkdir()
    (tmp_path / "docker" / "docker-compose.yml").write_text("services: {}\n")
    (tmp_path / "docker" / "docker-compose.ubuntu.yml").write_text("services: {}\n")
    (tmp_path / ".env").write_text("APP_VERSION=1.2.3\n")
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [1.2.3] - 2026-06-09\n")
    (tmp_path / ".env.deploy").write_text(
        "\n".join(
            [
                "UBUNTU_SSH_HOST=deploy@example.com",
                "UBUNTU_BUILD_PUSH=false",
                "PUBLIC_DOMAIN=protected-container.zenia.eu",
                "STAGING_REMOTE_DIR=/srv/staging",
                "STAGING_PUBLIC_DOMAIN=staging-protected-container.zenia.eu",
                "APP_IMAGE=example/app:staged",
                "PORTAINER_ENDPOINT_ID=1",
                "STAGING_PORTAINER_STACK_NAME=staging-protected-container",
            ]
        )
        + "\n"
    )
    (tmp_path / ".env.deploy.secrets").write_text("PORTAINER_ACCESS_TOKEN=token-123\n")

    for key in [
        "UBUNTU_SSH_HOST",
        "UBUNTU_BUILD_PUSH",
        "PUBLIC_DOMAIN",
        "STAGING_REMOTE_DIR",
        "STAGING_PUBLIC_DOMAIN",
        "APP_IMAGE",
        "PORTAINER_ENDPOINT_ID",
        "STAGING_PORTAINER_STACK_NAME",
        "PORTAINER_ACCESS_TOKEN",
        "PORTAINER_WEBHOOK_URL",
        "PORTAINER_WEBHOOK_TOKEN",
        "UBUNTU_COMPOSE_FILES",
    ]:
        monkeypatch.delenv(key, raising=False)

    class DummyHooks:
        def call(self, hook_name, *args, **kwargs):
            return None

    remote_calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        remote_calls.append(cmd)
        raise AssertionError("remote commands should not run before changelog validation")

    def fake_render_compose_stack_content(*, repo_root, compose_files):
        return "services:\n  app:\n    image: example/app:staged\n"

    monkeypatch.setattr("scripts.deploy.ubuntu_deploy.deploy_hooks.load_hooks", lambda **kwargs: DummyHooks())
    monkeypatch.setattr("scripts.deploy.ubuntu_deploy.render_compose_stack_content", fake_render_compose_stack_content)
    monkeypatch.setattr("scripts.deploy.ubuntu_deploy.deploy_log._get_git_ref", lambda repo_root: "new-git-ref")
    monkeypatch.setattr("scripts.deploy.ubuntu_deploy.subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match="Run /changelog"):
        main([], repo_root_override=tmp_path)

    assert remote_calls == []


def test_rewrite_staging_container_names_for_portainer_avoids_production_name_collisions():
    stack_content = """
services:
  app:
    x-deploy-role: app
    container_name: protected-container
    image: ghcr.io/example/app:latest
  storage-manager:
    container_name: storage-manager
    image: ghcr.io/example/storage-manager:latest
"""

    rewritten = rewrite_staging_container_names_for_portainer(
        stack_content=stack_content,
        stack_name="staging-protected-container",
    )

    assert "container_name: staging-protected-container\n" in rewritten
    assert "container_name: staging-protected-container-storage-manager\n" in rewritten
    assert "container_name: protected-container\n" not in rewritten
    assert "container_name: storage-manager\n" not in rewritten


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


def test_list_portainer_stack_containers_filters_by_compose_project_label(monkeypatch):
    class DummyResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return [
                {
                    "Id": "abc123",
                    "Names": ["/staging-protected-container"],
                    "Labels": {"com.docker.compose.project": "staging-protected-container"},
                },
                {
                    "Id": "def456",
                    "Names": ["/protected-container"],
                    "Labels": {"com.docker.compose.project": "protected-container"},
                },
            ]

    calls: list[str] = []

    def fake_get(url, headers, **kwargs):
        calls.append(url)
        return DummyResponse()

    monkeypatch.setattr("scripts.deploy.portainer_helpers.requests.get", fake_get)

    containers = list_portainer_stack_containers(
        host="192.168.1.45",
        https_port=9943,
        insecure=True,
        endpoint_id="1",
        access_token="token-123",
        stack_name="staging-protected-container",
    )

    assert [container["Id"] for container in containers] == ["abc123"]
    assert calls == ["https://192.168.1.45:9943/api/endpoints/1/docker/containers/json"]


def test_set_portainer_stack_containers_state_posts_start_to_each_container(monkeypatch):
    class ListResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return [
                {
                    "Id": "abc123",
                    "Names": ["/staging-protected-container"],
                    "Labels": {"com.docker.compose.project": "staging-protected-container"},
                },
                {
                    "Id": "def456",
                    "Names": ["/staging-protected-container-storage-manager"],
                    "Labels": {"com.docker.compose.project": "staging-protected-container"},
                },
            ]

    class PostResponse:
        status_code = 204
        text = ""

    posted_urls: list[str] = []

    def fake_get(url, headers, **kwargs):
        return ListResponse()

    def fake_post(url, headers, **kwargs):
        posted_urls.append(url)
        return PostResponse()

    monkeypatch.setattr("scripts.deploy.portainer_helpers.requests.get", fake_get)
    monkeypatch.setattr("scripts.deploy.portainer_helpers.requests.post", fake_post)

    names = set_portainer_stack_containers_state(
        host="192.168.1.45",
        https_port=9943,
        insecure=True,
        endpoint_id="1",
        access_token="token-123",
        stack_name="staging-protected-container",
        action="start",
    )

    assert names == ["staging-protected-container", "staging-protected-container-storage-manager"]
    assert posted_urls == [
        "https://192.168.1.45:9943/api/endpoints/1/docker/containers/abc123/start",
        "https://192.168.1.45:9943/api/endpoints/1/docker/containers/def456/start",
    ]


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
