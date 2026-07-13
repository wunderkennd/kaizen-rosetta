from pathlib import Path
import subprocess
import tempfile
import unittest

from google.protobuf import descriptor_pb2


ROOT = Path(__file__).resolve().parents[1]


class WorkbenchSchemaTests(unittest.TestCase):
    def test_preview_tracer_descriptor(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".binpb") as output:
            subprocess.run(
                ["buf", "build", "--as-file-descriptor-set", "-o", output.name],
                cwd=ROOT,
                check=True,
            )
            image = descriptor_pb2.FileDescriptorSet.FromString(
                Path(output.name).read_bytes()
            )

        schema = next(
            file for file in image.file if file.name == "workbench/v1/workbench.proto"
        )
        self.assertEqual(schema.package, "workbench.v1")
        service = next(item for item in schema.service if item.name == "PageWorkbenchService")
        self.assertEqual([method.name for method in service.method], ["PreviewPage"])
        request = next(item for item in schema.message_type if item.name == "PreviewPageRequest")
        self.assertEqual(
            [field.name for field in request.field],
            ["synthetic_persona", "page_key", "request_id"],
        )
        response = next(item for item in schema.message_type if item.name == "PreviewPageResponse")
        self.assertEqual(
            [field.name for field in response.field],
            [
                "contract_version",
                "scenario",
                "page",
                "optimization_status",
                "warnings",
                "correlation_id",
            ],
        )


if __name__ == "__main__":
    unittest.main()
