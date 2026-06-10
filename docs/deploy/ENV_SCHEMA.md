# Env schema: how to add a variable/secret

This repo intentionally uses a **strict, schema-driven** approach for all configuration keys used by:

- runtime `.env` (uploaded to Key Vault as a single secret)
- deploy-time `.env.deploy`
- GitHub Actions vars / secrets

The schema is the single source of truth:

- [scripts/deploy/env_schema.py](../../scripts/deploy/env_schema.py)

If a key is not in the schema, it is treated as **unknown** and validation fails.

## Concepts

### Vars vs Secrets

- **Vars** are non-sensitive values (e.g. `PUBLIC_DOMAIN`, `APP_IMAGE`, `CADDY_IMAGE`). They may be synced to GitHub Actions **variables**.
- **Secrets** are sensitive values (e.g. `GHCR_TOKEN`). They may be synced to GitHub Actions **secrets**.

In code:

- `VarsEnum` contains allowed variable keys.
- `SecretsEnum` contains allowed secret keys.

### Targets

Each key explicitly declares where it is expected to live via `EnvTarget`:

- `DOTENV_RUNTIME` → repo root `.env`
- `DOTENV_DEPLOY` → repo root `.env.deploy`
- `DOTENV_DEPLOY_SECRETS` → repo root `.env.deploy.secrets`
- `GH_ACTIONS_VAR` → GitHub Actions variable
- `GH_ACTIONS_SECRET` → GitHub Actions secret
- `KEYVAULT_SECRET` → Azure Key Vault secret name (rare; usually we upload full `.env` as one secret)

### Schema entries

Each key has an `EnvKeySpec`:

- `mandatory`: whether it must be present (after defaults are applied)
- `default`: optional default value
- `targets`: where the value is expected/allowed

There are two schemas:

- `RUNTIME_SCHEMA`: keys permitted in `.env` (e.g. `BASIC_AUTH_USER`, `APP_VERSION`, and the
  storage-manager sidecar knobs `SM_CHECK_INTERVAL_SECONDS`, `SM_LOG_LEVEL`, `SM_DB_PATH`,
  `SM_API_PORT`, which the `docker/storage-manager` compose service consumes via `${SM_*:-default}`)
- `DEPLOY_SCHEMA`: keys permitted in `.env.deploy` and `.env.deploy.secrets`

## Central Edge Auth And Authentik

`EDGE_AUTH_MODE` controls the central Caddy auth behavior:

| Value | Meaning |
| --- | --- |
| `basic` | Current rollback/default mode. Generated routes may continue using Caddy Basic Auth. |
| `oidc` | Authentik-backed edge auth. Cross-field validation requires Authentik public domain and core secrets. |
| `public` | Explicit public route mode for routes that should not import the protected auth guard. |

The selected gateway for the first OIDC rollout is Authentik. The deploy schema includes non-secret Authentik and route-contract values in `.env.deploy`, including:

- `EDGE_AUTH_GATEWAY`, `EDGE_AUTH_GATEWAY_SERVICE`, `EDGE_AUTH_GATEWAY_PORT`, `EDGE_AUTH_VERIFY_URI`
- `EDGE_AUTH_COPY_HEADERS`, `EDGE_AUTH_TOKEN_HEADER`, `EDGE_AUTH_DEFAULT_PROOF_LEVEL`, `EDGE_AUTH_TOKEN_ISSUER`
- `AUTH_APPROVER_EMAIL`, `AUTH_AUDIENCE`, `AUTH_POLICY`, `AUTH_PROOF_LEVEL`, `AUTH_SECRET_REF`
- `AUTHENTIK_PUBLIC_DOMAIN`, `AUTHENTIK_OUTPOST_SERVICE`, `AUTHENTIK_POSTGRESQL__HOST`, `AUTHENTIK_POSTGRESQL__PORT`, `AUTHENTIK_POSTGRESQL__NAME`, `AUTHENTIK_POSTGRESQL__USER`
- `AUTHENTIK_STORAGE__BACKEND`, `AUTHENTIK_BACKUP_DIR`, `AUTHENTIK_BOOTSTRAP_EMAIL`
- `AUTHENTIK_EMAIL__HOST`, `AUTHENTIK_EMAIL__PORT`, `AUTHENTIK_EMAIL__USERNAME`, `AUTHENTIK_EMAIL__FROM`, `AUTHENTIK_EMAIL__USE_TLS`, `AUTHENTIK_EMAIL__USE_SSL`
- `AUTHENTIK_GOOGLE_CLIENT_ID`, `AUTHENTIK_MICROSOFT_CLIENT_ID`, `AUTHENTIK_FACEBOOK_CLIENT_ID`, `AUTHENTIK_SIGNING_KEY_REF`

The deploy schema classifies these Authentik values as deploy-time secrets in `.env.deploy.secrets`:

- `AUTHENTIK_SECRET_KEY`
- `AUTHENTIK_POSTGRESQL__PASSWORD`
- `AUTHENTIK_BOOTSTRAP_PASSWORD_HASH`
- `AUTHENTIK_BOOTSTRAP_TOKEN`
- `AUTHENTIK_API_TOKEN`
- `AUTHENTIK_EMAIL__PASSWORD`
- `AUTHENTIK_GOOGLE_CLIENT_SECRET`
- `AUTHENTIK_MICROSOFT_CLIENT_SECRET`
- `AUTHENTIK_FACEBOOK_CLIENT_SECRET`

When `EDGE_AUTH_MODE=oidc`, validation requires `AUTHENTIK_PUBLIC_DOMAIN`, `AUTHENTIK_SECRET_KEY`, and `AUTHENTIK_POSTGRESQL__PASSWORD`. `AUTH_APPROVER_EMAIL` defaults operationally to `ACME_EMAIL` when it is not set. Provider client IDs and client secrets must be configured as pairs so examples and CI do not drift into half-configured social login.

Use `AUTHENTIK_BOOTSTRAP_PASSWORD_HASH` instead of a plaintext bootstrap password. Authentik's automated-install docs state that plaintext bootstrap passwords are supported but discouraged, while `AUTHENTIK_BOOTSTRAP_PASSWORD_HASH` stores only the local password verifier. Wrap generated hashes in single quotes in dotenv files so `$` characters are not interpolated.

## Add a new deploy-time variable (example)

Example: add a non-secret deploy config value `MY_FEATURE_FLAG` that should be stored in `.env.deploy` and also synced to GitHub Actions variables.

1) Add the enum entry

Edit [scripts/deploy/env_schema.py](../../scripts/deploy/env_schema.py) and add:

- `VarsEnum.MY_FEATURE_FLAG = "MY_FEATURE_FLAG"`

2) Add it to `DEPLOY_SCHEMA`

Add a new `EnvKeySpec` entry:

- `key=VarsEnum.MY_FEATURE_FLAG`
- `mandatory=False` (or `True` if required)
- `default="false"` (optional)
- `targets={EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_VAR}`

3) Add it to the example env file

Update:

- [env.deploy.example](../../env.deploy.example)

4) Use it in code via the enum

Never use raw string keys. Prefer:

- `os.getenv(VarsEnum.MY_FEATURE_FLAG.value)`

5) Run validation / tests

- `python3 scripts/deploy/validate_env.py`
- `pytest`

## Add a new secret (example)

Example: add `MY_API_TOKEN` as a deploy-time secret synced to GitHub Actions secrets.

1) Add enum entry:

- `SecretsEnum.MY_API_TOKEN = "MY_API_TOKEN"`

2) Add to `DEPLOY_SCHEMA` with:

- `targets={EnvTarget.DOTENV_DEPLOY, EnvTarget.GH_ACTIONS_SECRET}`

3) Update [env.deploy.secrets.example](../../env.deploy.secrets.example) (leave empty value)

4) Use it in code via the enum:

- `os.getenv(SecretsEnum.MY_API_TOKEN.value)`

5) Re-run `validate_env.py` and `pytest`

## Runtime `.env` vs deploy `.env.deploy`

Rule of thumb:

- Put **app runtime config** in `.env` (things the container needs while running). This file is uploaded to Key Vault.
- Put **deployment config** in `.env.deploy` (Azure resource settings, image ref, GHCR credentials, etc.). This file is not uploaded to Key Vault.

## GitHub Actions syncing

- [scripts/deploy/gh_sync_actions_env.py](../../scripts/deploy/gh_sync_actions_env.py) syncs schema keys to Actions vars/secrets.
- CI deployment uses Actions vars/secrets to generate `.env.deploy` on the runner.

If you add a key with `GH_ACTIONS_VAR` or `GH_ACTIONS_SECRET` targets, it will be included by the sync script automatically.

## Gotchas

- Unknown keys in `.env` or `.env.deploy` will fail validation.
- If a key is `mandatory=True`, it must be present (unless the deploy script derives it and injects it into the environment before validation).
- Don’t print secret values in logs. Vars can be logged.
