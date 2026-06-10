# Upstream Auth Contract

## Principles

- Caddy is the only public ingress for protected application traffic.
- Apps must treat edge-auth headers as trusted only when direct public access is impossible.
- Display identity and cryptographic proof are separate contracts.
- Caddy must strip spoofable client headers before calling the auth gateway.
- Signing keys and raw app secrets must stay outside Caddy and generated Caddyfiles.
- Machine-to-machine OAuth2 belongs to Authentik or an app API layer, not the browser `forward_auth` path.

## Contract Overview

Protected routes use the central Caddy `protected_auth` snippet before traffic is proxied to an app container. The snippet calls Authentik with Caddy `forward_auth`; only after Authentik allows the request does Caddy forward the request to the app.

The first rollout exposes two proof levels:

| Level | App may use it for | Required controls |
| --- | --- | --- |
| Level 1 trusted headers | UI display, audit attribution, low-risk internal workflows | No public app host ports, only central Caddy ingress, trusted proxy configuration, and spoofed-header stripping |
| Level 2 signed token | Replacing local auth for sensitive workflows | All Level 1 controls plus JWT verification of issuer, audience, expiry, and signature |

Apps should keep their local password, access-key, or session auth until they have validated the appropriate proof level in staging. Sensitive apps, including trading/admin dashboards, should not disable local auth until Level 2 token verification is implemented and tested.

## Header Contract

Caddy strips incoming client-supplied identity/proof headers before auth:

```caddy
request_header -X-Auth-*
request_header -X-Authentik-*
```

After Authentik approves the request, Caddy copies the gateway-approved headers into the app-facing namespace:

| App header | Source header | Meaning |
| --- | --- | --- |
| `X-Auth-User` | `X-Authentik-Username` | Authentik username |
| `X-Auth-Email` | `X-Authentik-Email` | Authenticated email address |
| `X-Auth-Groups` | `X-Authentik-Groups` | Authentik groups, as emitted by Authentik |
| `X-Auth-Token` | `X-Authentik-Jwt` | Authentik-issued JWT for Level 2 verification |

Do not trust client-sent `X-Auth-*` or `X-Authentik-*` values. The app should only consume those headers when the route is known to be reachable through central Caddy and the proxy has applied the shared guard.

Additional headers can be added later through the route contract and `EDGE_AUTH_COPY_HEADERS`, but each new header must be documented and verified before an app depends on it.

## Level 1: Trusted Proxy Identity Headers

Level 1 is suitable when the app only needs identity for display, audit logs, or coarse authorization that is already backed by the central Authentik policy.

An app using Level 1 must verify:

- The app has no public host port for normal web traffic.
- The app is attached to the private Docker `caddy` network.
- The public DNS name resolves only through the central proxy route.
- Caddy imports `protected_auth` for the app route when `EDGE_AUTH_MODE=oidc`.
- The app's framework only trusts proxy headers from the private Caddy path.
- App logs record the authenticated email or user id without logging `X-Auth-Token`.

Level 1 does not prove cryptographic user identity to the app. If Caddy is compromised, Caddy can still choose what headers reach the app. Use Level 2 for sensitive actions.

## Level 2: Signed User Assertion

Level 2 uses the Authentik JWT forwarded in `X-Auth-Token`.

An app using Level 2 must reject requests when the token is missing, expired, unsigned, signed by an unexpected key, issued by the wrong issuer, or intended for the wrong audience. At minimum, verify:

- `iss` matches the expected Authentik issuer for the configured application/provider.
- `aud` or the configured audience claim matches the app's `AUTH_AUDIENCE`.
- `exp` is present and in the future.
- The signature validates against the expected JWKS/public key.
- The user/group/entitlement claims satisfy the app's own authorization needs.
- The request host or route claim is checked when the provider supplies one and the app relies on host-specific authorization.

Prefer asymmetric signing with a gateway-owned private key and app-side JWKS verification. Per-app HMAC signing with an app secret is compatibility-only because it requires the auth gateway to know a secret that the app also trusts. If HMAC is used, register and sync a secret reference such as `AUTH_SECRET_REF`; do not write raw secret material into Caddyfile output, docs, or logs.

## Machine-To-Machine OAuth2

The architecture can accommodate future machine-to-machine OAuth2 flows, but they should be treated as a separate API contract from browser edge auth.

Use Authentik OAuth2 providers and the `client_credentials` flow for service-to-service calls. Authentik's official docs state that it supports standard OAuth2 flows including `client_credentials`, exposes token, introspection, revocation, JWKS, and discovery endpoints, and has a dedicated machine-to-machine authentication flow that returns signed JWT access tokens.

M2M guidance:

- Do not route service credentials through Caddy `forward_auth` browser sessions.
- Store client secrets, app password tokens, or JWT assertion material only in secret stores or ignored secret env files.
- Scope each machine client to the minimum API permissions it needs.
- Prefer short-lived signed JWT access tokens and JWKS verification at the receiving API.
- Use Authentik introspection or revocation endpoints when an API needs centralized token state.
- Keep human browser routes and service API routes separately documented, even if both use Authentik as the identity provider.

Relevant official Authentik docs:

- `https://docs.goauthentik.io/add-secure-apps/providers/oauth2/`
- `https://docs.goauthentik.io/add-secure-apps/providers/oauth2/machine_to_machine/`
- `https://docs.goauthentik.io/add-secure-apps/providers/proxy/`

## Migration Checklist Before Disabling Local Auth

Use this checklist per downstream app:

- [ ] The app has no public host ports for normal web traffic.
- [ ] The app's only public route is a central Caddy site block.
- [ ] The route imports `protected_auth` in OIDC mode.
- [ ] Anonymous requests are redirected or denied before app content is served.
- [ ] Authenticated but unauthorized users are denied before app content is served.
- [ ] Approved users can reach the app.
- [ ] Client-supplied spoofed `X-Auth-*` and `X-Authentik-*` headers do not reach the app.
- [ ] The app logs authenticated user/email metadata without logging tokens.
- [ ] Level 2 apps verify `X-Auth-Token` issuer, audience, expiry, and signature.
- [ ] Wrong-audience, expired, unsigned, and missing tokens are rejected.
- [ ] The rollback path is documented before local auth is disabled.

## What This Does Not Prove

Central Caddy auth does not make a fully compromised proxy harmless. A compromised proxy can still alter traffic, suppress headers, or forward requests incorrectly. The controls in this contract reduce blast radius by keeping signing keys outside Caddy, requiring apps to verify signed Level 2 assertions, blocking direct app reachability, and preserving rollback until the live route is proven.
