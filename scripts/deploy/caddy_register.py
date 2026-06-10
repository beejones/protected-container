"""Register an app's domain with the centralized Caddy proxy on Ubuntu.

Ensures the proxy Caddyfile contains a reverse-proxy site block for the
deployed app.  Idempotent — skips if the block exists; appends and restarts
Caddy when missing.

Called by :func:`ubuntu_deploy.main` as a post-deploy step when
``PUBLIC_DOMAIN`` is set and external Caddy integration is detected.
"""
from __future__ import annotations

import logging
import re
import shlex
import subprocess
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Container name (from docker/proxy/docker-compose.yml).
DEFAULT_CADDY_CONTAINER = "central-proxy"
LOG_PREFIX = "[CADDY-REGISTER]"


logger = logging.getLogger(__name__)

AUTH_MODE_BASIC = "basic"
AUTH_MODE_OIDC = "oidc"
AUTH_MODE_PUBLIC = "public"
PROTECTED_AUTH_SNIPPET_NAME = "protected_auth"
DEFAULT_EDGE_AUTH_GATEWAY_SERVICE = "authentik-server"
DEFAULT_EDGE_AUTH_GATEWAY_PORT = "9000"
DEFAULT_EDGE_AUTH_VERIFY_URI = "/outpost.goauthentik.io/auth/caddy"
DEFAULT_AUTH_POLICY = "protected-container-users"
DEFAULT_AUTH_PROOF_LEVEL = "headers"
DEFAULT_AUTHENTIK_COPY_HEADERS = (
    "X-Authentik-Username>X-Auth-User",
    "X-Authentik-Email>X-Auth-Email",
    "X-Authentik-Groups>X-Auth-Groups",
    "X-Authentik-Jwt>X-Auth-Token",
)


@dataclass(frozen=True)
class EdgeAuthRegistration:
    mode: str = AUTH_MODE_BASIC
    gateway_service: str = DEFAULT_EDGE_AUTH_GATEWAY_SERVICE
    gateway_port: str = DEFAULT_EDGE_AUTH_GATEWAY_PORT
    verify_uri: str = DEFAULT_EDGE_AUTH_VERIFY_URI
    copy_headers: tuple[str, ...] = DEFAULT_AUTHENTIK_COPY_HEADERS
    auth_policy: str = DEFAULT_AUTH_POLICY
    auth_proof_level: str = DEFAULT_AUTH_PROOF_LEVEL
    auth_audience: str = ""
    auth_secret_ref: str = ""

    def normalized(self) -> "EdgeAuthRegistration":
        mode = self.mode.strip().lower() or AUTH_MODE_BASIC
        if mode not in {AUTH_MODE_BASIC, AUTH_MODE_OIDC, AUTH_MODE_PUBLIC}:
            raise ValueError(f"Unsupported edge auth mode: {self.mode}")

        gateway_service = _validated_caddy_token(
            self.gateway_service.strip() or DEFAULT_EDGE_AUTH_GATEWAY_SERVICE,
            field_name="gateway_service",
        )
        gateway_port = self.gateway_port.strip() or DEFAULT_EDGE_AUTH_GATEWAY_PORT
        if not gateway_port.isdigit():
            raise ValueError("gateway_port must be numeric")

        verify_uri = self.verify_uri.strip() or DEFAULT_EDGE_AUTH_VERIFY_URI
        if not verify_uri.startswith("/") or re.search(r"\s", verify_uri):
            raise ValueError("verify_uri must be an absolute path without whitespace")

        copy_headers = tuple(_validated_header_copy(item.strip()) for item in self.copy_headers if item.strip())
        if mode == AUTH_MODE_OIDC and not copy_headers:
            raise ValueError("copy_headers must not be empty when edge auth mode is oidc")

        return EdgeAuthRegistration(
            mode=mode,
            gateway_service=gateway_service,
            gateway_port=gateway_port,
            verify_uri=verify_uri,
            copy_headers=copy_headers or DEFAULT_AUTHENTIK_COPY_HEADERS,
            auth_policy=self.auth_policy.strip() or DEFAULT_AUTH_POLICY,
            auth_proof_level=self.auth_proof_level.strip() or DEFAULT_AUTH_PROOF_LEVEL,
            auth_audience=self.auth_audience.strip(),
            auth_secret_ref=self.auth_secret_ref.strip(),
        )

# Template for the site block.  Placeholders: {domain}, {service}, {port}.
SITE_BLOCK_TEMPLATE = """\

# -------------------------
# {domain} Route (auto-registered)
# -------------------------
{domain} {{
    tls {{$ACME_EMAIL}}
    encode gzip
    header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"

    basic_auth /* {{
        {{$BASIC_AUTH_USER}} {{$BASIC_AUTH_HASH}}
    }}

    reverse_proxy {service}:{port}
}}
"""

OIDC_SITE_BLOCK_TEMPLATE = """\

# -------------------------
# {domain} Route (auto-registered)
# -------------------------
{metadata}{domain} {{
    tls {{$ACME_EMAIL}}
    encode gzip
    header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"

    route {{
        import protected_auth
        reverse_proxy {service}:{port}
    }}
}}
"""

PUBLIC_SITE_BLOCK_TEMPLATE = """\

# -------------------------
# {domain} Route (auto-registered)
# -------------------------
{domain} {{
    tls {{$ACME_EMAIL}}
    encode gzip
    header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"

    reverse_proxy {service}:{port}
}}
"""

PROTECTED_AUTH_SNIPPET_TEMPLATE = """\
({snippet_name}) {{
    request_header -X-Auth-*
    request_header -X-Authentik-*

    reverse_proxy /outpost.goauthentik.io/* {gateway_service}:{gateway_port}

    forward_auth {gateway_service}:{gateway_port} {{
        uri {verify_uri}
        copy_headers {{
{copy_headers}
        }}
        trusted_proxies private_ranges
    }}
}}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ssh_run(
    host: str,
    cmd: str,
    *,
    check: bool = True,
    capture: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess:
    """Run *cmd* on *host* via SSH."""
    full = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        host,
        cmd,
    ]
    return subprocess.run(
        full,
        input=input_text,
        capture_output=capture,
        text=True,
        check=check,
    )


def _domain_present(caddyfile_text: str, domain: str) -> bool:
    """Return True if *domain* already has a site block."""
    pattern = re.compile(
        r"^(?!\s*#)\s*" + re.escape(domain) + r"\s*\{",
        re.MULTILINE,
    )
    return bool(pattern.search(caddyfile_text))


def _public_domain_placeholder_present(caddyfile_text: str) -> bool:
    """Return True when a site block uses {$PUBLIC_DOMAIN}."""
    pattern = re.compile(r"^(?!\s*#)\s*\{\$PUBLIC_DOMAIN\}\s*\{", re.MULTILINE)
    return bool(pattern.search(caddyfile_text))


def _remote_public_domain(*, ssh_host: str, caddy_container: str) -> str:
    """Read PUBLIC_DOMAIN from remote Caddy container env if available."""
    cmd = (
        f"docker inspect {shlex.quote(caddy_container)} "
        "--format '{{range .Config.Env}}{{println .}}{{end}}' "
        "| grep '^PUBLIC_DOMAIN=' | head -n1 | cut -d= -f2-"
    )
    result = _ssh_run(ssh_host, cmd, check=False)
    if result.returncode != 0:
        return ""
    return str(result.stdout or "").strip()


def _result_text(result: subprocess.CompletedProcess) -> str:
    stderr = str(result.stderr or "").strip()
    stdout = str(result.stdout or "").strip()
    return stderr or stdout


def _find_site_block(caddyfile_text: str, site_label: str) -> str | None:
    """Return the full site block for *site_label* when present."""
    header_pattern = re.compile(
        r"^(?!\s*#)\s*" + re.escape(site_label) + r"\s*\{\s*$"
    )
    lines = caddyfile_text.splitlines(keepends=True)
    block_lines: list[str] = []
    depth = 0
    in_block = False

    for line in lines:
        normalized_line = line.rstrip("\r\n")
        stripped_line = normalized_line.strip()

        if not in_block:
            if not header_pattern.match(normalized_line):
                continue
            in_block = True
            depth = 1
            block_lines.append(line)
            continue

        block_lines.append(line)
        if stripped_line == "}":
            depth -= 1
            if depth == 0:
                return "".join(block_lines)
            continue

        if stripped_line.endswith("{") and not stripped_line.startswith("#"):
            depth += 1

    return None


def _site_block_has_basic_auth(site_block: str) -> bool:
    """Return True when *site_block* contains a live basic_auth directive."""
    pattern = re.compile(r"^(?!\s*#)\s*basic_auth\b", re.MULTILINE)
    return bool(pattern.search(site_block))


def _site_block_imports_protected_auth(site_block: str) -> bool:
    """Return True when *site_block* imports the shared OIDC auth guard."""
    pattern = re.compile(r"^(?!\s*#)\s*import\s+protected_auth\b", re.MULTILINE)
    return bool(pattern.search(site_block))


def _site_block_is_unprotected(site_block: str) -> bool:
    return not _site_block_has_basic_auth(site_block) and not _site_block_imports_protected_auth(site_block)


def _site_block_matches_auth(site_block: str, edge_auth: EdgeAuthRegistration) -> bool:
    if edge_auth.mode == AUTH_MODE_BASIC:
        return _site_block_has_basic_auth(site_block)
    if edge_auth.mode == AUTH_MODE_OIDC:
        return _site_block_imports_protected_auth(site_block)
    if edge_auth.mode == AUTH_MODE_PUBLIC:
        return _site_block_is_unprotected(site_block)
    return False


def _validated_caddy_token(value: str, *, field_name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise ValueError(f"{field_name} contains characters that are not safe in a Caddy upstream token")
    return value


def _validated_header_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9-]+", value):
        raise ValueError(f"Invalid HTTP header name: {value}")
    return value


def _validated_header_copy(value: str) -> str:
    source, separator, destination = value.partition(">")
    source_header = _validated_header_name(source.strip())
    if not separator:
        return source_header
    destination_header = _validated_header_name(destination.strip())
    return f"{source_header}>{destination_header}"


def parse_copy_headers(value: str) -> tuple[str, ...]:
    return tuple(_validated_header_copy(item.strip()) for item in value.split(",") if item.strip())


def _safe_comment_value(value: str) -> str:
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())


def _route_metadata(edge_auth: EdgeAuthRegistration) -> str:
    if edge_auth.mode != AUTH_MODE_OIDC:
        return ""

    metadata: list[str] = [
        f"# edge-auth-mode: {edge_auth.mode}\n",
        f"# edge-auth-policy: {_safe_comment_value(edge_auth.auth_policy)}\n",
        f"# edge-auth-proof-level: {_safe_comment_value(edge_auth.auth_proof_level)}\n",
    ]
    if edge_auth.auth_audience:
        metadata.append(f"# edge-auth-audience: {_safe_comment_value(edge_auth.auth_audience)}\n")
    if edge_auth.auth_secret_ref:
        metadata.append(f"# edge-auth-secret-ref: {_safe_comment_value(edge_auth.auth_secret_ref)}\n")
    return "".join(metadata)


def _render_protected_auth_snippet(edge_auth: EdgeAuthRegistration) -> str:
    copy_headers = "\n".join(f"            {header}" for header in edge_auth.copy_headers)
    return PROTECTED_AUTH_SNIPPET_TEMPLATE.format(
        snippet_name=PROTECTED_AUTH_SNIPPET_NAME,
        gateway_service=edge_auth.gateway_service,
        gateway_port=edge_auth.gateway_port,
        verify_uri=edge_auth.verify_uri,
        copy_headers=copy_headers,
    )


def _caddyfile_with_auth_snippet(caddyfile_text: str, edge_auth: EdgeAuthRegistration) -> str:
    if edge_auth.mode != AUTH_MODE_OIDC:
        return caddyfile_text

    expected_snippet = _render_protected_auth_snippet(edge_auth)
    existing_snippet = _find_site_block(caddyfile_text, f"({PROTECTED_AUTH_SNIPPET_NAME})")
    if existing_snippet is None:
        separator = "" if caddyfile_text.endswith("\n") else "\n"
        return f"{caddyfile_text}{separator}\n{expected_snippet}"
    if existing_snippet.strip() == expected_snippet.strip():
        return caddyfile_text
    return caddyfile_text.replace(existing_snippet, expected_snippet, 1)


def _write_remote_caddyfile(*, ssh_host: str, caddyfile_path: str, content: str, append: bool) -> None:
    """Write *content* to the remote Caddyfile, appending or replacing it."""
    tee_flag = "-a " if append else ""
    write_cmd = f"tee {tee_flag}{shlex.quote(caddyfile_path)} > /dev/null"
    full = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        ssh_host,
        write_cmd,
    ]
    try:
        subprocess.run(full, input=content, text=True, capture_output=True, check=True)
    except subprocess.CalledProcessError as exc:
        detail = str(exc.stderr or "").strip() or str(exc.stdout or "").strip()
        action = "append to" if append else "rewrite"
        raise RuntimeError(
            f"Failed to {action} Caddyfile on {ssh_host}: {detail}"
        )


def _render_site_block(*, domain: str, service: str, port: str, edge_auth: EdgeAuthRegistration | None = None) -> str:
    """Render a protected site block for *domain*."""
    resolved_edge_auth = (edge_auth or EdgeAuthRegistration()).normalized()
    if resolved_edge_auth.mode == AUTH_MODE_OIDC:
        return OIDC_SITE_BLOCK_TEMPLATE.format(
            domain=domain,
            service=service,
            port=port,
            metadata=_route_metadata(resolved_edge_auth),
        )
    if resolved_edge_auth.mode == AUTH_MODE_PUBLIC:
        return PUBLIC_SITE_BLOCK_TEMPLATE.format(domain=domain, service=service, port=port)
    return SITE_BLOCK_TEMPLATE.format(domain=domain, service=service, port=port)


def _restart_and_validate_caddy(*, ssh_host: str, caddy_container: str) -> None:
    """Restart the Caddy container and validate its active config."""
    logger.info("%s Restarting %s to pick up config", LOG_PREFIX, caddy_container)
    restart_result = _ssh_run(
        ssh_host,
        f"docker restart {shlex.quote(caddy_container)}",
        check=False,
    )
    if restart_result.returncode != 0:
        detail = _result_text(restart_result)
        raise RuntimeError(
            f"Failed to restart {caddy_container} on {ssh_host}: {detail}"
        )

    validate_cmd = (
        f"sleep 3 && docker exec {shlex.quote(caddy_container)} "
        f"caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile"
    )
    validate_result = _ssh_run(ssh_host, validate_cmd, check=False)
    if validate_result.returncode != 0:
        detail = _result_text(validate_result)
        raise RuntimeError(
            "Caddy registration appended the route but config validation failed: "
            f"{detail}. Check remote logs with: docker logs {caddy_container}"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ensure_caddy_registration(
    *,
    ssh_host: str,
    domain: str,
    service: str,
    port: str | int,
    caddyfile_path: str,
    caddy_container: str = DEFAULT_CADDY_CONTAINER,
    edge_auth: EdgeAuthRegistration | None = None,
    dry_run: bool = False,
) -> bool:
    """Ensure *domain* has a site block in the remote Caddyfile.

    Returns True if the block was added, False if already present.
    Raises on SSH or validation failure.
    """
    port = str(port)
    resolved_edge_auth = (edge_auth or EdgeAuthRegistration()).normalized()

    # 1. Read current Caddyfile from the host  ───────────────────────────
    result = _ssh_run(ssh_host, f"cat {shlex.quote(caddyfile_path)}", check=False)
    if result.returncode != 0:
        # Caddyfile not found — proxy stack not deployed yet.  Skip silently.
        logger.warning(
            "%s Caddyfile not found at %s; proxy stack may not be deployed yet. Skipping registration.",
            LOG_PREFIX,
            caddyfile_path,
        )
        return False

    caddyfile_text = result.stdout
    expected_block = _render_site_block(domain=domain, service=service, port=port, edge_auth=resolved_edge_auth)
    existing_domain_block = _find_site_block(caddyfile_text, domain)

    # 2. Already registered?  ────────────────────────────────────────────
    if existing_domain_block is not None:
        if _site_block_matches_auth(existing_domain_block, resolved_edge_auth):
            logger.info("%s %s already registered", LOG_PREFIX, domain)
            return False

        logger.warning(
            "%s %s has a stale or mismatched Caddy route; rewriting it for edge auth mode %s.",
            LOG_PREFIX,
            domain,
            resolved_edge_auth.mode,
        )
        updated_caddyfile_text = caddyfile_text.replace(existing_domain_block, expected_block, 1)
        updated_caddyfile_text = _caddyfile_with_auth_snippet(updated_caddyfile_text, resolved_edge_auth)

        if dry_run:
            logger.info("%s [dry-run] Would rewrite route for %s", LOG_PREFIX, domain)
            logger.debug("%s [dry-run] Rewritten block:\n%s", LOG_PREFIX, expected_block)
            return True

        _write_remote_caddyfile(
            ssh_host=ssh_host,
            caddyfile_path=caddyfile_path,
            content=updated_caddyfile_text,
            append=False,
        )

        result2 = _ssh_run(ssh_host, f"cat {shlex.quote(caddyfile_path)}")
        updated_domain_block = _find_site_block(str(result2.stdout or ""), domain)
        if updated_domain_block is None:
            raise RuntimeError(
                f"Rewrote Caddy block for {domain} but it was not found on re-read"
            )
        if not _site_block_matches_auth(updated_domain_block, resolved_edge_auth):
            raise RuntimeError(
                f"Rewrote Caddy block for {domain} but it still does not match edge auth mode {resolved_edge_auth.mode}"
            )

        caddyfile_text = str(result2.stdout or "")
        _restart_and_validate_caddy(ssh_host=ssh_host, caddy_container=caddy_container)
        logger.info("%s Registered %s -> %s:%s", LOG_PREFIX, domain, service, port)
        return True

    # Special case: the base Caddyfile may already define {$PUBLIC_DOMAIN}.
    # If that placeholder resolves to this domain in the running proxy
    # container, skip appending a literal duplicate site block.
    placeholder_block = _find_site_block(caddyfile_text, "{$PUBLIC_DOMAIN}")

    if placeholder_block is not None:
        resolved_public_domain = _remote_public_domain(
            ssh_host=ssh_host,
            caddy_container=caddy_container,
        )
        if resolved_public_domain and resolved_public_domain == domain:
            if not _site_block_matches_auth(placeholder_block, resolved_edge_auth):
                expected_placeholder_block = _render_site_block(
                    domain="{$PUBLIC_DOMAIN}",
                    service=service,
                    port=port,
                    edge_auth=resolved_edge_auth,
                )
                logger.warning(
                    "%s %s is covered by {$PUBLIC_DOMAIN} but the placeholder route is stale; rewriting it for edge auth mode %s.",
                    LOG_PREFIX,
                    domain,
                    resolved_edge_auth.mode,
                )
                updated_caddyfile_text = caddyfile_text.replace(placeholder_block, expected_placeholder_block, 1)
                updated_caddyfile_text = _caddyfile_with_auth_snippet(updated_caddyfile_text, resolved_edge_auth)

                if dry_run:
                    logger.info("%s [dry-run] Would rewrite {$PUBLIC_DOMAIN} route for %s", LOG_PREFIX, domain)
                    logger.debug("%s [dry-run] Rewritten block:\n%s", LOG_PREFIX, expected_placeholder_block)
                    return True

                _write_remote_caddyfile(
                    ssh_host=ssh_host,
                    caddyfile_path=caddyfile_path,
                    content=updated_caddyfile_text,
                    append=False,
                )
                result2 = _ssh_run(ssh_host, f"cat {shlex.quote(caddyfile_path)}")
                updated_placeholder_block = _find_site_block(str(result2.stdout or ""), "{$PUBLIC_DOMAIN}")
                if updated_placeholder_block is None:
                    raise RuntimeError(
                        f"Rewrote {{$PUBLIC_DOMAIN}} Caddy block for {domain} but the placeholder block was not found on re-read"
                    )
                if not _site_block_matches_auth(updated_placeholder_block, resolved_edge_auth):
                    raise RuntimeError(
                        f"Rewrote {{$PUBLIC_DOMAIN}} Caddy block for {domain} but it still does not match edge auth mode {resolved_edge_auth.mode}"
                    )
                _restart_and_validate_caddy(ssh_host=ssh_host, caddy_container=caddy_container)
                logger.info("%s Registered %s -> %s:%s", LOG_PREFIX, domain, service, port)
                return True

            logger.info(
                "%s %s already covered by {$PUBLIC_DOMAIN} placeholder",
                LOG_PREFIX,
                domain,
            )
            return False

    # 3. Build the site block  ───────────────────────────────────────────
    caddyfile_with_snippet = _caddyfile_with_auth_snippet(caddyfile_text, resolved_edge_auth)
    needs_full_rewrite = caddyfile_with_snippet != caddyfile_text
    content_to_write = f"{caddyfile_with_snippet}{expected_block}" if needs_full_rewrite else expected_block

    if dry_run:
        action = "rewrite" if needs_full_rewrite else "append to"
        logger.info("%s [dry-run] Would %s %s", LOG_PREFIX, action, caddyfile_path)
        logger.debug("%s [dry-run] Appended block:\n%s", LOG_PREFIX, expected_block)
        return True

    # 4. Append to host Caddyfile  ──────────────────────────────────────
    _write_remote_caddyfile(
        ssh_host=ssh_host,
        caddyfile_path=caddyfile_path,
        content=content_to_write,
        append=not needs_full_rewrite,
    )

    # 5. Verify the write  ──────────────────────────────────────────────
    result2 = _ssh_run(ssh_host, f"cat {shlex.quote(caddyfile_path)}")
    updated_domain_block = _find_site_block(str(result2.stdout or ""), domain)
    if updated_domain_block is None:
        raise RuntimeError(
            f"Appended Caddy block for {domain} but it was not found on re-read"
        )
    if not _site_block_matches_auth(updated_domain_block, resolved_edge_auth):
        raise RuntimeError(
            f"Appended Caddy block for {domain} but it does not match edge auth mode {resolved_edge_auth.mode}"
        )

    # 6. Restart Caddy to pick up bind-mount changes & obtain cert  ─────
    _restart_and_validate_caddy(ssh_host=ssh_host, caddy_container=caddy_container)

    logger.info("%s Registered %s -> %s:%s", LOG_PREFIX, domain, service, port)
    return True


def is_domain_registered(
    *,
    ssh_host: str,
    domain: str,
    caddyfile_path: str,
    caddy_container: str = DEFAULT_CADDY_CONTAINER,
    edge_auth: EdgeAuthRegistration | None = None,
) -> bool:
    """Return True when *domain* is covered by the remote Caddy config.

    Coverage is satisfied when either:
    - a literal site block exists for ``domain`` and matches the selected auth mode, or
    - a ``{$PUBLIC_DOMAIN}`` site block exists and resolves to ``domain``
      in the running Caddy container environment and matches the selected auth mode.
    """
    resolved_edge_auth = (edge_auth or EdgeAuthRegistration()).normalized()
    result = _ssh_run(ssh_host, f"cat {shlex.quote(caddyfile_path)}", check=False)
    if result.returncode != 0:
        return False

    caddyfile_text = str(result.stdout or "")
    domain_block = _find_site_block(caddyfile_text, domain)
    if domain_block is not None:
        return _site_block_matches_auth(domain_block, resolved_edge_auth)

    placeholder_block = _find_site_block(caddyfile_text, "{$PUBLIC_DOMAIN}")
    if placeholder_block is not None:
        resolved_public_domain = _remote_public_domain(
            ssh_host=ssh_host,
            caddy_container=caddy_container,
        )
        if resolved_public_domain and resolved_public_domain == domain:
            return _site_block_matches_auth(placeholder_block, resolved_edge_auth)

    return False
