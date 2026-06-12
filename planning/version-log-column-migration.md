# Plan: Version Log Column Migration

## Principles

- The version log is local deploy state, so readers should see the newest record directly under a stable header.
- Header changes must be self-healing: if an old supported schema is detected, the next write rewrites all rows into the current schema.
- Version ownership stays unchanged: deploy logging owns `.env` `APP_VERSION` and `out/deploy/version_log.csv`; changelog release notes stay separate.
- Schema changes should stay boring unless a new field has a reliable source and an active query use case.

## Overview

Change `out/deploy/version_log.csv` from `timestamp,git_ref,local_branch,version,target,stack_name,domain,image,status` to `timestamp,git_ref,version,status,target,local_branch,stack_name,domain,image`, and automatically migrate supported old layouts when deploy logging next writes the file.

## Scope

- Goal: New deploy and merge records use the requested column order, while old nine-column and older eight-column logs are rewritten into that order automatically.
- Non-goals: Do not add speculative columns in this pass; do not alter version bump semantics; do not make `CHANGELOG.md` automatic.
- Affected deploy surfaces: Ubuntu deploy logging, merge workflow version logging, docs, and focused pytest coverage.
- Unaffected deploy surfaces: Docker Compose service shape, env schema, hooks API shape, Azure deployment, Caddy routing, and Storage Manager behavior.

## Current Context

- `scripts/deploy/deploy_log.py` already stores newest rows directly below the CSV header.
- The module currently normalizes the older eight-column header and the current nine-column header in memory, but it writes the current nine-column header back out.
- `docs/deploy/STAGING.md` documents the version-log columns and rollback workflow.
- `docs/deploy/HOOKS.md` documents `DeployLogSettings.csv_path` and versioning behavior for downstream wrappers.

## Architecture Decisions

- Use header-aware migration rather than positional guessing for supported schemas.
- Keep the CSV at nine fields for this change. Candidate future fields such as `duration_seconds`, `deploy_actor`, `remote_host`, `deploy_mode`, or `toolkit_ref` are useful only if the deploy engine captures them consistently across merge, staging, production, and swap records.
- Keep the internal row representation ordered by the new `CSV_COLUMNS`, so version/status lookup helpers keep indexing one canonical schema.

## Task Overview

- [ ] Phase 0: Cleanup and documentation audit
- [ ] Phase 1: Implement header-aware migration and new writer order
- [ ] Phase 2: Update tests and docs for the new CSV contract
- [ ] Phase 3: Validate, update the plan, and archive if complete

## Phase 0 - Cleanup And Documentation Audit

Follow `.github/skills/code-cleanup/SKILL.md` for `scripts/deploy/deploy_log.py` and `tests/pytests/test_deploy_log.py`.

### Tasks

- [ ] Audit `deploy_log.py` for duplicated row normalization and stale column-index assumptions.
- [ ] Audit `test_deploy_log.py` for brittle positional assertions that should instead track the new canonical order.
- [ ] Review `docs/deploy/STAGING.md` and `docs/deploy/HOOKS.md` for stale version-log contract text.
- [ ] Confirm focused validation target before implementation.

### Exit Criteria

- [ ] Cleanup findings are resolved or recorded as follow-ups.
- [ ] The affected docs are known and scheduled for update.
- [ ] Focused validation target is `source .venv/bin/activate && python -m pytest tests/pytests/test_deploy_log.py -v`.

## Phase 1 - Migration And Writer Order

### Tasks

- [ ] Update `CSV_COLUMNS` to `timestamp,git_ref,version,status,target,local_branch,stack_name,domain,image`.
- [ ] Preserve constants for supported legacy layouts so old files can be detected by header.
- [ ] Convert old nine-column and older eight-column rows into the new canonical row order.
- [ ] Ensure append logic writes the new header and migrates existing rows on the next write.

### Acceptance Criteria

- [ ] A log with the old nine-column header rewrites into the new header without losing branch, status, target, stack, domain, or image values.
- [ ] A log with the older eight-column header still backfills `local_branch` as `main` and rewrites into the new header.
- [ ] New deploy and merge rows write `version` and `status` before `target`.

### Verification

- [ ] `source .venv/bin/activate && python -m pytest tests/pytests/test_deploy_log.py -v`

### Files Likely Touched

- `scripts/deploy/deploy_log.py`
- `tests/pytests/test_deploy_log.py`

### Exit Criteria

- [ ] Supported old schemas migrate automatically on append.
- [ ] Version bump and same-git-ref reuse behavior is unchanged.

## Phase 2 - Documentation

### Tasks

- [ ] Update `docs/deploy/STAGING.md` with the new column order and migration behavior.
- [ ] Update `docs/deploy/HOOKS.md` if hook guidance needs to mention automatic migration for custom CSV paths.
- [ ] Update `CHANGELOG.md` only if this branch is being prepared as a versioned release entry.

### Acceptance Criteria

- [ ] Docs show the new header order.
- [ ] Docs state that supported old headers are migrated automatically on the next deploy-log write.
- [ ] Docs do not imply changelog entries are generated by deploy logging.

### Verification

- [ ] Manual docs review against `deploy_log.py` constants and tests.

### Files Likely Touched

- `docs/deploy/STAGING.md`
- `docs/deploy/HOOKS.md`
- `CHANGELOG.md` if release notes are updated

### Exit Criteria

- [ ] The documented contract matches the code and tests.

## Phase 3 - Validation And Handoff

### Tasks

- [ ] Run focused pytest for deploy log behavior.
- [ ] Run typed-code-generation grep checks against changed Python files.
- [ ] Run `git diff --check`.
- [ ] Mark completed tasks and archive this plan if complete.

### Exit Criteria

- [ ] Focused tests pass.
- [ ] Typing guardrail search has no new violations.
- [ ] Diff whitespace checks pass.
- [ ] Plan is archived with completed checkboxes or left active with explicit remaining work.

## Risks And Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Positional row migration swaps values | High | Use header-specific conversion functions and tests for both supported legacy headers. |
| Downstream custom CSV paths stay old until written | Low | Document that migration happens on the next deploy-log write for any configured CSV path. |
| Extra fields create blank or inconsistent records | Medium | Defer new columns until the deploy engine captures a field consistently across record types. |

## Validation Plan

- Focused: `source .venv/bin/activate && python -m pytest tests/pytests/test_deploy_log.py -v`
- Typing scan: `rg "\bAny\b|\bobject\b|TypeAlias\s*=\s*(dict|Dict|Mapping|MutableMapping)|dict\[str, object\]|Dict\[str, object\]|Mapping\[str, object\]|MutableMapping\[str, object\]|: dict\b|-> dict\b" scripts/deploy/deploy_log.py tests/pytests/test_deploy_log.py`
- Whitespace: `git diff --check`

## Open Questions

- None. Extra fields are intentionally deferred unless a concrete downstream query or deploy-engine source is identified.