from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from google.protobuf.json_format import ParseError


CHECKER_PATH = Path(__file__).with_name("check_fixture_shape.py")
NORMALIZED_EQUALS = {
    "predicate": {
        "attributeKey": "country_code",
        "operator": "AUDIENCE_OPERATOR_EQUALS",
        "values": [{"stringValue": "US"}],
    }
}


def canonical_fingerprint(value: Any) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_checker():
    spec = importlib.util.spec_from_file_location("check_fixture_shape", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_case(case_id: str = "valid-case") -> dict[str, Any]:
    fingerprint = canonical_fingerprint(NORMALIZED_EQUALS)
    return {
        "caseId": case_id,
        "registryVersion": "2026-07-12",
        "rule": {
            "expression": NORMALIZED_EQUALS,
            "contentFingerprint": fingerprint,
        },
        "context": {},
        "expectedDecision": "AUDIENCE_EVALUATION_DECISION_MATCH",
        "expectedReasonCodes": [],
        "expectedNormalizedExpression": NORMALIZED_EQUALS,
        "expectedFingerprint": fingerprint,
    }


def invalid_case(case_id: str = "invalid-case") -> dict[str, Any]:
    case = valid_case(case_id)
    case.update(
        {
            "expectedDecision": "AUDIENCE_EVALUATION_DECISION_INVALID",
            "expectedReasonCodes": [
                "AUDIENCE_EVALUATION_REASON_CODE_INVALID_ARITY"
            ],
            "expectedValidationReasonCode": (
                "AUDIENCE_EVALUATION_REASON_CODE_INVALID_ARITY"
            ),
        }
    )
    return case


def int64_case(
    case_id: str,
    operator: str,
    source_values: list[str],
    normalized_values: list[str],
) -> dict[str, Any]:
    source = {
        "predicate": {
            "attributeKey": "account_age_days",
            "operator": operator,
            "values": [{"int64Value": value} for value in source_values],
        }
    }
    normalized = {
        "predicate": {
            "attributeKey": "account_age_days",
            "operator": operator,
            "values": [{"int64Value": value} for value in normalized_values],
        }
    }
    fingerprint = canonical_fingerprint(normalized)
    case = valid_case(case_id)
    case["rule"] = {
        "expression": source,
        "contentFingerprint": fingerprint,
    }
    case["expectedNormalizedExpression"] = normalized
    case["expectedFingerprint"] = fingerprint
    return case


class FixtureShapeTest(unittest.TestCase):
    def test_checker_exposes_portable_wire_vector_builder(self) -> None:
        checker = load_checker()
        self.assertTrue(callable(getattr(checker, "build_expected_wire", None)))

    def run_checker(
        self,
        valid: list[dict[str, Any]] | None = None,
        invalid: list[dict[str, Any]] | None = None,
        *,
        create_valid: bool = True,
        create_invalid: bool = True,
        populate_wire: bool = True,
    ) -> None:
        checker = load_checker()
        valid_cases = valid if valid is not None else [valid_case()]
        invalid_cases = invalid if invalid is not None else [invalid_case()]
        if populate_wire:
            for case in [*valid_cases, *invalid_cases]:
                if "expectedWire" in case or not {"rule", "context"} <= case.keys():
                    continue
                try:
                    case["expectedWire"] = checker.build_expected_wire(
                        case["rule"], case["context"]
                    )
                except ParseError:
                    case["expectedWire"] = {}
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory) / "conformance/audience/v1"
            directory.mkdir(parents=True)
            if create_valid:
                self.write_fixture(directory / "valid.jsonl", valid_cases)
            if create_invalid:
                self.write_fixture(
                    directory / "invalid.jsonl", invalid_cases
                )
            checker.FIXTURE_DIRECTORY = directory
            checker.main()

    def run_checker_raw(self, valid_raw: str) -> None:
        checker = load_checker()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory) / "conformance/audience/v1"
            directory.mkdir(parents=True)
            (directory / "valid.jsonl").write_text(valid_raw + "\n", encoding="utf-8")
            self.write_fixture(directory / "invalid.jsonl", [invalid_case()])
            checker.FIXTURE_DIRECTORY = directory
            checker.main()

    @staticmethod
    def with_raw_member(case: dict[str, Any], member: str) -> str:
        raw = json.dumps(case, ensure_ascii=False)
        assert raw.endswith("}")
        return raw[:-1] + "," + member + "}"

    @staticmethod
    def write_fixture(path: Path, cases: list[dict[str, Any]]) -> None:
        path.write_text(
            "".join(
                json.dumps(case, ensure_ascii=False, allow_nan=True) + "\n"
                for case in cases
            ),
            encoding="utf-8",
        )

    def test_rejects_bogus_well_formed_fingerprint(self) -> None:
        case = valid_case()
        case["expectedFingerprint"] = "a" * 64
        with self.assertRaisesRegex(AssertionError, "fingerprint mismatch"):
            self.run_checker(valid=[case])

    def test_rejects_malformed_fingerprint(self) -> None:
        case = valid_case()
        case["expectedFingerprint"] = "ABC"
        with self.assertRaisesRegex(AssertionError, "invalid fingerprint"):
            self.run_checker(valid=[case])

    def test_rejects_missing_envelope_field(self) -> None:
        case = valid_case()
        del case["context"]
        with self.assertRaisesRegex(AssertionError, "missing.*context"):
            self.run_checker(valid=[case])

    def test_rejects_missing_portable_wire_vectors(self) -> None:
        case = valid_case()
        with self.assertRaisesRegex(AssertionError, "missing.*expectedWire"):
            self.run_checker(valid=[case], populate_wire=False)

    def test_rejects_corrupted_binary_wire_vector(self) -> None:
        checker = load_checker()
        case = valid_case()
        case["expectedWire"] = checker.build_expected_wire(
            case["rule"], case["context"]
        )
        case["expectedWire"]["rule"]["binaryHex"] += "00"
        with self.assertRaisesRegex(AssertionError, "rule binary Protobuf mismatch"):
            self.run_checker(valid=[case])

    def test_rejects_corrupted_canonical_protojson_vector(self) -> None:
        checker = load_checker()
        case = valid_case()
        case["expectedWire"] = checker.build_expected_wire(
            case["rule"], case["context"]
        )
        case["expectedWire"]["context"]["canonicalProtoJson"] = (
            '{"registryVersion":"stale"}'
        )
        with self.assertRaisesRegex(AssertionError, "context canonical ProtoJSON mismatch"):
            self.run_checker(valid=[case])

    def test_rejects_non_hex_binary_wire_vector(self) -> None:
        checker = load_checker()
        case = valid_case()
        case["expectedWire"] = checker.build_expected_wire(
            case["rule"], case["context"]
        )
        case["expectedWire"]["context"]["binaryHex"] = "not-hex"
        with self.assertRaisesRegex(AssertionError, "context binaryHex"):
            self.run_checker(valid=[case])

    def test_rejects_cross_file_duplicate_case_id(self) -> None:
        with self.assertRaisesRegex(AssertionError, "duplicate duplicate-case"):
            self.run_checker(
                valid=[valid_case("duplicate-case")],
                invalid=[invalid_case("duplicate-case")],
            )

    def test_rejects_registry_version_mismatch(self) -> None:
        case = valid_case()
        case["registryVersion"] = "synthetic-v1"
        case["registry"] = {"version": "different", "definitions": []}
        with self.assertRaisesRegex(AssertionError, "registry version mismatch"):
            self.run_checker(valid=[case])

    def test_requires_fingerprint_for_normalized_invalid_case(self) -> None:
        case = invalid_case()
        del case["expectedFingerprint"]
        with self.assertRaisesRegex(
            AssertionError, "expectedNormalizedExpression requires expectedFingerprint"
        ):
            self.run_checker(invalid=[case])

    def test_rejects_unknown_decision(self) -> None:
        malformed = [None, 7, "", "MATCH"]
        for index, decision in enumerate(malformed):
            with self.subTest(decision=decision):
                case = valid_case(f"malformed-decision-{index}")
                case["expectedDecision"] = decision
                with self.assertRaisesRegex(AssertionError, "invalid expectedDecision"):
                    self.run_checker(valid=[case])

    def test_rejects_malformed_reason_codes(self) -> None:
        malformed = [None, 7, "", "UNKNOWN_REASON"]
        for index, reason in enumerate(malformed):
            with self.subTest(reason=reason):
                case = valid_case(f"malformed-reason-{index}")
                case["expectedReasonCodes"] = [reason]
                with self.assertRaisesRegex(AssertionError, "invalid expectedReasonCodes"):
                    self.run_checker(valid=[case])

    def test_rejects_duplicate_reason_codes(self) -> None:
        case = invalid_case()
        reason = "AUDIENCE_EVALUATION_REASON_CODE_INVALID_ARITY"
        case["expectedReasonCodes"] = [reason, reason]
        with self.assertRaisesRegex(AssertionError, "duplicate expectedReasonCodes"):
            self.run_checker(invalid=[case])

    def test_rejects_malformed_validation_reason(self) -> None:
        malformed = [None, 7, "", "UNKNOWN_REASON"]
        for index, reason in enumerate(malformed):
            with self.subTest(reason=reason):
                case = invalid_case(f"malformed-validation-reason-{index}")
                case["expectedValidationReasonCode"] = reason
                with self.assertRaisesRegex(
                    AssertionError, "invalid expectedValidationReasonCode"
                ):
                    self.run_checker(invalid=[case])

    def test_rejects_same_registry_version_with_different_content(self) -> None:
        first = valid_case("registry-content-a")
        second = invalid_case("registry-content-b")
        first["registryVersion"] = second["registryVersion"] = "synthetic-v1"
        first["registry"] = {"version": "synthetic-v1", "definitions": []}
        second["registry"] = {
            "version": "synthetic-v1",
            "definitions": [{"key": "different"}],
        }
        with self.assertRaisesRegex(AssertionError, "registry content mismatch"):
            self.run_checker(valid=[first], invalid=[second])

    def test_requires_both_fixture_files(self) -> None:
        with self.assertRaisesRegex(AssertionError, "missing fixture"):
            self.run_checker(create_invalid=False)

    def test_requires_fixture_directory(self) -> None:
        checker = load_checker()
        with tempfile.TemporaryDirectory() as temporary_directory:
            checker.FIXTURE_DIRECTORY = Path(temporary_directory) / "missing"
            with self.assertRaisesRegex(AssertionError, "missing fixture directory"):
                checker.main()

    def test_rejects_non_finite_normalized_number(self) -> None:
        case = valid_case()
        case["expectedNormalizedExpression"] = {"doubleValue": float("nan")}
        with self.assertRaisesRegex(ValueError, "non-finite JSON number"):
            self.run_checker(valid=[case])

    def test_accepts_value_equivalent_exponent_forms(self) -> None:
        checker = load_checker()
        self.assertEqual(
            checker.canonical_json(checker.JsonFloat("1e0")),
            checker.canonical_json(checker.JsonFloat("1.0")),
        )
        self.assertEqual(checker.canonical_json(checker.JsonFloat("1e0")), "1")

    def test_canonicalizes_json_integer_negative_zero(self) -> None:
        checker = load_checker()
        self.assertEqual(checker.canonical_json(checker.JsonInteger("-0")), "0")

    def test_canonicalizes_json_float_negative_zero(self) -> None:
        checker = load_checker()
        self.assertEqual(checker.canonical_json(checker.JsonFloat("-0.0")), "0")

    def test_accepts_rfc8785_official_style_numeric_vectors(self) -> None:
        checker = load_checker()
        vectors = {
            "333333333.33333329": "333333333.3333333",
            "1E30": "1e+30",
            "4.50": "4.5",
            "2e-3": "0.002",
            "0.000000000000000000000000001": "1e-27",
            "0.000001": "0.000001",
            "0.0000001": "1e-7",
            "5e-324": "5e-324",
            "1.7976931348623157e308": "1.7976931348623157e+308",
        }
        for source, expected in vectors.items():
            with self.subTest(source=source):
                self.assertEqual(
                    checker.canonical_json(checker.JsonFloat(source)),
                    expected,
                )

    def test_rfc8785_serializes_unicode_strings_and_keys(self) -> None:
        checker = load_checker()
        self.assertEqual(
            checker.canonical_json({"é": "café東京", "a": "€"}),
            '{"a":"€","é":"café東京"}',
        )

    def test_rejects_all_non_finite_json_number_spellings(self) -> None:
        for spelling in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(spelling=spelling):
                raw = self.with_raw_member(
                    valid_case(f"non-finite-{spelling}"),
                    f'"lexicalProbe":{spelling}',
                )
                with self.assertRaisesRegex(ValueError, "non-finite JSON number"):
                    self.run_checker_raw(raw)

    def test_rejects_duplicate_object_keys(self) -> None:
        raw = self.with_raw_member(valid_case(), '"caseId":"valid-case"')
        with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
            self.run_checker_raw(raw)

    def test_rejects_unsafe_integer_lexeme(self) -> None:
        raw = self.with_raw_member(valid_case(), '"lexicalProbe":9007199254740992')
        with self.assertRaisesRegex(AssertionError, "unsupported JSON integer"):
            self.run_checker_raw(raw)

    def test_rejects_unspecified_context_provenance(self) -> None:
        case = valid_case()
        case["context"] = {
            "attributes": {
                "country_code": {
                    "value": {"stringValue": "US"},
                    "provenance": "AUDIENCE_ATTRIBUTE_PROVENANCE_UNSPECIFIED",
                }
            },
            "registryVersion": "2026-07-12",
        }
        with self.assertRaisesRegex(AssertionError, "invalid provenance"):
            self.run_checker(valid=[case])

    def test_rejects_null_in_normalized_expression(self) -> None:
        case = valid_case()
        case["expectedNormalizedExpression"] = {"predicate": None}
        case["expectedFingerprint"] = "a" * 64
        with self.assertRaisesRegex(AssertionError, "normalized expression mismatch"):
            self.run_checker(valid=[case])

    def test_accepts_unicode_and_simple_double_vector(self) -> None:
        unicode_predicate = {
            "predicate": {
                "attributeKey": "label",
                "operator": "AUDIENCE_OPERATOR_EQUALS",
                "values": [{"stringValue": "café東京"}],
            }
        }
        double_predicate = {
            "predicate": {
                "attributeKey": "score",
                "operator": "AUDIENCE_OPERATOR_GREATER_THAN",
                "values": [{"doubleValue": 1.5}],
            }
        }
        children = [unicode_predicate, double_predicate]
        children.sort(
            key=lambda child: bytes.fromhex(canonical_fingerprint(child))
        )
        normalized = {"all": {"expressions": children}}
        fingerprint = canonical_fingerprint(normalized)
        case = valid_case("unicode-simple-double")
        case["rule"] = {
            "expression": {
                "all": {
                    "expressions": [double_predicate, unicode_predicate]
                }
            },
            "contentFingerprint": fingerprint,
        }
        case["expectedNormalizedExpression"] = normalized
        case["expectedFingerprint"] = fingerprint
        self.run_checker(valid=[case])

    def test_rejects_unrelated_normalized_expression(self) -> None:
        case = valid_case()
        case["expectedNormalizedExpression"] = {"unrelated": True}
        case["expectedFingerprint"] = canonical_fingerprint(
            case["expectedNormalizedExpression"]
        )
        with self.assertRaisesRegex(AssertionError, "normalized expression mismatch"):
            self.run_checker(valid=[case])

    def test_rejects_source_normalization_mismatch(self) -> None:
        source = {
            "predicate": {
                "attributeKey": "country_code",
                "operator": "AUDIENCE_OPERATOR_IN",
                "values": [
                    {"stringValue": "US"},
                    {"stringValue": "CA"},
                    {"stringValue": "US"},
                ],
            }
        }
        case = valid_case()
        case["rule"]["expression"] = source
        case["expectedNormalizedExpression"] = source
        fingerprint = canonical_fingerprint(source)
        case["expectedFingerprint"] = fingerprint
        case["rule"]["contentFingerprint"] = fingerprint
        with self.assertRaisesRegex(AssertionError, "normalized expression mismatch"):
            self.run_checker(valid=[case])

    def test_rejects_rule_content_fingerprint_mismatch(self) -> None:
        case = valid_case()
        case["rule"]["contentFingerprint"] = "b" * 64
        with self.assertRaisesRegex(AssertionError, "rule contentFingerprint mismatch"):
            self.run_checker(valid=[case])

    def test_accepts_signed_int64_boundaries(self) -> None:
        boundaries = [str(-(2**63)), str(2**63 - 1)]
        for index, boundary in enumerate(boundaries):
            with self.subTest(boundary=boundary):
                self.run_checker(
                    valid=[
                        int64_case(
                            f"int64-boundary-{index}",
                            "AUDIENCE_OPERATOR_EQUALS",
                            [boundary],
                            [boundary],
                        )
                    ]
                )

    def test_rejects_signed_int64_overflow_and_underflow(self) -> None:
        outside = [str(-(2**63) - 1), str(2**63)]
        for index, value in enumerate(outside):
            with self.subTest(value=value):
                case = int64_case(
                    f"int64-out-of-range-{index}",
                    "AUDIENCE_OPERATOR_EQUALS",
                    [value],
                    [value],
                )
                with self.assertRaisesRegex(AssertionError, "signed int64 range"):
                    self.run_checker(valid=[case])

    def test_canonicalizes_signed_int64_negative_zero(self) -> None:
        self.run_checker(
            valid=[
                int64_case(
                    "int64-negative-zero",
                    "AUDIENCE_OPERATOR_EQUALS",
                    ["-0"],
                    ["0"],
                )
            ]
        )

    def test_deduplicates_signed_int64_zero_membership_values(self) -> None:
        for operator in ("AUDIENCE_OPERATOR_IN", "AUDIENCE_OPERATOR_NOT_IN"):
            with self.subTest(operator=operator):
                self.run_checker(
                    valid=[
                        int64_case(
                            f"int64-zero-dedupe-{operator.lower()}",
                            operator,
                            ["-0", "0", "-0"],
                            ["0"],
                        )
                    ]
                )

    def test_rejects_malformed_impossible_rule_fingerprint(self) -> None:
        case = invalid_case("impossible-malformed-fingerprint")
        case["rule"] = {
            "expression": {},
            "contentFingerprint": "ABC",
        }
        del case["expectedNormalizedExpression"]
        del case["expectedFingerprint"]
        with self.assertRaisesRegex(AssertionError, "invalid rule contentFingerprint"):
            self.run_checker(invalid=[case])

    def test_rejects_mismatched_equivalence_group(self) -> None:
        first = valid_case("equivalent-a")
        second = valid_case("equivalent-b")
        first["equivalenceGroup"] = second["equivalenceGroup"] = "commutative-test"
        second["expectedNormalizedExpression"] = {
            "predicate": {
                "attributeKey": "platform",
                "operator": "AUDIENCE_OPERATOR_EQUALS",
                "values": [{"stringValue": "web"}],
            }
        }
        second["expectedFingerprint"] = canonical_fingerprint(
            second["expectedNormalizedExpression"]
        )
        second["rule"]["expression"] = second["expectedNormalizedExpression"]
        second["rule"]["contentFingerprint"] = second["expectedFingerprint"]
        with self.assertRaisesRegex(AssertionError, "equivalence group mismatch"):
            self.run_checker(valid=[first, second])

    def test_rejects_singleton_equivalence_group(self) -> None:
        case = valid_case()
        case["equivalenceGroup"] = "singleton"
        with self.assertRaisesRegex(AssertionError, "at least two declarations"):
            self.run_checker(valid=[case])


if __name__ == "__main__":
    unittest.main()
