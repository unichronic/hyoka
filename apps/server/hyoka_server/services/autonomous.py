from __future__ import annotations

from datetime import timedelta
from typing import Any

from hyoka_schemas.hashing import content_hash
from hyoka_schemas.ids import new_id
from hyoka_schemas.resources import GatePolicy, SelfImproveCreate
from hyoka_server.models import (
    CandidateRecord,
    FailureClusterRecord,
    GateDecisionRecord,
    ImprovementProposalRecord,
    PromotionRecord,
    ReleaseGateRecord,
    RunCaseRecord,
    RunRecord,
    SelfImprovementCycleRecord,
    SuiteRecord,
    now_utc,
)
from hyoka_server.services.artifacts import create_artifact
from hyoka_server.services.failures import mine_failure_clusters
from hyoka_server.services.gates import evaluate_gate_policy
from hyoka_server.services.improvements import generate_candidate_patch
from hyoka_server.services.manifests import build_manifest
from hyoka_server.services.patches import build_patch_bundle
from hyoka_server.services.runs import execute_run
from hyoka_server.settings import get_settings
from sqlalchemy import and_, desc, func, or_, update
from sqlalchemy.orm import Session


def queue_self_improvement_cycle(
    session: Session,
    payload: SelfImproveCreate,
    *,
    baseline_run: RunRecord,
) -> SelfImprovementCycleRecord:
    cycle = SelfImprovementCycleRecord(
        cycle_id=new_id("sic"),
        project_id=baseline_run.project_id,
        baseline_run_id=baseline_run.run_id,
        status="queued",
        request=payload.model_dump(mode="json", exclude_none=True),
        result={},
        queued_at=now_utc(),
    )
    session.add(cycle)
    session.flush()
    return cycle


def claim_self_improvement_cycle(
    session: Session,
    *,
    cycle_id: str,
    worker_id: str,
    lease_seconds: int | None = None,
) -> SelfImprovementCycleRecord | None:
    lease_seconds = lease_seconds or get_settings().self_improvement_lease_seconds
    max_attempts = get_settings().worker_max_attempts
    now = now_utc()
    lease_until = now + timedelta(seconds=lease_seconds)
    claimed = (
        session.execute(
            update(SelfImprovementCycleRecord)
            .where(SelfImprovementCycleRecord.cycle_id == cycle_id)
            .where(SelfImprovementCycleRecord.execution_attempts < max_attempts)
            .where(
                or_(
                    SelfImprovementCycleRecord.status == "queued",
                    and_(
                        SelfImprovementCycleRecord.status == "running",
                        SelfImprovementCycleRecord.lease_expires_at <= now,
                    ),
                )
            )
            .values(
                status="running",
                worker_id=worker_id,
                lease_expires_at=lease_until,
                execution_attempts=SelfImprovementCycleRecord.execution_attempts + 1,
                started_at=func.coalesce(SelfImprovementCycleRecord.started_at, now),
                error_message=None,
            )
        ).rowcount
        or 0
    )
    if claimed != 1:
        session.rollback()
        return None
    session.commit()
    return session.query(SelfImprovementCycleRecord).filter_by(cycle_id=cycle_id).one()


def claim_next_self_improvement_cycle(
    session: Session,
    *,
    worker_id: str,
    lease_seconds: int | None = None,
) -> SelfImprovementCycleRecord | None:
    now = now_utc()
    candidate = (
        session.query(SelfImprovementCycleRecord)
        .filter(SelfImprovementCycleRecord.execution_attempts < get_settings().worker_max_attempts)
        .filter(
            or_(
                SelfImprovementCycleRecord.status == "queued",
                and_(
                    SelfImprovementCycleRecord.status == "running",
                    SelfImprovementCycleRecord.lease_expires_at <= now,
                ),
            )
        )
        .order_by(SelfImprovementCycleRecord.queued_at.asc(), SelfImprovementCycleRecord.created_at.asc())
        .first()
    )
    if not candidate:
        return None
    return claim_self_improvement_cycle(
        session,
        cycle_id=candidate.cycle_id,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
    )


def _release_cycle_lease(cycle: SelfImprovementCycleRecord) -> None:
    cycle.worker_id = None
    cycle.lease_expires_at = None


def _extend_cycle_lease(session: Session, cycle: SelfImprovementCycleRecord) -> None:
    if not cycle.worker_id:
        return
    cycle.lease_expires_at = now_utc() + timedelta(seconds=get_settings().self_improvement_lease_seconds)
    session.flush()


def _candidate_from_proposal(
    session: Session,
    *,
    run: RunRecord,
    cluster: FailureClusterRecord,
    proposal_payload: dict[str, Any],
) -> CandidateRecord:
    candidate_patch = proposal_payload["candidate_patch"]
    candidate_payload = {
        "project_id": run.project_id,
        "name": f"{cluster.name}_{proposal_payload['target']}_candidate",
        "base_candidate_id": run.candidate_id,
        "targets": candidate_patch["targets"],
        "config": candidate_patch["config"],
        "metadata": {
            "created_by": "hyoka_autonomous_self_improvement",
            "source_cluster_id": cluster.cluster_id,
            "source_run_id": run.run_id,
            **dict(candidate_patch.get("metadata") or {}),
        },
    }
    candidate_hash = content_hash(candidate_payload)
    candidate = (
        session.query(CandidateRecord)
        .filter_by(project_id=run.project_id, candidate_hash=candidate_hash)
        .one_or_none()
    )
    if candidate:
        return candidate
    candidate = CandidateRecord(
        candidate_id=new_id("cand"),
        project_id=run.project_id,
        name=candidate_payload["name"],
        base_candidate_id=run.candidate_id,
        targets=candidate_payload["targets"],
        config=candidate_payload["config"],
        candidate_metadata=candidate_payload["metadata"],
        candidate_hash=candidate_hash,
    )
    session.add(candidate)
    session.flush()
    return candidate


def _create_validation_run(
    session: Session,
    *,
    baseline_run: RunRecord,
    candidate: CandidateRecord,
    mode: str,
) -> RunRecord:
    suite = session.query(SuiteRecord).filter_by(suite_id=baseline_run.suite_id).one()
    run = RunRecord(
        run_id=new_id("run"),
        project_id=baseline_run.project_id,
        suite_id=suite.suite_id,
        candidate_id=candidate.candidate_id,
        mode=mode,
        repeats=baseline_run.repeats,
        status="queued",
        eval_config={
            "source": "self_improvement_cycle",
            "baseline_run_id": baseline_run.run_id,
        },
        aggregate={},
    )
    session.add(run)
    session.flush()
    for trace_id in suite.trace_ids:
        session.add(
            RunCaseRecord(
                case_id=new_id("case"),
                run_id=run.run_id,
                trace_id=trace_id,
                attempt=1,
                status="pending",
                replay_output={},
                eval_results=[],
                metrics={},
            )
        )
    session.flush()
    return run


def _case_dicts(session: Session, run_id: str) -> list[dict[str, Any]]:
    return [
        {
            "case_id": case.case_id,
            "trace_id": case.trace_id,
            "status": case.status,
            "eval_results": case.eval_results,
        }
        for case in session.query(RunCaseRecord).filter_by(run_id=run_id).order_by(RunCaseRecord.id.asc()).all()
    ]


def _gate_policy(payload: SelfImproveCreate, baseline_run: RunRecord) -> GatePolicy:
    if payload.gate_policy:
        return payload.gate_policy
    baseline_pass_rate = float((baseline_run.aggregate or {}).get("pass_rate", 0.0))
    baseline_flaky_rate = float((baseline_run.aggregate or {}).get("flaky_rate", 0.0))
    return GatePolicy(
        min_pass_rate=max(0.95, baseline_pass_rate),
        max_flaky_rate=baseline_flaky_rate,
        block_on=["execution_error", "unsafe_tool_call", "configuration_error", "replay"],
        required_artifacts=["manifest"],
    )


def _evaluate_gate(
    session: Session,
    *,
    run: RunRecord,
    policy: GatePolicy,
    name: str,
) -> GateDecisionRecord:
    suite = session.query(SuiteRecord).filter_by(suite_id=run.suite_id).one()
    candidate = session.query(CandidateRecord).filter_by(candidate_id=run.candidate_id).one()
    gate_record = ReleaseGateRecord(
        gate_id=new_id("gate"),
        project_id=run.project_id,
        name=name,
        policy=policy.model_dump(mode="json", exclude_none=True),
        policy_hash=content_hash(policy.model_dump(mode="json", exclude_none=True)),
    )
    session.add(gate_record)
    decision, reasons = evaluate_gate_policy(
        policy,
        run.aggregate or {},
        _case_dicts(session, run.run_id),
        has_manifest=bool(run.manifest_id),
    )
    manifest = build_manifest(
        session,
        run=run,
        suite=suite,
        candidate=candidate,
        decision=decision,
        gate_policy=policy.model_dump(mode="json", exclude_none=True),
    )
    decision_record = GateDecisionRecord(
        decision_id=new_id("gd"),
        gate_id=gate_record.gate_id,
        run_id=run.run_id,
        candidate_id=run.candidate_id,
        decision=decision,
        pass_rate=float((run.aggregate or {}).get("pass_rate", 0.0)),
        flaky_rate=float((run.aggregate or {}).get("flaky_rate", 0.0)),
        blocking_reasons=reasons,
        manifest_id=manifest.manifest_id,
    )
    session.add(decision_record)
    session.flush()
    return decision_record


def _pct_delta(candidate: float, baseline: float) -> float | None:
    if baseline == 0:
        return None
    return ((candidate - baseline) / baseline) * 100


def _comparison(
    *,
    baseline_run: RunRecord,
    validation_run: RunRecord,
    payload: SelfImproveCreate,
    gate_decision: GateDecisionRecord | None,
) -> dict[str, Any]:
    baseline = baseline_run.aggregate or {}
    candidate = validation_run.aggregate or {}
    pass_rate_delta = float(candidate.get("pass_rate", 0.0)) - float(baseline.get("pass_rate", 0.0))
    p95_delta_pct = _pct_delta(float(candidate.get("p95_latency_ms", 0.0)), float(baseline.get("p95_latency_ms", 0.0)))
    cost_delta_pct = _pct_delta(float(candidate.get("total_cost_usd", 0.0)), float(baseline.get("total_cost_usd", 0.0)))
    blockers: list[str] = []
    if pass_rate_delta < payload.min_pass_rate_delta:
        blockers.append(
            f"pass_rate_delta {pass_rate_delta:.3f} below required delta {payload.min_pass_rate_delta:.3f}"
        )
    if (
        payload.max_p95_latency_increase_pct is not None
        and p95_delta_pct is not None
        and p95_delta_pct > payload.max_p95_latency_increase_pct
    ):
        blockers.append(
            f"p95 latency increase {p95_delta_pct:.3f}% above {payload.max_p95_latency_increase_pct:.3f}%"
        )
    if (
        payload.max_cost_increase_pct is not None
        and cost_delta_pct is not None
        and cost_delta_pct > payload.max_cost_increase_pct
    ):
        blockers.append(f"cost increase {cost_delta_pct:.3f}% above {payload.max_cost_increase_pct:.3f}%")
    if gate_decision and gate_decision.decision != "approved":
        blockers.extend(gate_decision.blocking_reasons)
    return {
        "baseline_run_id": baseline_run.run_id,
        "validation_run_id": validation_run.run_id,
        "pass_rate_delta": pass_rate_delta,
        "p95_latency_delta_pct": p95_delta_pct,
        "cost_delta_pct": cost_delta_pct,
        "gate_decision": gate_decision.decision if gate_decision else None,
        "blocking_reasons": blockers,
        "approved": not blockers and (gate_decision is None or gate_decision.decision == "approved"),
    }


def _maybe_promote(
    session: Session,
    *,
    payload: SelfImproveCreate,
    comparison: dict[str, Any],
    gate_decision: GateDecisionRecord | None,
) -> PromotionRecord | None:
    if not payload.promote_on_approval or not comparison["approved"] or gate_decision is None:
        return None
    promotion = PromotionRecord(
        promotion_id=new_id("prom"),
        candidate_id=gate_decision.candidate_id,
        gate_decision_id=gate_decision.decision_id,
        manifest_id=gate_decision.manifest_id,
        environment=payload.promotion_environment,
        actor="hyoka_autonomous_self_improvement",
        override=False,
    )
    session.add(promotion)
    session.flush()
    return promotion


def _execute_cycle_record(session: Session, cycle: SelfImprovementCycleRecord) -> SelfImprovementCycleRecord:
    payload = SelfImproveCreate.model_validate(cycle.request)
    baseline_run = session.query(RunRecord).filter_by(run_id=cycle.baseline_run_id).one()
    cycle.status = "running"
    cycle.started_at = cycle.started_at or now_utc()
    try:
        clusters = mine_failure_clusters(session, baseline_run)
        clusters = sorted(clusters, key=lambda cluster: (-cluster.case_count, cluster.created_at))[: payload.max_candidates]
        if not clusters:
            cycle.status = "completed"
            cycle.result = {"decision": "no_failures", "clusters": [], "candidates": []}
            cycle.completed_at = now_utc()
            _release_cycle_lease(cycle)
            session.commit()
            return cycle

        results = []
        gate_policy = _gate_policy(payload, baseline_run)
        validation_mode = payload.validation_mode or baseline_run.mode
        for cluster in clusters:
            _extend_cycle_lease(session, cycle)
            base_candidate = session.query(CandidateRecord).filter_by(candidate_id=baseline_run.candidate_id).one_or_none()
            cases = (
                session.query(RunCaseRecord)
                .filter(RunCaseRecord.run_id == baseline_run.run_id)
                .filter(RunCaseRecord.trace_id.in_(cluster.representative_trace_ids))
                .all()
            )
            proposal_payload = generate_candidate_patch(
                cluster=cluster,
                run=baseline_run,
                base_candidate=base_candidate,
                cases=cases,
                target=payload.target,
            )
            candidate = _candidate_from_proposal(
                session,
                run=baseline_run,
                cluster=cluster,
                proposal_payload=proposal_payload,
            )
            proposal = ImprovementProposalRecord(
                proposal_id=new_id("prop"),
                cluster_id=cluster.cluster_id,
                candidate_id=candidate.candidate_id,
                target=proposal_payload["target"],
                method=proposal_payload["method"],
                proposal=proposal_payload,
            )
            session.add(proposal)
            session.flush()
            patch_artifact = create_artifact(
                session,
                kind="patch_bundle",
                payload=build_patch_bundle(candidate=candidate, proposal=proposal),
                project_id=baseline_run.project_id,
                metadata={
                    "cycle_id": cycle.cycle_id,
                    "proposal_id": proposal.proposal_id,
                    "candidate_id": candidate.candidate_id,
                },
            )
            validation_run = _create_validation_run(
                session,
                baseline_run=baseline_run,
                candidate=candidate,
                mode=validation_mode,
            )
            session.commit()
            if payload.execute_validation:
                _extend_cycle_lease(session, cycle)
                session.commit()
                execute_run(session, validation_run.run_id, worker_id=f"self-improve:{cycle.cycle_id}")
                validation_run = session.query(RunRecord).filter_by(run_id=validation_run.run_id).one()
                cycle = session.query(SelfImprovementCycleRecord).filter_by(cycle_id=cycle.cycle_id).one()
                _extend_cycle_lease(session, cycle)

            gate_decision = None
            comparison: dict[str, Any] | None = None
            promotion = None
            if validation_run.status == "completed":
                gate_decision = _evaluate_gate(
                    session,
                    run=validation_run,
                    policy=gate_policy,
                    name=f"self-improvement:{cycle.cycle_id}",
                )
                comparison = _comparison(
                    baseline_run=baseline_run,
                    validation_run=validation_run,
                    payload=payload,
                    gate_decision=gate_decision,
                )
                promotion = _maybe_promote(
                    session,
                    payload=payload,
                    comparison=comparison,
                    gate_decision=gate_decision,
                )
            results.append(
                {
                    "cluster_id": cluster.cluster_id,
                    "failure_type": cluster.failure_type,
                    "proposal_id": proposal.proposal_id,
                    "candidate_id": candidate.candidate_id,
                    "patch_artifact_id": patch_artifact.artifact_id,
                    "validation_run_id": validation_run.run_id,
                    "validation_status": validation_run.status,
                    "gate_decision_id": gate_decision.decision_id if gate_decision else None,
                    "gate_decision": gate_decision.decision if gate_decision else None,
                    "promotion_id": promotion.promotion_id if promotion else None,
                    "comparison": comparison,
                }
            )
            session.commit()

        approved = [result for result in results if (result.get("comparison") or {}).get("approved")]
        best = sorted(
            results,
            key=lambda item: (
                (item.get("comparison") or {}).get("approved", False),
                (item.get("comparison") or {}).get("pass_rate_delta", -999),
            ),
            reverse=True,
        )[0]
        cycle.status = "completed"
        cycle.result = {
            "decision": "approved" if approved else "blocked",
            "clusters": [cluster.cluster_id for cluster in clusters],
            "candidates": results,
            "best_candidate_id": best.get("candidate_id"),
            "best_validation_run_id": best.get("validation_run_id"),
            "approved_candidate_ids": [result["candidate_id"] for result in approved],
        }
        cycle.completed_at = now_utc()
        _release_cycle_lease(cycle)
        session.commit()
        return cycle
    except Exception as exc:
        cycle.status = "failed"
        cycle.error_message = str(exc)
        cycle.completed_at = now_utc()
        _release_cycle_lease(cycle)
        session.commit()
        raise


def execute_self_improvement_cycle(
    session: Session,
    cycle_id: str,
    *,
    worker_id: str,
    already_claimed: bool = False,
) -> SelfImprovementCycleRecord | None:
    if already_claimed:
        cycle = session.query(SelfImprovementCycleRecord).filter_by(cycle_id=cycle_id).one_or_none()
        if not cycle:
            return None
    else:
        cycle = claim_self_improvement_cycle(session, cycle_id=cycle_id, worker_id=worker_id)
        if not cycle:
            return session.query(SelfImprovementCycleRecord).filter_by(cycle_id=cycle_id).one_or_none()
    return _execute_cycle_record(session, cycle)


def run_self_improvement_cycle(session: Session, payload: SelfImproveCreate) -> SelfImprovementCycleRecord:
    baseline_run = session.query(RunRecord).filter_by(run_id=payload.run_id).one()
    cycle = queue_self_improvement_cycle(session, payload, baseline_run=baseline_run)
    session.commit()
    executed = execute_self_improvement_cycle(
        session,
        cycle.cycle_id,
        worker_id=f"self-improve:{cycle.cycle_id}",
    )
    if executed is None:
        raise RuntimeError(f"self-improvement cycle could not be executed: {cycle.cycle_id}")
    return executed


def latest_cycles(session: Session, *, project_id: str, limit: int = 50) -> list[SelfImprovementCycleRecord]:
    return (
        session.query(SelfImprovementCycleRecord)
        .filter_by(project_id=project_id)
        .order_by(desc(SelfImprovementCycleRecord.created_at))
        .limit(limit)
        .all()
    )
