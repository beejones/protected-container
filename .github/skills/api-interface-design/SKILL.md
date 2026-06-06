---
name: api-interface-design
description: "Use when: designing or changing deploy-toolkit interfaces: CLI args, env schema, hook contracts, Compose labels, generated YAML/Caddyfile contracts, REST endpoints, module boundaries, or public helper signatures."
---

# API Interface Design Skill

## Principles

Interfaces are contracts. Every observable deploy behavior can become something downstream repos depend on: env keys, CLI args, generated files, hook names, Compose labels, docs-visible commands, and error text.

## When To Use

- Adding/changing deploy CLI args, env schema fields, hook contracts, Compose labels, generated ACI YAML, Caddyfile behavior, storage-manager API assumptions, or public helpers.
- Connecting deployment scripts to external services such as Azure, GitHub, Portainer, or registries.

## Procedure

1. Identify consumers: deploy scripts, wrappers, GitHub Actions, downstream hooks, docs, tests, users, Docker Compose, Azure, Portainer, Caddy, storage-manager.
2. Define the contract before implementation: inputs, outputs, defaults, errors, compatibility, and migration.
3. Normalize raw input at boundaries: CLI, env, Compose, hooks, external APIs, files.
4. Prefer additive compatibility. Avoid removing fields or changing meanings without rollout guidance.
5. Test success, invalid input, missing prerequisites, and docs-visible behavior.

## Red Flags

- Env key appears in code but not schema/examples/docs.
- Hook signature changes without downstream compatibility.
- CLI behavior changes without docs and `--help` checks.
- Generated Compose/YAML/Caddyfile shape changes without tests.
- Raw external API payloads leak into core logic.

## Exit Criteria

- [ ] Contract and consumers are explicit.
- [ ] Raw inputs are normalized at boundaries.
- [ ] Compatibility risks are addressed or documented.
- [ ] Tests cover success and meaningful error paths.
- [ ] Docs are updated for public behavior.