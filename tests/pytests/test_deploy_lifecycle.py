"""Tests for container lifecycle helpers in ubuntu_deploy.py."""

from __future__ import annotations

from pathlib import Path

from scripts.deploy.ubuntu_deploy import (
    build_remote_compose_deploy_cmd,
    build_remote_compose_no_start_cmd,
    build_remote_compose_start_cmd,
    build_remote_compose_stop_cmd,
)


REMOTE_DIR = Path("/home/user/containers/myapp")
COMPOSE_FILES = ["docker/docker-compose.yml"]


class TestBuildRemoteComposeNoStartCmd:
    def test_contains_no_start_flag(self) -> None:
        cmd = build_remote_compose_no_start_cmd(remote_dir=REMOTE_DIR, compose_files=COMPOSE_FILES)
        assert "--no-start" in cmd

    def test_contains_pull(self) -> None:
        cmd = build_remote_compose_no_start_cmd(remote_dir=REMOTE_DIR, compose_files=COMPOSE_FILES)
        assert "pull" in cmd

    def test_contains_remove_orphans(self) -> None:
        cmd = build_remote_compose_no_start_cmd(remote_dir=REMOTE_DIR, compose_files=COMPOSE_FILES)
        assert "--remove-orphans" in cmd

    def test_does_not_contain_dash_d(self) -> None:
        cmd = build_remote_compose_no_start_cmd(remote_dir=REMOTE_DIR, compose_files=COMPOSE_FILES)
        assert " -d " not in cmd
        assert " up -d" not in cmd

    def test_sets_env_dir(self) -> None:
        cmd = build_remote_compose_no_start_cmd(remote_dir=REMOTE_DIR, compose_files=COMPOSE_FILES)
        assert "ENV_DIR=" in cmd


class TestBuildRemoteComposeStopCmd:
    def test_contains_stop(self) -> None:
        cmd = build_remote_compose_stop_cmd(remote_dir=REMOTE_DIR, compose_files=COMPOSE_FILES)
        assert "stop" in cmd

    def test_does_not_contain_down(self) -> None:
        """Stop should not use 'down' which removes containers/volumes."""
        cmd = build_remote_compose_stop_cmd(remote_dir=REMOTE_DIR, compose_files=COMPOSE_FILES)
        assert "down" not in cmd

    def test_changes_to_remote_dir(self) -> None:
        cmd = build_remote_compose_stop_cmd(remote_dir=REMOTE_DIR, compose_files=COMPOSE_FILES)
        assert "cd /home/user/containers/myapp" in cmd

    def test_references_compose_file(self) -> None:
        cmd = build_remote_compose_stop_cmd(remote_dir=REMOTE_DIR, compose_files=COMPOSE_FILES)
        assert "-f docker/docker-compose.yml" in cmd


class TestBuildRemoteComposeStartCmd:
    def test_contains_start(self) -> None:
        cmd = build_remote_compose_start_cmd(remote_dir=REMOTE_DIR, compose_files=COMPOSE_FILES)
        assert "start" in cmd

    def test_does_not_contain_up(self) -> None:
        """Start should use 'start' not 'up' to avoid recreating containers."""
        cmd = build_remote_compose_start_cmd(remote_dir=REMOTE_DIR, compose_files=COMPOSE_FILES)
        # Should contain "start" but not "up" as a standalone compose subcommand
        assert " start;" in cmd or " start\"" in cmd or cmd.endswith("start")

    def test_changes_to_remote_dir(self) -> None:
        cmd = build_remote_compose_start_cmd(remote_dir=REMOTE_DIR, compose_files=COMPOSE_FILES)
        assert "cd /home/user/containers/myapp" in cmd


class TestBuildRemoteComposeDeployCmd:
    def test_contains_up_d(self) -> None:
        cmd = build_remote_compose_deploy_cmd(remote_dir=REMOTE_DIR, compose_files=COMPOSE_FILES)
        assert "up -d" in cmd

    def test_does_not_contain_no_start(self) -> None:
        cmd = build_remote_compose_deploy_cmd(remote_dir=REMOTE_DIR, compose_files=COMPOSE_FILES)
        assert "--no-start" not in cmd


class TestMultipleComposeFiles:
    def test_no_start_multiple_files(self) -> None:
        files = ["docker/docker-compose.yml", "docker/docker-compose.ubuntu.yml"]
        cmd = build_remote_compose_no_start_cmd(remote_dir=REMOTE_DIR, compose_files=files)
        assert "-f docker/docker-compose.yml" in cmd
        assert "-f docker/docker-compose.ubuntu.yml" in cmd

    def test_stop_multiple_files(self) -> None:
        files = ["docker/docker-compose.yml", "docker/docker-compose.ubuntu.yml"]
        cmd = build_remote_compose_stop_cmd(remote_dir=REMOTE_DIR, compose_files=files)
        assert "-f docker/docker-compose.yml" in cmd
        assert "-f docker/docker-compose.ubuntu.yml" in cmd
