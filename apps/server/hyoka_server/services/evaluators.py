from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from hyoka_server.models import CandidateRecord, TraceRecord
from hyoka_server.settings import get_settings
from jsonschema import ValidationError, validate

EvalResult = dict[str, Any]


@dataclass(frozen=True)
class EvalContext:
    trace: TraceRecord
    candidate: CandidateRecord
    replay_output: dict[str, Any]

    @property
    def config(self) -> dict[str, Any]:
        return self.candidate.config or {}

    @property
    def final_output(self) -> Any:
        return self.replay_output.get("final_output")

    @property
    def final_output_text(self) -> str:
        return str(self.final_output or "")


EvaluatorFn = Callable[[EvalContext, dict[str, Any]], list[EvalResult]]


class EvaluatorRegistry:
    def __init__(self) -> None:
        self._evaluators: dict[str, EvaluatorFn] = {}

    def register(self, name: str, evaluator: EvaluatorFn) -> None:
        self._evaluators[name] = evaluator

    def names(self) -> list[str]:
        return sorted(self._evaluators)

    def evaluate(self, context: EvalContext, specs: list[dict[str, Any]]) -> list[EvalResult]:
        results: list[EvalResult] = []
        for spec in specs:
            evaluator_type = str(spec.get("type") or spec.get("evaluator") or "")
            evaluator = self._evaluators.get(evaluator_type)
            if not evaluator:
                results.append(
                    eval_result(
                        evaluator=evaluator_type or "unknown_evaluator",
                        passed=False,
                        score=0.0,
                        labels=["evaluator", "configuration_error"],
                        reason=f"unknown evaluator type: {evaluator_type}",
                        severity="critical",
                    )
                )
                continue
            results.extend(evaluator(context, spec))
        return results


def eval_result(
    *,
    evaluator: str,
    passed: bool,
    score: float,
    labels: list[str],
    reason: str,
    evidence_step_ids: list[str] | None = None,
    severity: str = "none",
    metadata: dict[str, Any] | None = None,
) -> EvalResult:
    result = {
        "evaluator": evaluator,
        "version": "1.0.0",
        "score": score,
        "passed": passed,
        "severity": severity if not passed else "none",
        "labels": labels,
        "reason": reason,
        "evidence_step_ids": evidence_step_ids or [],
    }
    if metadata:
        result["metadata"] = metadata
    return result


def _tool_names(trace: TraceRecord) -> list[str]:
    return [
        step.get("tool_name") or step.get("name") or "unknown_tool"
        for step in trace.steps
        if step.get("type") == "tool_call"
    ]


def _select_value(context: EvalContext, selector: str) -> Any:
    if selector in {"final_output", "output", "text"}:
        return context.final_output
    if selector == "replay_output":
        return context.replay_output
    if selector == "trace.input":
        return context.trace.input
    if selector == "trace.summary":
        return context.trace.summary
    if selector == "trace.steps":
        return context.trace.steps
    if selector.startswith("replay_output."):
        value: Any = context.replay_output
        for part in selector.split(".")[1:]:
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value
    return context.final_output


def _ensure_allowed_callback_url(url: str) -> None:
    settings = get_settings()
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        raise ValueError("callback URL must be an absolute http(s) URL")
    if not settings.enable_http_replay:
        raise ValueError("HTTP evaluator callbacks are disabled; set HYOKA_ENABLE_HTTP_REPLAY=true")
    allowed_hosts = settings.allowed_replay_hosts
    if not allowed_hosts:
        raise ValueError("HYOKA_HTTP_REPLAY_ALLOWED_HOSTS must list every evaluator host")
    if host not in allowed_hosts:
        raise ValueError(f"HTTP evaluator host is not allowed: {host}")


def final_output_present(context: EvalContext, spec: dict[str, Any]) -> list[EvalResult]:
    output_text = context.final_output_text
    return [
        eval_result(
            evaluator=str(spec.get("name") or "final_output_present"),
            passed=bool(output_text.strip()),
            score=1.0 if output_text.strip() else 0.0,
            labels=["final_output"],
            reason="final output is present" if output_text.strip() else "final output is empty",
            severity="major",
        )
    ]


def no_error_steps(context: EvalContext, spec: dict[str, Any]) -> list[EvalResult]:
    error_steps = [
        step
        for step in context.trace.steps
        if step.get("status") == "error" or step.get("type") == "error"
    ]
    return [
        eval_result(
            evaluator=str(spec.get("name") or "no_error_steps"),
            passed=not error_steps,
            score=1.0 if not error_steps else 0.0,
            labels=["trajectory", "error"],
            reason="no error steps recorded" if not error_steps else f"{len(error_steps)} error step(s) recorded",
            evidence_step_ids=[step.get("step_id") for step in error_steps if step.get("step_id")],
            severity="major",
        )
    ]


def required_tool_called(context: EvalContext, spec: dict[str, Any]) -> list[EvalResult]:
    tool = str(spec.get("tool") or spec.get("tool_name") or "")
    tools = _tool_names(context.trace)
    passed = tool in tools
    return [
        eval_result(
            evaluator=str(spec.get("name") or "required_tool_called"),
            passed=passed,
            score=1.0 if passed else 0.0,
            labels=["tool_use", "missing_required_tool"],
            reason=f"{tool} was called" if passed else f"{tool} was not called",
            severity="major",
            metadata={"tool": tool},
        )
    ]


def forbidden_tool_not_called(context: EvalContext, spec: dict[str, Any]) -> list[EvalResult]:
    tool = str(spec.get("tool") or spec.get("tool_name") or "")
    tools = _tool_names(context.trace)
    passed = tool not in tools
    return [
        eval_result(
            evaluator=str(spec.get("name") or "forbidden_tool_not_called"),
            passed=passed,
            score=1.0 if passed else 0.0,
            labels=["tool_use", "unsafe_tool_call"],
            reason=f"{tool} was not called" if passed else f"{tool} was called",
            severity="critical",
            metadata={"tool": tool},
        )
    ]


def output_regex(context: EvalContext, spec: dict[str, Any]) -> list[EvalResult]:
    pattern = str(spec.get("pattern") or spec.get("regex") or "")
    passed = re.search(pattern, context.final_output_text, re.I | re.S) is not None
    return [
        eval_result(
            evaluator=str(spec.get("name") or "output_regex"),
            passed=passed,
            score=1.0 if passed else 0.0,
            labels=["final_output", "format"],
            reason="output matched expected regex" if passed else "output did not match expected regex",
            severity="major",
            metadata={"pattern": pattern},
        )
    ]


def max_latency(context: EvalContext, spec: dict[str, Any]) -> list[EvalResult]:
    threshold = float(spec.get("max_ms") or spec.get("threshold_ms") or 0)
    latency = float(context.trace.summary.get("latency_ms", 0))
    passed = latency <= threshold
    return [
        eval_result(
            evaluator=str(spec.get("name") or "max_latency"),
            passed=passed,
            score=1.0 if passed else 0.0,
            labels=["latency"],
            reason=f"latency {latency:.0f}ms <= {threshold:.0f}ms"
            if passed
            else f"latency {latency:.0f}ms exceeds {threshold:.0f}ms",
            severity="minor",
            metadata={"threshold_ms": threshold, "actual_ms": latency},
        )
    ]


def max_cost(context: EvalContext, spec: dict[str, Any]) -> list[EvalResult]:
    threshold = float(spec.get("max_usd") or spec.get("threshold_usd") or 0)
    cost = float(context.trace.summary.get("cost_usd", 0))
    passed = cost <= threshold
    return [
        eval_result(
            evaluator=str(spec.get("name") or "max_cost"),
            passed=passed,
            score=1.0 if passed else 0.0,
            labels=["cost"],
            reason=f"cost ${cost:.6f} <= ${threshold:.6f}"
            if passed
            else f"cost ${cost:.6f} exceeds ${threshold:.6f}",
            severity="minor",
            metadata={"threshold_usd": threshold, "actual_usd": cost},
        )
    ]


def json_schema(context: EvalContext, spec: dict[str, Any]) -> list[EvalResult]:
    schema = spec.get("schema")
    selector = str(spec.get("target") or "final_output")
    if not isinstance(schema, dict):
        return [
            eval_result(
                evaluator=str(spec.get("name") or "json_schema"),
                passed=False,
                score=0.0,
                labels=["json_schema", "configuration_error"],
                reason="json_schema evaluator requires a schema object",
                severity="critical",
            )
        ]
    value = _select_value(context, selector)
    try:
        validate(instance=value, schema=schema)
        return [
            eval_result(
                evaluator=str(spec.get("name") or "json_schema"),
                passed=True,
                score=1.0,
                labels=["json_schema"],
                reason=f"{selector} matched JSON schema",
                metadata={"target": selector},
            )
        ]
    except ValidationError as exc:
        return [
            eval_result(
                evaluator=str(spec.get("name") or "json_schema"),
                passed=False,
                score=0.0,
                labels=["json_schema", "schema_mismatch"],
                reason=exc.message,
                severity="major",
                metadata={"target": selector, "path": list(exc.path)},
            )
        ]


def http_evaluator(context: EvalContext, spec: dict[str, Any]) -> list[EvalResult]:
    name = str(spec.get("name") or "http_evaluator")
    url = spec.get("url")
    if not url:
        return [
            eval_result(
                evaluator=name,
                passed=False,
                score=0.0,
                labels=["evaluator", "configuration_error"],
                reason="http evaluator url is missing",
                severity="critical",
            )
        ]
    try:
        _ensure_allowed_callback_url(str(url))
        timeout_seconds = float(spec.get("timeout_seconds") or get_settings().replay_timeout_seconds)
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(
                str(url),
                json={
                    "trace": {
                        "trace_id": context.trace.trace_id,
                        "project_id": context.trace.project_id,
                        "input": context.trace.input,
                        "steps": context.trace.steps,
                        "summary": context.trace.summary,
                        "metadata": context.trace.trace_metadata,
                    },
                    "candidate": {
                        "candidate_id": context.candidate.candidate_id,
                        "name": context.candidate.name,
                        "targets": context.candidate.targets,
                        "config": context.candidate.config,
                    },
                    "replay_output": context.replay_output,
                    "rubric": spec.get("rubric"),
                },
                headers={str(key): str(value) for key, value in dict(spec.get("headers") or {}).items()},
            )
            response.raise_for_status()
            payload = response.json()
        passed = bool(payload.get("passed"))
        return [
            eval_result(
                evaluator=name,
                passed=passed,
                score=float(payload.get("score", 1.0 if passed else 0.0)),
                labels=[str(label) for label in payload.get("labels", ["http_evaluator"])],
                reason=str(payload.get("reason", "http evaluator completed")),
                evidence_step_ids=[str(step_id) for step_id in payload.get("evidence_step_ids", [])],
                severity=str(payload.get("severity", "major")),
                metadata={"provider": spec.get("provider", "http")},
            )
        ]
    except Exception as exc:
        return [
            eval_result(
                evaluator=name,
                passed=False,
                score=0.0,
                labels=["evaluator", "execution_error"],
                reason=str(exc),
                severity="critical",
            )
        ]


def llm_judge(context: EvalContext, spec: dict[str, Any]) -> list[EvalResult]:
    judge_spec = {**spec, "type": "http_evaluator", "name": spec.get("name") or "llm_judge"}
    result = http_evaluator(context, judge_spec)[0]
    result["metadata"] = {
        **dict(result.get("metadata") or {}),
        "judge_model": spec.get("model"),
        "rubric_hash": spec.get("rubric_hash"),
    }
    if "llm_judge" not in result["labels"]:
        result["labels"] = ["llm_judge", *result["labels"]]
    return [result]


def _legacy_specs(config: dict[str, Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = [
        {"type": "final_output_present"},
        {"type": "no_error_steps"},
    ]
    specs.extend({"type": "required_tool_called", "tool": tool} for tool in config.get("required_tools", []))
    specs.extend({"type": "forbidden_tool_not_called", "tool": tool} for tool in config.get("forbidden_tools", []))
    if output_pattern := config.get("expected_output_regex"):
        specs.append({"type": "output_regex", "pattern": output_pattern})
    if max_latency_ms := config.get("max_latency_ms"):
        specs.append({"type": "max_latency", "max_ms": max_latency_ms})
    if max_cost_usd := config.get("max_cost_usd"):
        specs.append({"type": "max_cost", "max_usd": max_cost_usd})
    if schema := config.get("expected_output_schema"):
        specs.append({"type": "json_schema", "target": "final_output", "schema": schema})
    specs.extend({**spec, "type": "json_schema"} for spec in config.get("json_schema_evaluators", []))
    specs.extend({**spec, "type": "http_evaluator"} for spec in config.get("http_evaluators", []))
    specs.extend({**spec, "type": "llm_judge"} for spec in config.get("llm_judges", []))
    specs.extend(config.get("evaluators", []))
    return specs


registry = EvaluatorRegistry()
registry.register("final_output_present", final_output_present)
registry.register("no_error_steps", no_error_steps)
registry.register("required_tool_called", required_tool_called)
registry.register("forbidden_tool_not_called", forbidden_tool_not_called)
registry.register("output_regex", output_regex)
registry.register("max_latency", max_latency)
registry.register("max_cost", max_cost)
registry.register("json_schema", json_schema)
registry.register("http_evaluator", http_evaluator)
registry.register("llm_judge", llm_judge)


def evaluate_case(trace: TraceRecord, candidate: CandidateRecord, replay_output: dict[str, Any]) -> list[EvalResult]:
    context = EvalContext(trace=trace, candidate=candidate, replay_output=replay_output)
    return registry.evaluate(context, _legacy_specs(candidate.config or {}))
