---
name: merge
description: "Use when: generating PR reports with or without a planning file, skipping plan requirements for no-plan merges, pausing for review, creating or updating pull requests, handling Copilot or reviewer feedback, watching CI, checking mergeability, merging PRs, and cleaning up branches after implementation and validation."
---

# Merge Workflow

## Principles

The merge workflow can run independently or as part of any planned workflow. It begins only after implementation, validation, and any applicable plan updates are complete. This guards against:
- Opening PRs with unverified work.
- Losing review evidence in local-only notes.
- Treating green CI as sufficient when GitHub still reports conflicts or blocked merge state.
- Merging while Copilot or human review comments remain unresolved.
- Leaving branches, PR reports, or local state messy after merge.

## When To Use

- PR/report/merge work after validated implementation work.
- Any plan-driven workflow, regardless of plan structure or phase naming.
- Standalone PR/report/merge work where the user explicitly skipped planning or no planning file exists.
- Creating or updating a PR from an existing feature branch.
- Handling Copilot review comments, human review comments, CI failures, mergeability checks, and squash merge cleanup.

## Preconditions

Before starting the merge workflow, verify all of the following:
- You are on a feature branch, not `main`.
- If no planning file exists or planning was explicitly skipped, record the no-plan/skipped-plan reason in the PR report instead of inventing a plan after the fact.
- If a planning file exists, it is updated or archived according to the workflow that invoked this skill.
- Required validation for the changed behavior has passed, including API and browser checks when applicable.
- There are no unresolved local decisions about scope, validation failures, or plan status.
- Do not read `.env.secrets` or `.env.deploy.secrets`.
- Run repo scripts inside the virtual environment: `source .venv/bin/activate && ...`.

If any precondition is false, stop and report what must be completed before this skill can continue.

## No-Plan / Skipped-Plan Mode

Use this mode when the user explicitly asks to merge without a plan, asks to skip planning, or there is no planning file for the branch.

- Do not fail solely because prior workflow phases or a planning file are absent.
- Do not create a retrospective planning file just to satisfy the merge workflow.
- Still require a feature branch, a reviewed diff, validation evidence or a documented validation gap, and a PR report.
- The PR report must include a `Plan Status` or equivalent section that states `No plan / planning skipped` and explains why.
- If the branch contains broad or risky changes and no validation evidence, stop and ask for the missing validation before PR creation.

## Procedure

### Generate PR Report

**Goal**: self-review the changes and produce a PR report. Do not create the PR yet.

1. Review branch state and diff against `main`:

```bash
git status --short
git --no-pager diff main..HEAD --stat
git --no-pager diff main..HEAD
git --no-pager log --oneline main..HEAD
```

2. Create `out/PR/Review_<branch_slug>.md` using the active repo standards.
3. Include:
   - problem statement or feature goal
   - root cause when the change fixes a bug
   - summary table of changed files
   - commit list
   - test results and regression status
   - API validation evidence for HTTP or JSON behavior
   - browser validation evidence for user-visible behavior
   - plan status, including whether the plan was archived, what remains, or why this merge is intentionally no-plan/skipped-plan
   - review checklist covering scope, typing, cleanup, docs, tests, and risk
4. Keep the report local for user review. Do not create a PR and do not push the report as a repo artifact unless the invoking workflow explicitly requires it.
5. If the report exposes missing validation, missing docs, or unresolved scope, return to the appropriate implementation or validation workflow, fix it, and regenerate the PR report.

### Pause For User Review

**Goal**: let the user inspect the PR report and changes before PR creation.

1. Stop here by default unless the user explicitly said `no pause`, `run the whole process`, or equivalent.
2. Report:
   - the PR report path
   - commits included in the branch
   - validation results
   - plan status, or the no-plan/skipped-plan reason
   - any residual risks
3. If changes are requested, return to implementation or validation as needed, then regenerate the report before proceeding.

### Create PR, Review, CI, And Merge

**Goal**: create the PR, address review, prove CI and mergeability, then merge.

1. Verify the working tree is clean:

```bash
git status --short
```

If anything is listed, commit intended changes or stop for user guidance. Do not discard user work.

2. Push all branch commits:

```bash
git push
```

3. Create the PR as a draft using the PR report as the body:

```bash
gh pr create --draft --title "feat: <title>" --body-file out/PR/Review_<branch_slug>.md
```

If a PR already exists, update the PR body or add the report as a PR comment immediately.

4. Verify the PR exists and includes the report:

```bash
gh pr view --json number,url,title,isDraft --jq '"PR #\(.number): \(.url) [draft=\(.isDraft)]"'
```

5. Check Copilot and human review feedback. Address every actionable comment with a code, doc, test, or report change, or explain clearly why no change is needed.
6. Commit and push review fixes. This push is what should trigger a meaningful CI run.
7. Mark the PR ready only after review feedback has been addressed:

```bash
gh pr ready
```

8. Watch CI until it finishes:

```bash
gh pr checks --watch
```

9. If CI fails, read the failing logs, diagnose locally, fix, commit, push, and repeat the CI check.
10. Verify GitHub reports the PR as cleanly mergeable. Green CI alone is not enough:

```bash
gh pr view --json mergeStateStatus,mergeable,reviewDecision,statusCheckRollup,isDraft
```

Do not merge if the PR is draft, dirty, conflicting, blocked, has required checks pending, or has unresolved required review state.

11. If the PR is not mergeable, update from the base branch, resolve conflicts, rerun relevant validation, push, and wait for CI again.
12. Merge only when CI passes and GitHub reports a clean merge state:

```bash
gh pr merge --squash --delete-branch
```

13. Clean up local state:

```bash
git checkout main && git pull
git branch -D feat/<descriptive-slug>
```

14. Remove the local PR report from `out/PR/` after merge unless the repo workflow explicitly keeps PR reports.

## Parallel Work Rule

While CI or review is running, do not idle if there is safe independent work to do. You may inspect logs, prepare fixes, update the merge checklist, or review artifacts. Do not make code or config changes that would invalidate a currently running validation result.

## Exit Criteria

PR report preparation is complete when:
- The PR report exists under `out/PR/`.
- The report includes diff, commits, validation evidence, plan status, risks, and checklist.
- If there is no planning file, the report explicitly says planning was skipped or not applicable and why.
- The user has reviewed the report or explicitly skipped the pause.

Merge completion is done when:
- The PR contains the report in its body or comments.
- Review feedback is addressed or explicitly resolved.
- Required checks pass.
- GitHub reports the PR is mergeable with no blocking state.
- The PR is merged.
- Local branch and report cleanup are complete or intentionally deferred with a note.
