import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from scripts.deploy import deploy_hooks
from scripts.deploy.env_schema import VarsEnum

@pytest.fixture
def repo_root(tmp_path):
    # Setup a dummy repo root structure
    (tmp_path / "scripts" / "deploy").mkdir(parents=True)
    return tmp_path

def test_load_hooks_default_missing(repo_root):
    # No default file exists
    hooks = deploy_hooks.load_hooks(repo_root)
    assert hooks._impl is None
    assert hooks.call("anything") is None

def test_load_hooks_default_exists(repo_root, monkeypatch):
    # Create default customization file
    custom_file = repo_root / "scripts" / "deploy" / "deploy_customizations.py"
    custom_file.write_text("def pre_validate_env(ctx): ctx.env['HOOKED'] = True")
    
    hooks = deploy_hooks.load_hooks(repo_root)
    assert hooks._impl is not None
    
    ctx = MagicMock()
    ctx.env = {}
    hooks.call("pre_validate_env", ctx)
    assert ctx.env.get("HOOKED") is True

def test_load_hooks_default_invalid_code(repo_root):
    # Create default file with syntax error
    custom_file = repo_root / "scripts" / "deploy" / "deploy_customizations.py"
    custom_file.write_text("invalid python code")
    
    with pytest.raises(ImportError) as exc:
        deploy_hooks.load_hooks(repo_root)
    assert "Failed to load hooks" in str(exc.value)

def test_load_hooks_explicit_missing(repo_root):
    # Explicitly requested module that doesn't exist
    with pytest.raises(ImportError) as exc:
        deploy_hooks.load_hooks(repo_root, module_path="nonexistent_module")
    assert "Failed to load hooks" in str(exc.value)

def test_load_hooks_soft_fail_precedence(repo_root, monkeypatch):
    # Create a hook that crashes
    custom_file = repo_root / "scripts" / "deploy" / "deploy_customizations.py"
    custom_file.write_text("def pre_validate_env(ctx): raise ValueError('crash')")
    
    # 1. Default (no soft-fail) -> Should raise
    hooks = deploy_hooks.load_hooks(repo_root)
    with pytest.raises(ValueError):
        hooks.call("pre_validate_env", MagicMock())
        
    # 2. Env-based soft-fail
    monkeypatch.setenv(VarsEnum.DEPLOY_HOOKS_SOFT_FAIL.value, "true")
    hooks_env = deploy_hooks.load_hooks(repo_root)
    hooks_env.call("pre_validate_env", MagicMock()) # Should NOT raise
    
    # 3. CLI-based override (soft-fail=False)
    hooks_cli = deploy_hooks.load_hooks(repo_root, soft_fail=False)
    with pytest.raises(ValueError):
        hooks_cli.call("pre_validate_env", MagicMock())
    
    # 4. CLI-based override (soft-fail=True)
    monkeypatch.setenv(VarsEnum.DEPLOY_HOOKS_SOFT_FAIL.value, "false")
    hooks_cli_on = deploy_hooks.load_hooks(repo_root, soft_fail=True)
    hooks_cli_on.call("pre_validate_env", MagicMock()) # Should NOT raise

def test_env_mutability_syncs_back():
    import os
    # We now pass os.environ directly to DeployContext.
    # It behaves like a MutableMapping.
    ctx = deploy_hooks.DeployContext(repo_root=Path("."), env=os.environ, args=MagicMock())
    
    # Hook modifies ctx.env
    ctx.env["UNIT_TEST_INJECT"] = "target-value"
    
    # Verify it is immediate in os.environ
    assert os.environ["UNIT_TEST_INJECT"] == "target-value"
    
    # Cleanup
    del os.environ["UNIT_TEST_INJECT"]

def test_load_hooks_by_file_path(tmp_path, repo_root):
    # Test loading from an arbitrary path (outside normal module resolution)
    custom_dir = tmp_path / "custom"
    custom_dir.mkdir()
    custom_file = custom_dir / "myhooks.py"
    custom_file.write_text("def pre_validate_env(ctx): ctx.env['PATH_LOADED'] = True")
    
    hooks = deploy_hooks.load_hooks(repo_root, module_path=str(custom_file))
    ctx = MagicMock()
    ctx.env = {}
    hooks.call("pre_validate_env", ctx)
    assert ctx.env.get("PATH_LOADED") is True
