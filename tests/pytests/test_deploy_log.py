"""Unit tests for scripts/deploy/deploy_log.py."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.deploy.deploy_log import (
    CSV_COLUMNS,
    LEGACY_CSV_COLUMNS,
    DeployLogSettings,
    _increment_patch,
    _read_app_version,
    _write_app_version,
    append_deploy_record,
    append_deploy_record_with_settings,
    get_csv_path,
)


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    """Create a minimal repo root with .env containing APP_VERSION."""
    env_file = tmp_path / ".env"
    env_file.write_text("APP_VERSION=1.2.3\nBASIC_AUTH_USER=admin\n")
    changelog_file = tmp_path / "CHANGELOG.md"
    changelog_file.write_text("# Changelog\n\n## [1.2.4] - 2026-06-09\n")
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
            local_branch="feature/deploy-log-branch",
            version="1.2.3",
        )
        assert csv_path.exists()
        rows = list(csv.reader(csv_path.open()))
        assert rows[0] == CSV_COLUMNS
        assert len(rows) == 2
        assert rows[1][2] == "feature/deploy-log-branch"
        assert rows[1][4] == "staging"
        assert rows[1][5] == "my-stack"
        assert rows[1][6] == "staging.example.com"
        assert rows[1][7] == "ghcr.io/user/app:latest"
        assert rows[1][8] == "success"

    def test_writes_newest_record_below_header(self, tmp_repo: Path) -> None:
        append_deploy_record(
            repo_root=tmp_repo,
            target="staging",
            stack_name="s1",
            domain="d1",
            image="img1",
            status="success",
            git_ref="b" * 40,
            local_branch="main",
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
            local_branch="release/deploy",
            version="1.0.1",
        )
        csv_path = get_csv_path(tmp_repo)
        rows = list(csv.reader(csv_path.open()))
        # Header + 2 data rows
        assert len(rows) == 3
        assert rows[1][1] == "c" * 40
        assert rows[1][2] == "release/deploy"
        assert rows[1][3] == "1.0.1"
        assert rows[1][4] == "production"
        assert rows[2][1] == "b" * 40
        assert rows[2][2] == "main"
        assert rows[2][3] == "1.0.0"
        assert rows[2][4] == "staging"

    def test_legacy_rows_are_prefilled_with_main(self, tmp_repo: Path) -> None:
        csv_path = tmp_repo / "out" / "deploy" / "deploy_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(LEGACY_CSV_COLUMNS)
            writer.writerow(["2026-05-18T00:00:00Z", "0" * 40, "1.2.3", "swap", "prod-stack", "prod.example.com", "img", "success"])

        csv_path = append_deploy_record(
            repo_root=tmp_repo,
            target="staging",
            stack_name="stg-stack",
            domain="stg.example.com",
            image="img",
            status="success",
            git_ref="1" * 40,
            local_branch="feature/deploy-log-branch",
            version="1.2.4",
        )

        rows = list(csv.reader(csv_path.open()))
        assert rows[0] == CSV_COLUMNS
        assert rows[1][2] == "feature/deploy-log-branch"
        assert rows[2][1] == "0" * 40
        assert rows[2][2] == "main"
        assert rows[2][3] == "1.2.3"
        assert rows[2][4] == "swap"

    def test_production_success_increments_version(self, tmp_repo: Path) -> None:
        csv_path = append_deploy_record(
            repo_root=tmp_repo,
            target="production",
            stack_name="prod-stack",
            domain="prod.example.com",
            image="img",
            status="success",
            git_ref="d" * 40,
            local_branch="main",
        )
        rows = list(csv.reader(csv_path.open()))
        assert rows[1][3] == "1.2.4"
        # .env should now have APP_VERSION=1.2.4
        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.4" in content

    def test_staging_success_for_same_git_ref_does_not_increment_again(self, tmp_repo: Path) -> None:
        csv_path = tmp_repo / "out" / "deploy" / "deploy_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            writer.writerow(["2026-05-18T00:00:00Z", "e" * 40, "main", "1.2.3", "staging", "stg-stack", "stg.example.com", "img", "success"])

        append_deploy_record(
            repo_root=tmp_repo,
            target="staging",
            stack_name="stg-stack",
            domain="stg.example.com",
            image="img",
            status="success",
            git_ref="e" * 40,
            local_branch="main",
        )
        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.3" in content

    def test_staging_success_for_new_git_ref_increments_version(self, tmp_repo: Path) -> None:
        csv_path = tmp_repo / "out" / "deploy" / "deploy_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            writer.writerow(["2026-05-18T00:00:00Z", "0" * 40, "main", "1.2.3", "swap", "prod-stack", "prod.example.com", "img", "success"])

        csv_path = append_deploy_record(
            repo_root=tmp_repo,
            target="staging",
            stack_name="stg-stack",
            domain="stg.example.com",
            image="img",
            status="success",
            git_ref="1" * 40,
            local_branch="release/deploy",
        )

        rows = list(csv.reader(csv_path.open()))
        assert rows[1][3] == "1.2.4"
        assert rows[1][4] == "staging"
        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.4" in content

    def test_new_git_ref_increment_requires_changelog_entry(self, tmp_repo: Path) -> None:
        (tmp_repo / "CHANGELOG.md").write_text("# Changelog\n\n## [1.2.3] - 2026-06-08\n")

        with pytest.raises(RuntimeError, match="Run /changelog"):
            append_deploy_record(
                repo_root=tmp_repo,
                target="staging",
                stack_name="stg-stack",
                domain="stg.example.com",
                image="img",
                status="success",
                git_ref="1" * 40,
                local_branch="release/deploy",
            )

        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.3" in content
        assert not get_csv_path(tmp_repo).exists()

    def test_swap_success_for_new_git_ref_increments_version(self, tmp_repo: Path) -> None:
        csv_path = tmp_repo / "out" / "deploy" / "deploy_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            writer.writerow(["2026-05-18T00:00:00Z", "0" * 40, "main", "1.2.3", "swap", "prod-stack", "prod.example.com", "img", "success"])

        csv_path = append_deploy_record(
            repo_root=tmp_repo,
            target="swap",
            stack_name="prod-stack",
            domain="prod.example.com",
            image="img",
            status="success",
            git_ref="1" * 40,
            local_branch="release/deploy",
        )

        rows = list(csv.reader(csv_path.open()))
        assert rows[1][3] == "1.2.4"
        assert rows[1][4] == "swap"
        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.4" in content

    def test_swap_success_for_same_git_ref_does_not_increment_again(self, tmp_repo: Path) -> None:
        _write_app_version(tmp_repo, "1.2.4")
        csv_path = tmp_repo / "out" / "deploy" / "deploy_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            writer.writerow(["2026-05-18T00:00:00Z", "1" * 40, "main", "1.2.4", "swap", "prod-stack", "prod.example.com", "img", "success"])

        csv_path = append_deploy_record(
            repo_root=tmp_repo,
            target="swap",
            stack_name="prod-stack",
            domain="prod.example.com",
            image="img",
            status="success",
            git_ref="1" * 40,
            local_branch="release/deploy",
        )

        rows = list(csv.reader(csv_path.open()))
        assert rows[1][3] == "1.2.4"
        assert rows[1][4] == "swap"
        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.4" in content

    def test_swap_success_after_staging_same_git_ref_does_not_increment_again(self, tmp_repo: Path) -> None:
        _write_app_version(tmp_repo, "1.2.4")
        csv_path = tmp_repo / "out" / "deploy" / "deploy_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            writer.writerow(["2026-05-18T00:05:00Z", "1" * 40, "release/deploy", "1.2.4", "staging", "stg-stack", "stg.example.com", "img", "success"])
            writer.writerow(["2026-05-18T00:00:00Z", "0" * 40, "main", "1.2.3", "swap", "prod-stack", "prod.example.com", "img", "success"])

        csv_path = append_deploy_record(
            repo_root=tmp_repo,
            target="swap",
            stack_name="prod-stack",
            domain="prod.example.com",
            image="img",
            status="success",
            git_ref="1" * 40,
            local_branch="release/deploy",
        )

        rows = list(csv.reader(csv_path.open()))
        assert rows[1][3] == "1.2.4"
        assert rows[1][4] == "swap"
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
            local_branch="main",
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
            local_branch="release/deploy",
            version="2.0.0",
        )
        rows = list(csv.reader(csv_path.open()))
        data = rows[1]
        # timestamp, git_ref, local_branch, version, target, stack_name, domain, image, status
        assert len(data) == 9
        assert data[1] == "0" * 40
        assert data[2] == "release/deploy"
        assert data[3] == "2.0.0"
        assert data[4] == "swap"
        assert data[7] == ""

    def test_custom_csv_path_writes_to_requested_path(self, tmp_repo: Path) -> None:
        settings = DeployLogSettings(csv_path=Path("out/custom/deploy_log.csv"))

        csv_path = append_deploy_record_with_settings(
            repo_root=tmp_repo,
            settings=settings,
            target="staging",
            stack_name="stg-stack",
            domain="stg.example.com",
            image="img",
            status="success",
            git_ref="1" * 40,
            local_branch="feature/deploy-log-hook",
            version="1.2.3",
        )

        assert csv_path == tmp_repo / "out" / "custom" / "deploy_log.csv"
        assert csv_path.exists()
        assert not get_csv_path(tmp_repo).exists()

    def test_disabled_versioning_keeps_current_production_version(self, tmp_repo: Path) -> None:
        settings = DeployLogSettings(csv_path=get_csv_path(tmp_repo), versioning_enabled=False)

        csv_path = append_deploy_record_with_settings(
            repo_root=tmp_repo,
            settings=settings,
            target="production",
            stack_name="prod-stack",
            domain="prod.example.com",
            image="img",
            status="success",
            git_ref="2" * 40,
            local_branch="release/deploy",
        )

        rows = list(csv.reader(csv_path.open()))
        assert rows[1][3] == "1.2.3"
        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.3" in content

    def test_disabled_versioning_keeps_current_swap_version(self, tmp_repo: Path) -> None:
        csv_path = tmp_repo / "out" / "deploy" / "deploy_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            writer.writerow(["2026-05-18T00:00:00Z", "0" * 40, "main", "1.2.3", "swap", "prod-stack", "prod.example.com", "img", "success"])

        settings = DeployLogSettings(csv_path=get_csv_path(tmp_repo), versioning_enabled=False)

        csv_path = append_deploy_record_with_settings(
            repo_root=tmp_repo,
            settings=settings,
            target="swap",
            stack_name="prod-stack",
            domain="prod.example.com",
            image="img",
            status="success",
            git_ref="3" * 40,
            local_branch="release/deploy",
        )

        rows = list(csv.reader(csv_path.open()))
        assert rows[1][3] == "1.2.3"
        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.3" in content
