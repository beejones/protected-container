# Agent Instructions

## 1. Critical Rules (Must Follow)
- **Security**: **NEVER** read `.env.secrets` or `.env.deploy.secrets`.
- **NEVER** store temp files in the codebase. Use out/tmp for this purpose and clean up when done.
- **Environment**: **ALWAYS** run scripts within the virtual environment.
  ```bash
  source .venv/bin/activate && python <script>
  ```
- **Server Startup**: Use the dedicated startup command to ensure proper logging.
  ```bash
  source .venv/bin/activate && python run.py
  ```

## 2. Development Standards
### Code Quality
- **Style**: Follow **PEP 8**. Use **f-strings** for formatting.
- **Logging**: Use `logging` module at `DEBUG` level. Use prefixes such as `[STORE]:`, `[COLLECTOR]:`, `[TRADER]:`, etc.
- **Error Handling**: Use `try-except` blocks. Fail gracefully; avoid complex fallback mechanisms unless strictly necessary for reliability.
- **Bugs**: Follow the **bug-fix** skill (`.github/skills/bug-fix/SKILL.md`): hypothesis → failing test (must fail gate) → minimal fix → verify. Every bug fix requires a test that proves it.
- **Typed code generation (mandatory)**: Before writing or modifying Python production or test code, read and follow the **typed-code-generation** skill (`.github/skills/typed-code-generation/SKILL.md`). It owns the dataclass-first workflow and the guardrails against loose `dict`/`object`/`Any` code.
- **Arguments**: Avoid optional arguments (`arg=None`) unless strictly necessary to prevent ambiguity/bugs. Validate nullable/untyped input at boundaries, then pass strict non-optional values internally. All defs require explicit types.
- **Dataclass-first**: Use dataclasses for internal data structures by default. `to_dict()` and `from_dict()` methods are permitted only at API/JSON/file boundaries and must be clearly labelled as restricted serialization utilities. Use `JSONValue` for JSON serialization payloads; do not use `dict[str, object]` as a generic JSON substitute. Search for existing data classes before creating new ones.
- **Forbidden loose typing in new core logic**: Do not introduce `Any`, `object`, `dict[str, object]`, `Dict[str, object]`, `Mapping[str, object]`, `MutableMapping[str, object]`, untyped `dict`, or optional-required parameters outside explicit boundary adapters. If a function needs multiple fields from a payload, create or reuse a dataclass/protocol/enum.
- **Typing Anti-Pattern (Forbidden)**: Do **not** declare required inputs as optional and then guard inside the same function (e.g., `def f(x: Optional[str]): if not x or not isinstance(x, str): return ...`). Validate/normalize at the boundary, then pass a strict required type (e.g., `str`) internally.
- **Boundary Typing Principle**: Normalize nullable/untyped input at API or adapter boundaries, then pass strict typed values internally. Core/public signatures should use explicit dataclasses/protocols and non-optional types when the value is required.
- **Fallback code**: Use fallbacks wisely where they cover for transient events such as API calls and timeouts. In the other cases prioritize gracefull failing
- **Docs maintenance**: When modifying a module, review the corresponding docs in `docs/<module>/` for: (1) missing documentation for new or changed behavior, (2) duplicate descriptions across files that should be consolidated, and (3) broken or incorrect internal links. Fix any issues found as part of the change. A doc should start with a section describing the main principles guarded by the code
- **Cleanup**: Delete obsolete code immediately.
- **Permissions**: You have permission to run tests without asking.
- **CI**: We need to reduce the usage of CI. Enable CI when we run it after the copilot PR review.

### Skill Routing
- **Before non-trivial work**: Check whether a skill applies. If unsure, read `.github/skills/using-agent-skills/SKILL.md` first.
- **Context setup**: Use `.github/skills/context-engineering/SKILL.md` when starting a session, switching modules, output quality drifts, or the right files/examples/tests need to be packed before work.
- **Planning**: Use `.github/skills/plan/SKILL.md` for `/plan`, planning files, task breakdown, dependency ordering, and validation planning.
- **Code cleanup / Phase 0**: Use `.github/skills/code-cleanup/SKILL.md` for cleanup of the module currently being changed, including Phase 0 cleanup, large-module refactors, duplicate-code consolidation, obsolete-code deletion, and `typed-code-generation` with existing dataclasses/model types.
- **Python typing**: Use `.github/skills/typed-code-generation/SKILL.md` before writing or modifying Python production or test code.
- **Bug fixes**: Use `.github/skills/bug-fix/SKILL.md` for regressions, uncaught exceptions, wrong behavior, or failing tests caused by production code.
- **Testing and validation**: Use `.github/skills/test/SKILL.md` for `/test`, focused validation plans, priority tests, UI tests, and full-suite evidence.
- **Browser runtime checks**: Use `.github/skills/browser-testing-with-devtools/SKILL.md` for real-browser DOM, console, network, screenshot, accessibility, and performance verification.
- **Simplification**: Use `.github/skills/code-simplify/SKILL.md` for behavior-preserving readability/refactor passes.
- **Code review**: Use `.github/skills/review/SKILL.md` before merge or when reviewing agent/human changes.
- **API/interface design**: Use `.github/skills/api-interface-design/SKILL.md` for Flask routes, module contracts, request/response shapes, and boundary validation.
- **Frontend UI**: Use `.github/skills/frontend-ui-engineering/SKILL.md` for template/static JS/CSS changes and Playwright-backed UI behavior.
- **Security**: Use `.github/skills/security-hardening/SKILL.md` for auth, secrets, untrusted input, external services, and deployment-sensitive paths.
- **Performance**: Use `.github/skills/performance-optimization/SKILL.md` for analyzer, optimizer, datasource, API, or UI performance work.
- **Docs/ADRs**: Use `.github/skills/documentation-and-adrs/SKILL.md` for docs maintenance, architecture rationale, and public contract changes.
- **Source-driven implementation**: Use `.github/skills/source-driven-development/SKILL.md` when framework/library behavior must be verified against official docs.
- **Analyzer evidence**: Use `.github/skills/analyzer-improvement-check/SKILL.md` when validating optimizer/analyzer improvements with live evidence.
- **Strategy adoption**: Use `.github/skills/strategy-promotion-adoption/SKILL.md` when promoting, rejecting, or applying strategy parameter improvements.
- **PR and merge work**: Use `.github/skills/merge/SKILL.md` for PR reports, reviewer feedback, CI watching, mergeability checks, merging, and cleanup.

# Project Context

## 1. Project Overview
**Stock Dashboard** is a Python web application for tracking and analyzing stock/crypto market data.
- **Backend**: Flask + Socket.IO (threaded mode).
- **Frontend**: HTML templates + Static Assets (JS/CSS).
- **Core Functionality**: Real-time market data collection, technical analysis (indicators), and trading strategy execution.

## 2. File Organization
Do not store temporary files in the source code directory. Use out/ for this purpose
- `src/common/`: Shared utilities and core logic. **Reuse code from here whenever possible.**
- `debug/`: Verification and one-off scripts. **Do NOT pollute the root directory.**
- `out/`: Temporary output files including test reports.
- `out/PR`: Temporary output files for  PR reports.
- `logs/`: Application logs (`logs/app.log`).
- `tests/pytests/`: Unit and integration tests.  Tests should start with test_<module>...
- `tests/UI/`: UI tests using playwright. Tests should start with test_ui_<module>...
- `planning/`: Planning files. Planning file must have a checkable task overview and clear phase exit criteria. The first phase in a plan should always be cleanup — follow the **code-cleanup** skill (`.github/skills/code-cleanup/SKILL.md`). Also check if docs must be merged or are obsolete. UI plans should show a mockup of the new design.
- `archive/planning/`: Completed plans go here. When all tasks in a plan are done, rename with `_ARCHIVED` suffix and move to `archive/planning/`.
- `docs/`: Documentation. Each major topic should have a doc. 

## 3. Workflows & Preferences
### User Preferences
- **CSV Exports**: Use semicolon (`;`) delimiter and comma (`,`) for decimals (Excel-friendly).
- **PR Reviews**: Return reports as raw markdown files (e.g., `out/PR/Review.md`).

### Testing Context
- **Tooling**: We use `pytest` for backend tests.
- **Canonical runner**: Use `source .venv/bin/activate && python scripts/run_tests.py` for mixed backend + UI validation. This is the default repo runner because it manages boundary lint, backend tests, UI sharding, and the test server lifecycle consistently.
- **Fail-fast CI / preflight**: When a known risky or recently fixed subset should run before the rest of the suite, pass a JSON array of selectors to `--priority-tests`. Example:
  ```bash
  source .venv/bin/activate && python scripts/run_tests.py --priority-tests='["tests/pytests/test_indicator_catalog.py","tests/UI/test_ui_indicator_catalog.py"]'
  ```
  The priority selectors run first and abort the suite immediately on failure; if they pass, the normal suite continues. Use this to front-load historically failing tests in CI without replacing full-suite coverage.
- **Philosophy**: Tests are encouraged for all new logic.

# App specific logic
See `./AGENT_APP_SPECIFIC`