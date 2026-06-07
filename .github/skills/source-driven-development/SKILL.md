---
name: source-driven-development
description: "Use when: implementing framework/library-specific behavior that must match current official docs, verifying Flask, Socket.IO, Playwright, pandas, NumPy, exchange client, charting, deployment, or browser API patterns, or resolving version-sensitive API uncertainty."
---

# Source Driven Development Skill

## Principles

Do not rely on memory for version-sensitive framework or library behavior. Detect the installed version, consult official sources, implement the documented pattern, and flag anything unverified.

This skill is for external technology contracts, not ordinary repo-local logic.

## When To Use

- Implementing or changing Flask, Flask-SocketIO, pytest, Playwright, pandas, NumPy, exchange/client library, browser API, charting, deployment, or packaging behavior.
- The user asks for documented, official, current, or best-practice implementation.
- Existing code conflicts with what you think the framework recommends.
- You are using an unfamiliar library API or version-sensitive feature.
- A framework/library deprecation or migration may matter.

## When Not To Use

- Pure Python logic that does not depend on external API behavior.
- Simple renames, doc edits, or local refactors.
- Repo-specific contracts already covered by local code and tests.
- The user explicitly requests a quick best-effort answer and accepts the risk.

## Procedure

### Step 1 - Detect Stack And Version

Read the relevant dependency/config source:
- `requirements.txt`, `setup.cfg`, or lock files for Python libraries.
- `package.json` or browser-extension manifests for frontend tooling.
- Docker/deploy config for deployment behavior.

State the version or note that it is not pinned.

### Step 2 - Fetch Official Sources

Use official documentation, official changelogs, standards references, or vendor docs. Prefer deep links to the exact API or behavior.

Avoid using Stack Overflow, random blogs, or AI summaries as primary authority.

### Step 3 - Reconcile With Local Patterns

If official docs and local code differ, surface the tradeoff:
- Follow docs and update local pattern.
- Match existing code for consistency.
- Introduce a migration plan.

Do not silently replace established local patterns unless the docs show the existing pattern is broken, deprecated, or unsafe.

### Step 4 - Implement And Cite

Implement the documented pattern. In the final summary or doc update, include the source URLs for non-obvious framework/library decisions.

Use inline comments sparingly and only when the source explains a surprising constraint that future maintainers need near the code.

### Step 5 - Verify Against The Repo

Run focused tests or scripts that exercise the documented behavior. Official docs tell you what should work; repo tests prove it works here.

## Red Flags

- Writing version-sensitive code without checking installed versions.
- Citing tutorials or memory instead of official docs.
- Using deprecated APIs because they appear in older examples.
- Fetching broad documentation homepages instead of the relevant page.
- Ignoring conflicts between docs and existing code.
- Final answer says "I think" about an API that could have been verified.

## Exit Criteria

- [ ] Relevant versions were detected or ambiguity was reported.
- [ ] Official sources were consulted for the external API behavior.
- [ ] Local patterns and docs were reconciled.
- [ ] Non-obvious external decisions include source URLs in the summary or docs.
- [ ] Focused repo validation passed or limitations are clearly reported.