"""评测记忆隔离测试 —— 评测样例不能读取或写入长期记忆。"""

from src.core import bootstrap


def test_build_system_评测模式关闭所有领域_agent长期记忆(monkeypatch) -> None:
    """评测装配必须让三个领域 Agent 都不加载或持久化长期记忆。"""
    monkeypatch.setattr(
        bootstrap,
        "load_config",
        lambda: {
            "llm": {
                "api_key": "mock",
                "base_url": "https://example.invalid/v1",
                "model": "mock-model",
            }
        },
    )

    coordinator = bootstrap.build_system(enable_long_term_memory=False)

    assert set(coordinator.agents) == {"db", "server", "log"}
    assert all(agent.long_term is None for agent in coordinator.agents.values())
