from __future__ import annotations

from datetime import UTC, datetime

from hyoka_server.models import CandidateRecord, TraceRecord
from hyoka_server.services.evaluators import evaluate_case


def _trace() -> TraceRecord:
    return TraceRecord(
        trace_id="tr_eval",
        project_id="default",
        schema_version="hyoka.trace.v1",
        agent_name="eval-agent",
        environment="test",
        status="ok",
        started_at=datetime.now(UTC),
        ended_at=None,
        input={"question": "hi"},
        steps=[],
        final_output_preview=None,
        summary={"latency_ms": 1, "tokens_total": 1, "cost_usd": 0.0, "status": "ok"},
        trace_metadata={},
        payload_hash="sha256:test",
        raw_payload={},
    )


def _candidate(config: dict) -> CandidateRecord:
    return CandidateRecord(
        candidate_id="cand_eval",
        project_id="default",
        name="eval-candidate",
        targets=["prompt"],
        config=config,
        candidate_metadata={},
        candidate_hash="sha256:candidate",
    )


def test_json_schema_evaluator_passes_and_fails() -> None:
    config = {
        "evaluators": [
            {
                "type": "json_schema",
                "target": "final_output",
                "schema": {"type": "object", "required": ["answer"]},
            }
        ]
    }
    passed = evaluate_case(_trace(), _candidate(config), {"final_output": {"answer": "ok"}})
    failed = evaluate_case(_trace(), _candidate(config), {"final_output": {"message": "missing"}})

    assert any(result["evaluator"] == "json_schema" and result["passed"] for result in passed)
    assert any("schema_mismatch" in result["labels"] for result in failed)
