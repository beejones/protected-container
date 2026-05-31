# Plan: Initial Working Hermes Environment

## Principles

The Hermes deployment must be a web-serving container, not an interactive CLI process that
exits under Portainer. `hermes.zenia.eu` is served only through the shared Caddy proxy, so the
application container must stay running, listen on the configured internal `WEB_PORT`, and share
the external `caddy` Docker network with the proxy. The fix should live in the downstream
`hermes-agent` repo through its Dockerfile, Compose files, env values, hooks, and docs; the
deployment toolkit stays the source of truth and is changed only if a reusable toolkit gap is
found.

The current failure is HTTP 502 from Caddy while the Portainer log shows the upstream Hermes image
starting an interactive session (`Welcome to Hermes Agent! Type your message...`), warning that
stdin is not a terminal, then shutting down s6 services. That strongly suggests the deployed
container is not running a long-lived HTTP/dashboard process on `WEB_PORT`.

---

## Affected Deploy Surfaces

- **Hermes app image**: `../hermes-agent/docker/Dockerfile` must set a deterministic runtime
  command or entrypoint for the web/dashboard process.
- **Compose source of truth**: `../hermes-agent/docker/docker-compose.yml` and
  `../hermes-agent/docker/docker-compose.ubuntu.yml` must expose the real internal HTTP port and
  keep the app on the `caddy` network.
- **Deploy env**: `../hermes-agent/.env.deploy` must use the correct `WEB_PORT`, app image,
  stack name, and public domain.
- **Deploy hooks**: `../hermes-agent/scripts/deploy/deploy_customizations.py` should validate the
  resolved domain, port, image, and upstream name without overriding shared toolkit behavior.
- **Caddy route**: the shared proxy must point `hermes.zenia.eu` at the live app container name and
  port.
- **Docs**: `../hermes-agent/README.md`, `../hermes-agent/AGENT_APP_SPECIFIC.md`, and this plan
  must capture the final runtime command, port, and verification steps.

---

## Checkable Task Overview

### Phase 0 - Cleanup And Runtime Audit

- [ ] Audit the Hermes downstream runtime slice: `docker/Dockerfile`, Compose files, deploy hooks,
      README, and `AGENT_APP_SPECIFIC.md` for stale assumptions that the upstream default command
      is web-ready.
- [ ] Inspect the published base image metadata (`Entrypoint`, `Cmd`, exposed ports, labels) and
      record what the image actually starts by default.
- [ ] Inspect the deployed Portainer container state, logs, and restart history to confirm whether
      the app exits or stays running without listening on `WEB_PORT`.
- [ ] Identify duplicate or conflicting runtime descriptions across README, app-specific agent
      docs, and planning notes; consolidate around the verified web/dashboard command.
- [ ] Record whether any toolkit behavior is implicated. Expected result: no toolkit change unless
      Caddy registration or compose rendering points at the wrong upstream after the app is healthy.

### Phase 1 - Find The Correct Hermes Web Runtime

- [ ] Run the base image locally with its default command and confirm it reproduces the interactive
      CLI / non-terminal shutdown behavior.
- [ ] Discover supported Hermes commands, services, or supervisor targets that start a persistent
      HTTP dashboard/API process. Check image help output, process supervisor configuration, and
      upstream docs or image labels as needed.
- [ ] Determine the real HTTP listen port and bind address. The process must bind to `0.0.0.0`, not
      only `127.0.0.1`, so Caddy can reach it from the Docker network.
- [ ] Decide the runtime contract: either keep `WEB_PORT=8080` if Hermes serves there, or update
      `WEB_PORT` and docs to the verified port.

### Phase 2 - Make The App Image Web-Serving

- [ ] Update `../hermes-agent/docker/Dockerfile` to set the verified long-running web/dashboard
      command or entrypoint instead of inheriting the interactive CLI default.
- [ ] Add any small app-specific config needed by that command under the Docker build context.
- [ ] Keep the image thin: continue using `ARG BASE_IMAGE=ghcr.io/beejones/hermes-agent-base:latest`
      and avoid copying large upstream payloads into the downstream repo.
- [ ] If the upstream image has no usable HTTP/dashboard mode, add a minimal wrapper service only
      after documenting that finding and confirming the intended user-facing behavior.

### Phase 3 - Align Compose, Env, And Hooks

- [ ] Update Compose `expose` and `.env.deploy` `WEB_PORT` to the verified internal HTTP port.
- [ ] Confirm `PORTAINER_STACK_NAME` matches the actual app `container_name` used by Caddy.
- [ ] Ensure the app joins the external `caddy` network and does not publish public host ports.
- [ ] Keep storage-manager labels and volumes intact unless the verified runtime uses a different
      data path.
- [ ] Add or update a hook test proving `build_deploy_plan` resolves the expected domain, upstream,
      image, and port.

### Phase 4 - Validate Locally Before Redeploy

- [ ] Build the downstream app image from `../hermes-agent/docker/Dockerfile` using the GHCR base
      image.
- [ ] Run the app image locally with the Compose configuration and confirm the container remains
      running.
- [ ] From another container on the same Docker network, curl the app on `http://<container>:WEB_PORT`
      and confirm an HTTP response from Hermes.
- [ ] Run `docker compose -f docker/docker-compose.yml -f docker/docker-compose.ubuntu.yml config`
      from the Hermes repo and confirm the rendered port, image, container name, labels, and
      networks match the deployment contract.
- [ ] Run the focused Hermes hook tests.

### Phase 5 - Redeploy And Verify Portainer/Caddy

- [ ] Push the updated Hermes app image to `ghcr.io/beejones/hermes-agent:latest` through the normal
      deploy build/push path.
- [ ] Redeploy the Portainer stack with `ubuntu_deploy.py --prod` after local validation passes.
- [ ] Confirm the Portainer container is healthy/running and no longer logs the interactive CLI
      goodbye / s6 shutdown path.
- [ ] Confirm the app is reachable from the Caddy container or Docker network at the expected
      upstream and port.
- [ ] Confirm `https://hermes.zenia.eu` returns the expected Hermes web response rather than HTTP
      502.
- [ ] If Caddy still returns 502 while the app is healthy, inspect Caddy route registration,
      upstream container name, network membership, and Caddy logs before changing toolkit code.

### Phase 6 - Document And Finalize

- [ ] Update the Hermes README with the verified command, internal port, local smoke test, and
      deploy verification steps.
- [ ] Update `AGENT_APP_SPECIFIC.md` with the runtime contract so future agents do not revert to
      the interactive CLI default.
- [ ] Update this plan with findings, validation evidence, and any remaining operator-only work.
- [ ] Archive or mark this plan complete only after `hermes.zenia.eu` is reachable through Caddy.

---

## Phase Exit Criteria

- **Phase 0**: the failing runtime assumption is identified, documented, and scoped to Hermes
  downstream files unless evidence shows a toolkit gap.
- **Phase 1**: the correct long-running Hermes web/dashboard command, bind address, and port are
  known.
- **Phase 2**: the downstream Dockerfile produces an app image that starts the web runtime by
  default.
- **Phase 3**: Compose, env, and hooks agree on image, container name, domain, network, and port.
- **Phase 4**: local container and compose smoke checks prove the app stays running and responds over
  HTTP on the Docker network.
- **Phase 5**: Portainer and Caddy serve `https://hermes.zenia.eu` without HTTP 502.
- **Phase 6**: docs and this plan accurately describe the final working runtime.

---

## Validation Commands

Run from `../hermes-agent` unless noted otherwise:

```bash
# Inspect the base image runtime metadata
docker image inspect ghcr.io/beejones/hermes-agent-base:latest \
  --format '{{json .Config.Entrypoint}} {{json .Config.Cmd}} {{json .Config.ExposedPorts}}'

# Render the deployment source of truth
docker compose -f docker/docker-compose.yml -f docker/docker-compose.ubuntu.yml config

# Build the downstream app image
docker build -f docker/Dockerfile -t ghcr.io/beejones/hermes-agent:local docker/

# Run focused hook tests
source .venv/bin/activate && pytest -q tests/pytests/test_deploy_customizations.py

# Deploy after local validation succeeds
source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py --prod
```

Remote verification examples after deploy:

```bash
# From the Portainer host, confirm the app is running and on the caddy network
docker ps --filter name=hermes-agent
docker network inspect caddy

# From the Caddy network, confirm the upstream responds before blaming Caddy
docker run --rm --network caddy curlimages/curl:latest \
  -fsS http://hermes-agent-production:${WEB_PORT:-8080}/

# Public route check
curl -I https://hermes.zenia.eu
```

---

## Known Failure Evidence

- Public route currently returns HTTP 502 for `https://hermes.zenia.eu`.
- Portainer logs show the upstream image entering an interactive prompt, warning that stdin is not
  a terminal, then stopping s6 services:
  - `Welcome to Hermes Agent! Type your message or /help for commands.`
  - `Warning: Input is not a terminal (fd=0).`
  - `Goodbye!`
  - `s6-rc: info: service ... stopping`

This evidence points first at the app runtime command, not at Caddy itself. Caddy should be
investigated only after the Hermes container is proven to stay up and answer HTTP on the Docker
network.