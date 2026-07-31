"""P2.4 v1 API 的依赖装配。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from src.application.action_services import ActionApplicationService
from src.domain.actions import ActionMode
from src.domain.services import ServiceMode, ServiceRegistry
from src.application.contracts import DiagnosisExecutor, ResultAssembler
from src.application.services import RunApplicationService, SessionApplicationService
from src.application.service_center import ServiceCenterApplicationService
from src.config import load_persistence_settings
from src.infrastructure.diagnosis.coordinator_executor import CoordinatorDiagnosisExecutor
from src.infrastructure.diagnosis.demo_orders.action_executor import (
    MockOrdersIndexRepairExecutor,
    OrdersIndexRepairExecutor,
    PostgresOrdersIndexRepairExecutor,
)
from src.infrastructure.diagnosis.demo_orders.executor import (
    DemoOrdersInvestigationExecutor,
    RoutedDemoOrdersExecutor,
    UnavailableDemoOrdersExecutor,
)
from src.infrastructure.diagnosis.demo_orders.result_assembler import P4CompatibleResultAssembler
from src.infrastructure.diagnosis.demo_orders.service_connector import PostgresOrdersSlowQueryConnector
from src.infrastructure.diagnosis.demo_orders.settings import (
    DemoOrdersConfigurationError,
    DemoOrdersEvidenceSettings,
    EvidenceMode,
    load_demo_orders_evidence_settings,
)
from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler
from src.infrastructure.persistence.database import PersistenceRuntime, SessionFactory, create_persistence_runtime


@dataclass(frozen=True)
class V1Services:
    """v1 路由所需的可替换运行时依赖。"""

    session_factory: SessionFactory
    session_service: SessionApplicationService
    run_service: RunApplicationService
    action_service: ActionApplicationService | None = None
    service_center: ServiceCenterApplicationService | None = None


def build_v1_services(coordinator: object) -> V1Services:
    """装配默认持久化 Runtime 与受控 P4.1/P4.2/legacy 诊断适配。"""
    persistence_settings = load_persistence_settings()
    runtime = create_persistence_runtime(persistence_settings.database_url)
    return build_v1_services_for_runtime(
        runtime,
        coordinator,
        app_database_url=persistence_settings.database_url,
    )


def build_v1_services_for_runtime(
    runtime: PersistenceRuntime,
    coordinator: object,
    *,
    demo_orders_settings: DemoOrdersEvidenceSettings | None = None,
    app_database_url: str | None = None,
) -> V1Services:
    """用给定 Runtime 构造服务，供临时库测试安全替换。"""
    executor, result_assembler, action_executor, action_mode = _build_diagnosis_components(
        coordinator,
        demo_orders_settings=demo_orders_settings,
        app_database_url=app_database_url,
    )
    session_factory = runtime.session_factory
    action_service = ActionApplicationService(session_factory, action_executor)
    return V1Services(
        session_factory=session_factory,
        session_service=SessionApplicationService(session_factory),
        run_service=RunApplicationService(
            session_factory,
            executor,
            result_assembler,
            action_service=action_service,
            action_mode=action_mode,
        ),
        action_service=action_service,
        service_center=_build_service_center(session_factory, demo_orders_settings, app_database_url),
    )


def _build_diagnosis_components(
    coordinator: object,
    *,
    demo_orders_settings: DemoOrdersEvidenceSettings | None,
    app_database_url: str | None,
) -> tuple[DiagnosisExecutor, ResultAssembler, OrdersIndexRepairExecutor | None, ActionMode | None]:
    """按 mode 选择 P4.1 与唯一 P4.2 action；失败配置不会创建执行器。"""
    fallback_executor = CoordinatorDiagnosisExecutor(coordinator)
    if demo_orders_settings is not None:
        settings = demo_orders_settings
    else:
        try:
            settings = load_demo_orders_evidence_settings(app_database_url=app_database_url)
        except DemoOrdersConfigurationError:
            if _configured_demo_orders_mode() is EvidenceMode.DISABLED:
                return fallback_executor, ConservativeResultAssembler(), None, None
            return RoutedDemoOrdersExecutor(UnavailableDemoOrdersExecutor()), P4CompatibleResultAssembler(), None, None
    if settings.mode is EvidenceMode.DISABLED:
        return fallback_executor, ConservativeResultAssembler(), None, None
    if settings.mode is EvidenceMode.MOCK:
        action_executor: OrdersIndexRepairExecutor = MockOrdersIndexRepairExecutor()
    else:
        action_executor = PostgresOrdersIndexRepairExecutor(settings)
    return (
        RoutedDemoOrdersExecutor(DemoOrdersInvestigationExecutor.from_settings(settings)),
        P4CompatibleResultAssembler(),
        action_executor,
        cast(ActionMode, settings.mode.value),
    )


def _configured_demo_orders_mode() -> EvidenceMode:
    """只用于决定配置失败时是否保留 legacy 装配，不暴露原始值。"""
    try:
        return EvidenceMode(os.environ.get("OPERMIND_DEMO_ORDERS_EVIDENCE_MODE", "disabled").strip().lower())
    except ValueError:
        return EvidenceMode.TARGET


def get_v1_services(request: Request) -> V1Services:
    """从应用状态读取已装配依赖，避免路由自行创建数据库连接。"""
    services = getattr(request.app.state, "v1_services", None)
    if not isinstance(services, V1Services):
        raise RuntimeError("v1 API 依赖尚未装配")
    return services


def _build_service_center(
    session_factory: SessionFactory,
    explicit_settings: DemoOrdersEvidenceSettings | None,
    app_database_url: str | None,
) -> ServiceCenterApplicationService:
    """无论 P4.1 诊断装配是否可用，均注册唯一受控服务及诚实快照模式。"""
    settings = explicit_settings
    if settings is None:
        try:
            settings = load_demo_orders_evidence_settings(app_database_url=app_database_url)
        except DemoOrdersConfigurationError:
            mode = _configured_demo_orders_mode()
            connector_mode = ServiceMode.DISABLED if mode is EvidenceMode.DISABLED else ServiceMode.TARGET
            connector = PostgresOrdersSlowQueryConnector(connector_mode)
            return ServiceCenterApplicationService(session_factory, ServiceRegistry((connector,)))

    connector = PostgresOrdersSlowQueryConnector(ServiceMode(settings.mode.value), settings)
    return ServiceCenterApplicationService(session_factory, ServiceRegistry((connector,)))
