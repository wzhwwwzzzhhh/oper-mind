"""同步 SQLAlchemy 应用元数据数据库基础设施。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """P2 ORM 模型的公共基类；P1.1d 不声明业务表。"""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _enable_sqlite_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
    """每个 SQLite 连接启用外键，避免测试与 PostgreSQL 语义漂移。"""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_app_engine(database_url: str) -> Engine:
    """创建应用元数据数据库 Engine，不创建表或执行迁移。"""
    url = make_url(database_url)
    backend_name = url.get_backend_name()
    if backend_name == "postgresql" and url.drivername != "postgresql+psycopg":
        raise ValueError("PostgreSQL 应用数据库必须使用 postgresql+psycopg URL。")
    if backend_name not in {"sqlite", "postgresql"}:
        raise ValueError("应用数据库仅支持 sqlite 或 postgresql+psycopg URL。")

    connect_args: dict[str, object] = {}
    if url.get_backend_name() == "sqlite":
        connect_args["check_same_thread"] = False

    engine = create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=url.get_backend_name() == "postgresql",
    )
    if url.get_backend_name() == "sqlite":
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


@dataclass(frozen=True)
class PersistenceRuntime:
    """可注入的 Engine 与单事务 Session factory。"""

    engine: Engine
    session_factory: sessionmaker[Session]


def create_persistence_runtime(database_url: str) -> PersistenceRuntime:
    """创建持久化运行时；调用方负责每个用例的事务边界。"""
    engine = create_app_engine(database_url)
    return PersistenceRuntime(
        engine=engine,
        session_factory=sessionmaker(bind=engine, expire_on_commit=False),
    )


SessionFactory = Callable[[], Session]
