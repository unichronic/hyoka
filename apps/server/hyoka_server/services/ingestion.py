from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from hyoka_schemas.hashing import canonical_json, content_hash
from hyoka_schemas.integration import HyokaEvent
from hyoka_schemas.traces import TraceCreate, TraceStep, TraceSummary
from hyoka_server.models import IdempotencyKeyRecord, TraceRecord
from hyoka_server.services.redaction import redact
from sqlalchemy.orm import Session


def jsonish(value: Any) -> Any:
    if value is None or isinstance(value, str):
        return value
    return canonical_json(value)


def utc_comparable(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def persist_trace(
    session: Session,
    trace: TraceCreate,
    *,
    idempotency_key: str | None = None,
) -> TraceRecord:
    if idempotency_key:
        idem = session.query(IdempotencyKeyRecord).filter_by(key=idempotency_key).one_or_none()
        if idem and idem.resource_type == "trace":
            existing = (
                session.query(TraceRecord)
                .filter_by(project_id=trace.project_id, trace_id=idem.resource_id)
                .one_or_none()
            )
            if existing:
                return existing

    existing = (
        session.query(TraceRecord)
        .filter_by(project_id=trace.project_id, trace_id=trace.trace_id)
        .one_or_none()
    )
    if existing:
        return existing

    payload = redact(trace.model_dump(mode="json"))
    record = TraceRecord(
        trace_id=trace.trace_id,
        project_id=trace.project_id,
        schema_version=trace.schema_version,
        agent_name=trace.agent_name,
        session_id=trace.session_id,
        environment=trace.environment,
        status=trace.summary.status,
        started_at=trace.started_at,
        ended_at=trace.ended_at,
        input=payload["input"],
        steps=payload["steps"],
        final_output_preview=jsonish(payload.get("final_output_preview")),
        summary=payload["summary"],
        trace_metadata=payload.get("metadata", {}),
        payload_hash=content_hash(payload),
        raw_payload=payload,
    )
    session.add(record)
    if idempotency_key:
        session.add(
            IdempotencyKeyRecord(
                key=idempotency_key,
                scope=f"trace:{trace.project_id}",
                resource_type="trace",
                resource_id=trace.trace_id,
            )
        )
    session.flush()
    return record


def _base_metadata(event: HyokaEvent) -> dict[str, Any]:
    return {
        "source": event.source,
        "service_name": event.service_name,
        "labels": event.labels,
        "attributes": event.attributes,
    }


def _initial_trace(event: HyokaEvent) -> TraceCreate:
    metadata = _base_metadata(event)
    metadata["integration"] = "hyoka_event"
    return TraceCreate(
        trace_id=event.trace_id,
        project_id=event.project_id,
        agent_name=event.agent_name or event.service_name or "unknown-agent",
        session_id=event.session_id,
        environment=event.environment,
        started_at=event.timestamp,
        input=event.input if isinstance(event.input, dict) else {"input": event.input},
        steps=[],
        summary=TraceSummary(status=event.status),
        metadata=metadata,
    )


def _event_to_step(event: HyokaEvent) -> dict[str, Any]:
    attrs = event.attributes or {}
    step = TraceStep(
        step_id=event.event_id,
        parent_step_id=event.parent_event_id,
        type=event.event_type,
        name=event.name,
        provider=attrs.get("provider"),
        model=attrs.get("model"),
        tool_name=attrs.get("tool_name"),
        input_hash=content_hash(event.input) if event.input is not None else None,
        output_hash=content_hash(event.output) if event.output is not None else None,
        output_preview=event.output,
        arguments_hash=content_hash(event.input) if event.event_type == "tool_call" else None,
        arguments_preview=event.input if event.event_type == "tool_call" else None,
        response_hash=content_hash(event.output) if event.event_type == "tool_call" else None,
        response_preview=event.output if event.event_type == "tool_call" else None,
        latency_ms=event.duration_ms,
        tokens_input=attrs.get("tokens_input"),
        tokens_output=attrs.get("tokens_output"),
        cost_usd=attrs.get("cost_usd"),
        status=event.status,
        metadata=_base_metadata(event),
    )
    return step.model_dump(mode="json", exclude_none=True)


def _merge_metadata(existing: dict[str, Any], event: HyokaEvent) -> dict[str, Any]:
    merged = dict(existing or {})
    labels = dict(merged.get("labels") or {})
    labels.update(event.labels)
    attributes = dict(merged.get("attributes") or {})
    attributes.update(event.attributes)
    if event.source:
        merged["source"] = event.source
    if event.service_name:
        merged["service_name"] = event.service_name
    if labels:
        merged["labels"] = labels
    if attributes:
        merged["attributes"] = attributes
    merged["integration"] = "hyoka_event"
    return merged


def _recompute_summary(record: TraceRecord) -> dict[str, Any]:
    steps = record.steps or []
    tokens_total = 0
    cost_usd = 0.0
    step_latency_ms = 0
    status = record.status
    for step in steps:
        tokens_total += int(step.get("tokens_input") or 0)
        tokens_total += int(step.get("tokens_output") or 0)
        cost_usd += float(step.get("cost_usd") or 0.0)
        step_latency_ms += int(step.get("latency_ms") or 0)
        if step.get("status") == "error":
            status = "error"
    explicit_latency_ms = int((record.summary or {}).get("latency_ms") or 0)
    latency_ms = explicit_latency_ms if record.ended_at and explicit_latency_ms else step_latency_ms
    return {
        "latency_ms": latency_ms,
        "tokens_total": tokens_total,
        "cost_usd": cost_usd,
        "status": status,
    }


def ingest_event(session: Session, event: HyokaEvent) -> TraceRecord:
    event_key = f"event:{event.project_id}:{event.event_id}"
    existing_event = session.query(IdempotencyKeyRecord).filter_by(key=event_key).one_or_none()
    existing_trace = (
        session.query(TraceRecord)
        .filter_by(project_id=event.project_id, trace_id=event.trace_id)
        .one_or_none()
    )
    if existing_event and existing_trace:
        return existing_trace

    if not existing_trace:
        existing_trace = persist_trace(session, _initial_trace(event))

    if event.event_type == "trace_start":
        if event.input is not None:
            existing_trace.input = event.input if isinstance(event.input, dict) else {"input": event.input}
        if utc_comparable(event.timestamp) < utc_comparable(existing_trace.started_at):
            existing_trace.started_at = event.timestamp
    elif event.event_type == "trace_end":
        existing_trace.ended_at = event.timestamp
        existing_trace.final_output_preview = jsonish(event.output)
        existing_trace.status = event.status
        existing_trace.summary = {
            **(existing_trace.summary or {}),
            "latency_ms": event.duration_ms or (existing_trace.summary or {}).get("latency_ms", 0),
            "status": event.status,
        }
    else:
        steps = list(existing_trace.steps or [])
        if not any(step.get("step_id") == event.event_id for step in steps):
            steps.append(_event_to_step(event))
        existing_trace.steps = steps

    existing_trace.trace_metadata = _merge_metadata(existing_trace.trace_metadata, event)
    existing_trace.summary = _recompute_summary(existing_trace)
    if existing_trace.ended_at and utc_comparable(existing_trace.ended_at) < utc_comparable(existing_trace.started_at):
        existing_trace.ended_at = existing_trace.started_at

    payload = {
        "trace_id": existing_trace.trace_id,
        "project_id": existing_trace.project_id,
        "agent_name": existing_trace.agent_name,
        "session_id": existing_trace.session_id,
        "environment": existing_trace.environment,
        "started_at": existing_trace.started_at.isoformat(),
        "ended_at": existing_trace.ended_at.isoformat() if existing_trace.ended_at else None,
        "input": existing_trace.input,
        "steps": existing_trace.steps,
        "final_output_preview": existing_trace.final_output_preview,
        "summary": existing_trace.summary,
        "metadata": existing_trace.trace_metadata,
    }
    redacted = redact(payload)
    existing_trace.input = redacted["input"]
    existing_trace.steps = redacted["steps"]
    existing_trace.final_output_preview = jsonish(redacted.get("final_output_preview"))
    existing_trace.summary = redacted["summary"]
    existing_trace.trace_metadata = redacted["metadata"]
    existing_trace.payload_hash = content_hash(redacted)
    existing_trace.raw_payload = redacted

    if not existing_event:
        session.add(
            IdempotencyKeyRecord(
                key=event_key,
                scope=f"event:{event.project_id}",
                resource_type="event",
                resource_id=event.event_id,
            )
        )
    session.flush()
    return existing_trace
