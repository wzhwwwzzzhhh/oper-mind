"""v1 API 的依赖装配。

诊断执行统一走多 Agent 内核（Coordinator）；审批闭环保留为通用骨架，
服务中心通过显式依赖装配注册已确认的只读服务 Connector。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request

from src.application.action_services import ActionApplicationService
from src.application.services import RunApplicationService, SessionApplicationService
from src.application.service_center import ServiceCenterApplicationService
from src.config import load_monitor_settings, load_persistence_settings, load_service_dsn
from src.domain.services import ServiceRegistry
from src.infrastructure.diagnosis.coordinator_executor import CoordinatorDiagnosisExecutor
from src.infrastructure.diagnosis.result_assembler import KernelReportResultAssembler
from src.infrastructure.persistence.database import PersistenceRuntime, SessionFactory, create_persistence_runtime
from src.infrastructure.services.postgres_connector import PostgresServiceConnector
from src.infrastructure.monitoring.sampler import MonitorSampler


@dataclass(frozen=True)
class V1Services:
    """v1 路由所需的可替换运行时依赖。"""

    session_factory: SessionFactory
    session_service: SessionApplicationService
    run_service: RunApplicationService
    action_service: ActionApplicationService | None = None
    service_center: ServiceCenterApplicationService | None = None
    monitor_sampler: MonitorSampler | None = None
    service_registry: ServiceRegistry | None = None


def build_v1_services(coordinator_factory: Callable[[], object]) -> V1Services:
    """装配默认持久化 Runtime 与多 Agent 内核诊断执行。

    coordinator_factory 每 Run 现造一套内核，隔离并发 Run 的 Agent 状态。
    """
    persistence_settings = load_persistence_settings()
    runtime = create_persistence_runtime(persistence_settings.database_url)
    return build_v1_services_for_runtime(runtime, coordinator_factory)


def build_v1_services_for_runtime(
    runtime: PersistenceRuntime,
    coordinator_factory: Callable[[], object],
) -> V1Services:
    """用给定 Runtime 构造服务，供临时库测试安全替换。

    诊断执行固定使用多 Agent 内核（每 Run 现造）；结果用 KernelReportResultAssembler，
    报告作答复、结构化字段保守留空。审批执行器仍为空骨架，服务注册表显式装配已确认的 Connector。
    """
    session_factory = runtime.session_factory
    monitor_settings = load_monitor_settings()
    action_service = ActionApplicationService(session_factory, executor=None)
    postgres_instances = (
        ("postgres-production", "生产 PostgreSQL 主库"),
        ("postgres-staging", "预发布 PostgreSQL 主库"),
    )
    registry = ServiceRegistry(
        tuple(
            PostgresServiceConnector(
                load_service_dsn(instance_id),
                instance_id=instance_id,
                title=title,
            )
            for instance_id, title in postgres_instances
        )
    )
    return V1Services(
        session_factory=session_factory,
        session_service=SessionApplicationService(session_factory),
        run_service=RunApplicationService(
            session_factory,
            CoordinatorDiagnosisExecutor(coordinator_factory),
            KernelReportResultAssembler(),
            action_service=action_service,
            action_mode=None,
        ),
        action_service=action_service,
        service_center=ServiceCenterApplicationService(
            session_factory,
            registry,
        ),
        monitor_sampler=MonitorSampler(
            session_factory=session_factory,
            connectors=registry.list_connectors(),
            retention_hours=monitor_settings.retention_hours,
            sample_interval_seconds=monitor_settings.sample_interval_seconds,
        ),
        service_registry=registry,
    )


def get_v1_services(request: Request) -> V1Services:
    """从应用状态读取已装配依赖，避免路由自行创建数据库连接。"""
    services = getattr(request.app.state, "v1_services", None)
    if not isinstance(services, V1Services):
        raise RuntimeError("v1 API 依赖尚未装配")
    return services
