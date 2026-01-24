from __future__ import annotations

import ast
from pathlib import Path


def _iter_py_files() -> list[Path]:
    repo_root = Path(__file__).parents[2]
    scripts_dir = repo_root / "scripts" / "deploy"
    return sorted([p for p in scripts_dir.glob("*.py") if p.is_file()])


def _is_os_getenv_call(node: ast.Call) -> bool:
    # Matches os.getenv(...)
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr != "getenv":
        return False
    return isinstance(node.func.value, ast.Name) and node.func.value.id == "os"


def _is_os_environ_subscript(node: ast.Subscript) -> bool:
    # Matches os.environ[...]
    if not isinstance(node.value, ast.Attribute):
        return False
    if node.value.attr != "environ":
        return False
    return isinstance(node.value.value, ast.Name) and node.value.value.id == "os"


def test_no_literal_env_key_access_in_scripts() -> None:
    offenders: list[str] = []

    for path in _iter_py_files():
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_os_getenv_call(node):
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    offenders.append(f"{path.name}: os.getenv({node.args[0].value!r})")

            if isinstance(node, ast.Subscript) and _is_os_environ_subscript(node):
                # Python 3.9+: slice is directly the node
                sl = node.slice
                if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                    offenders.append(f"{path.name}: os.environ[{sl.value!r}]")

    assert not offenders, "Literal env key access found:\n" + "\n".join(offenders)
