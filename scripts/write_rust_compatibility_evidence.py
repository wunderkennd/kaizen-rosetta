#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


CRATE_NAMES = ("buffa", "buffa-types", "connectrpc", "connectrpc-build")
CHECKS = (
    "all-generated-packages",
    "audience-binary",
    "audience-protojson",
    "server-streaming-interface",
    "unary-interface",
)


def command_output(command: list[str], repository_root: Path) -> str:
    return subprocess.run(
        command,
        cwd=repository_root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()


def locked_crate_versions(
    cargo_bin: str, manifest: Path, repository_root: Path
) -> dict[str, str]:
    metadata = json.loads(
        command_output(
            [
                cargo_bin,
                "metadata",
                "--locked",
                "--format-version",
                "1",
                "--manifest-path",
                str(manifest),
            ],
            repository_root,
        )
    )
    packages = metadata.get("packages")
    if not isinstance(packages, list):
        raise SystemExit("cargo metadata did not return a package list")

    versions_by_name: dict[str, set[str]] = {name: set() for name in CRATE_NAMES}
    for package in packages:
        if not isinstance(package, dict):
            continue
        name = package.get("name")
        version = package.get("version")
        if name in versions_by_name and isinstance(version, str):
            versions_by_name[name].add(version)

    versions: dict[str, str] = {}
    for name in CRATE_NAMES:
        candidates = versions_by_name[name]
        if len(candidates) != 1:
            raise SystemExit(
                f"cargo metadata must contain exactly one locked version for {name}"
            )
        versions[name] = next(iter(candidates))
    return versions


def current_git_commit(git_bin: str, repository_root: Path) -> str:
    commit = command_output(
        [git_bin, "rev-parse", "--verify", "HEAD^{commit}"], repository_root
    )
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise SystemExit("git rev-parse did not return a 40-character commit")
    return commit


def evidence_document(
    *,
    bsr_module_commit: str,
    descriptor_sha256: str,
    lockfile: Path,
    cargo_version: str,
    rust_version: str,
    crate_versions: dict[str, str],
    git_commit: str,
) -> dict[str, Any]:
    return {
        "records": [
            {
                "adapter": "connect-rust",
                "bsrModule": "buf.build/kaizen/rosetta",
                "bsrModuleCommit": bsr_module_commit,
                "canary": "rust-contracts-v1",
                "cargoLockSha256": hashlib.sha256(lockfile.read_bytes()).hexdigest(),
                "cargoVersion": cargo_version,
                "checks": list(CHECKS),
                "crateVersions": crate_versions,
                "descriptorSha256": descriptor_sha256,
                "generationMode": "cargo-build-rs-bsr-export",
                "gitCommit": git_commit,
                "rustVersion": rust_version,
                "schema": "rosetta.consumer-compatibility.rust.v1",
                "status": "passed",
            }
        ],
        "schema": "rosetta.consumer-compatibility.v1",
    }


def atomic_write_json(output: Path, document: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(document, temporary_file, indent=2, sort_keys=True)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, output)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--lockfile", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bsr-module-commit", required=True)
    parser.add_argument("--descriptor-sha256", required=True)
    parser.add_argument("--cargo-version", required=True)
    parser.add_argument("--rust-version", required=True)
    parser.add_argument("--cargo-bin", default="cargo")
    parser.add_argument("--git-bin", default="git")
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    crate_versions = locked_crate_versions(
        arguments.cargo_bin, arguments.manifest, arguments.repository_root
    )
    git_commit = current_git_commit(arguments.git_bin, arguments.repository_root)
    document = evidence_document(
        bsr_module_commit=arguments.bsr_module_commit,
        descriptor_sha256=arguments.descriptor_sha256,
        lockfile=arguments.lockfile,
        cargo_version=arguments.cargo_version,
        rust_version=arguments.rust_version,
        crate_versions=crate_versions,
        git_commit=git_commit,
    )
    atomic_write_json(arguments.output, document)


if __name__ == "__main__":
    main()
