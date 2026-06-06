---
name: typed-code-generation
description: "Use when: writing or modifying Python production/test code, changing signatures, adding helpers, refactoring deploy scripts, reviewing typing quality, or converting env/config/Compose/API payloads into typed internal models."
---

# Typed Code Generation

## Principles

New Python code must make data shape explicit. Raw env/config/Compose/API payloads belong at boundaries; deploy logic should receive strict typed values.

## When To Use

- Adding helpers, services, deploy steps, schema parsing, validation, or tests.
- Changing function signatures or public helper contracts.
- Reading `.env`, `.env.deploy`, example env files, Compose YAML, GitHub Actions payloads, Key Vault data, hook responses, or CLI args.
- Seeing `Any`, `object`, generic `dict`, or optional-required parameters in changed code.

## Hard Rules

- Normalize nullable/untyped input at boundaries, then pass strict required types internally.
- Do not introduce `Any`, `object`, raw `dict`, `dict[str, object]`, or optional-required inputs in new core logic.
- Use dataclasses, enums, protocols, or narrow type aliases when values travel together.
- Serialization helpers must be explicitly named as boundaries, for example `*_from_mapping`, `*_from_env`, `*_to_payload`, or `to_dict`.

## Required Workflow

1. Search existing deploy types/helpers before creating new ones.
2. Classify each raw source: CLI, env, Compose, hook, GitHub API, Azure API, filesystem, or internal typed value.
3. Convert raw boundary data into strict shapes.
4. Keep core deploy functions free of raw mapping plumbing.
5. Search changed Python files for loose typing patterns before finishing.
6. Run focused tests for the changed path.

## Exit Criteria

- [ ] New/changed core logic avoids loose `Any`, `object`, generic dicts, and optional-required inputs.
- [ ] Loose payloads are isolated to explicit boundary adapters.
- [ ] Existing helpers/types were reused where appropriate.
- [ ] Focused validation passed or baseline failures are reported.