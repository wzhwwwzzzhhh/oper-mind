"""PostgreSQL 只读 Engine 工厂。"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url


def create_read_only_postgres_engine(dsn: str) -> Engine:
    """创建带连接与语句超时的 PostgreSQL 只读 Engine。"""
    url = make_url(dsn)
    if url.get_backend_name() != "postgresql":
        raise ValueError("PostgreSQL 服务 DSN 必须使用 PostgreSQL URL。")
    return create_engine(
        url.set(drivername="postgresql+psycopg"),
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 3,
            "options": "-c statement_timeout=3000",
        },
    )


def create_read_write_postgres_engine(dsn: str) -> Engine:
    """创建仅供受控靶场固定动作使用的短生命周期 Engine。"""
    url = make_url(dsn)
    if url.get_backend_name() != "postgresql":
        raise ValueError("受控靶场 DSN 必须使用 PostgreSQL URL。")
    return create_engine(
        url.set(drivername="postgresql+psycopg"),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
    )
