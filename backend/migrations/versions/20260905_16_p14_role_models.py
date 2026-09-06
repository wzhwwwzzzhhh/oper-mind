"""P14 角色→Provider 模型装配表。"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260905_16_p14_role_models"
down_revision = "20260904_15_p12_mysql_kind"
branch_labels = None
depends_on = None

_ROLES = ("coordinator", "db", "server", "log", "knowledge", "debate", "reflection")


def upgrade() -> None:
    """创建角色模型装配表；Provider 删除时级联清理，对应角色回退默认模型。"""
    op.create_table(
        "model_role_assignments",
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("provider_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"role IN ({', '.join(repr(role) for role in _ROLES)})",
            name="model_role_assignment_role_valid",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["model_providers.id"],
            name="fk_model_role_assignments_provider_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role", name="pk_model_role_assignments"),
    )
    op.create_index(
        "ix_model_role_assignments_provider_id",
        "model_role_assignments",
        ["provider_id"],
    )


def downgrade() -> None:
    """删除角色模型装配表。"""
    op.drop_index("ix_model_role_assignments_provider_id", table_name="model_role_assignments")
    op.drop_table("model_role_assignments")
