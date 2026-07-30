"""创建 P4.2 固定修复审批、执行、验证与审计 schema。

Revision ID: 20260730_02_p4_actions
Revises: 20260726_01_p2
Create Date: 2026-07-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260730_02_p4_actions"
down_revision = "20260726_01_p2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建 P4.2 不可编辑 Proposal 及其审批、执行、验证和审计表。"""
    op.create_table(
        "action_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_run_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.String(length=160), nullable=False),
        sa.Column("action_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("mode", sa.String(length=12), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("target", sa.JSON(), nullable=False),
        sa.Column("root_cause_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("risk_summary", sa.Text(), nullable=False),
        sa.Column("verification_plan", sa.JSON(), nullable=False),
        sa.Column("next_event_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("failure_message", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending_approval', 'approved', 'rejected', 'expired', 'executing', 'verifying', 'verified', 'blocked', 'failed')",
            name="action_proposal_status_valid",
        ),
        sa.CheckConstraint("mode IN ('mock', 'target')", name="action_proposal_mode_valid"),
        sa.CheckConstraint("next_event_sequence >= 1", name="action_proposal_next_sequence_positive"),
        sa.ForeignKeyConstraint(["source_run_id"], ["diagnosis_runs.id"], name=op.f("fk_action_proposals_source_run_id_diagnosis_runs"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_action_proposals")),
        sa.UniqueConstraint("source_run_id", name="action_proposal_source_run_unique"),
    )
    op.create_index("ix_action_proposals_status_created_at", "action_proposals", ["status", "created_at"], unique=False)

    op.create_table(
        "action_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=12), nullable=False),
        sa.Column("actor", sa.String(length=80), nullable=False),
        sa.Column("comment", sa.String(length=500), nullable=True),
        sa.Column("action_digest", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("decision IN ('approve', 'reject')", name="action_approval_decision_valid"),
        sa.CheckConstraint("actor = 'local_operator'", name="action_approval_local_actor"),
        sa.ForeignKeyConstraint(["proposal_id"], ["action_proposals.id"], name=op.f("fk_action_approvals_proposal_id_action_proposals"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_action_approvals")),
        sa.UniqueConstraint("proposal_id", name="action_approval_proposal_unique"),
    )

    op.create_table(
        "action_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(length=12), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("precondition_summary", sa.String(length=500), nullable=True),
        sa.Column("action_summary", sa.String(length=500), nullable=True),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("failure_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("mode IN ('mock', 'target')", name="action_execution_mode_valid"),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'blocked', 'failed')", name="action_execution_status_valid"),
        sa.ForeignKeyConstraint(["proposal_id"], ["action_proposals.id"], name=op.f("fk_action_executions_proposal_id_action_proposals"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_action_executions")),
        sa.UniqueConstraint("proposal_id", name="action_execution_proposal_unique"),
    )

    op.create_table(
        "action_verifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=12), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("facts", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('verified', 'failed')", name="action_verification_status_valid"),
        sa.CheckConstraint("mode IN ('mock', 'target')", name="action_verification_mode_valid"),
        sa.ForeignKeyConstraint(["execution_id"], ["action_executions.id"], name=op.f("fk_action_verifications_execution_id_action_executions"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_action_verifications")),
        sa.UniqueConstraint("execution_id", name="action_verification_execution_unique"),
    )

    op.create_table(
        "action_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="action_event_sequence_positive"),
        sa.CheckConstraint(
            "type IN ('proposal_created', 'approval_recorded', 'execution_requested', 'execution_started', "
            "'precondition_checked', 'execution_completed', 'verification_started', 'verification_completed', "
            "'action_blocked', 'action_failed')",
            name="action_event_type_valid",
        ),
        sa.ForeignKeyConstraint(["proposal_id"], ["action_proposals.id"], name=op.f("fk_action_events_proposal_id_action_proposals"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_action_events")),
        sa.UniqueConstraint("proposal_id", "sequence", name="action_event_sequence_unique"),
    )
    op.create_index("ix_action_events_proposal_sequence", "action_events", ["proposal_id", "sequence"], unique=False)

    op.create_table(
        "action_idempotency_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint", sa.String(length=120), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=16), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("resource_type IN ('approval', 'execution')", name="action_idempotency_resource_type_valid"),
        sa.CheckConstraint("expires_at > created_at", name="action_idempotency_expiry_after_created"),
        sa.ForeignKeyConstraint(["proposal_id"], ["action_proposals.id"], name=op.f("fk_action_idempotency_keys_proposal_id_action_proposals"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_action_idempotency_keys")),
        sa.UniqueConstraint("proposal_id", "endpoint", "idempotency_key", name="action_idempotency_scope_unique"),
    )
    op.create_index("ix_action_idempotency_expires_at", "action_idempotency_keys", ["expires_at"], unique=False)


def downgrade() -> None:
    """按依赖逆序移除 P4.2 action schema。"""
    op.drop_index("ix_action_idempotency_expires_at", table_name="action_idempotency_keys")
    op.drop_table("action_idempotency_keys")
    op.drop_index("ix_action_events_proposal_sequence", table_name="action_events")
    op.drop_table("action_events")
    op.drop_table("action_verifications")
    op.drop_table("action_executions")
    op.drop_table("action_approvals")
    op.drop_index("ix_action_proposals_status_created_at", table_name="action_proposals")
    op.drop_table("action_proposals")
