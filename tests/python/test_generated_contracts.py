import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from google.protobuf.empty_pb2 import Empty
from google.protobuf.json_format import MessageToJson, Parse
from google.protobuf.message import Message

from experimentation.management.v1.management_service_connect import (
    ExperimentManagementService,
    ExperimentManagementServiceASGIApplication,
    ExperimentManagementServiceClient,
)
from experimentation.management.v1.management_service_pb2 import (
    TriggerSurrogateRecalibrationRequest,
)
from kaizen.audience.v1.expression_pb2 import (
    AllExpression,
    AudienceExpression,
    AudiencePredicate,
)
from kaizen.audience.v1.operator_pb2 import (
    AUDIENCE_OPERATOR_EQUALS,
    AUDIENCE_OPERATOR_GREATER_THAN_OR_EQUALS,
)
from kaizen.audience.v1.value_pb2 import AudienceValue


def test_audience_value_oneof_round_trips_through_google_protojson() -> None:
    value = AudienceValue(string_value="premium")

    assert isinstance(value, Message)
    assert value.WhichOneof("kind") == "string_value"

    encoded = MessageToJson(value)
    assert json.loads(encoded) == {"stringValue": "premium"}

    decoded = Parse(encoded, AudienceValue())
    assert decoded == value
    assert decoded.WhichOneof("kind") == "string_value"


def test_recursive_all_expression_round_trips_through_google_protojson() -> None:
    expression = AudienceExpression(
        all=AllExpression(
            expressions=[
                AudienceExpression(
                    predicate=AudiencePredicate(
                        attribute_key="country_code",
                        operator=AUDIENCE_OPERATOR_EQUALS,
                        values=[AudienceValue(string_value="US")],
                    )
                ),
                AudienceExpression(
                    predicate=AudiencePredicate(
                        attribute_key="account_age_days",
                        operator=AUDIENCE_OPERATOR_GREATER_THAN_OR_EQUALS,
                        values=[AudienceValue(int64_value=30)],
                    )
                ),
            ]
        )
    )

    encoded = MessageToJson(expression)
    assert json.loads(encoded) == {
        "all": {
            "expressions": [
                {
                    "predicate": {
                        "attributeKey": "country_code",
                        "operator": "AUDIENCE_OPERATOR_EQUALS",
                        "values": [{"stringValue": "US"}],
                    }
                },
                {
                    "predicate": {
                        "attributeKey": "account_age_days",
                        "operator": "AUDIENCE_OPERATOR_GREATER_THAN_OR_EQUALS",
                        "values": [{"int64Value": "30"}],
                    }
                },
            ]
        }
    }

    decoded = Parse(encoded, AudienceExpression())
    assert decoded == expression
    assert decoded.WhichOneof("node") == "all"
    assert len(decoded.all.expressions) == 2

    country, account_age = (
        child.predicate for child in decoded.all.expressions
    )
    assert country.attribute_key == "country_code"
    assert country.operator == AUDIENCE_OPERATOR_EQUALS
    assert country.values[0].WhichOneof("kind") == "string_value"
    assert country.values[0].string_value == "US"
    assert account_age.attribute_key == "account_age_days"
    assert account_age.operator == AUDIENCE_OPERATOR_GREATER_THAN_OR_EQUALS
    assert account_age.values[0].WhichOneof("kind") == "int64_value"
    assert account_age.values[0].int64_value == 30


class _EmptyExperimentManagementService(ExperimentManagementService):
    def __init__(self) -> None:
        self.received_requests: list[TriggerSurrogateRecalibrationRequest] = []

    async def trigger_surrogate_recalibration(
        self,
        request: TriggerSurrogateRecalibrationRequest,
        ctx: Any,
    ) -> Empty:
        assert isinstance(request, TriggerSurrogateRecalibrationRequest)
        assert request.model_id == "model-123"
        self.received_requests.append(request)
        return Empty()


async def _invoke_asgi(
    application: Callable[
        [dict[str, Any], Callable[[], Awaitable[dict[str, Any]]], Callable[[dict[str, Any]], Awaitable[None]]],
        Awaitable[None],
    ],
    *,
    path: str,
    body: bytes,
) -> list[dict[str, Any]]:
    request_delivered = False
    events: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal request_delivered
        if request_delivered:
            return {"type": "http.disconnect"}
        request_delivered = True
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
            (b"accept", b"application/json"),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    await application(scope, receive, send)
    return events


def test_generated_connect_interfaces_and_json_asgi_request() -> None:
    service = _EmptyExperimentManagementService()
    application = ExperimentManagementServiceASGIApplication(service)
    client = ExperimentManagementServiceClient("http://testserver")

    assert _EmptyExperimentManagementService.__mro__[1] is ExperimentManagementService
    assert callable(application)
    assert isinstance(client, ExperimentManagementServiceClient)

    path = (
        "/experimentation.management.v1.ExperimentManagementService/"
        "TriggerSurrogateRecalibration"
    )
    events = asyncio.run(
        _invoke_asgi(
            application,
            path=path,
            body=b'{"modelId":"model-123"}',
        )
    )

    response_start = next(event for event in events if event["type"] == "http.response.start")
    response_body = b"".join(
        event.get("body", b"")
        for event in events
        if event["type"] == "http.response.body"
    )
    headers = dict(response_start["headers"])

    assert response_start["status"] == 200
    assert headers[b"content-type"].startswith(b"application/json")
    assert json.loads(response_body) == {}
    assert len(service.received_requests) == 1
    assert isinstance(
        service.received_requests[0],
        TriggerSurrogateRecalibrationRequest,
    )
    assert service.received_requests[0].model_id == "model-123"
    asyncio.run(client.close())
