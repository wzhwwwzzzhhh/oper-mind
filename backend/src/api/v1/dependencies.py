"""P2.4 v1 API 的依赖装配。"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from src.application.services import RunApplicationService, SessionApplicationService
from src.config import load_persistence_settings
from src.infrastructure.diagnosis.coordinator_executor import CoordinatorDiagnosisExecutor
from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler
from src.infrastructure.persistence.database import PersistenceRuntime, SessionFactory, create_persistence_runtime


@dataclass(frozen=True)
class V1Services:
    """v1 路由所需的可替换运行时依赖。"""

    session_factory: SessionFactory
    session_service: SessionApplicationService
    run_service: RunApplicationService


def build_v1_services(coordinator: object) -> V1Services:
    """装配默认持久化 Runtime 与 P2 诊断适配，不执行迁移或建表。"""
    runtime = create_persistence_runtime(load_persistence_settings().database_url)
    return build_v1_services_for_runtime(runtime, coordinator)


def build_v1_services_for_runtime(runtime: PersistenceRuntime, coordinator: object) -> V1Services:
    """用给定 Runtime 构造服务，供临时库测试安全替换。"""
    session_factory = runtime.session_factory
    return V1Services(
        session_factory=session_factory,
        session_service=SessionApplicationService(session_factory),
        run_service=RunApplicationService(
            session_factory,
            CoordinatorDiagnosisExecutor(coordinator),
            ConservativeResultAssembler(),
        ),
    )


def get_v1_services(request: Request) -> V1Services:
    """从应用状态读取已装配依赖，避免路由自行创建数据库连接。"""
    services = getattr(request.app.state, "v1_services", None)
    if not isinstance(services, V1Services):
        raise RuntimeError("v1 API 依赖尚未装配")
    return services
