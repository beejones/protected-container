---
name: documentation-and-adrs
description: "Use when: updating docs, recording architecture decisions, documenting deploy contracts, maintaining docs/deploy, README, planning files, agent guidance, env-schema behavior, hook contracts, or public deployment workflows."
---

# Documentation And ADRs Skill

## Principles

Documentation should explain why the deploy toolkit works this way, which contracts future changes must preserve, and how to validate them.

## When To Use

- Deploy behavior, env schema, Compose shape, hook contracts, GitHub Actions, Caddy, storage-manager, Azure, Ubuntu, or user workflows change.
- Updating `docs/deploy/`, `README.md`, planning files, analysis notes, AGENT.md, or skills.
- A durable architecture decision needs rationale.

## Procedure

1. Decide the doc type: module/deploy doc, planning update, analysis report, ADR-style note, README update, or agent guidance.
2. Capture context, decision, constraints, alternatives, consequences, and validation.
3. Keep docs non-duplicative. Update the canonical doc rather than adding another partial explanation.
4. Verify links, commands, file paths, env keys, and examples match code.

## ADR Template

```markdown
# Decision: <Name>

## Principles
<What this decision protects.>

## Context
<Constraints and problem.>

## Decision
<Chosen approach.>

## Alternatives Considered
- <Alternative>: <why rejected or deferred.>

## Consequences
- <Operational or maintenance impact.>

## Validation
- `<command or artifact>`
```

## Exit Criteria

- [ ] The canonical doc or decision artifact is updated.
- [ ] The why, constraints, and validation are captured.
- [ ] Duplicate or stale docs were checked.
- [ ] Links, commands, env keys, and examples are accurate.