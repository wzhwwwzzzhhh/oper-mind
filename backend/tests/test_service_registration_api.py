"""P8 服务注册 API 测试：DSN 加密落库、动态 CRUD、安全视图与回归。"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from src.api.v1.dependencies import build_v1_services_for_runtime
from src.infrastructure.persistence.database import Base, create_persistence_runtime
from src.infrastructure.persistence.models import ServiceRegistryRecord

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"

MASTER_MATERIAL = "test-secret-key-0123456789abcdef0123456789abcdef"
# 指向本地快速拒绝端口，探活立即 unavailable，避免 3s socket 超时拖慢测试。
PG_DSN_PLAINTEXT = "postgresql://user:pass@127.0.0.1:1/orders"
REDIS_DSN_PLAINTEXT = "redis://:redact@127.0.0.1:1/0"
MYSQL_DSN_PLAINTEXT = "mysql+pymysql://readonly@127.0.0.1:1"


def _coordinator_factory(_service_id: str | None = None):
    """服务注册测试不触发多 Agent 内核的占位工厂。"""
    raise AssertionError("服务注册测试不应触发 Coordinator 构造。")


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    """以临时 SQLite 与加密主密钥构建完整装配的 v1 API 客户端。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")
    monkeypatch.setenv("OPERMIND_SECRET_KEY", MASTER_MATERIAL)

    database_path = tmp_path / "service-registration.sqlite3"
    runtime = create_persistence_runtime(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(runtime.engine)
    services = build_v1_services_for_runtime(runtime, _coordinator_factory)
    monkeypatch.setenv("OPERMIND_APP_DATABASE_URL", f"sqlite:///{database_path.as_posix()}")

    from src import app as api_module

    monkeypatch.setattr(api_module.app.state, "v1_services", services)
    with TestClient(api_module.app, raise_server_exceptions=False) as client:
        yield client
    runtime.engine.dispose()


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": "postgres",
        "instance_id": "postgres-orders",
        "title": "订单 PostgreSQL",
        "dsn": PG_DSN_PLAINTEXT,
    }
    payload.update(overrides)
    return payload


def _create_service(client: TestClient, **overrides: object) -> dict[str, object]:
    response = client.post("/api/v1/services", json=_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()["service"]


def _select_registry_row():
    """构造读取 service_registry 行的 SQL 语句（供 AC8 密文断言）。"""
    return select(ServiceRegistryRecord).where(ServiceRegistryRecord.instance_id == "postgres-orders")


def test_注册服务返回安全视图且响应无明文(api_client: TestClient) -> None:
    """AC1/AC8：注册 pg 服务返回 id/kind/title/has_dsn/掩码尾号，无 DSN 明文。"""
    response = api_client.post("/api/v1/services", json=_payload())

    assert response.status_code == 201
    body = response.json()
    service = body["service"]
    assert service["id"] == "postgres-orders"
    assert service["kind"] == "postgres"
    assert service["title"] == "订单 PostgreSQL"
    assert service["has_dsn"] is True
    assert service["dsn_masked_tail"] == PG_DSN_PLAINTEXT[-4:]
    raw = response.text
    assert PG_DSN_PLAINTEXT not in raw
    assert "user:pass" not in raw

    session = api_client.app.state.v1_services.session_factory()
    try:
        row = session.scalars(_select_registry_row()).first()
    finally:
        session.close()
    assert row is not None
    assert PG_DSN_PLAINTEXT not in row.dsn_encrypted
    assert "user:pass" not in row.dsn_encrypted


def test_注册服务ID与既有硬编码实例冲突返回409(api_client: TestClient) -> None:
    """AC2：注册 ID 与硬编码实例冲突时不创建。"""
    response = api_client.post("/api/v1/services", json=_payload(instance_id="postgres-production"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SERVICE_INSTANCE_CONFLICT"


def test_重复注册同ID返回409(api_client: TestClient) -> None:
    """AC2 扩展：重复注册同 ID 仍冲突。"""
    _create_service(api_client)
    response = api_client.post("/api/v1/services", json=_payload())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SERVICE_INSTANCE_CONFLICT"


def test_主密钥未配置时注册被拒绝(monkeypatch: pytest.MonkeyPatch, api_client: TestClient) -> None:
    """AC3：主密钥未配置时拒绝创建，不落任何明文 DSN。"""
    services = api_client.app.state.v1_services
    monkeypatch.setattr(services.service_registration, "_secret_key", None)

    response = api_client.post("/api/v1/services", json=_payload())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SECRET_KEY_NOT_CONFIGURED"
    assert PG_DSN_PLAINTEXT not in response.text


def test_非法服务类型被拒绝(api_client: TestClient) -> None:
    """类型白名单仍拒绝 P12 之外的服务。"""
    response = api_client.post("/api/v1/services", json=_payload(kind="mongodb"))

    assert response.status_code == 422


def test_非法实例ID格式被拒绝(api_client: TestClient) -> None:
    """实例 ID 只允许小写字母/数字/点/下划线/连字符。"""
    response = api_client.post("/api/v1/services", json=_payload(instance_id="Bad ID!"))

    assert response.status_code == 422


def test_已注册服务进入列表且与其他服务同列(api_client: TestClient) -> None:
    """AC4：动态注册服务出现在 GET /services，has_dsn 与掩码正确。"""
    _create_service(api_client)

    response = api_client.get("/api/v1/services")

    assert response.status_code == 200
    items = response.json()["items"]
    ids = [item["id"] for item in items]
    assert "postgres-orders" in ids
    registered = next(item for item in items if item["id"] == "postgres-orders")
    assert registered["has_dsn"] is True
    assert registered["dsn_masked_tail"] == PG_DSN_PLAINTEXT[-4:]
    raw = response.text
    assert PG_DSN_PLAINTEXT not in raw
    assert "user:pass" not in raw


def test_更新标题与DSN并重置状态(api_client: TestClient) -> None:
    """AC5：PUT 更新标题/DSN，掩码随新 DSN 更新。"""
    _create_service(api_client)
    new_dsn = "postgresql://admin:newpass@db-host:5432/warehouse"

    response = api_client.put(
        "/api/v1/services/postgres-orders",
        json={"title": "订单库已换", "dsn": new_dsn},
    )

    assert response.status_code == 200
    service = response.json()["service"]
    assert service["title"] == "订单库已换"
    assert service["has_dsn"] is True
    assert service["dsn_masked_tail"] == new_dsn[-4:]
    raw = response.text
    assert new_dsn not in raw
    assert "newpass" not in raw


def test_更新不存在服务返回404(api_client: TestClient) -> None:
    """PUT 不存在服务 → 404。"""
    response = api_client.put(
        "/api/v1/services/not-exist",
        json={"title": "不存在", "dsn": "postgresql://a:b@c:5432/d"},
    )

    assert response.status_code == 404


def test_删除服务返回204且重复删除仍204(api_client: TestClient) -> None:
    """AC6：DELETE 204，重复删除仍 204，列表不再出现。"""
    _create_service(api_client)

    first = api_client.delete("/api/v1/services/postgres-orders")
    assert first.status_code == 204

    repeat = api_client.delete("/api/v1/services/postgres-orders")
    assert repeat.status_code == 204

    items = api_client.get("/api/v1/services").json()["items"]
    assert "postgres-orders" not in [item["id"] for item in items]


def test_注册redis服务(api_client: TestClient) -> None:
    """Redis 类型可注册。"""
    service = _create_service(api_client, kind="redis", dsn=REDIS_DSN_PLAINTEXT)

    assert service["kind"] == "redis"
    assert service["dsn_masked_tail"] == REDIS_DSN_PLAINTEXT[-4:]


def test_注册mysql服务并保持安全投影(api_client: TestClient) -> None:
    """P12 AC7：MySQL 复用现有 CRUD，响应不回显 DSN。"""
    service = _create_service(
        api_client,
        kind="mysql",
        instance_id="mysql-local",
        title="本地 MySQL",
        dsn=MYSQL_DSN_PLAINTEXT,
    )

    assert service["kind"] == "mysql"
    listed = api_client.get("/api/v1/services").json()["items"]
    mysql_service = next(item for item in listed if item["id"] == "mysql-local")
    assert [item["id"] for item in mysql_service["supported_investigations"]] == [
        "service_health_pressure.v1"
    ]
    assert service["has_dsn"] is True
    assert service["dsn_masked_tail"] == MYSQL_DSN_PLAINTEXT[-4:]
    assert MYSQL_DSN_PLAINTEXT not in str(service)


def test_mysql越界dsn在落库前失败关闭(api_client: TestClient) -> None:
    """P12 AC8：database path 不允许，响应不回显 DSN。"""
    invalid_dsn = "mysql+pymysql://readonly@127.0.0.1:1/business"
    response = api_client.post(
        "/api/v1/services",
        json=_payload(kind="mysql", instance_id="mysql-invalid", dsn=invalid_dsn),
    )

    assert response.status_code == 409
    assert invalid_dsn not in response.text


def test_连接测试对不可达服务返回unavailable与安全原因(api_client: TestClient) -> None:
    """AC7：test-connection 对不可达服务返回 unavailable 与脱敏分类码。"""
    _create_service(api_client)

    response = api_client.post("/api/v1/services/postgres-orders/test-connection")

    assert response.status_code == 200
    body = response.json()
    assert body["service_id"] == "postgres-orders"
    assert body["availability"] in {"healthy", "unavailable", "not_configured"}
    assert body["error_code"] is None or body["error_code"] in {"connection_failed", "not_configured"}
    assert "user:pass" not in response.text
    assert PG_DSN_PLAINTEXT not in response.text


def test_连接测试不存在服务返回404(api_client: TestClient) -> None:
    """test-connection 对不存在服务返回 404。"""
    response = api_client.post("/api/v1/services/not-exist/test-connection")

    assert response.status_code == 404


def test_删除硬编码实例不影响运行时注册表(api_client: TestClient) -> None:
    """AC11/边界：DELETE 硬编码实例（无 DB 行）应幂等 204 且不改变 GET /services。"""
    response = api_client.delete("/api/v1/services/postgres-production")

    assert response.status_code == 204
    items = api_client.get("/api/v1/services").json()["items"]
    assert "postgres-production" in [item["id"] for item in items]


def test_动态注册服务可创建会话并保留历史(api_client: TestClient) -> None:
    """AC10/约束放宽：动态服务可建会话；删除服务后会话历史仍可查。"""
    _create_service(api_client)
    session_response = api_client.post("/api/v1/services/postgres-orders/sessions")
    assert session_response.status_code == 201
    session_id = session_response.json()["session"]["id"]

    delete_response = api_client.delete("/api/v1/services/postgres-orders")
    assert delete_response.status_code == 204

    session_get = api_client.get(f"/api/v1/sessions/{session_id}")
    assert session_get.status_code == 200
    assert session_get.json()["session"]["service_id"] == "postgres-orders"


def test_迁移在存在动态服务关联时拒绝回滚(tmp_path: Path) -> None:
    """P8 迁移 downgrade：session_services 存在动态 service_id 时拒绝回滚。"""
    database_path = tmp_path / "p8-migration.sqlite3"
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
            now = "2026-08-10T00:00:00+00:00"
            connection.exec_driver_sql(
                "INSERT INTO sessions (id, title, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, "迁移守卫", "active", now, now),
            )
            connection.exec_driver_sql(
                "INSERT INTO session_services (session_id, service_id, created_at) VALUES (?, ?, ?)",
                (session_id, "postgres-orders", now),
            )
    finally:
        engine.dispose()
    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "downgrade", "20260810_10_p8_model_mode"],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert downgrade.returncode != 0
    assert "拒绝回滚" in downgrade.stderr
