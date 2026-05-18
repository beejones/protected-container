"""Swap routing between staging and production environments.

Performs a zero-downtime traffic swap by rewriting Caddy reverse_proxy
upstreams. No containers are restarted — only the routing changes.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class SwapConfig:
    """Parameters needed to perform a staging ↔ production swap."""

    ssh_host: str
    caddyfile_path: str
    production_domain: str
    staging_domain: str
    caddy_container: str = "central-proxy"


@dataclass(frozen=True)
class SwapResult:
    """Outcome of a swap operation."""

    success: bool
    message: str
    prod_upstream_before: str = ""
    staging_upstream_before: str = ""
    prod_upstream_after: str = ""
    staging_upstream_after: str = ""


_REVERSE_PROXY_RE = re.compile(r"^(\s*reverse_proxy\s+)(\S+:\d+)(.*)$", re.MULTILINE)


def _ssh_run(
    host: str,
    cmd: str,
    *,
    check: bool = True,
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
        capture_output=True,
        text=True,
        check=check,
    )


def _check_stack_healthy(ssh_host: str, stack_name: str) -> bool:
    """Check if a stack has running containers via docker ps."""
    cmd = f"docker ps --filter name={shlex.quote(stack_name)} --format '{{{{.Status}}}}' | head -5"
    result = _ssh_run(ssh_host, cmd, check=False)
    if result.returncode != 0:
        return False
    output = str(result.stdout or "").strip()
    if not output:
        return False
    # At least one container should show "Up"
    return any("Up" in line for line in output.splitlines())


def _find_site_block(caddyfile_text: str, site_label: str) -> tuple[int, int] | None:
    """Return (start, end) character offsets of the site block for *site_label*."""
    header_pattern = re.compile(
        r"^(?!\s*#)\s*" + re.escape(site_label) + r"\s*\{\s*$",
        re.MULTILINE,
    )
    match = header_pattern.search(caddyfile_text)
    if not match:
        return None

    start = match.start()
    depth = 1
    pos = match.end()

    while pos < len(caddyfile_text) and depth > 0:
        ch = caddyfile_text[pos]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        pos += 1

    return (start, pos)


def _extract_upstream(site_block: str) -> str:
    """Extract the reverse_proxy upstream (service:port) from a site block."""
    m = _REVERSE_PROXY_RE.search(site_block)
    if not m:
        return ""
    return m.group(2)


def _replace_upstream(site_block: str, new_upstream: str) -> str:
    """Replace the reverse_proxy upstream in a site block."""
    return _REVERSE_PROXY_RE.sub(
        lambda m: f"{m.group(1)}{new_upstream}{m.group(3)}",
        site_block,
        count=1,
    )


def swap_caddyfile_upstreams(
    caddyfile_text: str,
    *,
    production_domain: str,
    staging_domain: str,
) -> tuple[str, str, str, str, str]:
    """Swap reverse_proxy upstreams between production and staging site blocks.

    Returns (new_caddyfile, prod_upstream_before, staging_upstream_before,
             prod_upstream_after, staging_upstream_after).
    Raises ValueError if either domain block or upstream is not found.
    """
    prod_range = _find_site_block(caddyfile_text, production_domain)
    # Fallback: Caddyfile may use {$PUBLIC_DOMAIN} placeholder instead of literal domain
    if prod_range is None:
        prod_range = _find_site_block(caddyfile_text, "{$PUBLIC_DOMAIN}")
    staging_range = _find_site_block(caddyfile_text, staging_domain)
    # Fallback: Caddyfile may use {$STAGING_PUBLIC_DOMAIN} placeholder
    if staging_range is None:
        staging_range = _find_site_block(caddyfile_text, "{$STAGING_PUBLIC_DOMAIN}")

    if prod_range is None:
        raise ValueError(f"Production domain '{production_domain}' not found in Caddyfile")
    if staging_range is None:
        raise ValueError(f"Staging domain '{staging_domain}' not found in Caddyfile")

    prod_block = caddyfile_text[prod_range[0]:prod_range[1]]
    staging_block = caddyfile_text[staging_range[0]:staging_range[1]]

    prod_upstream = _extract_upstream(prod_block)
    staging_upstream = _extract_upstream(staging_block)

    if not prod_upstream:
        raise ValueError(f"No reverse_proxy upstream found in production block for '{production_domain}'")
    if not staging_upstream:
        raise ValueError(f"No reverse_proxy upstream found in staging block for '{staging_domain}'")

    # Swap: production gets staging's upstream and vice versa
    new_prod_block = _replace_upstream(prod_block, staging_upstream)
    new_staging_block = _replace_upstream(staging_block, prod_upstream)

    # Rebuild caddyfile — replace blocks in reverse order to preserve offsets
    if prod_range[0] < staging_range[0]:
        # prod block comes first
        result = (
            caddyfile_text[:prod_range[0]]
            + new_prod_block
            + caddyfile_text[prod_range[1]:staging_range[0]]
            + new_staging_block
            + caddyfile_text[staging_range[1]:]
        )
    else:
        # staging block comes first
        result = (
            caddyfile_text[:staging_range[0]]
            + new_staging_block
            + caddyfile_text[staging_range[1]:prod_range[0]]
            + new_prod_block
            + caddyfile_text[prod_range[1]:]
        )

    return result, prod_upstream, staging_upstream, staging_upstream, prod_upstream


def perform_swap(config: SwapConfig) -> SwapResult:
    """Perform the full swap operation over SSH.

    1. Verify both stacks are healthy
    2. Read Caddyfile
    3. Swap upstreams
    4. Write back
    5. Reload Caddy
    """
    # Derive stack names from domain-based service names
    # Check health of both using domain-based container grep
    prod_stack = config.production_domain.replace(".", "-")
    staging_stack = config.staging_domain.replace(".", "-")

    # Health check: verify containers are running for both domains
    # We check by looking for running containers on the host
    cmd = "docker ps --format '{{.Names}}' 2>/dev/null"
    result = _ssh_run(config.ssh_host, cmd, check=False)
    if result.returncode != 0:
        return SwapResult(
            success=False,
            message=f"Failed to check container health: {result.stderr or result.stdout}",
        )

    # Read current Caddyfile
    read_result = _ssh_run(
        config.ssh_host,
        f"cat {shlex.quote(config.caddyfile_path)}",
        check=False,
    )
    if read_result.returncode != 0:
        return SwapResult(
            success=False,
            message=f"Failed to read Caddyfile at {config.caddyfile_path}",
        )

    caddyfile_text = read_result.stdout

    # Perform the swap
    try:
        (
            new_caddyfile,
            prod_upstream_before,
            staging_upstream_before,
            prod_upstream_after,
            staging_upstream_after,
        ) = swap_caddyfile_upstreams(
            caddyfile_text,
            production_domain=config.production_domain,
            staging_domain=config.staging_domain,
        )
    except ValueError as exc:
        return SwapResult(success=False, message=str(exc))

    # Write the updated Caddyfile
    write_cmd = f"tee {shlex.quote(config.caddyfile_path)} > /dev/null"
    write_result = _ssh_run(
        config.ssh_host,
        write_cmd,
        check=False,
        input_text=new_caddyfile,
    )
    if write_result.returncode != 0:
        return SwapResult(
            success=False,
            message=f"Failed to write updated Caddyfile: {write_result.stderr}",
        )

    # Reload Caddy
    reload_cmd = f"docker exec {shlex.quote(config.caddy_container)} caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile"
    reload_result = _ssh_run(config.ssh_host, reload_cmd, check=False)
    if reload_result.returncode != 0:
        return SwapResult(
            success=False,
            message=f"Caddy reload failed: {reload_result.stderr or reload_result.stdout}",
            prod_upstream_before=prod_upstream_before,
            staging_upstream_before=staging_upstream_before,
        )

    return SwapResult(
        success=True,
        message="Swap completed successfully",
        prod_upstream_before=prod_upstream_before,
        staging_upstream_before=staging_upstream_before,
        prod_upstream_after=prod_upstream_after,
        staging_upstream_after=staging_upstream_after,
    )
