---
name: review
description: "Use when: invoking /review, reviewing code before PR or merge, checking deploy contracts, env schema, docs, tests, secrets handling, Docker/Compose behavior, CI workflows, or deciding whether a change is ready."
---

# Review Skill

## Principles

Review is a quality gate, not a summary exercise. Findings come first, ordered by severity and grounded in files, behavior, or missing evidence.

Review every non-trivial change across correctness, readability, architecture, security, performance, and verification.

## Procedure

1. Understand the request, plan, diff, tests, docs, and affected deploy surface.
2. Review tests and evidence before implementation details.
3. Check deploy contracts: env schema, examples, Compose labels, CLI args, hooks, docs, workflows, and downstream compatibility.
4. Check security: secret files are never read, secrets are not logged, auth/Key Vault/GitHub secrets behavior is intentional.
5. Check performance only with evidence or obvious unbounded work.
6. Report findings first with severity, file reference, risk, evidence, and fix direction.

## Repo-Specific Review Checks

- `docker/docker-compose.yml` and `scripts/deploy/env_schema.py` remain authoritative and aligned.
- Env keys added to code are represented in schema, examples, docs, and GitHub Actions sync when applicable.
- Hook extension points remain the customization boundary.
- Deploy scripts keep downstream wrappers working with `repo_root_override`.
- Docs under `docs/deploy/` match current commands and paths.

## Exit Criteria

- [ ] Findings are ordered by severity.
- [ ] Correctness, architecture, security, performance, and verification were considered.
- [ ] Required fixes are separated from optional suggestions.
- [ ] Verification gaps and residual risks are stated.
- [ ] Final verdict is clear.