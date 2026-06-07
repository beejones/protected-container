---
name: using-agent-skills
description: "Use when: starting a session, deciding which repo skill applies, routing ambiguous work, chaining multiple skills, or updating AGENT.md skill awareness. Meta-skill for local skill discovery and workflow selection."
---

# Using Agent Skills

## Purpose

This is the local skill router for Stock Dashboard. Use it to choose the smallest applicable workflow skill before starting non-trivial work.

`AGENT.md` stays the compact always-on index. This skill holds the fuller routing rules so agents can load it only when needed.

## Core Rules

- Check for an applicable skill before planning, coding, reviewing, merging, or changing strategy behavior.
- Load only the skills that apply. Do not read every skill as a ritual.
- Skills are workflows with gates; follow their steps and verification requirements.
- Multiple skills can apply in sequence. State the sequence when it matters.
- If requirements are ambiguous enough to change architecture, file ownership, or acceptance criteria, ask the minimum blocking question before proceeding.
- Verification is part of completion. Do not finish with "looks right" when a command, test, replay, or manual check is available.

## Local Skill Map

| Situation | Skill |
| --- | --- |
| Need to decide which skill applies | `using-agent-skills` |
| Starting a session, switching modules, refreshing stale context, or packing relevant files/examples/tests | `context-engineering` |
| User invokes `/plan`, asks for a planning file, or needs task breakdown | `plan` |
| Phase 0 cleanup, code cleanup, dead code, duplication, oversized files | `code-cleanup` |
| Writing or modifying Python production/test code | `typed-code-generation` |
| Bug, regression, exception, failing test rooted in production code | `bug-fix` |
| Need a validation plan, focused tests, UI tests, priority tests, or full-suite evidence | `test` |
| Need browser runtime evidence: DOM, console, network, screenshots, accessibility, or performance traces | `browser-testing-with-devtools` |
| Working code needs behavior-preserving readability/refactor pass | `code-simplify` |
| Reviewing a change before merge or evaluating agent/human code | `review` |
| Designing Flask routes, module boundaries, request/response shapes, or typed contracts | `api-interface-design` |
| Building or changing templates, static JavaScript, CSS, layout, or UI states | `frontend-ui-engineering` |
| Touching auth, secrets, untrusted input, external services, or deployment-sensitive behavior | `security-hardening` |
| Investigating or improving analyzer, optimizer, datasource, API, or UI performance | `performance-optimization` |
| Updating docs, writing rationale, changing public contracts, or capturing architecture decisions | `documentation-and-adrs` |
| Implementing framework/library-specific behavior that must match current official docs | `source-driven-development` |
| Analyzer/optimizer improvement needs live evidence or parity validation | `analyzer-improvement-check` |
| Promote, reject, or apply improved strategy parameters | `strategy-promotion-adoption` |
| PR report, reviewer feedback, CI watch, mergeability, merge, branch cleanup | `merge` |

## Common Skill Sequences

### New Feature Or Broad Change

1. `plan` to create or update the planning artifact.
2. `context-engineering` to load the relevant plan section, source files, tests, docs, and one local pattern example.
3. `code-cleanup` for Phase 0 cleanup.
4. `typed-code-generation` before Python edits.
5. `api-interface-design`, `frontend-ui-engineering`, `security-hardening`, `performance-optimization`, or `source-driven-development` when the feature touches those concerns.
6. `test` for focused and broad validation evidence.
7. `code-simplify` after behavior works and tests pass, if the diff is harder to read than it should be.
8. `documentation-and-adrs` for changed docs, public contracts, or durable decisions.
9. `review` before merge.
10. `merge` for PR/report/CI/merge work.

### Bug Fix

1. `bug-fix` for hypothesis, failing test gate, minimal fix, and verification.
2. `context-engineering` when the failing path spans unfamiliar files or prior assumptions are stale.
3. `typed-code-generation` if Python production or test code changes.
4. `test` for focused regression and full-suite validation planning.
5. `code-simplify` only after the bug fix is proven and only if cleanup remains behavior-preserving.
6. `review` before merge.

### Strategy Improvement

1. `analyzer-improvement-check` for evidence, parity, and analyzer validation.
2. `strategy-promotion-adoption` for final promote/reject decisions and JSON updates.
3. `documentation-and-adrs` when a strategy-contract or decision report needs durable rationale.
4. `review` for final quality gate.
5. `merge` when preparing the final PR or merge.

### API Or Frontend Contract Change

1. `api-interface-design` to define request, response, errors, and compatibility.
2. `frontend-ui-engineering` when the contract is consumed in templates/static JS.
3. `security-hardening` if user input, auth, access keys, or external data is involved.
4. `browser-testing-with-devtools` for runtime console, network, screenshot, accessibility, and layout evidence.
5. `test` for route, UI, and full-suite validation decisions.
6. `documentation-and-adrs` for public behavior or durable decisions.

### Browser-Facing Bug Or Visual Issue

1. `browser-testing-with-devtools` to reproduce and inspect live DOM, console, network, styles, screenshots, or accessibility data.
2. `bug-fix` when production code is wrong and a failing test can prove the bug.
3. `frontend-ui-engineering` for UI implementation changes.
4. `test` for Playwright and focused validation.

### Planning-To-Build Handoff

1. `plan` creates the plan under `planning/` with checkable phases.
2. `context-engineering` packs the plan, relevant files, tests, docs, and examples for the implementation session.
3. The `build-feature` agent can implement the plan.
4. `merge` handles the post-implementation PR/merge stages.

## Adding More Skills

Add more skills only when they encode recurring project work. For one-off guidance, keep `AGENT.md` concise and avoid cluttering discovery.

## Anti-Patterns

| Anti-pattern | Why It Hurts |
| --- | --- |
| Starting implementation without checking skills | Skips repo-specific gates that prevent repeat mistakes. |
| Loading every skill every time | Burns context and dilutes the workflow. |
| Treating skills as suggestions | The value is in the sequence and gates, not just the prose. |
| Using a broad skill for a narrow task | Adds overhead and can encourage unrelated edits. |
| Adding skills for one-off preferences | Skills should capture repeated workflows, not clutter discovery. |

## Exit Criteria

Skill routing is complete when:
- [ ] The applicable skill or skill sequence is identified.
- [ ] Required skill files have been read before their workflow is used.
- [ ] The task proceeds under the smallest workflow that covers the risk.
- [ ] Any missing skill candidate is recorded only if it represents recurring project work.