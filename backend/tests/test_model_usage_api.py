"""P8 用量统计 API 测试（不触发真实 LLM/网络）。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.v1.dependencies import V1Services
from src.application.model_usage import ModelUsageApplicationService
from src.application.services import RunApplicationService, SessionApplicationService
from src.domain.model_usage import MODEL_PRICES_KEY, encode_prices
from src.infrastructure.persistence.app_settings_repository import SqlAlchemyAppSettingsRepository
from src.infrastructure.persistence.database import Base, create_persistence_runtime
from src.infrastructure.persistence.model_usage_repository import (
    SqlAlchemyModelUsageReader,
    SqlAlchemyPriceOverridesReader,
)


class _NoopExecutor:
    """用量测试不触发的确定性执行器占位。"""

    def stream(self, _query: str, _service_id: str | None = None):
        yield from ()
        return None


class _StubAssembler:
    """用量测试不触发的结果组装占位。"""

    def assemble(self, run: object, result: object) -> object:
        raise AssertionError("用量测试不应触发 Run 完成。")


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    """以临时 SQLite 构建 v1 API 客户端，并注入用量应用服务。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")

    database_path = tmp_path / "usage-api.sqlite3"
    runtime = create_persistence_runtime(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(runtime.engine)
    services = V1Services(
        session_factory=runtime.session_factory,
        session_service=SessionApplicationService(runtime.session_factory),
        run_service=RunApplicationService(runtime.session_factory, _NoopExecutor(), _StubAssembler()),
        model_usage_service=ModelUsageApplicationService(
            usage_reader=SqlAlchemyModelUsageReader(runtime.session_factory),
            price_reader=SqlAlchemyPriceOverridesReader(runtime.session_factory),
        ),
    )
    monkeypatch.setenv("OPERMIND_APP_DATABASE_URL", f"sqlite:///{database_path.as_posix()}")

    from src import app as api_module

    monkeypatch.setattr(api_module.app.state, "v1_services", services)
    with TestClient(api_module.app, raise_server_exceptions=False) as client:
        yield client
    runtime.engine.dispose()


def _insert_usage(client: TestClient, model: str, input_tokens: int, output_tokens: int, total_tokens: int, days_ago: int = 0) -> None:
    """直接向应用库插入一条用量记录（走仓储，不经 LLM）。"""
    from src.infrastructure.persistence.model_usage_repository import SqlAlchemyUsageRecorder

    recorder = SqlAlchemyUsageRecorder(client.app.state.v1_services.session_factory)
    recorder.record(
        {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "occurred_at": datetime.now(UTC) - timedelta(days=days_ago),
        }
    )


def test_无记录返回空态(api_client: TestClient) -> None:
    """AC6: 无用量记录时返回空 items，HTTP 200，不抛错。"""
    response = api_client.get("/api/v1/model/usage")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["estimate"] is True
    assert body["items"] == []


def test_按模型聚合返回token与估算花费(api_client: TestClient) -> None:
    """AC2/AC4: 有记录时按模型分组聚合，返回 token 与估算花费（内置默认单价）。"""
    _insert_usage(api_client, "deepseek-chat", 100, 50, 150)
    _insert_usage(api_client, "deepseek-chat", 200, 100, 300)
    _insert_usage(api_client, "gpt-4o-mini", 1000, 500, 1500)

    response = api_client.get("/api/v1/model/usage")
    assert response.status_code == 200, response.text
    items = {item["model"]: item for item in response.json()["items"]}

    deepseek = items["deepseek-chat"]
    assert deepseek["input_tokens"] == 300
    assert deepseek["output_tokens"] == 150
    assert deepseek["total_tokens"] == 450
    assert deepseek["price_source"] == "builtin"
    # 10000*1.0/1e6 + 5000*2.0/1e6 ... 精确计算：300*1.0/1e6 + 150*2.0/1e6 = 0.0006
    assert deepseek["estimated_cost"] == pytest.approx(300 * 1.0 / 1e6 + 150 * 2.0 / 1e6)

    mini = items["gpt-4o-mini"]
    assert mini["price_source"] == "builtin"
    assert mini["estimated_cost"] == pytest.approx(1000 * 1.5 / 1e6 + 500 * 6.0 / 1e6)


def test_时间窗过滤只返回窗口内(api_client: TestClient) -> None:
    """AC3: from/to 过滤只返回窗口内用量。"""
    _insert_usage(api_client, "deepseek-chat", 100, 50, 150, days_ago=10)
    _insert_usage(api_client, "deepseek-chat", 200, 100, 300, days_ago=0)

    now = datetime.now(UTC)
    response = api_client.get(
        "/api/v1/model/usage",
        params={
            "from": (now - timedelta(days=2)).isoformat(),
            "to": (now + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["total_tokens"] == 300


def test_模型过滤(api_client: TestClient) -> None:
    """model 参数只返回指定模型的聚合。"""
    _insert_usage(api_client, "deepseek-chat", 100, 50, 150)
    _insert_usage(api_client, "gpt-4o-mini", 1000, 500, 1500)

    response = api_client.get("/api/v1/model/usage", params={"model": "gpt-4o-mini"})
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["model"] == "gpt-4o-mini"


def test_from晚于to返回422(api_client: TestClient) -> None:
    """时间窗起点晚于终点应 422。"""
    now = datetime.now(UTC)
    response = api_client.get(
        "/api/v1/model/usage",
        params={
            "from": (now + timedelta(days=1)).isoformat(),
            "to": now.isoformat(),
        },
    )
    assert response.status_code == 422, response.text


def test_窗口跨度超过366天返回422(api_client: TestClient) -> None:
    """窗口跨度上限 366 天。"""
    now = datetime.now(UTC)
    response = api_client.get(
        "/api/v1/model/usage",
        params={
            "from": (now - timedelta(days=400)).isoformat(),
            "to": now.isoformat(),
        },
    )
    assert response.status_code == 422, response.text


def test_配置单价后按配置估算(api_client: TestClient) -> None:
    """AC4: app_settings 配置单价后按配置估算，标注 configured。"""
    session = api_client.app.state.v1_services.session_factory()
    try:
        SqlAlchemyAppSettingsRepository(session).set(
            MODEL_PRICES_KEY,
            encode_prices({"deepseek-chat": {"input": 3.0, "output": 6.0}}),
        )
        session.commit()
    finally:
        session.close()

    _insert_usage(api_client, "deepseek-chat", 1000, 500, 1500)
    response = api_client.get("/api/v1/model/usage")
    items = {item["model"]: item for item in response.json()["items"]}
    item = items["deepseek-chat"]
    assert item["price_source"] == "configured"
    assert item["price_per_million_input"] == 3.0
    assert item["price_per_million_output"] == 6.0
    assert item["estimated_cost"] == pytest.approx(1000 * 3.0 / 1e6 + 500 * 6.0 / 1e6)


def test_未列出模型回退通用默认并标注unset(api_client: TestClient) -> None:
    """未在默认表且未配置的模型：用通用默认，标注 unset。"""
    _insert_usage(api_client, "custom-model-x", 1000, 1000, 2000)
    response = api_client.get("/api/v1/model/usage")
    items = {item["model"]: item for item in response.json()["items"]}
    item = items["custom-model-x"]
    assert item["price_source"] == "unset"
    assert item["estimated_cost"] == pytest.approx(1000 * 1.0 / 1e6 + 1000 * 2.0 / 1e6)


def test_响应不含凭据与调用内容(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC7: 响应不得包含 API Key、sk-、DSN 或调用内容。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "sk-real-key-1234567890abcdef")
    _insert_usage(api_client, "deepseek-chat", 100, 50, 150)
    response = api_client.get("/api/v1/model/usage")
    assert response.status_code == 200
    assert "sk-real-key-1234567890abcdef" not in response.text
    assert "api_key" not in response.text
    assert "postgresql://" not in response.text
    assert "prompt" not in response.text.lower()


def test_mock模式统计为空态(api_client: TestClient) -> None:
    """AC5: mock 模式无采集，统计返回空 items（不伪造记录）。"""
    response = api_client.get("/api/v1/model/usage")
    assert response.status_code == 200
    assert response.json()["items"] == []
