# Fix Caddy Proxy Preserve Shared Routes

## Principles

- The central Ubuntu Caddy proxy is shared infrastructure for multiple app stacks.
- Refreshing the proxy from this toolkit must not erase routes owned by other deployed apps.
- Repo-owned proxy defaults may be synced, but existing non-template site blocks must be preserved unless a current deploy explicitly replaces the same domain.
- Caddy registration remains deterministic and idempotent.
- Validation must include live evidence for `stock-dashboard.zenia.eu`, `hermes.zenia.eu`, and `portainer.zenia.eu` after `ubuntu_deploy.py --prod`.

## Checkable Task Overview

- [x] Phase 0 cleanup: inspect the `4f2972e` proxy refresh and Caddy registration changes.
- [x] Phase 0 cleanup: confirm the regression is route loss in the remote central Caddyfile, not upstream container failure.
- [x] Phase 1 bug proof: add a failing regression test showing proxy refresh route merging must preserve existing non-template app routes.
- [x] Phase 2 implementation: preserve existing shared Caddy site blocks across `ubuntu_deploy_proxy.sh` sync/recreate.
- [x] Phase 2 implementation: avoid hardcoding downstream app domains in toolkit source.
- [x] Phase 3 validation: run focused Caddy/proxy tests.
- [x] Phase 3 validation: run typing/shell syntax checks for changed files.
- [x] Phase 4 deploy: run `source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py --prod`.
- [x] Phase 4 live verification: confirm `stock-dashboard.zenia.eu`, `hermes.zenia.eu`, and `portainer.zenia.eu` no longer fail TLS.

## Affected Surfaces

- Ubuntu deploy: `scripts/deploy/ubuntu_deploy.py` invokes the proxy refresh script.
- Shared Caddy proxy: `scripts/deploy/ubuntu_deploy_proxy.sh` owns syncing and recreating `central-proxy`.
- Caddy registration helpers: `scripts/deploy/caddy_register.py` owns route parsing and repair helpers.
- Tests: `tests/pytests/test_caddy_register.py` and `tests/pytests/test_ubuntu_deploy.py` cover route parsing and proxy script behavior.
- Docs: `docs/deploy/SHARED_CADDY_ROUTING.md` describes central proxy route preservation behavior.

## Root-Cause Hypothesis

Commit `4f2972e7e8cc0872c9e2171d2c532399821fbb01` made the proxy refresh recreate `central-proxy` from this repo's `docker/proxy/Caddyfile`. That template contains protected-container and Portainer routes but not routes registered by other app repos. The refresh overwrote the remote central Caddyfile, removing `stock-dashboard.zenia.eu` and `hermes.zenia.eu`, so Caddy no longer has TLS site blocks for those domains.

## Phase Exit Criteria

### Phase 0 Cleanup

- Remote evidence confirms the affected domains are absent from the central Caddyfile.
- The fix scope is limited to preserving shared routes during proxy refresh.

### Phase 1 Bug Proof

- A regression test fails before the production fix.

### Phase 2 Implementation

- Proxy sync preserves existing non-template Caddy site blocks.
- Existing template blocks still come from the repo-owned proxy template.
- No downstream domains are hardcoded in source.

### Phase 3 Validation

- Focused pytest selectors pass.
- Shell syntax checks pass for changed shell scripts.
- Python typing guard does not report new loose typing violations.

### Phase 4 Deploy And Live Verification

- Production Ubuntu deploy completes successfully.
- Live checks show TLS succeeds for `stock-dashboard.zenia.eu`, `hermes.zenia.eu`, and `portainer.zenia.eu`.

## Notes

- Reproduced before the fix with `curl -vkI --max-time 20 https://stock-dashboard.zenia.eu https://hermes.zenia.eu https://portainer.zenia.eu`: stock-dashboard and Hermes failed TLS with `tlsv1 alert internal error`; Portainer returned HTTP 200.
- Remote Caddyfile evidence before the fix showed only `{$PUBLIC_DOMAIN}` / `protected-container` and `portainer.zenia.eu` routes; no `stock-dashboard` or `hermes` site blocks were present.
- First attempted fix preserved routes in `ubuntu_deploy_proxy.sh`, but validation deploy showed the earlier app asset sync had already overwritten `docker/proxy/Caddyfile`. The final fix also excludes `docker/proxy/Caddyfile` from the general app asset sync.
- Regression proof: `source .venv/bin/activate && python -m pytest tests/pytests/test_ubuntu_deploy.py::test_proxy_deploy_script_preserves_existing_shared_routes_before_sync -x -v` failed before the preservation fix.
- Focused validation passed: `source .venv/bin/activate && python -m pytest tests/pytests/test_caddy_register.py tests/pytests/test_ubuntu_deploy.py -v` reported 67 passed.
- Shell/CLI validation passed: `bash -n scripts/deploy/ubuntu_deploy_proxy.sh` and `source .venv/bin/activate && python scripts/deploy/preserve_caddy_routes.py --help`.
- Final deploy passed: `source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py --prod` completed successfully at `APP_VERSION=0.2.9` for git ref `cf5a1726671ac39471bcfe76c0cfbe2e6534ae27`.
- Final live verification passed: `stock-dashboard.zenia.eu` and `hermes.zenia.eu` returned `HTTP/2 401` from Caddy Basic Auth, and `portainer.zenia.eu` returned `HTTP/2 200`.