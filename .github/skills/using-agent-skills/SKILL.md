---
name: using-agent-skills
description: "Use when: starting a session, deciding which deploy-toolkit skill applies, routing ambiguous work, chaining multiple skills, or updating AGENT.md skill awareness. Meta-skill for local skill discovery and workflow selection."
---

# Using Agent Skills

## Purpose

This is the local skill router for Protected Container. Use it to choose the smallest applicable workflow before starting non-trivial work.

`AGENT.md` stays the compact always-on index. This skill holds fuller routing rules so agents load them only when needed.

## Core Rules

- Check for an applicable skill before planning, coding, reviewing, merging, or changing deploy contracts.
- Load only the skills that apply.
- Skills are workflows with gates; follow their steps and verification requirements.
- Multiple skills can apply in sequence. State the sequence when it matters.
- If requirements are ambiguous enough to change deploy behavior, file ownership, or compatibility, ask the minimum blocking question.
- Verification is part of completion. Do not finish with "looks right" when a command, test, compose check, or browser check is available.

## Local Skill Map

| Situation | Skill |
| --- | --- |
| Need to decide which skill applies | `using-agent-skills` |
| Starting a session, switching deploy surfaces, refreshing stale context, or packing files/tests/docs/examples | `context-engineering` |
| User invokes `/plan`, asks for a planning file, or needs task breakdown | `plan` |
| Phase 0 cleanup, module cleanup, dead code, duplication, oversized files | `module-cleanup` |
| Writing or modifying Python production/test code | `typed-code-generation` |
| Bug, regression, exception, failing test rooted in production code | `bug-fix` |
| Need focused validation, pytest, compose checks, deploy help checks, or CI evidence | `test` |
| Deployment readiness before Ubuntu/Azure/local deploy or after contract changes | `deploy-readiness-check` |
| Rolling out deploy-contract changes across code, docs, examples, workflows, or templates | `deploy-rollout-adoption` |
| Working code needs behavior-preserving readability/refactor pass | `code-simplify` |
| Reviewing a change before merge or evaluating agent/human code | `review` |
| Designing CLI args, env schema, hook contracts, compose labels, APIs, or module boundaries | `api-interface-design` |
| Building or changing browser-facing flows, docs-visible UI, or deployment UI checks | `frontend-ui-engineering` |
| Need browser runtime evidence: DOM, console, network, screenshots, accessibility, or performance traces | `browser-testing-with-devtools` |
| Touching secrets, env files, auth, external services, GitHub Actions secrets, or deploy-sensitive behavior | `security-hardening` |
| Investigating or improving deploy, Docker, validation, API, browser, or test performance | `performance-optimization` |
| Updating docs, writing rationale, changing public contracts, or capturing architecture decisions | `documentation-and-adrs` |
| Implementing framework/library/tool behavior that must match official docs | `source-driven-development` |
| PR report, reviewer feedback, CI watch, mergeability, merge, branch cleanup | `merge` |

## Common Skill Sequences

### New Feature Or Broad Change

1. `plan` to create or update the planning artifact.
2. `context-engineering` to load the relevant plan section, source files, tests, docs, and one local pattern example.
3. `module-cleanup` for Phase 0 cleanup.
4. `typed-code-generation` before Python edits.
5. `api-interface-design`, `security-hardening`, `source-driven-development`, or `frontend-ui-engineering` when the feature touches those concerns.
6. `test` for focused and broad validation evidence.
7. `deploy-readiness-check` when deploy contracts or target prerequisites changed.
8. `code-simplify` after behavior works and tests pass, if the diff is harder to read than it should be.
9. `documentation-and-adrs` for changed docs, public contracts, or durable decisions.
10. `review` before merge.
11. `merge` for PR/report/CI/merge work.

### Bug Fix

1. `bug-fix` for hypothesis, failing test gate, minimal fix, and verification.
2. `context-engineering` when the failing path spans unfamiliar files or stale assumptions.
3. `typed-code-generation` if Python production or test code changes.
4. `test` for focused regression and broader validation planning.
5. `deploy-readiness-check` when the fix affects deploy commands, compose, or env schema.
6. `review` before merge when the fix is non-trivial.

### Deploy Contract Change

1. `api-interface-design` to define env schema, CLI, hook, compose label, or service contracts.
2. `security-hardening` for env/secrets/auth/external-service impact.
3. `deploy-readiness-check` for local contract validation.
4. `deploy-rollout-adoption` for final rollout/adoption decisions.
5. `documentation-and-adrs` for public behavior or durable rationale.
6. `review` and `merge` for final handoff.

### Browser-Facing Or UI Issue

1. `frontend-ui-engineering` for UI design and implementation quality.
2. `browser-testing-with-devtools` for runtime console, network, screenshot, accessibility, and layout evidence.
3. `test` for repeatable Playwright or focused validation where available.

## Adding More Skills

Add another local skill only when it captures recurring work with clear gates, red flags, and verification. For one-off guidance, keep `AGENT.md` concise.

## Exit Criteria

Skill routing is complete when:
- [ ] The applicable skill or skill sequence is identified.
- [ ] Required skill files have been read before their workflow is used.
- [ ] The task proceeds under the smallest workflow that covers the risk.
- [ ] Missing skill candidates are recorded only if they represent recurring project work.