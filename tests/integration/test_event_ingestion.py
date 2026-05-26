from __future__ import annotations

from fastapi.testclient import TestClient
from hyoka_server.database import engine
from hyoka_server.main import app
from hyoka_server.models import Base


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_generic_events_build_canonical_trace_and_deduplicate() -> None:
    client = TestClient(app)
    events = [
        {
            "event_id": "evt_start",
            "trace_id": "tr_generic",
            "type": "trace_start",
            "source": "hyoka_exposition",
            "service_name": "checkout-api",
            "agent_name": "refund-agent",
            "environment": "test",
            "input": {"role": "user", "content": "Refund order A123"},
            "labels": {"service": "checkout-api", "version": "2026.05.23"},
        },
        {
            "event_id": "evt_tool",
            "trace_id": "tr_generic",
            "type": "tool_call",
            "name": "lookup_order",
            "input": {"order_id": "A123"},
            "output": {"status": "delivered"},
            "duration_ms": 42,
            "attributes": {"tool_name": "lookup_order"},
            "labels": {"service": "checkout-api"},
        },
        {
            "event_id": "evt_end",
            "trace_id": "tr_generic",
            "type": "trace_end",
            "output": "Refund approved after checking delivery.",
            "duration_ms": 100,
        },
    ]

    response = client.post("/v1/events/batch", json=events)
    assert response.status_code == 200
    trace = response.json()[0]
    assert trace["trace_id"] == "tr_generic"
    assert trace["agent_name"] == "refund-agent"
    assert trace["summary"]["latency_ms"] == 100
    assert trace["final_output_preview"] == "Refund approved after checking delivery."
    assert len(trace["steps"]) == 1
    assert trace["steps"][0]["tool_name"] == "lookup_order"
    assert trace["metadata"]["labels"]["version"] == "2026.05.23"

    response = client.post("/v1/events/batch", json=events)
    assert response.status_code == 200
    trace = response.json()[0]
    assert len(trace["steps"]) == 1


def test_generic_events_accept_trace_updates_after_database_round_trip() -> None:
    client = TestClient(app)

    start = {
        "event_id": "evt_split_start",
        "trace_id": "tr_split_batches",
        "type": "trace_start",
        "agent_name": "swish-support-agent",
        "environment": "test",
        "timestamp": "2026-05-24T10:00:00Z",
        "input": {"complaint": "fries were cold"},
    }
    tool = {
        "event_id": "evt_split_tool",
        "trace_id": "tr_split_batches",
        "type": "tool_call",
        "name": "dependency.order_details",
        "timestamp": "2026-05-24T10:00:01Z",
        "input": {"order_id": "ORD001"},
        "output": {"total_amount": 478},
        "duration_ms": 25,
    }
    end = {
        "event_id": "evt_split_end",
        "trace_id": "tr_split_batches",
        "type": "trace_end",
        "timestamp": "2026-05-24T10:00:02Z",
        "output": {"action": "info"},
        "duration_ms": 2000,
    }

    assert client.post("/v1/events/batch", json=[start]).status_code == 200
    assert client.post("/v1/events/batch", json=[tool]).status_code == 200
    response = client.post("/v1/events/batch", json=[end])

    assert response.status_code == 200
    trace = response.json()[0]
    assert trace["trace_id"] == "tr_split_batches"
    assert trace["summary"]["latency_ms"] == 2000
    assert trace["steps"][0]["name"] == "dependency.order_details"
    assert trace["final_output_preview"] == '{"action":"info"}'
