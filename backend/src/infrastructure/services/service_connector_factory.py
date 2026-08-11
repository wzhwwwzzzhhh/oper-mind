"""P8 服务 Connector 工厂：按服务类型派生受控只读 Connector。

动态注册服务与启动加载共用此工厂；DSN 以明文在此构造瞬间传入，不进日志。
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.exc import SQLAlchemyError

from src.domain.services import ServiceConnector, ServiceRegistrationData
from src.infrastructure.persistence.database import SessionFactory
from src.infrastructure.persistence.service_registry_repository import (
    SqlAlchemyServiceRegistryRepository,
)
from src.infrastructure.services.postgres_connector import PostgresServiceConnector
from src.infrastructure.services.redis_connector import RedisServiceConnector


def build_service_connector(
    kind: str,
    dsn: str | None,
    instance_id: str,
    title: str,
    masked_tail: str | None = None,
) -> ServiceConnector:
    """按服务类型派生受控只读 Connector（启动加载与动态注册共用）。"""
    if kind == "postgres":
        return PostgresServiceConnector(
            dsn,
            instance_id=instance_id,
            title=title,
            dsn_masked_tail=masked_tail,
        )
    if kind == "redis":
        return RedisServiceConnector(
            dsn,
            instance_id=instance_id,
            title=title,
            dsn_masked_tail=masked_tail,
        )
    raise ValueError(f"暂不支持的服务类型：{kind}")


def load_registered_services(
    session_factory: SessionFactory,
) -> Sequence[ServiceRegistrationData]:
    """读取全部已落库动态注册服务；应用库不可用或未迁移时诚实降级为空列表。"""
    session = session_factory()
    try:
        return SqlAlchemyServiceRegistryRepository(session).list()
    except SQLAlchemyError:
        return []
    finally:
        session.close()
