"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
import uuid

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── services ────────────────────────────────────────────────────────────
    op.create_table(
        "services",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("repo_url", sa.Text, nullable=False),
        sa.Column("language", sa.String(50), nullable=False),
        sa.Column("spec_path", sa.Text),
        sa.Column("metadata", JSONB, default={}),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # ── endpoints ───────────────────────────────────────────────────────────
    op.create_table(
        "endpoints",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("service_id", UUID(as_uuid=True), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("operation_id", sa.String(255), nullable=False),
        sa.Column("method", sa.String(10)),
        sa.Column("path", sa.Text),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("spec_hash", sa.String(64)),
        sa.Column("source_hash", sa.String(64)),
        sa.Column("schema_hash", sa.String(64)),
        sa.Column("security_hash", sa.String(64)),
        sa.Column("metadata", JSONB, default={}),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.UniqueConstraint("service_id", "operation_id", name="uq_service_operation"),
    )

    # ── test_cases ──────────────────────────────────────────────────────────
    op.create_table(
        "test_cases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("endpoint_id", UUID(as_uuid=True), sa.ForeignKey("endpoints.id"), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("language", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), default="generated"),
        sa.Column("git_ref", sa.String(255)),
        sa.Column("fingerprint_at_generation", sa.String(64)),
        sa.Column("metadata", JSONB, default={}),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # ── pipeline_runs ───────────────────────────────────────────────────────
    op.create_table(
        "pipeline_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("service_id", UUID(as_uuid=True), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("status", sa.String(50), default="pending"),
        sa.Column("branch", sa.String(255)),
        sa.Column("commit_sha", sa.String(40)),
        sa.Column("triggered_by", sa.String(100)),
        sa.Column("options", JSONB, default={}),
        sa.Column("summary", JSONB, default={}),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── test_results ────────────────────────────────────────────────────────
    op.create_table(
        "test_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("test_case_id", UUID(as_uuid=True), sa.ForeignKey("test_cases.id")),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("error_message", sa.Text),
        sa.Column("stdout", sa.Text),
        sa.Column("stderr", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── feedback_items ──────────────────────────────────────────────────────
    op.create_table(
        "feedback_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("pipeline_runs.id")),
        sa.Column("endpoint_id", UUID(as_uuid=True), sa.ForeignKey("endpoints.id")),
        sa.Column("source", sa.String(50), nullable=False),  # auto | qe | ci
        sa.Column("feedback_type", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("fix_hint", sa.Text),
        sa.Column("applied", sa.Boolean, default=False),
        sa.Column("metadata", JSONB, default={}),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── learned_patterns ────────────────────────────────────────────────────
    op.create_table(
        "learned_patterns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("service_id", UUID(as_uuid=True), sa.ForeignKey("services.id")),
        sa.Column("pattern_type", sa.String(100), nullable=False),
        sa.Column("pattern_key", sa.String(255)),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("prompt_snippet", sa.Text),
        sa.Column("occurrence_count", sa.Integer, default=1),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── knowledge_docs ──────────────────────────────────────────────────────
    op.create_table(
        "knowledge_docs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("service_id", UUID(as_uuid=True), sa.ForeignKey("services.id")),
        sa.Column("doc_type", sa.String(50)),
        sa.Column("source_path", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("qdrant_ids", JSONB, default=[]),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── indexes ─────────────────────────────────────────────────────────────
    op.create_index("ix_endpoints_fingerprint", "endpoints", ["fingerprint"])
    op.create_index("ix_endpoints_service_id", "endpoints", ["service_id"])
    op.create_index("ix_test_cases_endpoint_id", "test_cases", ["endpoint_id"])
    op.create_index("ix_pipeline_runs_service_id", "pipeline_runs", ["service_id"])
    op.create_index("ix_feedback_items_endpoint_id", "feedback_items", ["endpoint_id"])
    op.create_index("ix_learned_patterns_service_id", "learned_patterns", ["service_id"])


def downgrade() -> None:
    for table in [
        "knowledge_docs", "learned_patterns", "feedback_items",
        "test_results", "pipeline_runs", "test_cases", "endpoints", "services",
    ]:
        op.drop_table(table)
