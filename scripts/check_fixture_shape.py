#!/usr/bin/env python3
"""Validate that audience conformance fixtures contain JSON objects."""

from __future__ import annotations

import json
from pathlib import Path


FIXTURE_DIRECTORY = Path("conformance/audience/v1")


def main() -> None:
    if not FIXTURE_DIRECTORY.is_dir():
        return

    for fixture_path in sorted(FIXTURE_DIRECTORY.glob("*.jsonl")):
        with fixture_path.open(encoding="utf-8") as fixture:
            for line_number, line in enumerate(fixture, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(
                        f"{fixture_path}:{line_number}: expected a JSON object"
                    )


if __name__ == "__main__":
    main()
