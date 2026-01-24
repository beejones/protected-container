#!/usr/bin/env python3
"""Generate a GUID/UUID (v4).

Usage:
  scripts/generate_guid.py
  scripts/generate_guid.py --count 5

Notes:
- Prints one UUID per line.
- UUIDv4 is the common "GUID" format used in many systems.
"""

from __future__ import annotations

import argparse
import uuid


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate GUID/UUID (v4)")
    parser.add_argument("--count", "-n", type=int, default=1, help="How many UUIDs to generate (default: 1)")
    args = parser.parse_args()

    if args.count < 1:
        raise SystemExit("--count must be >= 1")

    for _ in range(args.count):
        print(str(uuid.uuid4()))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
