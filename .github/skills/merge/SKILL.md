---
name: merge
description: "Use when: generating PR reports with or without a planning file, skipping plan requirements for no-plan merges, preparing changelog/version release notes, pausing for review, creating or updating pull requests, handling Copilot or reviewer feedback, watching CI, checking mergeability, merging PRs, and cleaning up branches after implementation and validation."
---

# Merge Workflow

## Principles

The merge workflow can run independently or as part of any planned workflow. It begins only after implementation, validation, and any applicable plan updates are complete. This guards against:
- Opening PRs with unverified work.
- Losing review evidence in local-only notes.
- Treating green CI as sufficient when GitHub still reports conflicts or blocked merge state.
- Merging while Copilot or human review comments remain unresolved.
- Landing main-bound changes without an `APP_VERSION` bump and changelog entry.
- Leaving branches, PR reports, or local state messy after merge.

## When To Use

- PR/report/merge work after validated implementation work.
- Any plan-driven workflow, regardless of plan structure or phase naming.
- Standalone PR/report/merge work where the user explicitly skipped planning or no planning file exists.
- Creating or updating a PR from an existing feature branch.
- Preparing release notes and version bumps for changes that will merge to `main`.
- Every `_protected-container` merge to `main` must run `/changelog` before final PR review or merge, even for deploy-only or documentation-heavy changes.
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

- In No-Plan / Skipped-Plan Mode, do not fail solely because prior workflow phases or a planning file are absent.
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
   - release-note summary covering new capabilities, fixed bugs, and touched models without changed-file details
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

### Update Changelog And Version

**Goal**: prepare the release-note artifacts that accompany a merge to `main`.

1. Load and follow `.github/skills/changelog/SKILL.md` before creating or updating the PR for final review. For `_protected-container`, this step is mandatory for every merge to `main`; do not proceed to PR final review, readiness, or merge until protected `CHANGELOG.md` contains the target version entry required by the deploy version preflight.
2. Use the PR report as the primary source. The changelog entry must summarize new capabilities and fixed bugs, mention touched models, and avoid changed-file details.
3. Follow the protected changelog skill's version-target rule. For deploy-managed `_protected-container` releases, do not pre-bump root `.env`; `ubuntu_deploy.py` writes the target `APP_VERSION` after the first successful deploy of the new git ref. Because `.env*` is ignored by default in this repo, do not force-add `.env`.
4. Update root `CHANGELOG.md`; add it to the branch if this is the first tracked changelog entry.
5. Update or regenerate the PR report if the version, changelog entry, or release-note status changed after the report was generated.
6. If the version class, release-note summary, or touched models are unclear, pause and ask the user before continuing.

### Create PR, Review, CI, And Merge

**Goal**: create the PR, address review, prove CI and mergeability, then merge.

1. Confirm the changelog/version step is complete or explicitly not applicable. If `CHANGELOG.md` changed, it must be included in the branch. If `.env` is ignored, verify `APP_VERSION` directly instead of expecting `git status` to show it.

2. Verify the working tree is clean:

```bash
git status --short
```

If anything is listed, commit intended changes or stop for user guidance. Do not discard user work.

3. Push all branch commits:

```bash
git push
```

4. Create the PR as a draft using the PR report as the body:

```bash
gh pr create --draft --title "feat: <title>" --body-file out/PR/Review_<branch_slug>.md
```

If a PR already exists, update the PR body or add the report as a PR comment immediately.

5. Verify the PR exists and includes the report:

```bash
gh pr view --json number,url,title,isDraft --jq '"PR #\(.number): \(.url) [draft=\(.isDraft)]"'
```

6. Draft review: check Copilot and human review feedback available on the draft PR. Address every actionable comment with a code, doc, test, or report change, or explain clearly why no change is needed. If the Copilot feedback was not requested, request it explicitly in the PR comments and wait for it.
7. Draft-review fixes: commit and push any review fixes. In repos that gate CI for draft PRs, these pushes should remain quiet while the PR stays draft. If review fixes change release-note content, rerun the changelog skill and update the PR report before moving to CI.
8. Draft-review pause: if the user has **not** yet approved moving from draft review to CI, stop here and report the PR URL, whether the PR body contains the current review report, draft review feedback status, validation results, changelog/version status, plan status or no-plan reason, and any residual risks.
9. CI start: if the user **has** already approved moving from draft review to CI, mark the PR ready immediately. Once that approval has been granted, do not introduce another pause just because review-fix commits were pushed or CI later turns green:

```bash
gh pr ready
```

10. CI validation: watch CI until it finishes, then continue directly to mergeability verification and merge unless GitHub reports a blocking condition or the user explicitly asked to hold before merge:

```bash
gh pr checks --watch
```

11. CI repair loop: if CI fails, read the failing logs, diagnose locally, fix, commit, push, and repeat the CI check. If the fix changes release-note content, rerun the changelog skill before repeating CI.
12. Merge approval gate: verify GitHub reports the PR as cleanly mergeable. Green CI alone is not enough:

```bash
gh pr view --json mergeStateStatus,mergeable,reviewDecision,statusCheckRollup,isDraft
```

Do not merge if the PR is draft, dirty, conflicting, blocked, has required checks pending, or has unresolved required review state.

13. Mergeability repair: if the PR is not mergeable, update from the base branch, resolve conflicts, rerun relevant validation, rerun the changelog skill if the version or release notes are affected, push, and wait for CI again.
14. Merge execution: merge immediately when CI passes and GitHub reports a clean merge state. Do not ask for another approval merely because review-fix commits were pushed or because CI just completed:

```bash
gh pr merge --squash --delete-branch
```

15. Local cleanup: clean up local state:

```bash
current_branch="$(git branch --show-current)"
git checkout main && git pull
git branch -D "$current_branch"
```

16. Remove the local PR report from `out/PR/` after merge unless the repo workflow explicitly keeps PR reports.

## Parallel Work Rule

While CI or review is running, do not idle if there is safe independent work to do. You may inspect logs, prepare fixes, update the merge checklist, or review artifacts. Do not make code or config changes that would invalidate a currently running validation result.

## Exit Criteria

PR report preparation is complete when:
- The PR report exists under `out/PR/`.
- The report includes diff, commits, validation evidence, plan status, risks, and checklist.
- The report includes a release-note summary with new capabilities, fixed bugs, and touched models.
- If there is no planning file, the report explicitly says planning was skipped or not applicable and why.
- The user has reviewed the report or explicitly skipped the pause.

Merge completion is done when:
- The PR contains the report in its body or comments.
- Review feedback is addressed or explicitly resolved.
- `APP_VERSION` has been bumped for the main-bound merge, and root `CHANGELOG.md` has the matching entry.
- Required checks pass.
- GitHub reports the PR is mergeable with no blocking state.
- The PR is merged.
- Local branch and report cleanup are complete or intentionally deferred with a note.
