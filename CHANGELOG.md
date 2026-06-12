# Changelog

All notable changes to this project will be documented in this file.

## [0.2.14] - 2026-06-12

### Git

- Last git ref: [`3c2078b`](https://github.com/beejones/protected-container/commit/3c2078b70cf8d0dacee193efc3ad815cd043c7f7)

### New Capabilities

- Added shared Caddy route preservation during Ubuntu proxy refreshes so existing downstream app routes survive protected-container deploys.
- Added candidate validation before replacing the live shared Caddy proxy files or recreating `central-proxy`.
- Added proxy-local `.env` generation so downstream hooks can rerun shared proxy Compose commands without manually exporting Caddy runtime values.
- Added automatic version-log CSV migration to `timestamp,git_ref,version,status,target,local_branch,stack_name,domain,image`.

### Fixed Bugs

- Fixed shared Caddy regressions where protected-container deploys could erase, unprotect, or misroute stock-dashboard and Hermes site blocks.
- Fixed proxy refreshes from downstream or temporary upstream checkouts by using the caller Python executable and an embedded route-preservation fallback when helper files are absent.
- Fixed Caddy crash-loop and Hermes `--swap` failures caused by proxy Compose environment interpolation and Basic Auth hash parsing.
- Fixed deploy logging so new successful git refs advance `APP_VERSION` once while repeated deploys of the same git ref reuse the recorded version.

### Touched Models

- Shared Caddy route preservation contract.
- Ubuntu shared proxy refresh safety contract.
- Downstream deployment hook compatibility contract.
- Version-log CSV schema and migration contract.
- `DeployLogSettings.versioning_enabled` behavior.

## [0.2.12] - 2026-06-12

### Git

- Last git ref: [`c3bc0c3`](https://github.com/beejones/protected-container/commit/c3bc0c37dbb360363ae36b001d2bc0b89c06ce63)

### New Capabilities

- Added a generated proxy-local `.env` during shared Caddy proxy refreshes so downstream hooks can rerun proxy Compose commands without manually exporting Caddy runtime variables.

### Fixed Bugs

- Fixed Hermes `--swap` post-deploy failures where `docker compose up -d caddy` in the shared proxy directory could not interpolate required `ACME_EMAIL` and Basic Auth values after the proxy Compose safety changes.

### Touched Models

- Shared Caddy proxy refresh environment contract.
- Downstream hook proxy Compose compatibility contract.

## [0.2.11] - 2026-06-12

### Git

- Last git ref: [`2d42279`](https://github.com/beejones/protected-container/commit/2d422791500dff6d2b4b0d30b02b46aed40c7d9d)

### New Capabilities

- Added remote candidate validation for shared Caddy proxy refreshes before replacing the live proxy files or recreating `central-proxy`.

### Fixed Bugs

- Fixed a serious proxy refresh regression where downstream deploys could recreate `central-proxy` with an invalid Basic Auth hash parsed through Docker Compose `env_file`, causing Caddy to crash-loop.
- Fixed proxy refresh environment handling so shell-sourced Basic Auth values are passed explicitly into Caddy validation and the live Compose recreate.

### Touched Models

- Shared Caddy proxy refresh safety contract.
- Ubuntu deploy proxy environment contract.

## [0.2.10] - 2026-06-12

### Git

- Last git ref: [`7633bc8`](https://github.com/beejones/protected-container/commit/7633bc899bf28f5e181cf682aaba03487f61e95c)

### New Capabilities

- Documented the Ubuntu upstream container and downstream wrapper contract in the hooks guide, with routing and README docs linking to that canonical guidance.

### Fixed Bugs

- Fixed downstream Ubuntu deploys that vendor this toolkit as a submodule or temporary upstream checkout by passing the active deploy Python executable into the proxy refresh helper instead of requiring a toolkit-local `.venv`.
- Fixed proxy refreshes from temporary upstream checkouts that include the proxy shell script and template but omit `preserve_caddy_routes.py`; route preservation now has a self-contained shell fallback.

### Touched Models

- Ubuntu deploy helper execution contract.
- Upstream container hook guidance contract.

## [0.2.9] - 2026-06-12

### Git

- Last git ref: [`cf5a172`](https://github.com/beejones/protected-container/commit/cf5a1726671ac39471bcfe76c0cfbe2e6534ae27)

### New Capabilities

- Added shared Caddy route preservation during Ubuntu proxy refreshes so existing app routes survive central proxy redeploys.
- Added deploy-log version resolution for new successful merge and Ubuntu deploy git refs, while preserving same-ref version reuse.

### Fixed Bugs

- Fixed a Caddy regression where refreshing `central-proxy` from the protected-container template erased other app routes, causing TLS failures for `stock-dashboard.zenia.eu` and `hermes.zenia.eu`.
- Fixed deploy logging so a new successful git ref bumps `APP_VERSION` from the newest successful version-log row unless `.env` is already ahead.

### Touched Models

- Shared Caddy routing preservation contract.
- Version-log CSV versioning contract.
- `DeployLogSettings.versioning_enabled` behavior.

## [0.2.6] - 2026-06-10

### Git

- Last git ref: [`41615a4`](https://github.com/beejones/protected-container/commit/41615a4e476b3abe1c99fe39fc6f5668d0033fc0)

### New Capabilities

- Added Ubuntu deploy convergence for the shared Portainer control plane so Portainer is kept on the central Caddy network with the documented Caddy-only ingress shape.
- Clarified Ubuntu platform prerequisites, upstream container hook responsibilities, and Portainer API/webhook authentication through the Caddy-routed Portainer URL.

### Fixed Bugs

- Fixed Portainer outages where the container was running but unreachable from Caddy because it was missing the `caddy` network or still used stale direct host port bindings.
- Fixed Ubuntu deploys so central Caddy is refreshed during deploy and stale Authentik/OIDC edge-auth deploy keys fail before remote work when Basic Auth is the active supported path.
- Fixed deploy logging so new git refs can record the current `APP_VERSION`, while repeated deploys of the same git ref reuse the version already recorded in the version log.

### Touched Models

- Version-log CSV versioning contract.
- Ubuntu deploy platform/control-plane contract.
- Portainer API/webhook auth contract.

## [0.2.5] - 2026-06-09

### New Capabilities

- Made the post-merge version-log command the owner of the `.env` `APP_VERSION` bump after the merged git ref exists.
- Updated the protected merge and changelog skills so `/changelog` prepares the target release entry but does not edit `.env` before merge.

### Fixed Bugs

- Fixed deploy/version workflow timing so new git refs record the current `APP_VERSION`, while repeated deploys of the same git ref reuse the version already logged for that ref.
- Fixed direct deploys after merge so they can reuse the `target=merge` row written by `python scripts/deploy/deploy_log.py --record-merge` without requiring every deploy ref to be pre-seeded.

### Touched Models

- Version-log CSV versioning contract.
- `DeployLogSettings` versioning behavior.

## [0.2.4] - 2026-06-09

Pull Request: [#34](https://github.com/beejones/protected-container/pull/34)

### New Capabilities

- Clarified the protected merge and changelog workflows so `/changelog` prepares version entries before main-bound merges.
- Added post-merge version-log recording so the merged git ref is recorded before deploy.
- Renamed the default deploy tracking CSV from `out/deploy/deploy_log.csv` to `out/deploy/version_log.csv`.
- Updated deploy documentation to describe deploy logging as a verifier and recorder of prepared release versions.

### Fixed Bugs

- Fixed deploy logging so new git refs use prepared version information instead of incrementing at deploy time.
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
