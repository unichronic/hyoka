from __future__ import annotations

from typing import Any

from hyoka_schemas.ids import new_id
from hyoka_server.models import AuditEventRecord
from hyoka_server.security import AuthContext
from sqlalchemy.orm import Session


def record_audit_event(
    session: Session,
    *,
    auth: AuthContext,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    project_id: str = "default",
    request_id: str | None = None,
    status: str = "ok",
    metadata: dict[str, Any] | None = None,
) -> AuditEventRecord:
    record = AuditEventRecord(
        event_id=new_id("aud"),
        project_id=project_id,
        actor_key_id=auth.key_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        request_id=request_id,
        audit_metadata=metadata or {},
    )
    session.add(record)
    session.flush()
    return record
