"""P6 模型 Provider 配置与 API Key 加密存储表。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260807_07_p6_model_provider"
down_revision = "20260807_06_p6_redis_monitor_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建 model_providers 表与 Provider 创建幂等键表；API Key 仅存密文。"""
    op.create_table(
        "model_providers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("api_key_encrypted", sa.String(length=1000), nullable=True),
        sa.Column("api_key_nonce", sa.String(length=64), nullable=True),
        sa.Column("active_endpoint", sa.String(length=20), nullable=True),
        sa.Column("verify_status", sa.String(length=20), nullable=False, server_default="unknown"),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verify_error_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "active_endpoint IS NULL OR active_endpoint IN ('diagnostic', 'judge')",
            name="model_provider_active_endpoint_valid",
        ),
        sa.CheckConstraint(
            "verify_status IN ('unknown', 'ok', 'failed', 'timeout')",
            name="model_provider_verify_status_valid",
        ),
        sa.CheckConstraint(
            "(api_key_encrypted IS NULL) = (api_key_nonce IS NULL)",
            name="model_provider_api_key_pair",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_model_providers"),
        sa.UniqueConstraint("active_endpoint", name="uq_model_providers_active_endpoint"),
    )
    op.create_table(
        "model_provider_idempotency_keys",
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.Uuid(), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="model_provider_idem_expiry_after_created",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["model_providers.id"],
            name="fk_model_provider_idem_provider_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("idempotency_key", name="pk_model_provider_idempotency_keys"),
    )
    op.create_index(
        "ix_model_provider_idem_expires_at",
        "model_provider_idempotency_keys",
        ["expires_at"],
    )


def downgrade() -> None:
    """删除模型 Provider 相关表。"""
    op.drop_index("ix_model_provider_idem_expires_at", table_name="model_provider_idempotency_keys")
    op.drop_table("model_provider_idempotency_keys")
    op.drop_table("model_providers")
