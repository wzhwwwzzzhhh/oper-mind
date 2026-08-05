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
