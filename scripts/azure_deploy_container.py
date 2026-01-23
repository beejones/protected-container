#!/usr/bin/env python3
"""Deploy protected-azure-container to Azure Container Instances (ACI).

Model:
- Multi-container group:
  - protected-azure-container app (code-server)
  - Caddy TLS proxy (HTTPS + reverse proxy; Basic Auth)
- Secrets:
  - Full .env is stored as a Key Vault secret (default: 'env')
  - App container fetches env at startup via Managed Identity
  - Basic Auth is configured via ACI secure env vars (recommended)

Notes:
- Exposes only 80/443 publicly. code-server is behind Caddy at https://<domain>/
- All access is protected by Basic Auth
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv


# Add scripts dir to path to allow importing sibling modules when running as a script.
sys.path.append(str(Path(__file__).parent))

import azure_deploy_container_helpers as deploy_helpers
import azure_deploy_yaml_helpers as yaml_helpers

try:
    from azure_utils import kv_data_plane_available, kv_secret_set_quiet, run_az_command
except ImportError:
    sys.path.append("scripts")
    from azure_utils import kv_data_plane_available, kv_secret_set_quiet, run_az_command


DEFAULT_CPU_CORES = 1.0
DEFAULT_MEMORY_GB = 2.0
DEFAULT_OIDC_APP_NAME = "github-actions-aci-deploy"


# Keep helper wiring centralized here; `main()` continues to use the historic names.
materialize_deploy_env_file_if_missing = deploy_helpers.materialize_deploy_env_file_if_missing
ensure_oidc_app_and_sp = deploy_helpers.ensure_oidc_app_and_sp
sync_github_actions_vars_secrets = deploy_helpers.sync_github_actions_vars_secrets

ensure_infra = deploy_helpers.ensure_infra
ensure_oidc_app_role_assignment = deploy_helpers.ensure_oidc_app_role_assignment

docker_pull = deploy_helpers.docker_pull
docker_login = deploy_helpers.docker_login
docker_build = deploy_helpers.docker_build
docker_push = deploy_helpers.docker_push

parse_image_ref = deploy_helpers.parse_image_ref
ghcr_repo_prefix_for_image = deploy_helpers.ghcr_repo_prefix_for_image

is_interactive = deploy_helpers.is_interactive
az_logged_in = deploy_helpers.az_logged_in

kv_secret_get = deploy_helpers.kv_secret_get
kv_secret_set = deploy_helpers.kv_secret_set

prompt_value = deploy_helpers.prompt_value
prompt_secret = deploy_helpers.prompt_secret
prompt_yes_no = deploy_helpers.prompt_yes_no

truthy = deploy_helpers.truthy
looks_like_bcrypt_hash = deploy_helpers.looks_like_bcrypt_hash
bcrypt_hash_password = deploy_helpers.bcrypt_hash_password
resolve_value = deploy_helpers.resolve_value

get_storage_key = deploy_helpers.get_storage_key
get_identity_details = deploy_helpers.get_identity_details
ensure_file_share_exists = deploy_helpers.ensure_file_share_exists

_env_filtered_content = deploy_helpers._env_filtered_content
_format_keyvault_set_help = deploy_helpers._format_keyvault_set_help
_hint_for_ghcr_scope_error = deploy_helpers._hint_for_ghcr_scope_error


def generate_deploy_yaml(
    *,
    name: str,
    location: str,
    image: str,
    registry_server: str | None,
    registry_username: str | None,
    registry_password: str | None,
    identity_id: str,
    identity_client_id: str | None,
    identity_tenant_id: str | None,
    storage_name: str,
    storage_key: str,
    kv_name: str,
    dns_label: str,
    public_domain: str,
    acme_email: str,
    basic_auth_user: str,
    basic_auth_hash: str,
    cpu_cores: float,
    memory_gb: float,
    share_workspace: str,
    caddy_data_share_name: str,
    caddy_config_share_name: str,
    caddy_image: str,
) -> str:
    """Back-compat re-export for tests and external callers."""

    return yaml_helpers.generate_deploy_yaml(
        name=name,
        location=location,
        image=image,
        registry_server=registry_server,
        registry_username=registry_username,
        registry_password=registry_password,
        identity_id=identity_id,
        identity_client_id=identity_client_id,
        identity_tenant_id=identity_tenant_id,
        storage_name=storage_name,
        storage_key=storage_key,
        kv_name=kv_name,
        dns_label=dns_label,
        public_domain=public_domain,
        acme_email=acme_email,
        basic_auth_user=basic_auth_user,
        basic_auth_hash=basic_auth_hash,
        cpu_cores=cpu_cores,
        memory_gb=memory_gb,
        share_workspace=share_workspace,
        caddy_data_share_name=caddy_data_share_name,
        caddy_config_share_name=caddy_config_share_name,
        caddy_image=caddy_image,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy protected-azure-container to Azure Container Instances")

    # These can come from --env-file (recommended) so they are not required.
    parser.add_argument("--resource-group", "-g", required=False, default=None)
    parser.add_argument("--location", "-l", default=None)
    parser.add_argument("--container-name", "-n", default=None)
    parser.add_argument("--dns-label", default=None, help="DNS label for <label>.<location>.azurecontainer.io")

    parser.add_argument("--image", "-i", default=None, help="Container image URL")

    parser.add_argument("--storage-name", default=None)
    parser.add_argument("--identity-name", default=None)
    parser.add_argument("--keyvault-name", default=None)

    parser.add_argument("--share-workspace", default=None)
    parser.add_argument("--caddy-data-share-name", default=None)
    parser.add_argument("--caddy-config-share-name", default=None)

    parser.add_argument("--public-domain", default=None)
    parser.add_argument("--acme-email", default=None)

    parser.add_argument("--basic-auth-user", default=None)
    parser.add_argument(
        "--basic-auth-hash",
        default=None,
        help="Basic Auth bcrypt hash. If you pass a plain password instead, the script will compute the bcrypt hash automatically.",
    )
    parser.add_argument(
        "--basic-auth-password",
        default=None,
        help="Basic Auth password (used to compute bcrypt hash if --basic-auth-hash not provided)",
    )
    parser.add_argument(
        "--bcrypt-cost",
        type=int,
        default=14,
        help="bcrypt cost for generated hash (default: 14)",
    )

    parser.add_argument("--registry-server", default=None, help="Container registry server (e.g. ghcr.io)")
    parser.add_argument("--registry-username", default=None, help="Registry username (for private images)")
    parser.add_argument("--registry-password", default=None, help="Registry password/token (for private images)")

    parser.add_argument(
        "--build",
        action="store_true",
        help="Build the container image locally before deploy (docker build)",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push the container image before deploy (docker push)",
    )
    parser.add_argument(
        "--build-push",
        action="store_true",
        help="Build and push the container image before deploy",
    )

    parser.add_argument(
        "--publish",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Build + push the image before deploy (default: enabled when GHCR_PRIVATE=true)",
    )
    parser.add_argument(
        "--docker-context",
        default=None,
        help="Docker build context directory (default: repo root)",
    )
    parser.add_argument(
        "--dockerfile",
        default=None,
        help="Optional Dockerfile path (default: use Docker's default resolution)",
    )

    parser.add_argument("--interactive", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument(
        "--persist-to-keyvault",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Offer to save entered deploy-time values to Key Vault secrets (default: off)",
    )

    parser.add_argument("--public-domain-secret", default="public-domain")
    parser.add_argument("--acme-email-secret", default="acme-email")
    parser.add_argument("--basic-auth-user-secret", default="basic-auth-user")
    parser.add_argument("--basic-auth-hash-secret", default="basic-auth-hash")
    parser.add_argument("--image-secret", default="image")
    parser.add_argument("--registry-username-secret", default="registry-username")
    parser.add_argument("--registry-password-secret", default="registry-password")
    parser.add_argument("--registry-server-secret", default="registry-server")

    parser.add_argument(
        "--env-file",
        default=None,
        help=(
            "Env file to load for deploy-time values. If omitted, auto-detects (in order): "
            ".env.deploy, env.deploy, .env"
        ),
    )

    parser.add_argument(
        "--azure-oidc-app-name",
        default=DEFAULT_OIDC_APP_NAME,
        help=f"Azure AD App Registration name for GitHub Actions OIDC (default: {DEFAULT_OIDC_APP_NAME})",
    )

    parser.add_argument(
        "--set-vars-secrets",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Sync deploy-time vars/secrets to GitHub Actions (via scripts/gh_sync_actions_env.py). "
            "Default: enabled. Use --no-set-vars-secrets in CI."
        ),
    )

    parser.add_argument(
        "--upload-env",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Upload runtime env to Key Vault secret 'env' before deploy (default: enabled)",
    )
    parser.add_argument(
        "--upload-env-file",
        default=None,
        help="Path to runtime env file to upload (default: repo root .env)",
    )
    parser.add_argument(
        "--upload-env-secret-name",
        default="env",
        help="Key Vault secret name for runtime env (default: env)",
    )
    parser.add_argument(
        "--upload-env-prefixes",
        default="BASIC_AUTH_",
        help="Comma-separated prefixes to include when uploading env (default: BASIC_AUTH_)",
    )
    parser.add_argument(
        "--upload-env-raw",
        action="store_true",
        help="Upload the full env file content (DANGER: may include deploy-only secrets)",
    )

    parser.add_argument(
        "--prefetch-images",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pre-pull Caddy image locally to validate it exists (default: enabled)",
    )

    parser.add_argument("--cpu", type=float, default=DEFAULT_CPU_CORES)
    parser.add_argument("--memory", type=float, default=DEFAULT_MEMORY_GB)

    # Prefer a stable mirror to avoid Docker Hub rate limiting in ACI.
    # Note: ghcr.io/caddyserver/caddy does not publish a '2-alpine' tag; we use a mirror.
    parser.add_argument("--caddy-image", default="caddy:2-alpine")

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]

    interactive = is_interactive() if args.interactive is None else bool(args.interactive)
    # Key Vault is used at *runtime* by the container to fetch the full .env secret.
    # For deploy-time inputs (image/domain/registry creds), default to local env/args.
    persist_to_kv = bool(args.persist_to_keyvault)

    # Load deploy-time values.
    # We load .env (runtime config) first, then .env.deploy (deploy-time overrides) on top.
    
    # 1. Load .env (if exists)
    runtime_env_path = repo_root / ".env"
    if runtime_env_path.exists():
        load_dotenv(dotenv_path=str(runtime_env_path), override=False)

    # 2. Load .env.deploy (or custom file)
    deploy_env_path: Path | None = None
    if args.env_file:
        deploy_env_path = Path(args.env_file).expanduser().resolve()
    else:
        for candidate in (repo_root / ".env.deploy", repo_root / "env.deploy"):
            if candidate.exists():
                deploy_env_path = candidate
                break

    # If no deploy env file exists, but we are defaulting, use .env.deploy path for materialization
    if deploy_env_path is None:
        deploy_env_path = repo_root / ".env.deploy"
        
    # load_dotenv() is a no-op if the file doesn't exist.
    # override=True ensures deploy-time vars take precedence over runtime vars.
    if deploy_env_path is not None and deploy_env_path.exists():
        load_dotenv(dotenv_path=str(deploy_env_path), override=True)
    elif not runtime_env_path.exists():
        # If neither exists, materialize .env.deploy if we have env vars (CI case)
        materialize_deploy_env_file_if_missing(path=deploy_env_path)

    if not az_logged_in():
        raise SystemExit("Not logged into Azure. Run: az login")

    # Resolve Azure OIDC App (create if missing) so sync script has correct ID.
    # Prioritize: Env EnvVar -> Arg Default -> Lookup/Create
    oidc_client_id = (os.getenv("AZURE_CLIENT_ID") or os.getenv("AZURE_APP_ID") or "").strip()
    if not oidc_client_id and bool(args.set_vars_secrets):
        oidc_app_name = (args.azure_oidc_app_name or DEFAULT_OIDC_APP_NAME).strip()
        oidc_client_id = ensure_oidc_app_and_sp(display_name=oidc_app_name)
        # Set in env so downstream logic can use it
        os.environ["AZURE_CLIENT_ID"] = oidc_client_id

    # Keep GitHub Actions vars/secrets in sync by default (so CI has what it needs).
    # In CI, pass --no-set-vars-secrets.
    if bool(args.set_vars_secrets):
        sync_github_actions_vars_secrets(repo_root=repo_root, deploy_env_path=deploy_env_path, azure_client_id=oidc_client_id)

    rg = (args.resource_group or os.getenv("AZURE_RESOURCE_GROUP") or os.getenv("RESOURCE_GROUP") or "").strip()
    if not rg:
        raise SystemExit(
            "Missing resource group. Provide --resource-group, or set AZURE_RESOURCE_GROUP in env.deploy/.env.deploy (or pass --env-file)."
        )

    location = (args.location or os.getenv("AZURE_LOCATION") or os.getenv("LOCATION") or "westeurope").strip() or "westeurope"
    name = (args.container_name or os.getenv("AZURE_CONTAINER_NAME") or os.getenv("ACI_CONTAINER_NAME") or "protected-azure-container").strip() or "protected-azure-container"
    dns_label = (args.dns_label or name).strip().lower()

    storage_name = (args.storage_name or f"{rg}stg").replace("-", "")
    storage_name = "".join([c for c in storage_name.lower() if c.isalnum()])[:24]

    # Sanitize Key Vault name: <24 chars, alphanumeric/hyphens, no start/end hyphen.
    # Default: derived from RG name.
    # We strip hyphens to save space and reduce risk of consecutive hyphens.
    identity_name = args.identity_name or f"{rg}-identity"

    if args.keyvault_name:
        kv_name = args.keyvault_name
    else:
        # e.g. "protected-azure-container-rg" -> "protectedazurecontainkv"
        base = "".join([c for c in rg.lower() if c.isalnum()])
        kv_name = f"{base}kv"[:24]

    # Ensure Azure resources exist so a single azure_deploy_container invocation can bootstrap infra.
    shares_to_ensure = [
        args.share_workspace or f"{name}-workspace",
        args.caddy_data_share_name or f"{name}-caddy-data",
        args.caddy_config_share_name or f"{name}-caddy-config",
    ]
    ensure_infra(
        resource_group=rg,
        location=location,
        container_name=name,
        identity_name=identity_name,
        keyvault_name=kv_name,
        storage_name=storage_name,
        shares=shares_to_ensure,
    )

    subscription_id = (os.getenv("AZURE_SUBSCRIPTION_ID") or "").strip()
    if not subscription_id:
        subscription_id = str(
            run_az_command(["account", "show", "--query", "id", "-o", "tsv"], capture_output=True)
        ).strip()
    if oidc_client_id and subscription_id:
        ensure_oidc_app_role_assignment(
            subscription_id=subscription_id, 
            resource_group=rg, 
            client_id=oidc_client_id,
            keyvault_name=kv_name
        )

    # Upload runtime env to Key Vault for the container to fetch at startup.
    # By default we upload only BASIC_AUTH_* keys to avoid leaking deploy credentials.
    if args.upload_env:
        # By default, always upload the repo root .env (runtime) so KV has the latest
        # runtime configuration, even if deploy-time values are loaded from .env.deploy.
        default_runtime_env = repo_root / ".env"
        upload_env_path = Path(args.upload_env_file).resolve() if args.upload_env_file else default_runtime_env

        # Safety: never upload deploy-only env files to Key Vault.
        if upload_env_path.name in {"env.deploy", ".env.deploy"}:
            raise SystemExit(
                f"Refusing to upload deploy-only env file to Key Vault: {upload_env_path}. "
                "Put runtime settings in .env (repo root) or pass --upload-env-file <runtime_env>."
            )
        if not upload_env_path.exists():
            raise SystemExit(
                f"Runtime env file not found: {upload_env_path}. "
                "Create .env (runtime) or pass --no-upload-env if you want to deploy without uploading."
            )

        prefixes = [p.strip() for p in (args.upload_env_prefixes or "").split(",") if p.strip()]
        try:
            env_content = _env_filtered_content(env_path=upload_env_path, prefixes=prefixes, raw=bool(args.upload_env_raw))
            kv_secret_set_quiet(vault_name=kv_name, secret_name=str(args.upload_env_secret_name), value=env_content)
        except subprocess.CalledProcessError as e:
            print(_format_keyvault_set_help(vault_name=kv_name, stderr=getattr(e, "stderr", None)), file=sys.stderr)
            raise SystemExit(1)

    kv_name_for_secrets = ""
    if persist_to_kv:
        kv_ok = kv_data_plane_available(kv_name)
        if not kv_ok:
            print("[deploy] Disabling --persist-to-keyvault because Key Vault is not reachable.", file=sys.stderr)
            persist_to_kv = False
        else:
            kv_name_for_secrets = kv_name

    share_workspace = shares_to_ensure[0]
    caddy_data_share = shares_to_ensure[1]
    caddy_config_share = shares_to_ensure[2]

    image = resolve_value(
        name="image",
        arg_value=args.image,
        env_names=["CONTAINER_IMAGE", "IMAGE", "GHCR_IMAGE"],
        kv_name=kv_name_for_secrets,
        kv_secret_name=args.image_secret,
        interactive=interactive,
        secret=False,
        prompt_label="Container image (e.g. ghcr.io/<owner>/protected-azure-container:tag)",
        persist_to_kv=persist_to_kv,
    )
    if not image:
        raise SystemExit(
            "Missing container image. Provide --image, set GHCR_IMAGE, or store Key Vault secret 'image'."
        )

    # Resolve build/push mode.
    build_requested = bool(args.build or args.build_push)
    push_requested = bool(args.push or args.build_push)

    public_domain = resolve_value(
        name="public_domain",
        arg_value=args.public_domain,
        env_names=["PUBLIC_DOMAIN", "AZURE_PUBLIC_DOMAIN"],
        kv_name=kv_name_for_secrets,
        kv_secret_name=args.public_domain_secret,
        interactive=interactive,
        secret=False,
        prompt_label="Public domain (e.g. yourdomain.com)",
        persist_to_kv=persist_to_kv,
    )
    if not public_domain:
        raise SystemExit(
            "Missing public domain. Provide --public-domain, set AZURE_PUBLIC_DOMAIN, or store Key Vault secret 'public-domain'."
        )

    acme_email = resolve_value(
        name="acme_email",
        arg_value=args.acme_email,
        env_names=["ACME_EMAIL", "AZURE_ACME_EMAIL"],
        kv_name=kv_name_for_secrets,
        kv_secret_name=args.acme_email_secret,
        interactive=interactive,
        secret=False,
        prompt_label="ACME email (Let's Encrypt)",
        persist_to_kv=persist_to_kv,
    )
    if not acme_email:
        raise SystemExit(
            "Missing ACME email. Provide --acme-email, set AZURE_ACME_EMAIL, or store Key Vault secret 'acme-email'."
        )

    basic_auth_user = resolve_value(
        name="basic_auth_user",
        arg_value=args.basic_auth_user,
        env_names=["BASIC_AUTH_USER"],
        kv_name=kv_name_for_secrets,
        kv_secret_name=args.basic_auth_user_secret,
        interactive=interactive,
        secret=False,
        prompt_label="Basic Auth username",
        default="admin",
        persist_to_kv=persist_to_kv,
    ) or "admin"

    # Only resolve an existing hash from args/env/Key Vault. Do not prompt for a hash.
    basic_auth_hash_or_password = resolve_value(
        name="basic_auth_hash",
        arg_value=args.basic_auth_hash,
        env_names=["BASIC_AUTH_HASH"],
        kv_name=kv_name_for_secrets,
        kv_secret_name=args.basic_auth_hash_secret,
        interactive=False,
        secret=True,
        prompt_label=None,
        persist_to_kv=persist_to_kv,
    )

    basic_auth_hash: str | None = None
    if basic_auth_hash_or_password:
        if looks_like_bcrypt_hash(basic_auth_hash_or_password):
            basic_auth_hash = basic_auth_hash_or_password
        else:
            # Treat as plaintext password and compute bcrypt hash.
            try:
                basic_auth_hash = bcrypt_hash_password(basic_auth_hash_or_password, cost=args.bcrypt_cost)
            except Exception as e:
                raise SystemExit(f"Failed to compute bcrypt hash for password provided via --basic-auth-hash: {e}")

    if not basic_auth_hash:
        # Ask for password and compute the bcrypt hash (Caddy-compatible).
        basic_auth_password = resolve_value(
            name="basic_auth_password",
            arg_value=args.basic_auth_password,
            env_names=["BASIC_AUTH_PASSWORD"],
            kv_name=kv_name_for_secrets,
            kv_secret_name=None,
            interactive=interactive,
            secret=True,
            prompt_label="Basic Auth password",
            persist_to_kv=False,
        )
        if not basic_auth_password:
            raise SystemExit(
                "Missing Basic Auth password. Provide --basic-auth-password (or BASIC_AUTH_PASSWORD), or store Key Vault secret 'basic-auth-hash'."
            )

        try:
            basic_auth_hash = bcrypt_hash_password(basic_auth_password, cost=args.bcrypt_cost)
        except Exception as e:
            raise SystemExit(f"Failed to compute bcrypt hash for password: {e}")

        # Offer to persist the computed hash.
        if persist_to_kv and args.basic_auth_hash_secret and interactive:
            if prompt_yes_no(
                f"Save computed bcrypt hash to Key Vault secret '{args.basic_auth_hash_secret}'?",
                default=True,
            ):
                try:
                    kv_secret_set(kv_name, args.basic_auth_hash_secret, basic_auth_hash)
                except subprocess.CalledProcessError as e:
                    print(
                        "WARNING: Failed to save computed hash to Key Vault; continuing without persisting.",
                        file=sys.stderr,
                    )
                    print(
                        _format_keyvault_set_help(vault_name=kv_name, stderr=getattr(e, "stderr", None)),
                        file=sys.stderr,
                    )

    # Optional registry credentials for private images (e.g. GHCR).
    # If deploying a public image, do not prompt for registry settings.
    ghcr_private = truthy(os.getenv("GHCR_PRIVATE"))

    # If the image is private and the user didn't specify any build/push flags,
    # default to publishing the image so a single command works end-to-end.
    if not (args.build or args.push or args.build_push):
        # Default to build-push unless explicitly disabled via --no-publish
        publish_default = True
        publish = publish_default if args.publish is None else bool(args.publish)
        if publish:
            build_requested = True
            push_requested = True

    registry_username_seed = (args.registry_username or os.getenv("REGISTRY_USERNAME") or os.getenv("GHCR_USERNAME") or "").strip()
    registry_password_seed = (args.registry_password or os.getenv("REGISTRY_PASSWORD") or os.getenv("GHCR_TOKEN") or "").strip()
    registry_server_seed = (args.registry_server or os.getenv("REGISTRY_SERVER") or "").strip()

    wants_registry_creds = ghcr_private or push_requested or any(
        [
            bool(registry_username_seed),
            bool(registry_password_seed),
            bool(registry_server_seed),
            args.registry_server is not None,
            args.registry_username is not None,
            args.registry_password is not None,
        ]
    )

    registry_server: str | None = None
    registry_username: str | None = None
    registry_password: str | None = None

    if wants_registry_creds:
        inferred_registry, _ = parse_image_ref(image)
        inferred_registry = inferred_registry or ("ghcr.io" if image.startswith("ghcr.io/") else None)

        # When pulling from a private GHCR image, infer the registry server from the image
        # so the user does not get prompted for it.
        registry_server_arg = args.registry_server
        if registry_server_arg is None and not registry_server_seed and (ghcr_private or push_requested) and inferred_registry:
            registry_server_arg = inferred_registry

        registry_server = resolve_value(
            name="registry_server",
            arg_value=registry_server_arg,
            env_names=["REGISTRY_SERVER"],
            kv_name=kv_name_for_secrets,
            kv_secret_name=args.registry_server_secret,
            interactive=interactive,
            secret=False,
            prompt_label="Registry server",
            default="ghcr.io" if image.startswith("ghcr.io/") else None,
            persist_to_kv=persist_to_kv,
        )

        # Infer username for GHCR if not provided
        registry_username_default = None
        if not args.registry_username and not registry_username_seed and image.startswith("ghcr.io/"):
            try:
                # ghcr.io/owner/repo
                registry_username_default = image.split("/")[1]
            except IndexError:
                pass

        registry_username = resolve_value(
            name="registry_username",
            arg_value=args.registry_username,
            env_names=["REGISTRY_USERNAME", "GHCR_USERNAME"],
            kv_name=kv_name_for_secrets,
            kv_secret_name=args.registry_username_secret,
            interactive=interactive,
            secret=False,
            prompt_label="Registry username",
            persist_to_kv=persist_to_kv,
            default=registry_username_default,
        )

        registry_password = resolve_value(
            name="registry_password",
            arg_value=args.registry_password,
            env_names=["REGISTRY_PASSWORD", "GHCR_TOKEN"],
            kv_name=kv_name_for_secrets,
            kv_secret_name=args.registry_password_secret,
            interactive=interactive,
            secret=True,
            prompt_label="Registry token/password",
            persist_to_kv=persist_to_kv,
        )

        if ghcr_private and not (registry_server and registry_username and registry_password):
            raise SystemExit(
                "GHCR_PRIVATE=true but registry credentials are incomplete. Set GHCR_USERNAME/GHCR_TOKEN (and optionally REGISTRY_SERVER=ghcr.io) or pass --registry-*."
            )

    # If we are pushing, ensure we have registry info/creds.
    if push_requested:
        inferred_registry, _ = parse_image_ref(image)
        inferred_registry = inferred_registry or ("ghcr.io" if image.startswith("ghcr.io/") else None)

        # If user didn't set REGISTRY_SERVER, infer it from image.
        if not registry_server and inferred_registry:
            registry_server = inferred_registry

        if not registry_server:
            raise SystemExit(
                "Cannot determine registry server for push. Set REGISTRY_SERVER (e.g. ghcr.io) or pass --registry-server."
            )

        # For pushes, credentials are required even if the image is public.
        if not (registry_username and registry_password):
            raise SystemExit(
                "--push/--build-push requires registry credentials. Set GHCR_USERNAME/GHCR_TOKEN (or REGISTRY_USERNAME/REGISTRY_PASSWORD) or pass --registry-username/--registry-password."
            )

    # Build/push before deploy if requested.
    if build_requested or push_requested:
        # Docker operations happen from the repo root by default.
        docker_context = (args.docker_context or str(repo_root)).strip() or str(repo_root)
        dockerfile = (args.dockerfile or "").strip() or None

        if not dockerfile and not args.docker_context:
            if (repo_root / "docker" / "Dockerfile").exists():
                # If docker/Dockerfile exists and no context given,
                # assume the user wants to build the inner "docker" directory as a context.
                docker_context = str(repo_root / "docker")
                # Leave dockerfile=None so it defaults to "Dockerfile" inside that context.
                dockerfile = None

        if build_requested:
            print(f"[docker] building image: {image}")
            try:
                docker_build(image=image, context_dir=docker_context, dockerfile=dockerfile)
            except FileNotFoundError:
                raise SystemExit("Docker not found. Install Docker and ensure 'docker' is on PATH.")

        if push_requested:
            assert registry_server and registry_username and registry_password
            try:
                docker_login(registry=registry_server, username=registry_username, token=registry_password)
                print(f"[docker] pushing image: {image}")
                try:
                    docker_push(image=image)
                except subprocess.CalledProcessError as e:
                    hint = _hint_for_ghcr_scope_error(getattr(e, "stderr", None))
                    if hint:
                        print(hint, file=sys.stderr)
                    raise
            except FileNotFoundError:
                raise SystemExit("Docker not found. Install Docker and ensure 'docker' is on PATH.")

    # Normalize: if no username/password provided, treat registry creds as disabled.
    # This prevents a defaulted registry_server (e.g. ghcr.io) from triggering the
    # "partial credentials" failure for public images.
    if not registry_username and not registry_password:
        registry_server = None

    if any([registry_server, registry_username, registry_password]) and not all([registry_server, registry_username, registry_password]):
        raise SystemExit(
            "Partial registry credentials provided. You must set all of registry server/username/password or none (for public images)."
        )

    storage_key = get_storage_key(storage_name, rg)
    identity_id, identity_client_id, identity_tenant_id = get_identity_details(identity_name, rg)

    # Recreate container group for identity/env updates.
    # Delete existing container if any, then wait for Azure to fully clean up to prevent "Conflict" errors.
    run_az_command(["container", "delete", "--resource-group", rg, "--name", name, "--yes"], capture_output=False, ignore_errors=True)
    
    # Wait for container to be fully deleted (not just deletion initiated)
    print("[deploy] Waiting for previous container to be fully deleted...")
    max_wait = 120  # seconds
    poll_interval = 5
    waited = 0
    while waited < max_wait:
        # Check if container still exists
        result = run_az_command(
            ["container", "show", "--resource-group", rg, "--name", name, "--query", "provisioningState", "-o", "tsv"],
            capture_output=True,
            ignore_errors=True,
            verbose=False,
        )
        if result is None:
            # Container no longer exists
            print(f"[deploy] Previous container deleted after {waited}s")
            break
        state = str(result).strip().lower()
        if state in ("deleting", "pending"):
            print(f"[deploy] Container still {state}... waiting")
        time.sleep(poll_interval)
        waited += poll_interval
    else:
        print(f"[deploy] Warning: Timed out waiting for container deletion after {max_wait}s, proceeding anyway...")

    caddy_image = (args.caddy_image or "").strip() or "caddy:2-alpine"

    if args.prefetch_images:
        try:
            print(f"[docker] prefetching caddy image: {caddy_image}")
            docker_pull(image=caddy_image)

            # If we are using GHCR for the main image, mirror Caddy to GHCR as well to avoid
            # multi-registry conflicts (ACI "RegistryErrorResponse" from Docker Hub).
            # We assume if the user is pushing/using 'ghcr.io', we can also push caddy there.
            if registry_server and "ghcr.io" in registry_server and registry_username:
                # Prefer keeping Caddy in the same ghcr.io/<owner>/<repo>/... namespace as the
                # main image. This avoids pushing to ghcr.io/<owner>/caddy, which often fails in
                # GitHub Actions due to package scoping/permissions.
                repo_prefix = ghcr_repo_prefix_for_image(image=image, registry_server=registry_server)
                if not repo_prefix:
                    repo_prefix = f"{registry_server}/{registry_username}"

                caddy_mirror_tag = f"{repo_prefix}/caddy:2-alpine"

                if caddy_image == caddy_mirror_tag:
                    print(f"[docker] Caddy image already in GHCR namespace: {caddy_image}")
                else:
                    print(f"[docker] Mirroring caddy to GHCR: {caddy_mirror_tag}")
                    try:
                        # Retag
                        subprocess.run(["docker", "tag", caddy_image, caddy_mirror_tag], check=True, capture_output=True)
                        # Push
                        docker_push(image=caddy_mirror_tag)
                        # Use the mirrored image in the YAML
                        caddy_image = caddy_mirror_tag
                        print(f"[docker] Successfully mirrored caddy. Using: {caddy_image}")
                    except subprocess.CalledProcessError as e:
                        hint = _hint_for_ghcr_scope_error(getattr(e, "stderr", None))
                        if hint:
                            print(hint, file=sys.stderr)
                        print(f"[warn] Failed to mirror caddy to GHCR ({e}); falling back to {caddy_image}", file=sys.stderr)
                    except Exception as e:
                        print(f"[warn] Failed to mirror caddy to GHCR ({e}); falling back to {caddy_image}", file=sys.stderr)

        except Exception as e:
            print(f"[warn] Could not prefetch caddy image locally ({e}); continuing.", file=sys.stderr)

    yaml_text = generate_deploy_yaml(
        name=name,
        location=location,
        image=image,
        registry_server=registry_server,
        registry_username=registry_username,
        registry_password=registry_password,
        identity_id=identity_id,
        identity_client_id=identity_client_id,
        identity_tenant_id=identity_tenant_id,
        storage_name=storage_name,
        storage_key=storage_key,
        kv_name=kv_name,
        dns_label=dns_label,
        public_domain=public_domain,
        acme_email=acme_email,
        basic_auth_user=basic_auth_user,
        basic_auth_hash=basic_auth_hash,
        cpu_cores=args.cpu,
        memory_gb=args.memory,
        share_workspace=share_workspace,
        caddy_data_share_name=caddy_data_share,
        caddy_config_share_name=caddy_config_share,
        caddy_image=caddy_image,
    )

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(yaml_text)
        yaml_path = f.name

    print(f"[deploy] wrote: {yaml_path}")

    # Retry container creation with exponential backoff for transient registry errors
    max_retries = 5
    base_delay = 10.0  # seconds
    for attempt in range(1, max_retries + 1):
        try:
            run_az_command(["container", "create", "--resource-group", rg, "--file", yaml_path], capture_output=False)
            break  # Success
        except subprocess.CalledProcessError as e:
            err = getattr(e, "stderr", "") or ""
            # Check if it's a transient registry conflict error or generic registry error
            # Examples:
            # - 'Conflict':'RegistryErrorResponse'
            # - (RegistryErrorResponse) An error response is received from the docker registry
            is_transient = "RegistryErrorResponse" in err or "Conflict" in err
            if is_transient and attempt < max_retries:
                sleep_time = min(60.0, base_delay * (2 ** (attempt - 1)))
                print(f"[deploy] Registry conflict error (attempt {attempt}/{max_retries}). Retrying in {sleep_time:.0f}s...")
                time.sleep(sleep_time)
            else:
                # Not a transient error or out of retries
                raise

    print("\n[done] Deployed.")
    print(f"  FQDN: {dns_label}.{location}.azurecontainer.io")
    print(f"  https://{public_domain}/  (VS Code)")



if __name__ == "__main__":
    raise SystemExit(main())
