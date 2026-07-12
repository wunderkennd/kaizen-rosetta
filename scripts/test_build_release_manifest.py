#!/usr/bin/env python3
"""Contract tests for the deterministic release-manifest builder."""

from pathlib import Path
import json
import os
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
DESCRIPTOR_SHA256 = "a" * 64
PINNED_GENERATORS = """\
version: v2
plugins:
  - remote: buf.build/protocolbuffers/go:v1.36.11
    revision: 1
    out: gen/go
  - remote: buf.build/connectrpc/es:v1.6.1
    revision: 2
    out: gen/ts
"""
RELEASE_SOURCE_ERROR = "release sources must match the recorded Git commit"


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
        (dist / "rosetta-descriptor.sha256").write_text(
            f"{descriptor_digest}\n" if descriptor_digest else ""
        )
        bin_directory = directory / "bin"
        bin_directory.mkdir()
        fake_buf = bin_directory / "buf"
        fake_buf.write_text("#!/usr/bin/env bash\nprintf '%s\\n' '1.66.0'\n")
        fake_buf.chmod(0o755)

        environment = {
            **os.environ,
            "PATH": f"{bin_directory}{os.pathsep}{os.environ['PATH']}",
            "BSR_MODULE_COMMIT": BASELINE_BSR_MODULE_COMMIT,
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
            "buf.build/connectrpc/es:v1.6.1", "buf.build/connectrpc/es"
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, buf_gen=unversioned_generator)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("generator remote must pin an explicit version", result.stderr)

    def test_rejects_a_mutable_generator_version(self) -> None:
        mutable_generator = PINNED_GENERATORS.replace("v1.6.1", "latest")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, buf_gen=mutable_generator)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("generator remote must pin an explicit version", result.stderr)

    def test_rejects_a_malformed_generator_version(self) -> None:
        malformed_generator = PINNED_GENERATORS.replace("v1.6.1", "v1latest")
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
        missing_revision = PINNED_GENERATORS.replace("    revision: 2\n", "")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, buf_gen=missing_revision)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("generator remote must pin an explicit revision", result.stderr)

    def test_rejects_a_zero_generator_revision(self) -> None:
        zero_revision = PINNED_GENERATORS.replace("    revision: 2\n", "    revision: 0\n")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, buf_gen=zero_revision)

            result = self.run_builder(root, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("generator revision must be positive", result.stderr)

    def test_rejects_duplicate_generator_names(self) -> None:
        duplicate_generator = PINNED_GENERATORS.replace(
            "buf.build/connectrpc/es:v1.6.1",
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
            "  - remote: buf.build/connectrpc/es:v1.6.1\n    revision: 2\n",
            "  - revision: 2\n    remote: buf.build/connectrpc/es:v1.6.1\n",
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root, buf_gen=reordered_generator)

            result = self.run_builder(root, environment)

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((root / "dist/release-manifest.json").read_text())
            self.assertIn(
                {
                    "name": "buf.build/connectrpc/es",
                    "revision": 2,
                    "version": "v1.6.1",
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
                "descriptorSha256": DESCRIPTOR_SHA256,
                "generatorPinsDocument": "docs/generator-pins.md",
                "generators": [
                    {
                        "name": "buf.build/bufbuild/es",
                        "revision": 1,
                        "version": "v2.12.1",
                    },
                    {
                        "name": "buf.build/connectrpc/es",
                        "revision": 2,
                        "version": "v1.6.1",
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
                "gitCommit": git_commit,
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

    def test_concurrent_builders_use_unique_temporary_files_and_clean_up(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, environment = self.make_project(root)
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
                list((root / "dist").glob("release-manifest.json.tmp.*")), []
            )


if __name__ == "__main__":
    unittest.main()
