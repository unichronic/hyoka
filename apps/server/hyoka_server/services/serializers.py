from __future__ import annotations

from hyoka_schemas.resources import (
    ApiKeyCreated,
    ApiKeyRead,
    ArtifactRecord,
    AuditEventRead,
    CandidateRead,
    FailureClusterRead,
    GateDecisionRead,
    ImprovementProposalRead,
    ManifestRead,
    PromotionRead,
    RunCaseRead,
    RunRead,
    SelfImproveCycleRead,
    SuiteRead,
)
from hyoka_schemas.traces import TraceRead
from hyoka_server.models import (
    ApiKeyRecord,
    ArtifactRecordModel,
    AuditEventRecord,
    CandidateRecord,
    FailureClusterRecord,
    GateDecisionRecord,
    ImprovementProposalRecord,
    ManifestRecordModel,
    PromotionRecord,
    RunCaseRecord,
    RunRecord,
    SelfImprovementCycleRecord,
    SuiteRecord,
    TraceRecord,
)


def trace_to_read(record: TraceRecord) -> TraceRead:
    return TraceRead(
        trace_id=record.trace_id,
        project_id=record.project_id,
        schema_version=record.schema_version,
        agent_name=record.agent_name,
        session_id=record.session_id,
        environment=record.environment,
        started_at=record.started_at,
        ended_at=record.ended_at,
        input=record.input,
        steps=record.steps,
        final_output_preview=record.final_output_preview,
        summary=record.summary,
        metadata=record.trace_metadata,
        payload_hash=record.payload_hash,
        created_at=record.created_at,
    )


def suite_to_read(record: SuiteRecord) -> SuiteRead:
    return SuiteRead(
        suite_id=record.suite_id,
        project_id=record.project_id,
        name=record.name,
        version=record.version,
        trace_ids=record.trace_ids,
        trace_set_hash=record.trace_set_hash,
        created_at=record.created_at,
        locked_at=record.locked_at,
    )


def candidate_to_read(record: CandidateRecord) -> CandidateRead:
    return CandidateRead(
        candidate_id=record.candidate_id,
        project_id=record.project_id,
        name=record.name,
        base_candidate_id=record.base_candidate_id,
        targets=record.targets,
        config=record.config,
        metadata=record.candidate_metadata,
        candidate_hash=record.candidate_hash,
        created_at=record.created_at,
    )


def run_to_read(record: RunRecord) -> RunRead:
    return RunRead(
        run_id=record.run_id,
        project_id=record.project_id,
        suite_id=record.suite_id,
        candidate_id=record.candidate_id,
        mode=record.mode,
        repeats=record.repeats,
        status=record.status,
        queued_at=record.queued_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        aggregate=record.aggregate or {},
        artifact_id=record.artifact_id,
        manifest_id=record.manifest_id,
        worker_id=record.worker_id,
        lease_expires_at=record.lease_expires_at,
        execution_attempts=record.execution_attempts,
        cancel_requested=record.cancel_requested,
        error_code=record.error_code,
        error_message=record.error_message,
    )


def case_to_read(record: RunCaseRecord) -> RunCaseRead:
    return RunCaseRead(
        case_id=record.case_id,
        run_id=record.run_id,
        trace_id=record.trace_id,
        status=record.status,
        attempt=record.attempt,
        replay_output=record.replay_output or {},
        eval_results=record.eval_results or [],
        metrics=record.metrics or {},
        started_at=record.started_at,
        completed_at=record.completed_at,
    )


def artifact_to_read(record: ArtifactRecordModel) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=record.artifact_id,
        project_id=record.project_id,
        kind=record.kind,
        content_hash=record.content_hash,
        uri=record.uri,
        size_bytes=record.size_bytes,
        metadata=record.artifact_metadata,
        created_at=record.created_at,
    )


def api_key_to_read(record: ApiKeyRecord) -> ApiKeyRead:
    return ApiKeyRead(
        key_id=record.key_id,
        project_id=record.project_id,
        name=record.name,
        key_prefix=record.key_prefix,
        scopes=record.scopes or [],
        expires_at=record.expires_at,
        last_used_at=record.last_used_at,
        revoked_at=record.revoked_at,
        created_at=record.created_at,
    )


def api_key_to_created(record: ApiKeyRecord, secret: str) -> ApiKeyCreated:
    return ApiKeyCreated(**api_key_to_read(record).model_dump(), secret=secret)


def audit_event_to_read(record: AuditEventRecord) -> AuditEventRead:
    return AuditEventRead(
        event_id=record.event_id,
        project_id=record.project_id,
        actor_key_id=record.actor_key_id,
        action=record.action,
        resource_type=record.resource_type,
        resource_id=record.resource_id,
        status=record.status,
        request_id=record.request_id,
        metadata=record.audit_metadata,
        created_at=record.created_at,
    )


def manifest_to_read(record: ManifestRecordModel) -> ManifestRead:
    return ManifestRead(
        manifest_id=record.manifest_id,
        run_id=record.run_id,
        suite_hash=record.suite_hash,
        candidate_hash=record.candidate_hash,
        trace_set_hash=record.trace_set_hash,
        eval_config_hash=record.eval_config_hash,
        replay_output_hash=record.replay_output_hash,
        result_hash=record.result_hash,
        gate_policy_hash=record.gate_policy_hash,
        decision=record.decision,
        signature=record.signature,
        payload=record.payload,
        created_at=record.created_at,
    )


def gate_decision_to_read(record: GateDecisionRecord) -> GateDecisionRead:
    return GateDecisionRead(
        decision_id=record.decision_id,
        gate_id=record.gate_id,
        run_id=record.run_id,
        candidate_id=record.candidate_id,
        decision=record.decision,
        pass_rate=record.pass_rate,
        flaky_rate=record.flaky_rate,
        blocking_reasons=record.blocking_reasons,
        manifest_id=record.manifest_id,
        created_at=record.created_at,
    )


def failure_cluster_to_read(record: FailureClusterRecord) -> FailureClusterRead:
    return FailureClusterRead(
        cluster_id=record.cluster_id,
        run_id=record.run_id,
        name=record.name,
        failure_type=record.failure_type,
        case_count=record.case_count,
        representative_trace_ids=record.representative_trace_ids,
        hypothesis=record.hypothesis,
        suggested_targets=record.suggested_targets,
        created_at=record.created_at,
    )


def improvement_proposal_to_read(record: ImprovementProposalRecord) -> ImprovementProposalRead:
    return ImprovementProposalRead(
        proposal_id=record.proposal_id,
        cluster_id=record.cluster_id,
        candidate_id=record.candidate_id,
        target=record.target,
        method=record.method,
        proposal=record.proposal,
        created_at=record.created_at,
    )


def self_improvement_cycle_to_read(record: SelfImprovementCycleRecord) -> SelfImproveCycleRead:
    return SelfImproveCycleRead(
        cycle_id=record.cycle_id,
        project_id=record.project_id,
        baseline_run_id=record.baseline_run_id,
        status=record.status,
        request=record.request or {},
        result=record.result or {},
        worker_id=record.worker_id,
        lease_expires_at=record.lease_expires_at,
        execution_attempts=record.execution_attempts,
        error_message=record.error_message,
        queued_at=record.queued_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        created_at=record.created_at,
    )


def promotion_to_read(record: PromotionRecord) -> PromotionRead:
    return PromotionRead(
        promotion_id=record.promotion_id,
        candidate_id=record.candidate_id,
        gate_decision_id=record.gate_decision_id,
        manifest_id=record.manifest_id,
        environment=record.environment,
        actor=record.actor,
        override=record.override,
        created_at=record.created_at,
    )
