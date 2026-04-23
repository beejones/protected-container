---
name: bug-fix
description: "Use when: fixing a bug, diagnosing an error, uncaught exception, test failure root-cause, regression. Test-first bug-fix process with gate-checked steps: hypothesis → failing test → minimal fix → verify."
---

# Bug-Fix Process (Test-First, Gate-Checked)

## Principles

Every bug fix must be **proven correct by a test that failed before the fix and passes after**. This guards against:
- Fixes that don't actually address the root cause.
- Regressions introduced by future changes.
- Tests that are tautological (pass regardless of the bug).

## When to Use

- A bug is reported or discovered during implementation.
- An uncaught exception, wrong output, or unexpected behavior is observed.
- A test fails and the root cause is in production code.
- A regression is detected after a refactor or feature change.

## Procedure

Follow these steps **in strict order**. Do NOT skip or reorder.

### Step 1 — Hypothesize

Form a hypothesis about the **root cause**. State it explicitly:
- In the todo list or commit message.
- Be specific: *"The bug is caused by X in function Y because Z."*

Do NOT guess broadly — narrow down to a single code path or condition.

### Step 2 — Write a Failing Test (GATE)

Write a test that **expects the correct behavior** (the behavior after the fix).

```bash
source .venv/bin/activate && python -m pytest tests/pytests/test_<module>.py::<TestClass>::<test_name> -x -v
```

**GATE CHECK: The test MUST fail.**

| Test result | Action |
|---|---|
| **Fails** ✓ | Hypothesis confirmed — proceed to Step 3. |
| **Passes** ✗ | Hypothesis is **wrong**. Delete the test, go back to Step 1, and re-evaluate. Do NOT proceed. |

### Step 3 — Implement the Minimal Fix

- Change **only production code** — the minimum needed to fix the bug.
- Do NOT modify the test written in Step 2.
- Do NOT refactor, clean up, or add features in the same change.

### Step 4 — Verify

Run the specific test again — it **must now pass**:

```bash
source .venv/bin/activate && python -m pytest tests/pytests/test_<module>.py::<TestClass>::<test_name> -x -v
```

Then run the full test suite to check for regressions:

```bash
source .venv/bin/activate && python -m pytest tests/
```

| Result | Action |
|---|---|
| Both pass ✓ | Commit the test and fix together. |
| Specific test fails | Fix is incomplete — revisit Step 3. |
| Other tests fail | Fix introduced a regression — revisit Step 3 with a narrower change. |

### Step 5 — Commit

Commit the test and fix together with a clear message:

```
fix(<module>): <short description>

Root cause: <hypothesis from Step 1>
Test: tests/pytests/test_<module>.py::<test_name>
```

## Anti-Patterns (Forbidden)

| Anti-pattern | Why it's wrong |
|---|---|
| Writing the fix before the test | Violates test-first; you can't prove the test would have caught the bug. |
| Test passes immediately | Hypothesis is wrong or test is trivial — must redo Step 1. |
| Modifying the test to make it pass | The test defines correct behavior; changing it defeats the purpose. |
| Skipping the "must fail" gate | Without proof of failure, the test may not actually cover the bug. |
| Large refactors in the fix commit | Mix of concerns; keep the fix minimal and isolated. |
