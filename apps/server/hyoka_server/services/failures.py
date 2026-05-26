from __future__ import annotations

from collections import defaultdict

from hyoka_schemas.ids import new_id
from hyoka_server.models import FailureClusterRecord, RunCaseRecord, RunRecord
from sqlalchemy.orm import Session

ACTIONABLE_FAILURE_LABELS = [
    "execution_error",
    "unsafe_tool_call",
    "missing_required_tool",
    "schema_mismatch",
    "final_output",
    "format",
    "llm_judge",
    "latency",
    "cost",
    "configuration_error",
    "replay",
    "tool_use",
]


def failure_cluster_key(labels: list[str], fallback: str) -> str:
    label_set = set(labels)
    for label in ACTIONABLE_FAILURE_LABELS:
        if label in label_set:
            return label
    return labels[0] if labels else fallback


def failure_cluster_targets(failure_type: str) -> list[str]:
    if failure_type in {"missing_required_tool", "unsafe_tool_call", "tool_use"}:
        return ["tool_policy", "prompt"]
    if failure_type in {"schema_mismatch", "format", "final_output"}:
        return ["output_contract", "prompt", "eval_rule"]
    if failure_type in {"latency", "cost"}:
        return ["runtime_policy", "prompt"]
    if failure_type in {"execution_error", "replay"}:
        return ["replay_policy", "tool_schema"]
    return ["prompt", "eval_rule"]


def mine_failure_clusters(session: Session, run: RunRecord) -> list[FailureClusterRecord]:
    existing = session.query(FailureClusterRecord).filter_by(run_id=run.run_id).all()
    if existing:
        return existing

    cases = session.query(RunCaseRecord).filter_by(run_id=run.run_id).all()
    groups: dict[str, list[RunCaseRecord]] = defaultdict(list)
    for case in cases:
        if case.status not in {"failed", "flaky", "error"}:
            continue
        labels = [
            label
            for result in (case.eval_results or [])
            if result.get("passed") is False
            for label in result.get("labels", [])
        ]
        groups[failure_cluster_key(labels, case.status)].append(case)

    created = []
    for failure_type, members in groups.items():
        name = str(failure_type).replace(" ", "_").lower()
        record = FailureClusterRecord(
            cluster_id=new_id("fc"),
            run_id=run.run_id,
            name=name,
            failure_type=str(failure_type),
            case_count=len(members),
            representative_trace_ids=[case.trace_id for case in members[:5]],
            hypothesis=f"Cases share failing label '{failure_type}'. Inspect representative traces and eval evidence.",
            suggested_targets=failure_cluster_targets(str(failure_type)),
        )
        session.add(record)
        created.append(record)
    session.flush()
    return created
