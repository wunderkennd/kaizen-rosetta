from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/verify_rust_contracts.sh"
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
        return subprocess.run(
            [str(SCRIPT)],
            cwd=ROOT,
            env=os.environ | environment,
            text=True,
            capture_output=True,
            check=False,
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
printf '%s\\n' "$*" > "${CARGO_ARGS_FILE}"
exit "${FAKE_CARGO_EXIT:-0}"
""",
        )
        return {
            "BUF_BIN": str(fake_buf),
            "RUSTC_BIN": str(fake_rustc),
            "CARGO_BIN": str(fake_cargo),
            "ROSETTA_RUST_BSR_COMMIT": VALID_BSR_COMMIT,
            "ROSETTA_RUST_DESCRIPTOR_SHA256": VALID_DESCRIPTOR_SHA256,
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

    def test_uses_locked_dependency_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            cargo_args = directory / "cargo-args"
            environment = self.fake_tools(directory)
            environment["CARGO_ARGS_FILE"] = str(cargo_args)
            result = self.run_script(environment)
            captured_args = cargo_args.read_text(encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--locked", captured_args.split())


if __name__ == "__main__":
    unittest.main()
