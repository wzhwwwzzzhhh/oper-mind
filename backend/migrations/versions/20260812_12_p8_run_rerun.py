"""P8 调查重跑来源字段：diagnosis_runs.rerun_of_run_id 自引用列。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260812_12_p8_run_rerun"
down_revision = "20260811_11_p8_service_registration"
branch_labels = None
depends_on = None


def _raise_if_rerun_rows(bind) -> None:
    """downgrade 前置检查：存在重跑来源历史行时拒绝回滚。"""
    if bind.dialect.name == "sqlite":
        value = bind.exec_driver_sql(
            "SELECT COUNT(*) FROM diagnosis_runs WHERE rerun_of_run_id IS NOT NULL"
        ).scalar()
    else:
        value = bind.execute(
            sa.text("SELECT COUNT(*) FROM diagnosis_runs WHERE rerun_of_run_id IS NOT NULL")
        ).scalar()
    if value and int(value) > 0:
        raise RuntimeError("存在重跑来源记录，拒绝回滚 rerun_of_run_id 字段。")


def upgrade() -> None:
    """diagnosis_runs 增加重跑来源自引用列、外键与索引。"""
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        with op.batch_alter_table("diagnosis_runs") as batch_op:
            batch_op.add_column(sa.Column("rerun_of_run_id", sa.Uuid(), nullable=True))
            batch_op.create_foreign_key(
                "fk_diagnosis_runs_rerun_of_id",
                "diagnosis_runs",
                ["rerun_of_run_id"],
                ["id"],
                ondelete="RESTRICT",
            )
            batch_op.create_index("ix_diagnosis_runs_rerun_of_id", ["rerun_of_run_id"])
    else:
        op.add_column("diagnosis_runs", sa.Column("rerun_of_run_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            "fk_diagnosis_runs_rerun_of_id",
            "diagnosis_runs",
            "diagnosis_runs",
            ["rerun_of_run_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index("ix_diagnosis_runs_rerun_of_id", "diagnosis_runs", ["rerun_of_run_id"])


def downgrade() -> None:
    """移除重跑来源列；存在重跑历史行时拒绝回滚。"""
    connection = op.get_bind()
    _raise_if_rerun_rows(connection)
    if connection.dialect.name == "sqlite":
        with op.batch_alter_table("diagnosis_runs") as batch_op:
            batch_op.drop_index("ix_diagnosis_runs_rerun_of_id")
            batch_op.drop_constraint("fk_diagnosis_runs_rerun_of_id", type_="foreignkey")
            batch_op.drop_column("rerun_of_run_id")
    else:
        op.drop_index("ix_diagnosis_runs_rerun_of_id", table_name="diagnosis_runs")
        op.drop_constraint("fk_diagnosis_runs_rerun_of_id", "diagnosis_runs", type_="foreignkey")
        op.drop_column("diagnosis_runs", "rerun_of_run_id")
