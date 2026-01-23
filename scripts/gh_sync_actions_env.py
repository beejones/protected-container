#!/usr/bin/env python3
"""Sync local .env files into GitHub Actions variables/secrets.

Primary use-case: make it easy to run the deploy workflow in CI.

It supports two approaches:

1) Store runtime dotenv as a single secret (recommended):
    - RUNTIME_ENV_DOTENV -> contents of .env (runtime inputs; uploaded to KV by azure_deploy_container.py)

2) Sync per-key variables/secrets from .env.deploy (deploy-time inputs).

Requirements:
- GitHub CLI installed and authenticated (gh auth login)
- Permission to set Actions secrets/vars on the repo

Examples:
  python3 scripts/gh_sync_actions_env.py --set
  python3 scripts/gh_sync_actions_env.py --set --also-sync-keys
  python3 scripts/gh_sync_actions_env.py --repo owner/repo --set
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import io
import hashlib
import sys
from pathlib import Path

from dotenv import dotenv_values

# Add scripts dir to path to allow importing azure_utils
sys.path.append(str(Path(__file__).parent))
try:
    from azure_utils import run_az_command, get_az_account_info, get_app_client_id_by_display_name
except ImportError:
    sys.path.append("scripts")
    from azure_utils import run_az_command, get_az_account_info, get_app_client_id_by_display_name


SECRET_KEY_RE = re.compile(r"(TOKEN|PASSWORD|SECRET|KEY|HASH)$")


# Keys which should always be treated as GitHub Actions *variables* (not secrets).
FORCE_VARIABLE_KEYS = {
    "AZURE_CLIENT_ID",
    "AZURE_TENANT_ID",
    "AZURE_SUBSCRIPTION_ID",
}


REQUIRED_FOR_AZURE_LOGIN = {
    "AZURE_CLIENT_ID",
    "AZURE_TENANT_ID",
    "AZURE_SUBSCRIPTION_ID",
}


def _run(cmd: list[str], *, input_text: str | None = None) -> str:
    def _format_cmd(argv: list[str]) -> str:
        # Avoid leaking secret values in error messages (e.g. `gh secret set ... -b <value>`).
        redacted: list[str] = []
        redact_next = False
        for a in argv:
            if redact_next:
                redacted.append("***")
                redact_next = False
                continue
            redacted.append(a)
            if a in {"-b", "--body"}:
                redact_next = True
        return " ".join(redacted)

    p = subprocess.run(
        cmd,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if p.returncode != 0:
        raise SystemExit(f"Command failed ({p.returncode}): {_format_cmd(cmd)}\n{p.stderr.strip()}")
    return p.stdout.strip()


def _detect_repo() -> str:
    # Uses current repo.
    return _run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])


def _detect_default_branch(repo: str) -> str | None:
    try:
        return _run(["gh", "repo", "view", repo, "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"])
    except Exception:
        return None


def _detect_current_branch() -> str | None:
    env_branch = (os.getenv("GITHUB_REF_NAME") or "").strip()
    if env_branch:
        return env_branch
    try:
        branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()
    except Exception:
        return None
    if not branch or branch == "HEAD":
        return None
    return branch


def _az_single_app_client_id() -> str | None:
    res = run_az_command(
        ["ad", "app", "list", "--query", "[].appId", "-o", "json"],
        capture_output=True,
        ignore_errors=True,
    )
    if isinstance(res, list):
        if len(res) == 1:
            return str(res[0])
    return None


def _az_federated_credentials(app_id: str) -> list[dict]:
    res = run_az_command(
        [
            "ad",
            "app",
            "federated-credential",
            "list",
            "--id",
            app_id,
            "-o",
            "json",
        ],
        capture_output=True,
        ignore_errors=True,
    )
    if isinstance(res, list):
        return res
    return []


def _ensure_federated_credential(*, app_id: str, repo: str, subject: str) -> None:
    issuer = "https://token.actions.githubusercontent.com"
    audience = "api://AzureADTokenExchange"

    existing = _az_federated_credentials(app_id)
    for item in existing:
        if str(item.get("issuer")) != issuer:
            continue
        if str(item.get("subject")) != subject:
            continue
        audiences = item.get("audiences") or []
        if audience in audiences:
            return

    suffix = ""
    marker = f"repo:{repo}:ref:refs/heads/"
    if subject.startswith(marker):
        suffix = subject[len(marker) :].strip()
    if not suffix:
        suffix = hashlib.sha1(subject.encode("utf-8")).hexdigest()[:8]
    safe_repo = repo.replace("/", "-")
    safe_suffix = re.sub(r"[^a-zA-Z0-9-]+", "-", suffix)[:32].strip("-")
    name = f"github-oidc-{safe_repo}-{safe_suffix}" if safe_suffix else f"github-oidc-{safe_repo}-{hashlib.sha1(subject.encode('utf-8')).hexdigest()[:8]}"
    name = name[:120]
    
    print(f"[oidc] Creating federated credential: {name}")
    
    params = json.dumps(
        {
            "name": name,
            "issuer": issuer,
            "subject": subject,
            "audiences": [audience],
        }
    )
    run_az_command(
        [
            "ad",
            "app",
            "federated-credential",
            "create",
            "--id",
            app_id,
            "--parameters",
            params,
        ],
        capture_output=False,
    )


def _has_gh_variables() -> bool:
    # gh variable set is relatively new; probe support.
    p = subprocess.run(["gh", "variable", "set", "-h"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return p.returncode == 0


def _set_secret(*, repo: str, name: str, value: str, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] set secret {name} (repo={repo})")
        return
    _run(["gh", "secret", "set", name, "-R", repo, "-b", value])
    print(f"[ok] set secret {name} (repo={repo})")


def _set_variable(*, repo: str, name: str, value: str, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] set var {name}={value!r} (repo={repo})")
        return

    # Prefer `gh variable set` when available.
    if _has_gh_variables():
        try:
            _run(["gh", "variable", "set", name, "-R", repo, "-b", value])
            print(f"[ok] set var {name} (repo={repo})")
            return
        except SystemExit:
            # Fall through to API fallback.
            pass

    # API fallback (PATCH then POST if missing)
    p = subprocess.run(
        [
            "gh",
            "api",
            "-X",
            "PATCH",
            f"repos/{repo}/actions/variables/{name}",
            "-f",
            f"name={name}",
            "-f",
            f"value={value}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if p.returncode == 0:
        print(f"[ok] set var {name} (repo={repo})")
        return

    err = (p.stderr or "").strip()
    if "HTTP 404" in err or "Not Found" in err:
        _run(
            [
                "gh",
                "api",
                "-X",
                "POST",
                f"repos/{repo}/actions/variables",
                "-f",
                f"name={name}",
                "-f",
                f"value={value}",
            ]
        )
        print(f"[ok] set var {name} (repo={repo})")
        return

    raise SystemExit(f"Command failed ({p.returncode}): gh api (set variable {name})\n{err}")


def _read_text(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"Missing file: {path}")
    return path.read_text(encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=None, help="GitHub repo in owner/repo form (default: current)")
    ap.add_argument("--deploy-env", default=".env.deploy", help="Path to deploy env file (default: .env.deploy)")
    ap.add_argument("--runtime-env", default=".env", help="Path to runtime env file (default: .env)")
    ap.add_argument(
        "--set",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Set secrets/vars (default: enabled; use --no-set for dry-run)",
    )
    ap.add_argument(
        "--only-files",
        action="store_true",
        help="Only set RUNTIME_ENV_DOTENV secret (no per-key sync)",
    )
    ap.add_argument(
        "--also-sync-keys",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Also sync keys from .env.deploy as GitHub Actions vars/secrets (default: enabled; use --no-also-sync-keys)",
    )
    ap.add_argument(
        "--auto-fill-azure-ids",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "If AZURE_TENANT_ID / AZURE_SUBSCRIPTION_ID are missing, try to read them from `az account show` "
            "(default: enabled; use --no-auto-fill-azure-ids to disable)."
        ),
    )
    ap.add_argument(
        "--auto-fill-azure-client-id",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "If AZURE_CLIENT_ID is missing, try to read it from `az ad app list` "
            "(default: enabled; use --no-auto-fill-azure-client-id to disable)."
        ),
    )
    ap.add_argument(
        "--azure-app-display-name",
        default="github-actions-aci-deploy",
        help=(
            "Optional: if AZURE_CLIENT_ID is missing, look it up by Azure AD App Registration display name "
            "using `az ad app list --display-name` (default: github-actions-aci-deploy)."
        ),
    )
    ap.add_argument(
        "--azure-client-id",
        default=None,
        help=(
            "Optional: explicitly set AZURE_CLIENT_ID (App Registration appId / client-id). "
            "This overrides the value from .env.deploy and avoids needing to look it up."
        ),
    )
    ap.add_argument(
        "--ensure-federated-credential",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Ensure GitHub OIDC federated credential exists on the Azure App Registration "
            "(default: enabled; use --no-ensure-federated-credential to disable)."
        ),
    )
    ap.add_argument(
        "--oidc-subject",
        default=None,
        help=(
            "Override the federated credential subject. Default is repo:<owner>/<repo>:ref:refs/heads/<default-branch>."
        ),
    )

    args = ap.parse_args()

    repo = args.repo or _detect_repo()
    dry_run = not bool(args.set)

    if dry_run:
        print("[dry-run] No changes will be made.")
        print("[dry-run] Re-run with: python3 scripts/gh_sync_actions_env.py --set")

    deploy_path = Path(args.deploy_env).expanduser().resolve()
    runtime_path = Path(args.runtime_env).expanduser().resolve()

    deploy_text = _read_text(deploy_path)
    runtime_text = _read_text(runtime_path)

    deploy_kv = dotenv_values(stream=io.StringIO(deploy_text))

    # Ensure required Azure login vars are present as GitHub Actions VARIABLES.
    # The deploy workflow uses these directly; they are not pulled from DEPLOY_ENV_DOTENV.
    env_azure_client_id = (os.getenv("AZURE_CLIENT_ID") or "").strip()
    env_azure_app_id = (os.getenv("AZURE_APP_ID") or "").strip()
    env_azure_tenant_id = (os.getenv("AZURE_TENANT_ID") or "").strip()
    env_azure_subscription_id = (os.getenv("AZURE_SUBSCRIPTION_ID") or "").strip()

    azure_app_id = str((deploy_kv.get("AZURE_APP_ID") or env_azure_app_id) or "").strip()

    azure_client_id = str(
        (args.azure_client_id or deploy_kv.get("AZURE_CLIENT_ID") or env_azure_client_id or azure_app_id) or ""
    ).strip()
    azure_tenant_id = str((deploy_kv.get("AZURE_TENANT_ID") or env_azure_tenant_id) or "").strip()
    azure_subscription_id = str((deploy_kv.get("AZURE_SUBSCRIPTION_ID") or env_azure_subscription_id) or "").strip()

    if args.auto_fill_azure_ids:
        info = get_az_account_info()
        if not azure_tenant_id:
            azure_tenant_id = info.get("tenantId") or ""
            if azure_tenant_id:
                print("[info] Filled AZURE_TENANT_ID from az account show")
        if not azure_subscription_id:
            azure_subscription_id = info.get("id") or ""
            if azure_subscription_id:
                print("[info] Filled AZURE_SUBSCRIPTION_ID from az account show")

        azure_app_display_name = (args.azure_app_display_name or os.getenv("AZURE_APP_DISPLAY_NAME") or "").strip()
        if not azure_client_id and azure_app_display_name:
            azure_client_id = get_app_client_id_by_display_name(azure_app_display_name) or ""
        if not azure_client_id and args.auto_fill_azure_client_id:
            azure_client_id = _az_single_app_client_id() or ""
        
        # Security: Do NOT fall back to picking the first app if multiple exist.
        if not azure_client_id and args.auto_fill_azure_client_id:
            # Check if there are multiple apps to warn the user?
            # _az_single_app_client_id returns None if 0 or >1.
            pass

    missing_required = [
        k
        for k, v in (
            ("AZURE_CLIENT_ID", azure_client_id),
            ("AZURE_TENANT_ID", azure_tenant_id),
            ("AZURE_SUBSCRIPTION_ID", azure_subscription_id),
        )
        if not str(v or "").strip()
    ]
    if missing_required:
        print(
            "[warn] Missing Azure OIDC values needed by the deploy workflow: "
            + ", ".join(missing_required)
            + ". Set them in .env.deploy (or pass --azure-client-id / --azure-app-display-name for AZURE_CLIENT_ID; "
            + "or set AZURE_APP_ID/AZURE_APP_DISPLAY_NAME env vars)."
        )

    if azure_client_id:
        _set_variable(repo=repo, name="AZURE_CLIENT_ID", value=azure_client_id, dry_run=dry_run)
        if args.ensure_federated_credential and not dry_run:
            explicit_subject = (args.oidc_subject or os.getenv("AZURE_OIDC_SUBJECT") or "").strip()
            subjects: set[str] = set()
            if explicit_subject:
                subjects.add(explicit_subject)
            else:
                default_branch = _detect_default_branch(repo) or "main"
                subjects.add(f"repo:{repo}:ref:refs/heads/{default_branch}")
                # Also authorize the 'production' environment for GitHub Actions deployment jobs
                subjects.add(f"repo:{repo}:environment:production")
                
                current_branch = _detect_current_branch()
                if current_branch and current_branch != default_branch:
                    subjects.add(f"repo:{repo}:ref:refs/heads/{current_branch}")

            for subject in sorted(subjects):
                _ensure_federated_credential(app_id=azure_client_id, repo=repo, subject=subject)
    if azure_tenant_id:
        _set_variable(repo=repo, name="AZURE_TENANT_ID", value=azure_tenant_id, dry_run=dry_run)
    if azure_subscription_id:
        _set_variable(repo=repo, name="AZURE_SUBSCRIPTION_ID", value=azure_subscription_id, dry_run=dry_run)

    # 1) Always store runtime dotenv as a secret.
    _set_secret(repo=repo, name="RUNTIME_ENV_DOTENV", value=runtime_text, dry_run=dry_run)

    # 1b) Also sync specific runtime keys needed by the workflow directly.
    # Parse the runtime env to extract individual values.
    runtime_kv = dotenv_values(stream=io.StringIO(runtime_text))
    
    # BASIC_AUTH_USER -> variable
    basic_auth_user = str(runtime_kv.get("BASIC_AUTH_USER") or "").strip()
    if basic_auth_user:
        _set_variable(repo=repo, name="BASIC_AUTH_USER", value=basic_auth_user, dry_run=dry_run)
    
    # BASIC_AUTH_HASH -> secret (contains bcrypt hash)
    basic_auth_hash = str(runtime_kv.get("BASIC_AUTH_HASH") or "").strip()
    if basic_auth_hash:
        _set_secret(repo=repo, name="BASIC_AUTH_HASH", value=basic_auth_hash, dry_run=dry_run)

    if args.only_files:
        return

    if not args.also_sync_keys:
        return

    # 2) Optionally sync deploy-time keys.
    for k, v in deploy_kv.items():
        if v is None:
            continue
        key = str(k).strip()
        val = str(v).strip()
        if not key or not val:
            continue

        # These are handled above (and may be auto-filled).
        if key in REQUIRED_FOR_AZURE_LOGIN:
            continue

        # Force variables for known non-secret keys.
        if key in FORCE_VARIABLE_KEYS:
            _set_variable(repo=repo, name=key, value=val, dry_run=dry_run)
            continue

        # Heuristic: secrets for tokens/passwords/keys/hashes; variables for the rest.
        if SECRET_KEY_RE.search(key):
            _set_secret(repo=repo, name=key, value=val, dry_run=dry_run)
        else:
            _set_variable(repo=repo, name=key, value=val, dry_run=dry_run)


if __name__ == "__main__":
    main()
