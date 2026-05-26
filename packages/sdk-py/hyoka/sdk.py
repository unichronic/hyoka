from __future__ import annotations

import asyncio
import functools
import inspect
import os
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, ParamSpec, TypeVar

import httpx
from hyoka_schemas.hashing import content_hash
from hyoka_schemas.ids import new_id

from hyoka.context import current_steps, current_trace_id

P = ParamSpec("P")
R = TypeVar("R")


class HyokaClient:
    def __init__(
        self,
        *,
        api_url: str | None = None,
        api_key: str | None = None,
        project_id: str | None = None,
        agent: str | None = None,
        environment: str | None = None,
    ) -> None:
        self.api_url = (api_url or os.getenv("HYOKA_API_URL") or "http://localhost:8686").rstrip("/")
        self.api_key = api_key or os.getenv("HYOKA_API_KEY")
        self.project_id = project_id or os.getenv("HYOKA_PROJECT_ID") or "default"
        self.agent = agent or os.getenv("HYOKA_AGENT_NAME") or "agent"
        self.environment = environment or os.getenv("HYOKA_ENVIRONMENT") or "dev"
        self._buffer: list[dict[str, Any]] = []
        self._event_buffer: list[dict[str, Any]] = []

    def enqueue_trace(self, trace_payload: dict[str, Any]) -> None:
        trace_payload.setdefault("project_id", self.project_id)
        self._buffer.append(trace_payload)

    def enqueue_event(self, event_payload: dict[str, Any]) -> None:
        event_payload.setdefault("project_id", self.project_id)
        event_payload.setdefault("agent_name", self.agent)
        event_payload.setdefault("environment", self.environment)
        self._event_buffer.append(event_payload)

    def flush(self) -> None:
        if not self._buffer and not self._event_buffer:
            return
        headers = {"X-Hyoka-Api-Key": self.api_key} if self.api_key else {}
        with httpx.Client(base_url=self.api_url, headers=headers, timeout=30.0) as client:
            if self._buffer:
                response = client.post("/v1/traces/batch", json=self._buffer)
                response.raise_for_status()
            if self._event_buffer:
                response = client.post("/v1/events/batch", json=self._event_buffer)
                response.raise_for_status()
        self._buffer.clear()
        self._event_buffer.clear()

    async def aflush(self) -> None:
        if not self._buffer and not self._event_buffer:
            return
        headers = {"X-Hyoka-Api-Key": self.api_key} if self.api_key else {}
        async with httpx.AsyncClient(base_url=self.api_url, headers=headers, timeout=30.0) as client:
            if self._buffer:
                response = await client.post("/v1/traces/batch", json=self._buffer)
                response.raise_for_status()
            if self._event_buffer:
                response = await client.post("/v1/events/batch", json=self._event_buffer)
                response.raise_for_status()
        self._buffer.clear()
        self._event_buffer.clear()


default_client = HyokaClient()


def _preview(value: Any, max_chars: int = 2000) -> Any:
    if isinstance(value, str):
        return value[:max_chars]
    if isinstance(value, int | float | bool) or value is None:
        return value
    text = repr(value)
    return text[:max_chars]


def _append_step(step: dict[str, Any]) -> None:
    steps = current_steps.get()
    if steps is not None:
        steps.append(step)


def trace(
    *,
    agent: str | None = None,
    suite: str | None = None,
    environment: str | None = None,
    client: HyokaClient | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    hyoka_client = client or default_client

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                return await _run_trace_async(func, args, kwargs, hyoka_client, agent, environment, suite)

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            return _run_trace_sync(func, args, kwargs, hyoka_client, agent, environment, suite)

        return sync_wrapper

    return decorator


async def _run_trace_async(
    func: Callable[..., Awaitable[R]],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    client: HyokaClient,
    agent: str | None,
    environment: str | None,
    suite: str | None,
) -> R:
    trace_id = new_id("tr")
    steps: list[dict[str, Any]] = []
    token_trace = current_trace_id.set(trace_id)
    token_steps = current_steps.set(steps)
    started = datetime.now(UTC)
    start = time.perf_counter()
    status = "ok"
    result_preview: Any = None
    try:
        result = await func(*args, **kwargs)
        result_preview = _preview(result)
        return result
    except Exception as exc:
        status = "error"
        result_preview = str(exc)
        _append_step(
            {
                "step_id": new_id("step"),
                "type": "error",
                "name": type(exc).__name__,
                "output_preview": str(exc),
                "status": "error",
            }
        )
        raise
    finally:
        ended = datetime.now(UTC)
        latency_ms = int((time.perf_counter() - start) * 1000)
        client.enqueue_trace(
            {
                "trace_id": trace_id,
                "project_id": client.project_id,
                "agent_name": agent or client.agent,
                "environment": environment or client.environment,
                "started_at": started.isoformat(),
                "ended_at": ended.isoformat(),
                "input": {"args": _preview(args), "kwargs": _preview(kwargs)},
                "steps": steps,
                "final_output_preview": result_preview,
                "summary": {"latency_ms": latency_ms, "tokens_total": 0, "cost_usd": 0.0, "status": status},
                "metadata": {"suite": suite} if suite else {},
            }
        )
        current_trace_id.reset(token_trace)
        current_steps.reset(token_steps)


def _run_trace_sync(
    func: Callable[..., R],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    client: HyokaClient,
    agent: str | None,
    environment: str | None,
    suite: str | None,
) -> R:
    trace_id = new_id("tr")
    steps: list[dict[str, Any]] = []
    token_trace = current_trace_id.set(trace_id)
    token_steps = current_steps.set(steps)
    started = datetime.now(UTC)
    start = time.perf_counter()
    status = "ok"
    result_preview: Any = None
    try:
        result = func(*args, **kwargs)
        result_preview = _preview(result)
        return result
    except Exception as exc:
        status = "error"
        result_preview = str(exc)
        _append_step(
            {
                "step_id": new_id("step"),
                "type": "error",
                "name": type(exc).__name__,
                "output_preview": str(exc),
                "status": "error",
            }
        )
        raise
    finally:
        ended = datetime.now(UTC)
        latency_ms = int((time.perf_counter() - start) * 1000)
        client.enqueue_trace(
            {
                "trace_id": trace_id,
                "project_id": client.project_id,
                "agent_name": agent or client.agent,
                "environment": environment or client.environment,
                "started_at": started.isoformat(),
                "ended_at": ended.isoformat(),
                "input": {"args": _preview(args), "kwargs": _preview(kwargs)},
                "steps": steps,
                "final_output_preview": result_preview,
                "summary": {"latency_ms": latency_ms, "tokens_total": 0, "cost_usd": 0.0, "status": status},
                "metadata": {"suite": suite} if suite else {},
            }
        )
        current_trace_id.reset(token_trace)
        current_steps.reset(token_steps)


def tool(func: Callable[P, R]) -> Callable[P, R]:
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                status = "ok"
                return result
            except Exception as exc:
                result = exc
                status = "error"
                raise
            finally:
                _append_step(
                    {
                        "step_id": new_id("step"),
                        "type": "tool_call",
                        "tool_name": func.__name__,
                        "arguments_hash": content_hash({"args": _preview(args), "kwargs": _preview(kwargs)}),
                        "arguments_preview": {"args": _preview(args), "kwargs": _preview(kwargs)},
                        "response_hash": content_hash(_preview(result)),
                        "response_preview": _preview(result),
                        "latency_ms": int((time.perf_counter() - start) * 1000),
                        "status": status,
                    }
                )

        return async_wrapper  # type: ignore[return-value]

    @functools.wraps(func)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            status = "ok"
            return result
        except Exception as exc:
            result = exc
            status = "error"
            raise
        finally:
            _append_step(
                {
                    "step_id": new_id("step"),
                    "type": "tool_call",
                    "tool_name": func.__name__,
                    "arguments_hash": content_hash({"args": _preview(args), "kwargs": _preview(kwargs)}),
                    "arguments_preview": {"args": _preview(args), "kwargs": _preview(kwargs)},
                    "response_hash": content_hash(_preview(result)),
                    "response_preview": _preview(result),
                    "latency_ms": int((time.perf_counter() - start) * 1000),
                    "status": status,
                }
            )

    return sync_wrapper


def retrieval_event(name: str, query: Any, results: Any, *, latency_ms: int | None = None) -> None:
    _append_step(
        {
            "step_id": new_id("step"),
            "type": "retrieval",
            "name": name,
            "arguments_preview": _preview(query),
            "response_preview": _preview(results),
            "latency_ms": latency_ms,
            "status": "ok",
        }
    )


def memory_event(operation: str, key: str, value: Any = None, *, provenance: dict[str, Any] | None = None) -> None:
    step_type = {
        "read": "memory_read",
        "write": "memory_write",
        "update": "memory_update",
        "delete": "memory_delete",
    }.get(operation, "custom_event")
    _append_step(
        {
            "step_id": new_id("step"),
            "type": step_type,
            "name": key,
            "output_preview": _preview(value),
            "metadata": {"provenance": provenance or {}},
            "status": "ok",
        }
    )


def emit_event(
    event_type: str,
    *,
    trace_id: str | None = None,
    name: str | None = None,
    input: Any | None = None,
    output: Any | None = None,
    status: str = "ok",
    duration_ms: int | None = None,
    attributes: dict[str, Any] | None = None,
    labels: dict[str, str] | None = None,
    client: HyokaClient | None = None,
) -> None:
    """Buffer a framework-neutral event for Prometheus-style push ingestion."""
    hyoka_client = client or default_client
    hyoka_client.enqueue_event(
        {
            "event_id": new_id("evt"),
            "trace_id": trace_id or current_trace_id.get() or new_id("tr"),
            "type": event_type,
            "name": name,
            "input": _preview(input),
            "output": _preview(output),
            "status": status,
            "duration_ms": duration_ms,
            "attributes": attributes or {},
            "labels": labels or {},
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )


def observe_openai() -> None:
    """Reserved hook for OpenAI SDK wrapping.

    The first implementation exposes explicit decorators and event helpers.
    Proxy mode should be used for zero-code OpenAI-compatible capture until the
    SDK monkey patch is enabled.
    """


def flush() -> None:
    default_client.flush()


async def aflush() -> None:
    await default_client.aflush()


def flush_at_exit() -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        flush()
        return
    loop.create_task(default_client.aflush())
