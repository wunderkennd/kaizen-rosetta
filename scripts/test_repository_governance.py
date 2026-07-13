#!/usr/bin/env python3
"""Repository policy tests for release ownership and immutable CI dependencies."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RepositoryGovernanceTests(unittest.TestCase):
    def test_codeowners_covers_all_schema_and_lock_sources(self) -> None:
        codeowners = (ROOT / ".github/CODEOWNERS").read_text()
        for pattern in ("/proto/", "/buf.lock"):
            with self.subTest(pattern=pattern):
                self.assertRegex(
                    codeowners,
                    rf"(?m)^{re.escape(pattern)}\s+@wunderkennd$",
                )

    def test_ci_actions_are_immutable_and_version_documented(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text().splitlines()
        action_lines = [
            (index, line)
            for index, line in enumerate(workflow)
            if re.search(r"\buses:\s*[^\s]+@", line)
        ]
        self.assertTrue(action_lines)
        for index, line in action_lines:
            with self.subTest(line=line.strip()):
                self.assertRegex(line, r"@([0-9a-f]{40}|[0-9a-f]{64})\s*$")
                self.assertGreater(index, 0)
                self.assertRegex(workflow[index - 1], r"^\s*# .+ v[0-9]")

    def test_buf_token_is_not_job_scoped(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        verify_job = workflow.split("  verify:\n", 1)[1]
        job_before_steps = verify_job.split("    steps:\n", 1)[0]
        self.assertNotIn("BUF_TOKEN", job_before_steps)


if __name__ == "__main__":
    unittest.main()
