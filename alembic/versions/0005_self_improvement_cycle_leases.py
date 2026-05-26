"""add self improvement cycle leases

Revision ID: 0005_self_improvement_cycle_leases
Revises: 0004_self_improvement_cycles
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_self_improvement_cycle_leases"
down_revision = "0004_self_improvement_cycles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("self_improvement_cycles") as batch_op:
            batch_op.add_column(sa.Column("worker_id", sa.String(length=128), nullable=True))
            batch_op.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
            batch_op.add_column(
                sa.Column("execution_attempts", sa.Integer(), nullable=False, server_default="0")
            )
            batch_op.add_column(sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True))
            batch_op.create_index("ix_self_improvement_status_lease", ["status", "lease_expires_at"])
    else:
        op.add_column("self_improvement_cycles", sa.Column("worker_id", sa.String(length=128), nullable=True))
        op.add_column("self_improvement_cycles", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(
            "self_improvement_cycles",
            sa.Column("execution_attempts", sa.Integer(), nullable=False, server_default="0"),
        )
        op.add_column("self_improvement_cycles", sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True))
        op.create_index(
            "ix_self_improvement_status_lease",
            "self_improvement_cycles",
            ["status", "lease_expires_at"],
        )

    op.execute("UPDATE self_improvement_cycles SET queued_at = created_at WHERE queued_at IS NULL")


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("self_improvement_cycles") as batch_op:
            batch_op.drop_index("ix_self_improvement_status_lease")
            batch_op.drop_column("queued_at")
            batch_op.drop_column("execution_attempts")
            batch_op.drop_column("lease_expires_at")
            batch_op.drop_column("worker_id")
    else:
        op.drop_index("ix_self_improvement_status_lease", table_name="self_improvement_cycles")
        op.drop_column("self_improvement_cycles", "queued_at")
        op.drop_column("self_improvement_cycles", "execution_attempts")
        op.drop_column("self_improvement_cycles", "lease_expires_at")
        op.drop_column("self_improvement_cycles", "worker_id")
