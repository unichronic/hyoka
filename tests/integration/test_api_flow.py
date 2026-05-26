from __future__ import annotations

from fastapi.testclient import TestClient
from hyoka_server.database import SessionLocal, engine
from hyoka_server.main import app
from hyoka_server.models import Base
from hyoka_server.services.runs import execute_run
from hyoka_server.services.workers import claim_next_run


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _trace(trace_id: str, *, include_lookup: bool) -> dict:
    steps = []
    if include_lookup:
        steps.append(
            {
                "step_id": f"{trace_id}_lookup",
                "type": "tool_call",
                "tool_name": "lookup_order",
                "status": "ok",
                "latency_ms": 100,
            }
        )
    steps.append(
        {
            "step_id": f"{trace_id}_refund",
            "type": "tool_call",
            "tool_name": "issue_refund",
            "status": "ok",
            "latency_ms": 110,
        }
    )
    return {
        "trace_id": trace_id,
        "agent_name": "refund-agent",
        "environment": "test",
        "input": {"role": "user", "content": "Refund my order"},
        "steps": steps,
        "final_output_preview": "Refund issued after delivery check" if include_lookup else "Refund issued",
        "summary": {"latency_ms": 1000, "tokens_total": 500, "cost_usd": 0.001, "status": "ok"},
    }


def test_ingest_suite_run_gate_manifest_flow() -> None:
    client = TestClient(app)

    response = client.post("/v1/traces/batch", json=[_trace("tr_ok", include_lookup=True), _trace("tr_bad", include_lookup=False)])
    assert response.status_code == 200
    assert len(response.json()) == 2

    response = client.post("/v1/suites", json={"name": "support-v1"})
    assert response.status_code == 200
    suite_id = response.json()["suite_id"]

    response = client.post(
        "/v1/candidates",
        json={
            "name": "guardrail",
            "targets": ["prompt"],
            "config": {"required_tools": ["lookup_order"], "expected_output_regex": "refund"},
        },
    )
    assert response.status_code == 200
    candidate_id = response.json()["candidate_id"]

    response = client.post("/v1/runs", json={"suite_id": suite_id, "candidate_id": candidate_id, "mode": "mock"})
    assert response.status_code == 200
    run_id = response.json()["run_id"]
    assert response.json()["status"] == "queued"

    with SessionLocal() as session:
        run = claim_next_run(session, worker_id="test-worker", lease_seconds=60)
        assert run is not None
        assert run.run_id == run_id
        execute_run(session, run.run_id, worker_id="test-worker", already_claimed=True)

    response = client.get(f"/v1/runs/{run_id}")
    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "completed"
    assert run["aggregate"]["case_count"] == 2
    assert run["aggregate"]["pass_rate"] == 0.5
    assert run["manifest_id"]

    response = client.post(
        "/v1/gates/evaluate",
        json={
            "run_id": run_id,
            "policy": {
                "min_pass_rate": 0.9,
                "max_flaky_rate": 0.0,
                "block_on": ["missing_required_tool"],
                "required_artifacts": ["manifest"],
            },
        },
    )
    assert response.status_code == 200
    gate = response.json()
    assert gate["decision"] == "blocked"
    assert gate["manifest_id"]

    response = client.get(f"/v1/manifests/{run_id}")
    assert response.status_code == 200
    assert response.json()["signature"].startswith("hmac-sha256:")

    response = client.post("/v1/failures/mine", params={"run_id": run_id})
    assert response.status_code == 200
    assert response.json()
    cluster = response.json()[0]
    assert cluster["failure_type"] == "missing_required_tool"
    assert cluster["suggested_targets"] == ["tool_policy", "prompt"]
    cluster_id = cluster["cluster_id"]

    response = client.post(
        "/v1/improvements/propose",
        params={"cluster_id": cluster_id, "target": "prompt", "create_candidate": True},
    )
    assert response.status_code == 200
    proposal = response.json()
    assert proposal["candidate_id"]
    assert proposal["proposal"]["candidate_patch"]["config"]["source_failure_cluster"] == cluster_id
    assert proposal["proposal"]["candidate_patch"]["config"]["self_improvement"]["source_evidence_hash"].startswith("sha256:")
    assert "generated_at" not in proposal["proposal"]["candidate_patch"]["metadata"]

    response = client.post(
        "/v1/improvements/propose",
        params={"cluster_id": cluster_id, "target": "prompt", "create_candidate": True},
    )
    assert response.status_code == 200
    assert response.json()["candidate_id"] == proposal["candidate_id"]


def test_live_replay_requires_explicit_allowlist() -> None:
    client = TestClient(app)

    assert client.post("/v1/traces", json=_trace("tr_live", include_lookup=True)).status_code == 200
    suite_id = client.post("/v1/suites", json={"name": "live"}).json()["suite_id"]
    candidate_id = client.post(
        "/v1/candidates",
        json={
            "name": "live-candidate",
            "targets": ["prompt"],
            "config": {"replay": {"url": "http://agent-runtime.local/replay"}},
        },
    ).json()["candidate_id"]
    run_id = client.post(
        "/v1/runs",
        json={"suite_id": suite_id, "candidate_id": candidate_id, "mode": "live"},
    ).json()["run_id"]

    with SessionLocal() as session:
        run = claim_next_run(session, worker_id="test-worker", lease_seconds=60)
        assert run is not None
        execute_run(session, run.run_id, worker_id="test-worker", already_claimed=True)

    run = client.get(f"/v1/runs/{run_id}").json()
    assert run["status"] == "completed"
    assert run["aggregate"]["error_count"] == 1
    cases = client.get(f"/v1/runs/{run_id}/cases").json()
    assert cases[0]["status"] == "error"
    assert cases[0]["eval_results"][0]["labels"] == ["replay", "execution_error"]
