# Ubuntu Centralized Caddy Deployment Plan

This plan tracks the work to transition the deployment architecture from a per-stack Caddy sidecar to a centralized Caddy TLS terminator and router, alongside Portainer for container management.

## Review Comments & Additions (2026-02-22)

These additions tighten migration safety, make the docs executable, and reduce ambiguity during rollout.

- **Add explicit prerequisites** before implementation:
   - DNS records for each routed host (including Portainer host if exposed via Caddy).
   - Host firewall allows only `80/tcp` and `443/tcp` publicly.
   - External Docker network name is standardized to `caddy`.
- **Add migration safety** as first-class work:
   - Keep compatibility for existing deployments until central proxy is confirmed healthy.
   - Define cutover order (bring up central Caddy → validate routes → remove sidecar references).
- **Add rollback plan**:
   - Re-enable previous compose pattern quickly if centralized routing fails.
   - Preserve previous compose artifacts until verification passes.
- **Strengthen verification**:
   - Validate HTTP→HTTPS redirect.
   - Validate authenticated access for app and Portainer routes.
   - Validate certificate issuance/renewal logs in Caddy.
- **Clarify documentation targets**:
   - Update `docs/deploy/UBUNTU_SERVER.md` and `README.md` so users do not follow stale sidecar guidance.

## Advantages of the New Architecture
- **Improved Security**: Only ports 80 and 443 are exposed on the host. Internal services like Portainer (9000/9443) are routed securely through Caddy, hiding them from direct external access.
- **Resource Efficiency**: A single Caddy container handles traffic and TLS certificates for all services on the host, preventing the overhead of running multiple sidecar proxies.
- **Simplified Deployment**: Downstream projects do not need their own TLS or routing configurations; they simply attach to the shared Docker network.
- **Centralized Management**: All routing rules and certificates are managed centrally in one `Caddyfile`.

## Task Checklist

### Phase 0 — Refactoring & Cleanup
- [x] Remove all unused, unnecessary, or obsolete code.
- [x] Identify and refactor duplicate logic into reusable helpers.
- [x] Ensure no file exceeds 1000 lines. Create `<name>_helpers` and add `pytest` tests if not existing.
- [x] Ensure files follow PEP 8 and maintainability standards.
- [x] Keep refactoring strictly in scope for deployment-path code/docs touched by this migration.

### Phase 1 — Remove Caddy Sidecar & Setup Central Proxy Configs
- [x] Modify `docker/docker-compose.yml` to remove sidecar, volumes, and add external network.
- [x] Create `docker/proxy/docker-compose.yml` for the central proxy.
- [x] Move and modify `docker/Caddyfile` to `docker/proxy/Caddyfile` with routes for portainer and protected-container.
- [x] Delete `docker/docker-compose.shared-caddy.yml` and `docker/Caddyfile.multiapp.example`.
- [x] Add a temporary rollback note describing how to restore prior sidecar behavior if cutover fails.
- [x] Ensure service/container naming in central proxy config does not collide with existing stack names.

### Phase 2 — Document Portainer & Centralized Caddy Setup
- [x] Document Portainer installation without exposed host ports via the `caddy` network.
- [x] Document Centralized Caddy installation via `docker/proxy/docker-compose.yml` and global network creation.
- [x] Document how to deploy the `protected-container` through Portainer on this setup.
- [x] Document DNS and firewall prerequisites explicitly before installation steps.
- [x] Document certificate troubleshooting (ACME failures, rate limits, and log inspection commands).

### Phase 3 — Document Shared Routing for Downstream Projects
- [x] Create `docs/deploy/SHARED_CADDY_ROUTING.md`.
- [x] Explain how downstream projects join the `caddy` network.
- [x] Explain how to add new routing blocks to the central `docker/proxy/Caddyfile` and reload Caddy.
- [x] Add a route naming convention (`<service>-<env>` labels/hostnames) to prevent collisions.
- [x] Add a safe reload and validation sequence for Caddyfile changes.

### Phase 4 — Verification
- [x] Verify local builds and compose files (`docker compose config`).
- [x] Validate markdown file formatting.
- [x] Run test suite to ensure no regressions.
- [x] Run smoke checks for app and Portainer through centralized Caddy over HTTPS.
- [x] Verify only ports 80/443 are public and Portainer is not directly exposed.
- [x] Capture rollback test result (ability to restore prior state quickly).

---

## Phase 0 — Refactoring & Cleanup

Perform the routine code cleanup and refactoring as defined in `AGENT.md` and `docs/CODE_PROMPTS.md`.

**Tasks:**
1. Remove all unused, unnecessary, or obsolete code.
2. Identify and refactor duplicate logic into reusable helpers.
3. Ensure no file exceeds 1000 lines. Create `<name>_helpers` and add `pytest` tests if not existing.
4. Ensure files follow PEP 8 and maintainability standards.

**Exit Criteria:**
- The codebase is clean, well-tested, and adheres to the guidelines in `AGENT.md`.

---

## Phase 1 — Remove Caddy Sidecar & Setup Central Proxy Configs

We are dropping the sidecar Caddy completely and creating bootstrap configurations for the central proxy.

**Tasks:**
1. Modify `docker/docker-compose.yml`:
   - Delete the `caddy` service.
   - Delete `caddy_data` and `caddy_config` volumes.
   - Add an external `caddy` network and attach the `app` service to it, so the central proxy can route traffic to `protected-container:8080`.
2. Move `/ Repurpose` Caddyfile:
   - Create `docker/proxy/docker-compose.yml` to define the central proxy stack (Caddy container bound to host ports 80 and 443).
   - Move `docker/Caddyfile` to `docker/proxy/Caddyfile`. This will be the master routing file.
   - Update `docker/proxy/Caddyfile` to route traffic to both `portainer:9000` and `protected-container:8080`.
3. Delete obsolete files:
   - `docker/docker-compose.shared-caddy.yml`
   - `docker/Caddyfile.multiapp.example`

**Exit Criteria:**
- `docker compose -f docker/docker-compose.yml config` and `docker compose -f docker/proxy/docker-compose.yml config` are valid.
- The `app` service is no longer coupled to a sidecar proxy.
- A documented rollback path exists and has been dry-run locally.

---

## Phase 2 — Document Portainer & Centralized Caddy Setup

Create or update deployment documentation (`docs/deploy/UBUNTU_SERVER.md`) to reflect the new server baseline setup.

**Tasks:**
1. Document Portainer installation:
   - Provide the Docker CLI command to stand up Portainer on the `caddy` network so it does not need host ports exposed.
2. Document the Centralized Caddy installation:
   - Explain how to use `docker/proxy/docker-compose.yml` to start the central proxy.
   - Show how the central Caddy binds to 80/443 and mounts `docker/proxy/Caddyfile`.
   - Explain the creation of the global `caddy` docker network.
3. Show how to deploy the `protected-container` through Portainer.

**Exit Criteria:**
- A clear, copy-pasteable guide exists for setting up the secure server infrastructure from scratch.
- DNS/firewall prerequisites and certificate troubleshooting are documented.

---

## Phase 3 — Document Shared Routing for Downstream Projects

**Tasks:**
1. Create `docs/deploy/SHARED_CADDY_ROUTING.md`.
2. Explain how *any* new project can leverage the central Caddy:
   - The new project's `docker-compose.yml` must join the external `caddy` network.
   - The server administrator adds a new routing block to the central `docker/proxy/Caddyfile` (e.g., `app.example.com { reverse_proxy new-app:3000 }`).
   - Reload the central caddy container (`docker exec -it caddy caddy reload -c /etc/caddy/Caddyfile`).

**Exit Criteria:**
- Step-by-step instructions are available for downstream projects to integrate into the routing layer.
- The doc includes route collision-avoidance conventions and safe reload validation.

---

## Phase 4 — Verification

**Tasks:**
1. Verify local builds and compose files.
2. Validate that markdown files format properly.
3. Run test suite to ensure no regressions from Phase 0.

**Exit Criteria:**
- Documentation accurately reflects the centralized architecture.
- Tests pass.
- HTTPS, auth, and exposure boundaries are verified with explicit smoke-check commands.

---

## Rollout Notes (Added)

Use this order for safer migration:

1. Create/verify external `caddy` network.
2. Start centralized Caddy stack from `docker/proxy/docker-compose.yml`.
3. Validate central routes for app + Portainer.
4. Update app stack to sidecar-free compose.
5. Remove obsolete sidecar files only after successful validation.

Rollback trigger examples:

- Central Caddy cannot issue certs.
- Portainer route unavailable through Caddy.
- App route returns persistent 5xx.

Rollback action:

- Restore previous compose file set and redeploy with prior sidecar topology.
