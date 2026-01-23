#!/usr/bin/env python3
"""Shared Azure CLI utilities."""

from __future__ import annotations

import json
import subprocess
import sys
import shutil
import textwrap
import time
from typing import Any


def kv_secret_set_quiet(*, vault_name: str, secret_name: str, value: str) -> None:
    """Set a Key Vault secret without printing the secret value.

    We intentionally do NOT use run_az_command() here because it logs the full command.
    """
    vault_name = (vault_name or "").strip()
    secret_name = (secret_name or "").strip()
    if not vault_name or not secret_name:
        raise ValueError("vault_name and secret_name are required")

    print(f"[kv] setting secret '{secret_name}' in vault '{vault_name}'")
    
    # Retry loop for RBAC propagation (max ~5 mins with exp backoff)
    max_retries = 20
    base_delay = 3.0
    
    for attempt in range(1, max_retries + 1):
        result = subprocess.run(
            [
                "az",
                "keyvault",
                "secret",
                "set",
                "--vault-name",
                vault_name,
                "--name",
                secret_name,
                "--value",
                value,
                "--output",
                "none",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            return

        err = (result.stderr or "").strip()
        # Check for typical RBAC propagation errors. 
        # "Forbidden" and "Caller is not authorized" usually mean propagation lag.
        if "Forbidden" in err or "Unauthorized" in err or "Caller is not authorized" in err:
            if attempt < max_retries:
                # Exponential backoff: 3, 4.5, 6.75, ... capped at 20s
                sleep_time = min(20.0, base_delay * (1.5 ** (attempt - 1)))
                print(f"[kv] Access denied (attempt {attempt}/{max_retries}). Waiting {sleep_time:.1f}s for RBAC propagation...")
                time.sleep(sleep_time)
                continue
        
        # If it's not an auth error, or we ran out of retries, raise.
        # Ensure we print stderr so it shows up in CI logs before raising
        print(f"[kv] Error setting secret (exit code {result.returncode}).", file=sys.stderr)
        print(f"[kv] STDOUT: {result.stdout.strip() if result.stdout else '<empty>'}", file=sys.stderr)
        print(f"[kv] STDERR: {result.stderr.strip() if result.stderr else '<empty>'}", file=sys.stderr)
        print(f"[kv] Secret value length: {len(value)} characters", file=sys.stderr)
        sys.stderr.flush()
            
        raise subprocess.CalledProcessError(
            result.returncode,
            result.args,  
            output=result.stdout,
            stderr=result.stderr,
        )


def kv_data_plane_available(vault_name: str) -> bool:
    if not vault_name:
        return False
    try:
        # Data-plane check (hits https://<vault>.vault.azure.net).
        # Keep it lightweight; we only need to know if the endpoint is reachable.
        run_az_command(
            [
                "keyvault",
                "secret",
                "list",
                "--vault-name",
                vault_name,
                "--maxresults",
                "1",
                "--output",
                "none",
            ],
            capture_output=False,
            ignore_errors=False,
            verbose=False,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(
            "WARNING: Key Vault secrets endpoint is not reachable/usable; cannot read or persist deploy values.",
            file=sys.stderr,
        )
        print(_format_keyvault_set_help(vault_name=vault_name, stderr=getattr(e, "stderr", None)), file=sys.stderr)
        return False


def _format_keyvault_set_help(*, vault_name: str, stderr: str | None) -> str:
    host = f"{vault_name}.vault.azure.net"
    err = (stderr or "").strip()
    dns_hint = "Failed to resolve" in err or "Name or service not known" in err

    msg = f"Could not write Key Vault secret to '{vault_name}' ({host})."
    if dns_hint:
        msg += " DNS resolution failed."

    details = ""
    if err:
        details = f"\n\nAzure CLI error:\n{err}"

    hint = "\n\n".join(
        [
            "Troubleshooting:",
            f"- Verify the vault name: az keyvault show --name {vault_name} --query name -o tsv",
            f"- If the vault uses a private endpoint, your machine (and ACI) must have access to the private DNS zone / VNet.",
            f"- If you expect public access, check network/VPN/DNS settings and retry.",
        ]
    )

    return textwrap.dedent(msg + details + "\n\n" + hint)



def run_az_command(args: list[str], *, capture_output: bool = True, ignore_errors: bool = False, verbose: bool = True) -> dict | str | None:
    """Run an azure cli command."""
    cmd = ["az"] + args
    if verbose:
        print(f"[az] {' '.join(cmd)}")

    # Check if az is installed
    if not shutil.which("az"):
        if ignore_errors:
            return None
        raise RuntimeError("Azure CLI (az) not found. Please install it.")

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        if ignore_errors:
            return None

        if result.stdout:
            print(result.stdout.rstrip(), file=sys.stderr)
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)

        raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout, stderr=result.stderr)

    if capture_output and result.stdout:
        out = result.stdout.strip()
        if not out:
            return None
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return out

    return None


def get_az_account_info() -> dict[str, str]:
    """Return dictionary with 'id' (subscription) and 'tenantId'."""
    try:
        res = run_az_command(["account", "show", "--output", "json"], capture_output=True)
        if isinstance(res, dict):
            return {
                "id": str(res.get("id") or ""),
                "tenantId": str(res.get("tenantId") or ""),
            }
    except Exception:
        pass
    return {"id": "", "tenantId": ""}


def get_service_principal_object_id(client_id: str) -> str | None:
    if not client_id:
        return None
    res = run_az_command([
        "ad",
        "sp",
        "show",
        "--id",
        client_id,
        "--query",
        "id",
        "-o",
        "tsv",
    ], capture_output=True, ignore_errors=True)
    val = str(res or "").strip()
    return val or None


def get_app_client_id_by_display_name(display_name: str) -> str | None:
    display_name = display_name.strip()
    if not display_name:
        return None

    # Query the first matching app registration
    apps = run_az_command(
        ["ad", "app", "list", "--display-name", display_name, "--query", "[].{appId:appId}", "-o", "json"],
        ignore_errors=True
    )
    if apps and isinstance(apps, list) and len(apps) > 0:
        return str(apps[0].get("appId") or "")
    return None
