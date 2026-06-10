# Plan: Central Caddy OIDC Edge Auth

## Principles

- Caddy is the only public ingress for protected app routes; app containers must not publish direct public host ports.
- Route protection is a shared proxy contract, not a per-app convention hidden in downstream docs.
- Basic Auth remains a rollback or break-glass path until the OIDC edge-auth path is staged, validated, and documented as the default.
- Identity headers are display/audit identity unless paired with a signed, audience-scoped assertion verified by the app.
- Secrets stay in env files, secret stores, or gateway-managed stores; generated Caddy config and docs must use placeholders or secret references only.
- Validation evidence must prove both route protection and no-direct-access assumptions before local app auth is relaxed.

## Overview

Replace the centralized Caddy Basic Auth edge gate with identity-aware protection for every public app route managed by protected-container's central Caddy proxy. Caddy remains the only public TLS and routing entrypoint, but it delegates login, session validation, user approval, and identity proof creation to an auth gateway or identity broker.

Caddy can protect all containers published underneath it only when those containers are reachable exclusively through Caddy-owned site blocks. A container is not protected merely because it joins the Docker `caddy` network. Every protected app container must be unreachable from outside the Docker/private network except through the Caddy gate, and every public site block must import the same protected-route contract.

For upstream containers, the plan introduces a Container Auth Contract. Caddy strips spoofable incoming identity/proof headers, runs the auth check, and forwards authenticated-user information to the app. If an app needs cryptographic proof, Caddy forwards a signed assertion produced by the auth gateway or a dedicated assertion service. Stock Caddy does not natively re-sign JWT payloads or mint per-app signed OIDC/JWT payloads from a Caddyfile. That separation is intentional: signing keys should not live in Caddy, so a Caddy compromise does not automatically let an attacker mint valid app assertions.

## Scope

- Goal: All Caddy-published app routes are protected by the central auth contract, authenticated user information is available to upstream containers, and new users are explicitly approved before reaching protected apps.
- Goal: Downstream containers have a documented path to replace local password/access-key login with central Caddy identity after proof verification is implemented.
- Goal: Caddy registration can declare per-app auth requirements such as audience, proof level, callback/redirect behavior, and optionally a secret reference for app-specific token signing.
- Non-goals: Protecting services that bypass Caddy, committing provider secrets, exposing app host ports, or requiring every downstream app to validate signed tokens in the first rollout slice.
- User-facing behavior: Anonymous users are redirected to a configured login provider. Authenticated-but-unapproved users see an access-request page with a Create Account / Request Access action, but no active local account is created until approval succeeds. Approvals go to `AUTH_APPROVER_EMAIL`, defaulting to `ACME_EMAIL`; on this server that is expected to be `ronny.bjones@hotmail.com` through env configuration.
- Affected areas: central proxy stack, reusable Caddy auth snippets, Caddy registration helper, auth gateway configuration, env schema, env examples, shared routing docs, downstream container docs, stock-dashboard wrapper/docs/tests, deployed-route smoke tests, and operator runbooks.

## Detailed Change Map

- Proxy topology: add one central auth gateway/broker service to the protected-container proxy stack; do not add one auth sidecar per app.
- Caddyfile: add reusable protected-route snippets, auth-gateway routes, callback/login routes, and per-app imports.
- Registration: extend `caddy_register.py` from `domain -> service:port` to an auth-aware contract with policy, audience, proof level, and secret reference metadata.
- User store: keep authorized users in the selected auth gateway/broker store, not in Caddy. For a broker such as Authentik or Keycloak this will be the broker database; for Authelia/OAuth2 Proxy it may be a file-backed or external directory/identity-store model.
- Provisioning: add an operator script to pre-provision approved users/groups/policies before first login, with dry-run and validation modes.
- Env/schema: add OIDC/gateway/provider/approval/proof settings and keep provider secrets out of examples and generated Caddyfiles.
- Downstream docs: add `docs/deploy/UPSTREAM_AUTH_CONTRACT.md` or equivalent content documenting how containers consume headers or signed assertions, how they prove traffic came through the Caddy gate, and when it is safe to disable local auth.
- Validation: add route-generation tests, env-schema tests, unauthenticated/unauthorized/approved smoke tests, spoofed-header checks, and token-verification checks.

## Current Context

- Ubuntu deployments use a centralized Caddy container named `central-proxy`; downstream apps join the external Docker `caddy` network and should not publish host ports.
- The current protected-container proxy Caddyfile and `scripts/deploy/caddy_register.py` generate per-domain site blocks with `basic_auth` using `BASIC_AUTH_USER` and `BASIC_AUTH_HASH`.
- The route registration helper treats a route as healthy only when it finds Basic Auth.
- The strict deploy env schema means any OIDC/auth-gateway/provider/allowlist keys must be added explicitly before validation passes.
- Existing docs teach downstream projects to join the `caddy` network and rely on generated Basic Auth routes.

## Generic Caddy Mechanisms

Stock `caddy:2-alpine` does not provide a generic built-in OpenID Connect login/client directive comparable to `basic_auth`. The useful generic mechanisms are:

| Mechanism | Stock Caddy Support | Use In This Plan |
| --- | --- | --- |
| Site blocks | Yes | Each public hostname gets its own route. Requests do not inherit behavior across site blocks. |
| Snippets and `import` | Yes | Define one reusable protected-route/auth snippet and import it into every protected app route. |
| `basic_auth` | Yes | Current model and temporary rollback/break-glass mode only. |
| `forward_auth` | Yes | Preferred generic auth integration. Caddy asks an auth gateway whether the request may continue. |
| `forward_auth copy_headers` | Yes | Copy gateway-provided identity/proof headers into the upstream request after successful auth. |
| `request_header` / `reverse_proxy header_up` | Yes | Strip client-supplied identity/proof headers before setting trusted proxy-controlled values. |
| Native generic OIDC login/client | No | Requires an external auth gateway or a custom Caddy build/plugin. |
| Per-app signed JWT payload using `APP_SECRET` | No, not in stock Caddyfile | Use the auth gateway to sign assertions, or build a custom Caddy plugin. |
| Custom Caddy auth plugin | Possible | Higher ownership cost because the project must build, pin, ship, and validate a custom Caddy image. |

References checked:

- Caddy `forward_auth`: https://caddyserver.com/docs/caddyfile/directives/forward_auth
- Caddy `request_header`: https://caddyserver.com/docs/caddyfile/directives/request_header
- Caddy `reverse_proxy` headers: https://caddyserver.com/docs/caddyfile/directives/reverse_proxy
- Caddyfile snippets/imports: https://caddyserver.com/docs/caddyfile/concepts
- Caddy `basic_auth`: https://caddyserver.com/docs/caddyfile/directives/basic_auth
- Caddy modules/extensions: https://caddyserver.com/docs/extending-caddy

## Proposed Architecture

Use stock Caddy plus a central auth gateway/broker.

This should be a central companion service in the protected-container proxy stack, not a Caddy sidecar per downstream app. Prefer a popular maintained auth gateway/broker that already supports Caddy `forward_auth`, social/OIDC providers, groups/policies, user approval, and durable user storage. The plan should only choose a custom Caddy plugin or custom assertion service if maintained gateway options cannot satisfy the proof contract.

```text
Browser
  -> Caddy central-proxy
     -> shared auth guard via forward_auth
        -> auth gateway / identity broker
           -> Google, Microsoft, Facebook login
           -> approval policy / group / allowlist
           -> signed identity assertion when required
     -> protected app container on Docker caddy network
```

Generated Caddy config should follow this shape after the exact gateway path and header names are selected:

```caddy
(protected_auth) {
    request_header -X-Auth-User
    request_header -X-Auth-Email
    request_header -X-Auth-Groups
    request_header -X-Auth-Token

    forward_auth auth-gateway:4180 {
        uri /auth/verify
        copy_headers {
            Remote-User>X-Auth-User
            Remote-Email>X-Auth-Email
            Remote-Groups>X-Auth-Groups
            X-Auth-Token>X-Auth-Token
        }
    }
}

app.example.com {
    import protected_auth
    reverse_proxy app-service:3000
}
```

Upstream containers do not validate the Caddy snippet itself. They validate the effects of the central gate: no direct public reachability, trusted proxy headers stripped and set by Caddy, and, for Level 2 adoption, a signed assertion whose issuer/audience/signature/expiry match the app registration. The implementation must add downstream documentation that explains how to consume Level 1 headers and how to verify Level 2 assertions.

The exact gateway service, port, verify URI, and copied headers are selected after Phase 2. The important contract is stable: registration imports one protected auth guard before proxying to the app.

## User Store And Provisioning

- Authorized users should live in the selected auth gateway/broker, not in Caddy and not in each downstream app by default.
- If the selected gateway has a database-backed user/group/policy model, that database is the source of truth for approvals.
- If the selected gateway uses file-backed access lists, the protected-container repo should own a generated approved-users file that is synced to the proxy host and mounted read-only into the gateway.
- The account lifecycle is pending request -> approval -> active account/group membership -> optional approval email -> app access.
- Add an operator script, tentatively `scripts/deploy/auth_users.py`, to provision users up front. It should support at least `--dry-run`, `add`, `remove`, `list`, `sync`, email validation, provider/group/policy assignment, and no secret logging.
- The provisioning script should target the selected gateway API when available; otherwise it should render/validate the file-backed approved-users source.
- Deauthorization must remove the user/group/policy assignment and invalidate sessions when the selected gateway supports it.

## Caddy Compromise Boundary

A fully compromised public reverse proxy is high impact. The design cannot make a hacked Caddy harmless, but it can prevent Caddy from becoming the token issuer:

- Caddy must not store JWT signing keys or per-app raw `APP_SECRET` values.
- The auth gateway/assertion service signs Level 2 assertions; apps verify those signatures independently.
- Assertions must be short-lived and audience-scoped to the registered app.
- Apps that use Level 2 should reject Level 1 headers alone for sensitive actions.
- Direct app reachability must be blocked at Docker/host firewall/compose level, so bypassing Caddy is not an option.
- Consider mTLS from Caddy to sensitive upstream apps as an additional route-origin signal, but do not treat mTLS alone as user authentication.
- Add monitoring and rotation runbooks for Caddy compromise: rotate gateway signing keys, revoke sessions, restart proxy/auth services, and audit app access logs.

## Review Comment Decisions

- Will Caddy handle this for all containers underneath it? Yes for every route the central Caddyfile owns and protects with the shared snippet/import. No for containers merely attached to Docker networking or exposed by host ports. Protected app containers must not be reachable from outside the Docker/private network.

- How can Caddy provide proof of authentication to underlying containers? Caddy can forward trusted identity headers copied from the auth gateway after `forward_auth` succeeds. For cryptographic proof, the auth gateway should mint a signed assertion and Caddy should forward it in a header such as `X-Auth-Token`.
- Can the proof be signed with each app's `APP_SECRET`? Not with stock Caddy alone. A Caddyfile can call `forward_auth` and copy headers, but it cannot generically build and sign per-app JWT payloads with per-app secrets. This is supported as an auth-gateway responsibility or as a custom Caddy module.
- Can registration let each app register its own `APP_SECRET`? Yes, but the preferred implementation is to register a secret reference and app audience, not put raw secrets in the Caddyfile. The auth gateway can then sign per-app assertions. If using HMAC with `APP_SECRET`, the gateway must receive the same secret as the app; that increases blast radius. The safer default is asymmetric signing where the gateway keeps the private key and apps verify with public JWKS.
- How should local app auth be replaced? First make central Caddy the only public path and pass verifiable identity to apps. Then downstream apps can replace password/access-key login with an adapter that trusts sanitized Caddy headers or verifies `X-Auth-Token`. Sensitive apps should require signed-token verification before disabling local auth.
- How do new users get authorized? Successful Google/Microsoft/Facebook login is authentication only. Authorization requires approval through a broker group, policy, or allowlist. Unauthorized users should see a Create Account / Request Access action routed to `AUTH_APPROVER_EMAIL`.

## Authentication Proof Contract

Two proof levels are planned so simple containers and security-sensitive containers both have a path.

### Level 1 - Trusted Proxy Identity Headers

- Caddy strips all incoming identity/proof headers before auth.
- `forward_auth` copies identity headers only from the auth gateway response after a 2xx decision.
- Apps may trust headers such as `X-Auth-User`, `X-Auth-Email`, `X-Auth-Groups`, and `X-Auth-Name` only when they are not reachable except through central Caddy.
- This level is useful for simple internal apps and display/audit identity.

### Level 2 - Signed User Assertion

- The auth gateway provides a short-lived signed JWT or comparable signed assertion in `X-Auth-Token`.
- Preferred signing model: asymmetric signing with gateway-owned private key and app-side JWKS/public-key verification.
- Optional compatibility model: per-app HMAC signing with an app-specific secret reference. This may use `APP_SECRET`, but only if the app owner accepts that the auth gateway must know that secret.
- Apps verify issuer, audience, expiry, and signature; they reject missing, expired, wrong-audience, or unverifiable tokens.
- This level is required before replacing local auth for sensitive apps such as stock-dashboard trading/admin flows.

## App Registration Contract

Extend Caddy registration from only `domain -> service:port` to an auth-aware registration contract:

| Field | Purpose |
| --- | --- |
| `domain` | Public hostname. |
| `service` / `port` | Internal Docker target. |
| `auth_mode` | `oidc`, `basic`, or `public`; default should become `oidc` for protected routes. |
| `auth_policy` | Broker policy/group/allowlist required for this app. |
| `auth_audience` | Expected token audience for Level 2 verification. |
| `proof_level` | `headers` or `signed_token`. |
| `secret_ref` | Optional reference to the per-app signing secret, not the raw secret. |
| `identity_headers` | Headers copied from gateway to upstream. |

Registration must not write raw `APP_SECRET` values into the Caddyfile. If per-app HMAC signing is chosen, the secret should be synced into the auth gateway secret store through the existing secret-sync path or a new explicit proxy-secret sync path.

## Candidate Auth Gateways

| Pattern | Fit | Notes |
| --- | --- | --- |
| Maintained identity broker plus Caddy `forward_auth` | Preferred default | Broker handles Google/Microsoft/Facebook, user approvals, groups, policies, sessions, and request-access UX while Caddy stays stock. Evaluate Authentik, Authelia, and Keycloak. |
| OAuth2 Proxy plus Caddy `forward_auth` | Possible but limited | Good for one provider and email allowlists. Its multi-provider story must be verified before relying on it for Google + Microsoft + Facebook. |
| Maintained gateway plus small assertion service | Possible if needed | Use a popular gateway for auth/approval, then a tiny local service mints per-app assertions. Adds code to own, but keeps signing keys out of Caddy. |
| Custom Caddy plugin | Possible fallback | Could sign payloads inside Caddy, but requires custom Caddy image build/pinning, plugin review, and long-term ownership. |
| Per-app OIDC only | Rejected as central default | Leaves each container to solve auth independently and does not give protected-container one consistent edge contract. |

## New-User Authorization Model

1. A user visits a protected route such as `https://stock-dashboard.example.com`.
2. Caddy strips identity/proof headers from the incoming request.
3. Caddy calls the auth gateway with `forward_auth`.
4. If no valid session exists, the gateway redirects to login or create account.
5. The user signs in with Google, Microsoft, or Facebook.
6. The gateway evaluates authorization using approved email, group membership, or policy.
7. If not authorized, the user sees a Create Account / Request Access action that contacts `AUTH_APPROVER_EMAIL`.
8. If authorized, the gateway returns 2xx plus identity/proof headers.
9. Caddy forwards the request to the app with only trusted identity/proof headers set by the gateway.
10. The app either trusts Level 1 proxy headers or verifies the Level 2 signed token, according to its documented adoption level.
11. After approval, the user receives an access-granted email from the approver or gateway notification workflow.

## UI Mockup

```text
Access Required
You signed in, but this server requires approval before apps are available.

[ Create Account / Request Access ]

Approval contact: ronny.bjones@hotmail.com
Signed-in identity: user@example.com
Provider: Google | Microsoft | Facebook
```

## Task Overview

- [x] Phase 0: Cleanup and documentation audit
- [x] Phase 1: Caddy mechanism investigation and decision record
- [x] Phase 2: Auth gateway selection and proof-route target
- [x] Phase 3: Env schema, secrets, user store, and provisioning contract
- [ ] Phase 4: Shared Caddy auth snippet and route registration (route-generation slice complete; live staging proof checks remain)
- [ ] Phase 5: Identity proof contract for downstream containers (docs complete; live header proof checks remain)
- [ ] Phase 6: New-user authorization workflow
- [ ] Phase 7: stock-dashboard adoption and smoke tests
- [ ] Phase 8: Staging, production migration, and cleanup

## Phase 0 - Cleanup And Documentation Audit

Follow `.github/skills/code-cleanup/SKILL.md` and its `code-simplify` / `typed-code-generation` chain for the touched deploy/auth modules before implementation.

### Tasks

- [x] Scope the cleanup to central proxy docs, env examples, `docker/proxy/`, `scripts/deploy/caddy_register.py`, env schema/tests, and deploy docs that describe public ingress.
- [x] Load the cleanup, simplification, typed-code, documentation, security, and test workflows before changing deploy/auth behavior.
- [x] Audit Basic Auth references in protected-container docs, env examples, Caddyfile templates, route-registration tests, and downstream shared-routing guidance.
- [x] Identify Caddy auth snippets and route-protection checks that should become reusable before adding OIDC branches.
- [x] Review docs for any guidance that allows direct app host ports on Ubuntu protected routes.
- [x] Identify compose, Docker network, Portainer, and firewall checks that prove app containers are unreachable without passing the Caddy gate.
- [x] Record the current Basic Auth behavior as the rollback baseline.

### Phase 0 Findings

- Basic Auth assumptions that must change are concentrated in `README.md`, `docs/DOCKER.md`, `docs/CODE_SERVER.md`, `docs/deploy/AZURE_CONTAINER.md`, `docs/deploy/ADD_YOUR_APP.md`, `docs/deploy/ENV_SCHEMA.md`, `docs/deploy/SHARED_CADDY_ROUTING.md`, `docs/deploy/UBUNTU_SERVER.md`, `env.example`, `env.secrets.example`, `env.deploy.example`, `docker/proxy/Caddyfile`, Azure YAML rendering helpers, `scripts/deploy/caddy_register.py`, and the Caddy/env schema tests.
- Reusable route-protection candidates are `SITE_BLOCK_TEMPLATE`, `_site_block_has_basic_auth`, `is_domain_registered`, the `{$PUBLIC_DOMAIN}` placeholder handling, and the protected route in `docker/proxy/Caddyfile`. These should move from Basic-Auth-specific checks to a generic protected-route contract during Phase 4.
- Direct-port guidance is mostly correct today: Ubuntu docs say only central Caddy binds host ports `80` and `443`, and shared routing docs tell downstream apps not to publish web host ports. Later phases must preserve this guidance and add validation that app stacks expose no public web ports before app-local auth is disabled.
- Compose/network validation target: proxy compose should still render with only central Caddy publishing `80`/`443`; downstream app compose and Portainer stack inspection should confirm app containers join the external `caddy` network without publishing public web ports.
- Rollback baseline: generated routes currently use `basic_auth` with `BASIC_AUTH_USER` and `BASIC_AUTH_HASH`; unprotected existing routes are repaired by rewriting them to Basic Auth; placeholder routes are considered healthy only when the placeholder block contains `basic_auth`; env schema keeps `BASIC_AUTH_HASH` as a runtime secret; Ubuntu deploy validates quoted bcrypt hashes; Azure YAML rendering includes one Basic Auth layer for all routes.
- Baseline validation passed with `source .venv/bin/activate && pytest -q tests/pytests/test_caddy_register.py tests/pytests/test_env_schema.py tests/pytests/test_env_schema_secrets.py` (`21 passed`).
- `docker compose -f docker/proxy/docker-compose.yml config` rendered successfully, but this command expands `env_file` values into terminal output. Future compose validation should use a redacted/no-secret-output variant and must not paste expanded environment values into reports.

### Exit Criteria

- [x] All Basic Auth assumptions that must change are listed.
- [x] All direct-port exposure risks are documented or scheduled for correction.
- [x] The no-direct-access validation target is known.
- [x] Baseline tests and validation commands are known.

## Phase 1 - Caddy Mechanism Investigation And Decision Record

### Tasks

- [x] Verify Caddy stock support for `forward_auth`, snippets/imports, header stripping, header copying, and reverse-proxy header setting against current docs.
- [x] Verify whether Caddy has any acceptable stock JWT/OIDC signing or validation mechanism; if not, record that an external gateway or custom module is required.
- [x] Decide the protected-route snippet/import structure that all generated app routes will use.
- [x] Decide whether Level 2 signed token proof is mandatory for all routes or only for apps that replace local auth.
- [x] Decide whether per-app `APP_SECRET` HMAC signing is acceptable or whether asymmetric JWKS signing is mandatory.
- [x] Decide the minimum route-origin proof for sensitive upstream containers: no direct port, private Docker network only, optional mTLS, and signed assertion verification.
- [x] Write a short decision section in the plan or a follow-up ADR-style doc.

### Phase 1 Decision Record

Status: accepted for implementation planning on 2026-06-10.

- Local stack evidence: the available `caddy:2-alpine` image is Caddy `v2.11.2`. Its stock module list includes `http.handlers.reverse_proxy`, `http.handlers.headers`, `http.handlers.authentication`, and `http.authentication.providers.http_basic`. It does not include stock OIDC or JWT auth/signing modules.
- Official Caddy docs confirm `forward_auth` is a Caddyfile shortcut over `reverse_proxy` for auth gateway pre-checks. It sends a cloned request to the gateway, grants access on `2xx`, copies configured response headers to the original request via `copy_headers`, and otherwise returns the gateway response to the client.
- Official Caddy docs confirm snippets and `import` can be reused in site blocks, and site blocks do not inherit behavior from each other. Therefore every protected app route must explicitly import the protected auth guard.
- Official Caddy docs confirm `request_header -Header-Name` deletes request headers and `reverse_proxy header_up` can set/add/delete upstream request headers. The protected auth guard will strip client-supplied identity/proof headers before `forward_auth` runs, then only copy gateway-approved identity/proof headers.
- Caddy owns TLS, site matching, shared auth-guard import, request-header stripping, `forward_auth`, copied identity/proof headers, and reverse proxying to private Docker-network upstreams.
- The auth gateway owns login redirects, provider sessions, user approval/authorization, group/policy checks, user store, access-request UX, and Level 2 assertion signing. Caddy must not store app signing keys or mint JWTs.
- Generated protected app routes will use one shared snippet, tentatively `(protected_auth)`, imported before `reverse_proxy`. Auth gateway callback/login routes must not import this snippet.
- Level 1 trusted headers are acceptable for display/audit identity only when the app is reachable exclusively through central Caddy. Level 2 signed assertion proof is mandatory before a sensitive app disables or replaces local auth.
- Default Level 2 signing model is asymmetric JWKS: the gateway keeps the private key, and apps verify issuer, audience, expiry, and signature with a public key/JWKS. Per-app `APP_SECRET` HMAC signing is compatibility-only and must be opt-in through a secret reference, never raw secret material in Caddyfile output.
- Minimum route-origin proof for sensitive upstreams is: no public app host ports, private Docker network ingress only through Caddy, trusted proxy/header configuration in the app, signed assertion verification, and optional mTLS as an extra origin signal rather than user auth.

### Phase 1 Verification Evidence

- `docker run --rm caddy:2-alpine caddy version` returned `v2.11.2`.
- `docker run --rm caddy:2-alpine caddy list-modules | rg 'http.handlers.reverse_proxy|http.handlers.authentication|http.authentication|http.handlers.request_header|http.handlers.headers|forward_auth'` confirmed stock reverse proxy, headers, authentication, and Basic Auth modules; no stock OIDC/JWT auth module was present in the local image.
- A temporary Caddyfile under `out/tmp` with `(protected_auth)`, `request_header` deletions, `forward_auth`, `copy_headers` renames, snippet `import`, and `reverse_proxy` validated successfully with `docker run --rm -v "$PWD/out/tmp/caddy-phase1-forward-auth.Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile`. The temporary file was deleted after validation.
- `docker compose -f docker/proxy/docker-compose.yml config --no-env-resolution --no-interpolate` rendered the proxy compose model with central Caddy publishing only `80` and `443`, without expanding env-file values.
- Official sources consulted: `https://caddyserver.com/docs/caddyfile/directives/forward_auth`, `https://caddyserver.com/docs/caddyfile/directives/request_header`, `https://caddyserver.com/docs/caddyfile/directives/reverse_proxy`, `https://caddyserver.com/docs/caddyfile/concepts`, `https://caddyserver.com/docs/caddyfile/directives/basic_auth`, and `https://caddyserver.com/docs/modules/`.

### Acceptance Criteria

- [x] The plan states exactly what Caddy owns and what the auth gateway owns.
- [x] The plan states how identity spoofing is prevented before headers reach apps.
- [x] The plan states what proof apps receive and how they should verify it.
- [x] The plan states whether raw app secrets ever leave app-owned secret storage.
- [x] The plan states what remains at risk if Caddy itself is compromised and which controls reduce that blast radius.

### Verification

- [x] `docker run --rm caddy:2-alpine caddy list-modules | grep -E 'reverse_proxy|authentication'` or equivalent module check if Docker is available.
- [x] `docker compose -f docker/proxy/docker-compose.yml config --no-env-resolution --no-interpolate`

### Files Likely Touched

- `planning/caddy-oidc-edge-auth-plan.md`
- `docs/deploy/SHARED_CADDY_ROUTING.md`
- `docs/deploy/UBUNTU_SERVER.md`

### Exit Criteria

- [x] The design no longer depends on assumed Caddy behavior.

## Phase 2 - Auth Gateway Selection And Proof-Route Target

### Tasks

- [x] Compare popular maintained options first: Authentik, Authelia, Keycloak, and OAuth2 Proxy. Only include custom Caddy plugin or custom assertion service if maintained options cannot satisfy the proof contract.
- [x] Compare each option against Google/Microsoft/Facebook support, Caddy `forward_auth`, access-request UX, database or file-backed user store, groups/allowlists, provisioning API, signed assertions, per-app audience support, Docker Compose operation, persistence, and rollback complexity.
- [x] Verify whether Facebook will be configured as OIDC or social OAuth through the selected gateway.
- [x] Define the staging proof-route target that will use Caddy `forward_auth`, return identity headers, and return a signed token for Level 2 proof.
- [x] Move live proof-route installation and anonymous/unauthorized/approved-user validation to Phase 4 and Phase 8, after env schema and proxy config exist.
- [x] Verify where approved users live for the selected option and how backups/restores work.
- [x] Verify whether the selected option can send access-granted notifications or whether protected-container must provide a simple notification script/manual runbook.

### Phase 2 Decision Record

Status: accepted on 2026-06-10. Authentik is selected for implementation planning; staging proof-route installation and live auth validation are implementation gates in Phase 4 and Phase 8 because they depend on Phase 3 env/schema and Phase 4 proxy config.

Select Authentik as the central auth gateway/broker for the first OIDC edge-auth rollout. It is the best fit for this repository because it combines a documented Caddy `forward_auth` proxy-provider integration, social/OIDC source brokerage, application/group/policy authorization, durable user and session storage, OpenAPI-backed provisioning, invitation/enrollment flows, email-capable onboarding, and proxy headers that include both identity fields and Authentik-issued JWT/JWKS metadata. This keeps Caddy stock and avoids adding a custom Caddy image, while still giving downstream apps a Level 2 signed-token path.

Use one Authentik proxy provider per protected app when the app needs distinct policy, group binding, audience, or proof behavior. Authentik's domain-level forward-auth mode is useful for broad shared protection under one parent domain, but its docs state that it cannot enforce different application-level authorization rules for each protected application. The protected-container route-registration contract should therefore default to single-application forward-auth providers for app-specific authorization.

Facebook should be configured as an Authentik social/OAuth source, not as a downstream app OIDC provider. Google and Microsoft also belong behind Authentik as sources/identity providers. Protected apps then integrate with the central edge contract instead of each app directly brokering Google, Microsoft, or Facebook.

Approved users live in Authentik's user/group/application binding model backed by Authentik's PostgreSQL database. Authentik requires PostgreSQL for application data, configuration, sessions, and background task coordination, and its docs point backup/restore operations at the Authentik/PostgreSQL backup guidance. Phase 3 should model this as proxy-stack-owned Authentik/PostgreSQL persistence with explicit backup paths, not Caddyfile state.

Use Authentik groups/application bindings as the first approval mechanism. Operators can pre-provision users or groups through Authentik's Admin UI or API, and protected-container should add `scripts/deploy/auth_users.py` as a wrapper around the Authentik API for repeatable `list`, `add`, `remove`, `sync`, and `--dry-run` flows. New-user self-service should not grant app access automatically: invitation/enrollment flows can create users and assign groups, but protected-container must bind app access only to approved groups or policies.

For access-request UX, keep the durable contract independent of Authentik internals: unauthenticated users follow Authentik login; authenticated-but-unapproved users should land on a request-access page or denial flow that emails or instructs the operator at `AUTH_APPROVER_EMAIL`. Authentik can send invitation and recovery emails when SMTP is configured, and can send invitation emails from the Admin UI. If the exact access-granted notification cannot be expressed cleanly through Authentik events/flows in Phase 6, protected-container should provide a simple operator notification script or runbook rather than blocking the gateway selection.

Keep Basic Auth rollback mode until the Authentik proof route is deployed and validated in staging. Rollback means generated routes can still render the existing Basic Auth guard and `BASIC_AUTH_HASH` remains a valid secret while `EDGE_AUTH_MODE=basic` is supported.

### Phase 2 Gateway Comparison

| Option | Decision | Fit Against Requirements |
| --- | --- | --- |
| Authentik | Selected | Documented Caddy proxy-provider `forward_auth`; supports forward-auth single-app mode for per-app authorization; supports social/OAuth and OIDC sources; has users, groups, application bindings, policies, invitations, email settings, OpenAPI, PostgreSQL-backed persistence, proxy identity headers, and Authentik JWT/JWKS metadata headers. |
| Keycloak | Strong fallback, not first rollout | Excellent identity broker, social providers, roles/groups, organizations, Admin API/CLI, signed OIDC tokens, JWKS, and audience controls. It lacks a native Caddy `forward_auth`/outpost integration in the docs gathered, so it would require OAuth2 Proxy or a custom adapter before Caddy can use it as an edge pre-auth gateway. |
| Authelia | Rejected for this goal | Good Caddy `forward_auth`, access control, and file-backed/local identity options, but its OIDC provider docs state that it does not support the OIDC relying-party role. That means it cannot natively broker Google/Microsoft/Facebook login as the central social-login gateway. |
| OAuth2 Proxy | Rejected as primary broker | Good Caddy-adjacent auth-request pattern, many providers, groups/email allowlists, and simple Docker operation. It is weaker for durable user approval, invitations, access-request workflow, provisioning, and multiple-provider governance; docs note multiple providers are incomplete. |
| Maintained gateway plus custom assertion service | Deferred fallback | Could preserve a popular gateway while adding app-specific assertions if Authentik's JWT/JWKS headers cannot satisfy Level 2 in staging. Adds code and key-management ownership, so do not build unless the proof-route test fails. |
| Custom Caddy plugin | Rejected for first rollout | Would move signing/key handling into Caddy and require a custom image, plugin review, pinning, and long-term maintenance. Phase 1 already established that Caddy should not become the token issuer. |

### Phase 2 Proof-Route Target

The staging proof route should use this selected shape:

```caddy
(protected_auth) {
    request_header -X-Auth-User
    request_header -X-Auth-Email
    request_header -X-Auth-Groups
    request_header -X-Auth-Token

    forward_auth authentik-outpost:9000 {
        uri /outpost.goauthentik.io/auth/caddy
        copy_headers {
            X-authentik-username>X-Auth-User
            X-authentik-email>X-Auth-Email
            X-authentik-groups>X-Auth-Groups
            X-Authentik-Jwt>X-Auth-Token
        }
    }
}
```

The exact outpost service name, auth host, copied header casing, trusted proxy settings, and public callback paths must be verified against the generated Authentik provider/outpost configuration during staging. Caddy must continue to strip all incoming `X-Auth-*` headers before calling Authentik.

### Phase 2 Source Evidence

- Authentik proxy provider docs confirm proxy mode, forward-auth single-application mode, forward-auth domain-level mode, `/outpost.goauthentik.io/auth/caddy`, user identity headers, application metadata headers, logout behavior, unauthenticated paths, and HTTP/HTTPS outpost listeners on `9000`/`9443`.
- Authentik Caddy integration docs show Caddy `forward_auth` against the outpost and copied headers including user, email, groups, name, UID, JWT, and JWKS metadata.
- Authentik OAuth2/OIDC provider docs confirm Authentik can act as an OIDC provider, exposes OAuth2/OIDC endpoints and JWKS, signs JWTs, and supports asymmetric signing with a selected signing key.
- Authentik sources docs confirm external directories and social login sources; Facebook is handled as a social/OAuth source behind Authentik rather than as app-local OIDC.
- Authentik user docs confirm users have `is_active`, groups, sessions, attributes, additional proxy headers, Admin UI management, API-backed automation, group assignment, deactivation, and session revocation.
- Authentik invitation docs confirm invitation/enrollment flows, invitation emails, optional automatic group assignment through user-write stages, and invitation policies.
- Authentik configuration and Docker Compose docs confirm PostgreSQL is required for application data/configuration/sessions/task coordination, file/S3 storage options exist, SMTP email settings can be configured, and Docker socket access for automatic outpost management has security risk that can be avoided with manual outpost deployment or a socket proxy.
- Authelia docs confirm Caddy `forward_auth` and access control, but also state Authelia currently does not support the OIDC relying-party role.
- Keycloak docs confirm rich identity brokering, social providers, roles/groups, workflows, Admin CLI/API, token signing, audience claims, and JWKS, but not a direct Caddy forward-auth gateway path.
- OAuth2 Proxy docs confirm Google/Microsoft/Facebook and other providers, auth-request headers, config validation, and allowlist controls, but also note the multiple-providers feature is incomplete.

### Acceptance Criteria

- [x] One gateway pattern is selected with rationale.
- [x] Provider compatibility for Google, Microsoft, and Facebook is confirmed from current provider docs.
- [x] The gateway can support the selected approval/request-access path, with exact denial-page or helper-page UX deferred to Phase 6.
- [x] The gateway can return the identity/proof fields required by the downstream contract.
- [x] The selected user store and provisioning path are documented.
- [x] Basic Auth rollback mode remains possible until production OIDC is proven.

### Verification

- [x] `docker compose -f docker/proxy/docker-compose.yml config --no-env-resolution --no-interpolate`
- [ ] `docker exec central-proxy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile` on staging after the proof route is installed in Phase 4.

### Files Likely Touched

- `docker/proxy/docker-compose.yml`
- `docker/proxy/Caddyfile`
- `docs/deploy/SHARED_CADDY_ROUTING.md`

### Exit Criteria

- [x] The implementation target is selected and provider-specific limitations are documented.
- [x] Live proof-route installation is sequenced behind the env/schema and proxy-config phases that make it deployable.

## Phase 3 - Env Schema, Secrets, User Store, And Provisioning Contract

### Tasks

- [x] Add explicit vars for `EDGE_AUTH_MODE`, auth gateway service/port/verify URI, public auth callback domain, copied identity headers, token header name, `AUTH_APPROVER_EMAIL`, default proof level, and default token issuer.
- [x] Default `AUTH_APPROVER_EMAIL` to `ACME_EMAIL` when not set, and document that production approval uses `ronny.bjones@hotmail.com` through env configuration.
- [x] Add app registration fields for `AUTH_AUDIENCE`, `AUTH_POLICY`, `AUTH_PROOF_LEVEL`, and optional `AUTH_SECRET_REF`.
- [x] Add required secrets for the selected gateway only: provider client secrets, cookie/session signing, bootstrap admin secret, token signing keys, JWKS private key, or per-app HMAC secret references.
- [x] Add user-store config for the selected gateway, including database volume/backup path or file-backed approved-users source.
- [x] Add authorization config for broker-managed groups or a file-backed approved-email list.
- [x] Add `scripts/deploy/auth_users.py` or equivalent to provision users up front with `list`, `add`, `remove`, `sync`, and `--dry-run` modes.
- [x] Ensure the provisioning script logs user identifiers and actions, but never provider secrets, signing keys, app secrets, session cookies, or full tokens.
- [x] Update env examples with placeholder-only values.
- [x] Extend schema tests for known keys, unknown-key failures, and cross-field rules when `EDGE_AUTH_MODE=oidc`.

### Phase 3 Implementation Notes

- `EDGE_AUTH_MODE` defaults to `basic`, preserving Basic Auth rollback until OIDC mode is explicitly enabled.
- Authentik deploy-time vars and secrets are schema-defined. Secrets include `AUTHENTIK_SECRET_KEY`, `AUTHENTIK_POSTGRESQL__PASSWORD`, `AUTHENTIK_BOOTSTRAP_PASSWORD_HASH`, `AUTHENTIK_BOOTSTRAP_TOKEN`, `AUTHENTIK_API_TOKEN`, SMTP password, and social provider client secrets.
- `AUTH_APPROVER_EMAIL` is resolved from explicit env first and falls back to `ACME_EMAIL`; the production approver address remains an environment value rather than a hardcoded repo default.
- Approved users live in Authentik group/application policy state. `AUTH_POLICY` names the approved-user group, and `scripts/deploy/auth_users.py` provides `list`, `add`, `remove`, `sync`, and `--dry-run` operations against Authentik's documented user/group API.
- The provisioning wrapper logs action, status, user email, and group details only. API tokens and provider/signing/session secrets are never printed by the script.
- Authentik's PostgreSQL-backed user/config/session store is represented by explicit PostgreSQL connection keys and `AUTHENTIK_BACKUP_DIR`; the concrete compose volumes are implemented in Phase 4.

### Acceptance Criteria

- [x] Every new key is schema-defined and categorized as var or secret.
- [x] Missing OIDC-required keys fail with actionable validation errors only when OIDC mode is enabled.
- [x] Basic Auth keys remain valid while `EDGE_AUTH_MODE=basic` is supported as rollback.
- [x] No provider secret, app secret, or token-signing material appears in docs, examples, logs, Caddyfile output, or generated plans.
- [x] Approved users can be provisioned before first login through a documented script or gateway API.
- [x] The selected user store has a documented backup/restore path.

### Verification

- [x] `source .venv/bin/activate && pytest -q tests/pytests/test_auth_users.py tests/pytests/test_env_schema.py tests/pytests/test_env_schema_secrets.py`
- [x] `source .venv/bin/activate && python scripts/deploy/validate_env.py --runtime out/tmp/phase3.env --deploy out/tmp/phase3.env.deploy` with placeholder OIDC values and placeholder Authentik secrets exported in-process.

### Files Likely Touched

- `scripts/deploy/env_schema.py`
- `scripts/deploy/auth_users.py`
- `tests/pytests/test_env_schema.py`
- `tests/pytests/test_env_schema_secrets.py`
- `tests/pytests/test_auth_users.py`
- `docs/deploy/ENV_SCHEMA.md`
- `env.example`
- `env.secrets.example`
- `env.deploy.example`
- `env.deploy.secrets.example`

### Exit Criteria

- [x] The repo has a validated configuration contract for central OIDC edge auth, authorized-user storage, and upfront user provisioning.

## Phase 4 - Shared Caddy Auth Snippet And Route Registration

### Tasks

- [x] Add a reusable Caddy auth snippet/import for protected routes.
- [x] Add the Authentik gateway route and selected `forward_auth` target from Phase 2 to the proxy Caddyfile.
- [x] Ensure the snippet strips client-supplied identity/proof headers before `forward_auth`.
- [x] Render generated app site blocks using `import protected_auth` before `reverse_proxy` when `EDGE_AUTH_MODE=oidc`.
- [x] Extend app registration output to record auth policy, proof level, audience, and optional secret reference as route metadata comments without raw secrets.
- [ ] Extend app registration to render/update any selected gateway policy or assertion-service app metadata needed for per-app audiences.
- [x] Keep Basic Auth route rendering only for explicit rollback mode.
- [x] Update route-health detection from `_site_block_has_basic_auth` to a generic protected-route check that recognizes the shared OIDC import.
- [x] Add repair logic for unprotected, stale Basic-Auth-only, or mismatched protected routes, including `{$PUBLIC_DOMAIN}` placeholder repair.
- [x] Ensure auth gateway routes and callbacks are not protected by their own forward-auth guard.

### Phase 4 Implementation Notes

- `docker/proxy/Caddyfile` now defines `(protected_auth)`, strips incoming `X-Auth-*` and `X-Authentik-*` headers, proxies Authentik outpost paths before `forward_auth`, copies Authentik identity/JWT headers into the `X-Auth-*` contract, and exposes the Authentik gateway route without importing the guard.
- `docker/proxy/docker-compose.yml` now includes profiled Authentik `server`, `worker`, and PostgreSQL services using the stable image tag pinned by Authentik's official compose artifact.
- `scripts/deploy/caddy_register.py` now has a typed `EdgeAuthRegistration` contract, Basic/OIDC/Public route rendering, shared-snippet insertion/update, OIDC metadata comments, auth-mode-aware route-health checks, and deterministic stale-route repair.
- `scripts/deploy/ubuntu_deploy.py` now resolves edge-auth registration values from process env or `.env.deploy` only and passes the selected auth contract into Caddy registration and verification without reading `.env.deploy.secrets`.
- `scripts/deploy/ubuntu_deploy.py` now derives the registration upstream port from the rendered Compose app service when `WEB_PORT` is unset, so the default code-server container registers against `8080` instead of the legacy `3000` fallback.
- `scripts/deploy/ubuntu_deploy.py` now refreshes the central proxy stack in OIDC mode before route registration, and `scripts/deploy/ubuntu_deploy_proxy.sh` starts the proxy compose stack with `--profile oidc` so Authentik services exist for `forward_auth`.
- `docs/deploy/SHARED_CADDY_ROUTING.md` now documents `EDGE_AUTH_MODE=basic|oidc|public`, OIDC profile startup, generated route repair behavior, and Basic Auth rollback.

### Acceptance Criteria

- [x] Every auto-registered protected app route imports the shared auth guard in OIDC mode.
- [x] Existing unprotected or Basic-Auth-only routes can be repaired deterministically.
- [x] Auth callback/login routes stay reachable in rendered Caddy config.
- [ ] The staging proof route blocks anonymous users, denies unauthorized users, and allows approved users.
- [x] Existing reverse-proxy headers in the static protected-container route remain intact.
- [x] Raw app secrets are not written into generated Caddy site blocks.
- [x] Generated routes include the shared auth import and no app route is marked protected without it.

### Verification

- [x] `source .venv/bin/activate && python -m pytest -q tests/pytests/test_ubuntu_deploy_proxy_script.py tests/pytests/test_ubuntu_deploy.py tests/pytests/test_caddy_register.py tests/pytests/test_env_schema.py tests/pytests/test_env_schema_secrets.py` (`88 passed`).
- [x] `source .venv/bin/activate && python -m pytest tests/pytests/test_ubuntu_deploy.py::test_prod_registration_uses_compose_exposed_app_port_when_web_port_unset -x -v` proved code-server registration uses the Compose `8080` port when `WEB_PORT` is unset.
- [x] `source .venv/bin/activate && python -m pytest tests/pytests/test_ubuntu_deploy_proxy_script.py::test_proxy_deploy_uses_oidc_profile_and_remote_env_files tests/pytests/test_ubuntu_deploy.py::test_prod_oidc_deploy_updates_proxy_stack_even_when_caddy_exists -x -v` proved the normal Ubuntu OIDC deploy path updates the proxy stack and starts the `oidc` profile.
- [x] `source .venv/bin/activate && python -m pytest -q tests/pytests` (`220 passed`).
- [x] `docker compose -f docker/proxy/docker-compose.yml config --no-env-resolution --no-interpolate`.
- [x] `docker run --rm -v "$PWD/docker/proxy/Caddyfile:/etc/caddy/Caddyfile:ro" -e ACME_EMAIL=ops@example.com -e PUBLIC_DOMAIN=app.example.com -e BASIC_AUTH_USER=admin -e 'BASIC_AUTH_HASH=$2a$14$abcdefghijklmnopqrstuvwxyzABCDEFGHijklmnopqrstuv' -e EDGE_AUTH_GATEWAY_SERVICE=authentik-server -e EDGE_AUTH_GATEWAY_PORT=9000 -e EDGE_AUTH_VERIFY_URI=/outpost.goauthentik.io/auth/caddy -e AUTHENTIK_PUBLIC_DOMAIN=auth.example.com caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile`.
- [ ] `docker exec central-proxy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile` on staging.
- [ ] Manual staging proof-route checks for anonymous redirect/denial, authenticated unauthorized denial, approved access, identity headers, and `X-Auth-Token` presence.

### Files Likely Touched

- `scripts/deploy/caddy_register.py`
- `tests/pytests/test_caddy_register.py`
- `docker/proxy/Caddyfile`
- `docker/proxy/docker-compose.yml`

### Exit Criteria

- [x] Route registration can generate, detect, and repair centrally protected OIDC routes.
- [ ] Authentik-backed staging route behavior is proven against a live proxy stack.

## Phase 5 - Identity Proof Contract For Downstream Containers

### Tasks

- [x] Answer whether the current architecture can accommodate future OAuth2 machine-to-machine flows.
- [x] Create downstream-container docs that explain how to use the auth mechanism from an app's perspective.
- [x] Document the Level 1 trusted-header contract and the Level 2 signed-token contract.
- [x] Document exactly which headers Caddy strips and which headers it sets after gateway approval.
- [x] Document requirements for apps that replace local auth: no host ports, only central Caddy ingress, strict trusted-proxy config, signed-token verification for sensitive workflows, and audit logging of the authenticated email/user.
- [x] Document token verification requirements for issuer, audience, expiry, signature, route/host claim when available, and provider/user identity claims.
- [x] Document the tradeoff between per-app `APP_SECRET` HMAC signing and asymmetric JWKS signing.
- [x] Add migration guidance for downstream containers to turn off local password auth only after Level 2 proof is verified where needed.
- [x] Document what an app cannot prove if Caddy is compromised, and why signing keys must stay outside Caddy.

### Phase 5 Implementation Notes

- Added `docs/deploy/UPSTREAM_AUTH_CONTRACT.md` as the canonical downstream app contract.
- The contract documents Level 1 trusted proxy headers, Level 2 signed JWT proof, exact current Caddy/Auth headers, app-side validation requirements, no-direct-public-access requirements, and the checklist that must pass before local app auth is disabled.
- Machine-to-machine OAuth2 is supported by the selected architecture through Authentik OAuth2 providers and `client_credentials`; it is documented as a separate API/service-token contract from browser `forward_auth` sessions.
- `docs/deploy/SHARED_CADDY_ROUTING.md` and `docs/deploy/UBUNTU_SERVER.md` now link downstream apps to the auth contract before they consume headers or replace local auth.

### Acceptance Criteria

- [x] Other containers have a clear contract for consuming central Caddy authentication.
- [x] Header spoofing risks and mitigations are explicit.
- [x] Apps can distinguish display identity from cryptographic proof.
- [x] The docs do not imply that provider login alone grants authorization.
- [x] The docs include a minimal validation checklist for app owners before disabling local auth.

### Verification

- [x] Documentation review against `docs/deploy/SHARED_CADDY_ROUTING.md`.
- [ ] Staging route sends identity/proof headers only after successful auth.
- [ ] Staging route does not forward spoofed client `X-Auth-*` headers.

### Files Likely Touched

- `docs/deploy/SHARED_CADDY_ROUTING.md`
- `docs/deploy/UPSTREAM_AUTH_CONTRACT.md`
- `docs/deploy/UBUNTU_SERVER.md`
- `docs/deploy/ENV_SCHEMA.md`

### Exit Criteria

- [x] Downstream apps have enough guidance to replace local auth safely.
- [ ] Live staging proves Authentik-approved requests send the documented headers and spoofed client headers are stripped.

## Phase 6 - New-User Authorization Workflow

### Tasks

- [ ] Define the canonical approval mechanism: broker group, broker policy, file-backed allowlist, or a combination.
- [ ] Implement or configure an access-request/create-account page that routes requests to `AUTH_APPROVER_EMAIL`.
- [ ] Make account creation pending-only until approval; after approval, create/activate the user or group membership in the selected gateway.
- [ ] Send an access-granted email after approval, either through gateway notifications or an operator script/runbook.
- [ ] Implement or document upfront user provisioning with `scripts/deploy/auth_users.py`.
- [ ] Define deauthorization: remove the user/group, invalidate active sessions if supported, and verify denial.
- [ ] Document provider setup for Google, Microsoft, and Facebook callback URLs and required scopes/claims.
- [ ] Document a break-glass path for operators if the auth gateway is down or misconfigured.
### Acceptance Criteria

- [ ] Operators can approve a new user without editing the Caddyfile directly.
- [ ] Operators can provision users before first login.
- [ ] Operators can remove a user and verify denial.
- [ ] Approved users receive an access-granted notification.
- [ ] Unauthorized users see the access-request path rather than an app page.
- [ ] The runbook never asks operators to paste secrets into docs or command output.

### Verification

- [ ] Manual staging test: anonymous user redirects to login.
- [ ] Manual staging test: authenticated unauthorized user sees access request.
- [ ] Manual staging test: newly approved user reaches the app.
- [ ] Manual staging test: removed user is denied after session invalidation or expiry.

### Files Likely Touched

- `docs/deploy/SHARED_CADDY_ROUTING.md`
- `docs/deploy/UBUNTU_SERVER.md`
- gateway-specific config files selected in Phase 2.

### Exit Criteria

- [ ] New-user authorization is repeatable and documented for server operators.

## Phase 7 - stock-dashboard Adoption And Smoke Tests

### Tasks

- [ ] Update stock-dashboard docs to consume the protected-container central auth contract.
- [ ] Update stock-dashboard deploy wrapper behavior only if additional proxy-owned config or allowlist files must be synced.
- [ ] Update deployed-route smoke tests so anonymous OIDC routes may return redirect-to-login as well as `401`/`403`, while still proving the app is not anonymously reachable.
- [ ] Add tests or docs for rejecting spoofed `X-Auth-*` headers if stock-dashboard consumes edge identity.
- [ ] Plan the stock-dashboard app-auth replacement separately if it needs code changes to verify `X-Auth-Token` and disable `ENABLE_PASSWORD_AUTH`.

### Acceptance Criteria

- [ ] stock-dashboard is protected by central OIDC edge auth.
- [ ] stock-dashboard docs explain which identity proof level it consumes.
- [ ] Smoke tests still prove anonymous public access is blocked before Flask app content is served.
- [ ] Any app-layer auth removal has its own test-backed implementation path.

### Verification

- [ ] From stock-dashboard root: `source .venv/bin/activate && pytest -q tests/pytests/test_deploy_caddy_protection.py`
- [ ] From stock-dashboard root: `source .venv/bin/activate && python scripts/deploy/ubuntu_deploy.py --help`
- [ ] Browser staging check for login, authorization, and websocket-backed pages.

### Files Likely Touched

- stock-dashboard `docs/deploy/UBUNTU_SERVER.md`
- stock-dashboard `docs/deploy/STAGING.md`
- stock-dashboard `docs/github-pages/security.md`
- stock-dashboard `tests/pytests/test_deploy_caddy_protection.py`
- stock-dashboard `scripts/deploy/ubuntu_deploy.py` only if proxy config sync changes.

### Exit Criteria

- [ ] stock-dashboard is a verified downstream consumer of the central protected-container auth contract.

## Phase 8 - Staging, Production Migration, And Cleanup

### Tasks

- [ ] Deploy OIDC edge auth to staging with Basic Auth rollback still available.
- [ ] Run anonymous, unauthorized, approved, signed-token, spoofed-header, and deauthorized smoke checks.
- [ ] Promote the same proxy/auth configuration to production.
- [ ] Remove or deprecate Basic Auth-only docs and env keys after production OIDC is stable for an agreed window.
- [ ] Archive this planning file when all tasks are done.

### Acceptance Criteria

- [ ] Production anonymous access is blocked by Caddy/auth gateway before reaching app content.
- [ ] Approved users can reach protected routes through the new flow.
- [ ] Upstream apps receive the documented identity/proof contract.
- [ ] Operator runbook covers approval, deauthorization, rollback, and secret rotation.
- [ ] Obsolete Basic Auth guidance is removed or clearly marked as fallback-only.

### Verification

- [ ] `curl -vkI https://<staging-domain>` shows redirect/denial from the auth layer, not app content.
- [ ] Browser staging check completes Google/Microsoft/Facebook login for approved users.
- [ ] Spoofed-header check confirms client-provided `X-Auth-*` headers do not reach the app.
- [ ] Token verification check confirms wrong audience/expired/unsigned tokens are rejected by apps that claim Level 2 adoption.
- [ ] `docker logs --tail 200 central-proxy` and auth-gateway logs show no secret leakage.
- [ ] Full suite when implementation is complete: `source .venv/bin/activate && python scripts/run_tests.py` from affected downstream repos.

### Files Likely Touched

- `planning/caddy-oidc-edge-auth-plan.md`
- `archive/planning/caddy-oidc-edge-auth-plan_ARCHIVED.md`
- release/change docs as required by merge workflow.

### Exit Criteria

- [ ] OIDC/social-login edge auth is the documented default for protected Caddy routes.

## Risks And Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Assuming Caddy protects every container automatically | High | Generate/import the auth guard for every protected site block and forbid direct host ports. |
| Treating headers as cryptographic proof | High | Separate Level 1 headers from Level 2 signed token verification. |
| Assuming stock Caddy can sign per-app `APP_SECRET` payloads | High | Make signing an auth-gateway responsibility or explicitly choose a custom Caddy plugin. |
| Header spoofing | High | Strip incoming identity/proof headers before `forward_auth`; set only gateway-approved values. |
| Sharing app `APP_SECRET` with the auth gateway | High | Prefer asymmetric JWKS signing; if HMAC is required, register secret references and document blast radius. |
| Provider-login-only access | High | Require broker group/policy/allowlist approval before forwarding to apps. |
| Facebook provider mismatch | Medium | Verify whether Facebook is OIDC or social OAuth through the selected broker before implementation. |
| Operator lockout | High | Keep explicit Basic Auth or other break-glass rollback until OIDC is proven in production. |
| Auth gateway outage blocks all protected apps | High | Add health checks, restart policy, monitoring, and rollback docs. |
| Downstream apps remove local auth too early | High | Require Level 2 proof validation for sensitive apps before disabling local auth. |
| Secrets leak through examples/logs | High | Use placeholder-only examples, schema secret classification, and log review. |
| WebSocket traffic breaks | Medium | Preserve existing reverse-proxy behavior and run browser smoke checks. |

## Validation Plan

- Protected-container focused tests: `source .venv/bin/activate && pytest -q tests/pytests/test_caddy_register.py tests/pytests/test_env_schema.py tests/pytests/test_env_schema_secrets.py`
- Protected-container compose validation: `docker compose -f docker/proxy/docker-compose.yml config --no-env-resolution --no-interpolate`
- Caddy validation on staging: `docker exec central-proxy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile`
- stock-dashboard focused tests after downstream adoption: `source .venv/bin/activate && pytest -q tests/pytests/test_deploy_caddy_protection.py`
- Manual/browser checks: login redirect, create-account/access-request page, unauthorized denial, approved access, deauthorization, spoofed-header rejection, signed-token validation, and websocket-backed pages.

## Open Questions

- Should the first Authentik staging route use a manually deployed proxy outpost or Docker-socket-managed outpost behind a socket proxy?
- Should the access-request flow be an Authentik flow/denial page, a small protected-container helper page, or an operator-runbook-only first slice?
- Is Level 2 signed-token proof required for every protected app at rollout, or only for apps replacing their own auth?
- Which downstream app should be the first reference implementation for replacing local auth with the central identity contract?
