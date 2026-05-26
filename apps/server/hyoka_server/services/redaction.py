from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

SECRET_KEY_RE = re.compile(
    r"(^|[_-])(api[_-]?key|authorization|bearer|password|secret|access[_-]?token|refresh[_-]?token|credential)([_-]|$)",
    re.I,
)
EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.+-])")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

REDACTED = "[redacted]"


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)):
                output[str(key)] = REDACTED
            else:
                output[str(key)] = redact(item)
        return output
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        return SSN_RE.sub(REDACTED, EMAIL_RE.sub(REDACTED, value))
    return value
