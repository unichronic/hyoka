from __future__ import annotations

from fastapi.testclient import TestClient
from hyoka_server.database import SessionLocal, engine
from hyoka_server.main import app
from hyoka_server.models import Base
from hyoka_server.services.workers import claim_next_run


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_run_can_only_be_claimed_once() -> None:
    client = TestClient(app)
    trace = {
        "trace_id": "tr_claim",
        "agent_name": "refund-agent",
        "input": {"role": "user", "content": "Refund"},
        "steps": [],
        "final_output_preview": "Refund queued",
        "summary": {"latency_ms": 10, "tokens_total": 1, "cost_usd": 0.0, "status": "ok"},
    }
    assert client.post("/v1/traces", json=trace).status_code == 200
    suite = client.post("/v1/suites", json={"name": "claims"}).json()
    candidate = client.post(
        "/v1/candidates",
        json={"name": "claim-candidate", "targets": ["prompt"], "config": {}},
    ).json()
    run = client.post(
        "/v1/runs",
        json={"suite_id": suite["suite_id"], "candidate_id": candidate["candidate_id"]},
    ).json()

    with SessionLocal() as session:
        first_claim = claim_next_run(session, worker_id="worker-a", lease_seconds=60)
        assert first_claim is not None
        assert first_claim.run_id == run["run_id"]

    with SessionLocal() as session:
        second_claim = claim_next_run(session, worker_id="worker-b", lease_seconds=60)
        assert second_claim is None
