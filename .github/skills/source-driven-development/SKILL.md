---
name: source-driven-development
description: "Use when: framework/tool behavior must be verified against official docs, including Docker Compose, Caddy, Azure, GitHub Actions, Portainer, Python libraries, browser APIs, or version-specific deployment behavior."
---

# Source-Driven Development Skill

## Principles

When correctness depends on framework, cloud, or tooling behavior, verify against authoritative sources before coding. Memory and old examples go stale.

## When To Use

- Implementing or changing Docker Compose, Caddy, Azure Container Instances, Azure Key Vault, GitHub Actions OIDC/secrets, Portainer, Python package, browser, or registry behavior.
- The user asks for documented, official, current, or best-practice behavior.
- Existing code and current docs appear to disagree.

## Procedure

1. Detect relevant versions or note when they are not pinned.
2. Fetch official documentation, standards references, or vendor changelogs for the exact behavior.
3. Reconcile docs with local patterns and downstream compatibility.
4. Implement the documented pattern or clearly document an intentional deviation.
5. Cite source URLs in the final summary or docs for non-obvious decisions.
6. Run focused local validation.

## Red Flags

- Writing provider/tool behavior from memory when version matters.
- Citing tutorials as primary authority.
- Ignoring conflicts between docs and existing contracts.
- No local validation after following documentation.

## Exit Criteria

- [ ] Relevant version/tool context was checked.
- [ ] Official sources were consulted.
- [ ] Local patterns and compatibility were reconciled.
- [ ] Non-obvious decisions include source URLs.
- [ ] Focused validation passed or limitations are stated.