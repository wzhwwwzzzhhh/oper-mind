"""Alembic 环境：只读取应用元数据数据库配置。"""

from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path
import sys

from alembic import context

# Alembic 直接执行时不保证当前目录是仓库根；只在迁移入口完成导入桥接。
BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
for path in (PROJECT_ROOT, BACKEND_ROOT):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)

from src.config import load_persistence_settings
from src.infrastructure.persistence.database import Base, create_app_engine
from src.infrastructure.persistence import models  # noqa: F401


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """从统一 Settings 读取迁移连接，不接触诊断数据源。"""
    return load_persistence_settings().database_url


def run_migrations_offline() -> None:
    """生成离线 SQL，不建立数据库连接。"""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """执行显式迁移；应用启动不会调用此函数。"""
    connectable = create_app_engine(_database_url())
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
