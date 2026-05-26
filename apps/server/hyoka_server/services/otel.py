from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from hyoka_schemas.integration import HyokaEvent

_GENAI_LLM_OPS = {"chat", "text_completion", "embeddings", "generate_content"}
_GENAI_RETRIEVAL_OPS = {"retrieve", "query"}


def _decode_value(value: dict[str, Any] | Any) -> Any:
    if not isinstance(value, dict):
        return value
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        return int(value["intValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "boolValue" in value:
        return bool(value["boolValue"])
    if "arrayValue" in value:
        return [_decode_value(item) for item in value.get("arrayValue", {}).get("values", [])]
    if "kvlistValue" in value:
        return {
            item.get("key"): _decode_value(item.get("value", {}))
            for item in value.get("kvlistValue", {}).get("values", [])
            if item.get("key")
        }
    if "bytesValue" in value:
        return value["bytesValue"]
    return value


def _attrs(items: list[dict[str, Any]] | None) -> dict[str, Any]:
    return {item["key"]: _decode_value(item.get("value", {})) for item in items or [] if item.get("key")}


def _maybe_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return value
    if stripped[0] not in "[{":
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _time_from_unix_nano(value: str | int | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    return datetime.fromtimestamp(int(value) / 1_000_000_000, UTC)


def _duration_ms(span: dict[str, Any]) -> int | None:
    start = span.get("startTimeUnixNano")
    end = span.get("endTimeUnixNano")
    if not start or not end:
        return None
    duration = int(end) - int(start)
    return max(0, int(duration / 1_000_000))


def _status(span: dict[str, Any]) -> str:
    status = span.get("status") or {}
    code = status.get("code")
    return "error" if code in {2, "2", "STATUS_CODE_ERROR", "ERROR"} else "ok"


def _step_type(attrs: dict[str, Any], name: str) -> str:
    oi_kind = str(attrs.get("openinference.span.kind") or "").upper()
    genai_op = str(attrs.get("gen_ai.operation.name") or "").lower()
    if oi_kind == "LLM" or genai_op in _GENAI_LLM_OPS:
        return "llm_call"
    if oi_kind == "TOOL" or attrs.get("tool.name") or attrs.get("gen_ai.tool.name"):
        return "tool_call"
    if oi_kind in {"RETRIEVER", "RERANKER"} or genai_op in _GENAI_RETRIEVAL_OPS:
        return "retrieval"
    if oi_kind in {"AGENT", "CHAIN"} or "router" in name.lower():
        return "router_decision"
    return "custom_event"


def _input(attrs: dict[str, Any]) -> Any:
    for key in (
        "input.value",
        "gen_ai.prompt",
        "gen_ai.input.messages",
        "llm.input_messages",
        "gen_ai.request.messages",
    ):
        if key in attrs:
            return _maybe_json(attrs[key])
    return None


def _output(attrs: dict[str, Any]) -> Any:
    for key in (
        "output.value",
        "gen_ai.completion",
        "gen_ai.output.messages",
        "llm.output_messages",
        "gen_ai.response.text",
    ):
        if key in attrs:
            return _maybe_json(attrs[key])
    return None


def _resource_labels(resource_attrs: dict[str, Any], span_attrs: dict[str, Any]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for source, target in {
        "service.name": "service",
        "deployment.environment.name": "environment",
        "deployment.environment": "environment",
        "service.version": "version",
        "cloud.region": "region",
        "team.name": "team",
    }.items():
        if source in resource_attrs:
            labels[target] = str(resource_attrs[source])
    if "gen_ai.provider.name" in span_attrs:
        labels["provider"] = str(span_attrs["gen_ai.provider.name"])
    if "openinference.span.kind" in span_attrs:
        labels["openinference_kind"] = str(span_attrs["openinference.span.kind"])
    return labels


def _model(attrs: dict[str, Any]) -> str | None:
    for key in ("gen_ai.request.model", "gen_ai.response.model", "llm.model_name", "model_name"):
        if value := attrs.get(key):
            return str(value)
    return None


def otlp_json_to_events(payload: dict[str, Any], *, default_project_id: str) -> list[HyokaEvent]:
    events: list[HyokaEvent] = []
    for resource_span in payload.get("resourceSpans", []):
        resource_attrs = _attrs((resource_span.get("resource") or {}).get("attributes"))
        service_name = str(resource_attrs.get("service.name") or resource_attrs.get("service.namespace") or "otel")
        environment = str(
            resource_attrs.get("deployment.environment.name")
            or resource_attrs.get("deployment.environment")
            or "dev"
        )
        for scope_span in resource_span.get("scopeSpans") or resource_span.get("instrumentationLibrarySpans") or []:
            for span in scope_span.get("spans", []):
                span_attrs = _attrs(span.get("attributes"))
                name = str(span.get("name") or span_attrs.get("span.name") or "otel-span")
                trace_id = str(span.get("traceId") or "")
                span_id = str(span.get("spanId") or "")
                if not trace_id or not span_id:
                    continue
                event_type = _step_type(span_attrs, name)
                attributes = {
                    **span_attrs,
                    "otel": {
                        "span_id": span_id,
                        "trace_id": trace_id,
                        "scope": scope_span.get("scope") or scope_span.get("instrumentationLibrary") or {},
                    },
                }
                if model := _model(span_attrs):
                    attributes["model"] = model
                if provider := span_attrs.get("gen_ai.provider.name"):
                    attributes["provider"] = provider
                if tool_name := span_attrs.get("tool.name") or span_attrs.get("gen_ai.tool.name"):
                    attributes["tool_name"] = tool_name
                if "gen_ai.usage.input_tokens" in span_attrs:
                    attributes["tokens_input"] = span_attrs["gen_ai.usage.input_tokens"]
                if "gen_ai.usage.output_tokens" in span_attrs:
                    attributes["tokens_output"] = span_attrs["gen_ai.usage.output_tokens"]
                if "llm.token_count.prompt" in span_attrs:
                    attributes["tokens_input"] = span_attrs["llm.token_count.prompt"]
                if "llm.token_count.completion" in span_attrs:
                    attributes["tokens_output"] = span_attrs["llm.token_count.completion"]
                events.append(
                    HyokaEvent(
                        event_id=f"otel_{span_id}",
                        trace_id=f"otel_{trace_id}",
                        project_id=str(span_attrs.get("hyoka.project_id") or default_project_id),
                        source="opentelemetry",
                        service_name=service_name,
                        agent_name=str(span_attrs.get("gen_ai.agent.name") or span_attrs.get("agent.name") or service_name),
                        environment=environment,
                        session_id=span_attrs.get("session.id") or span_attrs.get("conversation.id"),
                        timestamp=_time_from_unix_nano(span.get("startTimeUnixNano")),
                        type=event_type,
                        name=name,
                        parent_event_id=f"otel_{span['parentSpanId']}" if span.get("parentSpanId") else None,
                        status=_status(span),
                        duration_ms=_duration_ms(span),
                        input=_input(span_attrs),
                        output=_output(span_attrs),
                        attributes=attributes,
                        labels=_resource_labels(resource_attrs, span_attrs),
                    )
                )
    return events
