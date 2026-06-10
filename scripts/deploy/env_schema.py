"""Deterministic environment variable/secret schema for deployment.

This module is the single source of truth for:
- which keys exist (vars vs secrets)
- where they are expected to live (.env, .env.deploy, GitHub Actions vars/secrets)
- whether they are mandatory and/or have defaults

Design goals:
- No heuristic classification (no regex guessing).
- No backwards compatibility aliases.
- Fail fast with clear error messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping

from dotenv import dotenv_values


class EnvTarget(str, Enum):
    DOTENV_RUNTIME = "dotenv_runtime"  # `.env`
    DOTENV_SECRETS = "dotenv_secrets"  # `.env.secrets`
    DOTENV_DEPLOY = "dotenv_deploy"  # `.env.deploy`
    DOTENV_DEPLOY_SECRETS = "dotenv_deploy_secrets"  # `.env.deploy.secrets`
    GH_ACTIONS_VAR = "gh_actions_var"  # GitHub Actions variable
    GH_ACTIONS_SECRET = "gh_actions_secret"  # GitHub Actions secret
    KEYVAULT_SECRET = "keyvault_secret"  # Azure Key Vault secret


class KeyVaultSecretName(str, Enum):
    ENV = "env"  # stores full runtime `.env` content
    ENV_SECRETS = "env-secrets"  # stores full runtime `.env.secrets` content


class VarsEnum(str, Enum):
    # Azure identity / subscription (OIDC)
    AZURE_CLIENT_ID = "AZURE_CLIENT_ID"
    AZURE_TENANT_ID = "AZURE_TENANT_ID"
    AZURE_SUBSCRIPTION_ID = "AZURE_SUBSCRIPTION_ID"
    AZURE_OIDC_APP_NAME = "AZURE_OIDC_APP_NAME"

    # Azure deployment config
    AZURE_RESOURCE_GROUP = "AZURE_RESOURCE_GROUP"
    AZURE_LOCATION = "AZURE_LOCATION"
    AZURE_CONTAINER_NAME = "AZURE_CONTAINER_NAME"
    AZURE_DNS_LABEL = "AZURE_DNS_LABEL"
    AZURE_FILE_SHARE_QUOTA_GB = "AZURE_FILE_SHARE_QUOTA_GB"

    # Domain / TLS
    PUBLIC_DOMAIN = "PUBLIC_DOMAIN"
    ACME_EMAIL = "ACME_EMAIL"

    # Image / registry
    APP_IMAGE = "APP_IMAGE"
    GHCR_PRIVATE = "GHCR_PRIVATE"
    GHCR_USERNAME = "GHCR_USERNAME"

    # Defaults / sizing
    APP_CPU_CORES = "APP_CPU_CORES"
    APP_MEMORY_GB = "APP_MEMORY_GB"

    # Customization Hooks
    DEPLOY_HOOKS_MODULE = "DEPLOY_HOOKS_MODULE"
    DEPLOY_HOOKS_SOFT_FAIL = "DEPLOY_HOOKS_SOFT_FAIL"

    # Caddy / Sidecar
    CADDY_IMAGE = "CADDY_IMAGE"
    CADDY_CPU_CORES = "CADDY_CPU_CORES"
    CADDY_MEMORY_GB = "CADDY_MEMORY_GB"

    # Other / Extra
    OTHER_IMAGE = "OTHER_IMAGE"
    OTHER_CPU_CORES = "OTHER_CPU_CORES"
    OTHER_MEMORY_GB = "OTHER_MEMORY_GB"

    # Staging
    STAGING_PUBLIC_DOMAIN = "STAGING_PUBLIC_DOMAIN"
    STAGING_REMOTE_DIR = "STAGING_REMOTE_DIR"
    STAGING_PORTAINER_STACK_NAME = "STAGING_PORTAINER_STACK_NAME"

    # Runtime
    BASIC_AUTH_USER = "BASIC_AUTH_USER"
    APP_VERSION = "APP_VERSION"

    # Central edge auth / Authentik proxy gateway
    EDGE_AUTH_MODE = "EDGE_AUTH_MODE"
    EDGE_AUTH_GATEWAY = "EDGE_AUTH_GATEWAY"
    EDGE_AUTH_GATEWAY_SERVICE = "EDGE_AUTH_GATEWAY_SERVICE"
    EDGE_AUTH_GATEWAY_PORT = "EDGE_AUTH_GATEWAY_PORT"
    EDGE_AUTH_VERIFY_URI = "EDGE_AUTH_VERIFY_URI"
    EDGE_AUTH_COPY_HEADERS = "EDGE_AUTH_COPY_HEADERS"
    EDGE_AUTH_TOKEN_HEADER = "EDGE_AUTH_TOKEN_HEADER"
    EDGE_AUTH_DEFAULT_PROOF_LEVEL = "EDGE_AUTH_DEFAULT_PROOF_LEVEL"
    EDGE_AUTH_TOKEN_ISSUER = "EDGE_AUTH_TOKEN_ISSUER"
    AUTH_APPROVER_EMAIL = "AUTH_APPROVER_EMAIL"
    AUTH_AUDIENCE = "AUTH_AUDIENCE"
    AUTH_POLICY = "AUTH_POLICY"
    AUTH_PROOF_LEVEL = "AUTH_PROOF_LEVEL"
    AUTH_SECRET_REF = "AUTH_SECRET_REF"
    AUTHENTIK_PUBLIC_DOMAIN = "AUTHENTIK_PUBLIC_DOMAIN"
    AUTHENTIK_OUTPOST_SERVICE = "AUTHENTIK_OUTPOST_SERVICE"
    AUTHENTIK_POSTGRESQL__HOST = "AUTHENTIK_POSTGRESQL__HOST"
    AUTHENTIK_POSTGRESQL__PORT = "AUTHENTIK_POSTGRESQL__PORT"
    AUTHENTIK_POSTGRESQL__NAME = "AUTHENTIK_POSTGRESQL__NAME"
    AUTHENTIK_POSTGRESQL__USER = "AUTHENTIK_POSTGRESQL__USER"
    AUTHENTIK_STORAGE__BACKEND = "AUTHENTIK_STORAGE__BACKEND"
    AUTHENTIK_BACKUP_DIR = "AUTHENTIK_BACKUP_DIR"
    AUTHENTIK_EMAIL__HOST = "AUTHENTIK_EMAIL__HOST"
    AUTHENTIK_EMAIL__PORT = "AUTHENTIK_EMAIL__PORT"
    AUTHENTIK_EMAIL__USERNAME = "AUTHENTIK_EMAIL__USERNAME"
    AUTHENTIK_EMAIL__FROM = "AUTHENTIK_EMAIL__FROM"
    AUTHENTIK_EMAIL__USE_TLS = "AUTHENTIK_EMAIL__USE_TLS"
    AUTHENTIK_EMAIL__USE_SSL = "AUTHENTIK_EMAIL__USE_SSL"
    AUTHENTIK_BOOTSTRAP_EMAIL = "AUTHENTIK_BOOTSTRAP_EMAIL"
    AUTHENTIK_GOOGLE_CLIENT_ID = "AUTHENTIK_GOOGLE_CLIENT_ID"
    AUTHENTIK_MICROSOFT_CLIENT_ID = "AUTHENTIK_MICROSOFT_CLIENT_ID"
    AUTHENTIK_FACEBOOK_CLIENT_ID = "AUTHENTIK_FACEBOOK_CLIENT_ID"
    AUTHENTIK_SIGNING_KEY_REF = "AUTHENTIK_SIGNING_KEY_REF"

    # Storage-manager sidecar (consumed by docker/storage-manager compose via
    # ${SM_*:-default}; shipped in env.example, so the runtime schema must know them)
    SM_CHECK_INTERVAL_SECONDS = "SM_CHECK_INTERVAL_SECONDS"
    SM_LOG_LEVEL = "SM_LOG_LEVEL"
    SM_DB_PATH = "SM_DB_PATH"
    SM_API_PORT = "SM_API_PORT"


class SecretsEnum(str, Enum):
    # Image / registry
    GHCR_TOKEN = "GHCR_TOKEN"

    # Runtime
    BASIC_AUTH_HASH = "BASIC_AUTH_HASH"

    # App/runtime secret (optional; user-defined)
    APP_SECRET = "APP_SECRET"

    # Authentik / central edge auth secrets
    AUTHENTIK_SECRET_KEY = "AUTHENTIK_SECRET_KEY"
    AUTHENTIK_POSTGRESQL__PASSWORD = "AUTHENTIK_POSTGRESQL__PASSWORD"
    AUTHENTIK_BOOTSTRAP_PASSWORD_HASH = "AUTHENTIK_BOOTSTRAP_PASSWORD_HASH"
    AUTHENTIK_BOOTSTRAP_TOKEN = "AUTHENTIK_BOOTSTRAP_TOKEN"
    AUTHENTIK_API_TOKEN = "AUTHENTIK_API_TOKEN"
    AUTHENTIK_EMAIL__PASSWORD = "AUTHENTIK_EMAIL__PASSWORD"
    AUTHENTIK_GOOGLE_CLIENT_SECRET = "AUTHENTIK_GOOGLE_CLIENT_SECRET"
    AUTHENTIK_MICROSOFT_CLIENT_SECRET = "AUTHENTIK_MICROSOFT_CLIENT_SECRET"
    AUTHENTIK_FACEBOOK_CLIENT_SECRET = "AUTHENTIK_FACEBOOK_CLIENT_SECRET"

    # GitHub Actions meta-secret (not a container env var, but required by CI wiring)
    RUNTIME_ENV_DOTENV = "RUNTIME_ENV_DOTENV"
    RUNTIME_SECRETS_DOTENV = "RUNTIME_SECRETS_DOTENV"


@dataclass(frozen=True)
class EnvKeySpec:
    key: VarsEnum | SecretsEnum
    mandatory: bool
    default: str | None = None
    targets: frozenset[EnvTarget] = frozenset()
    keyvault_secret_name: KeyVaultSecretName | None = None


class EnvValidationError(ValueError):
    def __init__(self, *, context: str, problems: list[str]):
        super().__init__("; ".join(problems))
        self.context = context
        self.problems = problems

    def format(self) -> str:
        lines = [f"[env] validation failed: {self.context}"]
        for p in self.problems:
            lines.append(f"- {p}")
        return "\n".join(lines)


DERIVED_DEPLOY_ENV_KEYS: frozenset[str] = frozenset(
    {
        VarsEnum.AZURE_OIDC_APP_NAME.value,
    }
)

EDGE_AUTH_MODES: frozenset[str] = frozenset({"basic", "oidc", "public"})
EDGE_AUTH_GATEWAYS: frozenset[str] = frozenset({"authentik"})
AUTH_PROOF_LEVELS: frozenset[str] = frozenset({"headers", "signed_token"})


def get_derived_deploy_env_overrides(
    *,
    environ: Mapping[str, str],
    deploy_schema_keys: Iterable[str],
) -> dict[str, str]:
    """Return deploy-script-derived env values that may override `.env.deploy`.

    File-backed deploy values should win over inherited shell or CI environment
    variables. Only values generated by the deploy tooling itself are allowed to
    override `.env.deploy`.
    """

    allowed_keys = DERIVED_DEPLOY_ENV_KEYS.intersection(set(deploy_schema_keys))
    return {
        key: value
        for key, value in environ.items()
        if key in allowed_keys and str(value).strip()
    }


RUNTIME_SCHEMA: tuple[EnvKeySpec, ...] = (
    EnvKeySpec(
        key=VarsEnum.BASIC_AUTH_USER,
        mandatory=False,
        default="admin",
        targets=frozenset({EnvTarget.DOTENV_RUNTIME, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.APP_VERSION,
        mandatory=False,
        default="0.0.0",
        targets=frozenset({EnvTarget.DOTENV_RUNTIME}),
    ),
    EnvKeySpec(
        key=VarsEnum.SM_CHECK_INTERVAL_SECONDS,
        mandatory=False,
        default="300",
        targets=frozenset({EnvTarget.DOTENV_RUNTIME}),
    ),
    EnvKeySpec(
        key=VarsEnum.SM_LOG_LEVEL,
        mandatory=False,
        default="INFO",
        targets=frozenset({EnvTarget.DOTENV_RUNTIME}),
    ),
    EnvKeySpec(
        key=VarsEnum.SM_DB_PATH,
        mandatory=False,
        default="/data/storage_manager.db",
        targets=frozenset({EnvTarget.DOTENV_RUNTIME}),
    ),
    EnvKeySpec(
        key=VarsEnum.SM_API_PORT,
        mandatory=False,
        default="9100",
        targets=frozenset({EnvTarget.DOTENV_RUNTIME}),
    ),
)


SECRETS_SCHEMA: tuple[EnvKeySpec, ...] = (
    EnvKeySpec(
        key=SecretsEnum.BASIC_AUTH_HASH,
        mandatory=True,
        targets=frozenset({EnvTarget.DOTENV_SECRETS, EnvTarget.GH_ACTIONS_SECRET}),
    ),
    EnvKeySpec(
        key=SecretsEnum.APP_SECRET,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_SECRETS}),
    ),
)


DEPLOY_SCHEMA: tuple[EnvKeySpec, ...] = (
    EnvKeySpec(
        key=VarsEnum.AZURE_CLIENT_ID,
        mandatory=False,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AZURE_TENANT_ID,
        mandatory=False,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AZURE_SUBSCRIPTION_ID,
        mandatory=False,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AZURE_OIDC_APP_NAME,
        mandatory=True,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AZURE_RESOURCE_GROUP,
        mandatory=False,
        default="protected-container-rg",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AZURE_LOCATION,
        mandatory=False,
        default="westeurope",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AZURE_CONTAINER_NAME,
        mandatory=False,
        default="protected-container",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AZURE_DNS_LABEL,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AZURE_FILE_SHARE_QUOTA_GB,
        mandatory=False,
        default="5",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.PUBLIC_DOMAIN,
        mandatory=True,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.ACME_EMAIL,
        mandatory=True,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.APP_IMAGE,
        mandatory=True,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.GHCR_PRIVATE,
        mandatory=False,
        default="false",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.GHCR_USERNAME,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=SecretsEnum.GHCR_TOKEN,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY_SECRETS, EnvTarget.GH_ACTIONS_SECRET}),
    ),
    EnvKeySpec(
        key=VarsEnum.APP_CPU_CORES,
        mandatory=False,
        default="1.0",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.APP_MEMORY_GB,
        mandatory=False,
        default="2.0",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.CADDY_IMAGE,
        mandatory=False,
        default="caddy:2-alpine",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.CADDY_CPU_CORES,
        mandatory=False,
        default="0.5",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.CADDY_MEMORY_GB,
        mandatory=False,
        default="0.5",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.OTHER_IMAGE,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.OTHER_CPU_CORES,
        mandatory=False,
        default="0.25",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.OTHER_MEMORY_GB,
        mandatory=False,
        default="0.5",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.DEPLOY_HOOKS_MODULE,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.DEPLOY_HOOKS_SOFT_FAIL,
        mandatory=False,
        default="false",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.BASIC_AUTH_USER,
        mandatory=False,
        default="admin",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=SecretsEnum.BASIC_AUTH_HASH,
        mandatory=False,
        targets=frozenset({EnvTarget.GH_ACTIONS_SECRET}),
    ),
    EnvKeySpec(
        key=VarsEnum.EDGE_AUTH_MODE,
        mandatory=False,
        default="basic",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.EDGE_AUTH_GATEWAY,
        mandatory=False,
        default="authentik",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.EDGE_AUTH_GATEWAY_SERVICE,
        mandatory=False,
        default="authentik-outpost",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.EDGE_AUTH_GATEWAY_PORT,
        mandatory=False,
        default="9000",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.EDGE_AUTH_VERIFY_URI,
        mandatory=False,
        default="/outpost.goauthentik.io/auth/caddy",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.EDGE_AUTH_COPY_HEADERS,
        mandatory=False,
        default="X-authentik-username>X-Auth-User,X-authentik-email>X-Auth-Email,X-authentik-groups>X-Auth-Groups,X-Authentik-Jwt>X-Auth-Token",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.EDGE_AUTH_TOKEN_HEADER,
        mandatory=False,
        default="X-Auth-Token",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.EDGE_AUTH_DEFAULT_PROOF_LEVEL,
        mandatory=False,
        default="headers",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.EDGE_AUTH_TOKEN_ISSUER,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTH_APPROVER_EMAIL,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTH_AUDIENCE,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTH_POLICY,
        mandatory=False,
        default="protected-container-users",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTH_PROOF_LEVEL,
        mandatory=False,
        default="headers",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTH_SECRET_REF,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTHENTIK_PUBLIC_DOMAIN,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTHENTIK_OUTPOST_SERVICE,
        mandatory=False,
        default="authentik-outpost",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTHENTIK_POSTGRESQL__HOST,
        mandatory=False,
        default="authentik-postgresql",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTHENTIK_POSTGRESQL__PORT,
        mandatory=False,
        default="5432",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTHENTIK_POSTGRESQL__NAME,
        mandatory=False,
        default="authentik",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTHENTIK_POSTGRESQL__USER,
        mandatory=False,
        default="authentik",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTHENTIK_STORAGE__BACKEND,
        mandatory=False,
        default="file",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTHENTIK_BACKUP_DIR,
        mandatory=False,
        default="backups/authentik",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTHENTIK_EMAIL__HOST,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTHENTIK_EMAIL__PORT,
        mandatory=False,
        default="587",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTHENTIK_EMAIL__USERNAME,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTHENTIK_EMAIL__FROM,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTHENTIK_EMAIL__USE_TLS,
        mandatory=False,
        default="true",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTHENTIK_EMAIL__USE_SSL,
        mandatory=False,
        default="false",
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTHENTIK_BOOTSTRAP_EMAIL,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTHENTIK_GOOGLE_CLIENT_ID,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTHENTIK_MICROSOFT_CLIENT_ID,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTHENTIK_FACEBOOK_CLIENT_ID,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=VarsEnum.AUTHENTIK_SIGNING_KEY_REF,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}),
    ),
    EnvKeySpec(
        key=SecretsEnum.AUTHENTIK_SECRET_KEY,
        mandatory=False,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY_SECRETS, EnvTarget.GH_ACTIONS_SECRET}),
    ),
    EnvKeySpec(
        key=SecretsEnum.AUTHENTIK_POSTGRESQL__PASSWORD,
        mandatory=False,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY_SECRETS, EnvTarget.GH_ACTIONS_SECRET}),
    ),
    EnvKeySpec(
        key=SecretsEnum.AUTHENTIK_BOOTSTRAP_PASSWORD_HASH,
        mandatory=False,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY_SECRETS, EnvTarget.GH_ACTIONS_SECRET}),
    ),
    EnvKeySpec(
        key=SecretsEnum.AUTHENTIK_BOOTSTRAP_TOKEN,
        mandatory=False,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY_SECRETS, EnvTarget.GH_ACTIONS_SECRET}),
    ),
    EnvKeySpec(
        key=SecretsEnum.AUTHENTIK_API_TOKEN,
        mandatory=False,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY_SECRETS, EnvTarget.GH_ACTIONS_SECRET}),
    ),
    EnvKeySpec(
        key=SecretsEnum.AUTHENTIK_EMAIL__PASSWORD,
        mandatory=False,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY_SECRETS, EnvTarget.GH_ACTIONS_SECRET}),
    ),
    EnvKeySpec(
        key=SecretsEnum.AUTHENTIK_GOOGLE_CLIENT_SECRET,
        mandatory=False,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY_SECRETS, EnvTarget.GH_ACTIONS_SECRET}),
    ),
    EnvKeySpec(
        key=SecretsEnum.AUTHENTIK_MICROSOFT_CLIENT_SECRET,
        mandatory=False,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY_SECRETS, EnvTarget.GH_ACTIONS_SECRET}),
    ),
    EnvKeySpec(
        key=SecretsEnum.AUTHENTIK_FACEBOOK_CLIENT_SECRET,
        mandatory=False,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY_SECRETS, EnvTarget.GH_ACTIONS_SECRET}),
    ),
    # Staging (optional)
    EnvKeySpec(
        key=VarsEnum.STAGING_PUBLIC_DOMAIN,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY}),
    ),
    EnvKeySpec(
        key=VarsEnum.STAGING_REMOTE_DIR,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY}),
    ),
    EnvKeySpec(
        key=VarsEnum.STAGING_PORTAINER_STACK_NAME,
        mandatory=False,
        default=None,
        targets=frozenset({EnvTarget.DOTENV_DEPLOY}),
    ),
    # GitHub Actions expects this secret to exist to materialize `.env` in CI.
    EnvKeySpec(
        key=SecretsEnum.RUNTIME_ENV_DOTENV,
        mandatory=True,
        targets=frozenset({EnvTarget.GH_ACTIONS_SECRET}),
    ),
    EnvKeySpec(
        key=SecretsEnum.RUNTIME_SECRETS_DOTENV,
        mandatory=True,
        targets=frozenset({EnvTarget.GH_ACTIONS_SECRET}),
    ),
)


def _schema_keys(schema: Iterable[EnvKeySpec]) -> set[str]:
    return {spec.key.value for spec in schema}


def parse_dotenv_file(path: Path) -> dict[str, str]:
    """Parse dotenv file strictly.

    - Comments are ignored.
    - Keys are preserved even if they have empty values (""), so we can detect unknown/forbidden keys.
    """
    kv: dict[str, str] = {}
    raw = dotenv_values(path)
    for k, v in raw.items():
        if k is None:
            continue
        key = str(k).strip()
        if not key:
            continue
        val = "" if v is None else str(v).strip()
        kv[key] = val
    return kv


def _format_dotenv_value(value: str) -> str:
    # Keep it simple and deterministic; the values we write back (GUIDs) are safe unquoted.
    # If needed in the future, add quoting/escaping here.
    return str(value)


def write_dotenv_values(*, path: Path, updates: Mapping[str, str], create: bool = False) -> None:
    """Update (or create) a dotenv file in-place.

    - Preserves existing lines/comments.
    - Replaces existing KEY=... lines for keys in `updates`.
    - Appends missing keys at the end in sorted order.

    This is intentionally minimal: it avoids reformatting unrelated content.
    """
    if not updates:
        return

    if not path.exists():
        if not create:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        header = "\n".join(
            [
                "# Generated/updated by scripts/deploy/azure_deploy_container.py",
                "",
            ]
        )
        path.write_text(header)

    original_lines = path.read_text().splitlines()
    remaining = {k: _format_dotenv_value(v) for k, v in updates.items() if str(v).strip()}
    if not remaining:
        return

    out: list[str] = []
    for line in original_lines:
        s = line.strip()
        if not s or s.startswith("#") or "=" not in line:
            out.append(line)
            continue

        key = line.split("=", 1)[0].strip()
        if key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
            continue

        out.append(line)

    if remaining:
        if out and out[-1].strip() != "":
            out.append("")
        for key in sorted(remaining.keys()):
            out.append(f"{key}={remaining[key]}")

    path.write_text("\n".join(out) + "\n")


def validate_known_keys(schema: Iterable[EnvKeySpec], kv: Mapping[str, str], *, context: str) -> None:
    allowed = _schema_keys(schema)
    unknown = sorted([k for k in kv.keys() if k not in allowed])
    if unknown:
        raise EnvValidationError(
            context=context,
            problems=["Unknown key(s): " + ", ".join(unknown)],
        )


def apply_defaults(schema: Iterable[EnvKeySpec], kv: dict[str, str]) -> dict[str, str]:
    out = dict(kv)
    for spec in schema:
        if spec.key.value in out and str(out.get(spec.key.value) or "").strip():
            continue
        if spec.default is None:
            continue
        out[spec.key.value] = spec.default
    return out


def validate_required(schema: Iterable[EnvKeySpec], kv: Mapping[str, str], *, context: str) -> None:
    missing: list[str] = []
    for spec in schema:
        if not spec.mandatory:
            continue
        val = str(kv.get(spec.key.value) or "").strip()
        if not val:
            missing.append(spec.key.value)
    if missing:
        raise EnvValidationError(context=context, problems=["Missing mandatory key(s): " + ", ".join(sorted(missing))])


def truthy(val: str | None) -> bool:
    v = str(val or "").strip().lower()
    return v in {"1", "true", "yes", "y", "on"}


def resolve_auth_approver_email(*, deploy_kv: Mapping[str, str]) -> str:
    explicit_email = str(deploy_kv.get(VarsEnum.AUTH_APPROVER_EMAIL.value) or "").strip()
    if explicit_email:
        return explicit_email
    return str(deploy_kv.get(VarsEnum.ACME_EMAIL.value) or "").strip()


def _append_invalid_choice_problem(
    *,
    problems: list[str],
    key: VarsEnum,
    value: str | None,
    allowed_values: frozenset[str],
) -> None:
    raw_value = str(value or "").strip()
    if not raw_value or raw_value in allowed_values:
        return
    allowed = ", ".join(sorted(allowed_values))
    problems.append(f"{key.value} must be one of: {allowed}")


def _append_missing_problem(*, problems: list[str], deploy_kv: Mapping[str, str], key: VarsEnum | SecretsEnum) -> None:
    if not str(deploy_kv.get(key.value) or "").strip():
        problems.append(f"{key.value} is required when {VarsEnum.EDGE_AUTH_MODE.value}=oidc")


def _append_provider_pair_problem(
    *,
    problems: list[str],
    deploy_kv: Mapping[str, str],
    client_id_key: VarsEnum,
    client_secret_key: SecretsEnum,
) -> None:
    has_client_id = bool(str(deploy_kv.get(client_id_key.value) or "").strip())
    has_client_secret = bool(str(deploy_kv.get(client_secret_key.value) or "").strip())
    if has_client_id and not has_client_secret:
        problems.append(f"{client_secret_key.value} is required when {client_id_key.value} is set")
    if has_client_secret and not has_client_id:
        problems.append(f"{client_id_key.value} is required when {client_secret_key.value} is set")


def validate_cross_field_rules(*, deploy_kv: Mapping[str, str], context: str) -> None:
    """Extra validation for rules that can't be expressed with (mandatory/default) alone."""
    problems: list[str] = []

    edge_auth_mode = str(deploy_kv.get(VarsEnum.EDGE_AUTH_MODE.value) or "basic").strip()
    edge_auth_gateway = str(deploy_kv.get(VarsEnum.EDGE_AUTH_GATEWAY.value) or "authentik").strip()
    default_proof_level = str(deploy_kv.get(VarsEnum.EDGE_AUTH_DEFAULT_PROOF_LEVEL.value) or "headers").strip()
    app_proof_level = str(deploy_kv.get(VarsEnum.AUTH_PROOF_LEVEL.value) or "headers").strip()

    _append_invalid_choice_problem(
        problems=problems,
        key=VarsEnum.EDGE_AUTH_MODE,
        value=edge_auth_mode,
        allowed_values=EDGE_AUTH_MODES,
    )
    _append_invalid_choice_problem(
        problems=problems,
        key=VarsEnum.EDGE_AUTH_GATEWAY,
        value=edge_auth_gateway,
        allowed_values=EDGE_AUTH_GATEWAYS,
    )
    _append_invalid_choice_problem(
        problems=problems,
        key=VarsEnum.EDGE_AUTH_DEFAULT_PROOF_LEVEL,
        value=default_proof_level,
        allowed_values=AUTH_PROOF_LEVELS,
    )
    _append_invalid_choice_problem(
        problems=problems,
        key=VarsEnum.AUTH_PROOF_LEVEL,
        value=app_proof_level,
        allowed_values=AUTH_PROOF_LEVELS,
    )

    if truthy(deploy_kv.get(VarsEnum.GHCR_PRIVATE.value)):
        # For private GHCR images, username+token are required for ACI pull.
        if not str(deploy_kv.get(VarsEnum.GHCR_USERNAME.value) or "").strip():
            problems.append(f"{VarsEnum.GHCR_USERNAME.value} is required when {VarsEnum.GHCR_PRIVATE.value}=true")
        if not str(deploy_kv.get(SecretsEnum.GHCR_TOKEN.value) or "").strip():
            problems.append(f"{SecretsEnum.GHCR_TOKEN.value} is required when {VarsEnum.GHCR_PRIVATE.value}=true")

    if edge_auth_mode == "oidc":
        _append_missing_problem(problems=problems, deploy_kv=deploy_kv, key=VarsEnum.AUTHENTIK_PUBLIC_DOMAIN)
        _append_missing_problem(problems=problems, deploy_kv=deploy_kv, key=SecretsEnum.AUTHENTIK_SECRET_KEY)
        _append_missing_problem(problems=problems, deploy_kv=deploy_kv, key=SecretsEnum.AUTHENTIK_POSTGRESQL__PASSWORD)
        if not resolve_auth_approver_email(deploy_kv=deploy_kv):
            problems.append(
                f"{VarsEnum.AUTH_APPROVER_EMAIL.value} or {VarsEnum.ACME_EMAIL.value} is required when {VarsEnum.EDGE_AUTH_MODE.value}=oidc"
            )
        if default_proof_level == "signed_token" and not str(deploy_kv.get(VarsEnum.EDGE_AUTH_TOKEN_ISSUER.value) or "").strip():
            problems.append(
                f"{VarsEnum.EDGE_AUTH_TOKEN_ISSUER.value} is required when {VarsEnum.EDGE_AUTH_DEFAULT_PROOF_LEVEL.value}=signed_token"
            )

    _append_provider_pair_problem(
        problems=problems,
        deploy_kv=deploy_kv,
        client_id_key=VarsEnum.AUTHENTIK_GOOGLE_CLIENT_ID,
        client_secret_key=SecretsEnum.AUTHENTIK_GOOGLE_CLIENT_SECRET,
    )
    _append_provider_pair_problem(
        problems=problems,
        deploy_kv=deploy_kv,
        client_id_key=VarsEnum.AUTHENTIK_MICROSOFT_CLIENT_ID,
        client_secret_key=SecretsEnum.AUTHENTIK_MICROSOFT_CLIENT_SECRET,
    )
    _append_provider_pair_problem(
        problems=problems,
        deploy_kv=deploy_kv,
        client_id_key=VarsEnum.AUTHENTIK_FACEBOOK_CLIENT_ID,
        client_secret_key=SecretsEnum.AUTHENTIK_FACEBOOK_CLIENT_SECRET,
    )

    if problems:
        raise EnvValidationError(context=context, problems=problems)


def filter_schema_by_targets(schema: Iterable[EnvKeySpec], *, include: set[EnvTarget]) -> list[EnvKeySpec]:
    return [spec for spec in schema if spec.targets.intersection(include)]


def get_spec(schema: Iterable[EnvKeySpec], key: VarsEnum | SecretsEnum) -> EnvKeySpec:
    for spec in schema:
        if spec.key == key:
            return spec
    raise KeyError(key)
