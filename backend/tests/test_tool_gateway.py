"""ToolGateway 的六道关、脱敏和审计记录单元测试。"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator

import pytest

from src.core.tool_gateway import ToolGateway
from src.core.tool_registry import Tool, ToolExecutionResult, ToolRegistry


class EchoTool(Tool):
    """返回输入文本的最小测试工具。"""

    def __init__(self) -> None:
        super().__init__(
            name="echo",
            description="回显输入文本",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )

    def execute(self, text: str) -> str:
        """返回工具收到的文本。"""
        return text


class SensitiveTool(Tool):
    """返回包含敏感信息的最小测试工具。"""

    def __init__(self) -> None:
        super().__init__(
            name="sensitive",
            description="返回敏感信息以验证脱敏",
            parameters={"type": "object", "properties": {}},
        )

    def execute(self) -> str:
        """返回测试用敏感明文。"""
        return "password=hunter2 sk-abcdef123456 pg://user:pass@host"


class SlowTool(Tool):
    """执行一秒的最小测试工具。"""

    def __init__(self) -> None:
        super().__init__(
            name="slow",
            description="用于验证超时",
            parameters={"type": "object", "properties": {}},
        )

    def execute(self) -> str:
        """等待一秒后返回。"""
        time.sleep(1)
        return "慢工具完成"


class BoomTool(Tool):
    """抛出异常的最小测试工具。"""

    def __init__(self) -> None:
        super().__init__(
            name="boom",
            description="用于验证异常安全处理",
            parameters={"type": "object", "properties": {}},
        )

    def execute(self) -> str:
        """抛出带有唯一明文的异常。"""
        raise RuntimeError("内部异常明文-不要外泄")


class UnavailableTool(Tool):
    """返回结构化不可用状态的最小测试工具。"""

    def __init__(self) -> None:
        super().__init__(name="unavailable", description="不可用", parameters={"type": "object", "properties": {}})

    def execute(self) -> ToolExecutionResult:
        return ToolExecutionResult(
            status="unavailable",
            output="指标采集暂不可用",
            summary="服务器指标采集不可用",
        )


@pytest.fixture
def registry() -> ToolRegistry:
    """构造只包含本测试桩工具的注册中心。"""
    value = ToolRegistry()
    value.register(EchoTool())
    value.register(SensitiveTool())
    value.register(SlowTool())
    value.register(BoomTool())
    value.register(UnavailableTool())
    return value


@pytest.fixture
def gateway(registry: ToolRegistry) -> Iterator[ToolGateway]:
    """构造网关并在测试结束后释放线程池。"""
    value = ToolGateway(registry)
    try:
        yield value
    finally:
        value.shutdown()


def test_invoke_unregistered_tool_is_rejected(gateway: ToolGateway) -> None:
    """调用未注册工具时应拒绝请求。"""
    result = gateway.invoke("not-registered", "{}")

    assert result.record.status == "rejected"


def test_invoke_missing_required_argument_is_rejected(gateway: ToolGateway) -> None:
    """缺少工具声明的必填参数时应拒绝请求。"""
    result = gateway.invoke("echo", "{}")

    assert result.record.status == "rejected"


def test_invoke_invalid_json_is_rejected(gateway: ToolGateway) -> None:
    """参数不是合法 JSON 字符串时应拒绝请求。"""
    result = gateway.invoke("echo", "{bad")

    assert result.record.status == "rejected"


def test_invoke_non_object_json_is_rejected(gateway: ToolGateway) -> None:
    """参数 JSON 不是对象时应拒绝请求。"""
    result = gateway.invoke("echo", "[]")

    assert result.record.status == "rejected"


def test_invoke_argument_type_error_is_rejected(gateway: ToolGateway) -> None:
    """参数类型不符合 JSON Schema 时应拒绝请求。"""
    result = gateway.invoke("echo", json.dumps({"text": 123}))

    assert result.record.status == "rejected"


def test_invoke_success_returns_real_tool_output(gateway: ToolGateway) -> None:
    """参数校验通过且工具正常执行时应返回真实工具内容。"""
    result = gateway.invoke("echo", json.dumps({"text": "真实返回内容"}))

    assert result.record.status == "ok"
    assert "真实返回内容" in result.output


def test_invoke_structured_unavailable_is_not_marked_ok(gateway: ToolGateway) -> None:
    """工具显式降级时 unavailable 状态应穿过网关，不得伪装成功。"""
    result = gateway.invoke("unavailable", "{}")
    assert result.record.status == "unavailable"
    assert result.output == "指标采集暂不可用"
    assert result.record.detail == "服务器指标采集不可用"


def test_invoke_desensitizes_sensitive_tool_output(gateway: ToolGateway) -> None:
    """工具输出中的密码、密钥和连接串凭据都不得泄露。"""
    result = gateway.invoke("sensitive", "{}")

    assert result.record.status == "ok"
    assert "password=hunter2" not in result.output
    assert "sk-abcdef123456" not in result.output
    assert "pg://user:pass@host" not in result.output
    assert "[已脱敏" in result.output


def test_invoke_timeout_returns_timeout_status(registry: ToolRegistry) -> None:
    """工具执行超过限时时间时应返回 timeout 状态。"""
    gateway = ToolGateway(registry, timeout_seconds=0.2)
    try:
        result = gateway.invoke("slow", "{}")
    finally:
        gateway.shutdown()

    assert result.record.status == "timeout"


def test_invoke_tool_exception_is_safe(registry: ToolRegistry) -> None:
    """工具内部异常应返回安全错误且不得泄露异常原文。"""
    gateway = ToolGateway(registry)
    try:
        result = gateway.invoke("boom", "{}")
    finally:
        gateway.shutdown()

    assert result.record.status == "error"
    assert "内部异常明文-不要外泄" not in result.output
    assert "内部异常明文-不要外泄" not in result.record.detail
    assert "Traceback" not in result.output
    assert "Traceback" not in result.record.detail


def test_invoke_success_record_is_complete_and_sanitized(gateway: ToolGateway) -> None:
    """成功调用的审计记录应包含工具名、非负耗时且不含敏感明文。"""
    result = gateway.invoke("sensitive", "{}")
    record = result.record

    assert record.status == "ok"
    assert record.duration_ms >= 0
    assert record.tool == "sensitive"
    for secret in ("password=hunter2", "sk-abcdef123456", "pg://user:pass@host"):
        assert secret not in record.detail
