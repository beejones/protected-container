"""Deploy tracking CSV logger.

Appends a row to `out/deploy/deploy_log.csv` after each deploy, recording
the git ref, version, target environment, stack name, domain, image, and status.

After a successful **production** deploy, auto-increments the patch component
of APP_VERSION in `.env`.
"""

from __future__ import annotations

import csv
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values


CSV_COLUMNS = [
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


def _get_git_ref(repo_root: Path) -> str:
    """Return full 40-char commit SHA from `git rev-parse HEAD`."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, OSError):
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


def append_deploy_record(
    *,
    repo_root: Path,
    target: str,
    stack_name: str,
    domain: str,
    image: str,
    status: str,
    git_ref: str | None = None,
    version: str | None = None,
) -> Path:
    """Append a deploy record to the CSV log.

    Returns the path to the CSV file.
    """
    csv_path = get_csv_path(repo_root)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    resolved_git_ref = git_ref if git_ref is not None else _get_git_ref(repo_root)
    resolved_version = version if version is not None else _read_app_version(repo_root)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    write_header = not csv_path.exists() or csv_path.stat().st_size == 0

    with csv_path.open("a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(CSV_COLUMNS)
        writer.writerow([
            timestamp,
            resolved_git_ref,
            resolved_version,
            target,
            stack_name,
            domain,
            image,
            status,
        ])

    # Auto-increment patch version after successful production deploy
    if target == "production" and status == "success":
        new_version = _increment_patch(resolved_version)
        if new_version != resolved_version:
            _write_app_version(repo_root, new_version)

    return csv_path
