# Issue #3 – Structure the used env variables/secrets (Plan)

## Problem
Today env vars/secrets are:
- Spread across multiple scripts.
- Referenced by raw strings (and sometimes multiple aliases for the same concept).
- Partly inferred (e.g. “secret-ness” based on regex like `TOKEN|PASSWORD|KEY|HASH`). We need to remove all code related to this.

This makes deployments less deterministic, makes CI wiring fragile, and makes it hard to test “did we define everything we need?” early.

## Goals
- Single source of truth for **which keys exist**, whether they’re **vars vs secrets**, and whether they’re **mandatory** or have a **default**.
- Scripts under `scripts/` only reference env keys via `VarsEnum`/`SecretsEnum`.
- Early, explicit validation for `.env` (runtime) and `.env.deploy` (deploy-time): fail fast with a clear error listing missing keys.
- CI and local tooling use the same schema (no heuristic classification).
- Explicit definition per key of where it must be stored:
   - GitHub Actions variable vs secret
   - runtime `.env` vs deploy-time `.env.deploy`
   - Key Vault secret (and which secret name)
- Nicer, more deterministic CLI output (clear sections, consistent prefixing, optional `--verbose` / `--quiet`).
- Add pytests that validate schema behavior and prevent regressions (including “no raw env key strings in scripts”).
- No backward-compatibility: remove aliases and require canonical keys only.
## Non-goals
- Introducing a heavyweight config system (keep it simple; python-stdlib + `python-dotenv` already in deps).

---

## Current State (inventory)
Based on the current repo:

### Runtime env (`.env` uploaded as Key Vault secret `env`)
- `BASIC_AUTH_USER`
- `BASIC_AUTH_HASH`

Also in CI ([.github/workflows/deploy.yml](../.github/workflows/deploy.yml)) the workflow expects:
- secret `RUNTIME_ENV_DOTENV` (full runtime `.env` file content)
- secret `BASIC_AUTH_HASH`
- var `BASIC_AUTH_USER`

### Deploy-time env (`.env.deploy` / env vars in CI)
Used across scripts and workflows:
- Azure OIDC login: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`
- Deploy config: `AZURE_RESOURCE_GROUP`, `AZURE_LOCATION`, `AZURE_CONTAINER_NAME`, `AZURE_DNS_LABEL`
- Domain/TLS: `PUBLIC_DOMAIN` (and aliases), `ACME_EMAIL` (and aliases)
- Image/registry: `CONTAINER_IMAGE`, `GHCR_PRIVATE`, `GHCR_USERNAME`, `GHCR_TOKEN`

### Known alias keys in code today
Examples:
- `RESOURCE_GROUP` -> `AZURE_RESOURCE_GROUP`
- `LOCATION` -> `AZURE_LOCATION`
- `ACI_CONTAINER_NAME` -> `AZURE_CONTAINER_NAME`
- `IMAGE` / `GHCR_IMAGE` -> `CONTAINER_IMAGE`
- `AZURE_PUBLIC_DOMAIN` -> `PUBLIC_DOMAIN`
- `AZURE_ACME_EMAIL` -> `ACME_EMAIL`

Per the updated goals, these aliases should be removed (hard fail if encountered) once the refactor lands.

---

## Target Design

### 1) New schema module
Add a new module, e.g. `scripts/env_schema.py`, containing:

1. `class VarsEnum(str, Enum)`
   - Only non-sensitive, safe-to-log values (e.g. region, resource group, domain).

2. `class SecretsEnum(str, Enum)`
   - Sensitive values (tokens, passwords, hashes, etc).

3. A dataclass for requirements:

```python
@dataclass(frozen=True)
class EnvKeySpec:
    key: VarsEnum | SecretsEnum
    mandatory: bool
    default: str | None = None  # only used if not mandatory
   # Where this key is expected to live and/or be synchronized to.
   # Examples: runtime dotenv file, deploy dotenv file, GitHub Actions var/secret.
   targets: frozenset[EnvTarget] = frozenset()
   # Optional: for keys that map to a Key Vault secret name (e.g. runtime dotenv is stored as secret 'env').
   keyvault_secret_name: KeyVaultSecretName | None = None


class EnvTarget(Enum):
   DOTENV_RUNTIME = "dotenv_runtime"        # `.env`
   DOTENV_DEPLOY = "dotenv_deploy"          # `.env.deploy`
   GH_ACTIONS_VAR = "gh_actions_var"        # GitHub Actions variable
   GH_ACTIONS_SECRET = "gh_actions_secret"  # GitHub Actions secret
   KEYVAULT_SECRET = "keyvault_secret"      # Azure Key Vault secret


class KeyVaultSecretName(Enum):
   ENV = "env"  # stores full runtime `.env` content
```

4. Two explicit “schemas” (lists of `EnvKeySpec`):
   - `RUNTIME_SCHEMA`
   - `DEPLOY_SCHEMA`

Optionally a third “CI schema” can exist if we want to validate Actions inputs separately; but ideally CI consumes the same runtime/deploy schema.

### 2) Deterministic classification
- No regex heuristics (`TOKEN|PASSWORD|...`) for deciding secrets.
- `gh_sync_actions_env.py` uses the enums + `EnvKeySpec.targets` to decide which keys become Actions *vars* vs *secrets*.
- `gh_sync_actions_env.py` must not “guess” classification for unknown keys; unknown keys should error.

### 3) Validation API
In `scripts/env_schema.py` (or `scripts/env_loader.py` if you prefer separation), provide:

- `parse_dotenv_file(path: Path) -> dict[str, str]` (using `dotenv_values`) and treating empty values as missing.
- `validate_required(schema: list[EnvKeySpec], kv: Mapping[str, str], *, context: str) -> None` raising a structured error with missing keys.
- `validate_known_keys(schema: list[EnvKeySpec], kv: Mapping[str, str], *, context: str) -> None` failing on unknown keys.
- `validate_no_aliases(kv: Mapping[str, str]) -> None` failing fast if any legacy alias key is present.

Design constraints:
- Support reading from **files** (`.env`, `.env.deploy`) and/or **process env** (CI sets env vars directly).
- Merge precedence should be explicit and tested.

Recommended precedence:
- CLI arguments (highest)
- Environment variables (CI)
- `.env.deploy` values
- `.env` values
- Defaults from schema (only for non-mandatory keys)

### 4) Update scripts to use enums only
Refactor scripts in `scripts/` so they never do `os.getenv("RAW_KEY")`.
Instead, implement helpers:

- `get_var(VarsEnum.KEY, ...) -> str`
- `get_secret(SecretsEnum.KEY, ...) -> str`

Both should:
- enforce mandatory/default rules
- return a normalized final value
- be able to validate the key’s expected target(s) (e.g. a runtime key should not be required in `.env.deploy`).

Primary targets:
- `scripts/deploy/azure_deploy_container.py`
- `scripts/deploy/azure_deploy_container_helpers.py` (derive `DEPLOY_ENV_MATERIALIZE_KEYS` from schema)
- `scripts/deploy/gh_sync_actions_env.py` (remove `SECRET_KEY_RE` + `FORCE_VARIABLE_KEYS` heuristics)
- `scripts/deploy/azure_upload_env.py` (validate `.env` schema before upload)

### 4b) Output/logging improvements
Introduce a small formatting helper used by the deploy scripts (keep it lightweight):
- Consistent prefixes like `[deploy]`, `[env]`, `[kv]`, `[gh]`, `[az]`.
- Grouped output for: validated keys, missing keys, resolved defaults, and planned side effects.
- `--verbose` shows detailed resolution steps; default output stays succinct.

### 5) CI workflow alignment
Update [.github/workflows/deploy.yml](../.github/workflows/deploy.yml) to:
- Use canonical keys only (stop setting old aliases like `IMAGE`).
- Optionally add a “Validate env” step before running `azure_deploy_container.py`:
  - Create `.env` from `RUNTIME_ENV_DOTENV` secret (already done)
   - Validate `.env` and deploy-time env keys using a dedicated `scripts/deploy/validate_env.py` script.

Additionally, make the workflow’s mapping explicit and deterministic:
- A single list of required GitHub Actions *variables* and *secrets* should be derived from schema targets.
- Avoid setting redundant keys in workflow `env:` if they are already provided as Actions vars/secrets.

## Testing Plan (Pytests)
Add tests under `tests/pytests/`:

1. **Schema validation**
   - Missing mandatory key(s) fails with a clear list.
   - Optional keys with defaults are populated.
   - Empty string treated as missing.

2. **Reject aliases / unknown keys**
   - If `.env.deploy` contains any known legacy alias (e.g. `RESOURCE_GROUP`), validation fails.
   - Unknown keys fail by default (optionally allow a `--allow-unknown` mode for local experimentation, but CI should run strict).

3. **Actions sync classification (explicit targets)**
   - Given a sample `.env.deploy` and `.env`, `gh_sync_actions_env.py` chooses vars vs secrets exactly as declared.
   - Ensure keys without `GH_ACTIONS_*` targets are not synced.

4. **No raw env key usage in scripts** (regression guard)
   - A test that parses `scripts/*.py` via `ast` and fails if it finds `os.getenv("SOME_KEY")` with a literal string.
   - Allowlist may be needed for non-config keys like `GITHUB_REF_NAME` (or treat those as part of the schema too).

5. **Deploy script unit tests**
   - Extend `test_deploy_script.py` to validate that deploy YAML generation still includes expected env vars and secure env vars.
   - Add a focused test for “early validation fails before doing Azure calls” by mocking Azure CLI functions.

---

## Deliverables / Milestones

### Milestone A – Introduce schema + validation
- Add `scripts/env_schema.py` with enums, dataclass, schemas, validation, and explicit targets.
- Add a tiny CLI entry point (optional) for validation.
- Add core pytests for schema.

### Milestone B – Refactor deployment scripts
- Refactor `azure_deploy_container.py` and helpers to use schema accessors.
- Ensure early validation runs before any `az` calls.

### Milestone C – Refactor CI sync tooling
- Refactor `gh_sync_actions_env.py` to use schema classification.
- Update docs explaining which keys must be configured in GitHub Actions vars/secrets.

### Milestone D – CI workflow hardening
- Update `deploy.yml` to run validation step.
- Keep workflows using canonical keys only.

---

## Open Questions (decisions needed)
1. Should `GITHUB_REF_NAME`, `AZURE_OIDC_SUBJECT`, `AZURE_APP_DISPLAY_NAME` be part of the schema or be exempt as “operational” env vars? -> only when strictly necessary for deployment
2. Should `.env.deploy` error on unknown keys? Recommendation: yes (strict by default) to keep CI deterministic. -> yes
3. Should `BASIC_AUTH_USER` be treated as var (non-secret) everywhere, or keep it as secret to avoid user enumeration? Current repo treats it as a var; keep that unless threat model says otherwise.-> var
