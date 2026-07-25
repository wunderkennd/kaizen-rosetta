import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from google.protobuf.json_format import MessageToJson, Parse
from kaizen.audience.v1.context_pb2 import AudienceContext
from protovalidate import ValidationError, Validator
from workbench.v1.search_connect import (
    WorkbenchSearchService,
    WorkbenchSearchServiceASGIApplication,
    WorkbenchSearchServiceClient,
)
from workbench.v1.search_pb2 import (
    CONFIDENCE_BAND_HIGH,
    EXACT_MATCH_CLASS_CANONICAL_EXACT,
    LANGUAGE_HINT_ENGLISH,
    MATCHED_FIELD_CANONICAL_TITLE,
    RETRIEVAL_LANE_LEXICAL,
    RETRIEVAL_LANE_SEMANTIC,
    ROMAJI_HINT_UNLIKELY,
    ROUTING_MODE_HEURISTIC,
    ROUTING_MODE_MODEL_ACTIVE,
    ROUTING_REASON_CODE_BALANCED_DEFAULT,
    SCRIPT_HINT_LATIN,
    SEARCH_SCOPE_TITLE,
    SEARCH_STATUS_EMPTY,
    SEARCH_STATUS_OK,
    SOURCE_MODE_PRIMARY,
    AudienceFilterProvenance,
    EpisodeResource,
    LaneManifest,
    ListTitleEpisodesRequest,
    ListTitleEpisodesResponse,
    RetrievalContribution,
    RoutingManifest,
    SearchResult,
    SearchSourceManifest,
    SearchTitlesRequest,
    SearchTitlesResponse,
    SourceManifest,
    TitleSearchDetail,
)
from workbench.v1.workbench_pb2 import (
    RESOURCE_KIND_EPISODE,
    RESOURCE_KIND_MOVIE,
    RESOURCE_KIND_SERIES,
)


VALIDATOR = Validator()
SEARCH_PATH = "/workbench.v1.WorkbenchSearchService/SearchTitles"
EPISODES_PATH = "/workbench.v1.WorkbenchSearchService/ListTitleEpisodes"


def audience_context() -> AudienceContext:
    return AudienceContext(registry_version="2026-07-12")


def title_request(**changes: Any) -> SearchTitlesRequest:
    values: dict[str, Any] = {
        "query": "Frieren",
        "scope": SEARCH_SCOPE_TITLE,
        "audience_context": audience_context(),
        "limit": 10,
        "request_id": "request-1",
    }
    values.update(changes)
    return SearchTitlesRequest(**values)


def episode_request(**changes: Any) -> ListTitleEpisodesRequest:
    values: dict[str, Any] = {
        "parent_title_id": "series-1",
        "audience_context": audience_context(),
        "page_size": 25,
        "page_token": "page-1",
        "request_id": "request-2",
    }
    values.update(changes)
    return ListTitleEpisodesRequest(**values)


def routing_manifest(**changes: Any) -> RoutingManifest:
    values: dict[str, Any] = {
        "mode": ROUTING_MODE_HEURISTIC,
        "policy_id": "balanced-v1",
        "policy_version": "1",
        "language_hint": LANGUAGE_HINT_ENGLISH,
        "script_hint": SCRIPT_HINT_LATIN,
        "romaji_hint": ROMAJI_HINT_UNLIKELY,
        "confidence_band": CONFIDENCE_BAND_HIGH,
        "lexical_weight": 0.5,
        "semantic_weight": 0.5,
        "reason_codes": [ROUTING_REASON_CODE_BALANCED_DEFAULT],
    }
    values.update(changes)
    return RoutingManifest(**values)


def source_manifest() -> SearchSourceManifest:
    return SearchSourceManifest(
        source=SourceManifest(
            logical_source_id="title-catalog",
            logical_source_version="2026-07-24",
            document_manifest_version="documents-v1",
            manifest_build_id="build-1",
            mode=SOURCE_MODE_PRIMARY,
        ),
        lanes=[
            LaneManifest(
                lane=RETRIEVAL_LANE_LEXICAL,
                status=SEARCH_STATUS_OK,
                candidate_count=1,
            ),
            LaneManifest(
                lane=RETRIEVAL_LANE_SEMANTIC,
                status=SEARCH_STATUS_OK,
                candidate_count=1,
            ),
        ],
    )


def search_result(
    *,
    resource_id: str = "series-1",
    final_rank: int = 1,
    fused_score: float = 0.75,
) -> SearchResult:
    return SearchResult(
        resource_id=resource_id,
        resource_kind=RESOURCE_KIND_SERIES,
        title=TitleSearchDetail(episode_details_available=True),
        display_title="Frieren: Beyond Journey's End",
        description="An elven mage retraces a heroic journey.",
        image_url="https://example.test/frieren.jpg",
        final_rank=final_rank,
        fused_score=fused_score,
        exact_match_class=EXACT_MATCH_CLASS_CANONICAL_EXACT,
        contributions=[
            RetrievalContribution(lane=RETRIEVAL_LANE_LEXICAL, rank=1),
            RetrievalContribution(lane=RETRIEVAL_LANE_SEMANTIC, rank=2),
        ],
        matched_fields=[MATCHED_FIELD_CANONICAL_TITLE],
        audience=AudienceFilterProvenance(
            policy_id="audience-policy",
            policy_version="1",
            registry_version="2026-07-12",
        ),
    )


def title_response(
    *,
    results: list[SearchResult] | None = None,
    routing: RoutingManifest | None = None,
) -> SearchTitlesResponse:
    return SearchTitlesResponse(
        contract_version="workbench.v1",
        results=[search_result()] if results is None else results,
        routing=routing if routing is not None else routing_manifest(),
        source=source_manifest(),
        correlation_id="request-1",
    )


def episode_resource() -> EpisodeResource:
    return EpisodeResource(
        resource_id="episode-1",
        parent_title_id="series-1",
        resource_kind=RESOURCE_KIND_EPISODE,
        display_title="The Journey's End",
        season_display="Season 1",
        episode_display="Episode 1",
        image_url="https://example.test/episode-1.jpg",
        season_order=1,
        episode_order=1,
        release_order=1_696_118_400,
    )


def episode_response(
    *, episodes: list[EpisodeResource] | None = None
) -> ListTitleEpisodesResponse:
    return ListTitleEpisodesResponse(
        contract_version="workbench.v1",
        episodes=[episode_resource()] if episodes is None else episodes,
        next_page_token="page-2" if episodes is None else "",
        repository_status=SEARCH_STATUS_OK if episodes is None else SEARCH_STATUS_EMPTY,
        correlation_id="request-2",
    )


def assert_invalid(message: Any) -> None:
    with pytest.raises(ValidationError):
        VALIDATOR.validate(message)


class StaticWorkbenchSearchService(WorkbenchSearchService):
    async def search_titles(
        self, request: SearchTitlesRequest, ctx: Any
    ) -> SearchTitlesResponse:
        assert request.query == "Frieren"
        assert request.audience_context.registry_version == "2026-07-12"
        return title_response()

    async def list_title_episodes(
        self, request: ListTitleEpisodesRequest, ctx: Any
    ) -> ListTitleEpisodesResponse:
        assert request.parent_title_id == "series-1"
        assert request.audience_context.registry_version == "2026-07-12"
        return episode_response()


async def invoke_asgi(
    application: Callable[
        [
            dict[str, Any],
            Callable[[], Awaitable[dict[str, Any]]],
            Callable[[dict[str, Any]], Awaitable[None]],
        ],
        Awaitable[None],
    ],
    *,
    path: str,
    body: bytes,
) -> list[dict[str, Any]]:
    delivered = False
    events: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(event: dict[str, Any]) -> None:
        events.append(event)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [
            (b"host", b"testserver"),
            (b"content-type", b"application/json"),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    await application(scope, receive, send)
    return events


def response_body(events: list[dict[str, Any]]) -> dict[str, Any]:
    start = next(event for event in events if event["type"] == "http.response.start")
    assert start["status"] == 200
    body = b"".join(
        event.get("body", b"")
        for event in events
        if event["type"] == "http.response.body"
    )
    return json.loads(body)


def test_complete_title_request_is_valid() -> None:
    VALIDATOR.validate(title_request())


@pytest.mark.parametrize(
    "query",
    ["", " \t\n", "x" * 513],
)
def test_title_request_rejects_invalid_queries(query: str) -> None:
    assert_invalid(title_request(query=query))


@pytest.mark.parametrize("limit", [0, 51])
def test_title_request_rejects_out_of_range_limits(limit: int) -> None:
    assert_invalid(title_request(limit=limit))


def test_title_request_rejects_parent_title_id() -> None:
    assert_invalid(title_request(parent_title_id="series-1"))


def test_title_request_requires_audience_context() -> None:
    request = title_request()
    request.ClearField("audience_context")
    assert_invalid(request)


@pytest.mark.parametrize("parent_title_id", ["", " ", "x" * 257])
def test_episode_request_rejects_invalid_parent_title_ids(
    parent_title_id: str,
) -> None:
    assert_invalid(episode_request(parent_title_id=parent_title_id))


@pytest.mark.parametrize("page_size", [0, 101])
def test_episode_request_rejects_out_of_range_page_sizes(page_size: int) -> None:
    assert_invalid(episode_request(page_size=page_size))


def test_episode_request_requires_audience_context() -> None:
    request = episode_request()
    request.ClearField("audience_context")
    assert_invalid(request)


def test_search_result_requires_matching_detail() -> None:
    result = search_result()
    result.ClearField("title")
    assert_invalid(result)


def test_episode_resource_with_episode_kind_is_valid() -> None:
    VALIDATOR.validate(episode_resource())


@pytest.mark.parametrize(
    "resource_kind",
    [RESOURCE_KIND_SERIES, RESOURCE_KIND_MOVIE],
)
def test_episode_resource_rejects_non_episode_kind(resource_kind: int) -> None:
    resource = episode_resource()
    resource.resource_kind = resource_kind
    assert_invalid(resource)


def test_nonblank_audience_filter_provenance_is_valid() -> None:
    VALIDATOR.validate(search_result().audience)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("policy_id", ""),
        ("policy_id", " \t"),
        ("policy_version", ""),
        ("policy_version", "\n "),
        ("registry_version", ""),
        ("registry_version", " \r\n"),
    ],
)
def test_audience_filter_provenance_rejects_blank_identifiers(
    field_name: str, value: str
) -> None:
    provenance = search_result().audience
    setattr(provenance, field_name, value)
    assert_invalid(provenance)


def test_search_result_rejects_duplicate_contribution_lanes() -> None:
    result = search_result()
    result.contributions[1].lane = RETRIEVAL_LANE_LEXICAL
    assert_invalid(result)


def test_search_result_rejects_zero_contribution_rank() -> None:
    result = search_result()
    result.contributions[0].rank = 0
    assert_invalid(result)


@pytest.mark.parametrize("fused_score", [-0.1, float("inf"), float("-inf"), float("nan")])
def test_search_result_rejects_negative_or_nonfinite_scores(
    fused_score: float,
) -> None:
    assert_invalid(search_result(fused_score=fused_score))


@pytest.mark.parametrize(
    ("lexical_weight", "semantic_weight"),
    [(-0.1, 1.1), (1.1, -0.1), (0.4, 0.4), (0.6, 0.6)],
)
def test_routing_rejects_invalid_weights(
    lexical_weight: float, semantic_weight: float
) -> None:
    assert_invalid(
        routing_manifest(
            lexical_weight=lexical_weight,
            semantic_weight=semantic_weight,
        )
    )


@pytest.mark.parametrize(
    ("model_id", "model_version"),
    [("", ""), ("router", ""), ("", "1")],
)
def test_model_active_routing_requires_model_identity(
    model_id: str, model_version: str
) -> None:
    routing = routing_manifest(mode=ROUTING_MODE_MODEL_ACTIVE)
    if model_id:
        routing.model_id = model_id
    if model_version:
        routing.model_version = model_version
    assert_invalid(routing)


def test_model_active_routing_accepts_complete_model_identity() -> None:
    VALIDATOR.validate(
        routing_manifest(
            mode=ROUTING_MODE_MODEL_ACTIVE,
            model_id="router",
            model_version="1",
        )
    )


def test_heuristic_routing_rejects_model_identity() -> None:
    assert_invalid(
        routing_manifest(
            model_id="router",
            model_version="1",
        )
    )


def test_search_response_rejects_duplicate_final_ranks() -> None:
    assert_invalid(
        title_response(
            results=[
                search_result(resource_id="series-1", final_rank=1),
                search_result(resource_id="series-2", final_rank=1),
            ]
        )
    )


def test_search_response_rejects_noncontiguous_final_ranks() -> None:
    assert_invalid(
        title_response(
            results=[
                search_result(resource_id="series-1", final_rank=1),
                search_result(resource_id="series-2", final_rank=3),
            ]
        )
    )


def test_empty_search_results_and_episode_pages_are_valid() -> None:
    VALIDATOR.validate(title_response(results=[]))
    VALIDATOR.validate(episode_response(episodes=[]))


def assert_json_and_binary_round_trip(message: Any) -> None:
    VALIDATOR.validate(message)
    json_decoded = Parse(MessageToJson(message), type(message)())
    assert json_decoded == message
    binary_decoded = type(message).FromString(message.SerializeToString())
    assert binary_decoded == message


def test_title_messages_round_trip_through_protojson_and_binary() -> None:
    assert_json_and_binary_round_trip(title_request())
    assert_json_and_binary_round_trip(title_response())


def test_episode_messages_round_trip_through_protojson_and_binary() -> None:
    assert_json_and_binary_round_trip(episode_request())
    assert_json_and_binary_round_trip(episode_response())


async def exercise_generated_connect_asgi() -> tuple[dict[str, Any], dict[str, Any]]:
    application = WorkbenchSearchServiceASGIApplication(StaticWorkbenchSearchService())
    client = WorkbenchSearchServiceClient("http://testserver")
    try:
        assert isinstance(client, WorkbenchSearchServiceClient)
        title_events = await invoke_asgi(
            application,
            path=SEARCH_PATH,
            body=MessageToJson(title_request()).encode(),
        )
        episode_events = await invoke_asgi(
            application,
            path=EPISODES_PATH,
            body=MessageToJson(episode_request()).encode(),
        )
        return response_body(title_events), response_body(episode_events)
    finally:
        await client.close()


def test_generated_connect_asgi_endpoints_and_client_lifecycle() -> None:
    title_body, episode_body = asyncio.run(exercise_generated_connect_asgi())

    assert title_body == json.loads(MessageToJson(title_response()))
    assert episode_body == json.loads(MessageToJson(episode_response()))

    result = title_body["results"][0]
    assert result["resourceId"] == "series-1"
    assert result["title"]["episodeDetailsAvailable"] is True
    assert result["contributions"][0]["lane"] == "RETRIEVAL_LANE_LEXICAL"
    assert title_body["routing"]["mode"] == "ROUTING_MODE_HEURISTIC"
    assert title_body["correlationId"] == "request-1"

    episode = episode_body["episodes"][0]
    assert episode["resourceId"] == "episode-1"
    assert episode["parentTitleId"] == "series-1"
    assert episode["episodeDisplay"] == "Episode 1"
    assert episode_body["repositoryStatus"] == "SEARCH_STATUS_OK"
