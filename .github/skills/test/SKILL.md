---
name: test
description: "Use when: invoking /test, choosing focused validation, writing or running pytest/Playwright tests, using scripts/run_tests.py, priority tests, analyzer or optimizer replay evidence, proving bug fixes, or preparing pre-merge test evidence."
---

# Test Skill

## Principles

Tests are proof. Pick the smallest validation that can catch the bug or regression, then broaden only when the blast radius demands it.

For this repo, the canonical mixed runner is:

```bash
source .venv/bin/activate && python scripts/run_tests.py
```

It manages the test server, auth-disabled test mode, backend tests, UI sharding, and isolated historical data under `tests/out/databases`.

## When To Use

- The user invokes `/test`.
- You need a validation plan for a feature, bug fix, refactor, or PR.
- You are writing or running backend pytest tests.
- You are writing or running Playwright UI tests.
- You need `--priority-tests` for fail-fast validation.
- Analyzer, optimizer, strategy, datasource, or trading behavior needs replay evidence.

## Test Selection

### Focused Backend Logic

Use direct pytest selectors for small Python logic changes:

```bash
source .venv/bin/activate && python -m pytest tests/pytests/test_<module>.py -v
```

Prefer tests in `tests/pytests/` named `test_<module>...`.

### UI Behavior

Use Playwright tests in `tests/UI/` named `test_ui_<module>...`. For UI changes, verify:
- Page renders without console errors.
- Important workflows are covered.
- Layout works at representative desktop and mobile widths.
- Loading, empty, and error states are handled.

### Mixed Or Broad Validation

Use the canonical runner for shared contracts, UI plus backend changes, or pre-merge confidence:

```bash
source .venv/bin/activate && python scripts/run_tests.py
```

Use priority selectors when a risky or recently fixed subset should run before the rest:

```bash
source .venv/bin/activate && python scripts/run_tests.py --priority-tests='["tests/pytests/test_indicator_catalog.py","tests/UI/test_ui_indicator_catalog.py"]'
```

### Analyzer, Optimizer, And Strategy Evidence

For strategy-sensitive changes, pair tests with evidence from the applicable domain skill:
- `analyzer-improvement-check` for analyzer/optimizer parity and live evidence.
- `strategy-promotion-adoption` for promote/reject decisions and JSON updates.

Do not rely only on unit tests when the change can alter strategy outcomes.

## Writing Tests

- Assert outcomes and state, not private implementation details.
- Use descriptive test names that read like expected behavior.
- Keep tests DAMP: clear setup is better than over-shared helpers that hide intent.
- Prefer real local implementations or fakes over mocks when practical.
- Isolate filesystem, database, and runtime state.
- For bug fixes, follow `.github/skills/bug-fix/SKILL.md`: the regression test must fail before the fix and pass after.
- For Python code, follow `.github/skills/typed-code-generation/SKILL.md` before adding test helpers or fixtures.

## Validation Workflow

1. Identify the behavior at risk.
2. Choose the smallest test that proves that behavior.
3. Run it after the relevant code change.
4. If it fails, fix the cause or report the existing baseline failure.
5. Broaden to priority tests or the full runner when the change touches shared workflows.
6. Record exact commands and outcomes in the final summary or PR report.

Do not rerun the same passing command repeatedly without code changes. It adds time but not confidence.

## Red Flags

- "All tests pass" without the command that ran.
- Bug fix with no failing regression test.
- Tests skipped, weakened, or renamed to avoid failures.
- UI change with no browser or Playwright verification.
- Strategy change with no analyzer/optimizer evidence.
- Mock-heavy tests that never exercise real repo behavior.
- Full suite used as a substitute for a targeted test that should exist.

## Exit Criteria

- [ ] Focused validation matches the behavior at risk.
- [ ] Broad validation ran when shared contracts or user workflows changed.
- [ ] Exact commands and outcomes are recorded.
- [ ] New behavior has tests or a documented reason when tests are not practical.
- [ ] Existing baseline failures are reported clearly and not claimed as caused by unrelated edits.