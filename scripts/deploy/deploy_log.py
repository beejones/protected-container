"""Deploy tracking CSV logger.

Writes a row to `out/deploy/deploy_log.csv` after each deploy, recording
the git ref, local branch, version, target environment, stack name, domain,
image, and status.
Newest records are stored directly under the CSV header.

After a successful **production** deploy, auto-increments the patch component
of APP_VERSION in `.env`. A successful **swap** promotion records and writes
the next patch version when it promotes a different git ref than the latest
successful production/swap record.
"""

from __future__ import annotations

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

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_GIT_REF_COLUMN = CSV_COLUMNS.index("git_ref")
_TARGET_COLUMN = CSV_COLUMNS.index("target")
_STATUS_COLUMN = CSV_COLUMNS.index("status")


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


def _increment_patch(version: str) -> str:
    """Increment the patch component of a semver string."""
    match = _SEMVER_RE.match(version.strip())
    if not match:
        return version
    major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))
    return f"{major}.{minor}.{patch + 1}"


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


def get_csv_path(repo_root: Path) -> Path:
    """Return the path to the deploy log CSV."""
    return repo_root / "out" / "deploy" / "deploy_log.csv"


def default_deploy_log_settings(repo_root: Path) -> DeployLogSettings:
    """Return default settings for deploy tracking."""
    return DeployLogSettings(csv_path=get_csv_path(repo_root))


def _resolve_csv_path(*, repo_root: Path, csv_path: Path) -> Path:
    """Resolve a hook-provided CSV path relative to the repo root."""
    if csv_path.is_absolute():
        return csv_path
    return repo_root / csv_path


def _latest_successful_release_git_ref(existing_rows: list[list[str]]) -> str:
    """Return the newest successful production/swap git ref from existing CSV rows."""
    for row in existing_rows:
        if len(row) < len(CSV_COLUMNS):
            continue
        git_ref = str(row[_GIT_REF_COLUMN] or "").strip()
        target = str(row[_TARGET_COLUMN] or "").strip()
        status = str(row[_STATUS_COLUMN] or "").strip()
        if target in {"production", "swap"} and status == "success" and git_ref:
            return git_ref
    return ""


def _normalize_existing_row(row: list[str]) -> list[str]:
    """Return a current-schema deploy log row, backfilling legacy rows."""
    if len(row) == len(CSV_COLUMNS):
        return row
    if len(row) == len(LEGACY_CSV_COLUMNS):
        return [row[0], row[1], "main", *row[2:]]
    return row


def _should_increment_swap_version(*, target: str, status: str, git_ref: str, existing_rows: list[list[str]]) -> bool:
    """True when a swap promotion represents a new release git ref."""
    if target != "swap" or status != "success":
        return False
    latest_release_git_ref = _latest_successful_release_git_ref(existing_rows)
    return not latest_release_git_ref or latest_release_git_ref != git_ref


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

    existing_rows: list[list[str]] = []
    if csv_path.exists() and csv_path.stat().st_size > 0:
        with csv_path.open(newline="") as f:
            rows = list(csv.reader(f))
        if rows:
            if rows[0] == CSV_COLUMNS or rows[0] == LEGACY_CSV_COLUMNS:
                existing_rows = [_normalize_existing_row(row) for row in rows[1:]]
            else:
                existing_rows = [_normalize_existing_row(row) for row in rows]

    swap_incremented = False
    production_incremented = False
    if settings.versioning_enabled and version is None and _should_increment_swap_version(
        target=target,
        status=status,
        git_ref=resolved_git_ref,
        existing_rows=existing_rows,
    ):
        new_version = _increment_patch(resolved_version)
        if new_version != resolved_version:
            resolved_version = new_version
            swap_incremented = True
    elif settings.versioning_enabled and version is None and target == "production" and status == "success":
        new_version = _increment_patch(resolved_version)
        if new_version != resolved_version:
            resolved_version = new_version
            production_incremented = True

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

    # Persist any automatic release-version bump after the row is written.
    if production_incremented:
        _write_app_version(repo_root, resolved_version)
    elif swap_incremented:
        _write_app_version(repo_root, resolved_version)

    return csv_path
