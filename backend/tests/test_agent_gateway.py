"""验证 BaseAgent 的工具调用统一经过 ToolGateway。"""

from __future__ import annotations

from copy import deepcopy

from src.core.agent import BaseAgent
from src.core.tool_registry import Tool, ToolRegistry


class EchoTool(Tool):
    """返回输入文本的最小测试工具。"""

    def __init__(self) -> None:
        super().__init__(
            name="echo",
            description="回显文本",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )

    def execute(self, text: str) -> str:
        """返回传入文本。"""
        return text


class SensitiveTool(Tool):
    """返回敏感明文的最小测试工具。"""

    def __init__(self) -> None:
        super().__init__(
            name="sensitive",
            description="返回敏感文本",
            parameters={"type": "object", "properties": {}},
        )

    def execute(self) -> str:
        """返回测试用敏感串。"""
        return "password=hunter2 sk-abcdef123456 pg://user:pass@host"


class FakeLLM:
    """按两次调用一轮 ReAct 流程返回工具调用和最终答案。"""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        self.call_count = 0
        self.received_messages: list[list[dict]] = []

    def chat(self, messages: list[dict], tools: list[dict] | None = None, **kwargs: object) -> dict:
        """第一次请求工具，第二次返回最终答案，并保存收到的消息。"""
        del tools, kwargs
        self.call_count += 1
        if self.call_count % 2 == 1:
            arguments = '{"text":"桩工具返回内容"}' if self.tool_name == "echo" else "{}"
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call_{self.call_count}",
                        "type": "function",
                        "function": {"name": self.tool_name, "arguments": arguments},
                    }
                ],
            }

        self.received_messages.append(deepcopy(messages))
        return {"role": "assistant", "content": "最终诊断结论"}


class NoToolFakeLLM:
    """始终直接返回最终答案的假 LLM。"""

    def chat(self, messages: list[dict], tools: list[dict] | None = None, **kwargs: object) -> dict:
        """返回不带工具调用的最终答案。"""
        del messages, tools, kwargs
        return {"role": "assistant", "content": "无需工具的最终答复"}


def _registry(*tools: Tool) -> ToolRegistry:
    """注册测试工具并返回工具注册中心。"""
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def test_agent_collects_gateway_tool_invocation() -> None:
    """正常工具调用结束后应收集网关产生的审计记录。"""
    tool = EchoTool()
    agent = BaseAgent(
        llm=FakeLLM(tool.name),
        tools=_registry(tool),
        system_prompt="测试系统提示",
        enable_long_term_memory=False,
    )

    answer = agent.run("请回显文本")
    records = agent.get_tool_invocations()

    assert answer == "最终诊断结论"
    assert len(records) >= 1
    assert any(record.tool == tool.name and record.status == "ok" for record in records)


def test_agent_feeds_desensitized_tool_result_to_llm() -> None:
    """喂回假 LLM 的工具结果应已脱敏且不含敏感明文。"""
    tool = SensitiveTool()
    llm = FakeLLM(tool.name)
    agent = BaseAgent(
        llm=llm,
        tools=_registry(tool),
        system_prompt="测试系统提示",
        enable_long_term_memory=False,
    )

    agent.run("请读取敏感工具结果")
    messages_text = repr(llm.received_messages)

    assert "password=hunter2" not in messages_text
    assert "sk-abcdef123456" not in messages_text
    assert "pg://user:pass@host" not in messages_text
    assert "[已脱敏" in messages_text


def test_agent_clears_tool_invocations_before_each_run() -> None:
    """连续运行时第二次记录应从空列表重新收集而不累加第一次记录。"""
    tool = EchoTool()
    agent = BaseAgent(
        llm=FakeLLM(tool.name),
        tools=_registry(tool),
        system_prompt="测试系统提示",
        enable_long_term_memory=False,
    )

    agent.run("第一次调用")
    first_records = agent.get_tool_invocations()
    agent.run("第二次调用")
    second_records = agent.get_tool_invocations()

    assert len(first_records) == 1
    assert len(second_records) == 1
    assert second_records is not first_records
    assert second_records[0].tool == tool.name
    assert second_records[0].status == "ok"


def test_agent_without_tool_calls_returns_answer_without_records() -> None:
    """没有工具调用的运行应正常返回最终答复且不产生审计记录。"""
    agent = BaseAgent(
        llm=NoToolFakeLLM(),
        tools=_registry(EchoTool()),
        system_prompt="测试系统提示",
        enable_long_term_memory=False,
    )

    answer = agent.run("直接回答")

    assert answer == "无需工具的最终答复"
    assert agent.get_tool_invocations() == []
