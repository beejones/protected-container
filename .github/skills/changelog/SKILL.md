---
name: changelog
description: "Use when: updating CHANGELOG.md, preparing the next APP_VERSION target for main-bound merges, turning PR reports into release notes, and documenting new capabilities, fixed bugs, and touched models."
---

# Changelog Workflow

## Purpose

Use this skill from the merge workflow before a PR is created, updated for final review, or merged into `main`. It turns the PR report into release notes, prepares the next app-version changelog entry, and records the models touched by the change.

In `_protected-container`, `/changelog` owns the target version entry in `CHANGELOG.md`; it does **not** bump `.env` before merge. The post-merge version-log command owns the actual `APP_VERSION` bump after the git ref has changed, then records that merged ref in `out/deploy/version_log.csv`. `ubuntu_deploy.py` only verifies and reuses the recorded version for deploys of the same git ref.

`CHANGELOG.md` is the correct conventional filename for release notes in this repo. Use the root `CHANGELOG.md` file. If it is empty, initialize it with:

```markdown
# Changelog

All notable changes to this project will be documented in this file.
```

## Preconditions

- A current PR report exists under `out/PR/Review_<branch_slug>.md`.
- The implementation and validation work is complete enough for merge preparation.
- Do not read `.env.secrets` or `.env.deploy.secrets`.
- Use the root `.env` only for `APP_VERSION`.
- Remember that `.env*` is ignored by default in this repo. Do not force-add `.env`; `/changelog` must leave `.env` unchanged so the post-merge version-log command can bump it exactly once after the git ref changes.

If the PR report is stale, regenerate it before writing release notes. If the version class or touched models are unclear, ask the user before editing the changelog.

## Version Target

Derive the target version from the current root `.env` exactly once per PR that will merge to `main`, but do not write the target version back to `.env` during `/changelog`.

- Default to a patch bump, for example `0.11.10` -> `0.11.11`.
- Use a minor bump for a substantial new user-facing capability or API expansion.
- Use a major bump only for intentional breaking behavior or migration requirements.
- If `APP_VERSION` is missing, duplicated, or not valid `x.y.z` semver, stop and report the blocker.
- If the branch already contains a changelog entry for the same PR, update the existing entry instead of choosing another version.
- If the branch is rebased or updated from `main` and another merge consumed the target version, bump to the next available version and update the changelog heading.
- The target version must be the version that `python scripts/deploy/deploy_log.py --record-merge` will write after merge.

Verify the local pre-merge baseline after editing release notes. This value should still be the previous version:

```bash
grep '^APP_VERSION=' .env
```

## Changelog Entry

Add the new entry near the top of root `CHANGELOG.md`, below the title and optional introductory sentence. Use the bumped version and current date:

```markdown
## [0.11.11] - 2026-06-09

Pull Request: [#123](https://github.com/owner/repo/pull/123)

### New Capabilities

- ...

### Fixed Bugs

- ...

### Touched Models

- ...
```

Include the `Pull Request` line only when `gh pr view` or the PR report provides a real PR URL. If no PR exists yet, omit the line rather than adding a placeholder. Use `- None.` under a section only when there truly are no items. Do not omit the `Touched Models` section.

## Summary Rules

Use the PR report as the primary source. Use commits and diffs only to verify accuracy or fill in missing release-note facts.

- Focus on new capabilities, fixed bugs, behavior changes, operational improvements, and user-visible workflow changes.
- Do not list changed files, paths, or module-by-module implementation details.
- Keep bullets concise and understandable to someone reading release notes, not reviewing a diff.
- Do not invent user impact. If the change is internal, say what operational or maintenance capability it improves.
- Mention touched models explicitly. Count these as models when applicable:
  - dataclasses, typed domain models, protocols, enums, or state-machine models
  - API request/response payload models or JSON schemas
  - persisted config schemas, strategy model IDs, trade params, or analyzer/optimizer result models
  - external AI, ML, or provider model names if the change intentionally modified them
- If no models were touched, write `- None.` in `Touched Models`.

## Procedure

1. Read the current PR report and extract the release-note facts.
2. Identify the version bump class: patch, minor, or major.
3. Identify touched models from the PR report; if the report does not say, inspect the diff enough to answer accurately without turning the changelog into a file list.
4. Resolve the PR URL if available, preferring the PR report and then `gh pr view --json number,url` for the current branch. If no PR exists yet, continue without a PR line.
5. Leave root `.env` `APP_VERSION` unchanged.
6. Update root `CHANGELOG.md` with the new version entry.
7. Review the changelog entry for these gates:
   - It has `New Capabilities`, `Fixed Bugs`, and `Touched Models` sections.
  - It includes a `Pull Request` link when a real PR URL is available, and omits the line when no PR exists yet.
   - It contains no changed-file list or path-driven summary.
   - It names touched models or explicitly says `None.`.
   - It matches the PR report and does not overclaim.
8. If `CHANGELOG.md` was previously untracked, include it in the merge branch. Do not force-add `.env` if it remains ignored.
9. Update or regenerate the PR report if the release-note status, version, PR link, or changelog entry changed after the report was created.

## Exit Criteria

The changelog step is complete when:

- Root `.env` still has the previous valid `APP_VERSION` baseline; the target bump is reserved for the post-merge version-log command.
- Root `CHANGELOG.md` has a versioned entry dated with the merge preparation date.
- The changelog entry includes a PR link when one is available.
- The entry summarizes capabilities and fixes, not changed files.
- Touched models are named, or the entry states `None.`.
- The PR report reflects the version and changelog status.