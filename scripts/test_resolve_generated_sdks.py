#!/usr/bin/env python3
"""Contract tests for generated SDK pin parsing."""

from pathlib import Path
import tempfile
import unittest

from scripts.resolve_generated_sdks import parse_pins


class GeneratedSdkPinParserTests(unittest.TestCase):
    def test_accepts_revision_before_remote(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            configuration = Path(temporary_directory) / "buf.gen.yaml"
            configuration.write_text(
                """\
version: v2
plugins:
  - revision: 2
    remote: buf.build/protocolbuffers/go:v1.36.11
    out: gen/go
  - remote: buf.build/connectrpc/go:v1.20.0
    revision: 1
    out: gen/go
""",
                encoding="utf-8",
            )

            self.assertEqual(
                parse_pins(configuration),
                [
                    ("buf.build/protocolbuffers/go", "v1.36.11", 2),
                    ("buf.build/connectrpc/go", "v1.20.0", 1),
                ],
            )


if __name__ == "__main__":
    unittest.main()
