"""M4 实验条件测试 —— 验证 6 组编排开关与 trace 行为。"""

import pytest

from src.agents.report_agent import ReportAgent
from src.core.coordinator import CoordinatorAgent
from src.core.debate import DebateArena
from src.core.experiment import get_experiment_condition
from src.core.llm import LLMClient
from src.core.reflection import ReflectionEngine


class _StubAgent:
    """返回固定结论的领域 Agent，用于隔离编排条件。"""

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[str] = []

    def run(self, query: str) -> str:
        self.calls.append(query)
        return f"{self.name} 的诊断结论"

    def get_thinking(self) -> list[str]:
        return [f"{self.name} 已完成"]


def _coordinator(arm: str) -> tuple[CoordinatorAgent, dict[str, _StubAgent]]:
    """构造使用 mock LLM 的条件化 Coordinator。"""
    llm = LLMClient(api_key="mock", base_url="http://mock", model="mock")
    coordinator = CoordinatorAgent(
        llm=llm,
        debate=DebateArena(llm=llm),
        reflection=ReflectionEngine(llm=llm),
        report=ReportAgent(),
        experiment_condition=get_experiment_condition(arm),
    )
    agents = {name: _StubAgent(name) for name in ("db", "server", "log")}
    for name, agent in agents.items():
        coordinator.register_agent(name, agent)
    return coordinator, agents


def _trace_nodes(coordinator: CoordinatorAgent) -> list[str]:
    return [event["node"] for event in coordinator.get_trace()]


@pytest.mark.parametrize(
    "arm",
    ["single_agent", "full", "no_debate", "no_reflection", "force_chain", "force_parallel"],
)
def test_支持全部实验组(arm: str) -> None:
    assert get_experiment_condition(arm).arm == arm


def test_非法实验组报错() -> None:
    with pytest.raises(ValueError, match="不支持的实验组"):
        get_experiment_condition("unknown")


def test_single_agent_全面问题只调用一个主要领域_agent() -> None:
    coordinator, agents = _coordinator("single_agent")
    coordinator.route("明天大促，帮我全面体检一下系统整体健康度")

    nodes = _trace_nodes(coordinator)
    assert "direct" in nodes
    assert "chain" not in nodes
    assert "parallel" not in nodes
    assert "debate" not in nodes
    assert "report" in nodes
    assert "reflection" in nodes
    assert len(agents["db"].calls) == 1
    assert not agents["server"].calls
    assert not agents["log"].calls


def test_no_debate_冲突并行结论跳过辩论() -> None:
    coordinator, _ = _coordinator("no_debate")
    coordinator.route("明天大促，帮我全面体检一下系统整体健康度")

    nodes = _trace_nodes(coordinator)
    assert "parallel" in nodes
    assert "conflict_check" in nodes
    assert "debate" not in nodes
    assert "report" in nodes
    assert "reflection" in nodes


def test_no_reflection_报告后直接结束() -> None:
    coordinator, _ = _coordinator("no_reflection")
    coordinator.route("SELECT * FROM orders WHERE status = 'PENDING' 很慢")

    nodes = _trace_nodes(coordinator)
    assert "report" in nodes
    assert "reflection" not in nodes


def test_force_chain_只走链式协作() -> None:
    coordinator, _ = _coordinator("force_chain")
    coordinator.route("SELECT * FROM orders WHERE status = 'PENDING' 很慢")

    nodes = _trace_nodes(coordinator)
    assert "chain" in nodes
    assert "direct" not in nodes
    assert "parallel" not in nodes
    assert "debate" not in nodes


def test_force_parallel_冲突时仍触发辩论() -> None:
    coordinator, _ = _coordinator("force_parallel")
    coordinator.route("SELECT * FROM orders WHERE status = 'PENDING' 很慢")

    nodes = _trace_nodes(coordinator)
    assert "parallel" in nodes
    assert "conflict_check" in nodes
    assert "debate" in nodes
    assert "reflection" in nodes
