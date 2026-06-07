---
name: api-interface-design
description: "Use when: designing or changing Flask APIs, request/response shapes, route contracts, module boundaries, dataclass/protocol interfaces, external adapter contracts, error semantics, pagination/filtering, or JSON serialization behavior."
---

# API Interface Design Skill

## Principles

Interfaces are commitments. Every request field, response field, status code, error shape, ordering rule, and fallback behavior can become something a caller depends on.

Design the contract before implementation:
- API routes validate and normalize raw input.
- Internal services receive strict typed values.
- JSON/file/external boundaries are explicit.
- Error responses are predictable and do not leak internals.
- Existing public behavior changes only with a migration or clear compatibility plan.

## When To Use

- Adding or changing Flask routes in analyzer, optimizer, trading, or shared APIs.
- Changing request/response payloads, status codes, error semantics, or query parameters.
- Designing module boundaries, dataclasses, protocols, or adapter interfaces.
- Reading from config files, exchange clients, persisted runtime state, or browser/API payloads.
- Creating contracts that frontend, analyzer, optimizer, trading, or datasource code will consume.

## Repo Contract Rules

- Trading APIs live in `src/dashboards/trading/routes_api.py`.
- Analyzer APIs live in `src/analyzer/api.py`.
- Optimizer APIs live in `src/optimizer/api.py`.
- Signal generation should use `src/trading/signal_request.py:collect_signal_generation_request(...)` for request normalization.
- Trading signal generation should use `src/trading/signal_pipeline.py:generate_signals_with_strategies(...)`.
- Data-source fan-out should go through `src/datasources/data_manager.py:DataManager`.
- Numeric API payloads must sanitize `NaN` and infinity to `None` before `jsonify`.
- Strategy JSON must not define UI-owned `timeframe` or `min_confidence`; execution-only behavior belongs under `execution_config`.
- Python interfaces must follow `.github/skills/typed-code-generation/SKILL.md`.

## Procedure

### Step 1 - Identify Consumers

List every caller or downstream consumer:
- Frontend templates/static JavaScript.
- Analyzer/optimizer/trading internals.
- Tests and debug scripts.
- Persisted JSON/config files.
- External exchanges or deployment scripts.

If an existing caller depends on current behavior, prefer additive changes.

### Step 2 - Define The Contract

Write down:
- Route, method, query params, and request body.
- Required and optional fields.
- Response shape for success, empty result, validation error, not found, conflict, and server error.
- Sorting, filtering, pagination, and default behavior.
- Backward compatibility and deprecation approach.

For internal interfaces, define dataclasses, protocols, enums, or narrow value objects before implementation.

### Step 3 - Normalize At Boundaries

Boundary code may read raw request JSON, config mappings, query strings, or external payloads. It must convert them immediately into strict internal types.

Do not pass raw payload dictionaries through core logic. Do not declare required core inputs as optional and then guard inside the same function.

### Step 4 - Implement Consistently

- Reuse existing helper APIs and error patterns.
- Keep route handlers thin: parse, call typed service, serialize.
- Keep serialization utilities named as boundaries, for example `*_to_payload`, `*_from_mapping`, or `to_dict`.
- Preserve status-code and response-shape consistency with neighboring routes.
- Update frontend callers and tests in the same change when a contract changes.

### Step 5 - Validate The Contract

Use focused API or service tests for:
- Valid input.
- Missing required fields.
- Invalid types or enum values.
- Empty results.
- Error paths.
- NaN/inf serialization when numeric computation is involved.

For UI-facing API changes, add or update Playwright coverage when user workflows can regress.

## Red Flags

- Response shape changes depending on branch or exception type.
- Validation scattered across internal helpers instead of at the boundary.
- Raw `dict`, `object`, or `Any` payloads in core logic.
- New route duplicates existing signal generation or datasource behavior.
- List endpoints or table payloads have no limit, pagination, or bounded date range.
- API returns NaN or infinity.
- External adapter payloads are trusted without validation.
- Frontend callers are not updated with backend contract changes.

## Exit Criteria

- [ ] Contract and consumers are identified.
- [ ] Raw inputs are normalized at boundaries.
- [ ] Internal code uses strict typed shapes.
- [ ] Error semantics and response shapes match nearby APIs.
- [ ] JSON serialization is safe for NaN/inf values.
- [ ] Tests cover success, validation, and meaningful error paths.
- [ ] Docs are updated for public or durable contracts.