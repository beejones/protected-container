#!/usr/bin/env python3
"""Preserve shared Caddy site blocks while refreshing the proxy template."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


SITE_HEADER_RE = re.compile(r"^(?!\s*#)\s*(?P<label>[^\s{]+)\s*\{\s*$")


@dataclass(frozen=True)
class CaddySiteBlock:
    """A top-level Caddy site block and its source span."""

    label: str
    text: str
    start: int
    end: int


def _find_site_blocks(caddyfile_text: str) -> list[CaddySiteBlock]:
    """Return top-level Caddy site blocks from a Caddyfile."""
    lines = caddyfile_text.splitlines(keepends=True)
    blocks: list[CaddySiteBlock] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped_line = line.strip()
        match = SITE_HEADER_RE.match(line.rstrip("\r\n"))
        if match is None or stripped_line.startswith(("{", ":")):
            index += 1
            continue

        start = index
        depth = 1
        index += 1
        while index < len(lines) and depth > 0:
            current_line = lines[index].strip()
            if current_line.endswith("{") and not current_line.startswith("#"):
                depth += 1
            if current_line == "}":
                depth -= 1
            index += 1

        blocks.append(
            CaddySiteBlock(
                label=match.group("label"),
                text="".join(lines[start:index]),
                start=start,
                end=index,
            )
        )

    return blocks


def _append_preserved_blocks(*, incoming_text: str, preserved_blocks: list[CaddySiteBlock]) -> str:
    """Append preserved site blocks to incoming Caddyfile text."""
    if not preserved_blocks:
        return incoming_text

    incoming = incoming_text.rstrip() + "\n"
    preserved_text = "\n".join(block.text.strip() for block in preserved_blocks)
    return f"{incoming}\n# -------------------------\n# Preserved Shared Routes\n# -------------------------\n{preserved_text}\n"


def preserve_shared_routes(*, existing_text: str, incoming_text: str) -> str:
    """Return incoming Caddyfile text plus existing routes absent from incoming."""
    incoming_labels = {block.label for block in _find_site_blocks(incoming_text)}
    preserved_blocks = [
        block
        for block in _find_site_blocks(existing_text)
        if block.label not in incoming_labels
    ]
    return _append_preserved_blocks(
        incoming_text=incoming_text,
        preserved_blocks=preserved_blocks,
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="Preserve shared Caddy routes during proxy refresh.")
    parser.add_argument("--existing", type=Path, required=True)
    parser.add_argument("--incoming", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    existing_text = args.existing.read_text(encoding="utf-8") if args.existing.exists() else ""
    incoming_text = args.incoming.read_text(encoding="utf-8")
    args.output.write_text(
        preserve_shared_routes(
            existing_text=existing_text,
            incoming_text=incoming_text,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())