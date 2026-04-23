# Agent Instructions

## 1. Critical Rules (Must Follow)
- **Security**: **NEVER** read `.env.secrets` or `.env.deploy.secrets`.
- **NEVER** store temp files in the codebase. Use `out/` for this purpose and clean up when done.
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
- **Arguments**: Avoid optional arguments (`arg=None`) unless strictly necessary to prevent ambiguity/bugs. Avoid `Any`, `object`, and untyped `dict`; use dataclasses or explicit type aliases. Do strict input validation on arguments. Use strict-typing.
- **Dataclass-first**: Use dataclasses for internal data structures by default. `to_dict()` and `from_dict()` methods are permitted only at API/JSON/file boundaries and must be clearly labelled as these restricted utilities. We use JSONValue as type for these serializations and should only be used for the serialization purpose. Search for existing data classes before creating new ones.
- **Typing Anti-Pattern (Forbidden)**: Do **not** declare required inputs as optional and then guard inside the same function (e.g., `def f(x: Optional[str]): if not x or not isinstance(x, str): return ...`). Validate/normalize at the boundary, then pass a strict required type (e.g., `str`) internally.
- **Boundary Typing Principle**: Normalize nullable/untyped input at API or adapter boundaries, then pass strict typed values internally. Core/public signatures should use explicit dataclasses/protocols and non-optional types when the value is required.
- **Fallback code**: Use fallbacks wisely where they cover for transient events such as API calls and timeouts. In the other cases prioritize graceful failing.
- **Docs maintenance**: When modifying a module, review the corresponding docs in `docs/<module>/` for: (1) missing documentation for new or changed behavior, (2) duplicate descriptions across files that should be consolidated, and (3) broken or incorrect internal links. Fix any issues found as part of the change. A doc should start with a section describing the main principles guarded by the code.
- **Cleanup**: Delete obsolete code immediately.
- **Permissions**: You have permission to run tests without asking.

# Project Context

## 1. Project Overview
**protected-container** is a deployment toolkit for running a secured container payload in Azure and on Ubuntu servers, leveraging TLS and Azure Key Vault.
- **Current default payload**: code-server (VS Code in the browser).
- **Deployment targets**: Azure Container Instances and Ubuntu servers with a centralized Caddy proxy.
- **Core components**: Docker Compose configuration, deploy scripts (`scripts/deploy/`), env schema validation, and a storage-manager service.

## 2. File Organization
Do not store temporary files in the source code directory. Use `out/` for this purpose.
- `scripts/deploy/`: Deploy scripts for Azure and Ubuntu targets.
- `docker/`: Docker Compose files and container-specific scripts.
- `docs/deploy/`: Operator-facing deployment documentation.
- `debug/`: Verification and one-off scripts. **Do NOT pollute the root directory.**
- `out/`: Temporary output files including test reports.
- `out/PR/`: Temporary output files for PR reports.
- `logs/`: Application logs.
- `tests/pytests/`: Unit and integration tests. Tests should start with `test_<module>...`
- `planning/`: Planning files. Planning file must have a checkable task overview and clear phase exit criteria. The first phase in a plan should always be cleanup — follow the **module-cleanup** skill (`.github/skills/module-cleanup/SKILL.md`). Also check if docs must be merged or are obsolete.
- `archive/planning/`: Completed plans go here. When all tasks in a plan are done, rename with `_ARCHIVED` suffix and move to `archive/planning/`.
- `docs/`: Documentation. Each major topic should have a doc.

## 3. Workflows & Preferences
### User Preferences
- **PR Reviews**: Return reports as raw markdown files (e.g., `out/PR/Review.md`).

### Testing Context
- **Tooling**: We use `pytest` for backend tests.
- **Canonical runner**: `source .venv/bin/activate && python -m pytest tests/`
- **Philosophy**: Tests are encouraged for all new logic.

# App specific logic
See `./AGENT_APP_SPECIFIC.md`
