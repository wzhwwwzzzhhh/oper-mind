"""P14 Agent 角色模型装配：运行时装配（纯单元，不走 HTTP）。"""

from __future__ import annotations


def test_build_coordinator把角色llm装配到对应agent() -> None:
    """role_llms 应把专属 LLM 装到对应 Agent，协调器仍用共享默认。"""
    from src.core.bootstrap import build_coordinator
    from src.core.llm import LLMClient

    base = LLMClient(api_key="mock", base_url="http://mock", model="mock")
    role_llm = LLMClient(api_key="sk-role-key-12345678", base_url="https://role.example.com/v1", model="role-model")

    coordinator = build_coordinator(base, role_llms={"db": role_llm})

    assert coordinator.llm is base
    assert coordinator.agents["db"].llm is role_llm
    assert coordinator.agents["server"].llm is base
    assert coordinator.agents["log"].llm is base
    assert coordinator.agents["knowledge"].llm is base


def test_build_coordinator缺省回退共享llm() -> None:
    """未注入 role_llms 时全部角色回退共享默认，保持单脑行为。"""
    from src.core.bootstrap import build_coordinator
    from src.core.llm import LLMClient

    base = LLMClient(api_key="mock", base_url="http://mock", model="mock")

    coordinator = build_coordinator(base)

    assert coordinator.llm is base
    for agent in coordinator.agents.values():
        assert agent.llm is base
