"""Tests for scripts/deploy/swap_environment.py."""

from __future__ import annotations

import pytest

from scripts.deploy.swap_environment import (
    SwapConfig,
    _extract_upstream,
    _find_site_block,
    _replace_upstream,
    swap_caddyfile_upstreams,
)


SAMPLE_CADDYFILE = """\
# Global options
{
    email admin@example.com
}

# -------------------------
# prod.example.com Route (auto-registered)
# -------------------------
prod.example.com {
    tls {$ACME_EMAIL}
    encode gzip
    header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"

    basic_auth /* {
        {$BASIC_AUTH_USER} {$BASIC_AUTH_HASH}
    }

    reverse_proxy protected-container-app:3000
}

# -------------------------
# staging.example.com Route (auto-registered)
# -------------------------
staging.example.com {
    tls {$ACME_EMAIL}
    encode gzip
    header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"

    basic_auth /* {
        {$BASIC_AUTH_USER} {$BASIC_AUTH_HASH}
    }

    reverse_proxy protected-container-staging-app:3000
}
"""


class TestFindSiteBlock:
    def test_finds_production_block(self) -> None:
        result = _find_site_block(SAMPLE_CADDYFILE, "prod.example.com")
        assert result is not None
        block = SAMPLE_CADDYFILE[result[0]:result[1]]
        assert "prod.example.com {" in block
        assert "reverse_proxy protected-container-app:3000" in block

    def test_finds_staging_block(self) -> None:
        result = _find_site_block(SAMPLE_CADDYFILE, "staging.example.com")
        assert result is not None
        block = SAMPLE_CADDYFILE[result[0]:result[1]]
        assert "staging.example.com {" in block
        assert "reverse_proxy protected-container-staging-app:3000" in block

    def test_returns_none_for_missing(self) -> None:
        result = _find_site_block(SAMPLE_CADDYFILE, "missing.example.com")
        assert result is None


class TestExtractUpstream:
    def test_extracts_upstream(self) -> None:
        block = "prod.example.com {\n    reverse_proxy my-service:8080\n}\n"
        assert _extract_upstream(block) == "my-service:8080"

    def test_returns_empty_when_missing(self) -> None:
        block = "prod.example.com {\n    encode gzip\n}\n"
        assert _extract_upstream(block) == ""


class TestReplaceUpstream:
    def test_replaces_upstream(self) -> None:
        block = "    reverse_proxy old-service:3000\n"
        result = _replace_upstream(block, "new-service:4000")
        assert "new-service:4000" in result
        assert "old-service:3000" not in result


class TestSwapCaddyfileUpstreams:
    def test_swaps_upstreams(self) -> None:
        new_caddyfile, prod_before, staging_before, prod_after, staging_after = swap_caddyfile_upstreams(
            SAMPLE_CADDYFILE,
            production_domain="prod.example.com",
            staging_domain="staging.example.com",
        )
        assert prod_before == "protected-container-app:3000"
        assert staging_before == "protected-container-staging-app:3000"
        assert prod_after == "protected-container-staging-app:3000"
        assert staging_after == "protected-container-app:3000"

        # Verify the new caddyfile has swapped upstreams
        prod_range = _find_site_block(new_caddyfile, "prod.example.com")
        assert prod_range is not None
        prod_block = new_caddyfile[prod_range[0]:prod_range[1]]
        assert "reverse_proxy protected-container-staging-app:3000" in prod_block

        staging_range = _find_site_block(new_caddyfile, "staging.example.com")
        assert staging_range is not None
        staging_block = new_caddyfile[staging_range[0]:staging_range[1]]
        assert "reverse_proxy protected-container-app:3000" in staging_block

    def test_double_swap_restores_original(self) -> None:
        swapped, _, _, _, _ = swap_caddyfile_upstreams(
            SAMPLE_CADDYFILE,
            production_domain="prod.example.com",
            staging_domain="staging.example.com",
        )
        restored, _, _, _, _ = swap_caddyfile_upstreams(
            swapped,
            production_domain="prod.example.com",
            staging_domain="staging.example.com",
        )
        assert restored == SAMPLE_CADDYFILE

    def test_missing_production_domain_raises(self) -> None:
        with pytest.raises(ValueError, match="Production domain"):
            swap_caddyfile_upstreams(
                SAMPLE_CADDYFILE,
                production_domain="missing.example.com",
                staging_domain="staging.example.com",
            )

    def test_missing_staging_domain_raises(self) -> None:
        with pytest.raises(ValueError, match="Staging domain"):
            swap_caddyfile_upstreams(
                SAMPLE_CADDYFILE,
                production_domain="prod.example.com",
                staging_domain="missing.example.com",
            )

    def test_missing_upstream_raises(self) -> None:
        # Caddyfile with a block that has no reverse_proxy
        caddyfile = "prod.example.com {\n    encode gzip\n}\nstaging.example.com {\n    reverse_proxy stg:3000\n}\n"
        with pytest.raises(ValueError, match="No reverse_proxy upstream"):
            swap_caddyfile_upstreams(
                caddyfile,
                production_domain="prod.example.com",
                staging_domain="staging.example.com",
            )

    def test_placeholder_public_domain_fallback(self) -> None:
        """Caddyfile uses {$PUBLIC_DOMAIN} placeholder instead of literal domain."""
        caddyfile = (
            "{$PUBLIC_DOMAIN} {\n"
            "    reverse_proxy app:3000\n"
            "}\n"
            "staging.example.com {\n"
            "    reverse_proxy staging-app:3000\n"
            "}\n"
        )
        new_caddyfile, prod_before, staging_before, prod_after, staging_after = swap_caddyfile_upstreams(
            caddyfile,
            production_domain="prod.example.com",
            staging_domain="staging.example.com",
        )
        assert prod_before == "app:3000"
        assert staging_before == "staging-app:3000"
        assert prod_after == "staging-app:3000"
        assert staging_after == "app:3000"

    def test_placeholder_staging_domain_fallback(self) -> None:
        """Caddyfile uses {$STAGING_PUBLIC_DOMAIN} placeholder."""
        caddyfile = (
            "prod.example.com {\n"
            "    reverse_proxy app:3000\n"
            "}\n"
            "{$STAGING_PUBLIC_DOMAIN} {\n"
            "    reverse_proxy staging-app:3000\n"
            "}\n"
        )
        new_caddyfile, prod_before, staging_before, prod_after, staging_after = swap_caddyfile_upstreams(
            caddyfile,
            production_domain="prod.example.com",
            staging_domain="staging.example.com",
        )
        assert prod_before == "app:3000"
        assert staging_before == "staging-app:3000"
        assert prod_after == "staging-app:3000"
        assert staging_after == "app:3000"
