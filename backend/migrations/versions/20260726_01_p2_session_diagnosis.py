"""创建 P2 会话诊断闭环核心 schema。

Revision ID: 20260726_01_p2
Revises:
Create Date: 2026-07-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260726_01_p2"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建 Session、Run、Event、Result 与幂等记录表。"""
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=True),
        sa.Column("incident_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('active', 'archived')", name="session_status_valid"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
    )
    op.create_index("ix_sessions_updated_at_id", "sessions", ["updated_at", "id"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        # run_id 是应用层校验的索引引用，避免与 diagnosis_runs.input_message_id 的循环外键。
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant', 'system')", name="message_role_valid"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name=op.f("fk_messages_session_id_sessions"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index("ix_messages_session_created_at_id", "messages", ["session_id", "created_at", "id"], unique=False)
    op.create_index("ix_messages_run_id", "messages", ["run_id"], unique=False)

    op.create_table(
        "diagnosis_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("trace_id", sa.Uuid(), nullable=False),
        sa.Column("input_message_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("next_event_sequence", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="diagnosis_run_status_valid",
        ),
        sa.CheckConstraint("next_event_sequence >= 1", name="diagnosis_run_next_sequence_positive"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name=op.f("fk_diagnosis_runs_session_id_sessions"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["input_message_id"], ["messages.id"], name=op.f("fk_diagnosis_runs_input_message_id_messages"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_diagnosis_runs")),
        sa.UniqueConstraint("input_message_id", name="diagnosis_run_input_message_unique"),
    )
    op.create_index("ix_diagnosis_runs_session_created_at_id", "diagnosis_runs", ["session_id", "created_at", "id"], unique=False)
    op.create_index("ix_diagnosis_runs_trace_id", "diagnosis_runs", ["trace_id"], unique=False)

    op.create_table(
        "run_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="run_event_sequence_positive"),
        sa.CheckConstraint(
            "type IN ('run_queued', 'run_started', 'route_decided', 'agent_start', "
            "'agent_done', 'conflict_checked', 'debate_round', 'report', 'reflection', "
            "'run_succeeded', 'run_failed', 'run_cancelled')",
            name="run_event_type_valid",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["diagnosis_runs.id"], name=op.f("fk_run_events_run_id_diagnosis_runs"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_run_events")),
        sa.UniqueConstraint("run_id", "sequence", name="run_event_sequence_unique"),
    )
    op.create_index("ix_run_events_run_sequence", "run_events", ["run_id", "sequence"], unique=False)

    op.create_table(
        "diagnosis_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("root_causes", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("impact", sa.JSON(), nullable=True),
        sa.Column("recommendations", sa.JSON(), nullable=False),
        sa.Column("risks", sa.JSON(), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("agent_summary", sa.JSON(), nullable=False),
        sa.Column("report_markdown", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "severity IN ('info', 'low', 'medium', 'high', 'critical')",
            name="diagnosis_result_severity_valid",
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="diagnosis_result_confidence_range"),
        sa.CheckConstraint("schema_version >= 1", name="diagnosis_result_schema_version_positive"),
        sa.ForeignKeyConstraint(["run_id"], ["diagnosis_runs.id"], name=op.f("fk_diagnosis_results_run_id_diagnosis_runs"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_diagnosis_results")),
        sa.UniqueConstraint("run_id", name="diagnosis_result_run_unique"),
    )

    op.create_table(
        "run_idempotency_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint", sa.String(length=120), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("expires_at > created_at", name="run_idempotency_expiry_after_created"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name=op.f("fk_run_idempotency_keys_session_id_sessions"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["diagnosis_runs.id"], name=op.f("fk_run_idempotency_keys_run_id_diagnosis_runs"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_run_idempotency_keys")),
        sa.UniqueConstraint("session_id", "endpoint", "idempotency_key", name="run_idempotency_scope_unique"),
    )
    op.create_index("ix_run_idempotency_expires_at", "run_idempotency_keys", ["expires_at"], unique=False)


def downgrade() -> None:
    """移除 P2 会话诊断闭环核心 schema。"""
    op.drop_index("ix_run_idempotency_expires_at", table_name="run_idempotency_keys")
    op.drop_table("run_idempotency_keys")
    op.drop_table("diagnosis_results")
    op.drop_index("ix_run_events_run_sequence", table_name="run_events")
    op.drop_table("run_events")
    op.drop_index("ix_diagnosis_runs_trace_id", table_name="diagnosis_runs")
    op.drop_index("ix_diagnosis_runs_session_created_at_id", table_name="diagnosis_runs")
    op.drop_table("diagnosis_runs")
    op.drop_index("ix_messages_run_id", table_name="messages")
    op.drop_index("ix_messages_session_created_at_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_sessions_updated_at_id", table_name="sessions")
    op.drop_table("sessions")
