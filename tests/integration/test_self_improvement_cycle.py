from __future__ import annotations

from fastapi.testclient import TestClient
from hyoka_server.database import SessionLocal, engine
from hyoka_server.main import app
from hyoka_server.models import Base
from hyoka_server.services.autonomous import (
    claim_next_self_improvement_cycle,
    execute_self_improvement_cycle,
)
from hyoka_server.services.runs import execute_run
from hyoka_server.services.workers import claim_next_run


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _trace(trace_id: str) -> dict:
    return {
        "trace_id": trace_id,
        "agent_name": "refund-agent",
        "environment": "test",
        "input": {"role": "user", "content": "Refund my order"},
        "steps": [
            {
                "step_id": f"{trace_id}_lookup",
                "type": "tool_call",
                "tool_name": "lookup_order",
                "status": "ok",
                "latency_ms": 100,
            }
        ],
        "final_output_preview": "Refund approved after delivery check",
        "summary": {"latency_ms": 1000, "tokens_total": 500, "cost_usd": 0.001, "status": "ok"},
    }


def _execute_next_run(expected_run_id: str) -> None:
    with SessionLocal() as session:
        run = claim_next_run(session, worker_id="test-worker", lease_seconds=60)
        assert run is not None
        assert run.run_id == expected_run_id
        execute_run(session, run.run_id, worker_id="test-worker", already_claimed=True)


def _execute_next_self_improvement_cycle(expected_cycle_id: str) -> None:
    with SessionLocal() as session:
        cycle = claim_next_self_improvement_cycle(session, worker_id="test-cycle-worker", lease_seconds=60)
        assert cycle is not None
        assert cycle.cycle_id == expected_cycle_id
        execute_self_improvement_cycle(
            session,
            cycle.cycle_id,
            worker_id="test-cycle-worker",
            already_claimed=True,
        )


def test_self_improvement_cycle_worker_generates_validates_gates_and_reuses_candidate() -> None:
    client = TestClient(app)

    response = client.post("/v1/traces/batch", json=[_trace("tr_auto_1"), _trace("tr_auto_2")])
    assert response.status_code == 200
    suite_id = client.post("/v1/suites", json={"name": "auto-suite"}).json()["suite_id"]
    candidate_id = client.post(
        "/v1/candidates",
        json={
            "name": "bad-output-override",
            "targets": ["prompt"],
            "config": {
                "override_final_output": "I cannot help with that.",
                "expected_output_regex": "refund",
            },
        },
    ).json()["candidate_id"]
    run_id = client.post("/v1/runs", json={"suite_id": suite_id, "candidate_id": candidate_id, "mode": "mock"}).json()[
        "run_id"
    ]
    _execute_next_run(run_id)

    baseline = client.get(f"/v1/runs/{run_id}").json()
    assert baseline["aggregate"]["pass_rate"] == 0.0

    response = client.post(
        "/v1/self-improvement/cycles",
        json={
            "run_id": run_id,
            "target": "prompt",
            "execute_inline": False,
            "execute_validation": True,
            "promote_on_approval": True,
            "promotion_environment": "staging",
            "gate_policy": {"min_pass_rate": 1.0, "max_flaky_rate": 0.0, "required_artifacts": ["manifest"]},
        },
    )
    assert response.status_code == 200
    cycle = response.json()
    assert cycle["status"] == "queued"
    _execute_next_self_improvement_cycle(cycle["cycle_id"])

    response = client.get(f"/v1/self-improvement/cycles/{cycle['cycle_id']}")
    assert response.status_code == 200
    cycle = response.json()
    assert cycle["status"] == "completed"
    assert cycle["result"]["decision"] == "approved"
    candidate = cycle["result"]["candidates"][0]
    assert candidate["comparison"]["approved"] is True
    assert candidate["comparison"]["pass_rate_delta"] == 1.0
    assert candidate["gate_decision"] == "approved"
    assert candidate["promotion_id"]
    assert candidate["patch_artifact_id"]

    generated = client.get(f"/v1/candidates/{candidate['candidate_id']}").json()
    assert "override_final_output" not in generated["config"]
    assert any(op["op"] == "remove_mock_output_override" for op in generated["config"]["patch_operations"])

    assert cycle["worker_id"] is None
    assert cycle["execution_attempts"] == 1
