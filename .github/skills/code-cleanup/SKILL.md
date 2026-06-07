---
name: code-cleanup
description: "Use when: invoking /code-cleanup, cleaning the module currently being changed, running code-simplify as part of cleanup, removing duplicated or obsolete code, consolidating repeated logic, and applying typed-code-generation with existing dataclasses before Python edits."
---

# Code Cleanup

## Purpose

Code cleanup is a cleanup pass for the module currently being worked on. It combines behavior-preserving simplification, duplicate-code removal, obsolete-code deletion, and strict typed boundaries.

Use this skill when the user asks for cleanup, when a touched module has obvious duplication or stale code, during Phase 0 cleanup, or before continuing feature work in code that is hard to review.

## Required Skill Chain

Before editing code:
- Read and follow `.github/skills/code-simplify/SKILL.md` for the module or files being cleaned.
- For Python production or test edits, read and follow `.github/skills/typed-code-generation/SKILL.md`.
- If the cleanup exposes wrong behavior or failing tests caused by production code, switch to `.github/skills/bug-fix/SKILL.md` before changing behavior.

## Hard Rules

- Preserve behavior unless the user explicitly requested a behavior change.
- Keep scope to the module or files currently being changed.
- Delete obsolete code immediately once unused status is verified.
- Consolidate duplicated logic into the best existing helper or a new focused helper with tests when behavior risk is non-trivial.
- Prefer existing dataclasses, protocols, enums, and model-owned types before creating any new shape.
- Do not create `TypeAlias` wrappers around `dict`, `Mapping`, `MutableMapping`, or generic payloads to pretend a loose dict is typed.
- Do not introduce `Any`, `object`, generic dicts, or optional-required parameters in core logic.
- Do not weaken tests to make cleanup pass.
- Do not commit changes unless the user explicitly asks.

## Procedure

### Step 1 - Scope The Cleanup

Identify the active module or files:
- Files already touched in the current task.
- Files the user named explicitly.
- The nearest module directory when the user says "this module" or "the module we are working on".

Record the focused validation target before editing: a pytest selector, UI test, replay command, or other existing check that covers the cleanup surface.

### Step 2 - Run Code Simplify On The Target

Apply `.github/skills/code-simplify/SKILL.md` to the target module or files:
- Understand callers and behavior before editing.
- Prefer guard clauses, clearer names, and smaller helpers only when they reduce real complexity.
- Avoid clever compression and unrelated refactors.
- Keep every observable behavior, side effect, error path, log, and response shape intact.

### Step 3 - Find And Remove Duplication

Check for duplicated code in and near the target:
- Repeated parsing, normalization, validation, serialization, or fallback logic.
- Similar helper functions split across neighboring files.
- Logic reimplemented locally when `src/common/` or the target module already has a helper.
- Repeated test fixture builders that should share a local fixture/helper.

When duplication is real:
- Pick the canonical location with the smallest ownership boundary.
- Prefer existing helpers over new abstractions.
- Move shared behavior into a helper only when the helper has a clear domain name and at least one meaningful reuse.
- Update all duplicate call sites and delete the old copies.

### Step 4 - Delete Obsolete Code

Look for:
- Unused imports, functions, classes, constants, and branches.
- Commented-out code.
- Compatibility shims with no production or documented callers.
- Feature flags, fallbacks, or config paths that are no longer reachable.
- Test-only production defs that should live in tests or be removed.

Before deleting, verify with search, symbol usages, tests, and docs when needed. If usage is ambiguous, keep the code and record why instead of guessing.

### Step 5 - Apply Typed Code Generation

For Python edits, follow `.github/skills/typed-code-generation/SKILL.md`:
- Search model modules first (`models.py`, `*_models.py`, domain model modules such as `signal_config.py`, schema modules, and existing dataclasses).
- Use existing dataclasses directly when they represent the internal shape.
- Convert raw API/file/JSON payloads at named boundaries such as `*_from_payload`, `*_from_api_request`, `to_dict`, or `from_dict`.
- Pass dataclasses, protocols, enums, or strict scalar values into internal logic.
- Do not hide dicts behind `TypeAlias`; a dict alias is not a typed domain object.

### Step 6 - Validate

Run validation proportional to risk:
- Focused tests for the changed module.
- UI or browser checks when templates/static JS/CSS changed.
- `source .venv/bin/activate && python scripts/run_tests.py` when cleanup crosses shared behavior or many modules.

For Python cleanup, scan changed files for loose typing patterns:

```bash
rg "\bAny\b|\bobject\b|TypeAlias\s*=\s*(dict|Dict|Mapping|MutableMapping)|dict\[str, object\]|Dict\[str, object\]|Mapping\[str, object\]|MutableMapping\[str, object\]|: dict\b|-> dict\b" <changed-python-files>
```

Every remaining match must be one of:
- An explicit API/file/JSON/test boundary.
- Legacy code outside the cleanup scope.
- A violation fixed before completion.

## Exit Criteria

Code cleanup is complete when:
- [ ] The target module was simplified through the `code-simplify` workflow.
- [ ] Meaningful duplicated code was consolidated or explicitly ruled out.
- [ ] Obsolete code in scope was deleted.
- [ ] Python edits use existing dataclasses/model types where available and do not add dict `TypeAlias` pseudo-types.
- [ ] Focused validation passed, or pre-existing failures are reported with evidence.
- [ ] The final diff is narrower, clearer, and easier to review than the starting point.