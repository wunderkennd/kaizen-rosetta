from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GO_SCRIPT = ROOT / "scripts/compile_generated_go.sh"
TS_SCRIPT = ROOT / "scripts/compile_generated_ts.sh"


class GeneratedSdkCompilationScriptTest(unittest.TestCase):
    @staticmethod
    def executable(path: Path, contents: str) -> Path:
        path.write_text(contents, encoding="utf-8")
        path.chmod(0o755)
        return path

    def run_script(
        self, script: Path, environment: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(script)],
            cwd=ROOT,
            env=os.environ | environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_go_rejects_missing_generated_tree(self) -> None:
        result = self.run_script(
            GO_SCRIPT,
            {"GENERATED_GO_DIR": "/definitely/missing/generated-go"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("generated Go tree is missing", result.stderr)

    def test_go_rejects_missing_tool(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            generated = Path(temporary_directory) / "gen"
            generated.mkdir()
            (generated / "placeholder.go").write_text("package placeholder\n")
            result = self.run_script(
                GO_SCRIPT,
                {
                    "GENERATED_GO_DIR": str(generated),
                    "GO_BIN": "/definitely/missing/go",
                },
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Go compiler is unavailable", result.stderr)

    def test_go_propagates_compiler_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            generated = directory / "gen"
            generated.mkdir()
            (generated / "placeholder.go").write_text("package placeholder\n")
            fake_go = self.executable(
                directory / "go",
                '#!/usr/bin/env bash\n[[ "$1" != "test" ]]\n',
            )
            result = self.run_script(
                GO_SCRIPT,
                {
                    "GENERATED_GO_DIR": str(generated),
                    "GO_BIN": str(fake_go),
                    "ROSETTA_GO_VERSION": "",
                },
            )
        self.assertNotEqual(result.returncode, 0)

    def test_ts_rejects_missing_generated_tree(self) -> None:
        result = self.run_script(
            TS_SCRIPT,
            {"GENERATED_TS_DIR": "/definitely/missing/generated-ts"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("generated TypeScript tree is missing", result.stderr)

    def test_ts_rejects_missing_tool(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            generated = Path(temporary_directory) / "gen"
            generated.mkdir()
            (generated / "placeholder.ts").write_text("export {};\n")
            result = self.run_script(
                TS_SCRIPT,
                {
                    "GENERATED_TS_DIR": str(generated),
                    "NPM_BIN": "/definitely/missing/npm",
                },
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("npm is unavailable", result.stderr)

    def test_ts_propagates_compiler_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            generated = directory / "gen"
            generated.mkdir()
            (generated / "placeholder.ts").write_text("export {};\n")
            fake_npm = self.executable(directory / "npm", "#!/bin/sh\nexit 0\n")
            fake_tsc = self.executable(directory / "tsc", "#!/bin/sh\nexit 23\n")
            result = self.run_script(
                TS_SCRIPT,
                {
                    "GENERATED_TS_DIR": str(generated),
                    "NPM_BIN": str(fake_npm),
                    "TSC_BIN": str(fake_tsc),
                    "ROSETTA_NODE_VERSION": "",
                    "ROSETTA_NPM_VERSION": "",
                },
            )
        self.assertEqual(result.returncode, 23)


if __name__ == "__main__":
    unittest.main()
