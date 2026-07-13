#!/usr/bin/env python3
"""Contract tests for the deterministic release-manifest builder."""

from pathlib import Path
import copy
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_release_manifest.sh"
BASELINE_BSR_MODULE_COMMIT = os.environ.get(
    "RELEASE_MANIFEST_TEST_BSR_COMMIT",
    "3d978f388d4242f3b3c8e663465b85fd",
)
DESCRIPTOR_BYTES = b"deterministic descriptor fixture\n"
DESCRIPTOR_SHA256 = __import__("hashlib").sha256(DESCRIPTOR_BYTES).hexdigest()
PINNED_GENERATORS = """\
version: v2
plugins:
  - remote: buf.build/protocolbuffers/go:v1.36.11
    revision: 1
    out: gen/go
  - remote: buf.build/connectrpc/go:v1.20.0
    revision: 1
    out: gen/go-connect
"""
RELEASE_SOURCE_ERROR = "release sources must match the recorded Git commit"
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


def valid_rust_evidence(
    *,
    module_commit: str,
    descriptor_sha256: str,
    git_commit: str,
    cargo_lock_sha256: str,
) -> dict[str, object]:
    return {
        "adapter": "connect-rust",
        "bsrModule": "buf.build/kaizen/rosetta",
        "bsrModuleCommit": module_commit,
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


def rust_evidence_document(record: dict[str, object]) -> dict[str, object]:
    return {
        "records": [record],
        "schema": "rosetta.consumer-compatibility.v1",
    }


def generated_sdk_metadata(
    buf_gen: str, commit: str = BASELINE_BSR_MODULE_COMMIT
) -> dict[str, object]:
    pins = []
    for entry in re.split(r"(?m)^  - ", buf_gen)[1:]:
        remote = re.search(
            r"(?m)^\s*remote: (buf\.build/[^:]+):(v[0-9]+(?:\.[0-9]+){1,2})$",
            entry,
        )
        revision = re.search(r"(?m)^\s*revision: ([1-9][0-9]*)$", entry)
        if remote and revision:
            pins.append((remote.group(1), remote.group(2), revision.group(1)))
    sdks = []
    for generator, plugin_version, revision_text in pins:
        revision = int(revision_text)
        owner, plugin = generator.removeprefix("buf.build/").split("/")
        if plugin in {"python", "pyi", "py"}:
            ecosystem = "python"
            coordinate = f"kaizen-rosetta-{owner}-{plugin}"
            core = plugin_version.removeprefix("v")
            if core.count(".") == 1:
                core += ".0"
            version = f"{core}.{revision}.dev+{commit[:12]}"
        elif plugin == "go":
            ecosystem = "go"
            coordinate = f"buf.build/gen/go/kaizen/rosetta/{owner}/{plugin}"
            version = (
                f"{plugin_version}-00000000000000-{commit[:12]}.{revision}"
            )
        else:
            ecosystem = "npm"
            coordinate = f"@buf/kaizen_rosetta.{owner}_{plugin}"
            version = (
                f"{plugin_version.removeprefix('v')}-00000000000000-"
                f"{commit[:12]}.{revision}"
            )
        sdks.append(
            {
                "coordinate": coordinate,
                "ecosystem": ecosystem,
                "generator": generator,
                "moduleCommit": commit,
                "pluginRevision": revision,
                "pluginVersion": plugin_version,
                "publicationStatus": "published",
                "version": version,
            }
        )
    return {"moduleCommit": commit, "sdks": sdks}


def generated_sdk_verifications(
    buf_gen: str, commit: str = BASELINE_BSR_MODULE_COMMIT
) -> dict[str, object]:
    metadata = generated_sdk_metadata(buf_gen, commit)
    return {
        "moduleCommit": commit,
        "verifications": [
            {
                "coordinate": sdk["coordinate"],
                "evidence": "fixture exact-coordinate consumer passed",
                "ecosystem": sdk["ecosystem"],
                "generator": sdk["generator"],
                "moduleCommit": sdk["moduleCommit"],
                "pluginRevision": sdk["pluginRevision"],
                "pluginVersion": sdk["pluginVersion"],
                "status": "passed",
                "usable": True,
                "version": sdk["version"],
            }
            for sdk in metadata["sdks"]
        ],
    }


def expected_generated_sdks(buf_gen: str) -> list[dict[str, object]]:
    metadata = generated_sdk_metadata(buf_gen)
    verification = generated_sdk_verifications(buf_gen)
    by_generator = {
        record["generator"]: record for record in verification["verifications"]
    }
    return sorted(
        [
            {**sdk, "verification": by_generator[sdk["generator"]]}
            for sdk in metadata["sdks"]
        ],
        key=lambda sdk: sdk["generator"],
    )


class ReleaseManifestBuilderTests(unittest.TestCase):
    def test_builder_is_available_as_an_executable_script(self) -> None:
        self.assertTrue(SCRIPT.is_file())
        self.assertTrue(SCRIPT.stat().st_mode & 0o111)

    def make_project(
        self,
        directory: Path,
        *,
        buf_gen: str = PINNED_GENERATORS,
        descriptor_digest: str = DESCRIPTOR_SHA256,
        with_git_commit: bool = True,
        object_format: str = "sha1",
    ) -> tuple[Path, dict[str, str]]:
        scripts = directory / "scripts"
        scripts.mkdir()
        builder = scripts / SCRIPT.name
        shutil.copy2(SCRIPT, builder)
        shutil.copy2(ROOT / "scripts/validate_consumer_compatibility.py", scripts)
        shutil.copy2(ROOT / "scripts/verify_rust_contracts.sh", scripts)
        shutil.copy2(ROOT / "scripts/write_rust_compatibility_evidence.py", scripts)

        (directory / "buf.gen.yaml").write_text(buf_gen)
        (directory / "buf.yaml").write_text("version: v2\n")
        (directory / "buf.lock").write_text("# fixture lock\n")
        (directory / "Justfile").write_text("check:\n    true\n")
        (directory / "README.md").write_text("# Release fixture\n")
        docs = directory / "docs"
        docs.mkdir()
        (docs / "generator-pins.md").write_text("# Generator pins\n")
        (docs / "architecture_overview.md").write_text("# Architecture\n")
        proto = directory / "proto"
        proto.mkdir()
        (proto / "fixture.proto").write_text('syntax = "proto3";\n')
        retired = directory / "tools/release"
        retired.mkdir(parents=True)
        (retired / "retired-generators.json").write_text("[]\n")
        rust_canary = directory / "tools/compatibility/rust"
        rust_canary.mkdir(parents=True)
        shutil.copy2(ROOT / "tools/compatibility/rust/Cargo.lock", rust_canary)
        shutil.copy2(ROOT / "tools/compatibility/rust/build.rs", rust_canary)

        subprocess.run(
            ["git", "init", "-q", f"--object-format={object_format}"],
            cwd=directory,
            check=True,
        )
        if with_git_commit:
            subprocess.run(["git", "add", "."], cwd=directory, check=True)
            commit_environment = {
                **os.environ,
                "GIT_AUTHOR_NAME": "Rosetta Test",
                "GIT_AUTHOR_EMAIL": "rosetta-test@example.invalid",
                "GIT_AUTHOR_DATE": "2026-07-12T12:00:00Z",
                "GIT_COMMITTER_NAME": "Rosetta Test",
                "GIT_COMMITTER_EMAIL": "rosetta-test@example.invalid",
                "GIT_COMMITTER_DATE": "2026-07-12T12:00:00Z",
            }
            subprocess.run(
                ["git", "commit", "-q", "-m", "fixture"],
                cwd=directory,
                env=commit_environment,
                check=True,
            )

        dist = directory / "dist"
        dist.mkdir()
        (dist / "rosetta-descriptor.binpb").write_bytes(DESCRIPTOR_BYTES)
        (dist / "rosetta-descriptor.sha256").write_text(
            f"{descriptor_digest}\n" if descriptor_digest else ""
        )
        bsr_descriptor = dist / "test-bsr-descriptor.binpb"
        bsr_descriptor.write_bytes(DESCRIPTOR_BYTES)
        sdk_metadata = dist / "test-sdk-metadata.json"
        sdk_metadata.write_text(
            json.dumps(generated_sdk_metadata(buf_gen), sort_keys=True) + "\n"
        )
        sdk_verification = dist / "test-sdk-verification.json"
        sdk_verification.write_text(
            json.dumps(generated_sdk_verifications(buf_gen), sort_keys=True) + "\n"
        )
        git_commit = ""
        if with_git_commit:
            git_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=directory,
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
        rust_lock_digest = hashlib.sha256(
            (rust_canary / "Cargo.lock").read_bytes()
        ).hexdigest()
        rust_evidence = dist / "test-rust-evidence.json"
        rust_evidence.write_text(
            json.dumps(
                rust_evidence_document(
                    valid_rust_evidence(
                        module_commit=BASELINE_BSR_MODULE_COMMIT,
                        descriptor_sha256=DESCRIPTOR_SHA256,
                        git_commit=git_commit or "b" * 40,
                        cargo_lock_sha256=rust_lock_digest,
                    )
                ),
                sort_keys=True,
            )
            + "\n"
        )
        bin_directory = directory / "bin"
        bin_directory.mkdir()
        fake_buf = bin_directory / "buf"
        fake_buf.write_text(
            "#!/usr/bin/env bash\n"
            "if [[ -n \"${FAKE_BUF_MARKER:-}\" ]]; then\n"
            "  : > \"${FAKE_BUF_MARKER}\"\n"
            "fi\n"
            "printf '%s\\n' '1.66.0'\n"
        )
        fake_buf.chmod(0o755)

        environment = {
            **os.environ,
            "PATH": f"{bin_directory}{os.pathsep}{os.environ['PATH']}",
            "BSR_MODULE_COMMIT": BASELINE_BSR_MODULE_COMMIT,
            "BSR_DESCRIPTOR_FILE": str(bsr_descriptor),
            "BSR_SDK_METADATA_FILE": str(sdk_metadata),
            "BSR_SDK_VERIFICATION_FILE": str(sdk_verification),
            "ROSETTA_RUST_BSR_COMMIT": BASELINE_BSR_MODULE_COMMIT,
            "ROSETTA_RUST_COMPATIBILITY_FILE": str(rust_evidence),
        }
        return builder, environment

    def run_builder(
        self, directory: Path, environment: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(directory / "scripts/build_release_manifest.sh")],
            cwd=directory,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def read_rust_evidence(
        self, environment: dict[str, str]
    ) -> dict[str, object]:
        return json.loads(
            Path(environment["ROSETTA_RUST_COMPATIBILITY_FILE"]).read_text()
        )

    def write_rust_evidence(
        self, environment: dict[str, str], document: object
    ) -> None:
        Path(environment["ROSETTA_RUST_COMPATIBILITY_FILE"]).write_text(
            json.dumps(document) + "\n"
        )

    def install_fake_mktemp(self, directory: Path) -> Path:
        real_mktemp = shutil.which("mktemp")
        self.assertIsNotNone(real_mktemp)
        fake_mktemp = directory / "bin/mktemp"
        fake_mktemp.write_text(
            f"""#!/usr/bin/env bash
set -euo pipefail
if [[ -n "${{FAKE_MKTEMP_COUNTER:-}}" ]]; then
  count=0
  if [[ -f "${{FAKE_MKTEMP_COUNTER}}" ]]; then
    IFS= read -r count < "${{FAKE_MKTEMP_COUNTER}}"
  fi
  count="$((count + 1))"
  printf '%s\\n' "${{count}}" > "${{FAKE_MKTEMP_COUNTER}}"
  if [[ "${{count}}" == "${{FAKE_MKTEMP_FAIL_ON_CALL:-0}}" ]]; then
    exit 86
  fi
fi
path="$({shlex.quote(real_mktemp)} "$@")"
if [[ -n "${{FAKE_MKTEMP_LOG:-}}" ]]; then
  printf '%s\\n' "${{path}}" >> "${{FAKE_MKTEMP_LOG}}"
fi
printf '%s\\n' "${{path}}"
"""
        )
        fake_mktemp.chmod(0o755)
        return fake_mktemp

    def test_rejects_a_missing_bsr_module_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            environment.pop("BSR_MODULE_COMMIT")

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("BSR_MODULE_COMMIT is required", result.stderr)

    def test_rejects_a_git_sha_as_the_bsr_module_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            environment["BSR_MODULE_COMMIT"] = "b" * 40

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("immutable 32-character BSR module commit", result.stderr)

    def test_rejects_an_all_zero_bsr_module_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            environment["BSR_MODULE_COMMIT"] = "0" * 32

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("BSR_MODULE_COMMIT must not be all zeros", result.stderr)

    def test_requires_the_rust_release_commit_before_buf_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            environment.pop("ROSETTA_RUST_BSR_COMMIT")
            marker = root / "buf-invoked"
            environment["FAKE_BUF_MARKER"] = str(marker)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ROSETTA_RUST_BSR_COMMIT is required", result.stderr)
            self.assertFalse(marker.exists())

    def test_rejects_mismatched_release_commits_before_buf_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            environment["ROSETTA_RUST_BSR_COMMIT"] = "f" * 32
            marker = root / "buf-invoked"
            environment["FAKE_BUF_MARKER"] = str(marker)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "ROSETTA_RUST_BSR_COMMIT must equal BSR_MODULE_COMMIT",
                result.stderr,
            )
            self.assertFalse(marker.exists())

    def test_requires_a_rust_compatibility_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            environment.pop("ROSETTA_RUST_COMPATIBILITY_FILE")

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ROSETTA_RUST_COMPATIBILITY_FILE is required", result.stderr)

    def test_rejects_a_missing_rust_compatibility_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            Path(environment["ROSETTA_RUST_COMPATIBILITY_FILE"]).unlink()

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Rust compatibility evidence is required", result.stderr)

    def test_rejects_an_empty_rust_compatibility_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            Path(environment["ROSETTA_RUST_COMPATIBILITY_FILE"]).write_text("")

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Rust compatibility evidence is required", result.stderr)

    def test_rejects_invalid_rust_compatibility_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            Path(environment["ROSETTA_RUST_COMPATIBILITY_FILE"]).write_text(
                "{not-json\n"
            )

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid consumer compatibility JSON", result.stderr)

    def test_rejects_missing_rust_evidence_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            evidence = self.read_rust_evidence(environment)
            evidence["records"] = []
            self.write_rust_evidence(environment, evidence)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exactly one Rust evidence record required", result.stderr)

    def test_rejects_duplicate_rust_evidence_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            evidence = self.read_rust_evidence(environment)
            evidence["records"].append(copy.deepcopy(evidence["records"][0]))
            self.write_rust_evidence(environment, evidence)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate Rust evidence", result.stderr)

    def test_rejects_rust_evidence_for_a_stale_bsr_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            evidence = self.read_rust_evidence(environment)
            evidence["records"][0]["bsrModuleCommit"] = "f" * 32
            self.write_rust_evidence(environment, evidence)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("BSR commit mismatch", result.stderr)

    def test_rejects_rust_evidence_for_a_stale_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            evidence = self.read_rust_evidence(environment)
            evidence["records"][0]["descriptorSha256"] = "f" * 64
            self.write_rust_evidence(environment, evidence)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("descriptor mismatch", result.stderr)

    def test_rejects_rust_evidence_for_a_stale_git_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            evidence = self.read_rust_evidence(environment)
            evidence["records"][0]["gitCommit"] = "f" * 40
            self.write_rust_evidence(environment, evidence)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Git commit mismatch", result.stderr)

    def test_rejects_rust_evidence_for_a_stale_lock_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            evidence = self.read_rust_evidence(environment)
            evidence["records"][0]["cargoLockSha256"] = "f" * 64
            self.write_rust_evidence(environment, evidence)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Cargo.lock digest mismatch", result.stderr)

    def test_rejects_wrong_rust_toolchain_or_crate_versions(self) -> None:
        cases = {
            "Cargo": ("cargoVersion", "1.89.0", "Cargo version mismatch"),
            "Rust": ("rustVersion", "1.89.0", "Rust version mismatch"),
            "crates": ("crateVersions", {}, "crate version mismatch"),
        }
        for name, (field, value, error) in cases.items():
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    root = Path(temporary_directory)
                    _, environment = self.make_project(root)
                    evidence = self.read_rust_evidence(environment)
                    evidence["records"][0][field] = value
                    self.write_rust_evidence(environment, evidence)

                    result = self.run_builder(root, environment)

                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(error, result.stderr)

    def test_rejects_wrong_rust_canary_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            evidence = self.read_rust_evidence(environment)
            evidence["records"][0]["canary"] = "other-canary"
            self.write_rust_evidence(environment, evidence)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("canary mismatch", result.stderr)

    def test_rejects_failed_rust_compatibility_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            evidence = self.read_rust_evidence(environment)
            evidence["records"][0]["status"] = "failed"
            self.write_rust_evidence(environment, evidence)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("status must be passed", result.stderr)

    def test_rejects_dirty_tracked_rust_certification_sources(self) -> None:
        source_paths = (
            "tools/compatibility/rust/build.rs",
            "scripts/validate_consumer_compatibility.py",
            "scripts/verify_rust_contracts.sh",
            "scripts/write_rust_compatibility_evidence.py",
        )
        for source_path in source_paths:
            with self.subTest(source_path=source_path):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    root = Path(temporary_directory)
                    _, environment = self.make_project(root)
                    source = root / source_path
                    source.write_text(source.read_text() + "\n# dirty\n")

                    result = self.run_builder(root, environment)

                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(RELEASE_SOURCE_ERROR, result.stderr)
                    self.assertIn(source_path, result.stderr)

    def test_rejects_an_empty_descriptor_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, descriptor_digest="")

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("descriptor digest is required", result.stderr)

    def test_rejects_an_all_zero_descriptor_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, descriptor_digest="0" * 64)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("descriptor digest must not be all zeros", result.stderr)

    def test_rejects_a_bsr_commit_with_different_descriptor_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            Path(environment["BSR_DESCRIPTOR_FILE"]).write_bytes(
                b"descriptor from an unrelated valid BSR commit\n"
            )

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("BSR descriptor does not match local descriptor", result.stderr)

    def test_rejects_a_descriptor_digest_that_does_not_match_local_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, descriptor_digest="a" * 64)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("descriptor digest does not match local descriptor", result.stderr)

    def test_rejects_a_missing_git_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, with_git_commit=False)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Git commit is required", result.stderr)

    def test_accepts_a_64_character_git_object_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, object_format="sha256")

            result = self.run_builder(root, environment)

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((root / "dist/release-manifest.json").read_text())
            self.assertRegex(manifest["gitCommit"], r"^[0-9a-f]{64}$")

    def test_rejects_a_dirty_proto_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            (root / "proto/fixture.proto").write_text('syntax = "proto2";\n')

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(RELEASE_SOURCE_ERROR, result.stderr)
            self.assertIn("proto/fixture.proto", result.stderr)

    def test_rejects_a_dirty_generator_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            (root / "buf.gen.yaml").write_text(PINNED_GENERATORS + "# dirty\n")

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(RELEASE_SOURCE_ERROR, result.stderr)
            self.assertIn("buf.gen.yaml", result.stderr)

    def test_rejects_staged_release_documentation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            pins = root / "docs/generator-pins.md"
            pins.write_text("# Changed generator pins\n")
            subprocess.run(["git", "add", str(pins)], cwd=root, check=True)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(RELEASE_SOURCE_ERROR, result.stderr)
            self.assertIn("docs/generator-pins.md", result.stderr)

    def test_rejects_an_untracked_relevant_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            tests = root / "tests"
            tests.mkdir()
            (tests / "new_contract_test.py").write_text("# untracked\n")

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(RELEASE_SOURCE_ERROR, result.stderr)
            self.assertIn("tests/new_contract_test.py", result.stderr)

    def test_ignores_generated_and_superpowers_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            for relative_path in (
                "dist/extra-output.binpb",
                "gen/go/generated.pb.go",
                ".superpowers/sdd/report.md",
            ):
                output = root / relative_path
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text("generated\n")

            result = self.run_builder(root, environment)

            self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_a_generator_without_a_version(self) -> None:
        unversioned_generator = PINNED_GENERATORS.replace(
            "buf.build/connectrpc/go:v1.20.0", "buf.build/connectrpc/go"
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, buf_gen=unversioned_generator)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("generator remote must pin an explicit version", result.stderr)

    def test_rejects_a_mutable_generator_version(self) -> None:
        mutable_generator = PINNED_GENERATORS.replace("v1.20.0", "latest")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, buf_gen=mutable_generator)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("generator remote must pin an explicit version", result.stderr)

    def test_rejects_a_malformed_generator_version(self) -> None:
        malformed_generator = PINNED_GENERATORS.replace("v1.20.0", "v1latest")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, buf_gen=malformed_generator)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("generator remote must pin an explicit version", result.stderr)

    def test_rejects_a_local_generator_plugin(self) -> None:
        local_generator = """\
version: v2
plugins:
  - local: protoc-gen-go
    out: gen/go
"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, buf_gen=local_generator)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("only remote generator plugins are allowed", result.stderr)

    def test_rejects_a_protoc_builtin_generator_plugin(self) -> None:
        builtin_generator = """\
version: v2
plugins:
  - protoc_builtin: cpp
    out: gen/cpp
"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, buf_gen=builtin_generator)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("only remote generator plugins are allowed", result.stderr)

    def test_rejects_an_unknown_generator_plugin_kind(self) -> None:
        unknown_generator = """\
version: v2
plugins:
  - custom_plugin: generator
    out: gen/custom
"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, buf_gen=unknown_generator)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unknown generator plugin kind", result.stderr)

    def test_rejects_mixed_generator_plugin_kinds(self) -> None:
        mixed_generator = """\
version: v2
plugins:
  - remote: buf.build/protocolbuffers/go:v1.36.11
    local: protoc-gen-go
    revision: 1
    out: gen/go
"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, buf_gen=mixed_generator)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("generator plugin must select exactly one kind", result.stderr)

    def test_rejects_a_generator_without_a_revision(self) -> None:
        missing_revision = PINNED_GENERATORS.replace("    revision: 1\n", "", 1)
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, buf_gen=missing_revision)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("generator remote must pin an explicit revision", result.stderr)

    def test_rejects_a_zero_generator_revision(self) -> None:
        zero_revision = PINNED_GENERATORS.replace(
            "    revision: 1\n", "    revision: 0\n", 1
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, buf_gen=zero_revision)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("generator revision must be positive", result.stderr)

    def test_rejects_duplicate_generator_names(self) -> None:
        duplicate_generator = PINNED_GENERATORS.replace(
            "buf.build/connectrpc/go:v1.20.0",
            "buf.build/protocolbuffers/go:v1.36.11",
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, buf_gen=duplicate_generator)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate generator plugin name", result.stderr)

    def test_accepts_revision_before_remote(self) -> None:
        reordered_generator = PINNED_GENERATORS.replace(
            "  - remote: buf.build/connectrpc/go:v1.20.0\n    revision: 1\n",
            "  - revision: 1\n    remote: buf.build/connectrpc/go:v1.20.0\n",
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, buf_gen=reordered_generator)

            result = self.run_builder(root, environment)

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((root / "dist/release-manifest.json").read_text())
            self.assertIn(
                {
                    "name": "buf.build/connectrpc/go",
                    "revision": 1,
                    "version": "v1.20.0",
                },
                manifest["generators"],
            )

    def test_writes_complete_sorted_json_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(
                root, buf_gen=(ROOT / "buf.gen.yaml").read_text()
            )
            git_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            expected_manifest = {
                "bsrModule": "buf.build/kaizen/rosetta",
                "bsrModuleCommit": BASELINE_BSR_MODULE_COMMIT,
                "bufCliVersion": "1.66.0",
                "consumerCompatibility": {
                    "rust": valid_rust_evidence(
                        module_commit=BASELINE_BSR_MODULE_COMMIT,
                        descriptor_sha256=DESCRIPTOR_SHA256,
                        git_commit=git_commit,
                        cargo_lock_sha256=hashlib.sha256(
                            (ROOT / "tools/compatibility/rust/Cargo.lock").read_bytes()
                        ).hexdigest(),
                    )
                },
                "descriptorSha256": DESCRIPTOR_SHA256,
                "generatorPinsDocument": "docs/generator-pins.md",
                "generators": [
                    {
                        "name": "buf.build/bufbuild/es",
                        "revision": 1,
                        "version": "v2.12.1",
                    },
                    {
                        "name": "buf.build/connectrpc/go",
                        "revision": 1,
                        "version": "v1.20.0",
                    },
                    {
                        "name": "buf.build/connectrpc/py",
                        "revision": 1,
                        "version": "v0.11.0",
                    },
                    {
                        "name": "buf.build/protocolbuffers/go",
                        "revision": 1,
                        "version": "v1.36.11",
                    },
                    {
                        "name": "buf.build/protocolbuffers/pyi",
                        "revision": 1,
                        "version": "v33.5",
                    },
                    {
                        "name": "buf.build/protocolbuffers/python",
                        "revision": 1,
                        "version": "v33.5",
                    },
                ],
                "generatedSdks": expected_generated_sdks(
                    (ROOT / "buf.gen.yaml").read_text()
                ),
                "gitCommit": git_commit,
                "retiredGenerators": [],
            }
            expected_bytes = (
                json.dumps(expected_manifest, indent=2, sort_keys=True) + "\n"
            )

            first_result = self.run_builder(root, environment)
            self.assertEqual(first_result.returncode, 0, first_result.stderr)
            first_bytes = (root / "dist/release-manifest.json").read_text()
            second_result = self.run_builder(root, environment)
            self.assertEqual(second_result.returncode, 0, second_result.stderr)
            second_bytes = (root / "dist/release-manifest.json").read_text()

            self.assertEqual(first_bytes, expected_bytes)
            self.assertEqual(second_bytes, expected_bytes)
            manifest = json.loads(first_bytes)
            for field in ("generatedSdks", "generators", "retiredGenerators"):
                with self.subTest(field=field):
                    self.assertEqual(
                        json.dumps(manifest[field], indent=2, sort_keys=True) + "\n",
                        json.dumps(expected_manifest[field], indent=2, sort_keys=True)
                        + "\n",
                    )
            self.assertEqual(len(manifest["generators"]), 6)
            self.assertEqual(len(manifest["generatedSdks"]), 6)
            self.assertFalse(
                any(
                    "rust" in json.dumps(record).lower()
                    for field in ("generators", "generatedSdks")
                    for record in manifest[field]
                )
            )

    def test_rejects_missing_generated_sdk_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            metadata_path = Path(environment["BSR_SDK_METADATA_FILE"])
            metadata = json.loads(metadata_path.read_text())
            metadata["sdks"].pop()
            metadata_path.write_text(json.dumps(metadata))

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("generated SDK metadata missing", result.stderr)

    def test_rejects_mismatched_sdk_commit_association(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            metadata_path = Path(environment["BSR_SDK_METADATA_FILE"])
            metadata = json.loads(metadata_path.read_text())
            metadata["sdks"][0]["moduleCommit"] = "f" * 32
            metadata_path.write_text(json.dumps(metadata))

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("module commit mismatch", result.stderr)

    def test_rejects_mismatched_sdk_version_association(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            metadata_path = Path(environment["BSR_SDK_METADATA_FILE"])
            metadata = json.loads(metadata_path.read_text())
            metadata["sdks"][0]["version"] = metadata["sdks"][0][
                "version"
            ].replace("v1.36.11", "v9.99.99")
            metadata_path.write_text(json.dumps(metadata))

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("version/plugin association mismatch", result.stderr)

    def test_rejects_duplicate_generated_sdk_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            metadata_path = Path(environment["BSR_SDK_METADATA_FILE"])
            metadata = json.loads(metadata_path.read_text())
            metadata["sdks"][1]["coordinate"] = metadata["sdks"][0]["coordinate"]
            metadata_path.write_text(json.dumps(metadata))

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate generated SDK coordinate", result.stderr)

    def test_rejects_missing_available_generated_sdk_coordinate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            metadata_path = Path(environment["BSR_SDK_METADATA_FILE"])
            metadata = json.loads(metadata_path.read_text())
            metadata["sdks"][0].pop("coordinate")
            metadata_path.write_text(json.dumps(metadata))

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("generated SDK coordinate missing", result.stderr)

    def test_rejects_mismatched_generated_sdk_coordinate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            metadata_path = Path(environment["BSR_SDK_METADATA_FILE"])
            metadata = json.loads(metadata_path.read_text())
            metadata["sdks"][0]["coordinate"] += "-wrong"
            metadata_path.write_text(json.dumps(metadata))

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("generated SDK coordinate mismatch", result.stderr)

    def test_records_explicit_unavailable_generated_sdk_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            metadata_path = Path(environment["BSR_SDK_METADATA_FILE"])
            metadata = json.loads(metadata_path.read_text())
            unavailable = metadata["sdks"][0]
            unavailable["publicationStatus"] = "unavailable"
            unavailable["reason"] = "plugin does not publish a packaged SDK"
            unavailable.pop("coordinate")
            unavailable.pop("version")
            metadata_path.write_text(json.dumps(metadata))
            verification_path = Path(environment["BSR_SDK_VERIFICATION_FILE"])
            verification = json.loads(verification_path.read_text())
            record = next(
                item
                for item in verification["verifications"]
                if item["generator"] == unavailable["generator"]
            )
            record.update(
                {
                    "status": "not_applicable",
                    "usable": False,
                    "reason": "SDK is not published",
                }
            )
            record.pop("evidence")
            record.pop("coordinate")
            record.pop("version")
            verification_path.write_text(json.dumps(verification))

            result = self.run_builder(root, environment)

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((root / "dist/release-manifest.json").read_text())
            recorded = next(
                sdk
                for sdk in manifest["generatedSdks"]
                if sdk["generator"] == unavailable["generator"]
            )
            self.assertEqual(recorded["publicationStatus"], "unavailable")
            self.assertFalse(recorded["verification"]["usable"])
            self.assertNotIn("coordinate", recorded)

    def test_rejects_unavailable_verification_with_coordinate_claims(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            metadata_path = Path(environment["BSR_SDK_METADATA_FILE"])
            metadata = json.loads(metadata_path.read_text())
            unavailable = metadata["sdks"][0]
            unavailable["publicationStatus"] = "unavailable"
            unavailable["reason"] = "plugin does not publish a packaged SDK"
            unavailable.pop("coordinate")
            unavailable.pop("version")
            metadata_path.write_text(json.dumps(metadata))
            verification_path = Path(environment["BSR_SDK_VERIFICATION_FILE"])
            verification = json.loads(verification_path.read_text())
            record = verification["verifications"][0]
            record.update(
                {
                    "status": "not_applicable",
                    "usable": False,
                    "reason": "SDK is not published",
                }
            )
            record.pop("evidence")
            verification_path.write_text(json.dumps(verification))

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "unavailable generated SDK verification must not claim coordinate/version",
                result.stderr,
            )

    def test_records_published_but_unusable_generated_sdk(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            verification_path = Path(environment["BSR_SDK_VERIFICATION_FILE"])
            verification = json.loads(verification_path.read_text())
            record = verification["verifications"][0]
            record.update(
                {
                    "status": "failed",
                    "usable": False,
                    "reason": (
                        "known nested-import defect; guarded just generate repair required"
                    ),
                }
            )
            record.pop("evidence")
            verification_path.write_text(json.dumps(verification))

            result = self.run_builder(root, environment)

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((root / "dist/release-manifest.json").read_text())
            recorded = next(
                sdk
                for sdk in manifest["generatedSdks"]
                if sdk["generator"] == record["generator"]
            )
            self.assertEqual(recorded["publicationStatus"], "published")
            self.assertIsInstance(recorded["coordinate"], str)
            self.assertFalse(recorded["verification"]["usable"])
            self.assertEqual(recorded["verification"]["status"], "failed")

    def test_rejects_verification_for_a_stale_coordinate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            verification_path = Path(environment["BSR_SDK_VERIFICATION_FILE"])
            verification = json.loads(verification_path.read_text())
            verification["verifications"][0]["coordinate"] += "-stale"
            verification_path.write_text(json.dumps(verification))

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("verification coordinate mismatch", result.stderr)

    def test_rejects_verification_for_a_stale_sdk_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            verification_path = Path(environment["BSR_SDK_VERIFICATION_FILE"])
            verification = json.loads(verification_path.read_text())
            verification["verifications"][0]["version"] += ".stale"
            verification_path.write_text(json.dumps(verification))

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("verification version mismatch", result.stderr)

    def test_rejects_verification_for_a_stale_plugin_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            verification_path = Path(environment["BSR_SDK_VERIFICATION_FILE"])
            verification = json.loads(verification_path.read_text())
            verification["verifications"][0]["pluginVersion"] = "v9.9.9"
            verification_path.write_text(json.dumps(verification))

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("verification plugin version mismatch", result.stderr)

    def test_rejects_verification_for_a_stale_plugin_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            verification_path = Path(environment["BSR_SDK_VERIFICATION_FILE"])
            verification = json.loads(verification_path.read_text())
            verification["verifications"][0]["pluginRevision"] = 99
            verification_path.write_text(json.dumps(verification))

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("verification plugin revision mismatch", result.stderr)

    def test_rejects_verification_for_a_stale_ecosystem(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            verification_path = Path(environment["BSR_SDK_VERIFICATION_FILE"])
            verification = json.loads(verification_path.read_text())
            verification["verifications"][0]["ecosystem"] = "npm"
            verification_path.write_text(json.dumps(verification))

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("verification ecosystem mismatch", result.stderr)

    def test_rejects_verification_for_a_stale_module_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            verification_path = Path(environment["BSR_SDK_VERIFICATION_FILE"])
            verification = json.loads(verification_path.read_text())
            verification["verifications"][0]["moduleCommit"] = "f" * 32
            verification_path.write_text(json.dumps(verification))

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("verification module commit mismatch", result.stderr)

    def test_rejects_missing_generated_sdk_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            verification_path = Path(environment["BSR_SDK_VERIFICATION_FILE"])
            verification = json.loads(verification_path.read_text())
            verification["verifications"].pop()
            verification_path.write_text(json.dumps(verification))

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("generated SDK verification missing", result.stderr)

    def test_cleans_manifest_temp_when_rust_temp_creation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            self.install_fake_mktemp(root)
            counter = root / "mktemp-count"
            environment["FAKE_MKTEMP_COUNTER"] = str(counter)
            environment["FAKE_MKTEMP_FAIL_ON_CALL"] = "2"
            output = root / "dist/release-manifest.json"
            original_output = b"existing manifest must survive\n"
            output.write_bytes(original_output)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.returncode, 86)
            self.assertEqual(output.read_bytes(), original_output)
            self.assertEqual(
                list((root / "dist").glob("release-manifest.json.tmp.*")), []
            )

    def test_concurrent_builders_use_unique_temporary_files_and_clean_up(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
            self.install_fake_mktemp(root)
            mktemp_log = root / "mktemp-paths"
            environment["FAKE_MKTEMP_LOG"] = str(mktemp_log)
            processes = [
                subprocess.Popen(
                    [str(root / "scripts/build_release_manifest.sh")],
                    cwd=root,
                    env=environment,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                for _ in range(4)
            ]

            results = [process.communicate(timeout=15) for process in processes]

            for process, (_, stderr) in zip(processes, results):
                self.assertEqual(process.returncode, 0, stderr)
            manifest = json.loads((root / "dist/release-manifest.json").read_text())
            self.assertEqual(manifest["bsrModuleCommit"], BASELINE_BSR_MODULE_COMMIT)
            self.assertEqual(
                manifest["consumerCompatibility"]["rust"]["bsrModuleCommit"],
                BASELINE_BSR_MODULE_COMMIT,
            )
            rust_temp_paths = [
                path
                for path in mktemp_log.read_text().splitlines()
                if ".rust." in Path(path).name
            ]
            self.assertEqual(len(rust_temp_paths), 4)
            self.assertEqual(len(set(rust_temp_paths)), 4)
            self.assertEqual(
                list((root / "dist").glob("release-manifest.json.tmp.*")), []
            )
            self.assertEqual(
                list((root / "dist").glob("release-manifest.json.rust.*")), []
            )


if __name__ == "__main__":
    unittest.main()
