from __future__ import annotations

from fastapi.testclient import TestClient
from hyoka_server.database import engine
from hyoka_server.main import app
from hyoka_server.models import Base
from hyoka_server.settings import get_settings


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def teardown_function() -> None:
    get_settings.cache_clear()


def _trace(trace_id: str = "tr_sec") -> dict:
    return {
        "trace_id": trace_id,
        "agent_name": "security-agent",
        "input": {"message": "hello"},
        "steps": [],
        "final_output_preview": "ok",
        "summary": {"latency_ms": 1, "tokens_total": 1, "cost_usd": 0.0, "status": "ok"},
    }


def test_static_project_key_enforces_scope(monkeypatch) -> None:
    monkeypatch.setenv("HYOKA_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("HYOKA_API_KEYS", "tenant-a:tenant-key:read|write")
    get_settings.cache_clear()
    client = TestClient(app)

    assert client.post("/v1/traces", json=_trace()).status_code == 401

    response = client.post("/v1/traces", json=_trace(), headers={"X-Hyoka-Api-Key": "tenant-key"})
    assert response.status_code == 200
    assert response.json()["project_id"] == "tenant-a"

    response = client.get(
        "/v1/traces",
        params={"project_id": "tenant-b"},
        headers={"X-Hyoka-Api-Key": "tenant-key"},
    )
    assert response.status_code == 403


def test_db_api_key_lifecycle(monkeypatch) -> None:
    monkeypatch.setenv("HYOKA_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("HYOKA_API_KEYS", "admin-secret")
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.post(
        "/v1/api-keys",
        json={"project_id": "tenant-b", "name": "ci", "scopes": ["read", "write"]},
        headers={"X-Hyoka-Api-Key": "admin-secret"},
    )
    assert response.status_code == 200
    created = response.json()
    secret = created["secret"]

    response = client.post("/v1/traces", json=_trace("tr_key"), headers={"X-Hyoka-Api-Key": secret})
    assert response.status_code == 200
    assert response.json()["project_id"] == "tenant-b"

    response = client.get("/v1/audit-events", params={"project_id": "tenant-b"}, headers={"X-Hyoka-Api-Key": "admin-secret"})
    assert response.status_code == 200
    assert any(event["action"] == "trace.ingest" for event in response.json())

    response = client.delete(f"/v1/api-keys/{created['key_id']}", headers={"X-Hyoka-Api-Key": "admin-secret"})
    assert response.status_code == 200

    response = client.get("/v1/traces", headers={"X-Hyoka-Api-Key": secret})
    assert response.status_code == 401
