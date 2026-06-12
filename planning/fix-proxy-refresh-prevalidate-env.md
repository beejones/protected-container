# Fix Proxy Refresh Prevalidate Env

## Principles

- A shared proxy refresh must not stop a healthy `central-proxy` until the candidate Caddyfile and runtime env validate.
- Docker Compose `env_file` parsing must not be the only source for Caddy Basic Auth values because bcrypt hashes can contain characters that need shell-style quoting in dotenv files.
- The proxy deployment script should source env files once, validate required proxy auth values, and pass them into Compose explicitly.
- Downstream/upstream containers should not need code changes for shared proxy internals.

## Checkable Task Overview

- [x] Phase 0 cleanup: confirm the failure is a Caddy crash-loop caused by invalid `BASIC_AUTH_HASH` inside the recreated proxy container.
- [x] Phase 0 recovery: restore remote `central-proxy` and verify stock-dashboard, Hermes, and Portainer routes.
- [x] Phase 1 bug proof: add tests that proxy Compose receives Basic Auth through explicit environment values and validates before `up`.
- [x] Phase 2 implementation: update proxy Compose/script so sourced Basic Auth values override `env_file` parsing.
- [x] Phase 2 implementation: prevalidate the staged proxy with `docker run --rm ... caddy validate` before `up -d --force-recreate`.
- [ ] Phase 3 validation: run focused tests, shell syntax, deploy, and live route checks.
- [ ] Phase 4 docs/changelog: update `CHANGELOG.md` for the completed regression fix.

## Root-Cause Hypothesis

The downstream refresh recreated `central-proxy` using `env_file` values from Compose. The effective container `BASIC_AUTH_HASH` began with a literal quote, so Caddy rejected the basic-auth hash with `illegal base64 data at input byte 0` and exited. The script validated only after recreating the live proxy, so the bad candidate killed Caddy before the deploy failed.

## Expected Guidance

No Hermes container changes are needed. The toolkit should protect the shared proxy by validating the candidate config/env before recreating the live container, and by sourcing runtime auth values through shell semantics instead of relying only on Compose `env_file` parsing.

## Validation Notes

- Recovery evidence: restored remote `central-proxy`, then verified `stock-dashboard.zenia.eu` and `hermes.zenia.eu` return `HTTP/2 401` and `portainer.zenia.eu` returns `HTTP/2 200`.
- Regression proof: `source .venv/bin/activate && python -m pytest tests/pytests/test_ubuntu_deploy.py::test_proxy_compose_accepts_basic_auth_environment_overrides tests/pytests/test_ubuntu_deploy.py::test_proxy_deploy_script_prevalidates_before_recreating_caddy -x -v` failed before the fix because proxy Compose did not explicitly accept sourced Basic Auth values.
- Focused validation passed after the fix: `source .venv/bin/activate && python -m pytest tests/pytests/test_ubuntu_deploy.py -v` reported 57 passed.
- Shell validation passed: `bash -n scripts/deploy/ubuntu_deploy_proxy.sh`.