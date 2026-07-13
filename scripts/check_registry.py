#!/usr/bin/env python3
"""Fail closed unless the production audience registry matches approved v1 policy."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_REGISTRY = ROOT / "registry/audience/v1/attributes.textproto"
VERSION = "2026-07-12"
BASE_OPERATORS = {
    "AUDIENCE_OPERATOR_EQUALS",
    "AUDIENCE_OPERATOR_NOT_EQUALS",
    "AUDIENCE_OPERATOR_IN",
    "AUDIENCE_OPERATOR_NOT_IN",
    "AUDIENCE_OPERATOR_EXISTS",
    "AUDIENCE_OPERATOR_NOT_EXISTS",
}
STRING_PATTERN_OPERATORS = BASE_OPERATORS | {
    "AUDIENCE_OPERATOR_CONTAINS",
    "AUDIENCE_OPERATOR_REGEX",
}
NUMERIC_OPERATORS = BASE_OPERATORS | {
    "AUDIENCE_OPERATOR_GREATER_THAN",
    "AUDIENCE_OPERATOR_GREATER_THAN_OR_EQUALS",
    "AUDIENCE_OPERATOR_LESS_THAN",
    "AUDIENCE_OPERATOR_LESS_THAN_OR_EQUALS",
}
EXPECTED_POLICY = {
    "country_code": ("AUDIENCE_VALUE_TYPE_STRING", BASE_OPERATORS),
    "market_region": ("AUDIENCE_VALUE_TYPE_STRING", BASE_OPERATORS),
    "subscription_tier": ("AUDIENCE_VALUE_TYPE_STRING", BASE_OPERATORS),
    "account_age_days": ("AUDIENCE_VALUE_TYPE_INT64", NUMERIC_OPERATORS),
    "device_class": ("AUDIENCE_VALUE_TYPE_STRING", STRING_PATTERN_OPERATORS),
    "locale": ("AUDIENCE_VALUE_TYPE_STRING", BASE_OPERATORS),
    "maturity_context": ("AUDIENCE_VALUE_TYPE_STRING", BASE_OPERATORS),
    "platform": ("AUDIENCE_VALUE_TYPE_STRING", STRING_PATTERN_OPERATORS),
}
REQUIRED_METADATA = {
    "key",
    "valueType",
    "allowedOperators",
    "normalization",
    "sensitivity",
    "owner",
    "description",
}


def fail(message: str) -> None:
    raise SystemExit(message)


def parse_registry(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "buf",
            "convert",
            str(ROOT),
            "--type",
            "kaizen.audience.v1.AudienceAttributeRegistry",
            f"--from={path}#format=txtpb",
            "--to=-#format=json",
            "--validate",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip()
        fail(
            "registry failed schema parsing or validation"
            + (f": {detail}" if detail else "")
        )
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        fail(f"registry conversion did not return JSON: {error}")
    if not isinstance(parsed, dict):
        fail("registry conversion must return an object")
    return parsed


def validate_registry(registry: dict[str, Any]) -> None:
    if registry.get("version") != VERSION:
        fail(f"registry version must be {VERSION}")
    definitions = registry.get("definitions")
    if not isinstance(definitions, list) or len(definitions) != 8:
        fail("registry must contain exactly 8 definitions")

    keys = [definition.get("key") for definition in definitions]
    if len(set(keys)) != len(keys):
        fail("registry definition keys must be unique")
    if set(keys) != set(EXPECTED_POLICY):
        missing = sorted(set(EXPECTED_POLICY).difference(keys))
        extra = sorted(set(keys).difference(EXPECTED_POLICY))
        fail(f"registry keys mismatch: missing={missing}, extra={extra}")

    for definition in definitions:
        key = definition["key"]
        missing_metadata = REQUIRED_METADATA.difference(definition)
        if missing_metadata:
            fail(f"definition {key} missing metadata: {sorted(missing_metadata)}")
        if any(
            definition[field] in ("", [], None)
            for field in REQUIRED_METADATA.difference({"key"})
        ):
            fail(f"definition {key} contains empty required metadata")
        expected_type, expected_operators = EXPECTED_POLICY[key]
        actual_type = definition["valueType"]
        actual_operators = definition["allowedOperators"]
        if (
            actual_type != expected_type
            or not isinstance(actual_operators, list)
            or set(actual_operators) != expected_operators
            or len(actual_operators) != len(expected_operators)
        ):
            fail(f"type/operator policy mismatch for {key}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=PRODUCTION_REGISTRY)
    arguments = parser.parse_args()
    if not arguments.registry.is_file():
        fail(f"registry file is missing: {arguments.registry}")
    validate_registry(parse_registry(arguments.registry.resolve()))


if __name__ == "__main__":
    try:
        main()
    except SystemExit as error:
        if error.code not in (None, 0) and not isinstance(error.code, int):
            print(error.code, file=sys.stderr)
            raise SystemExit(1) from None
        raise
