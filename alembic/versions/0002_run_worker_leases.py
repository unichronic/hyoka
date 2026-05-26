"""add run worker leases

Revision ID: 0002_run_worker_leases
Revises: 0001_initial
Create Date: 2026-05-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_run_worker_leases"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("worker_id", sa.String(length=128), nullable=True))
    op.add_column("runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "runs",
        sa.Column("execution_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_runs_status_lease", "runs", ["status", "lease_expires_at"])
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("runs", "execution_attempts", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_runs_status_lease", table_name="runs")
    op.drop_column("runs", "execution_attempts")
    op.drop_column("runs", "lease_expires_at")
    op.drop_column("runs", "worker_id")
