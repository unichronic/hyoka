from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


def now_utc() -> datetime:
    return datetime.now(UTC)


JSONType = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    pass


class TraceRecord(Base):
    __tablename__ = "traces"
    __table_args__ = (
        UniqueConstraint("project_id", "trace_id", name="uq_traces_project_trace"),
        Index("ix_traces_project_created", "project_id", "created_at"),
        Index("ix_traces_agent_status", "agent_name", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(96), nullable=False)
    project_id: Mapped[str] = mapped_column(String(96), nullable=False, default="default")
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(200), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    environment: Mapped[str] = mapped_column(String(64), nullable=False, default="dev")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ok")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, nullable=False)
    final_output_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    trace_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class IdempotencyKeyRecord(Base):
    __tablename__ = "idempotency_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    scope: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class ApiKeyRecord(Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        UniqueConstraint("key_prefix", name="uq_api_keys_prefix"),
        Index("ix_api_keys_project", "project_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key_id: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    project_id: Mapped[str] = mapped_column(String(96), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(96), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONType, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class AuditEventRecord(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_project_created", "project_id", "created_at"),
        Index("ix_audit_action", "action"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    project_id: Mapped[str] = mapped_column(String(96), nullable=False)
    actor_key_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    action: Mapped[str] = mapped_column(String(96), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ok")
    request_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    audit_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class SuiteRecord(Base):
    __tablename__ = "suites"
    __table_args__ = (
        UniqueConstraint("project_id", "name", "version", name="uq_suites_project_name_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    suite_id: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    project_id: Mapped[str] = mapped_column(String(96), nullable=False, default="default")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    trace_ids: Mapped[list[str]] = mapped_column(JSONType, nullable=False)
    trace_set_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CandidateRecord(Base):
    __tablename__ = "candidates"
    __table_args__ = (
        UniqueConstraint("project_id", "candidate_hash", name="uq_candidates_project_hash"),
        Index("ix_candidates_project_created", "project_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    project_id: Mapped[str] = mapped_column(String(96), nullable=False, default="default")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    base_candidate_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    targets: Mapped[list[str]] = mapped_column(JSONType, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    candidate_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, nullable=False)
    candidate_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class ArtifactRecordModel(Base):
    __tablename__ = "artifacts"
    __table_args__ = (Index("ix_artifacts_project_created", "project_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artifact_id: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    project_id: Mapped[str] = mapped_column(String(96), nullable=False, default="default")
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class RunRecord(Base):
    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_project_status", "project_id", "status"),
        Index("ix_runs_status_lease", "status", "lease_expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    project_id: Mapped[str] = mapped_column(String(96), nullable=False, default="default")
    suite_id: Mapped[str] = mapped_column(String(96), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(96), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="mock")
    repeats: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    eval_config: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    aggregate: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    artifact_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    manifest_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class RunCaseRecord(Base):
    __tablename__ = "run_cases"
    __table_args__ = (Index("ix_run_cases_run", "run_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    run_id: Mapped[str] = mapped_column(String(96), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(96), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    replay_output: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    eval_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, nullable=False, default=list)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ManifestRecordModel(Base):
    __tablename__ = "manifests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    manifest_id: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    run_id: Mapped[str] = mapped_column(String(96), nullable=False)
    suite_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    candidate_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    trace_set_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    eval_config_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    replay_output_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    result_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    gate_policy_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    signature: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class ReleaseGateRecord(Base):
    __tablename__ = "release_gates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gate_id: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    project_id: Mapped[str] = mapped_column(String(96), nullable=False, default="default")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    policy: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class GateDecisionRecord(Base):
    __tablename__ = "gate_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    gate_id: Mapped[str] = mapped_column(String(96), nullable=False)
    run_id: Mapped[str] = mapped_column(String(96), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(96), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    pass_rate: Mapped[float] = mapped_column(Float, nullable=False)
    flaky_rate: Mapped[float] = mapped_column(Float, nullable=False)
    blocking_reasons: Mapped[list[str]] = mapped_column(JSONType, nullable=False)
    manifest_id: Mapped[str] = mapped_column(String(96), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class FailureClusterRecord(Base):
    __tablename__ = "failure_clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_id: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    run_id: Mapped[str] = mapped_column(String(96), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    failure_type: Mapped[str] = mapped_column(String(128), nullable=False)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    representative_trace_ids: Mapped[list[str]] = mapped_column(JSONType, nullable=False)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_targets: Mapped[list[str]] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class ImprovementProposalRecord(Base):
    __tablename__ = "improvement_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    cluster_id: Mapped[str] = mapped_column(String(96), nullable=False)
    candidate_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    target: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str] = mapped_column(String(64), nullable=False)
    proposal: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class SelfImprovementCycleRecord(Base):
    __tablename__ = "self_improvement_cycles"
    __table_args__ = (
        Index("ix_self_improvement_project_created", "project_id", "created_at"),
        Index("ix_self_improvement_status", "status"),
        Index("ix_self_improvement_status_lease", "status", "lease_expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    project_id: Mapped[str] = mapped_column(String(96), nullable=False)
    baseline_run_id: Mapped[str] = mapped_column(String(96), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    request: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class PromotionRecord(Base):
    __tablename__ = "promotions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    promotion_id: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    candidate_id: Mapped[str] = mapped_column(String(96), nullable=False)
    gate_decision_id: Mapped[str] = mapped_column(String(96), nullable=False)
    manifest_id: Mapped[str] = mapped_column(String(96), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
