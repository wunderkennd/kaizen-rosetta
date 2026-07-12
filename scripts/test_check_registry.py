from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_registry.py"
PRODUCTION = ROOT / "registry/audience/v1/attributes.textproto"


class RegistryGateTest(unittest.TestCase):
    def run_gate(self, contents: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            registry = Path(temporary_directory) / "attributes.textproto"
            registry.write_text(contents, encoding="utf-8")
            return subprocess.run(
                [str(SCRIPT), "--registry", str(registry)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

    def assert_rejected(self, contents: str, message: str) -> None:
        result = self.run_gate(contents)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(message, result.stderr)

    def test_accepts_the_checked_in_production_registry(self) -> None:
        result = self.run_gate(PRODUCTION.read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_malformed_textproto(self) -> None:
        self.assert_rejected("not valid textproto {", "registry failed schema parsing")

    def test_rejects_wrong_version(self) -> None:
        contents = PRODUCTION.read_text(encoding="utf-8").replace(
            'version: "2026-07-12"', 'version: "2026-07-11"', 1
        )
        self.assert_rejected(contents, "registry version must be 2026-07-12")

    def test_rejects_a_duplicate_key(self) -> None:
        contents = PRODUCTION.read_text(encoding="utf-8")
        first_definition = contents[contents.index("definitions {") : contents.index("\ndefinitions {", contents.index("definitions {") + 1)]
        self.assert_rejected(
            contents + first_definition + "\n",
            "registry failed schema parsing or validation",
        )

    def test_rejects_a_ninth_key(self) -> None:
        contents = PRODUCTION.read_text(encoding="utf-8")
        first_definition = contents[contents.index("definitions {") : contents.index("\ndefinitions {", contents.index("definitions {") + 1)]
        ninth = first_definition.replace('key: "country_code"', 'key: "ninth_key"')
        self.assert_rejected(contents + ninth + "\n", "exactly 8 definitions")

    def test_rejects_missing_required_metadata(self) -> None:
        contents = PRODUCTION.read_text(encoding="utf-8").replace(
            '  owner: "identity"\n', "", 1
        )
        self.assert_rejected(contents, "registry failed schema parsing or validation")

    def test_rejects_type_operator_policy_mismatch(self) -> None:
        contents = PRODUCTION.read_text(encoding="utf-8").replace(
            "  value_type: AUDIENCE_VALUE_TYPE_INT64",
            "  value_type: AUDIENCE_VALUE_TYPE_STRING",
            1,
        )
        self.assert_rejected(contents, "type/operator policy mismatch for account_age_days")


if __name__ == "__main__":
    unittest.main()
