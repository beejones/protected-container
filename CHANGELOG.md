# Changelog

All notable changes to this project will be documented in this file.

## [0.2.4] - 2026-06-09

Pull Request: [#34](https://github.com/beejones/protected-container/pull/34)

### New Capabilities

- Clarified the protected merge and changelog workflows so `/changelog` bumps `APP_VERSION` before main-bound merges.
- Added post-merge version-log recording so the merged git ref is recorded before deploy.
- Renamed the default deploy tracking CSV from `out/deploy/deploy_log.csv` to `out/deploy/version_log.csv`.
- Updated deploy documentation to describe deploy logging as a verifier and recorder of prepared release versions.

### Fixed Bugs

- Fixed deploy logging so new git refs record the already-prepared `APP_VERSION` instead of incrementing at deploy time.
- Fixed repeated deploys of an already logged git ref so they reuse that git ref's recorded version even if local `.env` has advanced for a later release.
- Fixed direct post-merge deploys so the merge record can seed the version for the same git ref before deployment starts.

### Touched Models

- Version-log CSV versioning contract.

## [0.2.3] - 2026-06-09

Pull Request: [#33](https://github.com/beejones/protected-container/pull/33)

### New Capabilities

- Added a protected deploy changelog gate so new git refs require a matching `APP_VERSION` and `CHANGELOG.md` release entry prepared by `/changelog`.
- Added an Ubuntu deploy preflight that validates the changelog gate before SSH or Portainer deployment work starts.

### Fixed Bugs

- Fixed deploy tracking so repeated staging, production, or swap deploys of the same git ref reuse the existing version instead of incrementing again.
- Fixed the versioning gap visible in the protected deploy log, where a later staging deploy of a new git ref reused `0.2.2` after `0.2.2` had already been staged and swapped to production.
- Updated protected deploy docs and examples to describe the git-ref versioning and changelog-gate contract consistently.

### Touched Models

- `DeployLogSettings` deploy hook settings dataclass.
- Version-log CSV versioning contract.

## [0.2.2] - 2026-05-18

### New Capabilities

- Deployed protected-container `0.2.2` to staging and promoted it to production through the swap workflow, based on the deploy log records for git ref `1612f3c0a921`.
- Recorded a later staging deploy for git ref `d7b05461aa39`, which now serves as historical evidence for the new git-ref-based versioning rule.

### Fixed Bugs

- None recorded in the deploy log.

### Touched Models

- None recorded in the deploy log.

## [Unreleased]

### Breaking Changes

- **Environment Variable Separation**: Configuration is now split into 4 files to improve security and clarity.
    - `.env`: Runtime non-secret configuration (e.g. `BASIC_AUTH_USER`).
    - `.env.secrets`: Runtime secrets (e.g. `BASIC_AUTH_HASH`, `APP_SECRET`). **Uploaded to Key Vault as `env-secrets`.**
    - `.env.deploy`: Deploy-time non-secret configuration (e.g. `AZURE_LOCATION`).
    - `.env.deploy.secrets`: Deploy-time secrets (e.g. `GHCR_TOKEN`). **Used locally, not uploaded.**

- **Migration Steps**:
    1. Move `BASIC_AUTH_HASH` from `.env` to `.env.secrets`.
    2. Move `GHCR_TOKEN` from `.env.deploy` to `.env.deploy.secrets`.
    3. Ensure your deploy scripts/pipelines populate `.env.secrets` and `.env.deploy.secrets` appropriately.

### Added

- Support for `.env.secrets` and `.env.deploy.secrets`.
- `azure_deploy_container.py` arguments: `--upload-secrets-file`, `--upload-secrets-secret-name`.
- `azure_start.sh` now fetches both `env` and `env-secrets` from Key Vault.
- `gh_sync_actions_env.py` supports syncing `.env.secrets` to GitHub Secrets.
