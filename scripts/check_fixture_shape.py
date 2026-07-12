#!/usr/bin/env python3
"""Validate audience conformance fixture envelopes and declared fingerprints."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import rfc8785


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIRECTORY = ROOT / "conformance/audience/v1"
PRODUCTION_REGISTRY_VERSION = "2026-07-12"
FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
REQUIRED = {
    "caseId",
    "registryVersion",
    "rule",
    "context",
    "expectedDecision",
    "expectedReasonCodes",
}
DECISIONS = {
    "AUDIENCE_EVALUATION_DECISION_UNSPECIFIED",
    "AUDIENCE_EVALUATION_DECISION_MATCH",
    "AUDIENCE_EVALUATION_DECISION_NO_MATCH",
    "AUDIENCE_EVALUATION_DECISION_INVALID",
}
REASON_CODES = {
    "AUDIENCE_EVALUATION_REASON_CODE_MISSING_ATTRIBUTE",
    "AUDIENCE_EVALUATION_REASON_CODE_TYPE_MISMATCH",
    "AUDIENCE_EVALUATION_REASON_CODE_INVALID_ARITY",
    "AUDIENCE_EVALUATION_REASON_CODE_UNREGISTERED_ATTRIBUTE",
    "AUDIENCE_EVALUATION_REASON_CODE_DISALLOWED_OPERATOR",
    "AUDIENCE_EVALUATION_REASON_CODE_INVALID_REGEX",
    "AUDIENCE_EVALUATION_REASON_CODE_LIMIT_EXCEEDED",
    "AUDIENCE_EVALUATION_REASON_CODE_LEGACY_CONVERSION_FAILURE",
    "AUDIENCE_EVALUATION_REASON_CODE_INVALID_CONTEXT",
}
OPERATORS = {
    "AUDIENCE_OPERATOR_UNSPECIFIED",
    "AUDIENCE_OPERATOR_EQUALS",
    "AUDIENCE_OPERATOR_NOT_EQUALS",
    "AUDIENCE_OPERATOR_IN",
    "AUDIENCE_OPERATOR_NOT_IN",
    "AUDIENCE_OPERATOR_GREATER_THAN",
    "AUDIENCE_OPERATOR_GREATER_THAN_OR_EQUALS",
    "AUDIENCE_OPERATOR_LESS_THAN",
    "AUDIENCE_OPERATOR_LESS_THAN_OR_EQUALS",
    "AUDIENCE_OPERATOR_CONTAINS",
    "AUDIENCE_OPERATOR_REGEX",
    "AUDIENCE_OPERATOR_EXISTS",
    "AUDIENCE_OPERATOR_NOT_EXISTS",
}
INTEGER = re.compile(r"-?(?:0|[1-9][0-9]*)$")
INT64_STRING = re.compile(r"-?(?:0|[1-9][0-9]*)$")
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1
VALID_PROVENANCE = {
    "AUDIENCE_ATTRIBUTE_PROVENANCE_OBSERVED",
    "AUDIENCE_ATTRIBUTE_PROVENANCE_SYNTHETIC",
    "AUDIENCE_ATTRIBUTE_PROVENANCE_DEFAULT",
    "AUDIENCE_ATTRIBUTE_PROVENANCE_OVERLAY",
}


class JsonInteger:
    def __init__(self, lexeme: str) -> None:
        self.lexeme = lexeme


class JsonFloat:
    def __init__(self, lexeme: str) -> None:
        self.lexeme = lexeme


class NormalizationImpossible(Exception):
    """The source expression has no node or a NOT node has no child."""


def reject_non_finite_json_number(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def canonical_integer(value: JsonInteger) -> str:
    lexeme = value.lexeme
    assert INTEGER.fullmatch(lexeme), "unsupported JSON integer"
    integer = int(lexeme)
    assert abs(integer) <= 2**53 - 1, "unsupported JSON integer"
    return rfc8785.dumps(integer).decode("utf-8")


def canonical_float(value: JsonFloat) -> str:
    lexeme = value.lexeme
    number = float(lexeme)
    if not math.isfinite(number):
        raise ValueError(f"non-finite JSON number: {lexeme}")
    return rfc8785.dumps(number).decode("utf-8")


def canonical_int64_string(value: str, location: str) -> str:
    assert INT64_STRING.fullmatch(value), (
        f"{location}: int64Value must be a canonical decimal string"
    )
    parsed = int(value)
    assert INT64_MIN <= parsed <= INT64_MAX, (
        f"{location}: int64Value must be within signed int64 range"
    )
    return str(parsed)


def validate_json_lexemes(value: Any) -> None:
    if isinstance(value, JsonInteger):
        canonical_integer(value)
    elif isinstance(value, JsonFloat):
        canonical_float(value)
    elif isinstance(value, list):
        for item in value:
            validate_json_lexemes(item)
    elif isinstance(value, dict):
        for item in value.values():
            validate_json_lexemes(item)


def canonical_json_value(value: Any) -> Any:
    if isinstance(value, JsonInteger):
        canonical_integer(value)
        return int(value.lexeme)
    if isinstance(value, JsonFloat):
        canonical_float(value)
        return float(value.lexeme)
    if isinstance(value, str):
        return value
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        assert abs(value) <= 2**53 - 1, "unsupported JSON integer"
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite JSON number: {value}")
        return value
    if isinstance(value, list):
        return [canonical_json_value(item) for item in value]
    if isinstance(value, dict):
        assert all(isinstance(key, str) for key in value), (
            "canonical JSON object keys must be strings"
        )
        return {key: canonical_json_value(item) for key, item in value.items()}
    raise AssertionError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Serialize an I-JSON value with the complete RFC 8785 algorithm."""

    return rfc8785.dumps(canonical_json_value(value)).decode("utf-8")


def context_validation_error(context: dict[str, Any]) -> str | None:
    attributes = context.get("attributes", {})
    if not isinstance(attributes, dict):
        return "attributes must be an object"
    for key, attribute in attributes.items():
        if not isinstance(attribute, dict):
            return f"attribute {key!r} must be an object"
        provenance = attribute.get("provenance")
        if provenance not in VALID_PROVENANCE:
            return f"attribute {key!r} has invalid provenance"
    return None


def normalize_value(value: Any, location: str) -> dict[str, Any]:
    assert isinstance(value, dict), f"{location}: audience value must be an object"
    kinds = {"stringValue", "boolValue", "int64Value", "doubleValue"}
    selected = kinds & value.keys()
    assert len(selected) == 1 and set(value) == selected, (
        f"{location}: audience value must select exactly one typed field"
    )
    kind = next(iter(selected))
    scalar = value[kind]
    if kind == "stringValue":
        assert isinstance(scalar, str), f"{location}: stringValue must be a string"
    elif kind == "boolValue":
        assert isinstance(scalar, bool), f"{location}: boolValue must be a boolean"
    elif kind == "int64Value":
        assert isinstance(scalar, str), f"{location}: int64Value must be a string"
        scalar = canonical_int64_string(scalar, location)
    else:
        assert isinstance(scalar, (JsonInteger, JsonFloat)), (
            f"{location}: doubleValue must be a JSON number"
        )
        canonical_json(scalar)
    return {kind: scalar}


def typed_value_sort_key(value: dict[str, Any]) -> tuple[int, Any]:
    kind, scalar = next(iter(value.items()))
    if kind == "stringValue":
        return 0, scalar.encode("utf-8")
    if kind == "boolValue":
        return 1, int(scalar)
    if kind == "int64Value":
        return 2, int(scalar)
    if isinstance(scalar, JsonInteger):
        return 3, float(canonical_integer(scalar))
    return 3, float(canonical_float(scalar))


def normalize_expression(
    expression: Any, location: str = "expression"
) -> dict[str, Any]:
    assert isinstance(expression, dict), f"{location}: expression must be an object"
    nodes = {"predicate", "all", "any", "not"}
    selected = nodes & expression.keys()
    if not selected and not expression:
        raise NormalizationImpossible(f"{location}: expression node is missing")
    assert len(selected) == 1 and set(expression) == selected, (
        f"{location}: expression must select exactly one node"
    )
    node_name = next(iter(selected))
    node = expression[node_name]
    assert isinstance(node, dict), f"{location}.{node_name}: node must be an object"

    if node_name == "predicate":
        assert set(node) == {"attributeKey", "operator", "values"}, (
            f"{location}.predicate: invalid predicate fields"
        )
        attribute_key = node["attributeKey"]
        operator = node["operator"]
        values = node["values"]
        assert isinstance(attribute_key, str) and attribute_key, (
            f"{location}.predicate: attributeKey must be a non-empty string"
        )
        assert isinstance(operator, str) and operator in OPERATORS, (
            f"{location}.predicate: invalid operator"
        )
        assert isinstance(values, list), (
            f"{location}.predicate: values must be an array"
        )
        normalized_values = [
            normalize_value(value, f"{location}.predicate.values[{index}]")
            for index, value in enumerate(values)
        ]
        if operator in {"AUDIENCE_OPERATOR_IN", "AUDIENCE_OPERATOR_NOT_IN"}:
            unique = {
                canonical_json(value): value for value in normalized_values
            }
            normalized_values = sorted(unique.values(), key=typed_value_sort_key)
        return {
            "predicate": {
                "attributeKey": attribute_key,
                "operator": operator,
                "values": normalized_values,
            }
        }

    if node_name in {"all", "any"}:
        assert set(node) == {"expressions"}, (
            f"{location}.{node_name}: invalid logical-node fields"
        )
        children = node["expressions"]
        assert isinstance(children, list), (
            f"{location}.{node_name}: expressions must be an array"
        )
        normalized_children = [
            normalize_expression(child, f"{location}.{node_name}[{index}]")
            for index, child in enumerate(children)
        ]
        normalized_children.sort(
            key=lambda child: hashlib.sha256(
                canonical_json(child).encode("utf-8")
            ).digest()
        )
        return {node_name: {"expressions": normalized_children}}

    if not node:
        raise NormalizationImpossible(f"{location}.not: child expression is missing")
    assert set(node) == {"expression"}, f"{location}.not: invalid NOT fields"
    return {
        "not": {
            "expression": normalize_expression(
                node["expression"], f"{location}.not"
            )
        }
    }


def validate(
    path: Path,
    seen: set[str],
    registry_contents: dict[str, tuple[str, str]],
    equivalence_groups: dict[str, list[tuple[str, str, str]]],
) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    for line_number, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        location = f"{path}:{line_number}"
        case = json.loads(
            raw,
            parse_int=JsonInteger,
            parse_float=JsonFloat,
            parse_constant=reject_non_finite_json_number,
            object_pairs_hook=reject_duplicate_object_keys,
        )
        validate_json_lexemes(case)
        assert isinstance(case, dict), f"{location}: expected a JSON object"
        missing = REQUIRED - case.keys()
        assert not missing, f"{location}: missing {sorted(missing)}"

        case_id = case["caseId"]
        assert isinstance(case_id, str) and case_id, (
            f"{location}: caseId must be a non-empty string"
        )
        assert case_id not in seen, f"{location}: duplicate {case_id}"
        seen.add(case_id)

        registry_version = case["registryVersion"]
        assert isinstance(registry_version, str) and registry_version, (
            f"{location}: registryVersion must be a non-empty string"
        )
        assert isinstance(case["rule"], dict), f"{location}: rule must be an object"
        rule_fingerprint = case["rule"].get("contentFingerprint")
        assert (
            isinstance(rule_fingerprint, str)
            and FINGERPRINT.fullmatch(rule_fingerprint)
        ), f"{location}: invalid rule contentFingerprint"
        assert isinstance(case["context"], dict), (
            f"{location}: context must be an object"
        )
        context_error = context_validation_error(case["context"])
        if path.name == "valid.jsonl":
            assert context_error is None, f"{location}: {context_error}"
        registry = case.get("registry")
        if registry is None:
            assert registry_version == PRODUCTION_REGISTRY_VERSION, (
                f"{location}: missing embedded registry for {registry_version}"
            )
        else:
            assert isinstance(registry, dict), (
                f"{location}: registry must be an object"
            )
            assert registry.get("version") == registry_version, (
                f"{location}: registry version mismatch"
            )
            assert registry_version != PRODUCTION_REGISTRY_VERSION, (
                f"{location}: production registry must not be embedded"
            )
            canonical_registry = canonical_json(registry)
            existing = registry_contents.get(registry_version)
            if existing is None:
                registry_contents[registry_version] = (canonical_registry, location)
            else:
                assert existing[0] == canonical_registry, (
                    f"{location}: registry content mismatch for {registry_version}; "
                    f"first declared at {existing[1]}"
                )

        expected_decision = case["expectedDecision"]
        assert isinstance(expected_decision, str) and expected_decision in DECISIONS, (
            f"{location}: invalid expectedDecision"
        )
        expected_reasons = case["expectedReasonCodes"]
        assert isinstance(expected_reasons, list), (
            f"{location}: expectedReasonCodes must be an array"
        )
        assert all(
            isinstance(reason, str) and reason in REASON_CODES
            for reason in expected_reasons
        ), f"{location}: invalid expectedReasonCodes"
        assert len(expected_reasons) == len(set(expected_reasons)), (
            f"{location}: duplicate expectedReasonCodes"
        )

        if path.name == "invalid.jsonl":
            validation_reason = case.get("expectedValidationReasonCode")
            assert (
                isinstance(validation_reason, str)
                and validation_reason in REASON_CODES
            ), f"{location}: invalid expectedValidationReasonCode"
            assert expected_reasons, (
                f"{location}: invalid cases require expectedReasonCodes"
            )
            assert validation_reason in expected_reasons, (
                f"{location}: validation reason missing from expectedReasonCodes"
            )
            if context_error is None:
                assert validation_reason != (
                    "AUDIENCE_EVALUATION_REASON_CODE_INVALID_CONTEXT"
                ), f"{location}: INVALID_CONTEXT requires an invalid context"
            else:
                assert validation_reason == (
                    "AUDIENCE_EVALUATION_REASON_CODE_INVALID_CONTEXT"
                ), f"{location}: {context_error}"

        normalized_present = "expectedNormalizedExpression" in case
        fingerprint_present = "expectedFingerprint" in case
        assert normalized_present == fingerprint_present, (
            f"{location}: expectedNormalizedExpression requires expectedFingerprint"
        )
        try:
            derived_normalized = normalize_expression(
                case["rule"].get("expression"), f"{location}: rule.expression"
            )
        except NormalizationImpossible:
            derived_normalized = None
        assert normalized_present == (derived_normalized is not None), (
            f"{location}: expectedNormalizedExpression requires expectedFingerprint "
            "for every normalizable rule"
        )
        if path.name == "valid.jsonl":
            assert normalized_present, (
                f"{location}: valid cases require normalized expression and fingerprint"
            )
        if normalized_present:
            fingerprint = case["expectedFingerprint"]
            assert isinstance(fingerprint, str) and FINGERPRINT.fullmatch(fingerprint), (
                f"{location}: invalid fingerprint"
            )
            normalized_json = canonical_json(case["expectedNormalizedExpression"])
            derived_json = canonical_json(derived_normalized)
            assert normalized_json == derived_json, (
                f"{location}: normalized expression mismatch"
            )
            computed = hashlib.sha256(derived_json.encode("utf-8")).hexdigest()
            assert computed == fingerprint, f"{location}: fingerprint mismatch"
            assert rule_fingerprint == computed, (
                f"{location}: rule contentFingerprint mismatch"
            )

            equivalence_group = case.get("equivalenceGroup")
            if equivalence_group is not None:
                assert isinstance(equivalence_group, str) and equivalence_group, (
                    f"{location}: equivalenceGroup must be a non-empty string"
                )
                equivalence_groups.setdefault(equivalence_group, []).append(
                    (normalized_json, fingerprint, location)
                )
        else:
            assert "equivalenceGroup" not in case, (
                f"{location}: equivalenceGroup requires normalized expression"
            )


def validate_equivalence_groups(
    equivalence_groups: dict[str, list[tuple[str, str, str]]],
) -> None:
    for group, declarations in equivalence_groups.items():
        assert len(declarations) >= 2, (
            f"equivalence group {group}: expected at least two declarations"
        )
        normalized_json, fingerprint, first_location = declarations[0]
        for candidate_json, candidate_fingerprint, location in declarations[1:]:
            assert (
                candidate_json == normalized_json
                and candidate_fingerprint == fingerprint
            ), (
                f"{location}: equivalence group mismatch for {group}; "
                f"first declared at {first_location}"
            )


def main() -> None:
    assert FIXTURE_DIRECTORY.is_dir(), (
        f"missing fixture directory: {FIXTURE_DIRECTORY}"
    )
    fixtures = [
        FIXTURE_DIRECTORY / "valid.jsonl",
        FIXTURE_DIRECTORY / "invalid.jsonl",
    ]
    for fixture in fixtures:
        assert fixture.is_file(), f"missing fixture: {fixture}"

    seen: set[str] = set()
    registry_contents: dict[str, tuple[str, str]] = {}
    equivalence_groups: dict[str, list[tuple[str, str, str]]] = {}
    for fixture in fixtures:
        validate(fixture, seen, registry_contents, equivalence_groups)
    validate_equivalence_groups(equivalence_groups)


if __name__ == "__main__":
    main()
