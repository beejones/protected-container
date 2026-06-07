---
name: plan
description: "Use when: invoking /plan, creating or updating planning files, decomposing a feature/spec into small verifiable tasks, estimating implementation scope, ordering dependencies, or preparing work for the build-feature workflow. Produces repo-ready plans under planning/."
---

# Plan Skill

## Principles

Planning turns a fuzzy request into small, ordered, verifiable work. The output is a written plan that survives context compaction, exposes hidden dependencies, and gives the user a concrete artifact to review before implementation.

Use this skill to produce plans that match this repository's expectations:
- Planning files live in `planning/` unless the user explicitly asks for a chat-only plan.
- Every plan has a checkable task overview and clear phase exit criteria.
- Phase 0 is always cleanup and follows `.github/skills/code-cleanup/SKILL.md`.
- Python implementation phases must honor `.github/skills/typed-code-generation/SKILL.md`.
- UI plans include a concise mockup or layout sketch for the intended design.
- Completed plans move to `archive/planning/` with an `_ARCHIVED` suffix.

## When To Use

- The user invokes `/plan` or asks for a planning file.
- A feature, refactor, cleanup, migration, or investigation needs more than one implementation step.
- Requirements are clear enough to break into tasks, but implementation order is not obvious.
- The work touches multiple files, modules, APIs, UI surfaces, data flows, or validation gates.
- The user needs an implementation artifact before starting `build-feature`.

## When Not To Use

- A single-file change has obvious scope and no meaningful dependency ordering.
- The user is asking only for brainstorming, a quick explanation, or a code review.
- A bug fix is already identified and should follow `.github/skills/bug-fix/SKILL.md` directly.
- Requirements are too ambiguous to plan. Ask the minimum blocking questions first.

## Procedure

### Step 1 - Enter Planning Mode

Stay read-only while planning. Do not implement code in the same pass unless the user explicitly pivots from planning to implementation.

Gather only the context needed to make a credible plan:
- Read `AGENT.md` and `.github/copilot-instructions.md` if not already loaded.
- Read the relevant source, tests, docs, config, and existing planning files.
- Identify local patterns, ownership boundaries, canonical helpers, and validation commands.
- Note unresolved requirements as assumptions or open questions.

### Step 2 - Define Scope

Write a short scope statement before tasking:
- Goal: what will be true when the plan is complete.
- Non-goals: what the plan intentionally excludes.
- User-facing behavior: what changes for the operator or application user.
- Affected modules: likely source, tests, docs, config, and UI surfaces.

If the scope is still unclear, ask only the questions that would change task order, file ownership, or acceptance criteria.

### Step 3 - Map Dependencies

Order work by dependency, not by file type. Build foundations first, then one usable vertical slice at a time.

For this repo, check whether the request touches any of these common chains:
- Config/schema -> typed boundary model -> engine/service logic -> API route -> UI -> tests/docs.
- Data source adapter -> `DataManager` fan-out -> analyzer/trading consumer -> UI/API response safety.
- Strategy JSON -> trade params JSON -> signal generation request -> engine evaluation -> analyzer/optimizer validation.
- Backend route -> Socket.IO/streaming update -> frontend state -> UI test.

Call out safe parallel work only when contracts are already stable. Shared schema, persistence, and API contracts should be sequenced before dependent tasks.

### Step 4 - Slice Into Small Tasks

Prefer small or medium tasks that can be completed and verified in one focused session.

Task sizing guide:

| Size | Files | Use |
| --- | --- | --- |
| XS | 1 | One helper, config field, or doc correction |
| S | 1-2 | One endpoint, component, parser, or test target |
| M | 3-5 | One complete vertical slice |
| L | 6-8 | Split if possible; requires a checkpoint |
| XL | 9+ | Too large; break it down |

Break a task down when:
- The title contains "and" between independent outcomes.
- Acceptance criteria need more than three bullets.
- It touches unrelated subsystems.
- It cannot be verified without several later tasks.

### Step 5 - Write The Planning File

Create or update `planning/<short-descriptive-name>.md`. Use kebab-case or the repo's existing plan naming pattern.

Use this structure unless an existing plan template nearby is more specific:

```markdown
# Plan: <Feature Or Change Name>

## Overview
<One paragraph describing the goal and expected outcome.>

## Scope
- Goal: <what will be true when done>
- Non-goals: <explicit exclusions>
- Affected areas: <modules, APIs, UI, config, docs>

## Current Context
- <Relevant existing behavior and constraints discovered from the codebase.>
- <Canonical helpers or patterns to reuse.>

## Architecture Decisions
- <Decision and rationale.>

## Task Overview
- [ ] Phase 0: Cleanup and documentation audit
- [ ] Phase 1: <foundation or first vertical slice>
- [ ] Phase 2: <next vertical slice>
- [ ] Phase 3: Validation and handoff

## Phase 0 - Cleanup And Documentation Audit

Follow `.github/skills/code-cleanup/SKILL.md` for the touched module.

### Tasks
- [ ] Audit target files for dead code, duplication, oversized modules, and existing helpers to reuse.
- [ ] Review `docs/<module>/` for missing, duplicate, or stale docs related to this change.
- [ ] Identify focused tests that should guard the existing behavior before implementation.

### Exit Criteria
- [ ] Cleanup findings are resolved or recorded as explicit follow-ups.
- [ ] Relevant docs are accurate or scheduled in a later phase.
- [ ] Baseline validation target is known.

## Phase 1 - <Name>

### Tasks
- [ ] <Task with one clear outcome.>

### Acceptance Criteria
- [ ] <Specific observable behavior.>

### Verification
- [ ] `<focused command>`

### Files Likely Touched
- `<path>`

### Exit Criteria
- [ ] <Phase-specific completion gate.>

## UI Mockup

<Required for UI plans. Use a compact text wireframe, route/layout notes, and states.>

## Risks And Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| <risk> | <High/Medium/Low> | <response> |

## Validation Plan
- Focused: `<command>`
- Full suite, when warranted: `source .venv/bin/activate && python scripts/run_tests.py`
- Manual/UI check: <what to verify>

## Open Questions
- <Question or "None".>
```

### Step 6 - Add Checkpoints

Every plan needs checkpoints between major phases. A checkpoint should prove the repository is still in a working state before the next phase starts.

Good checkpoints include:
- Focused pytest selectors for backend logic.
- UI tests under `tests/UI/` when templates, CSS, or JavaScript change.
- Analyzer/optimizer replay commands when strategy behavior changes.
- Full `scripts/run_tests.py` when shared behavior or broad user workflows change.
- Manual browser verification when a UI change cannot be fully asserted by tests.

### Step 7 - Quality Gate

Before handing off the plan, verify:
- Every task has acceptance criteria.
- Every phase has exit criteria.
- Verification commands are concrete and repo-correct.
- Phase 0 cleanup is present.
- UI work includes a mockup or layout sketch.
- Python work references typed-code-generation obligations.
- No task is XL-sized.
- Dependencies are ordered so the system remains usable between phases.
- Open questions are real blockers, not placeholders.

## Common Rationalizations

| Rationalization | Reality |
| --- | --- |
| "The task is obvious." | If it spans multiple files, hidden dependencies are likely. Write them down. |
| "I can plan while coding." | Planning and implementation optimize for different kinds of attention. Produce the artifact first. |
| "Cleanup can happen later." | This repo requires Phase 0 cleanup so new work does not build on stale or duplicated code. |
| "Tests are an implementation detail." | Verification is part of the plan. A task without proof is not ready to build. |
| "The plan can be broad." | Broad plans become broad diffs. Slice into work the agent can complete and validate. |

## Red Flags

- A plan starts implementation or edits production code during planning.
- The task overview is not checkable.
- Phase 0 cleanup is missing.
- Acceptance criteria describe activities instead of observable outcomes.
- Verification says only "run tests" without concrete commands or selectors.
- UI work has no mockup, states, or responsive notes.
- A task touches unrelated modules without a dependency reason.
- Open questions would change the architecture but are not surfaced to the user.

## Exit Criteria

The `/plan` skill is complete when:
- [ ] A plan exists in `planning/` or the user explicitly requested a chat-only plan.
- [ ] The plan has a checkable task overview and phase exit criteria.
- [ ] The plan is ordered by dependencies and vertical slices.
- [ ] Phase 0 cleanup and docs audit are included.
- [ ] Verification is specific enough for a later agent to run without rediscovering commands.
- [ ] Risks, mitigations, and open questions are documented.