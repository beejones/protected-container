import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.deploy.azure_utils import (
    run_az_command,
    get_az_account_info,
    get_app_client_id_by_display_name,
    kv_secret_set_quiet,
    kv_data_plane_available,
)

def test_run_az_command_success():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = '{"key": "value"}'
        
        res = run_az_command(["group", "list"], verbose=False)
        assert res == {"key": "value"}
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["az", "group", "list"]

def test_run_az_command_failure():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "error"
        
        with pytest.raises(subprocess.CalledProcessError):
            run_az_command(["group", "list"], verbose=False)

def test_get_app_client_id_by_display_name():
    with patch("scripts.deploy.azure_utils.run_az_command") as mock_az:
        # Mock success response
        mock_az.return_value = [{"appId": "0000-1111"}]
        assert get_app_client_id_by_display_name("My App") == "0000-1111"
        
        # Mock empty response
        mock_az.return_value = []
        assert get_app_client_id_by_display_name("My App") is None

def test_kv_secret_set_quiet():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        
        kv_secret_set_quiet(vault_name="mykv", secret_name="mysec", value="s3cret")
        
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "keyvault" in cmd
        assert "secret" in cmd
        assert "set" in cmd
        assert "--value" in cmd
        assert "s3cret" in cmd # Ensure value is passed

def test_kv_data_plane_available_success():
    with patch("scripts.deploy.azure_utils.run_az_command") as mock_az:
        mock_az.return_value = []
        assert kv_data_plane_available("mykv") is True

def test_kv_data_plane_available_failure():
    with patch("scripts.deploy.azure_utils.run_az_command") as mock_az:
        mock_az.side_effect = subprocess.CalledProcessError(1, ["cmd"], stderr="Failed to resolve")
        assert kv_data_plane_available("mykv") is False
