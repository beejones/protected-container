# Fix Proxy Preserve Helper Temp Checkout

## Principles

- Downstream repos should not need code or container changes for toolkit proxy refresh internals.
- `ubuntu_deploy_proxy.sh` must work when executed from a temporary upstream checkout that contains the shell script and proxy template but not every Python helper file.
- Shared Caddy route preservation must remain active; missing helper files must not cause route loss or skipped preservation.
- `docs/deploy/HOOKS.md` owns upstream-container and downstream wrapper guidance.

## Checkable Task Overview

- [x] Phase 0 cleanup: identify the failure as missing `preserve_caddy_routes.py`, not a virtualenv problem.
- [x] Phase 1 bug proof: add a regression test for running `ubuntu_deploy_proxy.sh` from a temp checkout without `preserve_caddy_routes.py`.
- [x] Phase 2 implementation: add a self-contained preservation fallback in `ubuntu_deploy_proxy.sh`.
- [x] Phase 3 docs/guidance: clarify in `HOOKS.md` that downstream containers do not need to package proxy helper internals.
- [x] Phase 4 validation: run focused Ubuntu deploy tests and proxy shell syntax checks.

## Root-Cause Hypothesis

The proxy refresh script invokes `scripts/deploy/preserve_caddy_routes.py` by path. Downstream wrappers can execute a temporary upstream checkout that includes `ubuntu_deploy_proxy.sh` and `docker/proxy/Caddyfile`, but omits the new helper file. The active Python executable is correct, but it has no helper path to open.

## Expected Guidance

No upstream container or downstream app code should change. Downstream repos should update/pin the toolkit after this fix and continue using their repo-local wrapper. The toolkit must preserve shared routes from within the proxy shell script even when the standalone helper file is absent.

## Validation Notes

- Regression proof: `source .venv/bin/activate && python -m pytest tests/pytests/test_ubuntu_deploy.py::test_proxy_deploy_script_preserves_routes_without_helper_file -x -v` failed before the fix with `can't open file .../scripts/deploy/preserve_caddy_routes.py`.
- Focused regression passed after adding the self-contained shell fallback.
- Focused validation passed: `source .venv/bin/activate && python -m pytest tests/pytests/test_ubuntu_deploy.py -v` reported 55 passed.
- Shell validation passed: `bash -n scripts/deploy/ubuntu_deploy_proxy.sh`.
- Typing pattern scan passed on the changed test/script files.