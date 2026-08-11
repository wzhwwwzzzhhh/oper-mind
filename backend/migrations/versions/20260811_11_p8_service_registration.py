"""P8 服务注册表与 service_id 约束放宽。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260811_11_p8_service_registration"
down_revision = "20260810_10_p8_model_mode"
branch_labels = None
depends_on = None

_SESSION_IDS = (
    "postgres-production",
    "postgres-staging",
    "postgres-target",
)
_SESSION_SERVICES_IDS = (
    "postgres-production",
    "postgres-staging",
    "postgres-target",
    "redis-production",
)


def _raise_if_dynamic_service_ids(bind) -> None:
    """downgrade 前置检查：存在动态 service_id 历史行时拒绝回滚。"""
    if bind.dialect.name == "sqlite":
        value = bind.exec_driver_sql(
            "SELECT COUNT(*) FROM session_services "
            "WHERE service_id NOT IN ('postgres-production', 'postgres-staging', 'postgres-target', 'redis-production')"
        ).scalar()
    else:
        value = bind.execute(
            sa.text(
                "SELECT COUNT(*) FROM session_services "
                "WHERE service_id NOT IN "
                "('postgres-production', 'postgres-staging', 'postgres-target', 'redis-production')"
            )
        ).scalar()
    if value and int(value) > 0:
        raise RuntimeError(
            "存在动态注册服务的会话关联记录，拒绝回滚 service_id 约束放宽。"
        )


def upgrade() -> None:
    """建 service_registry 表；放宽 sessions/session_services 的 service_id CHECK 白名单。"""
    connection = op.get_bind()
    op.create_table(
        "service_registry",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("instance_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("dsn_encrypted", sa.String(length=1000), nullable=True),
        sa.Column("dsn_nonce", sa.String(length=64), nullable=True),
        sa.Column("dsn_masked_tail", sa.String(length=8), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('postgres', 'redis')",
            name="service_registry_kind_valid",
        ),
        sa.CheckConstraint(
            "(dsn_encrypted IS NULL) = (dsn_nonce IS NULL)",
            name="service_registry_dsn_pair",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_service_registry"),
        sa.UniqueConstraint("instance_id", name="uq_service_registry_instance_id"),
    )
    if connection.dialect.name == "sqlite":
        with op.batch_alter_table("sessions") as batch_op:
            batch_op.drop_constraint("session_service_id_valid", type_="check")
    else:
        op.drop_constraint("session_service_id_valid", "sessions", type_="check")
    if connection.dialect.name == "sqlite":
        with op.batch_alter_table("session_services") as batch_op:
            batch_op.drop_constraint("session_services_service_id_valid", type_="check")
    else:
        op.drop_constraint("session_services_service_id_valid", "session_services", type_="check")


def downgrade() -> None:
    """恢复 service_id CHECK 白名单；存在动态 service_id 历史行时拒绝回滚。"""
    connection = op.get_bind()
    _raise_if_dynamic_service_ids(connection)
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        op.drop_table("service_registry")
        if sqlite:
            with op.batch_alter_table("sessions") as batch_op:
                batch_op.create_check_constraint(
                    "session_service_id_valid",
                    "service_id IS NULL OR service_id IN ("
                    + ", ".join(repr(item) for item in _SESSION_IDS)
                    + ")",
                )
        else:
            op.create_check_constraint(
                "session_service_id_valid",
                "sessions",
                "service_id IS NULL OR service_id IN ("
                + ", ".join(repr(item) for item in _SESSION_IDS)
                + ")",
            )
        if sqlite:
            with op.batch_alter_table("session_services") as batch_op:
                batch_op.create_check_constraint(
                    "session_services_service_id_valid",
                    "service_id IN (" + ", ".join(repr(item) for item in _SESSION_SERVICES_IDS) + ")",
                )
        else:
            op.create_check_constraint(
                "session_services_service_id_valid",
                "session_services",
                "service_id IN (" + ", ".join(repr(item) for item in _SESSION_SERVICES_IDS) + ")",
            )
    finally:
        if sqlite:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
