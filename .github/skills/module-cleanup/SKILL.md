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
- When a module has grown beyond 1000 lines.
- When duplicate logic is spotted across files.
- When preparing a module for a significant feature addition.
- When explicitly asked to clean up or optimize a module.
- When defs are found not used anywhere in the codebase or only in tests, we need to remove it.

## Procedure

### Step 1 — Audit the Module

1. **List all files** in the target module and their line counts:
   ```bash
   find src/<module>/ -name '*.py' | xargs wc -l | sort -n
   ```

2. **Identify dead code**:
   - Unused imports (use `grep` or IDE analysis).
   - Functions/classes with zero callers (use `grep -r "function_name" src/`).
   - Commented-out code blocks.
   - Deprecated feature flags or config branches.

3. **Identify duplicate logic**:
   - Similar functions across files in the module.
   - Copy-pasted patterns that differ only in parameters.
   - Logic that already exists in `src/common/` but was re-implemented.

### Step 2 — Remove Dead Code

- Delete unused imports, functions, classes, and commented-out blocks.
- Defs that are only used in tests should be moved to the test files or removed if they are not necessary.
- Remove obsolete feature flags and their branches.
- **Commit immediately** after each removal with a clear message:
  ```
  cleanup(<module>): remove unused <what>
  ```

### Step 3 — Extract Helpers

For files exceeding **1000 lines**:

1. Identify cohesive groups of helper functions.
2. Extract them into `src/<module>/<name>_helpers.py`.
3. Update imports in the original file.
4. Check if **other modules** can reuse these helpers — if so, consider moving to `src/common/`.

Naming convention:
- Helper module: `<original_name>_helpers.py`
- Test file: `tests/pytests/test_<module>_<name>_helpers.py`

### Step 4 — Refactor Duplicates

1. Identify the canonical location for the logic (prefer `src/common/` for cross-module use).
2. Create a single reusable function or class.
3. Replace all duplicate call sites with imports from the canonical location.
4. Run tests after each replacement to catch breakage early.

### Step 5 — Add Tests for Helpers

For every extracted or refactored helper:

1. Create or update the test file: `tests/pytests/test_<module>_<name>_helpers.py`
2. Cover:
   - Normal operation (happy path).
   - Edge cases (empty input, boundary values).
   - Error cases (invalid input that should raise or return gracefully).
3. Run the tests:
   ```bash
   source .venv/bin/activate && python -m pytest tests/pytests/test_<module>_<name>_helpers.py -v
   ```

### Step 6 — Review Documentation

1. Check `docs/<module>/` for:
   - Missing documentation for new helpers or changed behavior.
   - Duplicate descriptions across files that should be consolidated.
   - Broken or incorrect internal links.
2. Fix any issues found.
3. Ensure each doc starts with a **Principles** section.

### Step 7 — Verify & Commit

1. Run the full test suite:
   ```bash
   source .venv/bin/activate && python scripts/run_tests.py
   ```
2. Verify no regressions.
3. Commit with:
   ```
   cleanup(<module>): Phase 0 complete — <summary of changes>
   ```

## Exit Criteria

Phase 0 is complete when ALL of the following are true:

- [ ] No unused imports, functions, or commented-out code remains.
- [ ] No file exceeds 1000 lines.
- [ ] Duplicate logic has been consolidated into reusable helpers.
- [ ] All extracted helpers have pytest coverage.
- [ ] `docs/<module>/` is accurate and non-duplicative.
- [ ] Full test suite passes with no regressions.

## Code Quality Checklist

- **PEP 8** compliance (style, naming, spacing).
- **f-strings** for all string formatting.
- **Type annotations** on all function signatures.
- **Dataclass-first** for internal data structures.
- **Logging** with module-appropriate prefixes.
