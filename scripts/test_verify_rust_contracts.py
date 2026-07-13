from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.write_rust_compatibility_evidence import current_git_commit, locked_crate_versions


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/verify_rust_contracts.sh"
WRITER = ROOT / "scripts/write_rust_compatibility_evidence.py"
VALID_BSR_COMMIT = "045c39860c9c40178a3a1ed3088c218f"
DESCRIPTOR_CONTENT = b"immutable descriptor\n"
VALID_DESCRIPTOR_SHA256 = hashlib.sha256(DESCRIPTOR_CONTENT).hexdigest()


class RustContractVerificationScriptTest(unittest.TestCase):
    @staticmethod
    def executable(path: Path, contents: str) -> Path:
        path.write_text(contents, encoding="utf-8")
        path.chmod(0o755)
        return path

    def run_script(
        self, environment: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated_environment = {
                "ROSETTA_RUST_EVIDENCE_FILE": str(
                    Path(temporary_directory) / "consumer-compatibility-rust.json"
                )
            }
            return subprocess.run(
                [str(SCRIPT)],
                cwd=ROOT,
                env=os.environ | isolated_environment | environment,
                text=True,
                capture_output=True,
                check=False,
            )

    def run_writer(self, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        if not WRITER.is_file():
            return subprocess.CompletedProcess(
                [sys.executable, str(WRITER), *arguments],
                127,
                "",
                f"writer is missing: {WRITER}",
            )
        return subprocess.run(
            [sys.executable, str(WRITER), *arguments],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def locked_versions_for_packages(
        self, directory: Path, packages: list[dict[str, str]]
    ) -> dict[str, str]:
        metadata = json.dumps({"packages": packages})
        fake_cargo = self.executable(
            directory / "metadata-cargo",
            f"""#!/usr/bin/env python3
print({metadata!r})
""",
        )
        return locked_crate_versions(
            str(fake_cargo), directory / "Cargo.toml", directory
        )

    def fake_tools(self, directory: Path) -> dict[str, str]:
        fake_buf = self.executable(
            directory / "buf",
            """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "--version" ]]; then
  printf '%s\\n' "${FAKE_BUF_VERSION:-1.66.0}"
  exit 0
fi
if [[ "$1" == "export" ]]; then
  if [[ "${FAKE_BUF_EXPORT_EXIT:-0}" != 0 ]]; then
    exit "${FAKE_BUF_EXPORT_EXIT}"
  fi
  while [[ "$1" != "--output" ]]; do shift; done
  mkdir -p "$2/kaizen/audience/v1"
  printf 'syntax = "proto3";\\n' > "$2/kaizen/audience/v1/audience.proto"
  exit 0
fi
if [[ "$1" == "build" ]]; then
  while [[ "$1" != "--output" ]]; do shift; done
  printf 'immutable descriptor\\n' > "$2"
  exit 0
fi
exit 99
""",
        )
        fake_rustc = self.executable(
            directory / "rustc",
            """#!/usr/bin/env bash
if [[ "$1" == "--version" ]]; then
  printf '%s\\n' "${FAKE_RUSTC_VERSION:-rustc 1.88.0 (6b00bc388 2025-06-23)}"
  exit 0
fi
exit 99
""",
        )
        fake_cargo = self.executable(
            directory / "cargo",
            """#!/usr/bin/env bash
if [[ "$1" == "--version" ]]; then
  printf '%s\\n' "${FAKE_CARGO_VERSION:-cargo 1.88.0 (873a06493 2025-05-10)}"
  exit 0
fi
if [[ -n "${CARGO_ARGS_FILE:-}" ]]; then
  printf '%s\\n' "$*" >> "${CARGO_ARGS_FILE}"
fi
if [[ "$1" == "metadata" ]]; then
  printf '%s\\n' '{"packages":[{"name":"buffa","version":"0.7.1"},{"name":"buffa-types","version":"0.7.1"},{"name":"connectrpc","version":"0.7.0"},{"name":"connectrpc-build","version":"0.7.0"}]}'
  exit 0
fi
if [[ -n "${CANARY_REQUIRES_MISSING_EVIDENCE:-}" && -e "${CANARY_REQUIRES_MISSING_EVIDENCE}" ]]; then
  printf '%s\\n' "stale evidence was present when Cargo started" >&2
  exit 71
fi
if [[ -n "${CANARY_FINISHED_FILE:-}" && "${FAKE_CARGO_EXIT:-0}" == 0 ]]; then
  : > "${CANARY_FINISHED_FILE}"
fi
exit "${FAKE_CARGO_EXIT:-0}"
""",
        )
        return {
            "BUF_BIN": str(fake_buf),
            "RUSTC_BIN": str(fake_rustc),
            "CARGO_BIN": str(fake_cargo),
            "ROSETTA_RUST_BSR_COMMIT": VALID_BSR_COMMIT,
            "ROSETTA_RUST_DESCRIPTOR_SHA256": VALID_DESCRIPTOR_SHA256,
            "ROSETTA_RUST_EVIDENCE_FILE": str(
                directory / "consumer-compatibility-rust.json"
            ),
        }

    def test_rejects_missing_cargo(self) -> None:
        result = self.run_script(
            {
                "ROSETTA_RUST_BSR_COMMIT": VALID_BSR_COMMIT,
                "ROSETTA_RUST_DESCRIPTOR_SHA256": VALID_DESCRIPTOR_SHA256,
                "CARGO_BIN": "/definitely/missing/cargo",
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Cargo is unavailable", result.stderr)

    def test_rejects_rust_version_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            environment = self.fake_tools(directory)
            environment["FAKE_RUSTC_VERSION"] = "rustc 1.89.0 (29483883e 2025-08-04)"
            result = self.run_script(environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Rust version mismatch", result.stderr)

    def test_rejects_git_shaped_bsr_commit(self) -> None:
        result = self.run_script(
            {
                "ROSETTA_RUST_BSR_COMMIT": "0123456789abcdef0123456789abcdef01234567",
                "ROSETTA_RUST_DESCRIPTOR_SHA256": VALID_DESCRIPTOR_SHA256,
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly 32 lowercase hex", result.stderr)

    def test_just_passes_environment_values_without_shell_reinterpretation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence = Path(temporary_directory) / "consumer-compatibility-rust.json"
            result = subprocess.run(
                ["just", "rust-contracts"],
                cwd=ROOT,
                env=os.environ
                | {
                    "ROSETTA_RUST_BSR_COMMIT": "$(printf injected >&2)",
                    "ROSETTA_RUST_DESCRIPTOR_SHA256": VALID_DESCRIPTOR_SHA256,
                    "ROSETTA_RUST_EVIDENCE_FILE": str(evidence),
                },
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly 32 lowercase hex", result.stderr)
        self.assertNotIn("injected", result.stderr)

    def test_just_rejects_mismatched_release_commit_before_canary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            environment = self.fake_tools(directory)
            evidence = Path(environment["ROSETTA_RUST_EVIDENCE_FILE"])
            evidence.write_text("untouched evidence\n", encoding="utf-8")
            environment["BSR_MODULE_COMMIT"] = "f" * 32

            result = subprocess.run(
                ["just", "rust-contracts"],
                cwd=ROOT,
                env=os.environ | environment,
                text=True,
                capture_output=True,
                check=False,
            )

            remaining_evidence = evidence.read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(remaining_evidence, "untouched evidence\n")

    def test_propagates_buf_export_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            environment = self.fake_tools(directory)
            environment["FAKE_BUF_EXPORT_EXIT"] = "17"
            result = self.run_script(environment)
        self.assertEqual(result.returncode, 17)

    def test_rejects_descriptor_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            environment = self.fake_tools(directory)
            environment["ROSETTA_RUST_DESCRIPTOR_SHA256"] = "0" * 64
            result = self.run_script(environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("descriptor SHA-256 mismatch", result.stderr)

    def test_propagates_cargo_generation_or_compile_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            environment = self.fake_tools(directory)
            environment["CARGO_ARGS_FILE"] = str(directory / "cargo-args")
            environment["FAKE_CARGO_EXIT"] = "23"
            result = self.run_script(environment)
        self.assertEqual(result.returncode, 23)

    def test_cargo_failure_removes_stale_evidence_and_skips_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            evidence = directory / "consumer-compatibility-rust.json"
            writer_called = directory / "writer-called"
            evidence.write_text("stale evidence\n", encoding="utf-8")
            fake_writer = self.executable(
                directory / "writer",
                f"""#!/usr/bin/env bash
: > {writer_called!s}
exit 99
""",
            )
            environment = self.fake_tools(directory)
            environment.update(
                {
                    "FAKE_CARGO_EXIT": "23",
                    "CANARY_REQUIRES_MISSING_EVIDENCE": str(evidence),
                    "ROSETTA_RUST_EVIDENCE_FILE": str(evidence),
                    "ROSETTA_RUST_EVIDENCE_WRITER": str(fake_writer),
                }
            )
            result = self.run_script(environment)
            evidence_exists = evidence.exists()
            writer_was_called = writer_called.exists()
        self.assertEqual(result.returncode, 23)
        self.assertFalse(evidence_exists)
        self.assertFalse(writer_was_called)

    def test_success_calls_writer_after_cargo_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            evidence = directory / "consumer-compatibility-rust.json"
            canary_finished = directory / "canary-finished"
            writer_called = directory / "writer-called"
            writer_args = directory / "writer-args"
            fake_writer = self.executable(
                directory / "writer",
                f"""#!/usr/bin/env bash
set -euo pipefail
test -f {canary_finished!s}
: > {writer_called!s}
printf '%s\\n' "$*" > {writer_args!s}
while [[ "$1" != "--output" ]]; do shift; done
printf '%s\\n' '{{"status":"passed"}}' > "$2"
""",
            )
            environment = self.fake_tools(directory)
            environment.update(
                {
                    "CANARY_FINISHED_FILE": str(canary_finished),
                    "ROSETTA_RUST_EVIDENCE_FILE": str(evidence),
                    "ROSETTA_RUST_EVIDENCE_WRITER": str(fake_writer),
                }
            )
            result = self.run_script(environment)
            evidence_contents = evidence.read_text(encoding="utf-8") if evidence.exists() else ""
            writer_was_called = writer_called.exists()
            captured_writer_args = writer_args.read_text(encoding="utf-8").split()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(writer_was_called)
        self.assertEqual(evidence_contents, '{"status":"passed"}\n')
        self.assertIn("--cargo-version", captured_writer_args)
        self.assertEqual(
            captured_writer_args[captured_writer_args.index("--cargo-version") + 1],
            "1.88.0",
        )
        self.assertEqual(
            captured_writer_args.index("--rust-version"),
            captured_writer_args.index("--cargo-version") + 2,
        )
        self.assertIn("--rust-version", captured_writer_args)
        self.assertEqual(
            captured_writer_args[captured_writer_args.index("--rust-version") + 1],
            "1.88.0",
        )
        self.assertEqual(
            captured_writer_args.index("--cargo-bin"),
            captured_writer_args.index("--rust-version") + 2,
        )

    def test_canary_cargo_test_uses_locked_dependency_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            cargo_args = directory / "cargo-args"
            environment = self.fake_tools(directory)
            environment["CARGO_ARGS_FILE"] = str(cargo_args)
            result = self.run_script(environment)
            captured_invocations = [
                invocation.split()
                for invocation in cargo_args.read_text(encoding="utf-8").splitlines()
            ]
        self.assertEqual(result.returncode, 0, result.stderr)
        cargo_test_invocations = [
            invocation
            for invocation in captured_invocations
            if invocation and invocation[0] == "test"
        ]
        self.assertEqual(len(cargo_test_invocations), 1)
        self.assertIn("--locked", cargo_test_invocations[0])
        self.assertIn("--all-targets", cargo_test_invocations[0])

    def test_writer_uses_locked_metadata_for_deterministic_atomic_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            manifest = directory / "Cargo.toml"
            lockfile = directory / "Cargo.lock"
            evidence = directory / "consumer-compatibility-rust.json"
            cargo_args = directory / "cargo-args"
            git_args = directory / "git-args"
            manifest.write_text("[workspace]\n", encoding="utf-8")
            lockfile.write_bytes(b"locked dependency graph\n")
            expected_lock_digest = hashlib.sha256(lockfile.read_bytes()).hexdigest()
            evidence.write_text("stale evidence\n", encoding="utf-8")
            fake_cargo = self.executable(
                directory / "cargo",
                f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" > {cargo_args!s}
printf '%s\\n' '{{"packages":[{{"name":"buffa","version":"0.7.1"}},{{"name":"buffa-types","version":"0.7.1"}},{{"name":"connectrpc","version":"0.7.0"}},{{"name":"connectrpc-build","version":"0.7.0"}}]}}'
""",
            )
            fake_git = self.executable(
                directory / "git",
                f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" > {git_args!s}
printf '%s\\n' '{"b" * 40}'
""",
            )
            arguments = [
                "--repository-root",
                str(directory),
                "--manifest",
                str(manifest),
                "--lockfile",
                str(lockfile),
                "--output",
                str(evidence),
                "--bsr-module-commit",
                VALID_BSR_COMMIT,
                "--descriptor-sha256",
                "077c2d8d31c41bcdac5bc97ed1e6407dfdae95a80e0d86712c960b997dc254fa",
                "--cargo-version",
                "1.88.0",
                "--rust-version",
                "1.88.0",
                "--cargo-bin",
                str(fake_cargo),
                "--git-bin",
                str(fake_git),
            ]
            first_result = self.run_writer(arguments)
            first_bytes = evidence.read_bytes() if evidence.exists() else b""
            second_result = self.run_writer(arguments)
            second_bytes = evidence.read_bytes() if evidence.exists() else b""
            temporary_files = list(directory.glob(f".{evidence.name}.*.tmp"))
            captured_cargo_args = cargo_args.read_text(encoding="utf-8") if cargo_args.exists() else ""
            captured_git_args = git_args.read_text(encoding="utf-8") if git_args.exists() else ""

        self.assertEqual(first_result.returncode, 0, first_result.stderr)
        self.assertEqual(second_result.returncode, 0, second_result.stderr)
        self.assertEqual(first_bytes, second_bytes)
        self.assertEqual(temporary_files, [])
        self.assertEqual(
            captured_cargo_args.split(),
            [
                "metadata",
                "--locked",
                "--format-version",
                "1",
                "--manifest-path",
                str(manifest),
            ],
        )
        self.assertEqual(captured_git_args.strip(), "rev-parse --verify HEAD^{commit}")
        self.assertEqual(
            json.loads(first_bytes),
            {
                "records": [
                    {
                        "adapter": "connect-rust",
                        "bsrModule": "buf.build/kaizen/rosetta",
                        "bsrModuleCommit": VALID_BSR_COMMIT,
                        "canary": "rust-contracts-v1",
                        "cargoLockSha256": expected_lock_digest,
                        "cargoVersion": "1.88.0",
                        "checks": [
                            "all-generated-packages",
                            "audience-binary",
                            "audience-protojson",
                            "server-streaming-interface",
                            "unary-interface",
                        ],
                        "crateVersions": {
                            "buffa": "0.7.1",
                            "buffa-types": "0.7.1",
                            "connectrpc": "0.7.0",
                            "connectrpc-build": "0.7.0",
                        },
                        "descriptorSha256": "077c2d8d31c41bcdac5bc97ed1e6407dfdae95a80e0d86712c960b997dc254fa",
                        "generationMode": "cargo-build-rs-bsr-export",
                        "gitCommit": "b" * 40,
                        "rustVersion": "1.88.0",
                        "schema": "rosetta.consumer-compatibility.rust.v1",
                        "status": "passed",
                    }
                ],
                "schema": "rosetta.consumer-compatibility.v1",
            },
        )

    def test_writer_accepts_sha1_and_sha256_git_object_ids(self) -> None:
        for length in (40, 64):
            with self.subTest(length=length):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    directory = Path(temporary_directory)
                    fake_git = self.executable(
                        directory / "git",
                        f"#!/usr/bin/env bash\nprintf '%s\\n' '{'b' * length}'\n",
                    )

                    commit = current_git_commit(str(fake_git), directory)

                    self.assertEqual(commit, "b" * length)

    def test_writer_rejects_other_git_object_id_shapes(self) -> None:
        for name, value in {
            "39 characters": "b" * 39,
            "41 characters": "b" * 41,
            "63 characters": "b" * 63,
            "65 characters": "b" * 65,
            "nonhex SHA-1": "g" * 40,
            "nonhex SHA-256": "g" * 64,
            "uppercase SHA-1": "A" * 40,
            "uppercase SHA-256": "A" * 64,
        }.items():
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    directory = Path(temporary_directory)
                    fake_git = self.executable(
                        directory / "git",
                        f"#!/usr/bin/env bash\nprintf '%s\\n' '{value}'\n",
                    )

                    with self.assertRaisesRegex(
                        SystemExit,
                        "git rev-parse did not return a 40- or 64-character commit",
                    ):
                        current_git_commit(str(fake_git), directory)

    def test_writer_rejects_missing_locked_crate_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            with self.assertRaisesRegex(
                SystemExit,
                "exactly one locked version for connectrpc-build",
            ):
                self.locked_versions_for_packages(
                    directory,
                    [
                        {"name": "buffa", "version": "0.7.1"},
                        {"name": "buffa-types", "version": "0.7.1"},
                        {"name": "connectrpc", "version": "0.7.0"},
                    ],
                )

    def test_writer_rejects_conflicting_locked_crate_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            with self.assertRaisesRegex(
                SystemExit,
                "exactly one locked version for connectrpc",
            ):
                self.locked_versions_for_packages(
                    directory,
                    [
                        {"name": "buffa", "version": "0.7.1"},
                        {"name": "buffa-types", "version": "0.7.1"},
                        {
                            "id": "registry-a#connectrpc@0.7.0",
                            "name": "connectrpc",
                            "source": "registry-a",
                            "version": "0.7.0",
                        },
                        {
                            "id": "registry-b#connectrpc@0.8.1",
                            "name": "connectrpc",
                            "source": "registry-b",
                            "version": "0.8.1",
                        },
                        {"name": "connectrpc-build", "version": "0.7.0"},
                    ],
                )

    def test_writer_accepts_distinct_package_ids_at_the_same_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            versions = self.locked_versions_for_packages(
                directory,
                [
                    {"name": "buffa", "version": "0.7.1"},
                    {"name": "buffa-types", "version": "0.7.1"},
                    {
                        "id": "registry-a#connectrpc@0.7.0",
                        "name": "connectrpc",
                        "source": "registry-a",
                        "version": "0.7.0",
                    },
                    {
                        "id": "registry-b#connectrpc@0.7.0",
                        "name": "connectrpc",
                        "source": "registry-b",
                        "version": "0.7.0",
                    },
                    {"name": "connectrpc-build", "version": "0.7.0"},
                ],
            )
        self.assertEqual(
            versions,
            {
                "buffa": "0.7.1",
                "buffa-types": "0.7.1",
                "connectrpc": "0.7.0",
                "connectrpc-build": "0.7.0",
            },
        )


if __name__ == "__main__":
    unittest.main()
