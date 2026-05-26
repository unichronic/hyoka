from __future__ import annotations

import socket
import uuid
from datetime import UTC, datetime, timedelta

from hyoka_server.models import RunRecord
from hyoka_server.settings import get_settings
from sqlalchemy import and_, func, or_, update
from sqlalchemy.orm import Session


def default_worker_id() -> str:
    return f"{socket.gethostname()}-{uuid.uuid4().hex[:10]}"


def _now() -> datetime:
    return datetime.now(UTC)


def claim_run(
    session: Session,
    *,
    run_id: str,
    worker_id: str,
    lease_seconds: int | None = None,
) -> RunRecord | None:
    """Atomically claim a queued or stale running run.

    This is intentionally database-backed rather than in-process. It gives the
    MVP one clear execution owner per run and sets up the later transition to a
    durable workflow engine without coupling the API request lifecycle to work.
    """

    lease_seconds = lease_seconds or get_settings().worker_lease_seconds
    max_attempts = get_settings().worker_max_attempts
    now = _now()
    lease_until = now + timedelta(seconds=lease_seconds)
    claimed = (
        session.execute(
            update(RunRecord)
            .where(RunRecord.run_id == run_id)
            .where(RunRecord.cancel_requested.is_(False))
            .where(RunRecord.execution_attempts < max_attempts)
            .where(
                or_(
                    RunRecord.status == "queued",
                    and_(RunRecord.status == "running", RunRecord.lease_expires_at <= now),
                )
            )
            .values(
                status="running",
                worker_id=worker_id,
                lease_expires_at=lease_until,
                execution_attempts=RunRecord.execution_attempts + 1,
                started_at=func.coalesce(RunRecord.started_at, now),
            )
        ).rowcount
        or 0
    )
    if claimed != 1:
        session.rollback()
        return None
    session.commit()
    return session.query(RunRecord).filter_by(run_id=run_id).one()


def claim_next_run(
    session: Session,
    *,
    worker_id: str,
    lease_seconds: int | None = None,
) -> RunRecord | None:
    now = _now()
    candidate = (
        session.query(RunRecord)
        .filter(RunRecord.cancel_requested.is_(False))
        .filter(RunRecord.execution_attempts < get_settings().worker_max_attempts)
        .filter(
            or_(
                RunRecord.status == "queued",
                and_(RunRecord.status == "running", RunRecord.lease_expires_at <= now),
            )
        )
        .order_by(RunRecord.queued_at.asc())
        .first()
    )
    if not candidate:
        return None
    return claim_run(
        session,
        run_id=candidate.run_id,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
    )


def extend_run_lease(
    session: Session,
    *,
    run: RunRecord,
    lease_seconds: int | None = None,
) -> None:
    if not run.worker_id:
        return
    lease_seconds = lease_seconds or get_settings().worker_lease_seconds
    run.lease_expires_at = _now() + timedelta(seconds=lease_seconds)
    session.flush()


def release_run_lease(run: RunRecord) -> None:
    run.worker_id = None
    run.lease_expires_at = None
