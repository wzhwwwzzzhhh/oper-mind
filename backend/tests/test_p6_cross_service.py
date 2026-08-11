"""P6 多服务会话和显式单服务 Run 的聚焦测试。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.application.contracts import CreateRunCommand, CreateSessionCommand, DiagnosisExecutionResult
from src.application.errors import ServiceContextRequiredError, ServiceNotFoundError
from src.application.services import RunApplicationService, SessionApplicationService
from src.domain.records import SessionData
from src.domain.services import ServiceRegistry
from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler
from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.repositories import SqlAlchemySessionRepository

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


class _Executor:
    def stream(self, _query: str, _service_id: str | None = None):
        yield DiagnosisExecutionResult(strategy="mock")


class _Connector:
    def __init__(self, service_id: str) -> None:
        self._service_id = service_id

    def definition(self):
        from src.domain.services import ServiceDefinitionData

        return ServiceDefinitionData(
            id=self._service_id,
            title=self._service_id,
            kind="postgres",
            supported_investigations=(),
            action_boundary="只读",
            session_title="调查",
        )

    def health_snapshot(self):
        raise AssertionError("本测试不读取服务快照")


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine)
    finally:
        engine.dispose()


def test_多服务创建按顺序持久化且旧单值会话读取兜底(session_factory) -> None:
    registry = ServiceRegistry((_Connector("postgres-production"), _Connector("postgres-staging")))
    service = SessionApplicationService(session_factory, registry)

    created = service.create_session(
        CreateSessionCommand(title="联合调查", service_ids=("postgres-staging", "postgres-production"))
    )
    assert created.service_id is None
    assert created.service_ids == ("postgres-staging", "postgres-production")

    session = session_factory()
    try:
        loaded = SqlAlchemySessionRepository(session).get_by_id(created.id)
        assert loaded is not None
        assert loaded.service_ids == ("postgres-staging", "postgres-production")
        legacy = SessionData(title="旧会话", service_id="postgres-production")
        SqlAlchemySessionRepository(session).add(legacy)
        session.commit()
        assert SqlAlchemySessionRepository(session).get_by_id(legacy.id).service_ids == ("postgres-production",)  # type: ignore[union-attr]
    finally:
        session.close()


def test_服务集合校验和重复服务被拒绝(session_factory) -> None:
    service = SessionApplicationService(session_factory, ServiceRegistry((_Connector("postgres-production"),)))
    with pytest.raises(ValueError):
        CreateSessionCommand(title="重复", service_ids=("postgres-production", "postgres-production"))
    with pytest.raises(ServiceNotFoundError):
        service.create_session(CreateSessionCommand(title="不存在", service_ids=("postgres-staging",)))


def test_redis是会话服务关联表允许的已注册服务(session_factory) -> None:
    service = SessionApplicationService(session_factory, ServiceRegistry((_Connector("redis-production"),)))

    service.create_session(CreateSessionCommand(title="Redis 调查", service_ids=("redis-production",)))

    session = session_factory()
    try:
        assert session.execute(text("SELECT service_id FROM session_services")).scalar_one() == "redis-production"
    finally:
        session.close()


def test_run显式绑定会话服务并拒绝猜测或越界(session_factory) -> None:
    session_service = SessionApplicationService(
        session_factory,
        ServiceRegistry((_Connector("postgres-production"), _Connector("postgres-staging"))),
    )
    session_data = session_service.create_session(
        CreateSessionCommand(title="联合调查", service_ids=("postgres-production", "postgres-staging"))
    )
    run_service = RunApplicationService(session_factory, _Executor(), ConservativeResultAssembler())

    accepted = run_service.accept_run(
        CreateRunCommand(
            session_id=session_data.id,
            query="检查 orders 表索引",
            service_id="postgres-staging",
            idempotency_key=uuid4(),
        )
    )
    assert accepted.run.service_id == "postgres-staging"
    with pytest.raises(ServiceContextRequiredError):
        run_service.accept_run(
            CreateRunCommand(session_id=session_data.id, query="检查 orders 表索引", idempotency_key=uuid4())
        )
    with pytest.raises(ServiceContextRequiredError):
        run_service.accept_run(
            CreateRunCommand(
                session_id=session_data.id,
                query="检查 orders 表索引",
                service_id="postgres-target",
                idempotency_key=uuid4(),
            )
        )


def test_迁移在存在关联数据时拒绝降级(tmp_path: Path) -> None:
    database_path = tmp_path / "p6-migration.sqlite3"
    environment = os.environ.copy()
    environment.update(
        {
            "OPERMIND_APP_DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "OPERMIND_API_KEY": "mock",
            "OPERMIND_BASE_URL": "http://mock",
            "OPERMIND_MODEL": "mock",
            "PYTHONPATH": os.pathsep.join((str(BACKEND_ROOT), str(PROJECT_ROOT))),
        }
    )
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert upgrade.returncode == 0, upgrade.stderr
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.begin() as connection:
            session_id = str(uuid4())
            now = "2026-08-08T00:00:00+00:00"
            connection.exec_driver_sql(
                "INSERT INTO sessions (id, title, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, "迁移守卫", "active", now, now),
            )
            connection.exec_driver_sql(
                "INSERT INTO session_services (session_id, service_id, created_at) VALUES (?, ?, ?)",
                (session_id, "redis-production", now),
            )
    finally:
        engine.dispose()
    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "downgrade", "20260807_08_p6_host_metrics"],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert downgrade.returncode != 0
    assert "无法回滚" in downgrade.stderr
