"""Unit tests for scripts/deploy/deploy_log.py."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.deploy.deploy_log import (
    CSV_COLUMNS,
    _increment_patch,
    _read_app_version,
    _write_app_version,
    append_deploy_record,
    get_csv_path,
)


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    """Create a minimal repo root with .env containing APP_VERSION."""
    env_file = tmp_path / ".env"
    env_file.write_text("APP_VERSION=1.2.3\nBASIC_AUTH_USER=admin\n")
    return tmp_path


class TestIncrementPatch:
    def test_normal(self) -> None:
        assert _increment_patch("1.2.3") == "1.2.4"

    def test_zero(self) -> None:
        assert _increment_patch("0.0.0") == "0.0.1"

    def test_large_patch(self) -> None:
        assert _increment_patch("1.0.99") == "1.0.100"

    def test_invalid_returns_unchanged(self) -> None:
        assert _increment_patch("not-semver") == "not-semver"

    def test_partial_returns_unchanged(self) -> None:
        assert _increment_patch("1.2") == "1.2"


class TestReadAppVersion:
    def test_reads_from_env(self, tmp_repo: Path) -> None:
        assert _read_app_version(tmp_repo) == "1.2.3"

    def test_missing_env_returns_default(self, tmp_path: Path) -> None:
        assert _read_app_version(tmp_path) == "0.0.0"

    def test_missing_key_returns_default(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("BASIC_AUTH_USER=admin\n")
        assert _read_app_version(tmp_path) == "0.0.0"


class TestWriteAppVersion:
    def test_updates_existing(self, tmp_repo: Path) -> None:
        _write_app_version(tmp_repo, "1.2.4")
        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.4" in content
        assert "BASIC_AUTH_USER=admin" in content

    def test_appends_when_missing(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("OTHER=val\n")
        _write_app_version(tmp_path, "2.0.0")
        content = (tmp_path / ".env").read_text()
        assert "APP_VERSION=2.0.0" in content

    def test_creates_file_when_absent(self, tmp_path: Path) -> None:
        _write_app_version(tmp_path, "0.1.0")
        content = (tmp_path / ".env").read_text()
        assert "APP_VERSION=0.1.0" in content


class TestGetCsvPath:
    def test_returns_expected_path(self, tmp_path: Path) -> None:
        result = get_csv_path(tmp_path)
        assert result == tmp_path / "out" / "deploy" / "deploy_log.csv"


class TestAppendDeployRecord:
    def test_creates_csv_with_header(self, tmp_repo: Path) -> None:
        csv_path = append_deploy_record(
            repo_root=tmp_repo,
            target="staging",
            stack_name="my-stack",
            domain="staging.example.com",
            image="ghcr.io/user/app:latest",
            status="success",
            git_ref="a" * 40,
            version="1.2.3",
        )
        assert csv_path.exists()
        rows = list(csv.reader(csv_path.open()))
        assert rows[0] == CSV_COLUMNS
        assert len(rows) == 2
        assert rows[1][3] == "staging"
        assert rows[1][4] == "my-stack"
        assert rows[1][5] == "staging.example.com"
        assert rows[1][6] == "ghcr.io/user/app:latest"
        assert rows[1][7] == "success"

    def test_writes_newest_record_below_header(self, tmp_repo: Path) -> None:
        append_deploy_record(
            repo_root=tmp_repo,
            target="staging",
            stack_name="s1",
            domain="d1",
            image="img1",
            status="success",
            git_ref="b" * 40,
            version="1.0.0",
        )
        append_deploy_record(
            repo_root=tmp_repo,
            target="production",
            stack_name="s2",
            domain="d2",
            image="img2",
            status="failed",
            git_ref="c" * 40,
            version="1.0.1",
        )
        csv_path = get_csv_path(tmp_repo)
        rows = list(csv.reader(csv_path.open()))
        # Header + 2 data rows
        assert len(rows) == 3
        assert rows[1][1] == "c" * 40
        assert rows[1][2] == "1.0.1"
        assert rows[1][3] == "production"
        assert rows[2][1] == "b" * 40
        assert rows[2][2] == "1.0.0"
        assert rows[2][3] == "staging"

    def test_production_success_increments_version(self, tmp_repo: Path) -> None:
        append_deploy_record(
            repo_root=tmp_repo,
            target="production",
            stack_name="prod-stack",
            domain="prod.example.com",
            image="img",
            status="success",
            git_ref="d" * 40,
        )
        # .env should now have APP_VERSION=1.2.4
        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.4" in content

    def test_staging_success_does_not_increment(self, tmp_repo: Path) -> None:
        append_deploy_record(
            repo_root=tmp_repo,
            target="staging",
            stack_name="stg-stack",
            domain="stg.example.com",
            image="img",
            status="success",
            git_ref="e" * 40,
        )
        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.3" in content

    def test_swap_success_for_new_git_ref_increments_version(self, tmp_repo: Path) -> None:
        csv_path = tmp_repo / "out" / "deploy" / "deploy_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            writer.writerow(["2026-05-18T00:00:00Z", "0" * 40, "1.2.3", "swap", "prod-stack", "prod.example.com", "img", "success"])

        csv_path = append_deploy_record(
            repo_root=tmp_repo,
            target="swap",
            stack_name="prod-stack",
            domain="prod.example.com",
            image="img",
            status="success",
            git_ref="1" * 40,
        )

        rows = list(csv.reader(csv_path.open()))
        assert rows[1][2] == "1.2.4"
        assert rows[1][3] == "swap"
        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.4" in content

    def test_swap_success_for_same_git_ref_does_not_increment_again(self, tmp_repo: Path) -> None:
        _write_app_version(tmp_repo, "1.2.4")
        csv_path = tmp_repo / "out" / "deploy" / "deploy_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            writer.writerow(["2026-05-18T00:00:00Z", "1" * 40, "1.2.4", "swap", "prod-stack", "prod.example.com", "img", "success"])

        csv_path = append_deploy_record(
            repo_root=tmp_repo,
            target="swap",
            stack_name="prod-stack",
            domain="prod.example.com",
            image="img",
            status="success",
            git_ref="1" * 40,
        )

        rows = list(csv.reader(csv_path.open()))
        assert rows[1][2] == "1.2.4"
        assert rows[1][3] == "swap"
        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.4" in content

    def test_production_failure_does_not_increment(self, tmp_repo: Path) -> None:
        append_deploy_record(
            repo_root=tmp_repo,
            target="production",
            stack_name="prod-stack",
            domain="prod.example.com",
            image="img",
            status="failed",
            git_ref="f" * 40,
        )
        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.3" in content

    def test_column_integrity(self, tmp_repo: Path) -> None:
        csv_path = append_deploy_record(
            repo_root=tmp_repo,
            target="swap",
            stack_name="stack",
            domain="dom",
            image="",
            status="success",
            git_ref="0" * 40,
            version="2.0.0",
        )
        rows = list(csv.reader(csv_path.open()))
        data = rows[1]
        # timestamp, git_ref, version, target, stack_name, domain, image, status
        assert len(data) == 8
        assert data[1] == "0" * 40
        assert data[2] == "2.0.0"
        assert data[3] == "swap"
        assert data[6] == ""
