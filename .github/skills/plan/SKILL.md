---
name: plan
description: "Use when: invoking /plan, creating or updating planning files, decomposing deploy-toolkit work into verifiable tasks, estimating scope, ordering dependencies, or preparing work for implementation. Produces repo-ready plans under planning/."
---

# Plan Skill

## Principles

Planning turns a fuzzy deploy change into small, ordered, verifiable work. The output is a written artifact that survives context loss and lets humans review scope before implementation.

Repo expectations:
- Planning files live in `planning/` unless the user asks for chat-only planning.
- Every plan has a checkable task overview and phase exit criteria.
- Phase 0 is cleanup and docs audit, following `module-cleanup` where relevant.
- Python phases must honor `typed-code-generation`.
- Deploy-contract plans include validation commands for env schema, Compose, CLI help, docs, and tests.

## When To Use

- The user invokes `/plan` or asks for a planning file.
- A deploy feature, refactor, migration, or investigation spans multiple steps.
- Work touches deploy scripts, Compose, env schema, docs, tests, workflows, or examples.

## Procedure

### Step 1 - Stay Read-Only

Read the relevant request, docs, code, tests, env examples, and existing plans. Do not implement in the planning pass unless the user explicitly pivots.

### Step 2 - Define Scope

State goal, non-goals, affected deploy surfaces, compatibility expectations, and likely validation.

### Step 3 - Map Dependencies

Common dependency chains:
- Env schema -> example env files -> deploy script validation -> docs -> tests.
- Compose service shape -> deploy renderer -> Ubuntu/Azure behavior -> readiness checks.
- Hook contract -> downstream customizations -> docs/examples -> tests.
- GitHub Actions helper -> secrets/vars sync -> workflow docs -> CI validation.

### Step 4 - Slice Into Small Tasks

Prefer tasks that touch one deploy surface or one vertical contract slice. Split tasks that combine independent changes with "and".

### Step 5 - Write The Plan

Use `planning/<short-name>.md` with:
- Overview.
- Scope and non-goals.
- Current context.
- Architecture decisions.
- Checkable task overview.
- Phase 0 cleanup/docs audit.
- Phase tasks, acceptance criteria, verification, likely files, and exit criteria.
- Risks and mitigations.
- Open questions.

### Step 6 - Quality Gate

Before handoff, verify every phase has exit criteria and concrete commands such as focused pytest, `validate_env.py`, deploy command `--help`, `docker compose ... config`, or docs checks.

## Exit Criteria

- [ ] A plan exists in `planning/` or the user explicitly requested chat-only output.
- [ ] The task overview and phase exit criteria are checkable.
- [ ] Dependencies are ordered so contracts stay coherent.
- [ ] Phase 0 cleanup/docs audit is included.
- [ ] Validation commands are concrete and repo-correct.