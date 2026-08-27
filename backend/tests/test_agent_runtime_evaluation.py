"""Issue #98：Agent 运行真实性与安全投影的确定性评测基线。"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from data.scenarios import clear_active_scenario, set_active_scenario

from src.agents.report_agent import ReportAgent
from src.core.bootstrap import build_coordinator
from src.core.coordinator import CoordinatorAgent
from src.core.llm import LLMClient
from src.core.mock_runtime import assess_mock_conflict, assess_mock_reflection
from src.core.tool_gateway import ToolGateway
from src.core.tool_registry import Tool, ToolExecutionResult, ToolRegistry
from src.tools.db_tools import ExplainTool
from tests.support.agent_runtime_evaluation import RuntimeSnapshot, evaluate_runtime_snapshot


@pytest.fixture(autouse=True)
def _reset_scenario() -> Iterator[None]:
    """评测样例之间不共享激活场景。"""
    clear_active_scenario()
    yield
    clear_active_scenario()


def _schemas(*names: str) -> list[dict]:
    """构造只含工具名的最小 Function Calling 菜单。"""
    return [
        {
            "type": "function",
            "function": {"name": name, "description": name, "parameters": {"type": "object"}},
        }
        for name in names
    ]


def _mock_llm() -> LLMClient:
    return LLMClient(api_key="mock", base_url="http://mock", model="mock")


@pytest.mark.parametrize(
    ("query", "tools", "allowed"),
    [
        ("检查数据库慢查询", ("explain_sql", "show_index"), {"explain_sql", "show_index"}),
        ("检查服务器磁盘", ("check_cpu", "check_disk"), {"check_cpu", "check_disk"}),
        ("检索错误日志", ("search_logs", "aggregate_errors"), {"search_logs", "aggregate_errors"}),
        ("检索知识库操作手册", ("search_knowledge",), {"search_knowledge"}),
    ],
)
def test_mock规划只会选择当前角色工具(
    query: str,
    tools: tuple[str, ...],
    allowed: set[str],
) -> None:
    """角色菜单互斥，mock 规划不得跨域调用工具。"""
    set_active_scenario("S1")
    response = _mock_llm().chat([{"role": "user", "content": query}], tools=_schemas(*tools))
    calls = response.get("tool_calls", [])
    assert calls
    assert {call["function"]["name"] for call in calls} <= allowed


@pytest.mark.parametrize(
    ("query", "expected_tool"),
    [
        ("请检查数据库锁等待与阻塞情况", "check_lock_status"),
        ("请检查数据库连接池是否耗尽", "check_connection_pool"),
    ],
)
def test_mock数据库显式诊断意图优先选择对应工具(query: str, expected_tool: str) -> None:
    """锁与连接池问题必须命中专用只读工具，不能被通用 Explain 抢先。"""
    set_active_scenario("S1")
    response = _mock_llm().chat(
        [{"role": "user", "content": query}],
        tools=_schemas(
            "explain_sql",
            "show_index",
            "show_create_table",
            "check_lock_status",
            "check_connection_pool",
        ),
    )

    calls = response.get("tool_calls", [])
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == expected_tool


@pytest.mark.parametrize(
    ("query", "summary_fragment"),
    [
        ("请检查数据库锁等待与阻塞情况", "锁等待"),
        ("请检查数据库连接池是否耗尽", "连接"),
    ],
)
def test_mock数据库专项问题经正式图产出专用工具事件(query: str, summary_fragment: str) -> None:
    """P7 专项问题必须经过 DB Agent，并向公开 Trace 投影对应工具的脱敏摘要。"""
    set_active_scenario("S1")
    items = list(build_coordinator(_mock_llm(), enable_long_term_memory=False).route_stream(query))
    complete = items[-1]

    assert complete["kind"] == "complete"
    assert complete["strategy"] == "direct"
    starts = [event for event in complete["trace"] if event["type"] == "agent_start"]
    assert len(starts) == 1 and "Agent=db" in starts[0]["detail"]
    tool_events = [event for event in complete["trace"] if event["type"] == "tool_invoked"]
    assert len(tool_events) == 1
    assert tool_events[0].get("role") == "db"
    assert summary_fragment in tool_events[0]["detail"]


def test_mock混合工具菜单失败关闭() -> None:
    """混合角色工具菜单不能猜测角色或选择越权工具。"""
    response = _mock_llm().chat(
        [{"role": "user", "content": "检查故障"}],
        tools=_schemas("explain_sql", "check_cpu"),
    )
    assert "tool_calls" not in response
    assert "工具边界" in response["content"]


def test_mock工具菜单任一条目畸形即整体失败关闭() -> None:
    """合法 DB schema 混入畸形项时不得静默忽略畸形项。"""
    tools = [*_schemas("explain_sql"), {"type": "function", "function": {"description": "missing name"}}]
    response = _mock_llm().chat([{"role": "user", "content": "检查数据库"}], tools=tools)
    assert "tool_calls" not in response
    assert "失败关闭" in response["content"]


def test_mock工具结果生成角色化且带来源的结论() -> None:
    """不同领域的工具结果不能坍缩成同一条数据库固定结论。"""
    set_active_scenario("S1")
    llm = _mock_llm()
    db = llm.chat(
        [
            {"role": "user", "content": "检查数据库"},
            {"role": "assistant", "content": None, "tool_calls": [{"function": {"name": "explain_sql"}}]},
            {"role": "tool", "content": "访问类型：ALL"},
        ],
        tools=_schemas("explain_sql"),
    )["content"]
    server = llm.chat(
        [
            {"role": "user", "content": "检查服务器"},
            {"role": "assistant", "content": None, "tool_calls": [{"function": {"name": "check_cpu"}}]},
            {"role": "tool", "content": "CPU 使用率 92%"},
        ],
        tools=_schemas("check_cpu"),
    )["content"]
    assert db != server
    assert "证据来源：数据库工具" in db
    assert "证据来源：服务器工具" in server
    assert "添加索引" not in server
    assert "orders.status" not in server
    assert "影响证据" in server
    assert "模拟场景" in db and "模拟场景" in server


def test_mock结论绑定实际工具类别且知识标题安全() -> None:
    """S2 CPU 事实不得被总结为磁盘写满，知识证据只投影安全标题。"""
    set_active_scenario("S2")
    llm = _mock_llm()
    cpu = llm.chat(
        [
            {"role": "user", "content": "检查 CPU"},
            {"role": "assistant", "content": None, "tool_calls": [{"function": {"name": "check_cpu"}}]},
            {"role": "tool", "content": "CPU 使用率 35%"},
        ],
        tools=_schemas("check_cpu"),
    )["content"]
    knowledge = llm.chat(
        [
            {"role": "user", "content": "检索知识库"},
            {"role": "assistant", "content": None, "tool_calls": [{"function": {"name": "search_knowledge"}}]},
            {"role": "tool", "content": "知识检索命中 1 篇：- 《数据库应急手册<script>》"},
        ],
        tools=_schemas("search_knowledge"),
    )["content"]
    assert "磁盘空间接近耗尽" not in cpu
    assert "CPU 事实已采集" in cpu
    assert "《数据库应急手册》" in knowledge
    assert "<script>" not in knowledge


def test_mock数据库工具只消费显式场景事实() -> None:
    """没有 DB 场景事实时返回未知，不再读取全局 mock_db 或制造回退指标。"""
    set_active_scenario("S2")
    result = ExplainTool().execute("SELECT * FROM orders")
    assert "未提供数据库执行计划事实" in result
    assert "全表扫描" not in result


def test_mock质量节点只在真实冲突或证据不足时告警() -> None:
    """Debate/Reflection 状态来自输入事实，不再无条件通过或制造分歧。"""
    assert not assess_mock_conflict(
        {
            "db": "模拟场景证据来源：数据库工具；根因域：server",
            "server": "模拟场景证据来源：服务器工具；根因域：server",
        }
    )
    assert assess_mock_conflict(
        {
            "db": "模拟场景证据来源：数据库工具；根因域：db",
            "server": "模拟场景证据来源：服务器工具；根因域：server",
        }
    )
    assert assess_mock_reflection("## DB 诊断\n根因为连接耗尽")
    assert not assess_mock_reflection("## DB 诊断\n暂无可用证据，当前结论未知")


def test_public报告不回显请求和敏感哨兵() -> None:
    """公开报告只保留安全投影，不含 query、原始 SQL、路径、DSN、Key 或 traceback。"""
    key_sentinel = "sk" + "-runtime-secret"
    query = "请检查绝密工单-98，并执行 SELECT secret FROM account"
    diagnosis = (
        "证据来源：数据库工具；根因域：db\n"
        "SELECT secret FROM account\n"
        "建议执行 ALTER TABLE account ADD secret text\n"
        "C:\\private\\runtime.txt\n"
        "/data\n/\n`/data`\n\"/data\"\n路径=/data。\n"
        '工具实参={"query":"绝密工单"}\n'
        'arguments: {"table":"orders"}\n'
        '{"arguments":{"path":"/data"}}\n'
        '{"api_key":"plain-secret-value"}\n'
        "postgresql://user:password@db/internal\n"
        f"api_key={key_sentinel}\nTraceback (most recent call last)"
    )
    report = ReportAgent().generate(query, {"db": diagnosis})
    for forbidden in (
        "绝密工单-98",
        "SELECT secret",
        "ALTER TABLE",
        "C:\\private",
        "/data",
        "工具实参",
        "arguments:",
        "plain-secret-value",
        "postgresql://",
        key_sentinel,
        "Traceback",
        "{raw}",
    ):
        assert forbidden not in report
    assert "数据库/SQL 诊断请求" in report


def test_无适用领域不启动Agent或补造证据() -> None:
    """无关键词 direct 请求应诚实跳过，不发 Agent 启动或工具调用事件。"""
    set_active_scenario("S1")
    items = list(build_coordinator(_mock_llm(), enable_long_term_memory=False).route_stream("你好"))
    complete = items[-1]
    assert complete["kind"] == "complete"
    assert "当前结论未知" in complete["result"]
    trace_types = [item["event"]["type"] for item in items if item["kind"] == "trace"]
    assert "agent_start" not in trace_types
    assert "tool_invoked" not in trace_types
    quality = {
        event["node"]: event.get("status")
        for event in complete["trace"]
        if event["node"] in {"conflict_check", "debate", "reflection"}
    }
    assert quality == {"conflict_check": "skipped", "debate": "skipped", "reflection": "skipped"}


def test_Coordinator异常日志不含message或traceback(caplog: pytest.LogCaptureFixture) -> None:
    """流式失败日志只记录固定错误码与异常类型。"""

    class FailingGraph:
        def stream(self, *_args: object, **_kwargs: object) -> Iterator[dict]:
            raise RuntimeError("内部路径与凭据哨兵")
            yield {}

    coordinator = build_coordinator(_mock_llm(), enable_long_term_memory=False)
    coordinator._graph = FailingGraph()
    with caplog.at_level(logging.WARNING, logger="src.core.coordinator"):
        items = list(coordinator.route_stream("检查"))
    assert items == [{"kind": "error", "code": "DIAGNOSIS_FAILED", "message": "诊断执行失败，请稍后重试"}]
    assert "DIAGNOSIS_FAILED" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "内部路径与凭据哨兵" not in caplog.text
    assert "Traceback" not in caplog.text


def _deterministic_run_snapshot(scenario: str) -> dict[str, object]:
    """执行一次完整 mock 图并移除时间、耗时等非确定字段。"""
    set_active_scenario(scenario)
    coordinator = build_coordinator(_mock_llm(), enable_long_term_memory=False)
    items = list(coordinator.route_stream("全面体检并定位故障"))
    complete = items[-1]
    assert complete["kind"] == "complete"
    return {
        "report": complete["result"],
        "strategy": complete["strategy"],
        "trace": [
            {
                "type": event["type"],
                "node": event["node"],
                "status": event.get("status"),
                "role": event.get("role"),
            }
            for event in complete["trace"]
        ],
    }


@pytest.mark.parametrize(
    ("query", "expected_role"),
    [
        ("检查数据库 SQL", "db"),
        ("检查服务器 CPU", "server"),
        ("检索错误日志", "log"),
        ("检索知识库操作手册", "knowledge"),
    ],
)
def test_评测矩阵四个单域direct(
    query: str,
    expected_role: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """四个领域 direct 必须只启动并调用目标角色。"""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "ops.md").write_text(
        "# 检索知识库操作手册\n\n检索知识库操作手册：只读排障前先确认目标边界。\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPERMIND_KNOWLEDGE_DIR", str(knowledge_dir))
    set_active_scenario("S1")
    items = list(build_coordinator(_mock_llm(), enable_long_term_memory=False).route_stream(query))
    complete = items[-1]
    assert complete["kind"] == "complete"
    assert complete["strategy"] == "direct"
    starts = [event for event in complete["trace"] if event["type"] == "agent_start"]
    assert len(starts) == 1 and expected_role in starts[0]["detail"]
    tool_events = [event for event in complete["trace"] if event["type"] == "tool_invoked"]
    assert tool_events
    assert {event.get("role") for event in tool_events} == {expected_role}
    assert {event.get("status") for event in tool_events} == {"ok"}
    if expected_role == "knowledge":
        assert "《检索知识库操作手册》" in complete["result"]
    assert any(event["node"] == "conflict_check" and event.get("status") == "skipped" for event in complete["trace"])


def test_Knowledge未配置的工具事件明确unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """知识目录缺失时结论与 Tool Trace 都必须诚实降级。"""
    monkeypatch.setenv("OPERMIND_KNOWLEDGE_DIR", str(tmp_path / "missing"))
    set_active_scenario("S1")
    items = list(build_coordinator(_mock_llm(), enable_long_term_memory=False).route_stream("检索知识库操作手册"))
    complete = items[-1]
    assert complete["kind"] == "complete"
    tool_events = [event for event in complete["trace"] if event["type"] == "tool_invoked"]
    assert len(tool_events) == 1
    assert tool_events[0]["status"] == "unavailable"
    assert "当前结论未知" in complete["result"]
    assert any(event["node"] == "reflection" and event.get("status") == "skipped" for event in complete["trace"])


def test_评测矩阵chain保持角色顺序() -> None:
    """chain 正向路径保持 server→db→log，且质量分歧节点明确未执行。"""
    set_active_scenario("S1")
    items = list(build_coordinator(_mock_llm(), enable_long_term_memory=False).route_stream("数据库日志故障排查"))
    complete = items[-1]
    assert complete["kind"] == "complete"
    assert complete["strategy"] == "chain"
    roles = [event.get("role") for event in complete["trace"] if event["type"] == "tool_invoked"]
    assert roles == ["server", "db", "log"]
    assert any(event["node"] == "debate" and event.get("status") == "skipped" for event in complete["trace"])


class _FixedAgent:
    def __init__(self, result: str) -> None:
        self._result = result

    def run(self, _query: str) -> str:
        return self._result

    def get_thinking(self) -> list[dict[str, str]]:
        return []

    def get_tool_invocations(self) -> list[object]:
        return []


class _EvidenceTool(Tool):
    def __init__(self, name: str, output: str) -> None:
        super().__init__(name, "评测证据工具", {"type": "object", "properties": {}})
        self._output = output

    def execute(self) -> str:
        return self._output


class _ToolBackedAgent(_FixedAgent):
    def __init__(self, result: str, tool_name: str, tool_output: str) -> None:
        super().__init__(result)
        self._tool_name = tool_name
        self._tool_output = tool_output
        self._records: list[object] = []

    def run(self, _query: str) -> str:
        registry = ToolRegistry()
        registry.register(_EvidenceTool(self._tool_name, self._tool_output))
        gateway = ToolGateway(registry)
        try:
            self._records = [gateway.invoke(self._tool_name, "{}").record]
        finally:
            gateway.shutdown()
        return self._result

    def get_tool_invocations(self) -> list[object]:
        return self._records


def test_评测矩阵实际冲突触发确定性Debate() -> None:
    """parallel 的两条有来源冲突结论必须真正进入 Debate，且不伪造已裁决共识。"""
    coordinator = CoordinatorAgent(
        llm=_mock_llm(),
        debate=object(),
        reflection=object(),
        report=ReportAgent(),
    )
    coordinator.register_agent(
        "db",
        _ToolBackedAgent(
            "模拟场景证据来源：数据库工具；根因域：db；执行计划异常。",
            "explain_sql",
            "访问类型：ALL",
        ),
    )
    coordinator.register_agent(
        "server",
        _ToolBackedAgent(
            "模拟场景证据来源：服务器工具；根因域：server；磁盘空间耗尽。",
            "check_disk",
            "磁盘使用率：98%",
        ),
    )
    items = list(coordinator.route_stream("全面体检"))
    complete = items[-1]
    assert complete["kind"] == "complete"
    debate_events = [event for event in complete["trace"] if event["node"] == "debate"]
    assert debate_events and debate_events[-1]["status"] == "ok"
    tool_events = [event for event in complete["trace"] if event["type"] == "tool_invoked"]
    assert {event.get("role") for event in tool_events} == {"db", "server"}
    assert all(event.get("status") == "ok" for event in tool_events)
    assert "模拟场景辩论" in complete["result"]
    assert "保留冲突" in complete["result"]


class _UnverifiableReport:
    def generate(self, _query: str, _diagnoses: dict[str, str]) -> str:
        return "## 诊断\n根因为未经证据支持的固定结论。"


def test_Reflection修订上限后明确failed() -> None:
    """有来源输入若被报告丢弃，复审不得在修订上限后显示成功或仅提醒。"""
    coordinator = CoordinatorAgent(
        llm=_mock_llm(),
        debate=object(),
        reflection=object(),
        report=_UnverifiableReport(),
    )
    coordinator.register_agent("db", _FixedAgent("模拟场景证据来源：数据库工具；根因域：db；执行计划异常。"))
    items = list(coordinator.route_stream("检查数据库 SQL"))
    complete = items[-1]
    assert complete["kind"] == "complete"
    reflection_events = [event for event in complete["trace"] if event["node"] == "reflection"]
    assert [event.get("status") for event in reflection_events] == ["attention", "attention", "failed"]


class _UnavailableTool(Tool):
    def __init__(self) -> None:
        super().__init__("unavailable", "不可用桩", {"type": "object", "properties": {}})

    def execute(self) -> ToolExecutionResult:
        return ToolExecutionResult(status="unavailable", output="采集不可用", summary="采集不可用")


def test_评测矩阵ToolGateway拒绝与不可用不伪装成功() -> None:
    """实际网关结果必须分别保留 rejected 与 unavailable。"""
    registry = ToolRegistry()
    registry.register(_UnavailableTool())
    gateway = ToolGateway(registry)
    try:
        assert gateway.invoke("missing", "{}").record.status == "rejected"
        assert gateway.invoke("unavailable", "{}").record.status == "unavailable"
    finally:
        gateway.shutdown()


class _RealRouteLLM:
    client = SimpleNamespace(api_key="real")

    def chat(self, _messages: list[dict[str, Any]], **_kwargs: object) -> dict[str, str]:
        return {"content": '{"strategy":"direct","target":null}'}


class _NoIssuesReflection:
    def collect_feedback(self, _report: str, _reviewers: list[object]) -> list[str]:
        return []


def test_real路由target为空仍保留默认DB兼容兜底() -> None:
    """real LLM 的合法 direct+null 仍沿用基线默认 DB，不受 mock fail-closed 影响。"""
    coordinator = CoordinatorAgent(
        llm=_RealRouteLLM(),  # type: ignore[arg-type]
        debate=object(),
        reflection=_NoIssuesReflection(),
        report=ReportAgent(),
    )
    coordinator.register_agent("db", _FixedAgent("证据来源：数据库工具；当前未见异常。"))
    items = list(coordinator.route_stream("未包含领域关键词"))
    complete = items[-1]
    assert complete["kind"] == "complete"
    assert any(event["type"] == "agent_start" and "db" in event["detail"] for event in complete["trace"])


@pytest.mark.parametrize("scenario", ["S1", "S2", "S3", "S4"])
def test_完整mock评测快照重复执行一致(scenario: str) -> None:
    """同场景以隔离内核运行两次，报告和规范化 Trace 必须逐字一致。"""
    assert _deterministic_run_snapshot(scenario) == _deterministic_run_snapshot(scenario)


def test_负向评测器按类别捕获已知违规() -> None:
    """坏快照必须同时触发角色、证据、公开安全和虚假成功四类门禁。"""
    bad: RuntimeSnapshot = {
        "mode": "mock",
        "role_tools": {"server": ["explain_sql"]},
        "evidence": [
            {
                "claim": "CPU 使用率正常，但磁盘空间已耗尽",
                "source": "工具",
                "source_role": "server",
                "source_tool": "check_cpu",
                "source_output": "CPU 使用率 35%",
            }
        ],
        "report": (
            "SELECT secret FROM account\n`/data`\n{\"arguments\":{\"path\":\"/data\"}}\n"
            "{\"api_key\":\"plain-secret-value\"}\n"
            "C:\\private\\trace.log\nTraceback (most recent call last)"
        ),
        "statuses": [{"actual": "failed", "displayed": "ok"}],
    }
    assert set(evaluate_runtime_snapshot(bad)) == {
        "role_tool_boundary",
        "evidence_truthfulness",
        "public_safety",
        "false_success",
        "unmarked_mock",
    }


def test_负向评测器自动识别合法工具与错误结论类别() -> None:
    """server/check_cpu 虽属合法调用，但不得把 CPU 输出声明为磁盘耗尽。"""
    bad: RuntimeSnapshot = {
        "mode": "real",
        "role_tools": {"server": ["check_cpu"]},
        "evidence": [
            {
                "claim": "磁盘空间已耗尽",
                "source": "服务器工具",
                "source_role": "server",
                "source_tool": "check_cpu",
                "source_output": "CPU 使用率 35%",
            }
        ],
        "report": "服务器指标结论待复核",
        "statuses": [],
    }
    assert evaluate_runtime_snapshot(bad) == ["evidence_truthfulness"]
