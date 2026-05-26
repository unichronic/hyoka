from __future__ import annotations

from contextvars import ContextVar

current_trace_id: ContextVar[str | None] = ContextVar("hyoka_current_trace_id", default=None)
current_steps: ContextVar[list[dict] | None] = ContextVar("hyoka_current_steps", default=None)

