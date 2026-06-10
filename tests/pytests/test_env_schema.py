from __future__ import annotations

from pathlib import Path

import pytest

from scripts.deploy.env_schema import (
    DEPLOY_SCHEMA,
    RUNTIME_SCHEMA,
    EnvValidationError,
    SecretsEnum,
    VarsEnum,
    apply_defaults,
    parse_dotenv_file,
    resolve_auth_approver_email,
    truthy,
    validate_cross_field_rules,
    validate_known_keys,
    validate_required,
)


def _write(p: Path, text: str) -> Path:
    p.write_text(text, encoding="utf-8")
    return p


def test_parse_dotenv_preserves_empty_values(tmp_path: Path) -> None:
    p = _write(tmp_path / ".env", "BASIC_AUTH_USER=\nBASIC_AUTH_HASH=\n")
    kv = parse_dotenv_file(p)
    assert kv[VarsEnum.BASIC_AUTH_USER.value] == ""
    assert kv[SecretsEnum.BASIC_AUTH_HASH.value] == ""


def test_runtime_defaults_and_required(tmp_path: Path) -> None:
    p = _write(tmp_path / ".env", "BASIC_AUTH_USER=admin\n")
    kv = parse_dotenv_file(p)

    validate_known_keys(RUNTIME_SCHEMA, kv, context="runtime")
    kv = apply_defaults(RUNTIME_SCHEMA, kv)

    # default user applied (existing check, confirming it works)
    assert kv[VarsEnum.BASIC_AUTH_USER.value] == "admin"

    # required check (BASIC_AUTH_USER is default=admin, so meaningless to test required? It is optional).
    # Let's test that we can Validate without error.
    validate_required(RUNTIME_SCHEMA, kv, context="runtime")


def test_unknown_keys_fail(tmp_path: Path) -> None:
    p = _write(tmp_path / ".env", "NOT_A_KEY=1\n")
    kv = parse_dotenv_file(p)
    with pytest.raises(EnvValidationError):
        validate_known_keys(RUNTIME_SCHEMA, kv, context="runtime")


def test_storage_manager_keys_are_known_runtime_keys(tmp_path: Path) -> None:
    # SM_* keys ship in env.example and are consumed by the storage-manager
    # compose service; the runtime schema must accept them and apply defaults.
    p = _write(
        tmp_path / ".env",
        "SM_CHECK_INTERVAL_SECONDS=300\nSM_LOG_LEVEL=INFO\n"
        "SM_DB_PATH=/data/storage_manager.db\nSM_API_PORT=9100\n",
    )
    kv = parse_dotenv_file(p)
    validate_known_keys(RUNTIME_SCHEMA, kv, context="runtime")

    # Defaults applied when omitted.
    kv2 = apply_defaults(RUNTIME_SCHEMA, {})
    assert kv2[VarsEnum.SM_CHECK_INTERVAL_SECONDS.value] == "300"
    assert kv2[VarsEnum.SM_LOG_LEVEL.value] == "INFO"
    assert kv2[VarsEnum.SM_DB_PATH.value] == "/data/storage_manager.db"
    assert kv2[VarsEnum.SM_API_PORT.value] == "9100"


def test_alias_keys_fail(tmp_path: Path) -> None:
    p = _write(tmp_path / ".env.deploy", "IMAGE=ghcr.io/x/y:latest\n")
    kv = parse_dotenv_file(p)
    with pytest.raises(EnvValidationError):
        validate_known_keys(DEPLOY_SCHEMA, kv, context="deploy")


def test_truthy() -> None:
    assert truthy("true")
    assert truthy("1")
    assert not truthy("false")
    assert not truthy("")


def test_cross_field_rules_require_ghcr_creds(tmp_path: Path) -> None:
    # GHCR_PRIVATE=true requires GHCR_USERNAME and GHCR_TOKEN
    kv = {
        VarsEnum.GHCR_PRIVATE.value: "true",
        VarsEnum.GHCR_USERNAME.value: "",
        SecretsEnum.GHCR_TOKEN.value: "",
    }
    with pytest.raises(EnvValidationError):
        validate_cross_field_rules(deploy_kv=kv, context="deploy")

    kv2 = {
        VarsEnum.GHCR_PRIVATE.value: "true",
        VarsEnum.GHCR_USERNAME.value: "me",
        SecretsEnum.GHCR_TOKEN.value: "tok",
    }
    validate_cross_field_rules(deploy_kv=kv2, context="deploy")


def test_oidc_edge_auth_defaults_keep_basic_auth_rollback_valid() -> None:
    kv = apply_defaults(DEPLOY_SCHEMA, {})

    assert kv[VarsEnum.EDGE_AUTH_MODE.value] == "basic"
    assert kv[VarsEnum.EDGE_AUTH_GATEWAY.value] == "authentik"
    assert kv[VarsEnum.EDGE_AUTH_GATEWAY_SERVICE.value] == "authentik-outpost"
    assert kv[VarsEnum.EDGE_AUTH_VERIFY_URI.value] == "/outpost.goauthentik.io/auth/caddy"
    validate_cross_field_rules(deploy_kv=kv, context="deploy")


def test_oidc_edge_auth_requires_authentik_secrets_and_domain() -> None:
    kv = apply_defaults(
        DEPLOY_SCHEMA,
        {
            VarsEnum.EDGE_AUTH_MODE.value: "oidc",
            VarsEnum.ACME_EMAIL.value: "ops@example.com",
        },
    )

    with pytest.raises(EnvValidationError) as excinfo:
        validate_cross_field_rules(deploy_kv=kv, context="deploy")

    message = str(excinfo.value)
    assert VarsEnum.AUTHENTIK_PUBLIC_DOMAIN.value in message
    assert SecretsEnum.AUTHENTIK_SECRET_KEY.value in message
    assert SecretsEnum.AUTHENTIK_POSTGRESQL__PASSWORD.value in message


def test_oidc_edge_auth_accepts_minimal_authentik_contract() -> None:
    kv = apply_defaults(
        DEPLOY_SCHEMA,
        {
            VarsEnum.EDGE_AUTH_MODE.value: "oidc",
            VarsEnum.ACME_EMAIL.value: "ops@example.com",
            VarsEnum.AUTHENTIK_PUBLIC_DOMAIN.value: "auth.example.com",
            SecretsEnum.AUTHENTIK_SECRET_KEY.value: "secret-key",
            SecretsEnum.AUTHENTIK_POSTGRESQL__PASSWORD.value: "postgres-password",
        },
    )

    validate_cross_field_rules(deploy_kv=kv, context="deploy")
    assert resolve_auth_approver_email(deploy_kv=kv) == "ops@example.com"


def test_oidc_edge_auth_validates_modes_and_proof_levels() -> None:
    kv = apply_defaults(
        DEPLOY_SCHEMA,
        {
            VarsEnum.EDGE_AUTH_MODE.value: "saml",
            VarsEnum.EDGE_AUTH_GATEWAY.value: "custom",
            VarsEnum.EDGE_AUTH_DEFAULT_PROOF_LEVEL.value: "jwt",
            VarsEnum.AUTH_PROOF_LEVEL.value: "cookie",
        },
    )

    with pytest.raises(EnvValidationError) as excinfo:
        validate_cross_field_rules(deploy_kv=kv, context="deploy")

    message = str(excinfo.value)
    assert VarsEnum.EDGE_AUTH_MODE.value in message
    assert VarsEnum.EDGE_AUTH_GATEWAY.value in message
    assert VarsEnum.EDGE_AUTH_DEFAULT_PROOF_LEVEL.value in message
    assert VarsEnum.AUTH_PROOF_LEVEL.value in message


def test_oidc_signed_token_default_requires_issuer() -> None:
    kv = apply_defaults(
        DEPLOY_SCHEMA,
        {
            VarsEnum.EDGE_AUTH_MODE.value: "oidc",
            VarsEnum.EDGE_AUTH_DEFAULT_PROOF_LEVEL.value: "signed_token",
            VarsEnum.ACME_EMAIL.value: "ops@example.com",
            VarsEnum.AUTHENTIK_PUBLIC_DOMAIN.value: "auth.example.com",
            SecretsEnum.AUTHENTIK_SECRET_KEY.value: "secret-key",
            SecretsEnum.AUTHENTIK_POSTGRESQL__PASSWORD.value: "postgres-password",
        },
    )

    with pytest.raises(EnvValidationError) as excinfo:
        validate_cross_field_rules(deploy_kv=kv, context="deploy")

    assert VarsEnum.EDGE_AUTH_TOKEN_ISSUER.value in str(excinfo.value)


def test_oidc_provider_client_ids_and_secrets_must_be_paired() -> None:
    kv = apply_defaults(
        DEPLOY_SCHEMA,
        {
            VarsEnum.AUTHENTIK_GOOGLE_CLIENT_ID.value: "google-client-id",
            SecretsEnum.AUTHENTIK_MICROSOFT_CLIENT_SECRET.value: "microsoft-secret",
        },
    )

    with pytest.raises(EnvValidationError) as excinfo:
        validate_cross_field_rules(deploy_kv=kv, context="deploy")

    message = str(excinfo.value)
    assert SecretsEnum.AUTHENTIK_GOOGLE_CLIENT_SECRET.value in message
    assert VarsEnum.AUTHENTIK_MICROSOFT_CLIENT_ID.value in message
