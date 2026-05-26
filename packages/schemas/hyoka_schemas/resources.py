from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from hyoka_schemas.ids import new_id

ReplayMode = Literal["mock", "live", "hybrid", "sandbox"]
RunStatus = Literal["queued", "running", "finalizing", "completed", "failed", "cancelled", "timed_out"]
CaseStatus = Literal["pending", "running", "replayed", "evaluated", "passed", "failed", "flaky", "error", "skipped"]
GateDecision = Literal["approved", "blocked", "needs_review"]


class SuiteCreate(BaseModel):
    project_id: str = "default"
    name: str
    trace_ids: list[str] = Field(default_factory=list)
    query: dict[str, Any] = Field(default_factory=dict)


class SuiteRead(BaseModel):
    suite_id: str
    project_id: str
    name: str
    version: int
    trace_ids: list[str]
    trace_set_hash: str
    created_at: datetime
    locked_at: datetime | None = None


class CandidateCreate(BaseModel):
    model_config = ConfigDict(extra="allow")

    project_id: str = "default"
    name: str
    base_candidate_id: str | None = None
    targets: list[str] = Field(default_factory=lambda: ["prompt"])
    config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateRead(CandidateCreate):
    candidate_id: str
    candidate_hash: str
    created_at: datetime


class RunCreate(BaseModel):
    project_id: str = "default"
    suite_id: str
    candidate_id: str
    mode: ReplayMode = "mock"
    repeats: int = Field(default=1, ge=1, le=100)
    eval_config: dict[str, Any] = Field(default_factory=dict)


class RunCaseRead(BaseModel):
    case_id: str
    run_id: str
    trace_id: str
    status: CaseStatus
    attempt: int
    replay_output: dict[str, Any]
    eval_results: list[dict[str, Any]]
    metrics: dict[str, Any]
    started_at: datetime | None = None
    completed_at: datetime | None = None


class RunRead(BaseModel):
    run_id: str
    project_id: str
    suite_id: str
    candidate_id: str
    mode: ReplayMode
    repeats: int
    status: RunStatus
    queued_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    aggregate: dict[str, Any] = Field(default_factory=dict)
    artifact_id: str | None = None
    manifest_id: str | None = None
    worker_id: str | None = None
    lease_expires_at: datetime | None = None
    execution_attempts: int = 0
    cancel_requested: bool = False
    error_code: str | None = None
    error_message: str | None = None


class ArtifactRecord(BaseModel):
    artifact_id: str
    project_id: str = "default"
    kind: str
    content_hash: str
    uri: str
    size_bytes: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class GatePolicy(BaseModel):
    suite: str | None = None
    mode: ReplayMode | None = None
    min_pass_rate: float = Field(default=0.95, ge=0, le=1)
    max_flaky_rate: float = Field(default=0.0, ge=0, le=1)
    max_cost_increase_pct: float | None = Field(default=None, ge=0)
    max_p95_latency_ms: int | None = Field(default=None, ge=0)
    must_improve: list[str] = Field(default_factory=list)
    block_on: list[str] = Field(default_factory=list)
    required_artifacts: list[str] = Field(default_factory=list)


class GateEvaluateRequest(BaseModel):
    project_id: str = "default"
    name: str = "default-release-gate"
    run_id: str
    policy: GatePolicy


class GateDecisionRead(BaseModel):
    decision_id: str
    gate_id: str
    run_id: str
    candidate_id: str
    decision: GateDecision
    pass_rate: float
    flaky_rate: float
    blocking_reasons: list[str]
    manifest_id: str
    created_at: datetime


class ManifestRead(BaseModel):
    manifest_id: str
    run_id: str
    suite_hash: str
    candidate_hash: str
    trace_set_hash: str
    eval_config_hash: str
    replay_output_hash: str
    result_hash: str
    gate_policy_hash: str | None = None
    decision: GateDecision
    signature: str
    payload: dict[str, Any]
    created_at: datetime


class CompareRunsRequest(BaseModel):
    baseline_run_id: str
    candidate_run_id: str


class CompareRunsResponse(BaseModel):
    baseline_run_id: str
    candidate_run_id: str
    deltas: dict[str, Any]
    summary: str


class FailureClusterRead(BaseModel):
    cluster_id: str
    run_id: str
    name: str
    failure_type: str
    case_count: int
    representative_trace_ids: list[str]
    hypothesis: str
    suggested_targets: list[str]
    created_at: datetime


class ImprovementProposalRead(BaseModel):
    proposal_id: str
    cluster_id: str
    candidate_id: str | None = None
    target: str
    method: str
    proposal: dict[str, Any]
    created_at: datetime


class SelfImproveCreate(BaseModel):
    project_id: str = "default"
    run_id: str
    target: str = "prompt"
    max_candidates: int = Field(default=3, ge=1, le=10)
    validation_mode: ReplayMode | None = None
    execute_inline: bool = True
    execute_validation: bool = True
    promote_on_approval: bool = False
    promotion_environment: str = "staging"
    min_pass_rate_delta: float = 0.0
    max_cost_increase_pct: float | None = Field(default=None, ge=0)
    max_p95_latency_increase_pct: float | None = Field(default=None, ge=0)
    gate_policy: GatePolicy | None = None


class SelfImproveCycleRead(BaseModel):
    cycle_id: str
    project_id: str
    baseline_run_id: str
    status: str
    request: dict[str, Any]
    result: dict[str, Any] = Field(default_factory=dict)
    worker_id: str | None = None
    lease_expires_at: datetime | None = None
    execution_attempts: int = 0
    error_message: str | None = None
    queued_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class PromotionCreate(BaseModel):
    candidate_id: str
    gate_decision_id: str
    manifest_id: str
    environment: str = "prod"
    actor: str = "local"
    override: bool = False


class PromotionRead(PromotionCreate):
    promotion_id: str = Field(default_factory=lambda: new_id("prom"))
    created_at: datetime


class ApiKeyCreate(BaseModel):
    project_id: str = "default"
    name: str
    scopes: list[str] = Field(default_factory=lambda: ["read", "write"])
    expires_at: datetime | None = None

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: list[str]) -> list[str]:
        allowed = {"admin", "read", "write"}
        scopes = sorted({scope.strip() for scope in value if scope.strip()})
        invalid = [scope for scope in scopes if scope not in allowed]
        if invalid:
            raise ValueError(f"unsupported scopes: {', '.join(invalid)}")
        return scopes or ["read"]


class ApiKeyRead(BaseModel):
    key_id: str
    project_id: str
    name: str
    key_prefix: str
    scopes: list[str]
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime


class ApiKeyCreated(ApiKeyRead):
    secret: str


class AuditEventRead(BaseModel):
    event_id: str
    project_id: str
    actor_key_id: str | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    status: str
    request_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
