#!/usr/bin/env python3
"""Fail-closed validation for Rust consumer-compatibility evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


DOCUMENT_FIELDS = {"records", "schema"}
RECORD_FIELDS = {
    "adapter",
    "bsrModule",
    "bsrModuleCommit",
    "canary",
    "cargoLockSha256",
    "cargoVersion",
    "checks",
    "crateVersions",
    "descriptorSha256",
    "generationMode",
    "gitCommit",
    "rustVersion",
    "schema",
    "status",
}
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


def _require_lowercase_hex(value: object, *, length: int, label: str) -> str:
    error = f"{label} must be {length} lowercase hexadecimal characters"
    if type(value) is not str:
        raise ValueError(error)
    if re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is None:
        raise ValueError(error)
    return value


def _require_git_object_id(value: object, *, label: str) -> str:
    error = f"{label} must be 40 or 64 lowercase hexadecimal characters"
    if type(value) is not str:
        raise ValueError(error)
    if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value) is None:
        raise ValueError(error)
    return value


def validate_document(
    document: dict[str, object],
    *,
    bsr_module_commit: str,
    descriptor_sha256: str,
    git_commit: str,
    cargo_lock_path: Path,
) -> dict[str, object]:
    """Require one unique Rust record and return its normalized value."""
    if not isinstance(document, dict):
        raise ValueError("consumer compatibility document must be an object")
    if set(document) != DOCUMENT_FIELDS:
        raise ValueError("document fields mismatch")
    if document["schema"] != "rosetta.consumer-compatibility.v1":
        raise ValueError("document schema mismatch")

    records = document["records"]
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    if any(
        records[left] == records[right]
        for left in range(len(records))
        for right in range(left + 1, len(records))
    ):
        raise ValueError("duplicate Rust evidence")
    if len(records) != 1:
        raise ValueError("exactly one Rust evidence record required")

    evidence = records[0]
    if not isinstance(evidence, dict):
        raise ValueError("Rust evidence must be an object")
    return validate_rust_evidence(
        evidence,
        bsr_module_commit=bsr_module_commit,
        descriptor_sha256=descriptor_sha256,
        git_commit=git_commit,
        cargo_lock_path=cargo_lock_path,
    )


def validate_rust_evidence(
    evidence: dict[str, object],
    *,
    bsr_module_commit: str,
    descriptor_sha256: str,
    git_commit: str,
    cargo_lock_path: Path,
) -> dict[str, object]:
    """Return a normalized passed record or raise ValueError fail-closed."""
    if not isinstance(evidence, dict):
        raise ValueError("Rust evidence must be an object")
    if set(evidence) != RECORD_FIELDS:
        raise ValueError("Rust evidence fields mismatch")

    normalized_bsr_module_commit = _require_lowercase_hex(
        bsr_module_commit,
        length=32,
        label="expected BSR commit",
    )
    normalized_descriptor_sha256 = _require_lowercase_hex(
        descriptor_sha256,
        length=64,
        label="expected descriptor SHA-256",
    )
    normalized_git_commit = _require_git_object_id(
        git_commit,
        label="expected Git commit",
    )
    if not isinstance(cargo_lock_path, Path):
        raise ValueError("Cargo.lock path must be a Path")

    evidence_bsr_module_commit = _require_lowercase_hex(
        evidence["bsrModuleCommit"],
        length=32,
        label="BSR commit",
    )
    evidence_descriptor_sha256 = _require_lowercase_hex(
        evidence["descriptorSha256"],
        length=64,
        label="descriptor SHA-256",
    )
    evidence_git_commit = _require_git_object_id(
        evidence["gitCommit"],
        label="Git commit",
    )
    evidence_cargo_lock_sha256 = _require_lowercase_hex(
        evidence["cargoLockSha256"],
        length=64,
        label="Cargo.lock digest",
    )

    if evidence["schema"] != "rosetta.consumer-compatibility.rust.v1":
        raise ValueError("record schema mismatch")
    if evidence["adapter"] != "connect-rust":
        raise ValueError("adapter mismatch")
    if evidence["bsrModule"] != "buf.build/kaizen/rosetta":
        raise ValueError("BSR module mismatch")
    if evidence_bsr_module_commit != normalized_bsr_module_commit:
        raise ValueError("BSR commit mismatch")
    if evidence["canary"] != "rust-contracts-v1":
        raise ValueError("canary mismatch")

    cargo_lock_sha256 = hashlib.sha256(cargo_lock_path.read_bytes()).hexdigest()
    if evidence_cargo_lock_sha256 != cargo_lock_sha256:
        raise ValueError("Cargo.lock digest mismatch")
    if evidence["cargoVersion"] != "1.88.0":
        raise ValueError("Cargo version mismatch")
    if not isinstance(evidence["checks"], list) or evidence["checks"] != CHECKS:
        raise ValueError("checks mismatch")
    if (
        not isinstance(evidence["crateVersions"], dict)
        or evidence["crateVersions"] != CRATE_VERSIONS
    ):
        raise ValueError("crate version mismatch")
    if evidence_descriptor_sha256 != normalized_descriptor_sha256:
        raise ValueError("descriptor mismatch")
    if evidence["generationMode"] != "cargo-build-rs-bsr-export":
        raise ValueError("generation mode mismatch")
    if evidence_git_commit != normalized_git_commit:
        raise ValueError("Git commit mismatch")
    if evidence["rustVersion"] != "1.88.0":
        raise ValueError("Rust version mismatch")
    if evidence["status"] != "passed":
        raise ValueError("status must be passed")

    return {
        "adapter": "connect-rust",
        "bsrModule": "buf.build/kaizen/rosetta",
        "bsrModuleCommit": normalized_bsr_module_commit,
        "canary": "rust-contracts-v1",
        "cargoLockSha256": cargo_lock_sha256,
        "cargoVersion": "1.88.0",
        "checks": list(CHECKS),
        "crateVersions": dict(CRATE_VERSIONS),
        "descriptorSha256": normalized_descriptor_sha256,
        "generationMode": "cargo-build-rs-bsr-export",
        "gitCommit": normalized_git_commit,
        "rustVersion": "1.88.0",
        "schema": "rosetta.consumer-compatibility.rust.v1",
        "status": "passed",
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--bsr-module-commit", required=True)
    parser.add_argument("--descriptor-sha256", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--cargo-lock", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        evidence_bytes = arguments.evidence.read_bytes()
    except OSError:
        print("consumer compatibility evidence file unreadable", file=sys.stderr)
        return 1

    try:
        document = json.loads(evidence_bytes)
    except (ValueError, RecursionError):
        print("invalid consumer compatibility JSON", file=sys.stderr)
        return 1

    try:
        normalized = validate_document(
            document,
            bsr_module_commit=arguments.bsr_module_commit,
            descriptor_sha256=arguments.descriptor_sha256,
            git_commit=arguments.git_commit,
            cargo_lock_path=arguments.cargo_lock,
        )
    except OSError:
        print("Cargo.lock unreadable", file=sys.stderr)
        return 1
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1

    json.dump(normalized, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
