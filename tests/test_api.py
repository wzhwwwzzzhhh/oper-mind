"""M6 后端 API 与 SSE 流式诊断测试。"""

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.api.events import (
    DiagnosisCompleteEvent,
    DiagnosisProgressEvent,
    serialize_sse,
)
from src.api.schemas import TraceEvent
from src.core.coordinator import CoordinatorAgent
from src.core.debate import DebateArena
from src.core.experiment import get_experiment_condition
from src.core.llm import LLMClient
from src.core.reflection import ReflectionEngine
from src.agents.report_agent import ReportAgent


class _StubAgent:
    """用于隔离 API 测试的确定性领域 Agent。"""

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
        experiment_condition=get_experiment_condition("full"),
    )
    for name in ("db", "server", "log"):
        coordinator.register_agent(name, _StubAgent(name))
    return coordinator


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """替换模块单例，避免导入 API 时触发真实系统副作用。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")

    from src import app as api_module

    monkeypatch.setattr(api_module, "coordinator", _build_mock_coordinator())
    with TestClient(api_module.app, raise_server_exceptions=False) as client:
        yield client


def test_健康检查不暴露密钥(api_client: TestClient) -> None:
    """健康检查应返回模式和模型，但不可泄露 API Key。"""
    response = api_client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "mode": "mock", "model": "mock"}
    assert "api_key" not in body


def test_同步诊断返回稳定契约(api_client: TestClient) -> None:
    """同步接口在请求 trace 时应返回可视化所需字段。"""
    response = api_client.post(
        "/diagnose",
        json={"query": "明天大促，帮我全面体检一下系统整体健康度", "show_thinking": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result"]
    assert body["strategy"] == "parallel"
    assert body["thinking"]
    assert body["trace"]
    assert {"type", "node", "detail", "timestamp"} <= set(body["trace"][0])


def test_空请求返回统一校验错误(api_client: TestClient) -> None:
    """同步 API 的空白问题应返回统一错误体。"""
    response = api_client.post("/diagnose", json={"query": "   "})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"] == "请求参数不合法"
    assert body["details"]


def test_sse_依次输出进度与完成事件(api_client: TestClient) -> None:
    """SSE 应先输出节点进度，最后输出带终稿的 complete 事件。"""
    with api_client.stream(
        "GET",
        "/diagnose/stream",
        params={"query": "明天大促，帮我全面体检一下系统整体健康度"},
    ) as response:
        payloads = [
            json.loads(line.removeprefix("data: "))
            for line in response.iter_lines()
            if line.startswith("data: ")
        ]

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert payloads[0]["type"] == "route_decided"
    assert any(payload["type"] == "agent_start" for payload in payloads)
    assert payloads[-1]["type"] == "complete"
    assert payloads[-1]["strategy"] == "parallel"
    assert payloads[-1]["result"]


def test_sse_空请求返回统一错误(api_client: TestClient) -> None:
    """SSE 查询参数为空时不应建立流，而应返回统一错误体。"""
    response = api_client.get("/diagnose/stream", params={"query": " "})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_sse序列化遵循标准帧格式() -> None:
    """事件序列化必须满足 event/data/空行分隔的 SSE 规范。"""
    event = DiagnosisProgressEvent(
        type="route_decided",
        node="route",
        detail="兜底关键词路由 → direct",
        timestamp="2026-07-24T00:00:00+00:00",
    )
    frame = serialize_sse("progress", event)

    assert frame.startswith("event: progress\ndata: {")
    assert frame.endswith("\n\n")


def test_sse完成事件带完整trace() -> None:
    """完成事件必须能够承载前端 trace 回放数据。"""
    trace = [
        TraceEvent(
            type="route_decided",
            node="route",
            detail="兜底关键词路由 → direct",
            timestamp="2026-07-24T00:00:00+00:00",
        )
    ]
    event = DiagnosisCompleteEvent(result="报告", strategy="direct", trace=trace)

    assert event.trace[0].node == "route"


def test_sse流式异常返回安全错误(monkeypatch: pytest.MonkeyPatch) -> None:
    """图执行异常时，流式接口只暴露安全错误码和通用提示。"""
    llm = LLMClient(api_key="mock", base_url="http://mock", model="mock")
    coordinator = CoordinatorAgent(
        llm=llm,
        debate=DebateArena(llm=llm),
        reflection=ReflectionEngine(llm=llm),
        report=ReportAgent(),
    )

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

def test_sse图构建异常返回安全错误(monkeypatch: pytest.MonkeyPatch) -> None:
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
    """内部 trace 自带未知 type 时，公开 API 仍只输出约定事件类型。"""
    coordinator = _build_mock_coordinator()

    trace = coordinator._normalize_trace(
        [
            {
                "type": "future_event",
                "node": "future_node",
                "detail": "未来节点完成",
            }
        ]
    )

    assert trace[0]["type"] == "report"


def test_sse序列化异常仍输出标准错误(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SSE 适配层的模型校验异常不应直接中断 HTTP 流。"""
    from src import app as api_module

    def _invalid_stream(_query: str) -> Iterator[dict[str, object]]:
        yield {
            "kind": "trace",
            "event": {
                "type": "route_decided",
                "node": "route",
                "detail": "缺少时间戳",
            },
        }

    monkeypatch.setattr(api_module.coordinator, "route_stream", _invalid_stream)
    with api_client.stream("GET", "/diagnose/stream", params={"query": "测试"}) as response:
        frames = [line for line in response.iter_lines() if line]

    assert response.status_code == 200
    assert frames[0] == "event: error"
    payload = json.loads(frames[1].removeprefix("data: "))
    assert payload["code"] == "STREAM_SERIALIZATION_FAILED"