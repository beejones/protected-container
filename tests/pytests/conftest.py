from __future__ import annotations

import sys
from pathlib import Path


def pytest_configure() -> None:
    # Allow tests to import `scripts.*` as a package.
    repo_root = Path(__file__).parents[2]
    sys.path.append(str(repo_root))
