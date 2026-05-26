from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse
from hyoka_schemas.hashing import content_hash
from hyoka_schemas.ids import new_id
from starlette.background import BackgroundTask

HYOKA_SERVER_URL = os.getenv("HYOKA_SERVER_URL", "http://localhost:8686").rstrip("/")
HYOKA_API_KEY = os.getenv("HYOKA_API_KEY")
HYOKA_PROJECT_ID = os.getenv("HYOKA_PROJECT_ID", "default")
UPSTREAM_BASE_URL = os.getenv("HYOKA_PROXY_UPSTREAM_BASE_URL", "https://api.openai.com").rstrip("/")
PROVIDER_API_KEY = os.getenv("HYOKA_PROVIDER_API_KEY") or os.getenv("OPENAI_API_KEY")
PROXY_PORT = int(os.getenv("HYOKA_PROXY_PORT", "8687"))

app = FastAPI(title="Hyoka OpenAI-Compatible Proxy", version="0.1.0")


def _headers_for_upstream(request: Request) -> dict[str, str]:
    excluded = {"host", "content-length"}
    headers = {key: value for key, value in request.headers.items() if key.lower() not in excluded}
    if PROVIDER_API_KEY:
        headers["authorization"] = f"Bearer {PROVIDER_API_KEY}"
    return headers


def _extract_output(path: str, response_json: Any) -> Any:
    if not isinstance(response_json, dict):
        return None
    if path.endswith("chat/completions"):
        choices = response_json.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            return message.get("content")
    if path.endswith("responses"):
        if "output_text" in response_json:
            return response_json["output_text"]
        output = response_json.get("output") or []
        text_parts = []
        for item in output:
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"}:
                    text_parts.append(content.get("text", ""))
        return "\n".join(text_parts) if text_parts else None
    return None


async def _emit_trace(
    *,
    path: str,
    request_json: Any,
    response_json: Any,
    status_code: int,
    latency_ms: int,
    started_at: datetime,
    ended_at: datetime,
) -> None:
    if not isinstance(request_json, dict):
        return
    usage = response_json.get("usage", {}) if isinstance(response_json, dict) else {}
    final_output = _extract_output(path, response_json)
    model = request_json.get("model") or (response_json.get("model") if isinstance(response_json, dict) else None)
    trace = {
        "trace_id": new_id("tr"),
        "project_id": request_json.get("metadata", {}).get("hyoka_project_id", HYOKA_PROJECT_ID)
        if isinstance(request_json.get("metadata"), dict)
        else HYOKA_PROJECT_ID,
        "agent_name": request_json.get("metadata", {}).get("hyoka_agent", "proxy-agent")
        if isinstance(request_json.get("metadata"), dict)
        else "proxy-agent",
        "environment": request_json.get("metadata", {}).get("hyoka_environment", "dev")
        if isinstance(request_json.get("metadata"), dict)
        else "dev",
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "input": {"path": path, "messages": request_json.get("messages"), "input": request_json.get("input")},
        "steps": [
            {
                "step_id": new_id("step"),
                "type": "llm_call",
                "name": path,
                "provider": "openai-compatible",
                "model": model,
                "input_hash": content_hash(request_json),
                "output_hash": content_hash(response_json),
                "output_preview": final_output,
                "latency_ms": latency_ms,
                "tokens_input": usage.get("prompt_tokens") or usage.get("input_tokens"),
                "tokens_output": usage.get("completion_tokens") or usage.get("output_tokens"),
                "status": "ok" if status_code < 400 else "error",
            }
        ],
        "final_output_preview": final_output,
        "summary": {
            "latency_ms": latency_ms,
            "tokens_total": usage.get("total_tokens", 0),
            "cost_usd": 0.0,
            "status": "ok" if status_code < 400 else "error",
        },
        "metadata": {"proxy_path": path, "provider_status_code": status_code},
    }
    try:
        headers = {"X-Hyoka-Api-Key": HYOKA_API_KEY} if HYOKA_API_KEY else {}
        async with httpx.AsyncClient(base_url=HYOKA_SERVER_URL, headers=headers, timeout=10.0) as client:
            await client.post("/v1/traces", json=trace)
    except Exception:
        # Proxy capture should not fail the caller's provider response.
        return


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(path: str, request: Request) -> Response:
    started_at = datetime.now(UTC)
    start = time.perf_counter()
    body = await request.body()
    request_json: Any = None
    if body:
        try:
            request_json = await request.json()
        except Exception:
            request_json = None
    upstream_url = f"{UPSTREAM_BASE_URL}/v1/{path}"
    headers = _headers_for_upstream(request)
    streaming_requested = isinstance(request_json, dict) and bool(request_json.get("stream"))
    if streaming_requested:
        client = httpx.AsyncClient(timeout=None)
        upstream_request = client.build_request(
            request.method,
            upstream_url,
            params=request.query_params,
            content=body,
            headers=headers,
        )
        upstream = await client.send(upstream_request, stream=True)
        excluded_headers = {"content-encoding", "transfer-encoding", "connection"}
        response_headers = {key: value for key, value in upstream.headers.items() if key.lower() not in excluded_headers}
        ended_at = datetime.now(UTC)
        latency_ms = int((time.perf_counter() - start) * 1000)
        if path in {"chat/completions", "responses", "completions"}:
            await _emit_trace(
                path=f"/v1/{path}",
                request_json=request_json,
                response_json={"stream": True, "status_code": upstream.status_code},
                status_code=upstream.status_code,
                latency_ms=latency_ms,
                started_at=started_at,
                ended_at=ended_at,
            )

        async def close_stream() -> None:
            await upstream.aclose()
            await client.aclose()

        return StreamingResponse(
            upstream.aiter_raw(),
            status_code=upstream.status_code,
            headers=response_headers,
            background=BackgroundTask(close_stream),
        )

    async with httpx.AsyncClient(timeout=None) as client:
        upstream = await client.request(
            request.method,
            upstream_url,
            params=request.query_params,
            content=body,
            headers=headers,
        )
    ended_at = datetime.now(UTC)
    latency_ms = int((time.perf_counter() - start) * 1000)
    response_json: Any = None
    try:
        response_json = upstream.json()
    except Exception:
        response_json = {"body_preview": upstream.text[:4000]}
    if path in {"chat/completions", "responses", "completions"}:
        await _emit_trace(
            path=f"/v1/{path}",
            request_json=request_json,
            response_json=response_json,
            status_code=upstream.status_code,
            latency_ms=latency_ms,
            started_at=started_at,
            ended_at=ended_at,
        )
    excluded_headers = {"content-encoding", "transfer-encoding", "connection"}
    headers = {key: value for key, value in upstream.headers.items() if key.lower() not in excluded_headers}
    return Response(content=upstream.content, status_code=upstream.status_code, headers=headers)


def run() -> None:
    uvicorn.run("hyoka_proxy.main:app", host="0.0.0.0", port=PROXY_PORT, reload=False)


if __name__ == "__main__":
    run()
