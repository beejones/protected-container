---
name: typed-code-generation
description: "Use when: writing new Python code, changing function signatures, adding helpers, refactoring, reviewing typing quality, removing dict/object/Any patterns, or converting JSON/API payloads into typed internal models. Mandatory before generating production or test Python code."
---

# Typed Code Generation

## Principles

New code must be explicit about data shape. This guards against:
- Hidden schema drift caused by loose `dict`, `object`, or `Any` payloads.
- Core logic that silently accepts invalid API/file/JSON data.
- Generic JSON containers such as `Mapping[str, JSONValue]` being mistaken for typed domain models.
- Optional arguments being used as a substitute for boundary validation.
- Tests normalizing bad production patterns by copying untyped helpers.
- Do not just use TypeAlias to create a type which maps to a dict. A dict is not a typed object and does not prevent schema drift. Instead, create a dataclass or protocol that explicitly defines the expected fields and types.

## When To Use

Use this skill before writing or modifying Python production or test code, especially when:
- Adding a helper, service, model, route, adapter, or test fixture helper.
- Changing a function signature or return type.
- Reading data from JSON, HTTP requests, config files, exchange adapters, or persisted runtime state.
- Seeing `dict[str, object]`, `Dict[str, object]`, `Mapping[str, object]`, `dict[str, JSONValue]`, `Mapping[str, JSONValue]`, TypeAlias to dict, untyped `dict`, `object`, `Any`, or optional required inputs.
- Reviewing or cleaning existing code for AGENT typing compliance.

## Hard Rules

### Forbidden In New Core Logic

Do not introduce these in core/internal logic:
- `Any`
- `object`
- `TypeAlias` that points to `dict`, `Mapping`, `MutableMapping`, or other loose container payloads
- `dict[str, object]`
- `Dict[str, object]`
- `Mapping[str, object]`
- `MutableMapping[str, object]`
- `dict[str, JSONValue]`, `Mapping[str, JSONValue]`, or `MutableMapping[str, JSONValue]` as an internal domain type
- `JSONValue`, `list[JSONValue]`, or other generic JSON containers as internal business objects
- untyped `dict`, `list`, `tuple`, or `set`
- required values typed as optional and guarded inside the same function

If a function needs multiple fields from the same payload, create or reuse a dataclass, protocol, enum, or dedicated value object.

`JSONValue` annotations describe serialization compatibility, not business shape. A function such as `enrich_*`, `build_*`, `score_*`, `resolve_*`, `apply_*`, or `select_*` that accepts `Mapping[str, JSONValue]` and returns `dict[str, JSONValue]` is still untyped core logic unless its name and module make it an explicit boundary adapter.

Do not treat a helper as a boundary just because its name contains `payload`. If the helper enriches, resolves, scores, selects, builds, or otherwise applies business rules, that operation is no longer the boundary. Convert the raw payload into a dataclass first, run the business operation on dataclasses/protocols/enums, then serialize the typed result back to a payload in a separate `*_to_payload`, `*_from_payload`, or clearly named payload-copy adapter.

### Do Not Hide Dicts Behind TypeAlias

Do not make a loose payload look typed by naming it with `TypeAlias`:

```python
SignalConfigPayload: TypeAlias = dict[str, JSONValue]
OptimizerRow: TypeAlias = Mapping[str, JSONValue]
```

These aliases still allow arbitrary keys and do not protect against schema drift. They also make reviews harder because the annotation looks domain-specific while still behaving like a generic dict.

Using the generic container directly has the same problem:

```python
def enrich_optimizer_row(row: Mapping[str, JSONValue]) -> dict[str, JSONValue]:
    ...
```

This is a JSON payload transformation, not a typed internal API. Keep it only at a named serialization/API boundary, or convert the input to a dataclass before doing domain work.

Use one of these instead:
- Existing model-owned dataclasses such as `TradeSignalGenerationConfig`.
- A new dataclass when the code owns a concrete internal shape.
- A protocol when the code depends on behavior rather than storage.
- A named boundary function that accepts `Mapping[str, JSONValue]` only long enough to validate and convert.

The only acceptable dict-shaped aliases are narrow serialization aliases at explicit boundaries, and their names must say what boundary they belong to, such as `OptimizerApiResponsePayload` or `SignalConfigStoreRecord`. Do not use these aliases as internal business objects.

### Allowed Only At Explicit Boundaries

Loose payload shapes are allowed only at named boundaries:
- API request/response normalization.
- JSON/file persistence serialization or deserialization.
- Exchange/client adapter compatibility layers.
- Legacy compatibility shims.
- Test payload fixtures that intentionally model raw API/JSON data.

Loose payload shapes include `dict[str, JSONValue]`, `Mapping[str, JSONValue]`, `list[JSONValue]`, and standalone `JSONValue` parameters or returns. These are allowed to cross process, file, HTTP, or legacy compatibility boundaries; they are not acceptable as the typed representation passed through core helper layers.

Boundary functions must make the boundary obvious in the name, for example:
- `*_from_mapping(...)`
- `*_from_payload(...)`
- `*_from_api_request(...)`
- `*_to_payload(...)`
- `to_dict(...)`
- `from_dict(...)`

Boundary functions must immediately convert raw values into strict internal types before calling core logic.
They must not combine raw payload mutation with business enrichment under a verb like `enrich_*_payload`; split those flows into raw-to-dataclass normalization, dataclass enrichment, and payload serialization.

### Serialization Types

Use `JSONValue` for JSON serialization payload values when available. Do not use `dict[str, object]` as a generic JSON substitute.

Do not treat `dict[str, JSONValue]` or `Mapping[str, JSONValue]` as the typed substitute for a dataclass. They are acceptable for request bodies, response payloads, persisted JSON records, and `to_dict()`/`from_dict()` methods only when the code is clearly at that boundary.

`to_dict()` and `from_dict()` are allowed only at serialization boundaries. They must not become the internal representation used by business logic.

## Required Workflow

### Step 1 - Search Existing Types

Before creating a new type, search for existing dataclasses, protocols, type aliases, enums, and helpers in:
- the target module
- nearby model modules first (`models.py`, `*_models.py`, and domain model modules such as `signal_config.py` or schema modules)
- `src/common/`
- nearby test fixtures

Prefer reuse over new shapes. If a model-owned type already represents the payload or internal shape, import that type instead of creating a local alias with a similar name.

If the existing type is a dataclass or model object, use that type directly. Do not create a local `TypeAlias` to `dict[...]` just to avoid importing or constructing the model.

### Step 2 - Classify Inputs

For each raw value source, classify it:
- API boundary
- JSON/file boundary
- adapter boundary
- compatibility boundary
- already-normalized internal value

Only boundary code may touch loose payloads. Internal code receives normalized types.

### Step 3 - Define The Typed Shape

Use the narrowest appropriate structure:
- dataclass for grouped values
- enum for finite string modes/states
- protocol for interface behavior
- `JSONValue` for serialization payloads
- `Mapping[str, JSONValue]` or `dict[str, JSONValue]` only for explicit boundary adapters, never as the domain shape itself
- specific collection types such as `list[TradeRecord]`, not `list[object]`

Do not use `TypeAlias = dict[...]` or `TypeAlias = Mapping[...]` to satisfy this step. That is still an unstructured payload, not a typed domain shape.

Avoid optional fields for values that are required after normalization. Validate at the boundary, then pass non-optional values internally.

### Step 4 - Refactor Call Flow

Structure code as:

```python
raw_payload -> boundary_normalizer(...) -> dataclass/protocol/enum -> core_logic(...)
```

Do not let raw payload dictionaries leak through multiple internal helper layers.

### Step 5 - Review The Diff

Before finishing, search changed Python files for forbidden patterns:

```bash
rg "\bAny\b|\bobject\b|TypeAlias\s*=\s*(dict|Dict|Mapping|MutableMapping)|dict\[str, object\]|Dict\[str, object\]|Mapping\[str, object\]|MutableMapping\[str, object\]|: dict\b|-> dict\b" src tests
```

Also search changed files for generic JSON payloads and classify every match:

```bash
rg "dict\[str, JSONValue\]|Mapping\[str, JSONValue\]|MutableMapping\[str, JSONValue\]|list\[JSONValue\]|Sequence\[JSONValue\]|-> JSONValue|: JSONValue" src tests
```

For every match, record whether it is:
- an allowed named boundary
- a legacy compatibility shim outside the change
- a test raw-payload fixture
- a violation to fix before completion

### Step 6 - Validate

Run focused tests for the changed module. For broad typing cleanup, run the full suite:

```bash
source .venv/bin/activate && python scripts/run_tests.py
```

## Cleanup Existing Bad Patterns

When fixing existing code, keep changes module-scoped:
- Add boundary normalizers first.
- Introduce dataclasses/protocols for internal call paths.
- Replace one call path at a time.
- Delete obsolete loose helpers immediately.
- Add regression tests when behavior could change.

Do not rewrite unrelated modules just because a broad search found older violations. Record follow-up candidates instead.

## Exit Criteria

Typed code generation is complete when:
- [ ] New or changed core logic has no `Any`, `object`, generic dict, or optional-required inputs.
- [ ] Every loose payload use, including `Mapping[str, JSONValue]` and `dict[str, JSONValue]`, is isolated to an explicitly named boundary.
- [ ] Boundary code converts raw data into dataclasses/protocols/enums before core logic, and uses `JSONValue` only when serializing/deserializing at the edge.
- [ ] Existing dataclasses/helpers were reused where appropriate.
- [ ] Focused validation passed, and full validation ran when the blast radius was broad.

## Examples

### Bad

```python
SignalConfigPayload: TypeAlias = dict[str, JSONValue]


def build_signal_config(payload: SignalConfigPayload) -> SignalConfigPayload:
    payload["min_confidence"] = str(payload.get("min_confidence") or "WEAK")
    return payload
```

```python
def build_snapshot(position: Mapping[str, object]) -> dict[str, object]:
    size = float(position.get('size') or 0)
    return {'size': size}
```

```python
def enrich_optimizer_ab_row_signal_config_ids(
    row: Mapping[str, JSONValue],
) -> dict[str, JSONValue]:
    signal_config_id = str(row.get("signal_config_id") or "")
    return {**row, "signal_config_id": signal_config_id}
```

```python
def enrich_optimizer_ab_row_signal_config_payload(
    row: Mapping[str, JSONValue],
) -> dict[str, JSONValue]:
    ...
```

Even though `payload` appears in the name, this is an enrichment helper. The enrichment must use a dataclass row, and payload copying must be separated into a boundary adapter.

### Good

```python
@dataclass(frozen=True)
class PositionSnapshotInput:
    size: float


def position_snapshot_input_from_mapping(position: Mapping[str, object]) -> PositionSnapshotInput:
    size = parse_required_float(position.get('size'), field_name='size')
    return PositionSnapshotInput(size=size)


def build_snapshot(position: PositionSnapshotInput) -> PositionSnapshot:
    return PositionSnapshot(size=position.size)
```

```python
def signal_config_from_payload(payload: Mapping[str, JSONValue]) -> TradeSignalGenerationConfig:
    return TradeSignalGenerationConfig.from_api_request(payload)
```

```python
@dataclass(frozen=True)
class OptimizerABSignalConfigRow:
    signal_config_id: str
    strategy_id: str


def optimizer_ab_signal_config_row_from_payload(
    payload: Mapping[str, JSONValue],
) -> OptimizerABSignalConfigRow:
    return OptimizerABSignalConfigRow(
        signal_config_id=str(payload.get("signal_config_id") or "").strip(),
        strategy_id=str(payload.get("strategy_id") or "").strip(),
    )


def enrich_optimizer_ab_signal_config_row(
    row: OptimizerABSignalConfigRow,
) -> OptimizerABSignalConfigRow:
    return row
```

```python
def optimizer_ab_row_payload_with_signal_config_ids(
    payload: Mapping[str, JSONValue],
    signal_config_ids: OptimizerABSignalConfigIds,
) -> dict[str, JSONValue]:
    result = dict(payload)
    result["signal_config_id"] = signal_config_ids.signal_config_id
    return result
```

The payload helper only serializes typed enrichment results back into a JSON-compatible shape; it does not own the enrichment rule.
