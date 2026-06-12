# Fix Proxy Compose Hook Env Compatibility

## Principles

- Downstream hooks may rerun `docker compose up -d caddy` in the shared proxy directory after the toolkit proxy refresh completes.
- The shared proxy Compose file may require interpolation variables, but those variables must be available in the proxy directory without downstream hooks re-exporting toolkit internals.
- Secret-like values must not be printed; generated remote env files should contain only the proxy runtime values needed by Compose/Caddy.
- Hermes should not need container or hook code changes for this toolkit regression.

## Checkable Task Overview

- [x] Phase 0 cleanup: identify the `--swap` failure as missing Compose interpolation env in the proxy directory, not missing `ACME_EMAIL` in Hermes config.
- [x] Phase 1 bug proof: assert proxy refresh syncs a generated proxy `.env` with quoted Basic Auth hash values.
- [x] Phase 2 implementation: generate `docker/proxy/.env` in the staged proxy directory before candidate validation and live sync.
- [x] Phase 3 validation: run focused Ubuntu deploy tests and shell syntax checks.
- [ ] Phase 4 docs/changelog: update release notes and archive this plan.

## Root-Cause Hypothesis

The protected-container proxy Compose file now uses required interpolation variables for Caddy auth values. The toolkit proxy script exports them while refreshing, but Hermes `post_deploy` later runs `docker compose up -d caddy` directly in the proxy directory without those exports. Compose does not use `env_file` entries for interpolation, so it fails before recreating Caddy.

## Expected Guidance

Hermes should update/pin the toolkit after this fix and rerun the same deploy. No Hermes container changes should be required.

## Validation Notes

- Regression proof: `source .venv/bin/activate && python -m pytest tests/pytests/test_ubuntu_deploy.py::test_proxy_deploy_script_preserves_routes_without_helper_file -x -v` failed before the fix because the staged/synced proxy directory did not include `.env`.
- Focused validation passed after the fix: `source .venv/bin/activate && python -m pytest tests/pytests/test_ubuntu_deploy.py -v` reported 57 passed.
- Shell validation passed: `bash -n scripts/deploy/ubuntu_deploy_proxy.sh`.