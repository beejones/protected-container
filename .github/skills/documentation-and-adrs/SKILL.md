---
name: documentation-and-adrs
description: "Use when: updating docs, writing ADR-style rationale, changing public APIs or strategy contracts, documenting module principles, explaining architecture decisions, maintaining AGENT.md instructions, or recording user-facing behavior changes."
---

# Documentation And ADRs Skill

## Principles

Document the why, the contract, and the operating rules. Code shows what exists; docs should explain the constraints future humans and agents must preserve.

Repo rule: when modifying a module, review the corresponding `docs/<module>/` area for missing, duplicate, stale, or broken documentation. Each major doc should start with a principles section.

## When To Use

- Changing public API behavior, strategy JSON contracts, data-source behavior, analyzer/optimizer workflows, or deployment behavior.
- Adding or modifying docs under `docs/`, `planning/`, `analysis/`, or `AGENT.md`.
- Making a durable architecture decision or rejecting meaningful alternatives.
- Repeating the same explanation in chat or code review.
- Updating custom skills, instructions, agents, or workflow guidance.

## Documentation Types

### Module Docs

Use for durable behavior and operating principles. Put them under `docs/<module>/` when the module has a docs area.

Include:
- Principles guarded by the code.
- Public workflows or contracts.
- Important boundaries and data flow.
- Validation commands or evidence requirements.
- Links to related docs without duplication.

### Planning Files

Use `planning/` for active implementation plans. Completed plans move to `archive/planning/` with an `_ARCHIVED` suffix.

### Analysis Reports

Use `analysis/` for evidence-heavy investigation, optimizer/analyzer validation, or strategy adoption reasoning that should persist.

### ADR-Style Notes

Use ADR-style sections when a decision is expensive to reverse:
- Status.
- Date.
- Context.
- Decision.
- Alternatives considered.
- Consequences.

This repo does not require a separate ADR system before writing useful rationale. Prefer a small durable note in the most relevant docs location.

## Procedure

### Step 1 - Identify Documentation Impact

Ask:
- Did behavior, workflow, setup, API shape, strategy contract, or validation change?
- Would a future agent need this context to avoid re-deciding or breaking it?
- Is there an existing doc that should be updated instead of creating a new one?

### Step 2 - Update The Right Artifact

- Module behavior -> `docs/<module>/`.
- Active work breakdown -> `planning/`.
- Evidence or decision report -> `analysis/`.
- Agent operating rule -> `AGENT.md` or `.github/skills/<name>/SKILL.md`.
- User-facing README/setup behavior -> `README.md` or relevant setup docs.

Avoid duplicate docs. Prefer updating the canonical doc and linking to it.

### Step 3 - Write Useful Content

- Start major docs with principles.
- Explain why, not just what.
- Include constraints and rejected alternatives when they matter.
- Include exact commands for validation when future users need them.
- Use concise examples only when they prevent ambiguity.
- Remove stale or commented-out content instead of preserving it.

### Step 4 - Validate Docs

Check links, command accuracy, file paths, and consistency with code. If docs mention tests or scripts, ensure commands match repo conventions.

## Red Flags

- New public behavior with no docs update.
- Docs that duplicate another file and will drift.
- Comments explaining obvious code instead of intent.
- TODOs left where a small fix would solve the issue.
- Planning files left active after all tasks are complete.
- Strategy or API contract changes described only in chat.
- AGENT.md grows with detailed workflow content that belongs in a skill.

## Exit Criteria

- [ ] Relevant docs were reviewed for the changed module.
- [ ] New or changed behavior is documented in the canonical location.
- [ ] Duplicates, stale statements, and broken links were fixed or reported.
- [ ] Durable decisions include rationale and consequences.
- [ ] Validation commands in docs are accurate.