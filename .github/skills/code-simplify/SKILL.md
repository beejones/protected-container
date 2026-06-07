---
name: code-simplify
description: "Use when: invoking /code-simplify, simplifying working code without changing behavior, reducing nesting or duplication, improving names, removing dead code, shrinking overbuilt abstractions, or preparing code for easier review while preserving exact behavior."
---

# Code Simplify Skill

## Principles

Simplification means making working code easier to understand, test, and change while preserving exact behavior. The goal is not fewer lines. The goal is lower cognitive load, smaller review surface, and code that better matches this repository's conventions.

Preserve all observable behavior:
- Inputs and outputs.
- Error handling and exception types.
- Side effects and ordering.
- API response shape and JSON safety.
- UI behavior, layout intent, and accessibility affordances.
- Existing tests without weakening assertions.

## When To Use

- The user invokes `/code-simplify`.
- Code works, but it is harder to read or maintain than it should be.
- A review flags deep nesting, vague names, duplication, dead code, or needless abstraction.
- A recently implemented feature needs a cleanup pass before review.
- A module has local complexity that does not require the broader `.github/skills/code-cleanup/SKILL.md` workflow.

## When Not To Use

- Behavior is wrong or a test is failing because of a production bug. Use `.github/skills/bug-fix/SKILL.md`.
- Requirements are changing. Do the feature or bug workflow first, then simplify.
- The code is performance-critical and the simpler version has not been measured.
- You do not understand the code, callers, tests, and edge cases yet.
- The requested scope is a full cleanup pass. Use `.github/skills/code-cleanup/SKILL.md` and apply this skill inside individual refactors.

## Required Repo Guardrails

- Read `AGENT.md` and `.github/copilot-instructions.md` before broad simplification.
- Never read `.env.secrets` or `.env.deploy.secrets`.
- For Python production or test edits, read `.github/skills/typed-code-generation/SKILL.md` before changing code.
- Keep changes scoped to the user request and nearby touched code.
- Do not mix simplification with feature work or behavior-changing fixes.
- Do not weaken or rewrite tests just to make a refactor pass.
- Do not commit unless the user explicitly asks.

## Procedure

### Step 1 - Understand Before Editing

Apply Chesterton's Fence: understand why the code exists before removing or rewriting it.

Answer these questions before changing code:
- What responsibility does this code own?
- What calls it, and what does it call?
- What inputs, outputs, side effects, and error paths must be preserved?
- Which tests currently define behavior?
- Are there docs or planning files that explain the intended design?
- Is there git history that explains surprising complexity?

If the answers are unclear, gather more context first. Use semantic search, symbol usages, tests, docs, and git history as needed.

### Step 2 - Establish A Baseline

Identify the smallest meaningful validation target before editing:
- Focused pytest file or selector for Python logic.
- UI test for template, JavaScript, or CSS behavior.
- Existing analyzer/optimizer replay command for strategy-sensitive behavior.
- Manual browser check for visual-only changes.

Run the baseline when practical. If baseline tests already fail, record the failure and avoid claiming the simplification caused or fixed it unless you prove that with a separate bug-fix workflow.

### Step 3 - Find Concrete Simplification Opportunities

Look for specific signals, not vague preferences.

Structural signals:
- Deep nesting that can become guard clauses or focused helpers.
- Long functions with multiple responsibilities.
- Repeated conditionals that deserve a named predicate.
- Boolean flag arguments that obscure intent at call sites.
- Local helper chains where one helper adds no name, reuse, or test value.

Readability signals:
- Generic names such as `data`, `result`, `value`, or `temp` when the domain object is known.
- Abbreviations that are not common in the repo.
- Comments that restate obvious code instead of explaining intent.
- Dense expressions that require more effort than an explicit branch or named variable.

Redundancy signals:
- Duplicated logic across nearby files.
- Unused imports, unreachable branches, and commented-out code.
- Speculative abstractions with one implementation and no current extension point.
- Boundary parsing or JSON handling repeated instead of using an existing helper.

Python typing signals:
- Raw `dict`, `object`, `Any`, or optional-required inputs leaking past boundaries.
- Payload parsing repeated inside core logic instead of normalized at an adapter/API/file boundary.
- Missing dataclasses or enums where several fields travel together.

### Step 4 - Choose The Simplest Safe Change

Prefer transformations that reduce reader effort without changing contracts:
- Replace nested branches with early returns while keeping error behavior identical.
- Extract a helper only when the helper gives a real concept a useful name or removes meaningful duplication.
- Inline a wrapper only when it adds no validation, naming value, compatibility boundary, logging, or test seam.
- Rename symbols only when the new name is clearer and update all usages safely.
- Delete dead code only after confirming it has no production callers and no documented role.
- Reuse existing utilities in `src/common/` or the target module before creating new ones.

Avoid clever compression. A shorter expression that makes the reader pause is not simpler.

### Step 5 - Apply Changes Incrementally

Make one coherent simplification at a time:
1. Edit the smallest set of files needed.
2. Run the focused validation target when the change can affect behavior.
3. Keep or revert based on evidence.
4. Move to the next simplification only after the previous one is understandable and reviewable.

If a simplification would touch more than about 500 lines, stop and consider automation, narrower scope, or a separate planning file.

### Step 6 - Verify Behavior Preservation

Run validation proportional to risk:
- Focused tests for the changed module.
- UI tests and browser verification for frontend behavior.
- Full `source .venv/bin/activate && python scripts/run_tests.py` when simplification crosses shared contracts or multiple workflows.
- For Python changes, search changed files for forbidden loose typing patterns from `typed-code-generation` and justify any boundary-only matches.

Compare before and after:
- Is the new code easier to understand by repo conventions?
- Is the diff smaller and more reviewable than the original complexity?
- Did any error handling, fallback behavior, logging, or JSON safety disappear?
- Did tests pass without weakening expectations?

## Common Simplifications

Use these examples as direction, not as automatic rewrites:
- Nested validation branches -> guard clauses that preserve the same exceptions.
- Duplicated field parsing -> one named boundary normalizer returning a strict type.
- Repeated literal statuses or modes -> enum or local constants when the repo pattern supports it.
- Scattered boolean expressions -> named predicates when the concept appears more than once.
- Overlong function -> private helpers grouped by responsibility and covered by focused tests.
- Commented-out code -> removal after confirming history preserves it if needed.

## Common Rationalizations

| Rationalization | Reality |
| --- | --- |
| "Fewer lines is simpler." | Simplicity is comprehension speed, not line count. |
| "I can improve this unrelated area too." | Unscoped cleanup creates noisy diffs and regression risk. |
| "The tests need updating because the code is cleaner now." | If behavior is preserved, tests should not need weaker expectations. |
| "This abstraction may help someday." | Speculative flexibility is current complexity. Keep abstractions with present value. |
| "The original code is weird, so it can go." | First understand callers, history, and edge cases. Weird code may be protecting a real contract. |
| "Type cleanup is just aesthetics." | In this repo, strict typed boundaries prevent real analyzer/trading bugs. Follow typed-code-generation. |

## Red Flags

- Tests must be weakened or deleted for the simplification to pass.
- Error handling, logging, auth behavior, JSON sanitization, or fallbacks disappear without an explicit replacement.
- The diff mixes refactor, feature, and bug-fix work.
- A helper is extracted with a vague name and one trivial caller.
- A meaningful domain name is replaced with a generic one.
- The refactor touches many unrelated modules.
- You cannot explain why behavior is preserved.
- Baseline failures are silently ignored in the final summary.

## Exit Criteria

The `/code-simplify` skill is complete when:
- [ ] The simplified code preserves behavior and public contracts.
- [ ] The scope stayed focused on requested or recently touched code.
- [ ] Existing tests were not weakened to accommodate the refactor.
- [ ] Focused validation passed, or baseline failures are clearly reported.
- [ ] Python changes satisfy typed-code-generation guardrails.
- [ ] Dead code introduced or revealed by the simplification was removed.
- [ ] The final diff is easier to review and explain than the original code.