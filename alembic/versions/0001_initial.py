"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "traces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trace_id", sa.String(length=96), nullable=False),
        sa.Column("project_id", sa.String(length=96), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("agent_name", sa.String(length=200), nullable=False),
        sa.Column("session_id", sa.String(length=200), nullable=True),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("final_output_preview", sa.Text(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=80), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "trace_id", name="uq_traces_project_trace"),
    )
    op.create_index("ix_traces_project_created", "traces", ["project_id", "created_at"])
    op.create_index("ix_traces_agent_status", "traces", ["agent_name", "status"])

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=255), nullable=False, unique=True),
        sa.Column("scope", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "suites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("suite_id", sa.String(length=96), nullable=False, unique=True),
        sa.Column("project_id", sa.String(length=96), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("trace_ids", sa.JSON(), nullable=False),
        sa.Column("trace_set_hash", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("project_id", "name", "version", name="uq_suites_project_name_version"),
    )

    op.create_table(
        "candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("candidate_id", sa.String(length=96), nullable=False, unique=True),
        sa.Column("project_id", sa.String(length=96), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("base_candidate_id", sa.String(length=96), nullable=True),
        sa.Column("targets", sa.JSON(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("candidate_hash", sa.String(length=80), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "artifacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("artifact_id", sa.String(length=96), nullable=False, unique=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=80), nullable=False),
        sa.Column("uri", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(length=96), nullable=False, unique=True),
        sa.Column("project_id", sa.String(length=96), nullable=False),
        sa.Column("suite_id", sa.String(length=96), nullable=False),
        sa.Column("candidate_id", sa.String(length=96), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("repeats", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("eval_config", sa.JSON(), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("aggregate", sa.JSON(), nullable=False),
        sa.Column("artifact_id", sa.String(length=96), nullable=True),
        sa.Column("manifest_id", sa.String(length=96), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_runs_project_status", "runs", ["project_id", "status"])

    op.create_table(
        "run_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.String(length=96), nullable=False, unique=True),
        sa.Column("run_id", sa.String(length=96), nullable=False),
        sa.Column("trace_id", sa.String(length=96), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("replay_output", sa.JSON(), nullable=False),
        sa.Column("eval_results", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_run_cases_run", "run_cases", ["run_id"])

    op.create_table(
        "manifests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("manifest_id", sa.String(length=96), nullable=False, unique=True),
        sa.Column("run_id", sa.String(length=96), nullable=False),
        sa.Column("suite_hash", sa.String(length=80), nullable=False),
        sa.Column("candidate_hash", sa.String(length=80), nullable=False),
        sa.Column("trace_set_hash", sa.String(length=80), nullable=False),
        sa.Column("eval_config_hash", sa.String(length=80), nullable=False),
        sa.Column("replay_output_hash", sa.String(length=80), nullable=False),
        sa.Column("result_hash", sa.String(length=80), nullable=False),
        sa.Column("gate_policy_hash", sa.String(length=80), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("signature", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "release_gates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("gate_id", sa.String(length=96), nullable=False, unique=True),
        sa.Column("project_id", sa.String(length=96), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("policy", sa.JSON(), nullable=False),
        sa.Column("policy_hash", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "gate_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("decision_id", sa.String(length=96), nullable=False, unique=True),
        sa.Column("gate_id", sa.String(length=96), nullable=False),
        sa.Column("run_id", sa.String(length=96), nullable=False),
        sa.Column("candidate_id", sa.String(length=96), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("pass_rate", sa.Float(), nullable=False),
        sa.Column("flaky_rate", sa.Float(), nullable=False),
        sa.Column("blocking_reasons", sa.JSON(), nullable=False),
        sa.Column("manifest_id", sa.String(length=96), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "failure_clusters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cluster_id", sa.String(length=96), nullable=False, unique=True),
        sa.Column("run_id", sa.String(length=96), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("failure_type", sa.String(length=128), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("representative_trace_ids", sa.JSON(), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("suggested_targets", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "improvement_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("proposal_id", sa.String(length=96), nullable=False, unique=True),
        sa.Column("cluster_id", sa.String(length=96), nullable=False),
        sa.Column("candidate_id", sa.String(length=96), nullable=True),
        sa.Column("target", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=64), nullable=False),
        sa.Column("proposal", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "promotions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("promotion_id", sa.String(length=96), nullable=False, unique=True),
        sa.Column("candidate_id", sa.String(length=96), nullable=False),
        sa.Column("gate_decision_id", sa.String(length=96), nullable=False),
        sa.Column("manifest_id", sa.String(length=96), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("override", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("promotions")
    op.drop_table("improvement_proposals")
    op.drop_table("failure_clusters")
    op.drop_table("gate_decisions")
    op.drop_table("release_gates")
    op.drop_table("manifests")
    op.drop_index("ix_run_cases_run", table_name="run_cases")
    op.drop_table("run_cases")
    op.drop_index("ix_runs_project_status", table_name="runs")
    op.drop_table("runs")
    op.drop_table("artifacts")
    op.drop_table("candidates")
    op.drop_table("suites")
    op.drop_table("idempotency_keys")
    op.drop_index("ix_traces_agent_status", table_name="traces")
    op.drop_index("ix_traces_project_created", table_name="traces")
    op.drop_table("traces")
