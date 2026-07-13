import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from google.protobuf.json_format import MessageToJson, Parse
from kaizen.audience.v1.context_pb2 import AudienceContext
from workbench.v1.workbench_connect import (
    PageWorkbenchService,
    PageWorkbenchServiceASGIApplication,
    PageWorkbenchServiceClient,
)
from workbench.v1.workbench_pb2 import (
    MODULE_SOURCE_PERSONALIZED,
    OPTIMIZATION_STATUS_UNOPTIMIZED,
    RESOURCE_KIND_SERIES,
    CollectionModule,
    MediaCard,
    PageDocument,
    PageModule,
    PreviewPageRequest,
    PreviewPageResponse,
    ScenarioManifest,
    SyntheticPersonaSubject,
)


class StaticWorkbenchService(PageWorkbenchService):
    async def preview_page(self, request: PreviewPageRequest, ctx: Any) -> PreviewPageResponse:
        assert request.page_key == "home"
        assert request.synthetic_persona.persona_id == "persona-1"
        return PreviewPageResponse(
            contract_version="workbench.v1",
            scenario=ScenarioManifest(
                scenario_id="persona-1:home",
                scenario_fingerprint="a" * 64,
                audience_registry_version=request.synthetic_persona.audience_context.registry_version,
            ),
            page=PageDocument(
                page_id="home",
                modules=[
                    PageModule(
                        module_id="top-picks",
                        source=MODULE_SOURCE_PERSONALIZED,
                        collection=CollectionModule(
                            heading="Top Picks",
                            items=[
                                MediaCard(
                                    resource_id="series-1",
                                    resource_kind=RESOURCE_KIND_SERIES,
                                    title="Series One",
                                    original_position=0,
                                    final_position=0,
                                )
                            ],
                        ),
                    )
                ],
            ),
            optimization_status=OPTIMIZATION_STATUS_UNOPTIMIZED,
            correlation_id=request.request_id or "server-correlation",
        )


async def invoke_asgi(
    application: Callable[
        [dict[str, Any], Callable[[], Awaitable[dict[str, Any]]], Callable[[dict[str, Any]], Awaitable[None]]],
        Awaitable[None],
    ],
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
        "path": "/workbench.v1.PageWorkbenchService/PreviewPage",
        "raw_path": b"/workbench.v1.PageWorkbenchService/PreviewPage",
        "query_string": b"",
        "headers": [(b"host", b"testserver"), (b"content-type", b"application/json")],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    await application(scope, receive, send)
    return events


def test_preview_protojson_and_generated_connect_asgi() -> None:
    request = PreviewPageRequest(
        synthetic_persona=SyntheticPersonaSubject(
            persona_id="persona-1",
            audience_context=AudienceContext(registry_version="2026-07-12"),
        ),
        page_key="home",
        request_id="request-1",
    )
    decoded = Parse(MessageToJson(request), PreviewPageRequest())
    assert decoded == request

    service = StaticWorkbenchService()
    application = PageWorkbenchServiceASGIApplication(service)
    client = PageWorkbenchServiceClient("http://testserver")
    events = asyncio.run(invoke_asgi(application, MessageToJson(request).encode()))
    start = next(event for event in events if event["type"] == "http.response.start")
    body = b"".join(
        event.get("body", b"")
        for event in events
        if event["type"] == "http.response.body"
    )
    assert start["status"] == 200
    assert json.loads(body)["page"]["modules"][0]["collection"]["items"][0]["resourceId"] == "series-1"
    asyncio.run(client.close())
