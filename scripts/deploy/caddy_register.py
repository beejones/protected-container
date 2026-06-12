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


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Container name (from docker/proxy/docker-compose.yml).
DEFAULT_CADDY_CONTAINER = "central-proxy"
LOG_PREFIX = "[CADDY-REGISTER]"


logger = logging.getLogger(__name__)

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


def _site_block_has_expected_upstream(
    site_block: str,
    *,
    service: str,
    port: str,
) -> bool:
    """Return True when *site_block* proxies to the expected service port."""
    expected_upstream = f"{service}:{port}"
    pattern = re.compile(
        r"^(?!\s*#)\s*reverse_proxy\s+"
        + re.escape(expected_upstream)
        + r"(?:\s|\{|$)",
        re.MULTILINE,
    )
    return bool(pattern.search(site_block))


def _site_block_matches_expected_route(
    site_block: str,
    *,
    service: str,
    port: str,
) -> bool:
    """Return True when *site_block* is protected and points at the app."""
    return _site_block_has_basic_auth(site_block) and _site_block_has_expected_upstream(
        site_block,
        service=service,
        port=port,
    )


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


def _render_site_block(*, domain: str, service: str, port: str) -> str:
    """Render a protected site block for *domain*."""
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
    dry_run: bool = False,
) -> bool:
    """Ensure *domain* has a site block in the remote Caddyfile.

    Returns True if the block was added, False if already present.
    Raises on SSH or validation failure.
    """
    port = str(port)

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
    expected_block = _render_site_block(domain=domain, service=service, port=port)
    existing_domain_block = _find_site_block(caddyfile_text, domain)

    # 2. Already registered?  ────────────────────────────────────────────
    if existing_domain_block is not None:
        if _site_block_matches_expected_route(
            existing_domain_block,
            service=service,
            port=port,
        ):
            logger.info("%s %s already registered", LOG_PREFIX, domain)
            return False

        logger.warning(
            "%s %s has a stale Caddy route; rewriting it with basic_auth and upstream %s:%s.",
            LOG_PREFIX,
            domain,
            service,
            port,
        )
        updated_caddyfile_text = caddyfile_text.replace(existing_domain_block, expected_block, 1)

        if dry_run:
            logger.info("%s [dry-run] Would rewrite unprotected route for %s", LOG_PREFIX, domain)
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
        if not _site_block_matches_expected_route(
            updated_domain_block,
            service=service,
            port=port,
        ):
            raise RuntimeError(
                f"Rewrote Caddy block for {domain} but it still does not match basic_auth plus upstream {service}:{port}"
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
            if _site_block_matches_expected_route(
                placeholder_block,
                service=service,
                port=port,
            ):
                logger.info(
                    "%s %s already covered by {$PUBLIC_DOMAIN} placeholder",
                    LOG_PREFIX,
                    domain,
                )
                return False

            logger.info(
                "%s %s is covered by a stale {$PUBLIC_DOMAIN} placeholder; rewriting it with basic_auth and upstream %s:%s.",
                LOG_PREFIX,
                domain,
                service,
                port,
            )
            expected_placeholder_block = _render_site_block(
                domain="{$PUBLIC_DOMAIN}",
                service=service,
                port=port,
            )
            updated_caddyfile_text = caddyfile_text.replace(
                placeholder_block,
                expected_placeholder_block,
                1,
            )

            if dry_run:
                logger.info(
                    "%s [dry-run] Would rewrite {$PUBLIC_DOMAIN} placeholder for %s",
                    LOG_PREFIX,
                    domain,
                )
                logger.debug(
                    "%s [dry-run] Rewritten block:\n%s",
                    LOG_PREFIX,
                    expected_placeholder_block,
                )
                return True

            _write_remote_caddyfile(
                ssh_host=ssh_host,
                caddyfile_path=caddyfile_path,
                content=updated_caddyfile_text,
                append=False,
            )

            result2 = _ssh_run(ssh_host, f"cat {shlex.quote(caddyfile_path)}")
            updated_placeholder_block = _find_site_block(
                str(result2.stdout or ""),
                "{$PUBLIC_DOMAIN}",
            )
            if updated_placeholder_block is None:
                raise RuntimeError(
                    f"Rewrote {{$PUBLIC_DOMAIN}} Caddy block for {domain} but it was not found on re-read"
                )
            if not _site_block_matches_expected_route(
                updated_placeholder_block,
                service=service,
                port=port,
            ):
                raise RuntimeError(
                    f"Rewrote {{$PUBLIC_DOMAIN}} Caddy block for {domain} but it still does not match basic_auth plus upstream {service}:{port}"
                )

            _restart_and_validate_caddy(ssh_host=ssh_host, caddy_container=caddy_container)
            logger.info("%s Registered %s -> %s:%s", LOG_PREFIX, domain, service, port)
            return True

    # 3. Build the site block  ───────────────────────────────────────────
    block = expected_block

    if dry_run:
        logger.info("%s [dry-run] Would append to %s", LOG_PREFIX, caddyfile_path)
        logger.debug("%s [dry-run] Appended block:\n%s", LOG_PREFIX, block)
        return True

    # 4. Append to host Caddyfile  ──────────────────────────────────────
    _write_remote_caddyfile(
        ssh_host=ssh_host,
        caddyfile_path=caddyfile_path,
        content=block,
        append=True,
    )

    # 5. Verify the write  ──────────────────────────────────────────────
    result2 = _ssh_run(ssh_host, f"cat {shlex.quote(caddyfile_path)}")
    updated_domain_block = _find_site_block(str(result2.stdout or ""), domain)
    if updated_domain_block is None:
        raise RuntimeError(
            f"Appended Caddy block for {domain} but it was not found on re-read"
        )
    if not _site_block_has_basic_auth(updated_domain_block):
        raise RuntimeError(
            f"Appended Caddy block for {domain} but it is missing basic_auth"
        )

    # 6. Restart Caddy to pick up bind-mount changes & obtain cert  ─────
    _restart_and_validate_caddy(ssh_host=ssh_host, caddy_container=caddy_container)

    logger.info("%s Registered %s -> %s:%s", LOG_PREFIX, domain, service, port)
    return True


def is_domain_registered(
    *,
    ssh_host: str,
    domain: str,
    service: str,
    port: str | int,
    caddyfile_path: str,
    caddy_container: str = DEFAULT_CADDY_CONTAINER,
) -> bool:
    """Return True when *domain* is covered by the remote Caddy config.

    Coverage is satisfied when either:
    - a literal site block exists for ``domain`` and includes ``basic_auth``
      plus the expected ``reverse_proxy`` upstream, or
    - a ``{$PUBLIC_DOMAIN}`` site block exists and resolves to ``domain``
      in the running Caddy container environment and includes ``basic_auth``
      plus the expected ``reverse_proxy`` upstream.
    """
    port = str(port)

    result = _ssh_run(ssh_host, f"cat {shlex.quote(caddyfile_path)}", check=False)
    if result.returncode != 0:
        return False

    caddyfile_text = str(result.stdout or "")
    domain_block = _find_site_block(caddyfile_text, domain)
    if domain_block is not None:
        return _site_block_matches_expected_route(
            domain_block,
            service=service,
            port=port,
        )

    placeholder_block = _find_site_block(caddyfile_text, "{$PUBLIC_DOMAIN}")
    if placeholder_block is not None:
        resolved_public_domain = _remote_public_domain(
            ssh_host=ssh_host,
            caddy_container=caddy_container,
        )
        if resolved_public_domain and resolved_public_domain == domain:
            return _site_block_matches_expected_route(
                placeholder_block,
                service=service,
                port=port,
            )

    return False
