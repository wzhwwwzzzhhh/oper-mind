"""P8 监控阈值配置的单元与 API 契约测试（S1/S2）。"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy import text as sa_text
from sqlalchemy.orm import sessionmaker

from src.api.v1.dependencies import V1Services
from src.application.monitoring import (
    MonitorOverviewApplicationService,
    MonitorThresholdApplicationService,
)
from src.domain.monitoring import (
    DEFAULT_MONITOR_THRESHOLDS,
    MonitorThresholdConfig,
    MonitorThresholdSource,
    ServiceMonitorSampleData,
)
from src.domain.services import (
    PerformanceSignal,
    ServiceAvailability,
    ServiceDefinitionData,
    ServiceRegistry,
    ServiceSnapshotData,
    ServiceSourceStatus,
)
from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.models import ServiceMonitorThresholdRecord
from src.infrastructure.persistence.monitor_repositories import (
    SqlAlchemyMonitorSampleRepository,
    SqlAlchemyMonitorThresholdRepository,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def _run_alembic(
    command: list[str],
    database_path: Path,
    working_directory: Path,
) -> subprocess.CompletedProcess[str]:
    """通过绝对 alembic.ini 在指定库运行迁移命令。"""
    environment = os.environ.copy()
    environment.update(
        {
            "OPERMIND_APP_DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "OPERMIND_API_KEY": "mock",
            "OPERMIND_BASE_URL": "http://mock",
            "OPERMIND_MODEL": "mock",
            "PYTHONPATH": os.pathsep.join([str(BACKEND_ROOT), str(PROJECT_ROOT), environment.get("PYTHONPATH", "")]),
        }
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *command],
        cwd=working_directory,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_阈值迁移存在配置行时拒绝回滚(tmp_path: Path) -> None:
    """迁移 downgrade 防御：存在阈值配置行时拒绝回滚，避免静默丢弃用户配置。"""
    from src.infrastructure.persistence.database import create_app_engine

    database_path = tmp_path / "threshold-migration.sqlite3"
    upgrade = _run_alembic(["upgrade", "head"], database_path, PROJECT_ROOT)
    assert upgrade.returncode == 0, upgrade.stderr

    engine = create_app_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.begin() as connection:
            now = "2026-08-15T00:00:00+00:00"
            connection.exec_driver_sql(
                "INSERT INTO service_monitor_thresholds "
                "(service_id, slow_query_count_threshold, timeout_count_threshold, "
                " slowlog_count_threshold, window_minutes, count_availability_change, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("postgres-production", 3, None, 2, 10, 0, now),
            )
    finally:
        engine.dispose()

    downgrade = _run_alembic(
        ["downgrade", "20260812_12_p8_run_rerun"],
        database_path,
        PROJECT_ROOT,
    )
    assert downgrade.returncode != 0
    assert "拒绝回滚" in downgrade.stderr

    # 清空配置行后 downgrade 可正常完成。
    engine = create_app_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("DELETE FROM service_monitor_thresholds")
    finally:
        engine.dispose()
    downgrade_ok = _run_alembic(
        ["downgrade", "20260812_12_p8_run_rerun"],
        database_path,
        PROJECT_ROOT,
    )
    assert downgrade_ok.returncode == 0, downgrade_ok.stderr


def _sample(
    service_id: str,
    observed_at: datetime,
    *,
    slow: int | None = 0,
    timeout: int | None = 0,
    availability: ServiceAvailability = ServiceAvailability.HEALTHY,
    source_status: ServiceSourceStatus = ServiceSourceStatus.AVAILABLE,
    slowlog: int | None = None,
) -> ServiceMonitorSampleData:
    return ServiceMonitorSampleData(
        service_id=service_id,
        observed_at=observed_at,
        availability=availability,
        p50_ms=10.0 if source_status is ServiceSourceStatus.AVAILABLE else None,
        p95_ms=20.0 if source_status is ServiceSourceStatus.AVAILABLE else None,
        slow_query_count=slow if source_status is ServiceSourceStatus.AVAILABLE else None,
        timeout_count=timeout if source_status is ServiceSourceStatus.AVAILABLE else None,
        slowlog_count=slowlog,
        performance_signal=PerformanceSignal.NO_SLOW_QUERY_DETECTED,
        source_status=source_status,
    )


class _StubConnector:
    """静态注册表最小只读 Connector 桩，不触发任何外部连接。"""

    def __init__(self, service_id: str, kind: str = "postgres") -> None:
        self._definition = ServiceDefinitionData(
            id=service_id,
            title=f"{service_id} 标题",
            kind=kind,
            supported_investigations=(),
            action_boundary="只读",
            session_title=service_id,
        )

    def definition(self) -> ServiceDefinitionData:
        return self._definition

    def health_snapshot(self) -> ServiceSnapshotData:
        raise AssertionError("阈值路径不得调用 health_snapshot（不触发目标连接）。")


def _registry(*service_ids: str) -> ServiceRegistry:
    return ServiceRegistry(
        tuple(_StubConnector(service_id, kind="redis" if "redis" in service_id else "postgres") for service_id in service_ids)
    )


def _overview_service(session_factory, registry: ServiceRegistry) -> MonitorOverviewApplicationService:
    return MonitorOverviewApplicationService(
        session_factory=session_factory,
        registry=registry,
        sample_interval_seconds=300,
        retention_hours=24,
    )


# ---------------------------------------------------------------------------
# S1：领域模型与阈值应用服务单元测试
# ---------------------------------------------------------------------------


def test_默认配置与现状异常判定等价() -> None:
    """AC6：默认配置下异常计数与旧 `_trend_summary`（slow>0/timeout>0/slowlog>0/可用性变化）一致。"""
    assert DEFAULT_MONITOR_THRESHOLDS.slow_query_count_threshold == 1
    assert DEFAULT_MONITOR_THRESHOLDS.timeout_count_threshold == 1
    assert DEFAULT_MONITOR_THRESHOLDS.slowlog_count_threshold == 1
    assert DEFAULT_MONITOR_THRESHOLDS.window_minutes == 0
    assert DEFAULT_MONITOR_THRESHOLDS.count_availability_change is True

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    registry = _registry("postgres-production", "redis-production")
    now = datetime.now(UTC)
    with session_factory() as session:
        repository = SqlAlchemyMonitorSampleRepository(session)
        repository.add(_sample("postgres-production", now - timedelta(minutes=20)))
        repository.add(_sample("postgres-production", now - timedelta(minutes=15), slow=1))
        repository.add(
            _sample(
                "postgres-production",
                now - timedelta(minutes=10),
                availability=ServiceAvailability.UNHEALTHY,
            )
        )
        repository.add(_sample("postgres-production", now - timedelta(minutes=5), slow=0))
        # Redis 样本镜像真实采样：PG 语义标量（slow_query_count/timeout_count）恒为 null。
        repository.add(_sample("redis-production", now - timedelta(minutes=10), slow=None, timeout=None))
        repository.add(_sample("redis-production", now - timedelta(minutes=5), slow=None, timeout=None, slowlog=2))
        session.commit()

    overview = _overview_service(session_factory, registry).get_overview()

    postgres = next(item for item in overview.items if item.service_id == "postgres-production")
    # 15 分钟慢查询 1 处 + 10 分钟/5 分钟可用性状态变化 2 处 = 3 处异常（与旧规则一致）。
    assert postgres.trend_summary.sample_count == 4
    assert postgres.trend_summary.anomaly_sample_count == 3

    redis = next(item for item in overview.items if item.service_id == "redis-production")
    assert redis.trend_summary.anomaly_sample_count == 1


def test_配置阈值后异常计数按配置计算() -> None:
    """AC5：配置"窗口 10 分钟内慢查询 ≥ 3"后，跨采样点聚合计数生效。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    registry = _registry("postgres-production")
    now = datetime.now(UTC)
    with session_factory() as session:
        repository = SqlAlchemyMonitorSampleRepository(session)
        repository.add(_sample("postgres-production", now - timedelta(minutes=10), slow=1))
        repository.add(_sample("postgres-production", now - timedelta(minutes=5), slow=2))
        session.commit()
        SqlAlchemyMonitorThresholdRepository(session).upsert(
            "postgres-production",
            MonitorThresholdConfig(
                slow_query_count_threshold=3,
                timeout_count_threshold=None,
                slowlog_count_threshold=None,
                window_minutes=10,
                count_availability_change=False,
            ),
        )
        session.commit()

    overview = _overview_service(session_factory, registry).get_overview()

    item = overview.items[0]
    # 5 分钟前采样点窗口 [-15, -5] 覆盖两条样本：1+2=3 ≥ 3 → 异常；
    # 10 分钟前采样点窗口 [-20, -10] 只有自身：1 < 3 → 正常。
    assert item.trend_summary.anomaly_sample_count == 1


def test_不关注指标与可用性开关关闭时不计数() -> None:
    """AC5/AC2：阈值 null=不关注该指标；count_availability_change=false 不计可用性变化。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    registry = _registry("postgres-production")
    now = datetime.now(UTC)
    with session_factory() as session:
        repository = SqlAlchemyMonitorSampleRepository(session)
        repository.add(_sample("postgres-production", now - timedelta(minutes=10), slow=1))
        repository.add(
            _sample(
                "postgres-production",
                now - timedelta(minutes=5),
                slow=0,
                availability=ServiceAvailability.UNHEALTHY,
            )
        )
        session.commit()
        SqlAlchemyMonitorThresholdRepository(session).upsert(
            "postgres-production",
            MonitorThresholdConfig(
                slow_query_count_threshold=None,
                timeout_count_threshold=None,
                slowlog_count_threshold=None,
                window_minutes=0,
                count_availability_change=False,
            ),
        )
        session.commit()

    item = _overview_service(session_factory, registry).get_overview().items[0]

    # 全部指标不关注且可用性变化不计 → 永不异常（合法配置，如实反映）。
    assert item.trend_summary.anomaly_sample_count == 0


def test_首样本不判可用性异常() -> None:
    """§2.3 边界语义：首样本没有前一个样本，不判可用性异常。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    registry = _registry("postgres-production")
    now = datetime.now(UTC)
    with session_factory() as session:
        repository = SqlAlchemyMonitorSampleRepository(session)
        repository.add(
            _sample(
                "postgres-production",
                now - timedelta(minutes=10),
                slow=0,
                availability=ServiceAvailability.UNHEALTHY,
            )
        )
        repository.add(_sample("postgres-production", now - timedelta(minutes=5), slow=0))
        session.commit()

    item = _overview_service(session_factory, registry).get_overview().items[0]

    # 10 分钟前（首样本）异常态不计数；5 分钟前恢复为可用性变化 → 1 处。
    assert item.trend_summary.anomaly_sample_count == 1


def test_未配置读取返回内置默认与default来源() -> None:
    """AC1：未配置服务读取阈值返回内置默认并标注 default。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    service = MonitorThresholdApplicationService(session_factory, _registry("postgres-production"))

    view = service.get("postgres-production")

    assert view.source is MonitorThresholdSource.DEFAULT
    assert view.config == DEFAULT_MONITOR_THRESHOLDS


def test_保存后读取返回一致配置与configured来源() -> None:
    """AC2/AC7：保存合法配置后读取回一致值（新会话读回，等价重启后读回）。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    service = MonitorThresholdApplicationService(session_factory, _registry("postgres-production"))
    config = MonitorThresholdConfig(
        slow_query_count_threshold=3,
        timeout_count_threshold=None,
        slowlog_count_threshold=2,
        window_minutes=10,
        count_availability_change=False,
    )

    saved = service.save("postgres-production", config)

    assert saved.source is MonitorThresholdSource.CONFIGURED
    assert saved.config == config

    re_read = service.get("postgres-production")
    assert re_read.source is MonitorThresholdSource.CONFIGURED
    assert re_read.config == config


def test_未配置不产生记录() -> None:
    """PRD 数据影响：未配置不产生记录。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    registry = _registry("postgres-production")
    service = MonitorThresholdApplicationService(session_factory, registry)
    service.get("postgres-production")

    with session_factory() as session:
        assert session.get(ServiceMonitorThresholdRecord, "postgres-production") is None


def test_服务不存在抛出SERVICE_NOT_FOUND() -> None:
    """AC4：应用层服务边界校验：未注册服务读取/保存均拒绝。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    service = MonitorThresholdApplicationService(session_factory, _registry("postgres-production"))

    with pytest.raises(ValueError, match="SERVICE_NOT_FOUND"):
        service.get("ghost-service")
    with pytest.raises(ValueError, match="SERVICE_NOT_FOUND"):
        service.save("ghost-service", DEFAULT_MONITOR_THRESHOLDS)


def test_非法配置在领域层被拒绝() -> None:
    """AC3：阈值 < 0 / 窗口越界在领域层即被拒绝，不落库。"""
    with pytest.raises(ValidationError):
        MonitorThresholdConfig(
            slow_query_count_threshold=-1,
            window_minutes=0,
            count_availability_change=True,
        )
    with pytest.raises(ValidationError):
        MonitorThresholdConfig(
            window_minutes=2000,
            count_availability_change=True,
        )
    with pytest.raises(ValidationError):
        MonitorThresholdConfig(
            slowlog_count_threshold=2_000_000,
            window_minutes=0,
            count_availability_change=True,
        )


def test_配置行损坏回退内置默认() -> None:
    """可靠降级：配置行损坏时回退内置默认并标注 default。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    registry = _registry("postgres-production")
    with session_factory() as session:
        # DB 约束本身会拦截非法窗口值，此处显式绕过约束写入损坏行，验证防御性读取兜底。
        session.execute(sa_text("PRAGMA ignore_check_constraints = ON"))
        session.execute(
            sa_text(
                "INSERT INTO service_monitor_thresholds "
                "(service_id, slow_query_count_threshold, timeout_count_threshold, "
                " slowlog_count_threshold, window_minutes, count_availability_change, updated_at) "
                "VALUES ('postgres-production', 1, 1, 1, -5, 1, :updated_at)"
            ),
            {"updated_at": datetime.now(UTC)},
        )
        session.commit()

    view = MonitorThresholdApplicationService(session_factory, registry).get("postgres-production")

    assert view.source is MonitorThresholdSource.DEFAULT
    assert view.config == DEFAULT_MONITOR_THRESHOLDS

    # 概览同样回退默认：按默认规则计算异常，不降级整个服务。
    now = datetime.now(UTC)
    with session_factory() as session:
        SqlAlchemyMonitorSampleRepository(session).add(
            _sample("postgres-production", now - timedelta(minutes=5), slow=1)
        )
        session.commit()
    item = _overview_service(session_factory, registry).get_overview().items[0]
    assert item.trend_summary.anomaly_sample_count == 1


# ---------------------------------------------------------------------------
# S2：阈值 API 契约测试
# ---------------------------------------------------------------------------


@pytest.fixture
def thresholds_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> Iterator[TestClient]:
    """以临时 SQLite 与静态注册表装配 v1 API，供阈值路由端到端测试。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'thresholds.sqlite3'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    registry = _registry("postgres-production", "redis-production")

    from src.application.contracts import DiagnosisExecutionEvent, DiagnosisExecutionResult
    from src.application.services import RunApplicationService, SessionApplicationService
    from src.domain.diagnosis import RunEventType
    from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler

    class _DeterministicExecutor:
        """不访问真实 Agent、只输出一条安全事件的确定性执行器。"""

        def stream(self, _query: str) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
            yield DiagnosisExecutionEvent(
                type=RunEventType.ROUTE_DECIDED,
                node="route",
                occurred_at=datetime.now(UTC),
            )
            yield DiagnosisExecutionResult(strategy="direct")

    services = V1Services(
        session_factory=session_factory,
        session_service=SessionApplicationService(session_factory, registry=registry),
        run_service=RunApplicationService(
            session_factory,
            _DeterministicExecutor(),
            ConservativeResultAssembler(),
        ),
        service_registry=registry,
    )

    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")

    from src import app as api_module

    monkeypatch.setattr(api_module.app.state, "v1_services", services)
    with TestClient(api_module.app, raise_server_exceptions=False) as client:
        yield client
    engine.dispose()


def test_GET未配置返回内置默认并标注default(thresholds_client: TestClient) -> None:
    """AC1：GET 未配置服务的阈值 → 内置默认 + source=default。"""
    response = thresholds_client.get("/api/v1/services/postgres-production/monitor/thresholds")

    assert response.status_code == 200
    body = response.json()
    assert body["service_id"] == "postgres-production"
    assert body["source"] == "default"
    assert body["config"] == {
        "slow_query_count_threshold": 1,
        "timeout_count_threshold": 1,
        "slowlog_count_threshold": 1,
        "window_minutes": 0,
        "count_availability_change": True,
    }
    assert body["meta"]["request_id"]


def test_PUT保存后GET读回一致(thresholds_client: TestClient) -> None:
    """AC2：PUT 保存合法配置 → 返回已配置视图，GET 读回一致。"""
    payload = {
        "slow_query_count_threshold": 3,
        "timeout_count_threshold": None,
        "slowlog_count_threshold": 2,
        "window_minutes": 10,
        "count_availability_change": False,
    }
    put_response = thresholds_client.put(
        "/api/v1/services/postgres-production/monitor/thresholds", json=payload
    )

    assert put_response.status_code == 200
    put_body = put_response.json()
    assert put_body["source"] == "configured"
    assert put_body["config"] == payload

    get_response = thresholds_client.get("/api/v1/services/postgres-production/monitor/thresholds")
    assert get_response.status_code == 200
    get_body = get_response.json()
    assert get_body["source"] == "configured"
    assert get_body["config"] == payload


def test_PUT非法配置返回422且不落库(thresholds_client: TestClient) -> None:
    """AC3：阈值 < 0 / 窗口越界 / 未知字段 → 422 明确错误，不落库。"""
    for invalid in (
        {"slow_query_count_threshold": -1, "timeout_count_threshold": None, "slowlog_count_threshold": None, "window_minutes": 0, "count_availability_change": True},
        {"slow_query_count_threshold": 1, "timeout_count_threshold": None, "slowlog_count_threshold": None, "window_minutes": 9999, "count_availability_change": True},
        {"slow_query_count_threshold": 1, "timeout_count_threshold": None, "slowlog_count_threshold": None, "window_minutes": 0, "count_availability_change": True, "unknown_metric": 1},
        {"slow_query_count_threshold": 1, "timeout_count_threshold": None, "slowlog_count_threshold": None},  # 缺必填字段
    ):
        response = thresholds_client.put(
            "/api/v1/services/postgres-production/monitor/thresholds", json=invalid
        )
        assert response.status_code == 422, invalid
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    get_response = thresholds_client.get("/api/v1/services/postgres-production/monitor/thresholds")
    assert get_response.json()["source"] == "default"


def test_不存在服务返回404(thresholds_client: TestClient) -> None:
    """AC4：请求不存在的服务阈值 → 404，不探测外部资源。"""
    get_response = thresholds_client.get("/api/v1/services/ghost-service/monitor/thresholds")
    assert get_response.status_code == 404
    assert get_response.json()["error"]["code"] == "SERVICE_NOT_FOUND"

    put_response = thresholds_client.put(
        "/api/v1/services/ghost-service/monitor/thresholds",
        json={
            "slow_query_count_threshold": 1,
            "timeout_count_threshold": None,
            "slowlog_count_threshold": None,
            "window_minutes": 0,
            "count_availability_change": True,
        },
    )
    assert put_response.status_code == 404
    assert put_response.json()["error"]["code"] == "SERVICE_NOT_FOUND"


def test_响应不含敏感内容(thresholds_client: TestClient) -> None:
    """AC8：阈值接口与响应不含凭据、DSN、sk- 或原始异常详情。"""
    get_response = thresholds_client.get("/api/v1/services/postgres-production/monitor/thresholds")
    put_response = thresholds_client.put(
        "/api/v1/services/postgres-production/monitor/thresholds",
        json={
            "slow_query_count_threshold": 1,
            "timeout_count_threshold": None,
            "slowlog_count_threshold": None,
            "window_minutes": 0,
            "count_availability_change": True,
        },
    )
    for response in (get_response, put_response):
        raw = response.text
        for sensitive in ("password", "DSN", "dsn=", "sk-", "SELECT", "sql=", "username"):
            assert sensitive.lower() not in raw.lower()


def test_配置后概览异常计数按配置计算(thresholds_client: TestClient) -> None:
    """AC5：配置阈值后 GET /monitor/overview 的异常采样点计数按配置计算。"""
    now = datetime.now(UTC)
    with thresholds_client.app.state.v1_services.session_factory() as session:
        repository = SqlAlchemyMonitorSampleRepository(session)
        repository.add(_sample("postgres-production", now - timedelta(minutes=10), slow=1))
        repository.add(_sample("postgres-production", now - timedelta(minutes=5), slow=2))
        session.commit()

    thresholds_client.put(
        "/api/v1/services/postgres-production/monitor/thresholds",
        json={
            "slow_query_count_threshold": 3,
            "timeout_count_threshold": None,
            "slowlog_count_threshold": None,
            "window_minutes": 10,
            "count_availability_change": False,
        },
    )

    response = thresholds_client.get("/api/v1/monitor/overview")
    assert response.status_code == 200
    item = next(
        item for item in response.json()["items"] if item["service_id"] == "postgres-production"
    )
    # 窗口 10 分钟聚合：仅 5 分钟前采样点（1+2=3 ≥ 3）异常。
    assert item["trend_summary"]["anomaly_sample_count"] == 1


def test_未配置服务概览行为与配置前一致(thresholds_client: TestClient) -> None:
    """AC6：未配置服务异常计数与配置前一致（默认规则）。"""
    now = datetime.now(UTC)
    with thresholds_client.app.state.v1_services.session_factory() as session:
        repository = SqlAlchemyMonitorSampleRepository(session)
        repository.add(_sample("postgres-production", now - timedelta(minutes=15), slow=1))
        repository.add(_sample("postgres-production", now - timedelta(minutes=5), slow=0))
        session.commit()

    response = thresholds_client.get("/api/v1/monitor/overview")
    item = next(
        item for item in response.json()["items"] if item["service_id"] == "postgres-production"
    )
    assert item["trend_summary"]["anomaly_sample_count"] == 1
