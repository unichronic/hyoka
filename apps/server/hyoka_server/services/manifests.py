from __future__ import annotations

from typing import Any

from hyoka_schemas.hashing import content_hash, sign_hmac
from hyoka_schemas.ids import new_id
from hyoka_server.models import (
    CandidateRecord,
    ManifestRecordModel,
    RunCaseRecord,
    RunRecord,
    SuiteRecord,
)
from hyoka_server.services.artifacts import create_artifact
from hyoka_server.settings import get_settings
from sqlalchemy.orm import Session


def build_manifest(
    session: Session,
    *,
    run: RunRecord,
    suite: SuiteRecord,
    candidate: CandidateRecord,
    decision: str = "needs_review",
    gate_policy: dict[str, Any] | None = None,
) -> ManifestRecordModel:
    cases = (
        session.query(RunCaseRecord)
        .filter(RunCaseRecord.run_id == run.run_id)
        .order_by(RunCaseRecord.id.asc())
        .all()
    )
    replay_output = [
        {
            "case_id": case.case_id,
            "trace_id": case.trace_id,
            "status": case.status,
            "replay_output": case.replay_output,
            "eval_results": case.eval_results,
            "metrics": case.metrics,
        }
        for case in cases
    ]
    result = {
        "run_id": run.run_id,
        "status": run.status,
        "aggregate": run.aggregate,
        "cases": replay_output,
    }
    eval_config = run.eval_config or {}
    gate_policy_hash = content_hash(gate_policy) if gate_policy else None
    payload = {
        "manifest_id": new_id("man"),
        "run_id": run.run_id,
        "suite_id": suite.suite_id,
        "candidate_id": candidate.candidate_id,
        "suite_hash": content_hash(
            {
                "suite_id": suite.suite_id,
                "name": suite.name,
                "version": suite.version,
                "trace_ids": suite.trace_ids,
            }
        ),
        "candidate_hash": candidate.candidate_hash,
        "trace_set_hash": suite.trace_set_hash,
        "eval_config_hash": content_hash(eval_config),
        "replay_output_hash": content_hash(replay_output),
        "result_hash": content_hash(result),
        "gate_policy_hash": gate_policy_hash,
        "decision": decision,
    }
    signature = sign_hmac(payload, get_settings().manifest_secret)
    manifest = ManifestRecordModel(
        manifest_id=payload["manifest_id"],
        run_id=run.run_id,
        suite_hash=payload["suite_hash"],
        candidate_hash=payload["candidate_hash"],
        trace_set_hash=payload["trace_set_hash"],
        eval_config_hash=payload["eval_config_hash"],
        replay_output_hash=payload["replay_output_hash"],
        result_hash=payload["result_hash"],
        gate_policy_hash=gate_policy_hash,
        decision=decision,
        signature=signature,
        payload={**payload, "signature": signature},
    )
    session.add(manifest)
    session.flush()
    create_artifact(
        session,
        kind="manifest",
        payload=manifest.payload,
        project_id=run.project_id,
        metadata={"run_id": run.run_id, "manifest_id": manifest.manifest_id},
    )
    run.manifest_id = manifest.manifest_id
    session.flush()
    return manifest
