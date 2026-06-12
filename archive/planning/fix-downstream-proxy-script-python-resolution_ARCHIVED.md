# Fix Downstream Proxy Script Python Resolution

## Principles

- Downstream repos such as `hermes-agent` use this toolkit as an upstream/submodule and may execute deploy scripts from wrapper or temporary paths.
- Toolkit scripts must not assume the toolkit checkout owns `.venv`.
- `ubuntu_deploy.py` should pass its current Python executable to helper shell scripts when a helper needs Python.
- Downstream apps should need normal submodule updates, not repo-specific forks or custom patches.

## Checkable Task Overview

- [x] Phase 0 cleanup: inspect the failing `ubuntu_deploy_proxy.sh` path and downstream execution assumption.
- [x] Phase 1 bug proof: add regression coverage that the proxy script does not source toolkit `.venv` and uses an injected Python executable.
- [x] Phase 2 implementation: pass `sys.executable` from `ubuntu_deploy.py` to `ubuntu_deploy_proxy.sh` as `PYTHON_BIN`.
- [x] Phase 2 implementation: update `ubuntu_deploy_proxy.sh` to run the route-preservation helper with `${PYTHON_BIN:-python3}`.
- [x] Phase 3 docs/guidance: document downstream guidance for submodule consumers.
- [x] Phase 3 docs/guidance: keep upstream-container guidance in `docs/deploy/HOOKS.md` and link to it from routing docs.
- [x] Phase 4 validation: run focused Ubuntu deploy/proxy tests and shell syntax checks.

## Root-Cause Hypothesis

The shared proxy preservation change introduced `source .venv/bin/activate` inside `ubuntu_deploy_proxy.sh`. That works only when the toolkit repository itself has `.venv`. Downstream repos run the toolkit from their own venv/submodule/temp path, so the script fails before route preservation can run.

## Expected Guidance

Downstream repos should update/pin the toolkit to the fixed commit and continue running deploys from their own repo root and venv. They should not need to create a `.venv` inside the toolkit submodule or copy toolkit internals.

## Validation Notes

- Regression proof: `source .venv/bin/activate && python -m pytest tests/pytests/test_ubuntu_deploy.py::test_proxy_deploy_script_uses_injected_python_without_toolkit_venv -x -v` failed before the fix because `ubuntu_deploy_proxy.sh` sourced `.venv/bin/activate`.
- Focused validation passed: `source .venv/bin/activate && python -m pytest tests/pytests/test_ubuntu_deploy.py -v` reported 54 passed.
- Shell/CLI validation passed: `bash -n scripts/deploy/ubuntu_deploy_proxy.sh` and `source .venv/bin/activate && python scripts/deploy/preserve_caddy_routes.py --help`.