"""P8 模型运行参数进入 LLM 调用链测试（不触发真实 API）。"""

from __future__ import annotations

from types import SimpleNamespace

from src.core.llm import LLMClient

REAL_KEY = "test-key-1234567890abcdef"


class _FakeResponse:
    """模拟 OpenAI 完成响应。"""

    def __init__(self, content: str = "ok") -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=None))]
        self.usage = None


def _make_llm(**kwargs) -> tuple[LLMClient, dict]:
    """构造 LLM 客户端并捕获真实路径的 SDK kwargs。"""
    llm = LLMClient(api_key=REAL_KEY, base_url="http://test.example/v1", model="test-model", **kwargs)
    captured: dict = {}

    def fake_create(**call_kwargs):
        captured.update(call_kwargs)
        return _FakeResponse()

    llm.client.chat.completions.create = fake_create  # type: ignore[assignment]
    return llm, captured


def test_未配置参数时使用默认temperature() -> None:
    """AC2: 未配置参数时 chat 应传后端默认 temperature=0.0。"""
    llm, captured = _make_llm()
    llm.chat([{"role": "user", "content": "hi"}])
    assert captured["temperature"] == 0.0


def test_构造默认temperature进入调用链() -> None:
    """AC1: 配置 temperature=0.5 后 chat 应传 0.5（真进调用链）。"""
    llm, captured = _make_llm(default_temperature=0.5)
    llm.chat([{"role": "user", "content": "hi"}])
    assert captured["temperature"] == 0.5


def test_显式传参覆盖实例默认() -> None:
    """既有显式传参调用点（graph/debate 传 0.0）行为不变。"""
    llm, captured = _make_llm(default_temperature=0.5)
    llm.chat([{"role": "user", "content": "hi"}], temperature=0.0)
    assert captured["temperature"] == 0.0


def test_未配置max_tokens不传SDK() -> None:
    """AC2: max_tokens 未配置时不传 SDK（用模型默认）。"""
    llm, captured = _make_llm()
    llm.chat([{"role": "user", "content": "hi"}])
    assert "max_tokens" not in captured


def test_构造默认max_tokens进入调用链() -> None:
    """配置 max_tokens 后 chat 应传该值。"""
    llm, captured = _make_llm(default_max_tokens=4096)
    llm.chat([{"role": "user", "content": "hi"}])
    assert captured["max_tokens"] == 4096


def test_显式max_tokens覆盖实例默认() -> None:
    """显式传 max_tokens 时以显式值为准。"""
    llm, captured = _make_llm(default_max_tokens=4096)
    llm.chat([{"role": "user", "content": "hi"}], max_tokens=100)
    assert captured["max_tokens"] == 100


def test_mock路径不读参数() -> None:
    """AC8: mock 模式 chat 不读参数，返回确定性内容。"""
    llm = LLMClient(
        api_key="mock",
        base_url="http://mock",
        model="mock",
        default_temperature=0.9,
        default_max_tokens=99,
    )
    result = llm.chat([{"role": "user", "content": "你好"}])
    assert result["role"] == "assistant"
    assert "模拟场景" in result["content"]
    assert "当前结论未知" in result["content"]


def test_tools调用仍带工具参数且temperature生效() -> None:
    """工具调用路径参数与既有工具语义并存。"""
    llm, captured = _make_llm(default_temperature=0.5)
    llm.chat(
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "sample", "arguments": "{}"}}],
    )
    assert captured["tools"] is not None
    assert captured["tool_choice"] == "auto"
    assert captured["temperature"] == 0.5
