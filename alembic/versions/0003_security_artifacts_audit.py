"""add security, artifact scoping, and audit tables

Revision ID: 0003_security_artifacts_audit
Revises: 0002_run_worker_leases
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_security_artifacts_audit"
down_revision = "0002_run_worker_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.drop_constraint("candidates_candidate_hash_key", "candidates", type_="unique")
        op.create_unique_constraint("uq_candidates_project_hash", "candidates", ["project_id", "candidate_hash"])
        op.create_index("ix_candidates_project_created", "candidates", ["project_id", "created_at"])
    else:
        with op.batch_alter_table("candidates") as batch_op:
            batch_op.create_unique_constraint("uq_candidates_project_hash", ["project_id", "candidate_hash"])
            batch_op.create_index("ix_candidates_project_created", ["project_id", "created_at"])

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("artifacts") as batch_op:
            batch_op.add_column(sa.Column("project_id", sa.String(length=96), nullable=False, server_default="default"))
            batch_op.create_index("ix_artifacts_project_created", ["project_id", "created_at"])
            batch_op.alter_column("project_id", server_default=None)
    else:
        op.add_column(
            "artifacts",
            sa.Column("project_id", sa.String(length=96), nullable=False, server_default="default"),
        )
        op.create_index("ix_artifacts_project_created", "artifacts", ["project_id", "created_at"])
        op.alter_column("artifacts", "project_id", server_default=None)

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key_id", sa.String(length=96), nullable=False, unique=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("project_id", sa.String(length=96), nullable=False),
        sa.Column("key_prefix", sa.String(length=32), nullable=False),
        sa.Column("key_hash", sa.String(length=96), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("key_prefix", name="uq_api_keys_prefix"),
    )
    op.create_index("ix_api_keys_project", "api_keys", ["project_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(length=96), nullable=False, unique=True),
        sa.Column("project_id", sa.String(length=96), nullable=False),
        sa.Column("actor_key_id", sa.String(length=96), nullable=True),
        sa.Column("action", sa.String(length=96), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("request_id", sa.String(length=96), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_project_created", "audit_events", ["project_id", "created_at"])
    op.create_index("ix_audit_action", "audit_events", ["action"])


def downgrade() -> None:
    op.drop_index("ix_audit_action", table_name="audit_events")
    op.drop_index("ix_audit_project_created", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("ix_api_keys_project", table_name="api_keys")
    op.drop_table("api_keys")

    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("artifacts") as batch_op:
            batch_op.drop_index("ix_artifacts_project_created")
            batch_op.drop_column("project_id")
    else:
        op.drop_index("ix_artifacts_project_created", table_name="artifacts")
        op.drop_column("artifacts", "project_id")

    if op.get_bind().dialect.name == "postgresql":
        op.drop_index("ix_candidates_project_created", table_name="candidates")
        op.drop_constraint("uq_candidates_project_hash", "candidates", type_="unique")
        op.create_unique_constraint("candidates_candidate_hash_key", "candidates", ["candidate_hash"])
    else:
        with op.batch_alter_table("candidates") as batch_op:
            batch_op.drop_index("ix_candidates_project_created")
            batch_op.drop_constraint("uq_candidates_project_hash", type_="unique")
