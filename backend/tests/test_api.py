"""基础 HTTP 接口（/health）与多 Agent 内核流式安全边界测试。

旧 `/diagnose`、`/diagnose/stream`、`/memory/*` 接口已移除；诊断只经 v1 Run 主脊执行。
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.agents.report_agent import ReportAgent
from src.core.coordinator import CoordinatorAgent
from src.core.debate import DebateArena
from src.core.llm import LLMClient
from src.core.reflection import ReflectionEngine


class _StubAgent:
    """用于隔离测试的确定性领域 Agent。"""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self, _query: str) -> str:
        """返回稳定的领域诊断结果。"""
        return f"{self.name} 的诊断结论"

    def get_thinking(self) -> list[str]:
        """返回稳定的 Agent 思考摘要。"""
        return [f"{self.name} 已完成"]


def _build_mock_coordinator() -> CoordinatorAgent:
    """构建不会写入长期记忆的 mock 编排器。"""
    llm = LLMClient(api_key="mock", base_url="http://mock", model="mock")
    coordinator = CoordinatorAgent(
        llm=llm,
        debate=DebateArena(llm=llm),
        reflection=ReflectionEngine(llm=llm),
        report=ReportAgent(),
    )
    for name in ("db", "server", "log"):
        coordinator.register_agent(name, _StubAgent(name))
    return coordinator


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """以 mock 模型环境构建 API 客户端，避免导入时触发真实系统副作用。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")

    from src import app as api_module

    with TestClient(api_module.app, raise_server_exceptions=False) as client:
        yield client


def test_健康检查不暴露密钥(api_client: TestClient) -> None:
    """健康检查应返回模式和模型，但不可泄露 API Key。"""
    response = api_client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "mode": "mock", "model": "mock"}
    assert "api_key" not in body


def test_未装配时环境变量回退可用(monkeypatch: pytest.MonkeyPatch) -> None:
    """应用未装配时的健康检查回退路径必须能真正执行。

    历史缺陷：`src/app.py` 用了 `os.environ` 但漏了 `import os`，
    这条回退分支和空 api_key 的模式判定都会直接 NameError。
    """
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")

    from src import app as api_module

    config = api_module._env_config_fallback()

    assert config["llm"] == {"api_key": "mock", "base_url": "http://mock", "model": "mock"}
    # 独立裁判（judge_llm）已收口为未启用（issue #104），健康检查回退不再兜该字段。
    assert "judge_llm" not in config


def test_模式判定在空密钥下不抛异常(monkeypatch: pytest.MonkeyPatch) -> None:
    """config 未带 api_key 时会退到环境变量，这条短路右侧同样不能 NameError。"""
    monkeypatch.delenv("OPERMIND_API_KEY", raising=False)

    from src import app as api_module

    # 空 api_key 且环境变量缺失：判定为 mock（诚实空态，无可用 Key），且不得抛异常。
    assert api_module._service_mode({"llm": {"api_key": ""}}) == "mock"

    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    assert api_module._service_mode({"llm": {}}) == "mock"


def test_服务列表返回多个实例且不暴露凭据(api_client: TestClient) -> None:
    """正式服务列表返回固定 PostgreSQL 实例，响应不携带配置敏感信息。"""
    response = api_client.get("/api/v1/services")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [
        "postgres-production",
        "postgres-staging",
        "postgres-target",
        "redis-production",
    ]
    redis_item = next(item for item in body["items"] if item["id"] == "redis-production")
    assert redis_item["kind"] == "redis"
    assert redis_item["snapshot"]["availability"] == "not_configured"
    # P6：服务响应恒携带主机指标对象（诚实状态），不暴露敏感信息
    assert all("host_metrics" in item for item in body["items"])
    assert redis_item["host_metrics"]["source_status"] in {"available", "unavailable"}
    assert redis_item["host_metrics"]["mode"] in {"mock", "target"}
    serialized = response.text
    assert "OPERMIND_SERVICE_" not in serialized
    assert "postgresql://" not in serialized
    assert "password" not in serialized


def test_内核流式执行异常返回安全错误(monkeypatch: pytest.MonkeyPatch) -> None:
    """图执行异常时，内核流式接口只暴露安全错误码和通用提示。"""
    coordinator = _build_mock_coordinator()

    class _BrokenGraph:
        def stream(self, _state: dict[str, object], stream_mode: str) -> Iterator[dict[str, object]]:
            """模拟编排图的运行时异常。"""
            raise RuntimeError("内部测试异常")
            yield {}

    monkeypatch.setattr(coordinator, "_ensure_graph", lambda: _BrokenGraph())
    items = list(coordinator.route_stream("测试流式异常"))

    assert items[-1]["kind"] == "error"
    assert items[-1]["code"] == "DIAGNOSIS_FAILED"
    assert items[-1]["message"] == "诊断执行失败，请稍后重试"


def test_内核图构建异常返回安全错误(monkeypatch: pytest.MonkeyPatch) -> None:
    """首次构建图失败时，Coordinator 仍应输出标准 error 事件。"""
    coordinator = _build_mock_coordinator()

    def _raise_build_error() -> object:
        raise RuntimeError("图构建失败")

    monkeypatch.setattr(coordinator, "_ensure_graph", _raise_build_error)
    items = list(coordinator.route_stream("测试图构建异常"))

    assert items == [
        {
            "kind": "error",
            "code": "DIAGNOSIS_FAILED",
            "message": "诊断执行失败，请稍后重试",
        }
    ]


def test_未知内部trace类型映射为受控契约() -> None:
    """内部 trace 自带未知 type 时，内核仍只输出约定事件类型。"""
    coordinator = _build_mock_coordinator()

    trace = coordinator._normalize_trace(
        [{"type": "future_event", "node": "future_node", "detail": "未来节点完成"}]
    )

    assert trace[0]["type"] == "report"
