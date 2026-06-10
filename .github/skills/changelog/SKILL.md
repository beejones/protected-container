---
name: changelog
description: "Use when: updating CHANGELOG.md, preparing the next APP_VERSION target for main-bound merges, turning PR reports into release notes, adding Git commit links, and documenting new capabilities, fixed bugs, and touched models."
---

# Changelog Workflow

## Purpose

Use this skill from the merge workflow before a PR is created, updated for final review, or merged into `main`. It turns the PR report into release notes, records the latest git ref for traceability, and records the models touched by the change.

In `_protected-container`, `/changelog` owns release-note quality in `CHANGELOG.md`; deploy/version logging owns `out/deploy/version_log.csv`. `ubuntu_deploy.py` records the current git ref with the current `APP_VERSION`, reuses the recorded version for repeat deploys of the same git ref, and does not create or validate changelog entries.

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
- Remember that `.env*` is ignored by default in this repo. Do not force-add `.env`; if a version bump is needed, make it an explicit local versioning decision rather than inferring it from `version_log.csv` or `CHANGELOG.md`.

If the PR report is stale, regenerate it before writing release notes. If the version class, latest git ref, GitHub commit URL, or touched models are unclear, ask the user before editing the changelog.

## Version Target

Use the current root `.env` `APP_VERSION` as the changelog version unless the user explicitly asks for a version bump.

- Default to a patch bump, for example `0.11.10` -> `0.11.11`.
- Use a minor bump for a substantial new user-facing capability or API expansion.
- Use a major bump only for intentional breaking behavior or migration requirements.
- If `APP_VERSION` is missing, duplicated, or not valid `x.y.z` semver, stop and report the blocker.
- If the branch already contains a changelog entry for the same PR, update the existing entry instead of choosing another version.
- Do not infer a next version from `out/deploy/version_log.csv` or from previous `CHANGELOG.md` headings.
- The changelog version should match the `APP_VERSION` that deploy/version logging will read for the current git ref.

Verify the local version after editing release notes:

```bash
grep '^APP_VERSION=' .env
```

## Git Ref

Every changelog entry must include a `### Git` section with the latest git ref linked to GitHub.

Use this format:

```markdown
### Git

- Last git ref: [`abc1234`](https://github.com/owner/repo/commit/abc1234def5678...)
```

Rules:

- For new pre-merge changelog entries, use the current branch HEAD from `git rev-parse HEAD` as the last git ref.
- For entries being corrected after version logging or deploy, prefer the successful `merge` row for the version in `out/deploy/version_log.csv`; otherwise use the successful deploy row for that version.
- Link to the full GitHub commit URL. Use `git remote get-url origin` or the PR URL to resolve the GitHub `owner/repo`.
- Display the short ref, but link to the full ref.
- Do not invent GitHub URLs. If no GitHub remote or PR URL is available, stop and ask the user for the repository URL.

## Changelog Entry

Add the new entry near the top of root `CHANGELOG.md`, below the title and optional introductory sentence. Use the bumped version and current date:

```markdown
## [0.11.11] - 2026-06-09

Pull Request: [#123](https://github.com/owner/repo/pull/123)

### Git

- Last git ref: [`abc1234`](https://github.com/owner/repo/commit/abc1234def5678...)

### New Capabilities

- ...

### Fixed Bugs

- ...

### Touched Models

- ...
```

Include the `Pull Request` line only when `gh pr view` or the PR report provides a real PR URL. If no PR exists yet, omit the line rather than adding a placeholder. Always include the `### Git` section. Use `- None.` under a section only when there truly are no items. Do not omit the `Touched Models` section.

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
5. Resolve the latest git ref and GitHub commit URL for the `### Git` section.
6. Leave root `.env` `APP_VERSION` unchanged.
7. Update root `CHANGELOG.md` with the new version entry.
8. Review the changelog entry for these gates:
  - It has a `### Git` section with a `Last git ref` link to the full GitHub commit URL.
   - It has `New Capabilities`, `Fixed Bugs`, and `Touched Models` sections.
  - It includes a `Pull Request` link when a real PR URL is available, and omits the line when no PR exists yet.
   - It contains no changed-file list or path-driven summary.
   - It names touched models or explicitly says `None.`.
   - It matches the PR report and does not overclaim.
9. If `CHANGELOG.md` was previously untracked, include it in the merge branch. Do not force-add `.env` if it remains ignored.
10. Update or regenerate the PR report if the release-note status, version, PR link, git ref, or changelog entry changed after the report was created.

## Exit Criteria

The changelog step is complete when:

- Root `.env` has the intended valid `APP_VERSION` for the changelog entry.
- Root `CHANGELOG.md` has a versioned entry dated with the merge preparation date.
- The changelog entry includes a PR link when one is available.
- The changelog entry includes a `### Git` section with the last git ref linked to GitHub.
- The entry summarizes capabilities and fixes, not changed files.
- Touched models are named, or the entry states `None.`.
- The PR report reflects the version, git ref, and changelog status.