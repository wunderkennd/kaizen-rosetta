#!/usr/bin/env python3
"""Contract tests for fail-closed Rust compatibility evidence validation."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.validate_consumer_compatibility import validate_document


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts/validate_consumer_compatibility.py"
BSR_MODULE_COMMIT = "045c39860c9c40178a3a1ed3088c218f"
DESCRIPTOR_SHA256 = (
    "077c2d8d31c41bcdac5bc97ed1e6407dfdae95a80e0d86712c960b997dc254fa"
)
GIT_COMMIT = "b" * 40
CHECKS = [
    "all-generated-packages",
    "audience-binary",
    "audience-protojson",
    "server-streaming-interface",
    "unary-interface",
]
CRATE_VERSIONS = {
    "buffa": "0.7.1",
    "buffa-types": "0.7.1",
    "connectrpc": "0.7.0",
    "connectrpc-build": "0.7.0",
}


class ConsumerCompatibilityValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.cargo_lock = Path(self.temporary_directory.name) / "Cargo.lock"
        self.cargo_lock.write_bytes(b"locked dependency graph\n")

    def valid_document(self) -> dict[str, object]:
        return {
            "records": [
                {
                    "adapter": "connect-rust",
                    "bsrModule": "buf.build/kaizen/rosetta",
                    "bsrModuleCommit": BSR_MODULE_COMMIT,
                    "canary": "rust-contracts-v1",
                    "cargoLockSha256": hashlib.sha256(
                        self.cargo_lock.read_bytes()
                    ).hexdigest(),
                    "cargoVersion": "1.88.0",
                    "checks": list(CHECKS),
                    "crateVersions": dict(CRATE_VERSIONS),
                    "descriptorSha256": DESCRIPTOR_SHA256,
                    "generationMode": "cargo-build-rs-bsr-export",
                    "gitCommit": GIT_COMMIT,
                    "rustVersion": "1.88.0",
                    "schema": "rosetta.consumer-compatibility.rust.v1",
                    "status": "passed",
                }
            ],
            "schema": "rosetta.consumer-compatibility.v1",
        }

    def validate(self, document: dict[str, object]) -> dict[str, object]:
        return validate_document(
            document,
            bsr_module_commit=BSR_MODULE_COMMIT,
            descriptor_sha256=DESCRIPTOR_SHA256,
            git_commit=GIT_COMMIT,
            cargo_lock_path=self.cargo_lock,
        )

    def run_cli(self, evidence_path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--evidence",
                str(evidence_path),
                "--bsr-module-commit",
                BSR_MODULE_COMMIT,
                "--descriptor-sha256",
                DESCRIPTOR_SHA256,
                "--git-commit",
                GIT_COMMIT,
                "--cargo-lock",
                str(self.cargo_lock),
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def write_evidence(self, value: object) -> Path:
        evidence_path = Path(self.temporary_directory.name) / "evidence.json"
        evidence_path.write_text(json.dumps(value), encoding="utf-8")
        return evidence_path

    def test_returns_a_detached_normalized_rust_record(self) -> None:
        document = self.valid_document()

        normalized = self.validate(document)

        expected = copy.deepcopy(document["records"][0])  # type: ignore[index]
        self.assertEqual(normalized, expected)
        self.assertIsNot(normalized, document["records"][0])  # type: ignore[index]
        self.assertIsNot(normalized["checks"], expected["checks"])
        self.assertIsNot(normalized["crateVersions"], expected["crateVersions"])
        for identity in ("bsrModuleCommit", "descriptorSha256", "gitCommit"):
            self.assertIs(type(normalized[identity]), str)
        document["records"][0]["checks"].append("late-mutation")  # type: ignore[index,union-attr]
        self.assertEqual(normalized["checks"], CHECKS)

    def test_rejects_non_string_or_malformed_caller_bindings_even_when_evidence_matches(
        self,
    ) -> None:
        cases = {
            "BSR non-string": (
                "bsrModuleCommit",
                123,
                "bsr_module_commit",
                "expected BSR commit must be 32 lowercase hexadecimal characters",
            ),
            "BSR malformed": (
                "bsrModuleCommit",
                "A" * 32,
                "bsr_module_commit",
                "expected BSR commit must be 32 lowercase hexadecimal characters",
            ),
            "descriptor non-string": (
                "descriptorSha256",
                True,
                "descriptor_sha256",
                "expected descriptor SHA-256 must be 64 lowercase hexadecimal characters",
            ),
            "descriptor malformed": (
                "descriptorSha256",
                "A" * 64,
                "descriptor_sha256",
                "expected descriptor SHA-256 must be 64 lowercase hexadecimal characters",
            ),
            "Git non-string": (
                "gitCommit",
                [GIT_COMMIT],
                "git_commit",
                "expected Git commit must be 40 or 64 lowercase hexadecimal characters",
            ),
            "Git malformed": (
                "gitCommit",
                "g" * 40,
                "git_commit",
                "expected Git commit must be 40 or 64 lowercase hexadecimal characters",
            ),
        }

        for name, (field, value, binding, error) in cases.items():
            with self.subTest(name=name):
                document = self.valid_document()
                document["records"][0][field] = value  # type: ignore[index]
                arguments: dict[str, object] = {
                    "bsr_module_commit": BSR_MODULE_COMMIT,
                    "descriptor_sha256": DESCRIPTOR_SHA256,
                    "git_commit": GIT_COMMIT,
                }
                arguments[binding] = value
                with self.assertRaisesRegex(ValueError, error):
                    validate_document(
                        document,
                        cargo_lock_path=self.cargo_lock,
                        **arguments,  # type: ignore[arg-type]
                    )

    def test_rejects_non_string_or_malformed_evidence_identities_before_equality(
        self,
    ) -> None:
        cases = {
            "BSR non-string": (
                "bsrModuleCommit",
                123,
                "BSR commit must be 32 lowercase hexadecimal characters",
            ),
            "BSR malformed": (
                "bsrModuleCommit",
                "A" * 32,
                "BSR commit must be 32 lowercase hexadecimal characters",
            ),
            "descriptor non-string": (
                "descriptorSha256",
                True,
                "descriptor SHA-256 must be 64 lowercase hexadecimal characters",
            ),
            "descriptor malformed": (
                "descriptorSha256",
                "A" * 64,
                "descriptor SHA-256 must be 64 lowercase hexadecimal characters",
            ),
            "Git non-string": (
                "gitCommit",
                [GIT_COMMIT],
                "Git commit must be 40 or 64 lowercase hexadecimal characters",
            ),
            "Git malformed": (
                "gitCommit",
                "g" * 40,
                "Git commit must be 40 or 64 lowercase hexadecimal characters",
            ),
            "lock digest non-string": (
                "cargoLockSha256",
                False,
                "Cargo.lock digest must be 64 lowercase hexadecimal characters",
            ),
            "lock digest malformed": (
                "cargoLockSha256",
                "A" * 64,
                "Cargo.lock digest must be 64 lowercase hexadecimal characters",
            ),
        }

        for name, (field, value, error) in cases.items():
            with self.subTest(name=name):
                document = self.valid_document()
                document["records"][0][field] = value  # type: ignore[index]
                with self.assertRaisesRegex(ValueError, error):
                    self.validate(document)

    def test_rejects_non_path_cargo_lock_binding(self) -> None:
        with self.assertRaisesRegex(ValueError, "Cargo.lock path must be a Path"):
            validate_document(
                self.valid_document(),
                bsr_module_commit=BSR_MODULE_COMMIT,
                descriptor_sha256=DESCRIPTOR_SHA256,
                git_commit=GIT_COMMIT,
                cargo_lock_path=str(self.cargo_lock),  # type: ignore[arg-type]
            )

    def test_accepts_sha1_and_sha256_git_object_ids(self) -> None:
        for length in (40, 64):
            with self.subTest(length=length):
                git_commit = "b" * length
                document = self.valid_document()
                document["records"][0]["gitCommit"] = git_commit  # type: ignore[index]

                normalized = validate_document(
                    document,
                    bsr_module_commit=BSR_MODULE_COMMIT,
                    descriptor_sha256=DESCRIPTOR_SHA256,
                    git_commit=git_commit,
                    cargo_lock_path=self.cargo_lock,
                )

                self.assertEqual(normalized["gitCommit"], git_commit)

    def test_rejects_other_git_object_id_lengths_and_nonhex_values(self) -> None:
        for name, git_commit in {
            "39 characters": "b" * 39,
            "41 characters": "b" * 41,
            "63 characters": "b" * 63,
            "65 characters": "b" * 65,
            "nonhex SHA-1": "g" * 40,
            "nonhex SHA-256": "g" * 64,
        }.items():
            with self.subTest(name=name):
                document = self.valid_document()
                document["records"][0]["gitCommit"] = git_commit  # type: ignore[index]

                with self.assertRaisesRegex(
                    ValueError,
                    "Git commit must be 40 or 64 lowercase hexadecimal characters",
                ):
                    validate_document(
                        document,
                        bsr_module_commit=BSR_MODULE_COMMIT,
                        descriptor_sha256=DESCRIPTOR_SHA256,
                        git_commit=git_commit,
                        cargo_lock_path=self.cargo_lock,
                    )

    def test_cli_emits_only_deterministic_normalized_record_json(self) -> None:
        document = self.valid_document()

        result = self.run_cli(self.write_evidence(document))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            result.stdout,
            json.dumps(document["records"][0], indent=2, sort_keys=True) + "\n",  # type: ignore[index]
        )

    def test_cli_rejects_malformed_json_without_a_traceback(self) -> None:
        evidence_path = Path(self.temporary_directory.name) / "evidence.json"
        evidence_path.write_text("{not-json\n", encoding="utf-8")

        result = self.run_cli(evidence_path)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "invalid consumer compatibility JSON\n")

    def test_cli_rejects_recursive_json_without_a_traceback(self) -> None:
        evidence_path = Path(self.temporary_directory.name) / "evidence.json"
        evidence_path.write_text("[" * 2_000 + "0" + "]" * 2_000, encoding="utf-8")

        result = self.run_cli(evidence_path)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "invalid consumer compatibility JSON\n")

    def test_cli_rejects_mismatched_evidence_without_a_traceback(self) -> None:
        document = self.valid_document()
        document["records"][0]["bsrModuleCommit"] = "f" * 32  # type: ignore[index]

        result = self.run_cli(self.write_evidence(document))

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "BSR commit mismatch\n")

    def test_rejects_required_single_field_mutations(self) -> None:
        cases = {
            "missing": (
                lambda document: document["records"][0].pop("rustVersion"),
                "fields mismatch",
            ),
            "stale BSR commit": (
                lambda document: document["records"][0].__setitem__(
                    "bsrModuleCommit", "f" * 32
                ),
                "BSR commit mismatch",
            ),
            "descriptor mismatch": (
                lambda document: document["records"][0].__setitem__(
                    "descriptorSha256", "f" * 64
                ),
                "descriptor mismatch",
            ),
            "Git mismatch": (
                lambda document: document["records"][0].__setitem__(
                    "gitCommit", "f" * 40
                ),
                "Git commit mismatch",
            ),
            "lock mismatch": (
                lambda document: document["records"][0].__setitem__(
                    "cargoLockSha256", "f" * 64
                ),
                "Cargo.lock digest mismatch",
            ),
            "failed": (
                lambda document: document["records"][0].__setitem__(
                    "status", "failed"
                ),
                "status must be passed",
            ),
            "wrong canary": (
                lambda document: document["records"][0].__setitem__(
                    "canary", "another-script"
                ),
                "canary mismatch",
            ),
            "wrong generation mode": (
                lambda document: document["records"][0].__setitem__(
                    "generationMode", "bsr-generated-sdk"
                ),
                "generation mode mismatch",
            ),
            "crate drift": (
                lambda document: document["records"][0]["crateVersions"].__setitem__(
                    "connectrpc", "0.8.1"
                ),
                "crate version mismatch",
            ),
            "duplicate": (
                lambda document: document["records"].append(document["records"][0]),
                "duplicate Rust evidence",
            ),
        }

        for name, (mutate, error) in cases.items():
            with self.subTest(name=name):
                document = self.valid_document()
                mutate(document)
                with self.assertRaisesRegex(ValueError, error):
                    self.validate(document)

    def test_rejects_unknown_and_missing_document_fields_first(self) -> None:
        for name, mutate in {
            "missing": lambda document: document.pop("schema"),
            "unknown": lambda document: document.__setitem__("extra", True),
        }.items():
            with self.subTest(name=name):
                document = self.valid_document()
                mutate(document)
                with self.assertRaisesRegex(ValueError, "document fields mismatch"):
                    self.validate(document)

    def test_rejects_unknown_record_field_before_values(self) -> None:
        document = self.valid_document()
        record = document["records"][0]  # type: ignore[index]
        record["extra"] = True
        record["status"] = "failed"

        with self.assertRaisesRegex(ValueError, "fields mismatch"):
            self.validate(document)

    def test_rejects_invalid_outer_document_values_and_shapes(self) -> None:
        cases = {
            "schema": (
                lambda document: document.__setitem__("schema", "v2"),
                "document schema mismatch",
            ),
            "records type": (
                lambda document: document.__setitem__("records", {}),
                "records must be a list",
            ),
            "missing record": (
                lambda document: document.__setitem__("records", []),
                "exactly one Rust evidence record required",
            ),
            "multiple distinct": (
                lambda document: document["records"].append(
                    {"schema": "another-consumer"}
                ),
                "exactly one Rust evidence record required",
            ),
            "record type": (
                lambda document: document.__setitem__("records", ["rust"]),
                "Rust evidence must be an object",
            ),
        }

        for name, (mutate, error) in cases.items():
            with self.subTest(name=name):
                document = self.valid_document()
                mutate(document)
                with self.assertRaisesRegex(ValueError, error):
                    self.validate(document)

    def test_rejects_drift_in_exact_record_constants(self) -> None:
        cases = {
            "record schema": ("schema", "v2", "record schema mismatch"),
            "adapter": ("adapter", "grpc-rust", "adapter mismatch"),
            "BSR module": ("bsrModule", "example.invalid/module", "BSR module mismatch"),
            "Rust version": ("rustVersion", "1.89.0", "Rust version mismatch"),
            "Cargo version": ("cargoVersion", "1.89.0", "Cargo version mismatch"),
        }

        for name, (field, value, error) in cases.items():
            with self.subTest(name=name):
                document = self.valid_document()
                document["records"][0][field] = value  # type: ignore[index]
                with self.assertRaisesRegex(ValueError, error):
                    self.validate(document)

    def test_rejects_any_check_list_drift(self) -> None:
        for name, checks in {
            "missing": CHECKS[:-1],
            "unknown": [*CHECKS, "unknown-check"],
            "reordered": list(reversed(CHECKS)),
            "duplicate": [*CHECKS[:-1], CHECKS[-2]],
            "wrong type": tuple(CHECKS),
        }.items():
            with self.subTest(name=name):
                document = self.valid_document()
                document["records"][0]["checks"] = checks  # type: ignore[index]
                with self.assertRaisesRegex(ValueError, "checks mismatch"):
                    self.validate(document)

    def test_rejects_any_crate_map_drift(self) -> None:
        for name, crate_versions in {
            "missing": {key: value for key, value in CRATE_VERSIONS.items() if key != "buffa"},
            "unknown": {**CRATE_VERSIONS, "other": "1.0.0"},
            "wrong type": list(CRATE_VERSIONS.items()),
        }.items():
            with self.subTest(name=name):
                document = self.valid_document()
                document["records"][0]["crateVersions"] = crate_versions  # type: ignore[index]
                with self.assertRaisesRegex(ValueError, "crate version mismatch"):
                    self.validate(document)

    def test_complete_repository_example_validates(self) -> None:
        example_path = ROOT / "tools/release/consumer-compatibility-rust.example.json"
        example = json.loads(example_path.read_text(encoding="utf-8"))
        record = example["records"][0]

        normalized = validate_document(
            example,
            bsr_module_commit=BSR_MODULE_COMMIT,
            descriptor_sha256=DESCRIPTOR_SHA256,
            git_commit=record["gitCommit"],
            cargo_lock_path=ROOT / "tools/compatibility/rust/Cargo.lock",
        )

        self.assertEqual(normalized, record)

    def test_readme_explains_production_slot_replacement(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "Production automation replaces the example Git commit and Cargo.lock hash "
            "slots with values from the successful canary output.",
            " ".join(readme.split()),
        )


if __name__ == "__main__":
    unittest.main()
