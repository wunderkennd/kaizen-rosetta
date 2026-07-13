#!/usr/bin/env python3
"""Fail-closed validation for Rust consumer-compatibility evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path


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
    if evidence["schema"] != "rosetta.consumer-compatibility.rust.v1":
        raise ValueError("record schema mismatch")
    if evidence["adapter"] != "connect-rust":
        raise ValueError("adapter mismatch")
    if evidence["bsrModule"] != "buf.build/kaizen/rosetta":
        raise ValueError("BSR module mismatch")
    if evidence["bsrModuleCommit"] != bsr_module_commit:
        raise ValueError("BSR commit mismatch")
    if evidence["canary"] != "rust-contracts-v1":
        raise ValueError("canary mismatch")

    cargo_lock_sha256 = hashlib.sha256(cargo_lock_path.read_bytes()).hexdigest()
    if evidence["cargoLockSha256"] != cargo_lock_sha256:
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
    if evidence["descriptorSha256"] != descriptor_sha256:
        raise ValueError("descriptor mismatch")
    if evidence["generationMode"] != "cargo-build-rs-bsr-export":
        raise ValueError("generation mode mismatch")
    if evidence["gitCommit"] != git_commit:
        raise ValueError("Git commit mismatch")
    if evidence["rustVersion"] != "1.88.0":
        raise ValueError("Rust version mismatch")
    if evidence["status"] != "passed":
        raise ValueError("status must be passed")

    return {
        "adapter": "connect-rust",
        "bsrModule": "buf.build/kaizen/rosetta",
        "bsrModuleCommit": bsr_module_commit,
        "canary": "rust-contracts-v1",
        "cargoLockSha256": cargo_lock_sha256,
        "cargoVersion": "1.88.0",
        "checks": list(CHECKS),
        "crateVersions": dict(CRATE_VERSIONS),
        "descriptorSha256": descriptor_sha256,
        "generationMode": "cargo-build-rs-bsr-export",
        "gitCommit": git_commit,
        "rustVersion": "1.88.0",
        "schema": "rosetta.consumer-compatibility.rust.v1",
        "status": "passed",
    }
