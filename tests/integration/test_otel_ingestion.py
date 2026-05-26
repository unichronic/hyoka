from __future__ import annotations

from fastapi.testclient import TestClient
from hyoka_server.database import engine
from hyoka_server.main import app
from hyoka_server.models import Base


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_otlp_json_genai_span_ingestion() -> None:
    client = TestClient(app)
    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "agent-api"}},
                        {"key": "deployment.environment.name", "value": {"stringValue": "test"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "otel-test"},
                        "spans": [
                            {
                                "traceId": "0123456789abcdef0123456789abcdef",
                                "spanId": "1111111111111111",
                                "name": "openai.chat",
                                "startTimeUnixNano": "1710000000000000000",
                                "endTimeUnixNano": "1710000000500000000",
                                "attributes": [
                                    {"key": "gen_ai.operation.name", "value": {"stringValue": "chat"}},
                                    {"key": "gen_ai.provider.name", "value": {"stringValue": "openai"}},
                                    {"key": "gen_ai.request.model", "value": {"stringValue": "gpt-test"}},
                                    {"key": "gen_ai.usage.input_tokens", "value": {"intValue": "12"}},
                                    {"key": "gen_ai.usage.output_tokens", "value": {"intValue": "7"}},
                                    {"key": "input.value", "value": {"stringValue": "{\"question\":\"hi\"}"}},
                                    {"key": "output.value", "value": {"stringValue": "hello"}},
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }

    response = client.post("/v1/otel/v1/traces", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["ingested_events"] == 1
    trace = body["traces"][0]
    assert trace["trace_id"] == "otel_0123456789abcdef0123456789abcdef"
    assert trace["agent_name"] == "agent-api"
    assert trace["steps"][0]["type"] == "llm_call"
    assert trace["steps"][0]["model"] == "gpt-test"
    assert trace["summary"]["tokens_total"] == 19
