---
name: frontend-ui-engineering
description: "Use when: building or changing browser-facing deployment flows, code-server or Portainer checks, docs-visible UI behavior, templates/static assets, responsive layout, accessibility, Playwright tests, or visual/manual verification."
---

# Frontend UI Engineering Skill

## Principles

Deployment UI should be clear, operational, accessible, and focused on repeated admin tasks. Avoid decorative layouts and keep controls predictable.

## When To Use

- Browser-facing deployment behavior changes.
- code-server, Portainer, Caddy auth, docs demos, templates, static assets, responsive layout, or accessibility are involved.
- Writing or updating Playwright/browser checks.

## Procedure

1. Read the existing UI surface, docs, and tests.
2. Define states: loading, success, empty, validation error, server error, disabled/pending, and auth failure when relevant.
3. Implement with semantic HTML and keyboard-accessible controls when source changes are needed.
4. Keep frontend assumptions aligned with deploy/API contracts.
5. Verify with browser/runtime evidence and repeatable tests when practical.

## Red Flags

- UI has only a happy path.
- Console errors are ignored.
- Controls are not keyboard-accessible.
- API/auth failures disappear silently.
- Layout is checked only at one viewport.

## Exit Criteria

- [ ] UI follows existing operational design patterns.
- [ ] Relevant states are handled.
- [ ] Keyboard and basic accessibility are covered.
- [ ] Browser or Playwright verification is documented.