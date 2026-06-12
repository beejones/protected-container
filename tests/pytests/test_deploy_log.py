"""Unit tests for scripts/deploy/deploy_log.py."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.deploy.deploy_log import (
    CSV_COLUMNS,
    LEGACY_CSV_COLUMNS,
    PREVIOUS_CSV_COLUMNS,
    DeployLogSettings,
    _increment_patch,
    _read_app_version,
    _write_app_version,
    append_deploy_record,
    append_deploy_record_with_settings,
    append_merge_record,
    get_csv_path,
)


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    """Create a minimal repo root with .env containing APP_VERSION."""
    env_file = tmp_path / ".env"
    env_file.write_text("APP_VERSION=1.2.3\nBASIC_AUTH_USER=admin\n")
    changelog_file = tmp_path / "CHANGELOG.md"
    changelog_file.write_text("# Changelog\n\n## [1.2.4] - 2026-06-09\n\n## [1.2.3] - 2026-06-08\n")
    return tmp_path


def column_value(row: list[str], column: str) -> str:
    """Return a value from a deploy-log row by current column name."""
    return row[CSV_COLUMNS.index(column)]


def current_csv_row(
    *,
    timestamp: str,
    git_ref: str,
    version: str,
    status: str,
    target: str,
    local_branch: str,
    stack_name: str,
    domain: str,
    image: str,
) -> list[str]:
    """Return a deploy-log row in the current CSV order."""
    return [
        timestamp,
        git_ref,
        version,
        status,
        target,
        local_branch,
        stack_name,
        domain,
        image,
    ]


def previous_csv_row(
    *,
    timestamp: str,
    git_ref: str,
    local_branch: str,
    version: str,
    target: str,
    stack_name: str,
    domain: str,
    image: str,
    status: str,
) -> list[str]:
    """Return a deploy-log row in the previous nine-column CSV order."""
    return [
        timestamp,
        git_ref,
        local_branch,
        version,
        target,
        stack_name,
        domain,
        image,
        status,
    ]


def legacy_csv_row(
    *,
    timestamp: str,
    git_ref: str,
    version: str,
    target: str,
    stack_name: str,
    domain: str,
    image: str,
    status: str,
) -> list[str]:
    """Return a deploy-log row in the older eight-column CSV order."""
    return [timestamp, git_ref, version, target, stack_name, domain, image, status]


class TestIncrementPatch:
    def test_normal(self) -> None:
        assert _increment_patch("1.2.3") == "1.2.4"

    def test_large_patch(self) -> None:
        assert _increment_patch("1.0.99") == "1.0.100"

    def test_invalid_raises(self) -> None:
        with pytest.raises(RuntimeError, match="valid x.y.z semver"):
            _increment_patch("not-semver")


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
        assert result == tmp_path / "out" / "deploy" / "version_log.csv"


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
        assert column_value(rows[1], "version") == "1.2.3"
        assert column_value(rows[1], "status") == "success"
        assert column_value(rows[1], "target") == "staging"
        assert column_value(rows[1], "local_branch") == "feature/deploy-log-branch"
        assert column_value(rows[1], "stack_name") == "my-stack"
        assert column_value(rows[1], "domain") == "staging.example.com"
        assert column_value(rows[1], "image") == "ghcr.io/user/app:latest"

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
        assert column_value(rows[1], "git_ref") == "c" * 40
        assert column_value(rows[1], "version") == "1.0.1"
        assert column_value(rows[1], "status") == "failed"
        assert column_value(rows[1], "target") == "production"
        assert column_value(rows[1], "local_branch") == "release/deploy"
        assert column_value(rows[2], "git_ref") == "b" * 40
        assert column_value(rows[2], "version") == "1.0.0"
        assert column_value(rows[2], "status") == "success"
        assert column_value(rows[2], "target") == "staging"
        assert column_value(rows[2], "local_branch") == "main"

    def test_previous_rows_are_migrated_to_current_order(self, tmp_repo: Path) -> None:
        csv_path = tmp_repo / "out" / "deploy" / "version_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(PREVIOUS_CSV_COLUMNS)
            writer.writerow(previous_csv_row(
                timestamp="2026-05-18T00:00:00Z",
                git_ref="0" * 40,
                local_branch="release/old-layout",
                version="1.2.3",
                target="production",
                stack_name="prod-stack",
                domain="prod.example.com",
                image="img",
                status="success",
            ))

        csv_path = append_deploy_record(
            repo_root=tmp_repo,
            target="staging",
            stack_name="stg-stack",
            domain="stg.example.com",
            image="new-img",
            status="failed",
            git_ref="1" * 40,
            local_branch="feature/new-layout",
            version="1.2.4",
        )

        rows = list(csv.reader(csv_path.open()))
        assert rows[0] == CSV_COLUMNS
        assert column_value(rows[1], "version") == "1.2.4"
        assert column_value(rows[1], "status") == "failed"
        assert column_value(rows[1], "target") == "staging"
        assert column_value(rows[1], "local_branch") == "feature/new-layout"
        assert column_value(rows[2], "git_ref") == "0" * 40
        assert column_value(rows[2], "version") == "1.2.3"
        assert column_value(rows[2], "status") == "success"
        assert column_value(rows[2], "target") == "production"
        assert column_value(rows[2], "local_branch") == "release/old-layout"
        assert column_value(rows[2], "stack_name") == "prod-stack"
        assert column_value(rows[2], "domain") == "prod.example.com"
        assert column_value(rows[2], "image") == "img"

    def test_legacy_rows_are_prefilled_with_main(self, tmp_repo: Path) -> None:
        csv_path = tmp_repo / "out" / "deploy" / "version_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(LEGACY_CSV_COLUMNS)
            writer.writerow(legacy_csv_row(
                timestamp="2026-05-18T00:00:00Z",
                git_ref="0" * 40,
                version="1.2.3",
                target="swap",
                stack_name="prod-stack",
                domain="prod.example.com",
                image="img",
                status="success",
            ))

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
        assert column_value(rows[1], "local_branch") == "feature/deploy-log-branch"
        assert column_value(rows[2], "git_ref") == "0" * 40
        assert column_value(rows[2], "version") == "1.2.3"
        assert column_value(rows[2], "status") == "success"
        assert column_value(rows[2], "target") == "swap"
        assert column_value(rows[2], "local_branch") == "main"

    def test_production_success_records_current_version_without_existing_record(self, tmp_repo: Path) -> None:
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
        assert column_value(rows[1], "git_ref") == "d" * 40
        assert column_value(rows[1], "version") == "1.2.3"

    def test_production_success_reuses_post_merge_version_record(self, tmp_repo: Path) -> None:
        append_merge_record(
            repo_root=tmp_repo,
            git_ref="d" * 40,
            local_branch="main",
        )
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
        assert column_value(rows[1], "version") == "1.2.3"
        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.3" in content

    def test_merge_record_records_current_app_version(self, tmp_repo: Path) -> None:
        csv_path = append_merge_record(
            repo_root=tmp_repo,
            git_ref="d" * 40,
            local_branch="main",
        )

        rows = list(csv.reader(csv_path.open()))
        assert rows[0] == CSV_COLUMNS
        assert column_value(rows[1], "git_ref") == "d" * 40
        assert column_value(rows[1], "version") == "1.2.3"
        assert column_value(rows[1], "status") == "success"
        assert column_value(rows[1], "target") == "merge"
        assert column_value(rows[1], "local_branch") == "main"
        assert column_value(rows[1], "stack_name") == ""
        assert column_value(rows[1], "domain") == ""
        assert column_value(rows[1], "image") == ""
        assert "APP_VERSION=1.2.3" in (tmp_repo / ".env").read_text()

    def test_merge_record_does_not_require_changelog_entry(self, tmp_repo: Path) -> None:
        (tmp_repo / "CHANGELOG.md").write_text("# Changelog\n\n## [1.2.3] - 2026-06-08\n")

        csv_path = append_merge_record(
            repo_root=tmp_repo,
            git_ref="d" * 40,
            local_branch="main",
        )

        rows = list(csv.reader(csv_path.open()))
        assert column_value(rows[1], "version") == "1.2.3"
        assert "APP_VERSION=1.2.3" in (tmp_repo / ".env").read_text()

    def test_merge_record_without_changelog_enforcement_records_current_version(self, tmp_repo: Path) -> None:
        csv_path = tmp_repo / "out" / "deploy" / "version_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            writer.writerow(current_csv_row(
                timestamp="2026-05-18T00:00:00Z",
                git_ref="0" * 40,
                version="1.2.3",
                status="success",
                target="swap",
                local_branch="main",
                stack_name="prod-stack",
                domain="prod.example.com",
                image="img",
            ))

        settings = DeployLogSettings(csv_path=get_csv_path(tmp_repo), versioning_enabled=False)

        csv_path = append_merge_record(
            repo_root=tmp_repo,
            settings=settings,
            git_ref="1" * 40,
            local_branch="release/deploy",
        )

        rows = list(csv.reader(csv_path.open()))
        assert column_value(rows[1], "git_ref") == "1" * 40
        assert column_value(rows[1], "version") == "1.2.3"
        assert column_value(rows[1], "target") == "merge"
        assert column_value(rows[2], "git_ref") == "0" * 40
        assert column_value(rows[2], "version") == "1.2.3"
        assert "APP_VERSION=1.2.3" in (tmp_repo / ".env").read_text()

    def test_merge_record_requires_valid_current_app_version(self, tmp_repo: Path) -> None:
        (tmp_repo / ".env").write_text("APP_VERSION=not-semver\n")

        with pytest.raises(RuntimeError, match="valid x.y.z semver"):
            append_merge_record(
                repo_root=tmp_repo,
                git_ref="d" * 40,
                local_branch="main",
            )

        assert not get_csv_path(tmp_repo).exists()

    def test_merge_record_is_idempotent_for_existing_git_ref(self, tmp_repo: Path) -> None:
        csv_path = append_merge_record(
            repo_root=tmp_repo,
            git_ref="d" * 40,
            local_branch="main",
        )
        csv_path = append_merge_record(
            repo_root=tmp_repo,
            git_ref="d" * 40,
            local_branch="main",
        )

        rows = list(csv.reader(csv_path.open()))
        assert len(rows) == 2
        assert column_value(rows[1], "version") == "1.2.3"

    def test_merge_record_migrates_previous_order_for_existing_git_ref(self, tmp_repo: Path) -> None:
        csv_path = tmp_repo / "out" / "deploy" / "version_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(PREVIOUS_CSV_COLUMNS)
            writer.writerow(previous_csv_row(
                timestamp="2026-05-18T00:00:00Z",
                git_ref="d" * 40,
                local_branch="release/previous-order",
                version="1.2.3",
                target="merge",
                stack_name="",
                domain="",
                image="",
                status="success",
            ))

        csv_path = append_merge_record(
            repo_root=tmp_repo,
            git_ref="d" * 40,
            local_branch="main",
        )

        rows = list(csv.reader(csv_path.open()))
        assert len(rows) == 2
        assert rows[0] == CSV_COLUMNS
        assert column_value(rows[1], "git_ref") == "d" * 40
        assert column_value(rows[1], "version") == "1.2.3"
        assert column_value(rows[1], "status") == "success"
        assert column_value(rows[1], "target") == "merge"
        assert column_value(rows[1], "local_branch") == "release/previous-order"

    def test_merge_record_for_new_git_ref_bumps_patch_after_previous_success(self, tmp_repo: Path) -> None:
        csv_path = tmp_repo / "out" / "deploy" / "version_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            writer.writerow(current_csv_row(
                timestamp="2026-06-10T00:00:00Z",
                git_ref="0" * 40,
                version="1.2.3",
                status="success",
                target="merge",
                local_branch="main",
                stack_name="",
                domain="",
                image="",
            ))

        csv_path = append_merge_record(
            repo_root=tmp_repo,
            git_ref="1" * 40,
            local_branch="main",
        )

        rows = list(csv.reader(csv_path.open()))
        assert column_value(rows[1], "git_ref") == "1" * 40
        assert column_value(rows[1], "version") == "1.2.4"
        assert column_value(rows[1], "target") == "merge"
        assert "APP_VERSION=1.2.4" in (tmp_repo / ".env").read_text()

    def test_deploy_reuses_post_merge_version_for_same_git_ref(self, tmp_repo: Path) -> None:
        append_merge_record(
            repo_root=tmp_repo,
            git_ref="d" * 40,
            local_branch="main",
        )
        _write_app_version(tmp_repo, "1.2.5")

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
        assert column_value(rows[1], "version") == "1.2.3"
        assert column_value(rows[1], "target") == "production"
        assert column_value(rows[2], "version") == "1.2.3"
        assert column_value(rows[2], "target") == "merge"

    def test_staging_success_for_same_git_ref_does_not_increment_again(self, tmp_repo: Path) -> None:
        csv_path = tmp_repo / "out" / "deploy" / "version_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            writer.writerow(current_csv_row(
                timestamp="2026-05-18T00:00:00Z",
                git_ref="e" * 40,
                version="1.2.3",
                status="success",
                target="staging",
                local_branch="main",
                stack_name="stg-stack",
                domain="stg.example.com",
                image="img",
            ))

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

    def test_staging_success_for_new_git_ref_uses_current_version_when_already_ahead(self, tmp_repo: Path) -> None:
        _write_app_version(tmp_repo, "1.2.4")
        (tmp_repo / "CHANGELOG.md").write_text("# Changelog\n\n## [1.2.4] - 2026-06-09\n")
        csv_path = tmp_repo / "out" / "deploy" / "version_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            writer.writerow(current_csv_row(
                timestamp="2026-05-18T00:00:00Z",
                git_ref="0" * 40,
                version="1.2.3",
                status="success",
                target="swap",
                local_branch="main",
                stack_name="prod-stack",
                domain="prod.example.com",
                image="img",
            ))

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
        assert column_value(rows[1], "version") == "1.2.4"
        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.4" in content
        rows = list(csv.reader(csv_path.open()))
        assert column_value(rows[1], "git_ref") == "1" * 40
        assert column_value(rows[1], "version") == "1.2.4"

    def test_new_successful_deploy_git_ref_bumps_patch_after_previous_success(self, tmp_repo: Path) -> None:
        csv_path = tmp_repo / "out" / "deploy" / "version_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            writer.writerow(current_csv_row(
                timestamp="2026-06-10T00:00:00Z",
                git_ref="0" * 40,
                version="1.2.3",
                status="success",
                target="merge",
                local_branch="main",
                stack_name="",
                domain="",
                image="",
            ))

        csv_path = append_deploy_record(
            repo_root=tmp_repo,
            target="production",
            stack_name="prod-stack",
            domain="prod.example.com",
            image="img",
            status="success",
            git_ref="1" * 40,
            local_branch="release/deploy",
        )

        rows = list(csv.reader(csv_path.open()))
        assert column_value(rows[1], "git_ref") == "1" * 40
        assert column_value(rows[1], "version") == "1.2.4"
        assert "APP_VERSION=1.2.4" in (tmp_repo / ".env").read_text()

    def test_swap_success_for_new_git_ref_uses_current_version_when_already_ahead(self, tmp_repo: Path) -> None:
        _write_app_version(tmp_repo, "1.2.4")
        (tmp_repo / "CHANGELOG.md").write_text("# Changelog\n\n## [1.2.4] - 2026-06-09\n")
        csv_path = tmp_repo / "out" / "deploy" / "version_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            writer.writerow(current_csv_row(
                timestamp="2026-05-18T00:00:00Z",
                git_ref="0" * 40,
                version="1.2.3",
                status="success",
                target="swap",
                local_branch="main",
                stack_name="prod-stack",
                domain="prod.example.com",
                image="img",
            ))

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
        assert column_value(rows[1], "version") == "1.2.4"
        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.4" in content
        rows = list(csv.reader(csv_path.open()))
        assert column_value(rows[1], "git_ref") == "1" * 40
        assert column_value(rows[1], "version") == "1.2.4"

    def test_same_git_ref_reuses_existing_deploy_version_even_if_env_changed(self, tmp_repo: Path) -> None:
        _write_app_version(tmp_repo, "1.2.4")
        csv_path = tmp_repo / "out" / "deploy" / "version_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            writer.writerow(current_csv_row(
                timestamp="2026-05-18T00:00:00Z",
                git_ref="1" * 40,
                version="1.2.3",
                status="success",
                target="staging",
                local_branch="main",
                stack_name="stg-stack",
                domain="stg.example.com",
                image="img",
            ))

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
        assert column_value(rows[1], "version") == "1.2.3"
        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.4" in content

    def test_swap_success_for_same_git_ref_does_not_increment_again(self, tmp_repo: Path) -> None:
        _write_app_version(tmp_repo, "1.2.4")
        csv_path = tmp_repo / "out" / "deploy" / "version_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            writer.writerow(current_csv_row(
                timestamp="2026-05-18T00:00:00Z",
                git_ref="1" * 40,
                version="1.2.4",
                status="success",
                target="swap",
                local_branch="main",
                stack_name="prod-stack",
                domain="prod.example.com",
                image="img",
            ))

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
        assert column_value(rows[1], "version") == "1.2.4"
        assert column_value(rows[1], "target") == "swap"
        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.4" in content

    def test_swap_success_after_staging_same_git_ref_does_not_increment_again(self, tmp_repo: Path) -> None:
        _write_app_version(tmp_repo, "1.2.4")
        csv_path = tmp_repo / "out" / "deploy" / "version_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            writer.writerow(current_csv_row(
                timestamp="2026-05-18T00:05:00Z",
                git_ref="1" * 40,
                version="1.2.4",
                status="success",
                target="staging",
                local_branch="release/deploy",
                stack_name="stg-stack",
                domain="stg.example.com",
                image="img",
            ))
            writer.writerow(current_csv_row(
                timestamp="2026-05-18T00:00:00Z",
                git_ref="0" * 40,
                version="1.2.3",
                status="success",
                target="swap",
                local_branch="main",
                stack_name="prod-stack",
                domain="prod.example.com",
                image="img",
            ))

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
        assert column_value(rows[1], "version") == "1.2.4"
        assert column_value(rows[1], "target") == "swap"
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
        assert len(data) == 9
        assert rows[0] == CSV_COLUMNS
        assert column_value(data, "git_ref") == "0" * 40
        assert column_value(data, "version") == "2.0.0"
        assert column_value(data, "status") == "success"
        assert column_value(data, "target") == "swap"
        assert column_value(data, "local_branch") == "release/deploy"
        assert column_value(data, "image") == ""

    def test_custom_csv_path_writes_to_requested_path(self, tmp_repo: Path) -> None:
        settings = DeployLogSettings(csv_path=Path("out/custom/version_log.csv"))

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

        assert csv_path == tmp_repo / "out" / "custom" / "version_log.csv"
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
        assert column_value(rows[1], "version") == "1.2.3"
        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.3" in content

    def test_disabled_versioning_keeps_current_swap_version(self, tmp_repo: Path) -> None:
        csv_path = tmp_repo / "out" / "deploy" / "version_log.csv"
        csv_path.parent.mkdir(parents=True)
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            writer.writerow(current_csv_row(
                timestamp="2026-05-18T00:00:00Z",
                git_ref="0" * 40,
                version="1.2.3",
                status="success",
                target="swap",
                local_branch="main",
                stack_name="prod-stack",
                domain="prod.example.com",
                image="img",
            ))

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
        assert column_value(rows[1], "version") == "1.2.3"
        content = (tmp_repo / ".env").read_text()
        assert "APP_VERSION=1.2.3" in content
