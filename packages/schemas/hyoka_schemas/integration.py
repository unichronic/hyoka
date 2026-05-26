from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from hyoka_schemas.ids import new_id

HyokaEventType = Literal[
    "trace_start",
    "trace_end",
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


class HyokaEvent(BaseModel):
    """Framework-neutral event envelope for any service or agent runtime."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    event_id: str = Field(default_factory=lambda: new_id("evt"))
    trace_id: str
    project_id: str = "default"
    source: str = "custom"
    service_name: str | None = None
    agent_name: str | None = None
    environment: str = "dev"
    session_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: HyokaEventType = Field(alias="type")
    name: str | None = None
    parent_event_id: str | None = None
    status: Literal["ok", "error", "cancelled", "timeout"] = "ok"
    duration_ms: int | None = Field(default=None, ge=0)
    input: Any | None = None
    output: Any | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class HyokaExposition(BaseModel):
    """Payload a service can expose at /hyoka/traces for pull ingestion."""

    schema_version: str = "hyoka.exposition.v1"
    resource: dict[str, Any] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)
    events: list[HyokaEvent] = Field(default_factory=list)
    traces: list[dict[str, Any]] = Field(default_factory=list)

