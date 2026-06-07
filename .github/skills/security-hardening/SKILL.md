---
name: security-hardening
description: "Use when: handling authentication, access keys, secrets, user input, config/env values, external APIs, exchange data, browser content, deployment scripts, CORS, error exposure, or any security-sensitive code path."
---

# Security Hardening Skill

## Principles

Treat every external value as untrusted until a boundary validates it. Treat every secret as non-readable and non-loggable. Treat auth and deployment behavior as security-sensitive even in test mode.

Critical repo rule: never read `.env.secrets` or `.env.deploy.secrets`.

## When To Use

- Changing login, auth bypass, `X-Access-Key`, `APP_SECRET`, `SECRET_KEY`, or test-mode behavior.
- Handling request JSON, query strings, form data, config/env values, exchange responses, browser content, logs, or uploaded/imported files.
- Adding external API integrations or deployment automation.
- Changing CORS, cookies, session behavior, error handling, or headers.
- Reviewing code for security risk.

## Boundary Rules

### Always Do

- Validate raw request/config/external payloads at the boundary.
- Convert raw values to strict typed internal models before core logic.
- Keep secrets in environment files or secret stores, never code or logs.
- Redact tokens, access keys, cookies, and credential-like values in logs and errors.
- Return generic user-facing errors for server failures.
- Preserve auth checks unless the change is explicitly about auth.
- Keep test-mode auth bypass constrained to `STOCK_DASHBOARD_TEST_MODE=true` or documented local test paths.

### Ask First

- Adding new auth flows or bypass paths.
- Changing how `APP_SECRET`, `SECRET_KEY`, or `X-Access-Key` works.
- Broadening CORS or network exposure.
- Storing new sensitive data.
- Adding file upload/import features.
- Changing deployment secret handling.

### Never Do

- Read `.env.secrets` or `.env.deploy.secrets`.
- Print secrets or full request headers in logs.
- Trust client-side validation as the only validation.
- Render untrusted strings as HTML.
- Build shell commands from unsanitized input.
- Expose stack traces or internal exception details to API clients.

## Procedure

### Step 1 - Identify Trust Boundaries

List every untrusted source:
- HTTP request body, query params, headers, cookies.
- Browser DOM, console, local storage, and network data.
- Exchange/API responses.
- Config files and env vars.
- Files under `logs/`, `out/`, or user-generated artifacts.

### Step 2 - Validate And Normalize

Validate shape, type, ranges, enums, and required fields at the boundary. Convert to dataclasses, enums, protocols, or explicit typed values before internal use.

### Step 3 - Protect Secrets And Logs

Search changed code for suspicious names such as `secret`, `token`, `password`, `key`, `cookie`, and `authorization`. Confirm values are not logged, committed, or sent to clients.

### Step 4 - Review Auth And Error Semantics

Verify protected endpoints require the intended auth path. Confirm test-mode behavior cannot accidentally enable production bypasses. Ensure API errors are useful but not revealing.

### Step 5 - Validate

Run focused tests for auth, validation, and error paths. For UI/browser-facing changes, verify the browser console and network responses do not expose sensitive details.

## Red Flags

- New code opens or reads secret env files.
- Raw request payloads passed into core logic.
- Stack traces returned through JSON responses.
- Access-key checks duplicated inconsistently.
- CORS widened without a stated reason.
- User/external data inserted with `innerHTML` or unsanitized template output.
- Debug logs include headers, tokens, cookies, or raw payloads.
- Deployment examples accidentally include real-looking credentials.

## Exit Criteria

- [ ] Trust boundaries are identified.
- [ ] Inputs are validated and normalized before core logic.
- [ ] Secrets are not read, logged, committed, or returned.
- [ ] Auth and test-mode behavior remain intentional.
- [ ] Error responses avoid internal details.
- [ ] Focused security-relevant tests or manual checks ran when behavior changed.