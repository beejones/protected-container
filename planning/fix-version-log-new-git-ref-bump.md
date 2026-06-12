# Fix Version Log New Git Ref Bump

## Principles

- `out/deploy/version_log.csv` records successful merge refs and Ubuntu deploy refs.
- A repeated successful row for the same git ref reuses the version already recorded for that git ref.
- A successful merge or Ubuntu deploy for a different git ref bumps root `.env` `APP_VERSION` before writing the new version-log row.
- Failed deploy rows do not bump `.env` `APP_VERSION`.
- Deploy logging stays local to the shared deploy contract and does not read secret dotenv files.

## Checkable Task Overview

- [ ] Phase 0 cleanup: inspect `scripts/deploy/deploy_log.py`, its tests, and nearby docs for stale versioning assumptions.
- [ ] Phase 0 cleanup: confirm no duplicated version-selection helper should be extracted before the bug fix.
- [ ] Phase 0 cleanup: remove or update obsolete text revealed by the new versioning contract.
- [ ] Phase 0 cleanup: keep Python typing strict and avoid new loose payload types.
- [ ] Phase 1 bug proof: add a regression test that fails when a new successful deploy git ref reuses the previous version.
- [ ] Phase 2 implementation: update deploy-log version selection so new successful git refs bump `.env` patch before the row is written.
- [ ] Phase 2 implementation: preserve same-git-ref reuse and disabled-versioning behavior.
- [ ] Phase 3 docs: update deploy docs that currently say new git refs record the current `APP_VERSION`.
- [ ] Phase 4 validation: run focused deploy-log tests.
- [ ] Phase 4 validation: run the relevant typing guard scan on changed Python files.
- [ ] Phase 4 validation: run a deploy-log CLI parse or focused deploy command check if needed.

## Affected Surfaces

- Ubuntu deploy: `ubuntu_deploy.py` calls deploy logging after deploy completion.
- Deploy version log: `scripts/deploy/deploy_log.py` owns `.env` `APP_VERSION` reads/writes and CSV rows.
- Docs: `docs/deploy/STAGING.md` and `docs/deploy/HOOKS.md` describe the versioning contract.
- Tests: `tests/pytests/test_deploy_log.py` covers merge/deploy version-log behavior.

Local Docker, Azure deploy, env schema, and deployment hooks are not expected to need behavior changes for this bug.

## Root-Cause Hypothesis

`append_deploy_record_with_settings()` only reuses an existing version for the same successful git ref. When the current git ref is new, it records the current `.env` `APP_VERSION` without comparing the newest successful version-log record, so a new deploy can write another `0.2.6` row for a different git ref.

## Phase Exit Criteria

### Phase 0 Cleanup

- The version-log module has been inspected with the `code-cleanup`, `code-simplify`, and `typed-code-generation` workflows.
- No unrelated refactor is mixed into the bug fix.
- Stale docs or test names that contradict the intended contract are identified for update.

### Phase 1 Bug Proof

- A focused pytest regression test expects a new successful deploy git ref to bump `.env` patch after a previous successful row.
- The regression test fails before the production fix.

### Phase 2 Implementation

- New successful deploy refs bump `.env` `APP_VERSION` and record that bumped version.
- Same successful git refs reuse their existing recorded version.
- Disabled versioning keeps the current explicit behavior.
- Failed deploy rows do not bump `.env`.

### Phase 3 Docs

- Deploy docs describe the new-git-ref bump rule consistently.
- Hook docs accurately describe `settings.versioning_enabled`.

### Phase 4 Validation

- `source .venv/bin/activate && python -m pytest tests/pytests/test_deploy_log.py -v` passes.
- Changed Python files pass the typed-code-generation loose-typing scan or remaining matches are documented as existing explicit boundaries.

## Notes

- The build-feature mode references `.github/skills/module-cleanup/SKILL.md`, but this repo does not currently contain that file. The available repo cleanup workflow is `.github/skills/code-cleanup/SKILL.md`, which chains `code-simplify` and `typed-code-generation`.