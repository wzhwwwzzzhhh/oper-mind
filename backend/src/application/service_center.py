"""P4.3 已注册服务中心、有限快照与服务会话创建用例。"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from src.application.errors import ServiceCenterUnavailableError, ServiceNotFoundError
from src.domain.records import DiagnosisRunCursor, RepositoryPage, SessionData
from src.domain.services import ServiceActivityData, ServiceConnector, ServiceRegistry, ServiceViewData
from src.infrastructure.persistence.database import SessionFactory
from src.infrastructure.persistence.repositories import SqlAlchemySessionRepository
from src.infrastructure.persistence.service_repositories import SqlAlchemyServiceActivityRepository


TransactionT = TypeVar("TransactionT")


class CreateServiceSessionCommand(BaseModel):
    """仅携带静态服务键的服务上下文会话创建命令。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    service_id: str = Field(min_length=1, max_length=64)


class ServiceCenterApplicationService:
    """编排静态 Connector、短事务 Session 创建和活动只读模型。"""

    def __init__(self, session_factory: SessionFactory, registry: ServiceRegistry | None) -> None:
        self._session_factory = session_factory
        self._registry = registry

    def list_services(self) -> list[ServiceViewData]:
        """读取所有静态注册服务的当前有限快照。"""
        registry = self._required_registry()
        return [
            ServiceViewData(definition=connector.definition(), snapshot=connector.health_snapshot())
            for connector in registry.list_connectors()
        ]

    def get_service(self, service_id: str) -> ServiceViewData:
        """读取一个静态服务的身份与当前有限快照。"""
        connector = self._get_connector(service_id)
        return ServiceViewData(definition=connector.definition(), snapshot=connector.health_snapshot())

    def create_service_session(self, command: CreateServiceSessionCommand) -> SessionData:
        """为静态服务创建 active Session，不创建 Message、Run 或外部读取。"""
        definition = self._get_connector(command.service_id).definition()

        def operation(session: Session) -> SessionData:
            value = SessionData(title=definition.session_title, service_id=definition.id)
            SqlAlchemySessionRepository(session).add(value)
            return value

        return _in_transaction(self._session_factory, operation)

    def list_activities(
        self,
        service_id: str,
        cursor: DiagnosisRunCursor | None,
        limit: int,
    ) -> RepositoryPage[ServiceActivityData, DiagnosisRunCursor]:
        """读取服务绑定会话中的 Run/Proposal/Verify 最小历史摘要。"""
        self._get_connector(service_id)
        session = self._session_factory()
        try:
            return SqlAlchemyServiceActivityRepository(session).list_by_service_id(service_id, cursor, limit)
        finally:
            session.close()

    def _required_registry(self) -> ServiceRegistry:
        """旧 P2 测试装配未提供服务中心时安全拒绝。"""
        if self._registry is None:
            raise ServiceCenterUnavailableError()
        return self._registry

    def _get_connector(self, service_id: str) -> ServiceConnector:
        """只从静态注册表取得 Connector，不接受动态服务定义。"""
        connector = self._required_registry().get_connector(service_id)
        if connector is None:
            raise ServiceNotFoundError()
        return connector


def _in_transaction(session_factory: SessionFactory, operation: Callable[[Session], TransactionT]) -> TransactionT:
    """为服务入口创建短事务，不在事务中执行外部读取。"""
    session = session_factory()
    try:
        result = operation(session)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
