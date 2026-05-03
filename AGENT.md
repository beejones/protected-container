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
- **Logging**: Use `logging` module at `DEBUG` level. Use prefixes: `[STORE]:`, `[COLLECTOR]:`, `[TRADER]:`.
- **Error Handling**: Use `try-except` blocks. Fail gracefully; avoid complex fallback mechanisms unless strictly necessary for reliability.
- **Bugs**: Follow the **bug-fix** skill (`.github/skills/bug-fix/SKILL.md`): hypothesis → failing test (must fail gate) → minimal fix → verify. Every bug fix requires a test that proves it.
- **Arguments**: Avoid optional arguments (`arg=None`) unless strictly necessary to prevent ambiguity/bugs. Use object, dict and `Any` only when necessary. Prioritize using data classes. Do strict input validation on arguments. Use strict-typing.
- **Dataclass-first**: Use dataclasses for internal data structures by default. `to_dict()` and `from_dict()` methods are permitted only at API/JSON/file boundaries and must be clearly labelled as these restricted utilities. We use JSONValue as type for these serializations and should only be used for the serialization purpose. Search for existing data classes before creating new ones. 
- **Typing Anti-Pattern (Forbidden)**: Do **not** declare required inputs as optional and then guard inside the same function (e.g., `def f(x: Optional[str]): if not x or not isinstance(x, str): return ...`). Validate/normalize at the boundary, then pass a strict required type (e.g., `str`) internally.
- **Boundary Typing Principle**: Normalize nullable/untyped input at API or adapter boundaries, then pass strict typed values internally. Core/public signatures should use explicit dataclasses/protocols and non-optional types when the value is required.
- **Fallback code**: Use fallbacks wisely where they cover for transient events such as API calls and timeouts. In the other cases prioritize gracefull failing
- **Docs maintenance**: When modifying a module, review the corresponding docs in `docs/<module>/` for: (1) missing documentation for new or changed behavior, (2) duplicate descriptions across files that should be consolidated, and (3) broken or incorrect internal links. Fix any issues found as part of the change. A doc should start with a section describing the main principles guarded by the code
- **Cleanup**: Delete obsolete code immediately.
- **Permissions**: You have permission to run tests without asking.

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
- `planning/`: Planning files. Planning file must have a checkable task overview and clear phase exit criteria. The first phase in a plan should always be cleanup — follow the **module-cleanup** skill (`.github/skills/module-cleanup/SKILL.md`). Also check if docs must be merged or are obsolete. UI plans should show a mockup of the new design.
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