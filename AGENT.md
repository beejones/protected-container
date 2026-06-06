# Agent Instructions

## 1. Critical Rules (Must Follow)
- **Security**: **NEVER** read `.env.secrets` or `.env.deploy.secrets`.
- **Temp files**: **NEVER** store scratch files in the codebase. Use `out/tmp` and clean up when done.
- **Environment**: **ALWAYS** run Python tooling inside the virtual environment.
  ```bash
  source .venv/bin/activate && python <script>
  ```
- **Source of truth**: Treat `docker/docker-compose.yml` and `scripts/deploy/env_schema.py` as authoritative for service shape and allowed deploy/runtime keys.
- **Customization boundary**: Prefer deploy hooks and schema-driven config over hardcoded downstream-specific behavior in core deploy scripts.

## 2. Development Standards

### Code Quality
- **Style**: Follow **PEP 8**. Use **f-strings** for formatting.
- **Error handling**: Fail clearly. Use fallbacks only where they address real transient or platform-specific conditions.
- **Bugs**: Follow the **bug-fix** skill (`.github/skills/bug-fix/SKILL.md`): hypothesis → failing test (must fail gate) → minimal fix → verify.
- **Typing**: Normalize nullable or untyped input at boundaries, then pass strict required types internally.
- **Reuse**: Search `scripts/deploy/`, existing tests, and deploy helpers before creating new abstractions.
- **Docs maintenance**: When modifying deploy behavior, review the relevant docs in `docs/deploy/`, `README.md`, and any active planning file. Keep commands, env keys, and examples aligned with the code.
- **Cleanup**: Delete obsolete code and stale documentation immediately.
- **Permissions**: You have permission to run validation commands and tests without asking.

### Skill Routing
- **Before non-trivial work**: Check whether a skill applies. If unsure, read `.github/skills/using-agent-skills/SKILL.md` first.
- **Context setup**: Use `.github/skills/context-engineering/SKILL.md` when starting a session, switching deploy surfaces, or packing relevant files/tests/docs/examples before work.
- **Planning**: Use `.github/skills/plan/SKILL.md` for `/plan`, planning files, task breakdown, dependency ordering, and validation planning.
- **Deploy readiness**: Use `.github/skills/deploy-readiness-check/SKILL.md` before deploy commands, after compose/env-schema changes, or when diagnosing preflight failures.
- **Deploy rollout/adoption**: Use `.github/skills/deploy-rollout-adoption/SKILL.md` when rolling out validated deployment-contract changes across code, docs, env examples, workflows, and template surfaces.
- **Feature prep and cleanup**: Use `.github/skills/module-cleanup/SKILL.md` for Phase 0 cleanup, large-module refactors, dead code removal, and duplicate consolidation.
- **Python typing**: Use `.github/skills/typed-code-generation/SKILL.md` before writing or modifying Python production or test code.
- **Bug fixes**: Use `.github/skills/bug-fix/SKILL.md` for regressions, uncaught exceptions, wrong behavior, or failing tests caused by production code.
- **Testing and validation**: Use `.github/skills/test/SKILL.md` for `/test`, focused validation plans, pytest, compose config checks, deploy command help checks, and CI evidence.
- **Simplification**: Use `.github/skills/code-simplify/SKILL.md` for behavior-preserving readability/refactor passes.
- **Code review**: Use `.github/skills/review/SKILL.md` before merge or when reviewing agent/human changes.
- **API/interface design**: Use `.github/skills/api-interface-design/SKILL.md` for deploy hook contracts, env schema contracts, CLI args, compose labels, and service/API boundaries.
- **Frontend UI**: Use `.github/skills/frontend-ui-engineering/SKILL.md` for code-server, Portainer, docs-visible UI, or browser-facing deployment flows.
- **Browser runtime checks**: Use `.github/skills/browser-testing-with-devtools/SKILL.md` for real-browser DOM, console, network, screenshot, accessibility, and performance verification.
- **Security**: Use `.github/skills/security-hardening/SKILL.md` for secrets, env files, auth, Key Vault, GitHub Actions secrets, CORS, external inputs, or deploy-sensitive paths.
- **Performance**: Use `.github/skills/performance-optimization/SKILL.md` for measure-first deploy, build, validation, Docker, API, or browser performance work.
- **Docs/ADRs**: Use `.github/skills/documentation-and-adrs/SKILL.md` for docs maintenance, architecture rationale, public deploy contracts, and agent guidance updates.
- **Source-driven implementation**: Use `.github/skills/source-driven-development/SKILL.md` when framework/library/tool behavior must be verified against official docs.
- **PR and merge work**: Use `.github/skills/merge/SKILL.md` for PR reports, reviewer feedback, CI watching, mergeability checks, merging, and cleanup.

## 3. Project Context

### Project Overview
**Protected Container** is a deployment toolkit for running application payloads behind automatic HTTPS, with strict env-schema validation and parallel deploy paths for Ubuntu servers and Azure Container Instances.

Core concerns in this repo:
- Docker Compose as the service contract
- centralized Caddy routing for Ubuntu hosts
- Portainer-assisted or direct Compose Ubuntu deploys
- Azure ACI deploy generation from Compose
- schema-driven env/secrets handling
- hook-based downstream customization
- storage-manager integration through Compose labels

### File Organization
Do not store temporary files in the source tree. Use `out/` for temporary artifacts.

- `scripts/deploy/`: Core deployment logic, helpers, env schema, and deploy utilities.
- `docker/`: Compose files, Dockerfiles, startup scripts, proxy stack, and storage-manager assets.
- `docs/deploy/`: Deployment contracts, how-to guides, and customization docs.
- `tests/pytests/`: Python unit and integration tests.
- `planning/`: Active planning files. Plans must have checkable tasks and explicit phase exit criteria. Phase 0 should always be cleanup.
- `out/`: Temporary output files, including review artifacts under `out/PR/`.
- `.github/agents/` and `.github/skills/`: Repo-specific Copilot workflow customizations.

## 4. Workflows And Preferences

### Validation Context
- **Tooling**: We use `pytest` for Python tests.
- **Common focused checks**:
  ```bash
  source .venv/bin/activate && pytest -q tests/pytests/test_<module>.py
  source .venv/bin/activate && python3 scripts/deploy/validate_env.py
  source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py --help
  source .venv/bin/activate && python scripts/deploy/azure_deploy_container.py --help
  docker compose -f docker/docker-compose.yml config
  ```
- **CI baseline**: The GitHub Actions workflow currently runs `pytest` and Docker image build checks. Keep local validation aligned with the touched surface.
- **Philosophy**: Prefer the narrowest executable check that can falsify the change before running broader validation.

### Reviews
- **PR Reviews**: Return review artifacts as raw markdown files under `out/PR/`.

## 5. App-Specific Logic
See `./AGENT_APP_SPECIFIC.md`.