"""v1 API 的依赖装配。

诊断执行统一走多 Agent 内核（Coordinator）；审批闭环保留为通用骨架，
服务中心通过显式依赖装配注册已确认的只读服务 Connector。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from fastapi import Request

from src.application.action_execution import ControlledActionExecutor
from src.application.action_services import ActionApplicationService
from src.application.knowledge import KnowledgeReaderService
from src.application.model_mode import resolve_runtime_mode
from src.application.model_params import resolve_model_params
from src.application.plain_messages import PlainMessageApplicationService
from src.application.service_center import ServiceCenterApplicationService
from src.application.service_registration import ServiceRegistrationApplicationService
from src.application.services import RunApplicationService, SessionApplicationService
from src.config import (
    load_action_mode,
    load_host_metrics_settings,
    load_knowledge_settings,
    load_monitor_settings,
    load_persistence_settings,
    load_service_dsn,
)
from src.core.bootstrap import build_coordinator, build_llm_from_config
from src.core.coordinator import CoordinatorAgent
from src.domain.model_params import ModelParams
from src.domain.services import ServiceRegistrationData, ServiceRegistry
from src.infrastructure.actions.postgres_target_executor import PostgresTargetActionExecutor
from src.infrastructure.diagnosis.coordinator_executor import CoordinatorDiagnosisExecutor
from src.infrastructure.diagnosis.postgres_missing_index import PostgresMissingIndexCollector
from src.infrastructure.diagnosis.result_assembler import KernelReportResultAssembler
from src.infrastructure.monitoring.host_metrics import PsutilHostMetricsCollector
from src.infrastructure.monitoring.sampler import MonitorSampler
from src.infrastructure.persistence.app_settings_repository import SqlAlchemyAppSettingsStore
from src.infrastructure.persistence.database import PersistenceRuntime, SessionFactory, create_persistence_runtime
from src.infrastructure.persistence.plain_message_writer import SqlAlchemyPlainMessageWriter
from src.infrastructure.secrets import (
    SecretKeyNotConfiguredError,
    SecretKeyTooShortError,
    decrypt_dsn,
    load_secret_key,
)
from src.infrastructure.services.postgres_connector import PostgresServiceConnector
from src.infrastructure.services.redis_connector import RedisServiceConnector
from src.infrastructure.services.service_connector_factory import (
    build_service_connector,
    load_registered_services,
)


@dataclass(frozen=True)
class V1Services:
    """v1 路由所需的可替换运行时依赖。"""

    session_factory: SessionFactory
    session_service: SessionApplicationService
    run_service: RunApplicationService
    plain_message_service: PlainMessageApplicationService | None = None
    action_service: ActionApplicationService | None = None
    service_center: ServiceCenterApplicationService | None = None
    monitor_sampler: MonitorSampler | None = None
    service_registry: ServiceRegistry | None = None
    knowledge_service: KnowledgeReaderService | None = None
    service_registration: ServiceRegistrationApplicationService | None = None


def build_v1_services() -> V1Services:
    """装配默认持久化 Runtime 与按生效配置每 Run 解析的 Coordinator 工厂。

    coordinator 工厂每 Run 现造一套内核，隔离并发 Run 的 Agent 状态；模型生效配置
    与运行时模式在每次构建时经 ``resolve_runtime_mode`` 解析（运行时模式覆盖优先，
    DB 激活 Provider 优先、env/YAML 兜底），因此 Provider 保存 / 激活 / 删除与模式
    切换后下一次 Run 即生效，无需重启。
    """
    persistence_settings = load_persistence_settings()
    runtime = create_persistence_runtime(persistence_settings.database_url)
    return build_v1_services_for_runtime(
        runtime,
        _resolved_coordinator_factory(runtime),
        registry_loader=lambda: load_registered_services(runtime.session_factory),
    )


def _resolved_coordinator_factory(runtime: PersistenceRuntime) -> Callable[[str | None], CoordinatorAgent]:
    """构造每 Run 解析生效模型配置、运行时模式与运行参数的 Coordinator 工厂。"""
    secret_key = _load_secret_key_or_none()

    def build(service_id: str | None) -> CoordinatorAgent:
        resolution = resolve_runtime_mode(runtime.session_factory, secret_key)
        params = resolve_model_params(SqlAlchemyAppSettingsStore(runtime.session_factory))
        llm = build_llm_from_config(
            resolution["config"],
            params=ModelParams(temperature=params["temperature"], max_tokens=params["max_tokens"]),
        )
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
    coordinator_factory: Callable[[str | None], CoordinatorAgent],
    registry_loader: Callable[[], Sequence[ServiceRegistrationData]] | None = None,
) -> V1Services:
    """用给定 Runtime 构造服务，供临时库测试安全替换。

    诊断执行固定使用多 Agent 内核（每 Run 现造）；结果用 KernelReportResultAssembler，
    报告作答复、结构化字段保守留空。审批执行器仍为空骨架，服务注册表显式装配已确认的
    硬编码 Connector，并可选加载已落库动态注册服务（registry_loader 注入，避免装配直连库）。
    """
    session_factory = runtime.session_factory
    monitor_settings = load_monitor_settings()
    host_metrics_settings = load_host_metrics_settings()
    action_mode = load_action_mode()
    action_executor: ControlledActionExecutor | None = (
        PostgresTargetActionExecutor(load_service_dsn("postgres-target"))
        if action_mode == "target"
        else None
    )
    action_service = ActionApplicationService(session_factory, executor=action_executor)
    # 单一后端主机采集器：服务快照与历史采样共享同一实例（采样器为 TTL 缓存保温）。
    host_collector = PsutilHostMetricsCollector(cache_seconds=host_metrics_settings.cache_seconds)
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
    secret_key = _load_secret_key_or_none()
    if registry_loader is not None:
        for item in registry_loader():
            dsn = _resolve_registered_dsn(item, secret_key)
            registry.register(
                build_service_connector(
                    item.kind,
                    dsn,
                    item.instance_id,
                    item.title,
                    item.dsn_masked_tail,
                )
            )
    service_registration = ServiceRegistrationApplicationService(
        session_factory,
        registry,
        secret_key,
        connector_factory=build_service_connector,
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
            registry=registry,
        ),
        plain_message_service=PlainMessageApplicationService(SqlAlchemyPlainMessageWriter(session_factory)),
        action_service=action_service,
        service_center=ServiceCenterApplicationService(
            session_factory,
            registry,
            host_metrics_collector=host_collector,
        ),
        monitor_sampler=MonitorSampler(
            session_factory=session_factory,
            registry=registry,
            retention_hours=monitor_settings.retention_hours,
            sample_interval_seconds=monitor_settings.sample_interval_seconds,
            host_collector=host_collector,
        ),
        service_registry=registry,
        knowledge_service=KnowledgeReaderService(load_knowledge_settings().directory),
        service_registration=service_registration,
    )


def _resolve_registered_dsn(item: ServiceRegistrationData, secret_key: bytes | None) -> str | None:
    """把动态注册服务的 DSN 密文解析为明文；主密钥缺失或不可解时诚实返回 None。"""
    if item.dsn_encrypted is None or item.dsn_nonce is None:
        return None
    if secret_key is None:
        return None
    try:
        return decrypt_dsn(item.dsn_encrypted, item.dsn_nonce, secret_key)
    except Exception:
        return None


def get_v1_services(request: Request) -> V1Services:
    """从应用状态读取已装配依赖，避免路由自行创建数据库连接。"""
    services = getattr(request.app.state, "v1_services", None)
    if not isinstance(services, V1Services):
        raise RuntimeError("v1 API 依赖尚未装配")
    return services
