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

## Open Questions (resolve before Phase 2 execution)

These must be answered before the scaffold is run, because they cannot be inferred safely:

- [ ] **Target path / repo**: Confirm the new repo location is `/home/ronny/dev/hermes-agent`
      (it does not currently exist) and whether a remote (e.g. `github.com/beejones/hermes-agent`)
      already exists or must be created.
- [ ] **App payload**: What is the "hermes agent"? Confirm the upstream image name(s) the weekly
      `hermes` workflow should fetch and the resulting base image tag under `ghcr.io/beejones`
      (e.g. `ghcr.io/beejones/hermes-agent-base:latest`).
- [ ] **Web port / health**: What internal port does the hermes agent serve, and does it expose
      an HTTP endpoint for Caddy reverse-proxy + basic-auth gating?
- [ ] **Domain**: Confirm `hermes.zenia.eu` DNS already points at the Ubuntu Caddy host.
- [ ] **Submodule pin**: Which ref/branch of `protected-azure-container` should the submodule pin to.

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

### Phase 0 — Cleanup (module-cleanup skill, mandatory)
- [ ] Audit the scaffold-relevant slice in the toolkit (`scripts/deploy/`, `docker/`,
      `env.*.example`, `docs/deploy/`) for dead code / stale references that would be copied
      into or referenced by the new repo.
- [ ] Remove or fix any stale references the scaffold would propagate (e.g. `scripts/run_tests.py`
      mentioned in the prompt — confirm it exists or correct the reference).
- [ ] Consolidate any duplicated scaffold guidance across `docs/deploy/ADD_YOUR_APP.md`,
      `docs/ADD_YOUR_APP.md`, and `planning/`.
- [ ] Ensure focused tests still pass for touched toolkit helpers (if any toolkit file changes).
- [ ] Review `docs/deploy/` links/examples referenced by this plan for accuracy.
- [ ] Verify toolkit baseline is green (`pytest`, `validate_env.py`, compose `config`).

### Phase 1 — Repo skeleton & submodule
- [ ] Create `../hermes-agent` repo (git init + initial commit) at the confirmed path.
- [ ] Add `protected-azure-container` as submodule at `scripts/deploy/_protected_container`
      (pinned to the confirmed ref).
- [ ] Copy core files: `.github/` (excluding `workflows/deploy.yml`), `.gitignore`, `AGENT.md`,
      `LICENSE`.
- [ ] Copy `AGENT_APP_SPECIFIC.md` and rewrite it for the hermes agent app.
- [ ] Copy `env.*.example` and create the basic non-secret `.env*` working files
      (never create or copy `.env.secrets` / `.env.deploy.secrets`).
- [ ] Create `requirements.txt` sufficient to run the toolkit deploy scripts and tests.
- [ ] Create an initial `README.md` describing the app and the deploy flow.

### Phase 2 — Container shape (source of truth)
- [ ] Author `docker/docker-compose.ubuntu.yml` for the hermes agent: container name, the
      external `caddy` network, no published web host ports, app image, and `WEB_PORT`.
- [ ] Add `storage-manager.<n>.*` cleanup labels for the app's volumes.
- [ ] Set env values (`PUBLIC_DOMAIN=hermes.zenia.eu`, `WEB_PORT`, `PORTAINER_STACK_NAME`,
      image refs) in the new repo `.env.deploy` working file.

### Phase 3 — Deploy hooks & Caddy registration
- [ ] Implement `scripts/deploy/deploy_customizations.py` exporting `get_hooks()` with
      `build_deploy_plan` to set the hermes image/command/resources and storage registration.
- [ ] Wire hook discovery (`DEPLOY_HOOKS_MODULE` or default path) so `ubuntu_deploy.py` finds it.
- [ ] Confirm Caddy registration parameters (`PUBLIC_DOMAIN`, `WEB_PORT`, upstream name) are
      derived correctly for `hermes.zenia.eu`.

### Phase 4 — Workflows
- [ ] Copy CI workflow; confirm `deploy.yml` is intentionally excluded.
- [ ] Create `.github/workflows/hermes.yml`: weekly schedule (cron) that pulls the latest
      upstream hermes agent image(s) and pushes a base image to `ghcr.io/beejones`.

### Phase 5 — Validate
- [ ] `docker compose -f docker/docker-compose.ubuntu.yml config` renders cleanly.
- [ ] `python scripts/deploy/_protected_container/scripts/deploy/validate_env.py` passes for
      the new repo env files.
- [ ] `ubuntu_deploy.py --help` resolves through the submodule.
- [ ] Hook unit test (in the new repo) for `build_deploy_plan`.
- [ ] Dry-run / non-destructive deploy validation against the Ubuntu host (no prod changes
      without confirmation).

### Phase 6 — Docs & finalize
- [ ] README documents prerequisites, submodule init, env setup, and the deploy command.
- [ ] Update this plan with deviations and remaining work; archive only when complete.

---

## Phase Exit Criteria

- **Phase 0**: module-cleanup exit criteria met — no dead code/stale references the scaffold
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

- [ ] Add `.venv` and submodule init instructions to README so deploy scripts run.
- [ ] Confirm whether `scripts/run_tests.py` exists in the toolkit or whether the README/prompt
      should reference `pytest` directly.
- [ ] Decide GHCR auth approach for the weekly `hermes` workflow (PAT vs `GITHUB_TOKEN` scope to
      `ghcr.io/beejones`).
- [ ] Ensure no `.env.secrets` / `.env.deploy.secrets` are ever created or committed.