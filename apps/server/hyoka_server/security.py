from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Header, HTTPException, Request
from hyoka_schemas.ids import new_id
from sqlalchemy.orm import Session

from hyoka_server.models import ApiKeyRecord
from hyoka_server.settings import get_settings

ALL_PROJECTS = "*"
ALL_SCOPES = {"admin", "read", "write"}


@dataclass(frozen=True)
class AuthContext:
    project_id: str
    scopes: frozenset[str]
    key_id: str | None = None
    key_prefix: str | None = None
    static: bool = False

    @property
    def is_admin(self) -> bool:
        return "admin" in self.scopes

    @property
    def all_projects(self) -> bool:
        return self.project_id == ALL_PROJECTS


def unauthenticated_context() -> AuthContext:
    return AuthContext(project_id=ALL_PROJECTS, scopes=frozenset(ALL_SCOPES), key_id="anonymous-dev")


def generate_api_key() -> tuple[str, str]:
    raw = f"hyoka_live_{secrets.token_urlsafe(32)}"
    return raw[:20], raw


def hash_api_key(secret: str) -> str:
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def verify_api_key(secret: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(secret), expected_hash)


def _extract_api_key(authorization: str | None, x_hyoka_api_key: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return x_hyoka_api_key


def _static_context(secret: str) -> AuthContext | None:
    settings = get_settings()
    for entry in settings.allowed_api_keys:
        parts = entry.split(":", 2)
        if len(parts) == 3:
            project_id, expected_secret, scopes_text = parts
            scopes = frozenset(scope.strip() for scope in scopes_text.split("|") if scope.strip())
        else:
            project_id = ALL_PROJECTS
            expected_secret = entry
            scopes = frozenset(ALL_SCOPES)
        if hmac.compare_digest(secret, expected_secret):
            return AuthContext(
                project_id=project_id or ALL_PROJECTS,
                scopes=scopes or frozenset(ALL_SCOPES),
                key_id="static-env-key",
                key_prefix=secret[:8],
                static=True,
            )
    return None


def authenticate_request(
    *,
    session: Session,
    authorization: str | None,
    x_hyoka_api_key: str | None,
) -> AuthContext:
    settings = get_settings()
    if not settings.require_api_key:
        return unauthenticated_context()

    supplied = _extract_api_key(authorization, x_hyoka_api_key)
    if not supplied:
        raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "API key required"})

    if static_context := _static_context(supplied):
        return static_context

    prefix = supplied[:20]
    record = session.query(ApiKeyRecord).filter_by(key_prefix=prefix).one_or_none()
    now = datetime.now(UTC)
    if (
        not record
        or record.revoked_at is not None
        or (record.expires_at is not None and record.expires_at <= now)
        or not verify_api_key(supplied, record.key_hash)
    ):
        raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Invalid API key"})

    record.last_used_at = now
    session.flush()
    return AuthContext(
        project_id=record.project_id,
        scopes=frozenset(record.scopes or []),
        key_id=record.key_id,
        key_prefix=record.key_prefix,
    )


def require_scope(auth: AuthContext, scope: str) -> None:
    if "admin" in auth.scopes or scope in auth.scopes:
        return
    raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"Missing scope: {scope}"})


def require_project(auth: AuthContext, project_id: str) -> None:
    if auth.all_projects or auth.project_id == project_id:
        return
    raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Project access denied"})


def scoped_project(auth: AuthContext, requested_project_id: str | None = None) -> str:
    project_id = requested_project_id or ("default" if auth.all_projects else auth.project_id)
    require_project(auth, project_id)
    return project_id


def request_id_from_request(request: Request) -> str:
    return getattr(request.state, "request_id", None) or new_id("req")


AuthHeader = Annotated[str | None, Header(alias="Authorization")]
ApiKeyHeader = Annotated[str | None, Header(alias="X-Hyoka-Api-Key")]
