# Cleanup Repo Instructions And Stale References

## Principles

- Repo instructions, planning files, and issue templates must describe this deployment toolkit, not inherited behavior from another codebase.
- `AGENT.md`, `AGENT_APP_SPECIFIC.md`, `.github/agents`, `.github/skills`, and planning/docs should tell one coherent story about Compose-driven deploys, env schema, hooks, shared Caddy routing, and Ubuntu/Azure targets.
- Cleanup should remove contradictory or misleading references while preserving useful historical planning context where it is still relevant.
- Validation for this cleanup is contract-focused: no stale cross-repo terminology should remain in the targeted files after the edit.

## Checkable Task Overview

- [ ] Phase 0: Audit stale copied references and define cleanup scope
- [ ] Phase 1: Rewrite top-level agent instructions for this repo
- [ ] Phase 2: Clean stale cross-repo references in planning and templates
- [ ] Phase 3: Validate cleanup and prepare merge

## Phase 0: Audit Cleanup Scope

Identify remaining copied references from the stock-dashboard repo and confirm whether each one is stale, historical, or intentionally generic.

Files expected to be reviewed:
- `AGENT.md`
- `planning/UBUNTU_SERVER_DEPLOYMENT.md`
- `planning/STORAGE_MANAGER.md`
- `.github/ISSUE_TEMPLATE/bug_report.md`

### Exit Criteria

- Target files are identified.
- Cleanup scope is limited to stale or misleading cross-repo references.
- Validation commands are chosen before editing.

## Phase 1: Rewrite Top-Level Instructions

Update `AGENT.md` so it matches this repo's actual structure and workflows.

Expected outcomes:
- Replace stock-dashboard project context with deployment-toolkit context.
- Remove references to nonexistent runners or UI folders.
- Keep the rules that still apply, especially env-secret handling, virtualenv usage, planning discipline, and deploy-centric validation.

### Exit Criteria

- `AGENT.md` reflects the current repo accurately.
- Top-level instructions do not contradict `AGENT_APP_SPECIFIC.md` or the current `.github/agents` / `.github/skills` files.

## Phase 2: Clean Planning And Template References

Update stale wording in planning files and issue templates without changing the underlying implementation history.

Expected outcomes:
- Remove stock-dashboard-specific references that no longer belong in this repo.
- Replace legacy comparisons with neutral or repo-specific wording.
- Keep valid upstream/downstream planning context where it still helps explain decisions.

### Exit Criteria

- Target planning files and template text no longer contain stale copied references.
- Historical intent is preserved where still relevant.

## Phase 3: Validate Cleanup And Prepare Merge

Validation commands:

```bash
rg -n "stock[- ]dashboard|STOCK_DASHBOARD|trade strategy|optimizer|watchlist|analyzer|trader|HistoricalDataStore|signal pipeline" AGENT.md .github planning docs tests scripts
```

Plus diagnostics checks on edited markdown files.

If cleanup is complete:
- commit the cleanup changes
- push the branch
- review merge readiness based on git state and validation results

### Exit Criteria

- The targeted stale-reference sweep returns no unexpected matches.
- Edited files have no diagnostics.
- Branch is ready for the merge step.