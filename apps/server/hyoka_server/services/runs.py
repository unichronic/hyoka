from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, datetime
from statistics import pstdev
from typing import Any
from urllib.parse import urlparse

import httpx
from hyoka_schemas.hashing import content_hash
from hyoka_server.models import CandidateRecord, RunCaseRecord, RunRecord, SuiteRecord, TraceRecord
from hyoka_server.services.artifacts import create_artifact
from hyoka_server.services.evaluators import eval_result, evaluate_case
from hyoka_server.services.manifests import build_manifest
from hyoka_server.services.workers import claim_run, extend_run_lease, release_run_lease
from hyoka_server.settings import get_settings
from sqlalchemy.orm import Session


def _now() -> datetime:
    return datetime.now(UTC)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)
    return float(ordered[index])


def _mock_replay(trace: TraceRecord, candidate: CandidateRecord, attempt: int) -> dict[str, Any]:
    config = candidate.config or {}
    output = config.get("override_final_output", trace.final_output_preview)
    return {
        "mode": "mock",
        "attempt": attempt,
        "source_trace_id": trace.trace_id,
        "candidate_id": candidate.candidate_id,
        "final_output": output,
        "steps": trace.steps,
        "output_hash": content_hash(output),
    }


def _ensure_allowed_replay_url(url: str) -> None:
    settings = get_settings()
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        raise ValueError("HTTP replay URL must be an absolute http(s) URL")
    if not settings.enable_http_replay:
        raise ValueError("HTTP replay is disabled; set HYOKA_ENABLE_HTTP_REPLAY=true")
    allowed_hosts = settings.allowed_replay_hosts
    if not allowed_hosts:
        raise ValueError("HYOKA_HTTP_REPLAY_ALLOWED_HOSTS must list every replay/evaluator host")
    if host not in allowed_hosts:
        raise ValueError(f"HTTP replay host is not allowed: {host}")


def _extract_final_output(payload: Any) -> Any:
    if isinstance(payload, dict):
        for key in ("final_output", "output", "response", "content", "text"):
            if key in payload:
                return payload[key]
    return payload


def _http_replay(trace: TraceRecord, candidate: CandidateRecord, attempt: int, mode: str) -> dict[str, Any]:
    config = candidate.config or {}
    replay_config = dict(config.get("replay") or {})
    url = replay_config.get("url")
    if not url:
        raise ValueError("candidate.config.replay.url is required for live, hybrid, and sandbox replay")
    _ensure_allowed_replay_url(str(url))
    method = str(replay_config.get("method") or "POST").upper()
    timeout_seconds = float(replay_config.get("timeout_seconds") or get_settings().replay_timeout_seconds)
    payload = {
        "trace_id": trace.trace_id,
        "project_id": trace.project_id,
        "mode": mode,
        "attempt": attempt,
        "input": trace.input,
        "source_steps": trace.steps,
        "candidate": {
            "candidate_id": candidate.candidate_id,
            "name": candidate.name,
            "targets": candidate.targets,
            "config": candidate.config,
            "metadata": candidate.candidate_metadata,
        },
    }
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.request(
            method,
            str(url),
            json=payload,
            headers={str(key): str(value) for key, value in dict(replay_config.get("headers") or {}).items()},
        )
        response.raise_for_status()
        try:
            response_payload: Any = response.json()
        except ValueError:
            response_payload = response.text
    return {
        "mode": mode,
        "attempt": attempt,
        "source_trace_id": trace.trace_id,
        "candidate_id": candidate.candidate_id,
        "final_output": _extract_final_output(response_payload),
        "response": response_payload,
        "output_hash": content_hash(response_payload),
    }


def replay_case(trace: TraceRecord, candidate: CandidateRecord, attempt: int, mode: str) -> dict[str, Any]:
    if mode == "mock":
        return _mock_replay(trace, candidate, attempt)
    return _http_replay(trace, candidate, attempt, mode)


def execute_run(
    session: Session,
    run_id: str,
    *,
    worker_id: str | None = None,
    already_claimed: bool = False,
) -> RunRecord:
    run = session.query(RunRecord).filter_by(run_id=run_id).one()
    suite = session.query(SuiteRecord).filter_by(suite_id=run.suite_id).one()
    candidate = session.query(CandidateRecord).filter_by(candidate_id=run.candidate_id).one()

    if run.status in {"completed", "failed", "cancelled"}:
        return run

    if not already_claimed:
        claimed = claim_run(session, run_id=run_id, worker_id=worker_id or "inline-worker")
        if not claimed:
            session.refresh(run)
            return run
        run = claimed
    else:
        run.status = "running"
        run.started_at = run.started_at or _now()
        extend_run_lease(session, run=run)
        session.commit()

    latencies: list[float] = []
    costs: list[float] = []
    failures_by_trace: dict[str, list[str]] = defaultdict(list)

    try:
        for case in (
            session.query(RunCaseRecord)
            .filter(RunCaseRecord.run_id == run.run_id)
            .order_by(RunCaseRecord.id.asc())
            .all()
        ):
            session.refresh(run)
            if run.cancel_requested:
                pending_cases = (
                    session.query(RunCaseRecord)
                    .filter(RunCaseRecord.run_id == run.run_id)
                    .filter(RunCaseRecord.status.in_(["pending", "running"]))
                    .all()
                )
                for pending_case in pending_cases:
                    pending_case.status = "skipped"
                run.status = "cancelled"
                run.completed_at = _now()
                release_run_lease(run)
                session.commit()
                return run

            if case.status in {"passed", "failed", "flaky", "skipped"}:
                continue

            trace = (
                session.query(TraceRecord)
                .filter(TraceRecord.project_id == run.project_id, TraceRecord.trace_id == case.trace_id)
                .one()
            )
            extend_run_lease(session, run=run)
            case.status = "running"
            case.started_at = _now()
            session.commit()

            attempt_results: list[bool] = []
            attempt_outputs: list[str] = []
            last_eval_results: list[dict[str, Any]] = []
            last_replay_output: dict[str, Any] = {}
            try:
                for attempt in range(1, run.repeats + 1):
                    replay_output = replay_case(trace, candidate, attempt, run.mode)
                    eval_results = evaluate_case(trace, candidate, replay_output)
                    passed = all(result["passed"] for result in eval_results)
                    attempt_results.append(passed)
                    attempt_outputs.append(str(replay_output.get("final_output") or ""))
                    last_eval_results = eval_results
                    last_replay_output = replay_output
            except Exception as exc:
                last_replay_output = {
                    "mode": run.mode,
                    "attempt": len(attempt_results) + 1,
                    "source_trace_id": trace.trace_id,
                    "candidate_id": candidate.candidate_id,
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                }
                last_eval_results = [
                    eval_result(
                        evaluator="replay_execution",
                        passed=False,
                        score=0.0,
                        labels=["replay", "execution_error"],
                        reason=str(exc),
                        severity="critical",
                    )
                ]
                attempt_results.append(False)

            pass_rate = sum(1 for result in attempt_results if result) / len(attempt_results)
            output_variance = len(set(attempt_outputs))
            flaky = run.repeats > 1 and (0 < pass_rate < 1 or output_variance > 1)
            case.status = "error" if last_replay_output.get("error") else "flaky" if flaky else "passed" if pass_rate == 1 else "failed"
            case.replay_output = last_replay_output
            case.eval_results = last_eval_results
            case.metrics = {
                "pass_rate": pass_rate,
                "repeats": run.repeats,
                "output_variants": output_variance,
                "score_stddev": pstdev([1.0 if result else 0.0 for result in attempt_results])
                if len(attempt_results) > 1
                else 0.0,
                "latency_ms": trace.summary.get("latency_ms", 0),
                "cost_usd": trace.summary.get("cost_usd", 0.0),
            }
            case.completed_at = _now()
            latencies.append(float(trace.summary.get("latency_ms", 0)))
            costs.append(float(trace.summary.get("cost_usd", 0.0)))
            for result in last_eval_results:
                if not result["passed"]:
                    failures_by_trace[trace.trace_id].extend(result.get("labels", []))
            session.commit()

        cases = session.query(RunCaseRecord).filter(RunCaseRecord.run_id == run.run_id).all()
        total = len(cases)
        passed_count = sum(1 for case in cases if case.status == "passed")
        flaky_count = sum(1 for case in cases if case.status == "flaky")
        failed_count = sum(1 for case in cases if case.status == "failed")
        error_count = sum(1 for case in cases if case.status == "error")
        run.status = "finalizing"
        run.aggregate = {
            "status": "completed",
            "case_count": total,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "error_count": error_count,
            "flaky_count": flaky_count,
            "pass_rate": passed_count / total if total else 0.0,
            "flaky_rate": flaky_count / total if total else 0.0,
            "p95_latency_ms": _p95(latencies),
            "total_cost_usd": sum(costs),
            "failure_labels": sorted({label for labels in failures_by_trace.values() for label in labels}),
        }
        report = {
            "run_id": run.run_id,
            "aggregate": run.aggregate,
            "cases": [
                {
                    "case_id": case.case_id,
                    "trace_id": case.trace_id,
                    "status": case.status,
                    "eval_results": case.eval_results,
                    "metrics": case.metrics,
                }
                for case in cases
            ],
        }
        artifact = create_artifact(
            session,
            kind="eval_report",
            payload=report,
            project_id=run.project_id,
            metadata={"run_id": run.run_id, "suite_id": run.suite_id, "candidate_id": run.candidate_id},
        )
        run.artifact_id = artifact.artifact_id
        run.status = "completed"
        run.completed_at = _now()
        release_run_lease(run)
        session.flush()
        manifest = build_manifest(
            session,
            run=run,
            suite=suite,
            candidate=candidate,
            decision="needs_review",
        )
        run.manifest_id = manifest.manifest_id
        session.commit()
        return run
    except Exception as exc:
        run.status = "failed"
        run.completed_at = _now()
        run.error_code = "RUN_EXECUTION_FAILED"
        run.error_message = str(exc)
        release_run_lease(run)
        session.commit()
        raise
