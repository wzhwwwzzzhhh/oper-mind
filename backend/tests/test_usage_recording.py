"""P8 用量采集测试：真实调用落库、mock 不采集、采集失败不阻断调用。"""

from __future__ import annotations

from types import SimpleNamespace

from src.core.llm import LLMClient
from src.domain.model_usage import UsageRecord
from src.infrastructure.persistence.database import create_persistence_runtime
from src.infrastructure.persistence.model_usage_repository import (
    SqlAlchemyModelUsageReader,
    SqlAlchemyUsageRecorder,
)

REAL_KEY = "test-key-1234567890abcdef"


class _FakeUsage:
    """模拟 OpenAI usage 对象（prompt/completion/total）。"""

    def __init__(self, prompt: int, completion: int, total: int) -> None:
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.total_tokens = total


class _FakeResponse:
    """模拟带 usage 的 OpenAI 完成响应。"""

    def __init__(self, usage: object | None = None) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))]
        self.usage = usage


class _CapturingRecorder:
    """内存记录器：捕获 UsageRecord 供断言（不落库）。"""

    def __init__(self) -> None:
        self.records: list[UsageRecord] = []

    def record(self, record: UsageRecord) -> None:
        self.records.append(record)


def _make_llm_with_recorder(recorder: _CapturingRecorder) -> LLMClient:
    """构造注入记录器的真实模式 LLM 客户端。"""
    llm = LLMClient(
        api_key=REAL_KEY,
        base_url="http://test.example/v1",
        model="test-model",
        usage_recorder=recorder,
    )

    def fake_create(**call_kwargs):
        return _FakeResponse(
            usage=_FakeUsage(prompt=10, completion=5, total=15),
        )

    llm.client.chat.completions.create = fake_create  # type: ignore[assignment]
    return llm


def test_真实调用后usage落库() -> None:
    """AC1: 真实调用完成时把 input/output/total + 模型名 + 时间戳交给记录器。"""
    recorder = _CapturingRecorder()
    llm = _make_llm_with_recorder(recorder)
    llm.chat([{"role": "user", "content": "hi"}])
    assert len(recorder.records) == 1
    record = recorder.records[0]
    assert record["model"] == "test-model"
    # OpenAI usage 字段映射：prompt→input、completion→output、total→total
    assert record["input_tokens"] == 10
    assert record["output_tokens"] == 5
    assert record["total_tokens"] == 15
    assert record["occurred_at"].tzinfo is not None


def test_usage缺失时不采集() -> None:
    """响应无 usage 时跳过采集（不产生记录、不报错）。"""
    recorder = _CapturingRecorder()
    llm = LLMClient(api_key=REAL_KEY, base_url="http://test.example/v1", model="test-model", usage_recorder=recorder)

    def fake_create(**call_kwargs):
        return _FakeResponse(usage=None)

    llm.client.chat.completions.create = fake_create  # type: ignore[assignment]
    result = llm.chat([{"role": "user", "content": "hi"}])
    assert result["role"] == "assistant"
    assert recorder.records == []


def test_mock调用不采集() -> None:
    """AC5: mock 模式 chat 不采集用量（恒 0）。"""
    recorder = _CapturingRecorder()
    llm = LLMClient(api_key="mock", base_url="http://mock", model="mock", usage_recorder=recorder)
    result = llm.chat([{"role": "user", "content": "你好"}])
    assert "模拟场景" in result["content"]
    assert recorder.records == []


def test_采集失败不影响调用() -> None:
    """AC8: 记录器抛异常时调用仍正常返回。"""

    class _BrokenRecorder:
        def record(self, _record: UsageRecord) -> None:
            raise RuntimeError("应用库不可用")

    llm = LLMClient(api_key=REAL_KEY, base_url="http://test.example/v1", model="test-model", usage_recorder=_BrokenRecorder())

    def fake_create(**call_kwargs):
        return _FakeResponse(usage=_FakeUsage(prompt=1, completion=1, total=2))

    llm.client.chat.completions.create = fake_create  # type: ignore[assignment]
    result = llm.chat([{"role": "user", "content": "hi"}])
    assert result["role"] == "assistant"
    assert result["content"] == "ok"


def test_未注入记录器时行为不变() -> None:
    """recorder 默认 None：既有构造与调用语义不变（无采集）。"""
    llm = LLMClient(api_key=REAL_KEY, base_url="http://test.example/v1", model="test-model")

    def fake_create(**call_kwargs):
        return _FakeResponse(usage=_FakeUsage(prompt=1, completion=1, total=2))

    llm.client.chat.completions.create = fake_create  # type: ignore[assignment]
    result = llm.chat([{"role": "user", "content": "hi"}])
    assert result["role"] == "assistant"


def test_recorder真实落库与聚合查询(tmp_path) -> None:
    """SqlAlchemyUsageRecorder 落库后，聚合查询可按模型/时间窗取回。"""
    from pathlib import Path

    database_path = Path(tmp_path) / "usage.sqlite3"
    runtime = create_persistence_runtime(f"sqlite:///{database_path.as_posix()}")
    from src.infrastructure.persistence.database import Base

    Base.metadata.create_all(runtime.engine)
    try:
        recorder = SqlAlchemyUsageRecorder(runtime.session_factory)
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        recorder.record(
            {
                "model": "deepseek-chat",
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150,
                "occurred_at": now - timedelta(days=1),
            }
        )
        recorder.record(
            {
                "model": "deepseek-chat",
                "input_tokens": 200,
                "output_tokens": 100,
                "total_tokens": 300,
                "occurred_at": now,
            }
        )
        recorder.record(
            {
                "model": "gpt-4o-mini",
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "occurred_at": now,
            }
        )

        reader = SqlAlchemyModelUsageReader(runtime.session_factory)
        rows = reader.stats()
        by_model = {row["model"]: row for row in rows}
        assert by_model["deepseek-chat"]["input_tokens"] == 300
        assert by_model["deepseek-chat"]["output_tokens"] == 150
        assert by_model["deepseek-chat"]["total_tokens"] == 450
        assert by_model["gpt-4o-mini"]["total_tokens"] == 15

        # 时间窗过滤：只取今天
        today_rows = reader.stats(
            from_at=now - timedelta(hours=1),
            to_at=now + timedelta(minutes=1),
        )
        today_by_model = {row["model"]: row for row in today_rows}
        assert today_by_model["deepseek-chat"]["total_tokens"] == 300
        assert "gpt-4o-mini" in today_by_model

        # 模型过滤
        filtered = reader.stats(model="gpt-4o-mini")
        assert len(filtered) == 1
        assert filtered[0]["model"] == "gpt-4o-mini"

        # 无匹配记录返回空列表
        empty = reader.stats(model="不存在的模型")
        assert empty == []
    finally:
        runtime.engine.dispose()
