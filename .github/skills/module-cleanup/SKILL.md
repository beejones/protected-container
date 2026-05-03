---
name: module-cleanup
description: "Use when: Phase 0 cleanup, refactoring a module, reducing file size, extracting helpers, removing dead code, improving code quality before a feature build. Structured module optimization procedure."
---

# Module Cleanup (Phase 0)

## Principles

Every feature plan starts with cleanup of the module being changed. This guards against:
- Accumulating dead code that obscures intent.
- Duplicated logic that diverges over time.
- Large files that are hard to navigate and review.
- Missing test coverage for shared helpers.

## When to Use

- Phase 0 of any planning file (mandatory).
- When a deploy script, compose file set, or docs area has grown hard to reason about.
- When duplicate logic is spotted across `scripts/deploy/`, `docker/`, `docs/deploy/`, or `tests/pytests/`.
- When preparing a module for a significant feature addition.
- When explicitly asked to clean up or optimize a module.
- When defs are found not used anywhere in the codebase or only in tests.

## Procedure

### Step 1 — Audit the Target Slice

1. **List all files** in the target path and their line counts:
   ```bash
   find <target-path> -type f \( -name '*.py' -o -name '*.md' -o -name '*.sh' -o -name '*.yml' \) | xargs wc -l | sort -n
   ```

2. **Identify dead code or stale contract surface**:
   - Unused imports or helpers in `scripts/deploy/`.
   - CLI flags, env keys, or branches that are no longer referenced.
   - Commented-out code blocks.
   - Docs or planning steps that no longer match current behavior.

3. **Identify duplicate logic**:
   - Similar helpers across deploy scripts.
   - Copy-pasted command construction or env resolution.
   - Repeated deployment contract descriptions across `README.md`, `docs/deploy/`, and planning files.

### Step 2 — Remove Dead Code And Stale Contracts

- Delete unused imports, functions, classes, and commented-out blocks.
- Defs that are only used in tests should be moved to the test files or removed if they are not necessary.
- Remove obsolete flags, env keys, compose labels, or docs branches that no longer reflect the product.
- Commit immediately after each meaningful removal with a clear message.

### Step 3 — Extract Helpers

For files that have become too large or mix unrelated concerns:

1. Identify cohesive groups of helper functions.
2. Extract them into a nearby helper module, for example:
   - `scripts/deploy/<topic>_helpers.py`
   - `tests/pytests/test_<topic>.py`
3. Update imports in the original file.
4. Prefer one canonical helper location rather than duplicate helpers per deploy path.

### Step 4 — Refactor Duplicates

1. Identify the canonical location for the logic, usually under `scripts/deploy/` for shared deployment behavior.
2. Create one reusable helper or function.
3. Replace duplicate call sites.
4. Run focused checks after each replacement to catch breakage early.

### Step 5 — Add Tests For Helpers

For every extracted or refactored helper:

1. Create or update the focused pytest file under `tests/pytests/`.
2. Cover normal behavior, edge cases, and error cases.
3. Run the focused tests:
   ```bash
   source .venv/bin/activate && pytest -q tests/pytests/test_<module>.py
   ```

### Step 6 — Review Documentation

1. Check the relevant docs slice, usually one or more of:
   - `docs/deploy/`
   - `README.md`
   - `planning/`
2. Look for:
   - Missing documentation for changed behavior.
   - Duplicate descriptions that should be consolidated.
   - Broken or incorrect internal links.
   - Examples or env keys that no longer match the code.
3. Fix any issues found.
4. Ensure design docs start with a **Principles** section when they describe guarded behavior.

### Step 7 — Verify And Commit

1. Run the smallest relevant validations first, then broader ones as needed:
   ```bash
   source .venv/bin/activate && pytest
   source .venv/bin/activate && python3 scripts/deploy/validate_env.py
   docker compose -f docker/docker-compose.yml config
   ```
2. Add `bash -n` or extra compose config checks when shell or deploy stacks were touched.
3. Verify no regressions.
4. Commit with a clear Phase 0 cleanup message.

## Exit Criteria

Phase 0 is complete when ALL of the following are true:

- [ ] No unused imports, dead helpers, or commented-out code remains in the target slice.
- [ ] Duplicate logic has been consolidated into reusable helpers.
- [ ] Extracted or refactored helpers have focused pytest coverage.
- [ ] Relevant docs, examples, and planning files are accurate and non-duplicative.
- [ ] Relevant validation commands pass with no regressions.

## Code Quality Checklist

- **PEP 8** compliance (style, naming, spacing).
- **f-strings** for all string formatting.
- **Type annotations** on all function signatures.
- **Shared contract awareness**: Compose, env schema, and docs should agree after cleanup.
- **Logging** should stay consistent with the surrounding module conventions.
