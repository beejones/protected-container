---
name: test
description: "Use when: invoking /test, choosing focused validation, writing or running pytest, Docker Compose config checks, deploy command help checks, env-schema validation, CI evidence, or proving bug fixes before merge."
---

# Test Skill

## Principles

Tests are proof. Pick the smallest validation that can catch the likely regression, then broaden when deploy-contract risk justifies it.

## Common Commands

```bash
source .venv/bin/activate && pytest -q tests/pytests/test_<module>.py
source .venv/bin/activate && python3 scripts/deploy/validate_env.py
source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py --help
source .venv/bin/activate && python scripts/deploy/azure_deploy_container.py --help
docker compose -f docker/docker-compose.yml config
docker compose -f docker/proxy/docker-compose.yml config
docker compose -f docker/storage-manager/docker-compose.yml config
```

## When To Use

- New behavior, bug fixes, refactors, CLI changes, env schema changes, Compose changes, docs commands, or workflow changes need proof.
- A plan needs concrete verification commands.
- A failure must be triaged into test issue vs production issue.

## Procedure

1. Classify the change: pure helper, CLI, env schema, Compose, docs, workflow, Ubuntu, Azure, storage-manager, or browser-facing.
2. Choose focused validation that can falsify the changed path.
3. For bug fixes, follow `bug-fix`: reproduction test fails before fix and passes after.
4. Broaden to compose config, deploy command help, env validation, or CI-equivalent checks when contracts changed.
5. Record exact commands and outcomes in the final summary or PR report.

## Red Flags

- "All tests pass" without commands.
- Bug fix without a failing regression test.
- Env/Compose changes without schema/config validation.
- Deploy command behavior changes without `--help` or dry/local validation.
- Docs command updates without checking command accuracy.
- Skipped or weakened tests are hidden in the diff.

## Exit Criteria

- [ ] Focused validation matches the behavior at risk.
- [ ] Broader deploy readiness checks ran when contracts changed.
- [ ] Exact commands and outcomes are recorded.
- [ ] Existing baseline failures are reported clearly.