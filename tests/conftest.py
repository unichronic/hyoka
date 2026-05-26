from __future__ import annotations

import os

os.environ.setdefault("HYOKA_DATABASE_URL", "sqlite:///./.hyoka/test-hyoka.db")
os.environ.setdefault("HYOKA_ARTIFACT_ROOT", "./.hyoka/test-artifacts")
os.environ.setdefault("HYOKA_INLINE_WORKER", "false")
os.environ.setdefault("HYOKA_LOG_LEVEL", "warning")

