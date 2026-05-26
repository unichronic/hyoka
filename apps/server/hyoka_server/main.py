from __future__ import annotations

import json
import logging
import time
from typing import Annotated, Any

import uvicorn
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from hyoka_schemas.hashing import content_hash
from hyoka_schemas.ids import new_id
from hyoka_schemas.integration import HyokaEvent
from hyoka_schemas.resources import (
    ApiKeyCreate,
    CandidateCreate,
    CompareRunsRequest,
    CompareRunsResponse,
    GateEvaluateRequest,
    PromotionCreate,
    RunCreate,
    SelfImproveCreate,
    SuiteCreate,
)
from hyoka_schemas.traces import TraceCreate
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from hyoka_server.database import SessionLocal, engine, get_session
from hyoka_server.logging import configure_logging
from hyoka_server.models import (
    ApiKeyRecord,
    ArtifactRecordModel,
    AuditEventRecord,
    Base,
    CandidateRecord,
    FailureClusterRecord,
    GateDecisionRecord,
    ImprovementProposalRecord,
    ManifestRecordModel,
    PromotionRecord,
    ReleaseGateRecord,
    RunCaseRecord,
    RunRecord,
    SelfImprovementCycleRecord,
    SuiteRecord,
    TraceRecord,
    now_utc,
)
from hyoka_server.security import (
    ApiKeyHeader,
    AuthContext,
    AuthHeader,
    authenticate_request,
    generate_api_key,
    hash_api_key,
    request_id_from_request,
    require_project,
    require_scope,
    scoped_project,
)
from hyoka_server.services.artifacts import artifact_store
from hyoka_server.services.audit import record_audit_event
from hyoka_server.services.autonomous import (
    execute_self_improvement_cycle,
    latest_cycles,
    queue_self_improvement_cycle,
)
from hyoka_server.services.evaluators import registry as evaluator_registry
from hyoka_server.services.failures import mine_failure_clusters
from hyoka_server.services.gates import evaluate_gate_policy
from hyoka_server.services.improvements import generate_candidate_patch
from hyoka_server.services.ingestion import ingest_event, persist_trace
from hyoka_server.services.manifests import build_manifest
from hyoka_server.services.otel import otlp_json_to_events
from hyoka_server.services.runs import execute_run
from hyoka_server.services.serializers import (
    api_key_to_created,
    api_key_to_read,
    artifact_to_read,
    audit_event_to_read,
    candidate_to_read,
    case_to_read,
    failure_cluster_to_read,
    gate_decision_to_read,
    improvement_proposal_to_read,
    manifest_to_read,
    promotion_to_read,
    run_to_read,
    self_improvement_cycle_to_read,
    suite_to_read,
    trace_to_read,
)
from hyoka_server.settings import get_settings

logger = logging.getLogger(__name__)

REQUEST_COUNT = Counter("hyoka_api_requests_total", "API requests", ["method", "path", "status"])
REQUEST_LATENCY = Histogram("hyoka_api_request_latency_seconds", "API request latency", ["method", "path"])


def _execute_run_background(run_id: str) -> None:
    with SessionLocal() as session:
        execute_run(session, run_id)


def get_auth_context(
    request: Request,
    session: Session = Depends(get_session),
    authorization: AuthHeader = None,
    x_hyoka_api_key: ApiKeyHeader = None,
) -> AuthContext:
    auth = authenticate_request(
        session=session,
        authorization=authorization,
        x_hyoka_api_key=x_hyoka_api_key,
    )
    request.state.auth = auth
    session.commit()
    return auth


def read_auth(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    require_scope(auth, "read")
    return auth


def write_auth(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    require_scope(auth, "write")
    return auth


def admin_auth(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    require_scope(auth, "admin")
    return auth


def _ensure_payload_project(auth: AuthContext, project_id: str) -> None:
    require_project(auth, project_id)


def _resolve_payload_project(auth: AuthContext, project_id: str) -> str:
    if not auth.all_projects and project_id == "default":
        return auth.project_id
    require_project(auth, project_id)
    return project_id


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.auto_migrate:
        Base.metadata.create_all(bind=engine)

    app = FastAPI(
        title="Hyoka API",
        version="0.1.0",
        description="Reliability and self-improvement layer for AI agents.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials="*" not in settings.allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or new_id("req")
        request.state.request_id = request_id
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.max_request_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": {"code": "REQUEST_TOO_LARGE", "message": "Request body is too large"}},
                headers={"X-Request-ID": request_id},
            )
        path = request.url.path
        method = request.method
        status = "500"
        start = time.perf_counter()
        try:
            response = await call_next(request)
            status = str(response.status_code)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            route = request.scope.get("route")
            normalized_path = getattr(route, "path", path)
            REQUEST_COUNT.labels(method=method, path=normalized_path, status=status).inc()
            REQUEST_LATENCY.labels(method=method, path=normalized_path).observe(time.perf_counter() - start)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    def readyz(session: Session = Depends(get_session)) -> dict[str, str]:
        session.execute(select(func.count(TraceRecord.id)))
        return {"status": "ready"}

    @app.get("/metrics", include_in_schema=False)
    def metrics(_: AuthContext = Depends(read_auth)) -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post("/v1/traces")
    def ingest_trace(
        trace: TraceCreate,
        request: Request,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        auth: AuthContext = Depends(write_auth),
        session: Session = Depends(get_session),
    ):
        trace.project_id = _resolve_payload_project(auth, trace.project_id)
        record = persist_trace(session, trace, idempotency_key=idempotency_key)
        record_audit_event(
            session,
            auth=auth,
            action="trace.ingest",
            resource_type="trace",
            resource_id=record.trace_id,
            project_id=record.project_id,
            request_id=request_id_from_request(request),
        )
        session.commit()
        session.refresh(record)
        return trace_to_read(record)

    @app.post("/v1/traces/batch")
    def ingest_traces_batch(
        traces: list[TraceCreate],
        request: Request,
        auth: AuthContext = Depends(write_auth),
        session: Session = Depends(get_session),
    ):
        created = []
        for trace in traces:
            trace.project_id = _resolve_payload_project(auth, trace.project_id)
            record = persist_trace(session, trace)
            created.append(trace_to_read(record))
        record_audit_event(
            session,
            auth=auth,
            action="trace.ingest_batch",
            resource_type="trace",
            project_id=traces[0].project_id if traces else scoped_project(auth),
            request_id=request_id_from_request(request),
            metadata={"count": len(created)},
        )
        session.commit()
        return created

    @app.post("/v1/events")
    def ingest_single_event(
        event: HyokaEvent,
        request: Request,
        auth: AuthContext = Depends(write_auth),
        session: Session = Depends(get_session),
    ):
        event.project_id = _resolve_payload_project(auth, event.project_id)
        record = ingest_event(session, event)
        record_audit_event(
            session,
            auth=auth,
            action="event.ingest",
            resource_type="trace",
            resource_id=record.trace_id,
            project_id=record.project_id,
            request_id=request_id_from_request(request),
        )
        session.commit()
        session.refresh(record)
        return trace_to_read(record)

    @app.post("/v1/events/batch")
    def ingest_events_batch(
        events: list[HyokaEvent],
        request: Request,
        auth: AuthContext = Depends(write_auth),
        session: Session = Depends(get_session),
    ):
        records_by_key: dict[tuple[str, str], TraceRecord] = {}
        for event in events:
            event.project_id = _resolve_payload_project(auth, event.project_id)
            record = ingest_event(session, event)
            records_by_key[(record.project_id, record.trace_id)] = record
        record_audit_event(
            session,
            auth=auth,
            action="event.ingest_batch",
            resource_type="trace",
            project_id=events[0].project_id if events else scoped_project(auth),
            request_id=request_id_from_request(request),
            metadata={"count": len(events), "trace_count": len(records_by_key)},
        )
        session.commit()
        return [trace_to_read(record) for record in records_by_key.values()]

    def _ingest_otlp_json(
        payload: dict[str, Any],
        request: Request,
        auth: AuthContext,
        session: Session,
    ):
        default_project = "default" if auth.all_projects else auth.project_id
        events = otlp_json_to_events(payload, default_project_id=default_project)
        records_by_key: dict[tuple[str, str], TraceRecord] = {}
        for event in events:
            event.project_id = _resolve_payload_project(auth, event.project_id)
            record = ingest_event(session, event)
            records_by_key[(record.project_id, record.trace_id)] = record
        record_audit_event(
            session,
            auth=auth,
            action="otel.ingest",
            resource_type="trace",
            project_id=events[0].project_id if events else scoped_project(auth),
            request_id=request_id_from_request(request),
            metadata={"event_count": len(events), "trace_count": len(records_by_key)},
        )
        session.commit()
        return {
            "ingested_events": len(events),
            "traces": [trace_to_read(record) for record in records_by_key.values()],
        }

    @app.post("/v1/otel/traces")
    def ingest_otel_traces(
        payload: dict[str, Any],
        request: Request,
        auth: AuthContext = Depends(write_auth),
        session: Session = Depends(get_session),
    ):
        return _ingest_otlp_json(payload, request, auth, session)

    @app.post("/v1/otel/v1/traces")
    def ingest_otel_exporter_traces(
        payload: dict[str, Any],
        request: Request,
        auth: AuthContext = Depends(write_auth),
        session: Session = Depends(get_session),
    ):
        return _ingest_otlp_json(payload, request, auth, session)

    @app.get("/v1/integrations/spec")
    def integration_spec(_: AuthContext = Depends(read_auth)) -> dict[str, Any]:
        return {
            "schema_version": "hyoka.integration.v1",
            "push": {
                "events": "POST /v1/events",
                "events_batch": "POST /v1/events/batch",
                "canonical_trace": "POST /v1/traces",
                "canonical_trace_batch": "POST /v1/traces/batch",
                "otel_otlp_json": "POST /v1/otel/v1/traces",
            },
            "pull": {
                "recommended_path": "/hyoka/traces",
                "content_types": ["application/json", "application/x-ndjson"],
                "cli": "hyoka scrape http://service:port/hyoka/traces",
            },
            "event_fields": {
                "required": ["trace_id", "type"],
                "recommended_labels": ["service", "agent", "environment", "version", "region"],
                "types": [
                    "trace_start",
                    "trace_end",
                    "llm_call",
                    "tool_call",
                    "retrieval",
                    "memory_read",
                    "memory_write",
                    "router_decision",
                    "error",
                    "custom_event",
                ],
            },
            "evaluators": {
                "registry": "GET /v1/evaluators",
                "config_key": "candidate.config.evaluators",
            },
            "self_improvement": {
                "cycle": "POST /v1/self-improvement/cycles",
                "list_cycles": "GET /v1/self-improvement/cycles",
                "execution": "Set execute_inline=false for worker-owned durable execution.",
                "patch_bundle_artifact_kind": "patch_bundle",
                "adapters": ["generic", "langgraph", "crewai", "autogen", "llamaindex", "openai_agents_sdk"],
            },
        }

    @app.get("/v1/evaluators")
    def list_evaluators(_: AuthContext = Depends(read_auth)) -> dict[str, Any]:
        return {
            "evaluators": evaluator_registry.names(),
            "config_examples": {
                "json_schema": {
                    "type": "json_schema",
                    "target": "final_output",
                    "schema": {"type": "object", "required": ["answer"]},
                },
                "llm_judge": {
                    "type": "llm_judge",
                    "url": "https://eval-runtime.internal/judge",
                    "model": "judge-model",
                    "rubric": "Score factuality and policy compliance.",
                },
            },
        }

    @app.get("/v1/traces")
    def list_traces(
        project_id: str | None = None,
        agent: str | None = None,
        environment: str | None = None,
        status: str | None = None,
        limit: int = Query(default=50, le=200),
        offset: int = 0,
        auth: AuthContext = Depends(read_auth),
        session: Session = Depends(get_session),
    ):
        project_id = scoped_project(auth, project_id)
        query = session.query(TraceRecord).filter(TraceRecord.project_id == project_id)
        if agent:
            query = query.filter(TraceRecord.agent_name == agent)
        if environment:
            query = query.filter(TraceRecord.environment == environment)
        if status:
            query = query.filter(TraceRecord.status == status)
        records = query.order_by(desc(TraceRecord.created_at)).offset(offset).limit(limit).all()
        return [trace_to_read(record) for record in records]

    @app.get("/v1/traces/{trace_id}")
    def get_trace(
        trace_id: str,
        project_id: str | None = None,
        auth: AuthContext = Depends(read_auth),
        session: Session = Depends(get_session),
    ):
        project_id = scoped_project(auth, project_id)
        record = session.query(TraceRecord).filter_by(project_id=project_id, trace_id=trace_id).one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail={"code": "TRACE_NOT_FOUND"})
        return trace_to_read(record)

    @app.post("/v1/suites")
    def create_suite(
        payload: SuiteCreate,
        request: Request,
        auth: AuthContext = Depends(write_auth),
        session: Session = Depends(get_session),
    ):
        payload.project_id = _resolve_payload_project(auth, payload.project_id)
        trace_ids = payload.trace_ids
        if not trace_ids:
            query = session.query(TraceRecord).filter(TraceRecord.project_id == payload.project_id)
            if agent := payload.query.get("agent"):
                query = query.filter(TraceRecord.agent_name == agent)
            if status := payload.query.get("status"):
                query = query.filter(TraceRecord.status == status)
            if environment := payload.query.get("environment"):
                query = query.filter(TraceRecord.environment == environment)
            trace_ids = [record.trace_id for record in query.order_by(TraceRecord.created_at.asc()).all()]
        if not trace_ids:
            raise HTTPException(status_code=400, detail={"code": "EMPTY_SUITE", "message": "No traces matched suite"})
        existing_count = (
            session.query(func.count(TraceRecord.id))
            .filter(TraceRecord.project_id == payload.project_id, TraceRecord.trace_id.in_(trace_ids))
            .scalar()
        )
        if existing_count != len(set(trace_ids)):
            raise HTTPException(status_code=400, detail={"code": "UNKNOWN_TRACE_IN_SUITE"})
        current_version = (
            session.query(func.max(SuiteRecord.version))
            .filter(SuiteRecord.project_id == payload.project_id, SuiteRecord.name == payload.name)
            .scalar()
            or 0
        )
        record = SuiteRecord(
            suite_id=new_id("suite"),
            project_id=payload.project_id,
            name=payload.name,
            version=current_version + 1,
            trace_ids=sorted(set(trace_ids)),
            trace_set_hash=content_hash(sorted(set(trace_ids))),
        )
        session.add(record)
        record_audit_event(
            session,
            auth=auth,
            action="suite.create",
            resource_type="suite",
            resource_id=record.suite_id,
            project_id=record.project_id,
            request_id=request_id_from_request(request),
            metadata={"trace_count": len(record.trace_ids), "version": record.version},
        )
        session.commit()
        session.refresh(record)
        return suite_to_read(record)

    @app.get("/v1/suites")
    def list_suites(
        project_id: str | None = None,
        auth: AuthContext = Depends(read_auth),
        session: Session = Depends(get_session),
    ):
        project_id = scoped_project(auth, project_id)
        records = session.query(SuiteRecord).filter_by(project_id=project_id).order_by(desc(SuiteRecord.created_at)).all()
        return [suite_to_read(record) for record in records]

    @app.get("/v1/suites/{suite_id}")
    def get_suite(
        suite_id: str,
        auth: AuthContext = Depends(read_auth),
        session: Session = Depends(get_session),
    ):
        record = session.query(SuiteRecord).filter_by(suite_id=suite_id).one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail={"code": "SUITE_NOT_FOUND"})
        require_project(auth, record.project_id)
        return suite_to_read(record)

    @app.post("/v1/candidates")
    def create_candidate(
        payload: CandidateCreate,
        request: Request,
        auth: AuthContext = Depends(write_auth),
        session: Session = Depends(get_session),
    ):
        payload.project_id = _resolve_payload_project(auth, payload.project_id)
        candidate_payload = payload.model_dump(mode="json")
        candidate_hash = content_hash(candidate_payload)
        existing = (
            session.query(CandidateRecord)
            .filter_by(project_id=payload.project_id, candidate_hash=candidate_hash)
            .one_or_none()
        )
        if existing:
            return candidate_to_read(existing)
        record = CandidateRecord(
            candidate_id=new_id("cand"),
            project_id=payload.project_id,
            name=payload.name,
            base_candidate_id=payload.base_candidate_id,
            targets=payload.targets,
            config=payload.config,
            candidate_metadata=payload.metadata,
            candidate_hash=candidate_hash,
        )
        session.add(record)
        record_audit_event(
            session,
            auth=auth,
            action="candidate.create",
            resource_type="candidate",
            resource_id=record.candidate_id,
            project_id=record.project_id,
            request_id=request_id_from_request(request),
        )
        session.commit()
        session.refresh(record)
        return candidate_to_read(record)

    @app.get("/v1/candidates")
    def list_candidates(
        project_id: str | None = None,
        auth: AuthContext = Depends(read_auth),
        session: Session = Depends(get_session),
    ):
        project_id = scoped_project(auth, project_id)
        records = (
            session.query(CandidateRecord).filter_by(project_id=project_id).order_by(desc(CandidateRecord.created_at)).all()
        )
        return [candidate_to_read(record) for record in records]

    @app.get("/v1/candidates/{candidate_id}")
    def get_candidate(
        candidate_id: str,
        auth: AuthContext = Depends(read_auth),
        session: Session = Depends(get_session),
    ):
        record = session.query(CandidateRecord).filter_by(candidate_id=candidate_id).one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail={"code": "CANDIDATE_NOT_FOUND"})
        require_project(auth, record.project_id)
        return candidate_to_read(record)

    @app.post("/v1/runs")
    def create_run(
        payload: RunCreate,
        background_tasks: BackgroundTasks,
        request: Request,
        auth: AuthContext = Depends(write_auth),
        session: Session = Depends(get_session),
    ):
        payload.project_id = _resolve_payload_project(auth, payload.project_id)
        suite = session.query(SuiteRecord).filter_by(suite_id=payload.suite_id).one_or_none()
        candidate = session.query(CandidateRecord).filter_by(candidate_id=payload.candidate_id).one_or_none()
        if not suite:
            raise HTTPException(status_code=404, detail={"code": "SUITE_NOT_FOUND"})
        if not candidate:
            raise HTTPException(status_code=404, detail={"code": "CANDIDATE_NOT_FOUND"})
        require_project(auth, suite.project_id)
        require_project(auth, candidate.project_id)
        if suite.project_id != candidate.project_id or payload.project_id != suite.project_id:
            raise HTTPException(status_code=400, detail={"code": "PROJECT_MISMATCH"})
        suite.locked_at = suite.locked_at or now_utc()
        run = RunRecord(
            run_id=new_id("run"),
            project_id=payload.project_id,
            suite_id=payload.suite_id,
            candidate_id=payload.candidate_id,
            mode=payload.mode,
            repeats=payload.repeats,
            status="queued",
            eval_config=payload.eval_config,
            aggregate={},
        )
        session.add(run)
        session.flush()
        for trace_id in suite.trace_ids:
            session.add(
                RunCaseRecord(
                    case_id=new_id("case"),
                    run_id=run.run_id,
                    trace_id=trace_id,
                    attempt=1,
                    status="pending",
                    replay_output={},
                    eval_results=[],
                    metrics={},
                )
            )
        record_audit_event(
            session,
            auth=auth,
            action="run.create",
            resource_type="run",
            resource_id=run.run_id,
            project_id=run.project_id,
            request_id=request_id_from_request(request),
            metadata={"suite_id": run.suite_id, "candidate_id": run.candidate_id, "mode": run.mode},
        )
        session.commit()
        session.refresh(run)
        if settings.inline_worker:
            background_tasks.add_task(_execute_run_background, run.run_id)
        return run_to_read(run)

    @app.get("/v1/runs")
    def list_runs(
        project_id: str | None = None,
        auth: AuthContext = Depends(read_auth),
        session: Session = Depends(get_session),
    ):
        project_id = scoped_project(auth, project_id)
        records = session.query(RunRecord).filter_by(project_id=project_id).order_by(desc(RunRecord.queued_at)).all()
        return [run_to_read(record) for record in records]

    @app.get("/v1/runs/{run_id}")
    def get_run(
        run_id: str,
        auth: AuthContext = Depends(read_auth),
        session: Session = Depends(get_session),
    ):
        record = session.query(RunRecord).filter_by(run_id=run_id).one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"})
        require_project(auth, record.project_id)
        return run_to_read(record)

    @app.get("/v1/runs/{run_id}/cases")
    def get_run_cases(
        run_id: str,
        auth: AuthContext = Depends(read_auth),
        session: Session = Depends(get_session),
    ):
        run = session.query(RunRecord).filter_by(run_id=run_id).one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"})
        require_project(auth, run.project_id)
        records = session.query(RunCaseRecord).filter_by(run_id=run_id).order_by(RunCaseRecord.id.asc()).all()
        return [case_to_read(record) for record in records]

    @app.post("/v1/runs/{run_id}/cancel")
    def cancel_run(
        run_id: str,
        request: Request,
        auth: AuthContext = Depends(write_auth),
        session: Session = Depends(get_session),
    ):
        run = session.query(RunRecord).filter_by(run_id=run_id).one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"})
        require_project(auth, run.project_id)
        run.cancel_requested = True
        record_audit_event(
            session,
            auth=auth,
            action="run.cancel",
            resource_type="run",
            resource_id=run.run_id,
            project_id=run.project_id,
            request_id=request_id_from_request(request),
        )
        session.commit()
        return run_to_read(run)

    @app.post("/v1/runs/compare")
    def compare_runs(
        payload: CompareRunsRequest,
        auth: AuthContext = Depends(read_auth),
        session: Session = Depends(get_session),
    ):
        baseline = session.query(RunRecord).filter_by(run_id=payload.baseline_run_id).one_or_none()
        candidate = session.query(RunRecord).filter_by(run_id=payload.candidate_run_id).one_or_none()
        if not baseline or not candidate:
            raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"})
        require_project(auth, baseline.project_id)
        require_project(auth, candidate.project_id)
        if baseline.project_id != candidate.project_id:
            raise HTTPException(status_code=400, detail={"code": "PROJECT_MISMATCH"})
        deltas = {
            "pass_rate": (candidate.aggregate or {}).get("pass_rate", 0) - (baseline.aggregate or {}).get("pass_rate", 0),
            "flaky_rate": (candidate.aggregate or {}).get("flaky_rate", 0) - (baseline.aggregate or {}).get("flaky_rate", 0),
            "p95_latency_ms": (candidate.aggregate or {}).get("p95_latency_ms", 0)
            - (baseline.aggregate or {}).get("p95_latency_ms", 0),
            "total_cost_usd": (candidate.aggregate or {}).get("total_cost_usd", 0)
            - (baseline.aggregate or {}).get("total_cost_usd", 0),
        }
        summary = (
            f"candidate pass_rate delta {deltas['pass_rate']:.3f}, "
            f"flaky_rate delta {deltas['flaky_rate']:.3f}, "
            f"p95 latency delta {deltas['p95_latency_ms']:.0f}ms"
        )
        return CompareRunsResponse(
            baseline_run_id=baseline.run_id,
            candidate_run_id=candidate.run_id,
            deltas=deltas,
            summary=summary,
        )

    @app.post("/v1/failures/mine")
    def mine_failures(
        run_id: str,
        request: Request,
        auth: AuthContext = Depends(write_auth),
        session: Session = Depends(get_session),
    ):
        run = session.query(RunRecord).filter_by(run_id=run_id).one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"})
        require_project(auth, run.project_id)
        if not session.query(RunCaseRecord).filter_by(run_id=run_id).first():
            raise HTTPException(status_code=404, detail={"code": "RUN_CASES_NOT_FOUND"})
        created = mine_failure_clusters(session, run)
        record_audit_event(
            session,
            auth=auth,
            action="failures.mine",
            resource_type="run",
            resource_id=run_id,
            project_id=run.project_id,
            request_id=request_id_from_request(request),
            metadata={"cluster_count": len(created)},
        )
        session.commit()
        return [failure_cluster_to_read(record) for record in created]

    @app.get("/v1/failure-clusters")
    def list_failure_clusters(
        run_id: str | None = None,
        project_id: str | None = None,
        auth: AuthContext = Depends(read_auth),
        session: Session = Depends(get_session),
    ):
        query = session.query(FailureClusterRecord)
        if run_id:
            run = session.query(RunRecord).filter_by(run_id=run_id).one_or_none()
            if not run:
                raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"})
            require_project(auth, run.project_id)
            query = query.filter_by(run_id=run_id)
        else:
            scoped = scoped_project(auth, project_id)
            run_ids = [run.run_id for run in session.query(RunRecord.run_id).filter_by(project_id=scoped).all()]
            query = query.filter(FailureClusterRecord.run_id.in_(run_ids))
        return [failure_cluster_to_read(record) for record in query.order_by(desc(FailureClusterRecord.created_at)).all()]

    @app.post("/v1/improvements/propose")
    def propose_improvement(
        cluster_id: str,
        request: Request,
        target: str = "prompt",
        create_candidate: bool = False,
        auth: AuthContext = Depends(write_auth),
        session: Session = Depends(get_session),
    ):
        cluster = session.query(FailureClusterRecord).filter_by(cluster_id=cluster_id).one_or_none()
        if not cluster:
            raise HTTPException(status_code=404, detail={"code": "FAILURE_CLUSTER_NOT_FOUND"})
        run = session.query(RunRecord).filter_by(run_id=cluster.run_id).one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"})
        require_project(auth, run.project_id)
        base_candidate = session.query(CandidateRecord).filter_by(candidate_id=run.candidate_id).one_or_none()
        cases = (
            session.query(RunCaseRecord)
            .filter(RunCaseRecord.run_id == run.run_id)
            .filter(RunCaseRecord.trace_id.in_(cluster.representative_trace_ids))
            .all()
        )
        proposal = generate_candidate_patch(
            cluster=cluster,
            run=run,
            base_candidate=base_candidate,
            cases=cases,
            target=target,
        )
        candidate_id = None
        if create_candidate:
            candidate_patch = proposal["candidate_patch"]
            candidate_payload = {
                "project_id": run.project_id,
                "name": f"{cluster.name}_{target}_candidate",
                "base_candidate_id": run.candidate_id,
                "targets": candidate_patch["targets"],
                "config": candidate_patch["config"],
                "metadata": {
                    "created_by": "hyoka_failure_miner",
                    "source_cluster_id": cluster.cluster_id,
                    "source_run_id": run.run_id,
                    **dict(candidate_patch.get("metadata") or {}),
                },
            }
            candidate_hash = content_hash(candidate_payload)
            candidate = (
                session.query(CandidateRecord)
                .filter_by(project_id=run.project_id, candidate_hash=candidate_hash)
                .one_or_none()
            )
            if not candidate:
                candidate = CandidateRecord(
                    candidate_id=new_id("cand"),
                    project_id=run.project_id,
                    name=candidate_payload["name"],
                    base_candidate_id=run.candidate_id,
                    targets=candidate_payload["targets"],
                    config=candidate_payload["config"],
                    candidate_metadata=candidate_payload["metadata"],
                    candidate_hash=candidate_hash,
                )
                session.add(candidate)
                session.flush()
            candidate_id = candidate.candidate_id
        record = ImprovementProposalRecord(
            proposal_id=new_id("prop"),
            cluster_id=cluster_id,
            candidate_id=candidate_id,
            target=target,
            method=proposal["method"],
            proposal=proposal,
        )
        session.add(record)
        record_audit_event(
            session,
            auth=auth,
            action="improvement.propose",
            resource_type="improvement_proposal",
            resource_id=record.proposal_id,
            project_id=run.project_id,
            request_id=request_id_from_request(request),
            metadata={"cluster_id": cluster_id, "candidate_id": candidate_id},
        )
        session.commit()
        session.refresh(record)
        return improvement_proposal_to_read(record)

    @app.get("/v1/improvement-proposals")
    def list_improvement_proposals(
        run_id: str | None = None,
        project_id: str | None = None,
        auth: AuthContext = Depends(read_auth),
        session: Session = Depends(get_session),
    ):
        query = session.query(ImprovementProposalRecord)
        if run_id:
            run = session.query(RunRecord).filter_by(run_id=run_id).one_or_none()
            if not run:
                raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"})
            require_project(auth, run.project_id)
            cluster_ids = [
                cluster.cluster_id
                for cluster in session.query(FailureClusterRecord.cluster_id).filter_by(run_id=run_id).all()
            ]
            query = query.filter(ImprovementProposalRecord.cluster_id.in_(cluster_ids))
        else:
            scoped = scoped_project(auth, project_id)
            run_ids = [run.run_id for run in session.query(RunRecord.run_id).filter_by(project_id=scoped).all()]
            cluster_ids = [
                cluster.cluster_id
                for cluster in session.query(FailureClusterRecord.cluster_id)
                .filter(FailureClusterRecord.run_id.in_(run_ids))
                .all()
            ]
            query = query.filter(ImprovementProposalRecord.cluster_id.in_(cluster_ids))
        return [
            improvement_proposal_to_read(record)
            for record in query.order_by(desc(ImprovementProposalRecord.created_at)).all()
        ]

    @app.post("/v1/self-improvement/cycles")
    def create_self_improvement_cycle(
        payload: SelfImproveCreate,
        request: Request,
        auth: AuthContext = Depends(write_auth),
        session: Session = Depends(get_session),
    ):
        payload.project_id = _resolve_payload_project(auth, payload.project_id)
        run = session.query(RunRecord).filter_by(run_id=payload.run_id).one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"})
        require_project(auth, run.project_id)
        if payload.project_id != run.project_id:
            raise HTTPException(status_code=400, detail={"code": "PROJECT_MISMATCH"})
        if run.status != "completed":
            raise HTTPException(status_code=409, detail={"code": "RUN_NOT_COMPLETED"})
        cycle = queue_self_improvement_cycle(session, payload, baseline_run=run)
        request_id = request_id_from_request(request)
        record_audit_event(
            session,
            auth=auth,
            action="self_improvement.cycle",
            resource_type="self_improvement_cycle",
            resource_id=cycle.cycle_id,
            project_id=cycle.project_id,
            request_id=request_id,
            metadata={"baseline_run_id": cycle.baseline_run_id, "status": cycle.status},
        )
        session.commit()
        if payload.execute_inline:
            executed = execute_self_improvement_cycle(
                session,
                cycle.cycle_id,
                worker_id=f"api:{request_id or cycle.cycle_id}",
            )
            if executed:
                cycle = executed
        session.refresh(cycle)
        return self_improvement_cycle_to_read(cycle)

    @app.get("/v1/self-improvement/cycles")
    def list_self_improvement_cycles(
        project_id: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        auth: AuthContext = Depends(read_auth),
        session: Session = Depends(get_session),
    ):
        scoped = scoped_project(auth, project_id)
        return [self_improvement_cycle_to_read(record) for record in latest_cycles(session, project_id=scoped, limit=limit)]

    @app.get("/v1/self-improvement/cycles/{cycle_id}")
    def get_self_improvement_cycle(
        cycle_id: str,
        auth: AuthContext = Depends(read_auth),
        session: Session = Depends(get_session),
    ):
        record = session.query(SelfImprovementCycleRecord).filter_by(cycle_id=cycle_id).one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail={"code": "SELF_IMPROVEMENT_CYCLE_NOT_FOUND"})
        require_project(auth, record.project_id)
        return self_improvement_cycle_to_read(record)

    @app.post("/v1/gates/evaluate")
    def evaluate_gate(
        payload: GateEvaluateRequest,
        request: Request,
        auth: AuthContext = Depends(write_auth),
        session: Session = Depends(get_session),
    ):
        payload.project_id = _resolve_payload_project(auth, payload.project_id)
        run = session.query(RunRecord).filter_by(run_id=payload.run_id).one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"})
        require_project(auth, run.project_id)
        if run.project_id != payload.project_id:
            raise HTTPException(status_code=400, detail={"code": "PROJECT_MISMATCH"})
        if run.status != "completed":
            raise HTTPException(status_code=409, detail={"code": "RUN_NOT_COMPLETED"})
        suite = session.query(SuiteRecord).filter_by(suite_id=run.suite_id).one()
        candidate = session.query(CandidateRecord).filter_by(candidate_id=run.candidate_id).one()
        gate_record = ReleaseGateRecord(
            gate_id=new_id("gate"),
            project_id=payload.project_id,
            name=payload.name,
            policy=payload.policy.model_dump(mode="json", exclude_none=True),
            policy_hash=content_hash(payload.policy.model_dump(mode="json", exclude_none=True)),
        )
        session.add(gate_record)
        cases = session.query(RunCaseRecord).filter_by(run_id=run.run_id).all()
        case_dicts = [
            {
                "case_id": case.case_id,
                "trace_id": case.trace_id,
                "status": case.status,
                "eval_results": case.eval_results,
            }
            for case in cases
        ]
        decision, reasons = evaluate_gate_policy(
            payload.policy,
            run.aggregate or {},
            case_dicts,
            has_manifest=bool(run.manifest_id),
        )
        manifest = build_manifest(
            session,
            run=run,
            suite=suite,
            candidate=candidate,
            decision=decision,
            gate_policy=payload.policy.model_dump(mode="json", exclude_none=True),
        )
        decision_record = GateDecisionRecord(
            decision_id=new_id("gd"),
            gate_id=gate_record.gate_id,
            run_id=run.run_id,
            candidate_id=run.candidate_id,
            decision=decision,
            pass_rate=float((run.aggregate or {}).get("pass_rate", 0.0)),
            flaky_rate=float((run.aggregate or {}).get("flaky_rate", 0.0)),
            blocking_reasons=reasons,
            manifest_id=manifest.manifest_id,
        )
        session.add(decision_record)
        record_audit_event(
            session,
            auth=auth,
            action="gate.evaluate",
            resource_type="gate_decision",
            resource_id=decision_record.decision_id,
            project_id=run.project_id,
            request_id=request_id_from_request(request),
            metadata={"run_id": run.run_id, "decision": decision},
        )
        session.commit()
        session.refresh(decision_record)
        return gate_decision_to_read(decision_record)

    @app.get("/v1/gates/{gate_id}/decisions")
    def list_gate_decisions(
        gate_id: str,
        auth: AuthContext = Depends(read_auth),
        session: Session = Depends(get_session),
    ):
        gate = session.query(ReleaseGateRecord).filter_by(gate_id=gate_id).one_or_none()
        if not gate:
            raise HTTPException(status_code=404, detail={"code": "GATE_NOT_FOUND"})
        require_project(auth, gate.project_id)
        records = session.query(GateDecisionRecord).filter_by(gate_id=gate_id).order_by(desc(GateDecisionRecord.created_at)).all()
        return [gate_decision_to_read(record) for record in records]

    @app.get("/v1/gate-decisions")
    def list_all_gate_decisions(
        project_id: str | None = None,
        auth: AuthContext = Depends(read_auth),
        session: Session = Depends(get_session),
    ):
        scoped = scoped_project(auth, project_id)
        gate_ids = [gate.gate_id for gate in session.query(ReleaseGateRecord.gate_id).filter_by(project_id=scoped).all()]
        records = (
            session.query(GateDecisionRecord)
            .filter(GateDecisionRecord.gate_id.in_(gate_ids))
            .order_by(desc(GateDecisionRecord.created_at))
            .limit(100)
            .all()
        )
        return [gate_decision_to_read(record) for record in records]

    @app.post("/v1/promotions")
    def create_promotion(
        payload: PromotionCreate,
        request: Request,
        auth: AuthContext = Depends(write_auth),
        session: Session = Depends(get_session),
    ):
        decision = session.query(GateDecisionRecord).filter_by(decision_id=payload.gate_decision_id).one_or_none()
        if not decision:
            raise HTTPException(status_code=404, detail={"code": "GATE_DECISION_NOT_FOUND"})
        run = session.query(RunRecord).filter_by(run_id=decision.run_id).one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"})
        require_project(auth, run.project_id)
        if payload.candidate_id != decision.candidate_id or payload.manifest_id != decision.manifest_id:
            raise HTTPException(status_code=400, detail={"code": "PROMOTION_DECISION_MISMATCH"})
        if decision.decision != "approved" and not payload.override:
            raise HTTPException(status_code=409, detail={"code": "GATE_NOT_APPROVED"})
        record = PromotionRecord(
            promotion_id=new_id("prom"),
            candidate_id=payload.candidate_id,
            gate_decision_id=payload.gate_decision_id,
            manifest_id=payload.manifest_id,
            environment=payload.environment,
            actor=payload.actor,
            override=payload.override,
        )
        session.add(record)
        record_audit_event(
            session,
            auth=auth,
            action="promotion.create",
            resource_type="promotion",
            resource_id=record.promotion_id,
            project_id=run.project_id,
            request_id=request_id_from_request(request),
            metadata={"override": record.override, "environment": record.environment},
        )
        session.commit()
        session.refresh(record)
        return promotion_to_read(record)

    @app.get("/v1/promotions")
    def list_promotions(
        project_id: str | None = None,
        auth: AuthContext = Depends(read_auth),
        session: Session = Depends(get_session),
    ):
        scoped = scoped_project(auth, project_id)
        candidate_ids = [
            candidate.candidate_id for candidate in session.query(CandidateRecord.candidate_id).filter_by(project_id=scoped).all()
        ]
        records = (
            session.query(PromotionRecord)
            .filter(PromotionRecord.candidate_id.in_(candidate_ids))
            .order_by(desc(PromotionRecord.created_at))
            .limit(100)
            .all()
        )
        return [promotion_to_read(record) for record in records]

    @app.get("/v1/artifacts/{artifact_id}")
    def get_artifact(
        artifact_id: str,
        include_content: bool = False,
        auth: AuthContext = Depends(read_auth),
        session: Session = Depends(get_session),
    ):
        record = session.query(ArtifactRecordModel).filter_by(artifact_id=artifact_id).one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail={"code": "ARTIFACT_NOT_FOUND"})
        require_project(auth, record.project_id)
        response = artifact_to_read(record).model_dump(mode="json")
        if include_content:
            body = artifact_store().read_json(record.uri)
            try:
                content = json.loads(body)
            except json.JSONDecodeError:
                content = body
            if content_hash(content) != record.content_hash:
                raise HTTPException(status_code=409, detail={"code": "ARTIFACT_INTEGRITY_CHECK_FAILED"})
            response["content"] = content
        return response

    @app.get("/v1/manifests/{run_id}")
    def get_manifest(
        run_id: str,
        auth: AuthContext = Depends(read_auth),
        session: Session = Depends(get_session),
    ):
        run = session.query(RunRecord).filter_by(run_id=run_id).one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND"})
        require_project(auth, run.project_id)
        record = session.query(ManifestRecordModel).filter_by(run_id=run_id).order_by(desc(ManifestRecordModel.created_at)).first()
        if not record:
            raise HTTPException(status_code=404, detail={"code": "MANIFEST_NOT_FOUND"})
        return manifest_to_read(record)

    @app.get("/v1/dashboard/summary")
    def dashboard_summary(
        project_id: str | None = None,
        auth: AuthContext = Depends(read_auth),
        session: Session = Depends(get_session),
    ):
        project_id = scoped_project(auth, project_id)
        latest_run = session.query(RunRecord).filter_by(project_id=project_id).order_by(desc(RunRecord.queued_at)).first()
        gate_ids = [gate.gate_id for gate in session.query(ReleaseGateRecord.gate_id).filter_by(project_id=project_id).all()]
        latest_gate = (
            session.query(GateDecisionRecord)
            .filter(GateDecisionRecord.gate_id.in_(gate_ids))
            .order_by(desc(GateDecisionRecord.created_at))
            .first()
        )
        return {
            "traces": session.query(func.count(TraceRecord.id)).filter_by(project_id=project_id).scalar() or 0,
            "suites": session.query(func.count(SuiteRecord.id)).filter_by(project_id=project_id).scalar() or 0,
            "candidates": session.query(func.count(CandidateRecord.id)).filter_by(project_id=project_id).scalar() or 0,
            "runs": session.query(func.count(RunRecord.id)).filter_by(project_id=project_id).scalar() or 0,
            "latest_run": run_to_read(latest_run).model_dump(mode="json") if latest_run else None,
            "latest_gate": gate_decision_to_read(latest_gate).model_dump(mode="json") if latest_gate else None,
        }

    @app.post("/v1/api-keys")
    def create_api_key(
        payload: ApiKeyCreate,
        request: Request,
        auth: AuthContext = Depends(admin_auth),
        session: Session = Depends(get_session),
    ):
        payload.project_id = _resolve_payload_project(auth, payload.project_id)
        prefix, secret = generate_api_key()
        record = ApiKeyRecord(
            key_id=new_id("key"),
            project_id=payload.project_id,
            name=payload.name,
            key_prefix=prefix,
            key_hash=hash_api_key(secret),
            scopes=payload.scopes,
            expires_at=payload.expires_at,
        )
        session.add(record)
        record_audit_event(
            session,
            auth=auth,
            action="api_key.create",
            resource_type="api_key",
            resource_id=record.key_id,
            project_id=record.project_id,
            request_id=request_id_from_request(request),
            metadata={"scopes": record.scopes},
        )
        session.commit()
        session.refresh(record)
        return api_key_to_created(record, secret)

    @app.get("/v1/api-keys")
    def list_api_keys(
        project_id: str | None = None,
        auth: AuthContext = Depends(admin_auth),
        session: Session = Depends(get_session),
    ):
        project_id = scoped_project(auth, project_id)
        records = session.query(ApiKeyRecord).filter_by(project_id=project_id).order_by(desc(ApiKeyRecord.created_at)).all()
        return [api_key_to_read(record) for record in records]

    @app.delete("/v1/api-keys/{key_id}")
    def revoke_api_key(
        key_id: str,
        request: Request,
        auth: AuthContext = Depends(admin_auth),
        session: Session = Depends(get_session),
    ):
        record = session.query(ApiKeyRecord).filter_by(key_id=key_id).one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail={"code": "API_KEY_NOT_FOUND"})
        require_project(auth, record.project_id)
        record.revoked_at = now_utc()
        record_audit_event(
            session,
            auth=auth,
            action="api_key.revoke",
            resource_type="api_key",
            resource_id=record.key_id,
            project_id=record.project_id,
            request_id=request_id_from_request(request),
        )
        session.commit()
        return api_key_to_read(record)

    @app.get("/v1/audit-events")
    def list_audit_events(
        project_id: str | None = None,
        limit: int = Query(default=100, le=500),
        auth: AuthContext = Depends(admin_auth),
        session: Session = Depends(get_session),
    ):
        project_id = scoped_project(auth, project_id)
        records = (
            session.query(AuditEventRecord)
            .filter_by(project_id=project_id)
            .order_by(desc(AuditEventRecord.created_at))
            .limit(limit)
            .all()
        )
        return [audit_event_to_read(record) for record in records]

    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run("hyoka_server.main:app", host=settings.service_host, port=settings.service_port, reload=False)


if __name__ == "__main__":
    run()
