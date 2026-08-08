"""v1 API 的依赖装配。

诊断执行统一走多 Agent 内核（Coordinator）；审批闭环保留为通用骨架，
服务中心通过显式依赖装配注册已确认的只读服务 Connector。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request

from src.application.action_services import ActionApplicationService
from src.application.model_providers import resolve_model_config
from src.application.services import RunApplicationService, SessionApplicationService
from src.application.service_center import ServiceCenterApplicationService
from src.config import load_action_mode, load_monitor_settings, load_persistence_settings, load_service_dsn
from src.application.action_execution import ControlledActionExecutor
from src.core.bootstrap import build_coordinator, build_llm_from_config
from src.domain.services import ServiceRegistry
from src.infrastructure.diagnosis.coordinator_executor import CoordinatorDiagnosisExecutor
from src.infrastructure.diagnosis.result_assembler import KernelReportResultAssembler
from src.infrastructure.diagnosis.postgres_missing_index import PostgresMissingIndexCollector
from src.infrastructure.persistence.database import PersistenceRuntime, SessionFactory, create_persistence_runtime
from src.infrastructure.secrets import (
    SecretKeyNotConfiguredError,
    SecretKeyTooShortError,
    load_secret_key,
)
from src.infrastructure.services.postgres_connector import PostgresServiceConnector
from src.infrastructure.services.redis_connector import RedisServiceConnector
from src.infrastructure.actions.postgres_target_executor import PostgresTargetActionExecutor
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


def build_v1_services() -> V1Services:
    """装配默认持久化 Runtime 与按生效配置每 Run 解析的 Coordinator 工厂。

    coordinator 工厂每 Run 现造一套内核，隔离并发 Run 的 Agent 状态；模型生效配置
    在每次构建时经 ``resolve_model_config`` 解析（DB 激活 Provider 优先，env/YAML 兜底），
    因此 Provider 保存 / 激活 / 删除后下一次 Run 即生效，无需重启。
    """
    persistence_settings = load_persistence_settings()
    runtime = create_persistence_runtime(persistence_settings.database_url)
    return build_v1_services_for_runtime(runtime, _resolved_coordinator_factory(runtime))


def _resolved_coordinator_factory(runtime: PersistenceRuntime) -> Callable[[str | None], object]:
    """构造每 Run 解析生效模型配置的 Coordinator 工厂。"""
    secret_key = _load_secret_key_or_none()

    def build(service_id: str | None) -> object:
        config = resolve_model_config(runtime.session_factory, secret_key)
        llm = build_llm_from_config(config)
        return build_coordinator(llm, service_id=service_id)

    return build


def _load_secret_key_or_none() -> bytes | None:
    """读取 Provider API Key 主密钥；未配置或过短时返回 None，允许只读与无 Key 保存。"""
    try:
        return load_secret_key()
    except (SecretKeyNotConfiguredError, SecretKeyTooShortError):
        return None


def build_v1_services_for_runtime(
    runtime: PersistenceRuntime,
    coordinator_factory: Callable[[str | None], object],
) -> V1Services:
    """用给定 Runtime 构造服务，供临时库测试安全替换。

    诊断执行固定使用多 Agent 内核（每 Run 现造）；结果用 KernelReportResultAssembler，
    报告作答复、结构化字段保守留空。审批执行器仍为空骨架，服务注册表显式装配已确认的 Connector。
    """
    session_factory = runtime.session_factory
    monitor_settings = load_monitor_settings()
    action_mode = load_action_mode()
    action_executor: ControlledActionExecutor | None = (
        PostgresTargetActionExecutor(load_service_dsn("postgres-target"))
        if action_mode == "target"
        else None
    )
    action_service = ActionApplicationService(session_factory, executor=action_executor)
    postgres_instances = (
        ("postgres-production", "生产 PostgreSQL 主库"),
        ("postgres-staging", "预发布 PostgreSQL 主库"),
        ("postgres-target", "受控 PostgreSQL 靶场"),
    )
    redis_instances = (
        ("redis-production", "生产 Redis 缓存"),
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
        + tuple(
            RedisServiceConnector(
                load_service_dsn(instance_id),
                instance_id=instance_id,
                title=title,
            )
            for instance_id, title in redis_instances
        )
    )
    return V1Services(
        session_factory=session_factory,
        session_service=SessionApplicationService(session_factory, registry=registry),
        run_service=RunApplicationService(
            session_factory,
            CoordinatorDiagnosisExecutor(
                coordinator_factory,
                missing_index_collector=PostgresMissingIndexCollector(load_service_dsn("postgres-target")),
            ),
            KernelReportResultAssembler(),
            action_service=action_service,
            action_mode=action_mode,
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
