---
name: security-hardening
description: "Use when: handling secrets, env files, auth, Basic Auth hashes, Azure Key Vault, GitHub Actions secrets, registries, SSH, external APIs, deploy logs, browser content, shell/file operations, or security review."
---

# Security Hardening Skill

## Principles

Treat every external value as untrusted and every secret as non-readable. Deployment tooling has a larger blast radius than app code because it touches credentials, infrastructure, registries, and remote machines.

## Non-Negotiable Rules

- Never read `.env.secrets` or `.env.deploy.secrets`.
- Never print, log, commit, or summarize secret values.
- Use example files for placeholders only.
- Validate env keys through `scripts/deploy/env_schema.py`.
- Redact tokens, keys, passwords, auth headers, registry credentials, SSH targets when needed, and Key Vault values.
- Do not expose stack traces or raw provider errors in user-facing output when they may contain sensitive data.

## Procedure

1. Identify trust boundaries: env files, CLI args, Compose, GitHub/Azure/Portainer/registry APIs, SSH, browser content, generated files.
2. Validate and normalize raw values before core logic.
3. Review auth/authorization and secret storage behavior.
4. Search diffs for suspicious names: `secret`, `password`, `token`, `key`, `auth`, `credential`, `registry`.
5. Verify logs and errors are useful but redacted.
6. Run focused tests for security-sensitive behavior when changed.

## Red Flags

- Secret env files are opened.
- Raw dotenv contents are logged.
- Unknown env keys bypass schema unintentionally.
- GitHub Actions secrets or Azure Key Vault values are echoed.
- Shell commands interpolate untrusted input.
- Caddy/Basic Auth behavior changes without docs and validation.

## Exit Criteria

- [ ] Trust boundaries are identified.
- [ ] Secrets were not read, printed, logged, or committed.
- [ ] Inputs are validated and normalized.
- [ ] Error/log output avoids sensitive details.
- [ ] Security-sensitive behavior has focused validation or documented limitations.