"""Version log CSV logger.

Writes a row to `out/deploy/version_log.csv` after each deploy, recording
the git ref, local branch, version, target environment, stack name, domain,
image, and status.
Newest records are stored directly under the CSV header.

For a new git ref, the current APP_VERSION must already have a matching
CHANGELOG.md entry from /changelog. Later deploy records for that same git ref
reuse the version already recorded in the deploy log.
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values


CSV_COLUMNS = [
    "timestamp",
    "git_ref",
    "local_branch",
    "version",
    "target",
    "stack_name",
    "domain",
    "image",
    "status",
]

LEGACY_CSV_COLUMNS = [
    "timestamp",
    "git_ref",
    "version",
    "target",
    "stack_name",
    "domain",
    "image",
    "status",
]

_CHANGELOG_VERSION_HEADING_RE = re.compile(r"^## \[(?P<version>\d+\.\d+\.\d+)\]")
_GIT_REF_COLUMN = CSV_COLUMNS.index("git_ref")
_STATUS_COLUMN = CSV_COLUMNS.index("status")
_MERGE_TARGET = "merge"


@dataclass
class DeployLogSettings:
    """Mutable deploy-log settings exposed to deployment hooks."""
    csv_path: Path
    versioning_enabled: bool = True


def _run_git_command(repo_root: Path, args: list[str]) -> str:
    """Return stripped stdout from a git command, or an empty string."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return ""


def _get_git_ref(repo_root: Path) -> str:
    """Return full 40-char commit SHA from `git rev-parse HEAD`."""
    return _run_git_command(repo_root, ["rev-parse", "HEAD"]) or "unknown"


def _get_local_branch(repo_root: Path) -> str:
    """Return the checked-out local branch name, or unknown for detached HEAD."""
    branch = _run_git_command(repo_root, ["branch", "--show-current"])
    if branch and branch != "HEAD":
        return branch
    branch = _run_git_command(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    if branch and branch != "HEAD":
        return branch
    return "unknown"


def _read_app_version(repo_root: Path) -> str:
    """Read APP_VERSION from .env, defaulting to 0.0.0."""
    env_path = repo_root / ".env"
    if not env_path.exists():
        return "0.0.0"
    values = dotenv_values(env_path)
    return str(values.get("APP_VERSION") or "0.0.0").strip() or "0.0.0"


def _write_app_version(repo_root: Path, new_version: str) -> None:
    """Update APP_VERSION in .env in-place."""
    env_path = repo_root / ".env"
    if not env_path.exists():
        env_path.write_text(f"APP_VERSION={new_version}\n")
        return

    lines = env_path.read_text().splitlines()
    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("APP_VERSION=") or stripped.startswith("APP_VERSION ="):
            lines[i] = f"APP_VERSION={new_version}"
            found = True
            break
    if not found:
        lines.append(f"APP_VERSION={new_version}")
    env_path.write_text("\n".join(lines) + "\n")


def _changelog_has_version_entry(repo_root: Path, version: str) -> bool:
    """Return whether CHANGELOG.md already contains a heading for version."""
    changelog_path = repo_root / "CHANGELOG.md"
    if not changelog_path.exists():
        return False
    for line in changelog_path.read_text().splitlines():
        match = _CHANGELOG_VERSION_HEADING_RE.match(line.strip())
        if match and match.group("version") == version:
            return True
    return False


def _require_changelog_entry_for_version(repo_root: Path, version: str) -> None:
    """Fail before deploying a version that /changelog has not prepared."""
    if _changelog_has_version_entry(repo_root, version):
        return
    raise RuntimeError(
        f"CHANGELOG.md is missing an entry for {version}. Run /changelog before deploying a new git ref."
    )


def get_csv_path(repo_root: Path) -> Path:
    """Return the path to the version log CSV."""
    return repo_root / "out" / "deploy" / "version_log.csv"


def default_deploy_log_settings(repo_root: Path) -> DeployLogSettings:
    """Return default settings for deploy tracking."""
    return DeployLogSettings(csv_path=get_csv_path(repo_root))


def _resolve_csv_path(*, repo_root: Path, csv_path: Path) -> Path:
    """Resolve a hook-provided CSV path relative to the repo root."""
    if csv_path.is_absolute():
        return csv_path
    return repo_root / csv_path


def _latest_successful_deploy_git_ref(existing_rows: list[list[str]]) -> str:
    """Return the newest successful deploy git ref from existing CSV rows."""
    for row in existing_rows:
        if len(row) < len(CSV_COLUMNS):
            continue
        git_ref = str(row[_GIT_REF_COLUMN] or "").strip()
        status = str(row[_STATUS_COLUMN] or "").strip()
        if status == "success" and git_ref:
            return git_ref
    return ""


def _successful_deploy_version_for_git_ref(*, git_ref: str, existing_rows: list[list[str]]) -> str:
    """Return the newest successful deploy version for a git ref."""
    for row in existing_rows:
        if len(row) < len(CSV_COLUMNS):
            continue
        row_git_ref = str(row[_GIT_REF_COLUMN] or "").strip()
        status = str(row[_STATUS_COLUMN] or "").strip()
        if status == "success" and row_git_ref == git_ref:
            return str(row[CSV_COLUMNS.index("version")] or "").strip()
    return ""


def _normalize_existing_row(row: list[str]) -> list[str]:
    """Return a current-schema deploy log row, backfilling legacy rows."""
    if len(row) == len(CSV_COLUMNS):
        return row
    if len(row) == len(LEGACY_CSV_COLUMNS):
        return [row[0], row[1], "main", *row[2:]]
    return row


def _read_existing_deploy_rows(csv_path: Path) -> list[list[str]]:
    """Read deploy-log rows using the current schema shape."""
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return []
    with csv_path.open(newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return []
    if rows[0] == CSV_COLUMNS or rows[0] == LEGACY_CSV_COLUMNS:
        return [_normalize_existing_row(row) for row in rows[1:]]
    return [_normalize_existing_row(row) for row in rows]


def _requires_new_version_record(*, status: str, git_ref: str, existing_rows: list[list[str]]) -> bool:
    """True when a successful event records a new git ref."""
    if status != "success":
        return False
    latest_deploy_git_ref = _latest_successful_deploy_git_ref(existing_rows)
    return not latest_deploy_git_ref or latest_deploy_git_ref != git_ref


def require_changelog_for_pending_version_record(
    *,
    repo_root: Path,
    settings: DeployLogSettings,
    status: str,
    git_ref: str | None = None,
    version: str | None = None,
) -> None:
    """Validate the merge-prepared version before writing deploy state."""
    if not settings.versioning_enabled or version is not None:
        return
    csv_path = _resolve_csv_path(repo_root=repo_root, csv_path=settings.csv_path)
    existing_rows = _read_existing_deploy_rows(csv_path)
    resolved_git_ref = git_ref if git_ref is not None else _get_git_ref(repo_root)
    if not _requires_new_version_record(
        status=status,
        git_ref=resolved_git_ref,
        existing_rows=existing_rows,
    ):
        return
    resolved_version = _read_app_version(repo_root)
    _require_changelog_entry_for_version(repo_root, resolved_version)


def append_deploy_record(
    *,
    repo_root: Path,
    target: str,
    stack_name: str,
    domain: str,
    image: str,
    status: str,
    git_ref: str | None = None,
    local_branch: str | None = None,
    version: str | None = None,
) -> Path:
    """Write a deploy record to the default CSV log.

    Returns the path to the CSV file.
    """
    return append_deploy_record_with_settings(
        repo_root=repo_root,
        settings=default_deploy_log_settings(repo_root),
        target=target,
        stack_name=stack_name,
        domain=domain,
        image=image,
        status=status,
        git_ref=git_ref,
        local_branch=local_branch,
        version=version,
    )


def append_deploy_record_with_settings(
    *,
    repo_root: Path,
    settings: DeployLogSettings,
    target: str,
    stack_name: str,
    domain: str,
    image: str,
    status: str,
    git_ref: str | None = None,
    local_branch: str | None = None,
    version: str | None = None,
) -> Path:
    """Write a deploy record to the CSV log.

    Returns the path to the CSV file.
    """
    csv_path = _resolve_csv_path(repo_root=repo_root, csv_path=settings.csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    resolved_git_ref = git_ref if git_ref is not None else _get_git_ref(repo_root)
    resolved_local_branch = local_branch if local_branch is not None else _get_local_branch(repo_root)
    resolved_version = version if version is not None else _read_app_version(repo_root)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    existing_rows = _read_existing_deploy_rows(csv_path)

    if settings.versioning_enabled and version is None:
        existing_version = _successful_deploy_version_for_git_ref(
            git_ref=resolved_git_ref,
            existing_rows=existing_rows,
        )
        if existing_version:
            resolved_version = existing_version
        elif _requires_new_version_record(
            status=status,
            git_ref=resolved_git_ref,
            existing_rows=existing_rows,
        ):
            _require_changelog_entry_for_version(repo_root, resolved_version)

    new_row = [
        timestamp,
        resolved_git_ref,
        resolved_local_branch,
        resolved_version,
        target,
        stack_name,
        domain,
        image,
        status,
    ]

    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
        writer.writerow(new_row)
        writer.writerows(existing_rows)

    return csv_path


def append_merge_record(
    *,
    repo_root: Path,
    settings: DeployLogSettings | None = None,
    git_ref: str | None = None,
    local_branch: str | None = None,
    version: str | None = None,
) -> Path:
    """Record a post-merge version row unless the git ref is already logged."""
    resolved_settings = settings if settings is not None else default_deploy_log_settings(repo_root)
    csv_path = _resolve_csv_path(repo_root=repo_root, csv_path=resolved_settings.csv_path)
    existing_rows = _read_existing_deploy_rows(csv_path)
    resolved_git_ref = git_ref if git_ref is not None else _get_git_ref(repo_root)
    if _successful_deploy_version_for_git_ref(git_ref=resolved_git_ref, existing_rows=existing_rows):
        return csv_path

    resolved_version = version if version is not None else _read_app_version(repo_root)
    if resolved_settings.versioning_enabled and version is None:
        _require_changelog_entry_for_version(repo_root, resolved_version)

    return append_deploy_record_with_settings(
        repo_root=repo_root,
        settings=resolved_settings,
        target=_MERGE_TARGET,
        stack_name="",
        domain="",
        image="",
        status="success",
        git_ref=resolved_git_ref,
        local_branch=local_branch,
        version=resolved_version,
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the version-log CLI parser."""
    parser = argparse.ArgumentParser(description="Update the protected version log.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--csv-path", type=Path, default=None)
    parser.add_argument("--record-merge", action="store_true")
    parser.add_argument("--disable-versioning", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for version-log maintenance."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    if not args.record_merge:
        parser.error("choose an action, for example --record-merge")
    settings = DeployLogSettings(
        csv_path=args.csv_path if args.csv_path is not None else get_csv_path(repo_root),
        versioning_enabled=not args.disable_versioning,
    )
    csv_path = append_merge_record(repo_root=repo_root, settings=settings)
    print(f"Version log ready: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
