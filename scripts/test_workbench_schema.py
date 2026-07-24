from pathlib import Path
import subprocess
import tempfile
from typing import Optional
import unittest

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory


ROOT = Path(__file__).resolve().parents[1]
SEARCH_ENUMS = {
    "SearchScope": [
        "SEARCH_SCOPE_UNSPECIFIED",
        "SEARCH_SCOPE_TITLE",
        "SEARCH_SCOPE_EPISODE",
    ],
    "RetrievalLane": [
        "RETRIEVAL_LANE_UNSPECIFIED",
        "RETRIEVAL_LANE_LEXICAL",
        "RETRIEVAL_LANE_SEMANTIC",
    ],
    "RoutingMode": [
        "ROUTING_MODE_UNSPECIFIED",
        "ROUTING_MODE_DISABLED",
        "ROUTING_MODE_HEURISTIC",
        "ROUTING_MODE_MODEL_SHADOW",
        "ROUTING_MODE_MODEL_ACTIVE",
    ],
}
SEARCH_MESSAGES = {
    "SearchTitlesRequest": [
        "query",
        "scope",
        "audience_context",
        "limit",
        "request_id",
        "parent_title_id",
    ],
    "SearchTitlesResponse": [
        "contract_version",
        "results",
        "routing",
        "source",
        "warnings",
        "correlation_id",
    ],
    "ListTitleEpisodesRequest": [
        "parent_title_id",
        "audience_context",
        "page_size",
        "page_token",
        "request_id",
    ],
    "ListTitleEpisodesResponse": [
        "contract_version",
        "episodes",
        "next_page_token",
        "repository_status",
        "warnings",
        "correlation_id",
    ],
}
FORBIDDEN_FIELD_NAMES = {
    "sql",
    "filter_expression",
    "table",
    "index",
    "endpoint",
    "credential",
    "embedding",
    "logit",
    "query_plan",
    "native_score",
    "provider_payload",
}


def build_descriptor_set() -> descriptor_pb2.FileDescriptorSet:
    with tempfile.NamedTemporaryFile(suffix=".binpb") as output:
        subprocess.run(
            ["buf", "build", "--as-file-descriptor-set", "-o", output.name],
            cwd=ROOT,
            check=True,
        )
        return descriptor_pb2.FileDescriptorSet.FromString(
            Path(output.name).read_bytes()
        )


def find_file(
    image: descriptor_pb2.FileDescriptorSet, name: str
) -> Optional[descriptor_pb2.FileDescriptorProto]:
    return next((file for file in image.file if file.name == name), None)


def build_descriptor_pool(
    image: descriptor_pb2.FileDescriptorSet,
) -> descriptor_pool.DescriptorPool:
    pool = descriptor_pool.DescriptorPool()
    pending = list(image.file)
    while pending:
        deferred = []
        for file in pending:
            try:
                pool.AddSerializedFile(file.SerializeToString())
            except TypeError:
                deferred.append(file)
        if len(deferred) == len(pending):
            missing = ", ".join(file.name for file in deferred)
            raise AssertionError(f"unable to load descriptor dependencies for: {missing}")
        pending = deferred
    return pool


def extension_value(options, pool: descriptor_pool.DescriptorPool, name: str):
    extension = pool.FindExtensionByName(name)
    options_descriptor = pool.FindMessageTypeByName(
        extension.containing_type.full_name
    )
    options_class = message_factory.GetMessageClass(options_descriptor)
    dynamic_options = options_class.FromString(options.SerializeToString())
    return dynamic_options.Extensions[extension]


def cel_expressions(constraints) -> dict[str, str]:
    return {rule.id: rule.expression for rule in constraints.cel}


class WorkbenchSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.image = build_descriptor_set()

    def test_preview_tracer_descriptor(self) -> None:
        schema = find_file(self.image, "workbench/v1/workbench.proto")
        self.assertIsNotNone(schema)
        assert schema is not None
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


class WorkbenchSearchSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.image = build_descriptor_set()
        cls.pool = build_descriptor_pool(cls.image)

    def search_schema(self) -> descriptor_pb2.FileDescriptorProto:
        schema = find_file(self.image, "workbench/v1/search.proto")
        self.assertIsNotNone(schema, "workbench/v1/search.proto is missing")
        assert schema is not None
        return schema

    def test_search_service_and_dependencies(self) -> None:
        schema = self.search_schema()
        self.assertEqual(schema.package, "workbench.v1")
        self.assertEqual(
            list(schema.dependency),
            [
                "buf/validate/validate.proto",
                "kaizen/audience/v1/context.proto",
                "workbench/v1/workbench.proto",
            ],
        )
        service = next(
            (item for item in schema.service if item.name == "WorkbenchSearchService"),
            None,
        )
        self.assertIsNotNone(service)
        assert service is not None
        self.assertEqual(
            [method.name for method in service.method],
            ["SearchTitles", "ListTitleEpisodes"],
        )

    def test_search_enum_vocabularies(self) -> None:
        schema = self.search_schema()
        enums = {enum.name: enum for enum in schema.enum_type}
        for name, expected_values in SEARCH_ENUMS.items():
            self.assertIn(name, enums)
            self.assertEqual(
                [value.name for value in enums[name].value],
                expected_values,
            )

    def test_search_message_fields(self) -> None:
        schema = self.search_schema()
        messages = {message.name: message for message in schema.message_type}
        for name, expected_fields in SEARCH_MESSAGES.items():
            self.assertIn(name, messages)
            self.assertEqual(
                [field.name for field in messages[name].field],
                expected_fields,
            )

    def test_search_result_detail_is_required(self) -> None:
        schema = self.search_schema()
        result = next(
            message for message in schema.message_type if message.name == "SearchResult"
        )
        detail_index = next(
            index for index, oneof in enumerate(result.oneof_decl) if oneof.name == "detail"
        )
        self.assertEqual(
            [
                field.name
                for field in result.field
                if field.HasField("oneof_index") and field.oneof_index == detail_index
            ],
            ["title", "episode"],
        )
        constraints = extension_value(
            result.oneof_decl[detail_index].options,
            self.pool,
            "buf.validate.oneof",
        )
        self.assertTrue(constraints.required)

    def test_search_validation_cel_rules(self) -> None:
        schema = self.search_schema()
        messages = {message.name: message for message in schema.message_type}

        request_rules = cel_expressions(
            extension_value(
                messages["SearchTitlesRequest"].options,
                self.pool,
                "buf.validate.message",
            )
        )
        self.assertEqual(
            request_rules["search_titles_request.title_forbids_parent"],
            "this.scope != 1 || !has(this.parent_title_id)",
        )

        response_rules = cel_expressions(
            extension_value(
                messages["SearchTitlesResponse"].options,
                self.pool,
                "buf.validate.message",
            )
        )
        self.assertEqual(
            response_rules,
            {
                "search_titles_response.unique_final_ranks": (
                    "this.results.map(result, result.final_rank).unique()"
                ),
                "search_titles_response.contiguous_final_ranks": (
                    "this.results.all(result, "
                    "result.final_rank <= uint(this.results.size()))"
                ),
            },
        )

        contributions = next(
            field
            for field in messages["SearchResult"].field
            if field.name == "contributions"
        )
        contribution_rules = cel_expressions(
            extension_value(
                contributions.options,
                self.pool,
                "buf.validate.field",
            )
        )
        self.assertEqual(
            contribution_rules["search_result.unique_contribution_lanes"],
            "this.map(contribution, contribution.lane).unique()",
        )

        routing_rules = cel_expressions(
            extension_value(
                messages["RoutingManifest"].options,
                self.pool,
                "buf.validate.message",
            )
        )
        self.assertEqual(
            routing_rules,
            {
                "routing_manifest.normalized_weights": (
                    "this.lexical_weight + this.semantic_weight >= 0.999999999 "
                    "&& this.lexical_weight + this.semantic_weight <= 1.000000001"
                ),
                "routing_manifest.model_identity_presence_agrees": (
                    "has(this.model_id) == has(this.model_version)"
                ),
                "routing_manifest.model_identity_matches_mode": (
                    "((this.mode == 3 || this.mode == 4) && has(this.model_id)) || "
                    "((this.mode != 3 && this.mode != 4) && "
                    "!has(this.model_id))"
                ),
            },
        )

    def test_search_wire_surface_omits_provider_details(self) -> None:
        schema = self.search_schema()
        for message in schema.message_type:
            for field in message.field:
                for forbidden in FORBIDDEN_FIELD_NAMES:
                    self.assertNotIn(
                        forbidden,
                        field.name.lower(),
                        f"{message.name}.{field.name} exposes {forbidden}",
                    )


if __name__ == "__main__":
    unittest.main()
