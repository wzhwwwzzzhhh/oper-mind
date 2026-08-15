"""P8 消息编辑与删除：messages 表新增 edited_at / archived_at 可空列。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260814_13_p8_message_edit_delete"
down_revision = "20260812_12_p8_run_rerun"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """messages 表增加 edited_at / archived_at 两列（可空，无数据回填）。"""
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        with op.batch_alter_table("messages") as batch_op:
            batch_op.add_column(sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True))
            batch_op.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    else:
        op.add_column("messages", sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column("messages", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """移除 edited_at / archived_at 两列。

    SQLite 上 drop_column 需要重建 messages 表，而 messages 被 diagnosis_runs
    外键引用，重建被引用表前必须临时关闭外键检查，否则 FOREIGN KEY constraint failed。
    """
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        try:
            with op.batch_alter_table("messages") as batch_op:
                batch_op.drop_column("archived_at")
                batch_op.drop_column("edited_at")
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    else:
        op.drop_column("messages", "archived_at")
        op.drop_column("messages", "edited_at")
