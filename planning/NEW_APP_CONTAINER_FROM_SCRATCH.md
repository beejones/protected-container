# Plan: New App Container From Scratch (`hermes-agent`)

## Principles

A new downstream application repository must be a **thin consumer** of this deployment
toolkit, never a divergent fork of it. The toolkit (`protected-azure-container`) is
embedded as a **git submodule** and is the single source of deployment behavior; the new
repo only contributes app-specific Compose shape, env values, deploy **hooks**, and docs.
Every deployment contract is preserved: `docker/docker-compose.ubuntu.yml` is the truth
for the deployed container, the centralized Caddy proxy is the only public ingress,
storage-manager cleanup lives in Compose labels, and `env_schema.py` governs allowed keys.
Customization happens through `deploy_customizations.py` hooks, not by editing toolkit code.
The scaffold must be reproducible, idempotent where possible, and leave no secrets in Git.

> Cross-repo note: the **deliverable artifact** of this plan is the scaffolded new repo at
> `../hermes-agent`. This planning file and the toolkit changes (if any) live in
> `protected-azure-container`. Toolkit code is treated as read-only/source-of-truth and is
> only modified if a genuine reusable gap is found (and then via the normal contracts).

---

## Source Prompt (verbatim driving instructions)

> We are going to build a new repo based on our current repo in `../hermes-agent`.
> We start by copying our core repo files to the new repo we are creating. Copy:
> - `.github/` (skip `.github/workflows/deploy.yml`)
> - `.gitignore`
> - `AGENT.md`
> - `AGENT_APP_SPECIFIC.md` and update for the new APP
> - `LICENSE`
> - `env.*.example` and create the basic `.env*` files
>
> Use this repo as a git submodule in `scripts/deploy/_protected_container`.
>
> See `docs/deploy`. We want to use `scripts/deploy/ubuntu_deploy.py` to deploy the new repo
> to our Ubuntu Portainer host. Create the necessary hooks to be able to deploy our new
> container and make sure it is running at `hermes.zenia.eu` leveraging our Caddy proxy and
> storage-manager. We need to properly register our new container to the Caddy environment.
>
> `docker/docker-compose.ubuntu.yml` is the truth for the container we deploy.
>
> Create an initial `README.md`.
>
> Create an initial `requirements.txt` (needed to run `scripts/run_tests.py` and the
> `scripts/deploy` scripts).
>
> Create a GitHub workflow called `hermes` that runs every week, fetches the latest hermes
> agent images, and stores them in `ghcr.io/beejones` as the base hermes image.
>
> Plus any other missed steps.

---

## Open Questions (RESOLVED — decisions recorded)

The user was unavailable during execution and instructed the agent to proceed
autonomously with good defaults, later confirming the upstream image. Decisions:

- [x] **Target path / repo**: `/home/ronny/dev/hermes-agent` (exists, empty scaffold dirs).
      Git is initialized **locally only**; no remote is created/pushed in this scope.
- [x] **App payload / upstream image**: upstream is `docker.io/nousresearch/hermes-agent:latest`
      (confirmed by user). The weekly `hermes` workflow re-publishes it as the base image
      `ghcr.io/beejones/hermes-agent-base:latest`. Upstream ref is overridable via the
      `HERMES_UPSTREAM_IMAGE` workflow/repo variable.
- [x] **Web port**: `WEB_PORT=8080` (assumption; adjust if the hermes image serves elsewhere).
      Caddy reverse-proxies `hermes.zenia.eu` → `hermes-agent-production:8080` behind basic-auth.
- [x] **Domain**: `PUBLIC_DOMAIN=hermes.zenia.eu` (assumed DNS already points at the Caddy host).
- [x] **Submodule pin**: `git@github.com:beejones/protected-azure-container.git`, pinned to `main`,
      mounted at `scripts/deploy/_protected_container` (per prompt).

---

## Affected Deploy Surfaces

- **New repo scaffold** (`../hermes-agent`): all of it.
- **Git submodule**: `scripts/deploy/_protected_container` -> this toolkit.
- **Local Docker / Ubuntu deploy**: `docker/docker-compose.ubuntu.yml` in the new repo.
- **Caddy shared routing**: registration via `ubuntu_deploy.py` for `hermes.zenia.eu`.
- **Storage-manager**: Compose labels on the new app service.
- **Hooks**: `scripts/deploy/deploy_customizations.py` in the new repo.
- **Env schema**: new repo `.env*` values validated against the toolkit `env_schema.py`.
- **Workflows**: new repo `.github/workflows/` (CI copied, `deploy.yml` skipped, new `hermes.yml`).
- **Docs**: new repo `README.md` and any app-specific deploy notes.

---

## Checkable Task Overview

### Phase 0 — Cleanup (code-cleanup skill, mandatory)
- [x] Audit the scaffold-relevant slice in the toolkit (`scripts/deploy/`, `docker/`,
      `env.*.example`, `docs/deploy/`) for dead code / stale references that would be copied
      into or referenced by the new repo. (Audited file sizes + grepped for `run_tests.py`,
      `_protected_container`, cross-doc refs.)
- [x] Remove or fix any stale references the scaffold would propagate (e.g. `scripts/run_tests.py`
      mentioned in the prompt — confirm it exists or correct the reference). (`scripts/run_tests.py`
      is intentionally a downstream/template runner — present in the new repo and sibling repos,
      NOT a toolkit file; no toolkit reference to fix.)
- [x] Consolidate any duplicated scaffold guidance across `docs/deploy/ADD_YOUR_APP.md`,
      `docs/ADD_YOUR_APP.md`, and `planning/`. (Found `docs/ADD_YOUR_APP.md` was a byte-for-byte
      duplicate of `docs/deploy/ADD_YOUR_APP.md` with no live references — README links only the
      `docs/deploy/` copy. Removed the orphaned root duplicate; commit `2f7d538`.)
- [x] Ensure focused tests still pass for touched toolkit helpers (no toolkit helper code changed;
      full suite run as the regression check below).
- [x] Review `docs/deploy/` links/examples referenced by this plan for accuracy. (README link to
      `docs/deploy/ADD_YOUR_APP.md` remains valid after the duplicate removal; no broken links.)
- [x] Verify toolkit baseline is green (`pytest` 171 passed, compose `config` OK; `validate_env.py`
      requires populated secret env files and is exercised in the deploy flow, not this baseline).

### Phase 1 — Repo skeleton & submodule
- [x] Create `../hermes-agent` repo (git init + initial commit) at the confirmed path.
- [x] Add `protected-azure-container` as submodule at `scripts/deploy/_protected_container`
      (pinned to the confirmed ref).
- [x] Copy core files: `.github/` (excluding `workflows/deploy.yml`), `.gitignore`, `AGENT.md`,
      `LICENSE`.
- [x] Copy `AGENT_APP_SPECIFIC.md` and rewrite it for the hermes agent app.
- [x] Copy `env.*.example` and create the basic non-secret `.env*` working files
      (never create or copy `.env.secrets` / `.env.deploy.secrets`).
- [x] Create `requirements.txt` sufficient to run the toolkit deploy scripts and tests.
- [x] Create an initial `README.md` describing the app and the deploy flow.

### Phase 2 — Container shape (source of truth)
- [x] Author `docker/docker-compose.ubuntu.yml` for the hermes agent: container name, the
      external `caddy` network, no published web host ports, app image, and `WEB_PORT`.
- [x] Add `storage-manager.<n>.*` cleanup labels for the app's volumes.
- [x] Set env values (`PUBLIC_DOMAIN=hermes.zenia.eu`, `WEB_PORT`, `PORTAINER_STACK_NAME`,
      image refs) in the new repo `.env.deploy` working file.
- [x] Create `docker/Dockerfile` so the deploy build/push step has a build target. The
      `ubuntu_deploy.py` Step 2 ("Building and pushing APP_IMAGE locally") runs
      `docker build -f docker/Dockerfile -t $APP_IMAGE docker/` and previously failed with
      "Dockerfile not found". The Dockerfile is a thin layer `FROM` the weekly base image
      (`BASE_IMAGE=ghcr.io/beejones/hermes-agent-base:latest`) built into a **distinct** app
      tag (`APP_IMAGE=ghcr.io/beejones/hermes-agent:latest`) so the weekly base is never
      clobbered. Aligned `.env.deploy` (APP_IMAGE/BASE_IMAGE/DOCKERFILE), compose default image,
      README, and `AGENT_APP_SPECIFIC.md`. (Alternative: `--skip-build-push` / `UBUNTU_BUILD_PUSH=false`
      to deploy the base image directly without a build.)

### Phase 3 — Deploy hooks & Caddy registration
- [x] Implement `scripts/deploy/deploy_customizations.py` exporting `get_hooks()` with
      `build_deploy_plan` to set the hermes image/command/resources and storage registration.
- [x] Wire hook discovery (`DEPLOY_HOOKS_MODULE` or default path) so `ubuntu_deploy.py` finds it.
- [x] Confirm Caddy registration parameters (`PUBLIC_DOMAIN`, `WEB_PORT`, upstream name) are
      derived correctly for `hermes.zenia.eu`.

### Phase 4 — Workflows
- [x] Copy CI workflow; confirm `deploy.yml` is intentionally excluded.
- [x] Create `.github/workflows/hermes.yml` as the **weekly fetch CI**: a `schedule` (cron
      `17 4 * * 1`) that fetches the latest upstream hermes agent image and copies it to
      `ghcr.io/beejones/hermes-agent-base` (`:latest` + a dated tag). The same workflow is
      **idempotent on manual runs**: it checks GHCR with `docker manifest inspect` and only
      fetches+copies when the base image is missing (bootstrap/ensure-exists), unless
      `force=true` is passed. This guarantees a first deploy can always pull the base, and the
      weekly run keeps it current. Upstream source overridable via `HERMES_UPSTREAM_IMAGE`.

### Phase 5 — Validate
- [~] **Run the `hermes.yml` CI to publish the base image to GHCR** (operator-run, in progress).
      Trigger the workflow (`workflow_dispatch`, or wait for the weekly `schedule`) so it fetches
      the upstream hermes agent image and copies it to
      `ghcr.io/beejones/hermes-agent-base:latest` (+ dated tag). This is the **bootstrap step**
      that makes the base image exist before the first deploy can build `APP_IMAGE` (the
      Dockerfile is `FROM` the base). The user reports the workflow is already running. Verify
      success afterwards with `docker manifest inspect ghcr.io/beejones/hermes-agent-base:latest`
      (or by confirming the package appears under `ghcr.io/beejones`).
- [x] `docker compose -f docker/docker-compose.ubuntu.yml config` renders cleanly.
- [ ] `python scripts/deploy/_protected_container/scripts/deploy/validate_env.py` passes for
      the new repo env files. (Pending: requires `.env.secrets`/`.env.deploy.secrets` with
      real values; deferred to the operator.)
- [x] `ubuntu_deploy.py --help` resolves through the submodule.
- [x] Hook unit test (in the new repo) for `build_deploy_plan`.
- [ ] Dry-run / non-destructive deploy validation against the Ubuntu host (no prod changes
      without confirmation). (Deferred: needs SSH host + operator confirmation.)

### Phase 6 — Docs & finalize
- [x] README documents prerequisites, submodule init, env setup, and the deploy command.
- [ ] Update this plan with deviations and remaining work; archive only when complete.

---

## Phase Exit Criteria

- **Phase 0**: code-cleanup exit criteria met — no dead code/stale references the scaffold
  would propagate, docs accurate, toolkit validations green.
- **Phase 1**: new repo exists, submodule initialized, core files present, `AGENT_APP_SPECIFIC.md`
  rewritten for hermes, `requirements.txt` + `README.md` present, no secret files created.
- **Phase 2**: `docker/docker-compose.ubuntu.yml` validates and joins the `caddy` network with
  storage-manager labels and no public web host ports.
- **Phase 3**: hooks load via the toolkit loader and `build_deploy_plan` produces the hermes
  plan; Caddy registration params resolve to `hermes.zenia.eu`.
- **Phase 4**: CI present, `deploy.yml` excluded, `hermes.yml` schedules weekly image refresh to
  `ghcr.io/beejones`.
- **Phase 5**: all listed validations pass; no destructive prod deploy performed without explicit
  confirmation.
- **Phase 6**: README and this plan are accurate; plan archived only when all boxes checked.

---

## Validation Commands

Run from the **new repo** root (`../hermes-agent`), using the toolkit via the submodule:

```bash
# Compose is the truth for the deployed container
docker compose -f docker/docker-compose.ubuntu.yml config

# Env schema validation through the submodule
source .venv/bin/activate && \
  python3 scripts/deploy/_protected_container/scripts/deploy/validate_env.py

# Deploy CLI resolves through the submodule
source .venv/bin/activate && \
  python scripts/deploy/_protected_container/scripts/deploy/ubuntu_deploy.py --help

# Focused hook test (new repo)
source .venv/bin/activate && pytest -q tests/pytests/test_deploy_customizations.py
```

Toolkit baseline checks (run in `protected-azure-container` if any toolkit file changes):

```bash
source .venv/bin/activate && pytest
source .venv/bin/activate && python3 scripts/deploy/validate_env.py
docker compose -f docker/docker-compose.yml config
```

---

## Docs To Update

- New repo `README.md` (created in Phase 1, finalized in Phase 6).
- New repo `AGENT_APP_SPECIFIC.md` (rewritten for hermes).
- This planning file (kept truthful through Stage 4).
- Reference (do not duplicate): toolkit `docs/deploy/SHARED_CADDY_ROUTING.md`,
  `docs/deploy/HOOKS.md`, `docs/deploy/STORAGE_MANAGER.md`, `docs/deploy/UBUNTU_SERVER.md`,
  `docs/deploy/ENV_SCHEMA.md`.

---

## Other / Missed Steps (tracked)

- [x] Add `.venv` and submodule init instructions to README so deploy scripts run.
- [x] `scripts/run_tests.py` ships in the new repo (shared template runner, also present in
      sibling repos). It runs backend tests from `tests/pytests` and UI tests from `tests/UI`.
      Validated via `python scripts/run_tests.py --backend-only` (PASS). `requirements.txt`
      covers both the backend and UI (playwright) paths.
- [x] Decide GHCR auth approach for the weekly `hermes` workflow. **Decision:** keep the
      `GITHUB_TOKEN` + `packages: write` default, which pushes to `ghcr.io/<repo-owner>` and works
      when the hermes-agent repo is owned by `beejones`. If `ghcr.io/beejones` is a different
      owner/org than the repo, the operator must add a PAT with `write:packages` as the
      `HERMES_GHCR_TOKEN` repo secret and switch the workflow login to use it. Documented as an
      operator follow-up; no code change needed for the common (same-owner) case.
- [x] Ensure no `.env.secrets` / `.env.deploy.secrets` are ever created or committed
      (verified via `git check-ignore`; only `*.example` secret templates are tracked).