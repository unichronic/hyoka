"""add self improvement cycles

Revision ID: 0004_self_improvement_cycles
Revises: 0003_security_artifacts_audit
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_self_improvement_cycles"
down_revision = "0003_security_artifacts_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "self_improvement_cycles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cycle_id", sa.String(length=96), nullable=False, unique=True),
        sa.Column("project_id", sa.String(length=96), nullable=False),
        sa.Column("baseline_run_id", sa.String(length=96), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_self_improvement_project_created", "self_improvement_cycles", ["project_id", "created_at"])
    op.create_index("ix_self_improvement_status", "self_improvement_cycles", ["status"])


def downgrade() -> None:
    op.drop_index("ix_self_improvement_status", table_name="self_improvement_cycles")
    op.drop_index("ix_self_improvement_project_created", table_name="self_improvement_cycles")
    op.drop_table("self_improvement_cycles")
