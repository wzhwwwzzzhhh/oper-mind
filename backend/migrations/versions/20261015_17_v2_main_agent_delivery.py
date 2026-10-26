"""V2 主 Agent 的 runtime_kind 与输入／交付 1:1 扩展表。"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261015_17_v2_main_delivery"
down_revision = "20260905_16_p14_role_models"
branch_labels = None
depends_on = None


def _scalar(bind, statement: str) -> int:
    """读取单值计数；兼容 SQLite 与带绑定参数的方言。"""
    value = bind.exec_driver_sql(statement).scalar() if bind.dialect.name == "sqlite" else bind.execute(
        sa.text(statement)
    ).scalar()
    return int(value or 0)


def _sqlite_foreign_keys(bind, enabled: bool) -> None:
    """SQLite batch 重建被引用表前必须临时关闭外键检查，否则历史行会让 DROP TABLE 失败。"""
    if bind.dialect.name == "sqlite":
        bind.exec_driver_sql(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}")


def upgrade() -> None:
    """增加 Run 判别值，并创建 MainAgent 输入／交付扩展表。"""
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        _sqlite_foreign_keys(bind, enabled=False)
        try:
            with op.batch_alter_table("diagnosis_runs") as batch_op:
                batch_op.add_column(
                    sa.Column(
                        "runtime_kind",
                        sa.String(length=20),
                        nullable=False,
                        server_default="diagnosis",
                    )
                )
                batch_op.create_check_constraint(
                    "diagnosis_run_runtime_kind_valid",
                    "runtime_kind IN ('diagnosis', 'main_agent')",
                )
        finally:
            _sqlite_foreign_keys(bind, enabled=True)
    else:
        op.add_column(
            "diagnosis_runs",
            sa.Column(
                "runtime_kind",
                sa.String(length=20),
                nullable=False,
                server_default=sa.text("'diagnosis'"),
            ),
        )
        op.create_check_constraint(
            "diagnosis_run_runtime_kind_valid",
            "diagnosis_runs",
            "runtime_kind IN ('diagnosis', 'main_agent')",
        )

    op.create_table(
        "run_inputs",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("schema_version >= 1", name="run_input_schema_version_positive"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["diagnosis_runs.id"],
            name="fk_run_inputs_run_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("run_id", name="pk_run_inputs"),
    )
    op.create_table(
        "run_deliveries",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("schema_version >= 1", name="run_delivery_schema_version_positive"),
        sa.CheckConstraint(
            "kind IN ('answer', 'needs_input', 'comparison')",
            name="run_delivery_kind_valid",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["diagnosis_runs.id"],
            name="fk_run_deliveries_run_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("run_id", name="pk_run_deliveries"),
    )


def downgrade() -> None:
    """仅在不存在 V2 数据时移除扩展；任何主 Agent 事实都拒绝回滚。"""
    bind = op.get_bind()
    main_runs = _scalar(bind, "SELECT COUNT(*) FROM diagnosis_runs WHERE runtime_kind <> 'diagnosis'")
    inputs = _scalar(bind, "SELECT COUNT(*) FROM run_inputs")
    deliveries = _scalar(bind, "SELECT COUNT(*) FROM run_deliveries")
    if main_runs or inputs or deliveries:
        raise RuntimeError("拒绝不安全回滚：存在 V2 主 Agent Run 或输入／交付数据。")

    op.drop_table("run_deliveries")
    op.drop_table("run_inputs")
    if bind.dialect.name == "sqlite":
        _sqlite_foreign_keys(bind, enabled=False)
        try:
            with op.batch_alter_table("diagnosis_runs") as batch_op:
                batch_op.drop_constraint("diagnosis_run_runtime_kind_valid", type_="check")
                batch_op.drop_column("runtime_kind")
        finally:
            _sqlite_foreign_keys(bind, enabled=True)
    else:
        op.drop_constraint(
            "diagnosis_run_runtime_kind_valid",
            "diagnosis_runs",
            type_="check",
        )
        op.drop_column("diagnosis_runs", "runtime_kind")
