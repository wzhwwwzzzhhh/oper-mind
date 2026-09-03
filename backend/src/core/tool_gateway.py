"""工具网关 —— 大脑调用工具的唯一受控入口。

架构基石：模型永远拿不到裸能力。任何工具调用都必须经过本网关的六道关：
准入（必须已注册）→ 参数校验（对齐工具声明的 JSON Schema）→ 限时执行 →
执行 → 脱敏（凭据/敏感值绝不外流）→ 留痕（结构化审计记录）。

网关只做受控转发与留痕，不理解任何具体服务；具体读写由注册的 Tool 承担。
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import CancelledError, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.core.tool_registry import ToolExecutionResult, ToolRegistry

ToolInvocationStatus = Literal["ok", "unavailable", "rejected", "timeout", "error"]
ToolWaitStatus = Literal["not_waited", "completed", "timed_out"]
ToolAcceptanceStatus = Literal["not_applicable", "accepted", "closed"]
ToolUnderlyingExecutionStatus = Literal[
    "not_started",
    "completed",
    "cancelled_before_start",
    "stop_state_unknown",
]

# 脱敏规则：命中即整体替换为占位符，防止凭据/密钥流入结果、Trace、日志。
# 说明：这是"最后一道防线"，工具本身也不应把凭据放进返回值。
_REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # 形如 sk-xxxx 的密钥
    (re.compile(r"sk-[A-Za-z0-9_\-]{6,}"), "[已脱敏:密钥]"),
    # password=... / pwd: ... / token=...（到分隔符为止）
    (
        re.compile(r"(?i)\b(password|passwd|pwd|token|secret|api[_-]?key)\b\s*[=:]\s*\S+"),
        r"\1=[已脱敏]",
    ),
    # 连接串中的凭据段 scheme://user:pass@host
    (re.compile(r"://[^:/@\s]+:[^@/\s]+@"), "://[已脱敏]@"),
)


class ToolInvocation(BaseModel):
    """一次工具调用的结构化审计记录（跨层数据，前端 Trace 只看脱敏摘要）。

    禁止承载：CoT、Prompt、原始敏感数据、异常堆栈、凭据。
    """

    tool: str = Field(description="被调用的工具名")
    status: ToolInvocationStatus = Field(description="调用结果状态")
    started_at: str = Field(description="调用开始的 UTC ISO 8601 时间戳")
    duration_ms: int = Field(ge=0, description="调用耗时（毫秒）")
    detail: str = Field(description="脱敏后的简要说明，供前端 Trace 展示")
    wait_status: ToolWaitStatus = Field(
        default="not_waited",
        description="调用方等待是否完成或到期",
    )
    acceptance_status: ToolAcceptanceStatus = Field(
        default="not_applicable",
        description="本次调用是否仍接纳底层结果",
    )
    underlying_execution_status: ToolUnderlyingExecutionStatus = Field(
        default="not_started",
        description="仅表达 future 能证明的底层执行状态",
    )


class GatewayResult(BaseModel):
    """网关返回给大脑的结果：脱敏后的工具输出 + 本次调用的审计记录。"""

    output: str = Field(description="脱敏后的工具输出，可安全交给大脑与前端")
    record: ToolInvocation = Field(description="本次调用的结构化审计记录")


def desensitize(text: str) -> str:
    """对文本套用全部脱敏规则；凭据/密钥/连接串口令一律替换为占位符。"""
    cleaned = text
    for pattern, replacement in _REDACTION_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


def _validate_arguments(schema: dict[str, Any], args: dict[str, Any]) -> str | None:
    """按工具声明的 JSON Schema 做最小参数校验。

    仅校验本项目工具实际使用的子集：required 必填、properties 顶层类型。
    校验通过返回 None；否则返回中文错误说明。
    """
    required = schema.get("required", [])
    if isinstance(required, list):
        for key in required:
            if key not in args:
                return f"缺少必填参数：{key}"

    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return None

    # JSON Schema 类型 → Python 类型的最小映射
    type_map: dict[str, type | tuple[type, ...]] = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    for key, value in args.items():
        spec = properties.get(key)
        if not isinstance(spec, dict):
            continue
        expected = spec.get("type")
        py_type = type_map.get(expected) if isinstance(expected, str) else None
        if py_type is not None and not isinstance(value, py_type):
            return f"参数 {key} 类型应为 {expected}"
    return None


def _now_iso() -> str:
    """前端可排序的 UTC ISO 8601 时间戳。"""
    return datetime.now(UTC).isoformat()


class ToolGateway:
    """工具调用的唯一受控入口。

    大脑只把「工具名 + JSON 参数字符串」交给网关；网关完成六道关后，
    返回脱敏输出与结构化审计记录。网关不感知具体服务语义。
    """

    def __init__(self, registry: ToolRegistry, timeout_seconds: float = 3.0) -> None:
        self._registry = registry
        self._timeout_seconds = timeout_seconds
        # 复用单线程池承载限时执行；工具执行为同步阻塞，交由 future 计时。
        self._executor = ThreadPoolExecutor(max_workers=1)

    def invoke(self, name: str, arguments: str) -> GatewayResult:
        """执行一次受控工具调用，返回脱敏输出 + 审计记录（永不抛出）。"""
        started_at = _now_iso()
        start = time.monotonic()

        def _finish(
            status: ToolInvocationStatus,
            output: str,
            detail: str,
            *,
            wait_status: ToolWaitStatus = "not_waited",
            acceptance_status: ToolAcceptanceStatus = "not_applicable",
            underlying_execution_status: ToolUnderlyingExecutionStatus = "not_started",
        ) -> GatewayResult:
            duration_ms = int((time.monotonic() - start) * 1000)
            safe_output = desensitize(output)
            record = ToolInvocation(
                tool=name,
                status=status,
                started_at=started_at,
                duration_ms=duration_ms,
                detail=desensitize(detail),
                wait_status=wait_status,
                acceptance_status=acceptance_status,
                underlying_execution_status=underlying_execution_status,
            )
            return GatewayResult(output=safe_output, record=record)

        # 关 1：准入——工具必须已显式注册
        tool = self._registry.get(name)
        if tool is None:
            msg = f"工具 {name} 未注册，已拒绝"
            return _finish("rejected", json.dumps({"error": msg}, ensure_ascii=False), msg)

        # 关 2：参数——必须是合法 JSON 且满足工具声明的 Schema
        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            msg = "参数必须是有效的 JSON，已拒绝"
            return _finish("rejected", json.dumps({"error": msg}, ensure_ascii=False), msg)
        if not isinstance(args, dict):
            msg = "参数必须是 JSON 对象，已拒绝"
            return _finish("rejected", json.dumps({"error": msg}, ensure_ascii=False), msg)
        schema_error = _validate_arguments(tool.parameters, args)
        if schema_error is not None:
            msg = f"参数校验失败：{schema_error}"
            return _finish("rejected", json.dumps({"error": msg}, ensure_ascii=False), msg)

        # 关 3 + 4：限时 + 执行
        def _execute_tool() -> tuple[Literal["ok", "type_error", "error"], object | None]:
            """在 worker 内封闭 Tool 异常，避免与 Gateway 等待超时混淆。"""

            try:
                return "ok", tool.execute(**args)
            except TypeError:
                return "type_error", None
            except Exception:
                return "error", None

        try:
            future = self._executor.submit(_execute_tool)
        except Exception:
            msg = "工具执行异常"
            return _finish("error", json.dumps({"error": msg}, ensure_ascii=False), msg)

        try:
            outcome, raw_result = future.result(timeout=self._timeout_seconds)
        except FutureTimeoutError:
            cancelled_before_start = future.cancel()
            if cancelled_before_start:
                msg = f"工具等待超过 {self._timeout_seconds:g}s，结果接纳已关闭；排队执行已取消"
                underlying_status: ToolUnderlyingExecutionStatus = "cancelled_before_start"
            else:
                msg = f"工具等待超过 {self._timeout_seconds:g}s，结果接纳已关闭；底层停止状态未知"
                underlying_status = "stop_state_unknown"
            return _finish(
                "timeout",
                json.dumps({"error": msg}, ensure_ascii=False),
                msg,
                wait_status="timed_out",
                acceptance_status="closed",
                underlying_execution_status=underlying_status,
            )
        except CancelledError:
            msg = "工具排队执行已取消，结果接纳已关闭"
            return _finish(
                "error",
                json.dumps({"error": msg}, ensure_ascii=False),
                msg,
                wait_status="completed",
                acceptance_status="closed",
                underlying_execution_status="cancelled_before_start",
            )
        except Exception:
            # future 协议本身异常也只给出中性说明。
            msg = "工具执行异常"
            return _finish(
                "error",
                json.dumps({"error": msg}, ensure_ascii=False),
                msg,
                wait_status="completed",
                acceptance_status="accepted",
                underlying_execution_status="completed",
            )

        if outcome == "type_error":
            msg = "工具参数不匹配"
            return _finish(
                "error",
                json.dumps({"error": msg}, ensure_ascii=False),
                msg,
                wait_status="completed",
                acceptance_status="accepted",
                underlying_execution_status="completed",
            )
        if outcome == "error":
            msg = "工具执行异常"
            return _finish(
                "error",
                json.dumps({"error": msg}, ensure_ascii=False),
                msg,
                wait_status="completed",
                acceptance_status="accepted",
                underlying_execution_status="completed",
            )

        # 关 5 + 6：脱敏 + 留痕（在 _finish 内统一完成）
        # detail 支持工具可选脱敏审计摘要：工具定义 audit_summary() 则用之，
        # 否则维持中性文案；对既有工具零影响、向后兼容。摘要同样过脱敏兜底。
        if isinstance(raw_result, ToolExecutionResult):
            return _finish(
                raw_result.status,
                raw_result.output,
                raw_result.summary,
                wait_status="completed",
                acceptance_status="accepted",
                underlying_execution_status="completed",
            )

        output = str(raw_result)
        detail = f"调用 {name} 成功"
        audit_summary = getattr(tool, "audit_summary", None)
        if callable(audit_summary):
            try:
                detail = str(audit_summary())
            except Exception:
                detail = f"调用 {name} 成功"
        try:
            execution_status = tool.execution_status()
        except Exception:
            msg = "工具执行状态不可用"
            return _finish(
                "error",
                json.dumps({"error": msg}, ensure_ascii=False),
                msg,
                wait_status="completed",
                acceptance_status="accepted",
                underlying_execution_status="completed",
            )
        return _finish(
            execution_status,
            output,
            detail,
            wait_status="completed",
            acceptance_status="accepted",
            underlying_execution_status="completed",
        )

    def shutdown(self) -> None:
        """释放内部线程池。"""
        self._executor.shutdown(wait=False, cancel_futures=True)
