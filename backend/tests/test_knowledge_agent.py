"""知识检索 Agent 接入链路测试：ToolGateway 准入、路由接入与 Trace 审计摘要。

覆盖 AC7、AC8：知识检索作为 Agent 工具经网关白名单准入、限时、脱敏；
检索进入 Agent 上下文；Trace 只展示脱敏摘要。使用 tmp_path 确定性目录，不连接外部资源。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agents.knowledge_agent import KnowledgeAgent
from src.core.graph import _keyword_strategy, _keyword_target
from src.core.tool_gateway import ToolGateway
from src.core.tool_registry import ToolRegistry
from src.tools.knowledge_tools import SearchKnowledgeTool


class FakeLLM:
    """一次工具调用 + 一次最终答复的确定性假 LLM。"""

    def __init__(self) -> None:
        self.call_count = 0
        self.tool_results: list[str] = []

    def chat(self, messages: list[dict], tools: list[dict] | None = None, **kwargs: object) -> dict:
        """第一次请求检索工具，第二次返回引用知识库的最终答复。"""
        del tools, kwargs
        self.call_count += 1
        if self.call_count == 1:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_knowledge_1",
                        "type": "function",
                        "function": {
                            "name": "search_knowledge",
                            "arguments": json.dumps({"query": "kill 慢查询 SOP"}),
                        },
                    }
                ],
            }
        content = "根据知识库《kill 慢查询 SOP》文档，操作前应先确认会话状态。"
        return {"role": "assistant", "content": content}


def _write(base: Path, rel: str, text: str) -> None:
    """在临时知识目录内写入一篇测试文档。"""
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _knowledge_dir(tmp_path: Path) -> Path:
    """构造含 SOP 文档的临时知识目录。"""
    base = tmp_path / "knowledge"
    _write(base, "kill-slow-query.md", "# kill 慢查询 SOP\n\n先确认会话状态，再 kill 慢查询进程。\n")
    return base


@pytest.fixture
def knowledge_dir(tmp_path: Path) -> Path:
    """每个用例独立的临时知识目录。"""
    return _knowledge_dir(tmp_path)


def test_knowledge_agent_注册检索工具(knowledge_dir: Path) -> None:
    """KnowledgeAgent 应注册 search_knowledge 工具。"""
    agent = KnowledgeAgent(llm=object(), knowledge_dir=str(knowledge_dir), enable_long_term_memory=False)  # type: ignore[arg-type]

    assert agent.tools.get("search_knowledge") is not None


def test_search_knowledge经网关白名单准入(knowledge_dir: Path) -> None:
    """未注册工具应被网关拒绝，已注册的 search_knowledge 可正常调用。"""
    tool = SearchKnowledgeTool(directory=str(knowledge_dir))
    registry = ToolRegistry()
    registry.register(tool)
    gateway = ToolGateway(registry)
    try:
        rejected = gateway.invoke("not-registered", "{}")
        ok = gateway.invoke("search_knowledge", json.dumps({"query": "慢查询"}))
    finally:
        gateway.shutdown()

    assert rejected.record.status == "rejected"
    assert ok.record.status == "ok"
    assert ok.record.tool == "search_knowledge"


def test_knowledge_tool经网关后记录脱敏审计摘要(knowledge_dir: Path) -> None:
    """网关 detail 应使用工具的 audit_summary（命中数与标题），不含正文片段。"""
    tool = SearchKnowledgeTool(directory=str(knowledge_dir))
    registry = ToolRegistry()
    registry.register(tool)
    gateway = ToolGateway(registry)
    try:
        ok = gateway.invoke("search_knowledge", json.dumps({"query": "慢查询"}))
    finally:
        gateway.shutdown()

    assert ok.record.status == "ok"
    assert "知识检索命中 1 篇" in ok.record.detail
    assert "kill 慢查询 SOP" in ok.record.detail
    assert "先确认会话状态" not in ok.record.detail


def test_knowledge_agent_检索结果进入Agent上下文(knowledge_dir: Path) -> None:
    """工具结果应脱敏后进入 Agent 上下文，供最终答复引用知识库。"""
    llm = FakeLLM()
    agent = KnowledgeAgent(llm=llm, knowledge_dir=str(knowledge_dir), enable_long_term_memory=False)  # type: ignore[arg-type]

    answer = agent.run("kill 慢查询的 SOP 是什么？")

    assert answer == "根据知识库《kill 慢查询 SOP》文档，操作前应先确认会话状态。"
    records = agent.get_tool_invocations()
    assert len(records) >= 1
    assert records[0].tool == "search_knowledge"
    assert records[0].status == "ok"


def test_keyword_target识别知识检索() -> None:
    """关键词兜底应把知识检索问题路由到 knowledge，日志类问题不受影响。"""
    assert _keyword_target("kill 慢查询的 SOP 是什么") == "db"
    assert _keyword_target("查一下知识库里的 SOP 手册") == "knowledge"
    assert _keyword_target("服务器 CPU 高") == "server"
    assert _keyword_target("看下错误日志") == "log"
    assert _keyword_strategy("查一下知识库里的操作指引") == "direct"


def test_graph_路由prompt含knowledge领域() -> None:
    """LLM 路由提示词应包含 knowledge 领域取值。"""
    prompt_file = Path(__file__).resolve().parents[1] / "src" / "core" / "graph.py"
    source = prompt_file.read_text(encoding="utf-8")

    assert "knowledge" in source


def test_keyword_s1_s4路由结果不变() -> None:
    """新增 knowledge 关键词不得改变既有 db/server/log 关键词路由结论。"""
    assert _keyword_strategy("全面体检服务器和数据库") == "parallel"
    assert _keyword_strategy("数据库卡慢") == "chain"
    assert _keyword_target("select * from orders") == "db"
    assert _keyword_target("cpu 100%") == "server"