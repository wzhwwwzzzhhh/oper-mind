"""P12 将 service_registry kind CHECK 扩展为 MySQL。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260904_15_p12_mysql_kind"
down_revision = "20260815_14_merge_p8_heads"
branch_labels = None
depends_on = None

_CONSTRAINT = "service_registry_kind_valid"
_UPGRADE_CHECK = "kind IN ('postgres', 'redis', 'mysql')"
_DOWNGRADE_CHECK = "kind IN ('postgres', 'redis')"


def _replace_check(expression: str) -> None:
    """只替换 named CHECK；SQLite 使用仓库既有 batch 兼容路径。"""
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        with op.batch_alter_table("service_registry") as batch_op:
            batch_op.drop_constraint(_CONSTRAINT, type_="check")
            batch_op.create_check_constraint(_CONSTRAINT, expression)
    else:
        op.drop_constraint(_CONSTRAINT, "service_registry", type_="check")
        op.create_check_constraint(_CONSTRAINT, "service_registry", expression)


def upgrade() -> None:
    """保留全部现有行，只把合法 kind 扩展为 mysql。"""
    _replace_check(_UPGRADE_CHECK)


def downgrade() -> None:
    """存在 MySQL 注册记录时失败关闭，不修改或删除任何数据。"""
    connection = op.get_bind()
    count = connection.execute(
        sa.text("SELECT COUNT(*) FROM service_registry WHERE kind = 'mysql'")
    ).scalar()
    if count and int(count) > 0:
        raise RuntimeError("存在 MySQL 服务注册记录，拒绝不安全回滚。")
    _replace_check(_DOWNGRADE_CHECK)
