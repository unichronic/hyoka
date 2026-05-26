from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from hyoka_schemas.ids import new_id

TraceStepType = Literal[
    "llm_call",
    "tool_call",
    "tool_result",
    "retrieval",
    "memory_read",
    "memory_write",
    "memory_update",
    "memory_delete",
    "router_decision",
    "human_review",
    "error",
    "custom_event",
]

TraceStatus = Literal["ok", "error", "cancelled", "timeout"]


class TraceStep(BaseModel):
    model_config = ConfigDict(extra="allow")

    step_id: str = Field(default_factory=lambda: new_id("step"))
    parent_step_id: str | None = None
    type: TraceStepType
    name: str | None = None
    provider: str | None = None
    model: str | None = None
    tool_name: str | None = None
    input_hash: str | None = None
    output_hash: str | None = None
    output_preview: Any | None = None
    arguments_hash: str | None = None
    arguments_preview: Any | None = None
    response_hash: str | None = None
    response_preview: Any | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    tokens_input: int | None = Field(default=None, ge=0)
    tokens_output: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    status: TraceStatus = "ok"
    metadata: dict[str, Any] = Field(default_factory=dict)


class TraceSummary(BaseModel):
    latency_ms: int = Field(default=0, ge=0)
    tokens_total: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0)
    status: TraceStatus = "ok"


class TraceCreate(BaseModel):
    model_config = ConfigDict(extra="allow")

    trace_id: str = Field(default_factory=lambda: new_id("tr"))
    project_id: str = "default"
    schema_version: str = "hyoka.trace.v1"
    agent_name: str
    session_id: str | None = None
    environment: str = "dev"
    git_sha: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    input: dict[str, Any]
    steps: list[TraceStep] = Field(default_factory=list)
    final_output_preview: Any | None = None
    summary: TraceSummary = Field(default_factory=TraceSummary)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("started_at", "ended_at")
    @classmethod
    def ensure_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class TraceRead(TraceCreate):
    payload_hash: str
    created_at: datetime

