---
name: code-simplify
description: "Use when: invoking /code-simplify, simplifying working deploy code without changing behavior, reducing nesting or duplication, improving names, removing dead code, shrinking overbuilt abstractions, or preparing code for review."
---

# Code Simplify Skill

## Principles

Simplification means making working code easier to understand, test, and change while preserving exact behavior. It is not a line-count contest.

Preserve inputs, outputs, side effects, error behavior, CLI behavior, env-schema behavior, Compose output, docs-visible commands, and tests.

## When To Use

- Code works but is harder to read or maintain than needed.
- A review flags nesting, vague names, duplication, dead code, or needless abstraction.
- A feature needs a cleanup pass before review.

## Procedure

1. Understand callers, tests, docs, and deploy contracts before editing.
2. Establish a focused validation baseline.
3. Identify concrete simplification signals: deep nesting, repeated conditionals, duplicate env parsing, unused helpers, speculative wrappers, or comments that restate code.
4. Make one coherent simplification at a time.
5. Run focused validation after behavior-sensitive changes.
6. Verify tests pass without weakening assertions.

## Red Flags

- Tests must be weakened for the simplification to pass.
- Error handling, logging, secret redaction, compatibility behavior, or docs-visible CLI behavior disappears.
- Refactor mixes with feature or bug-fix work.
- Changes touch unrelated deploy surfaces without a dependency reason.
- You cannot explain why behavior is preserved.

## Exit Criteria

- [ ] Behavior and public contracts are preserved.
- [ ] Scope stayed focused.
- [ ] Existing tests were not weakened.
- [ ] Focused validation passed or baseline failures are reported.
- [ ] The final diff is easier to review and explain.