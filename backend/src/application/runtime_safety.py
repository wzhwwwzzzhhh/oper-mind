"""P11 Runtime 输出协议保护：只校验信号，不拥有 Run 业务事实。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import TypeVar

from src.application.contracts import (
    DiagnosisExecutionError,
    DiagnosisExecutionEvent,
    DiagnosisExecutionResult,
)
from src.application.run_execution import (
    RunDiagnosisResultSignal,
    RunEventSignal,
    RunExecutionError,
    RunFailureCode,
    RunFailureSignal,
    RunMainDeliverySignal,
    safe_failure_signal,
)
from src.application.runtime_contracts import (
    RuntimeEventSignal,
    RuntimeFailureSignal,
    RuntimeResultSignal,
    RuntimeSignal,
)
from src.domain.harness_contracts import (
    CONTRACT_VERSION_V1,
    FailureCodeId,
    FailureCodeValue,
)

_SAFE_FAILURE_MESSAGES: dict[FailureCodeId, str] = {
    FailureCodeId.VALIDATION_INVALID_REQUEST: "诊断请求无效",
    FailureCodeId.RUNTIME_UNEXPECTED_EXCEPTION: "诊断运行发生异常",
    FailureCodeId.RUNTIME_UNSUPPORTED_CAPABILITY: "诊断运行能力不受支持",
    FailureCodeId.MODEL_EXECUTION_FAILED: "诊断执行失败，请稍后重试",
    FailureCodeId.TOOL_REJECTED: "诊断工具调用被拒绝",
    FailureCodeId.TOOL_TIMEOUT: "诊断工具等待超时",
    FailureCodeId.POLICY_DENIED: "诊断请求未通过策略检查",
    FailureCodeId.APPROVAL_REQUIRED: "诊断操作需要人工审批",
    FailureCodeId.BUDGET_EXCEEDED: "诊断运行预算已用尽",
    FailureCodeId.CANCEL_REQUESTED: "诊断执行已取消",
    FailureCodeId.RECOVERY_REQUIRED: "诊断运行需要人工恢复",
    FailureCodeId.PERSISTENCE_CONFLICT: "诊断状态发生冲突",
    FailureCodeId.INTERNAL_INVARIANT_VIOLATION: "诊断运行输出协议异常",
}

_SignalT = TypeVar("_SignalT")


class _ProtocolViolation(Exception):
    """内部专用：未知对象或终止后输出。"""


def _failure(code: FailureCodeId) -> RuntimeFailureSignal:
    """只从封闭 code 重建固定文案，永不复用上游异常或 message。"""

    return RuntimeFailureSignal(
        contract_version=CONTRACT_VERSION_V1,
        code=FailureCodeValue(
            contract_version=CONTRACT_VERSION_V1,
            code=code,
            namespace=code.namespace,
        ),
        message=_SAFE_FAILURE_MESSAGES[code],
    )


def _safe_runtime_failure(signal: RuntimeFailureSignal) -> RuntimeFailureSignal:
    """保留已校验的封闭 failure code，但重新生成安全文案。"""

    return _failure(signal.code.code)


def _guard_finite_stream(
    stream_factory: Callable[[], Iterator[object]],
    classify: Callable[[object], tuple[_SignalT, bool]],
    protocol_failure: Callable[[], _SignalT],
    exception_failure: Callable[[Exception, bool], _SignalT],
) -> Iterator[_SignalT]:
    """共用有限流内核：正常 EOF 后只接纳唯一终止 signal。

    协议失败不等待不受信任的 iterator cleanup；无限流与阻塞迭代仍诚实保留为
    deadline gap。``classify`` 返回 ``(signal, is_terminal)``；未知对象应抛出
    ``_ProtocolViolation``。
    """

    try:
        iterator = iter(stream_factory())
    except Exception as error:
        yield exception_failure(error, False)
        return

    terminal: _SignalT | None = None
    while True:
        try:
            item = next(iterator)
        except StopIteration:
            if terminal is None:
                yield protocol_failure()
            else:
                yield terminal
            return
        except Exception as error:
            yield exception_failure(error, terminal is not None)
            return

        if terminal is not None:
            yield protocol_failure()
            return

        try:
            signal, is_terminal = classify(item)
        except _ProtocolViolation:
            yield protocol_failure()
            return
        except Exception as error:
            yield exception_failure(error, False)
            return

        if is_terminal:
            terminal = signal
            continue
        yield signal


def _classify_runtime_item(
    item: object,
) -> tuple[RuntimeEventSignal | RuntimeResultSignal | RuntimeFailureSignal, bool]:
    """把 legacy 执行器对象收敛为 P10 信号。"""
    if isinstance(item, DiagnosisExecutionEvent):
        return RuntimeEventSignal(contract_version=CONTRACT_VERSION_V1, event=item), False
    if isinstance(item, DiagnosisExecutionResult):
        return RuntimeResultSignal(contract_version=CONTRACT_VERSION_V1, result=item), True
    if isinstance(item, RuntimeFailureSignal):
        return _safe_runtime_failure(item), True
    raise _ProtocolViolation


def _runtime_exception_failure(
    error: Exception,
    after_terminal: bool,
) -> RuntimeEventSignal | RuntimeResultSignal | RuntimeFailureSignal:
    """保留 P11 既有异常映射。"""
    if isinstance(error, DiagnosisExecutionError):
        return _failure(
            FailureCodeId.INTERNAL_INVARIANT_VIOLATION
            if after_terminal
            else FailureCodeId.MODEL_EXECUTION_FAILED
        )
    return _failure(FailureCodeId.RUNTIME_UNEXPECTED_EXCEPTION)


def guard_runtime_stream(
    stream_factory: Callable[[], Iterator[object]],
) -> Iterator[RuntimeSignal]:
    """把当前执行器输出收敛为 event* + 恰好一个安全终止 signal。

    保留原签名、P10/P11 信号类型与失败映射；正常 EOF 前不交付暂存终止值。
    """
    yield from _guard_finite_stream(
        stream_factory,
        _classify_runtime_item,
        lambda: _failure(FailureCodeId.INTERNAL_INVARIANT_VIOLATION),
        _runtime_exception_failure,
    )


def _classify_run_item(item: object) -> tuple[RunEventSignal | RunDiagnosisResultSignal | RunMainDeliverySignal | RunFailureSignal, bool]:
    """把 typed RunExecutor 对象收敛为封闭 Run signal。"""
    if isinstance(item, RunEventSignal):
        return item, False
    if isinstance(item, (RunDiagnosisResultSignal, RunMainDeliverySignal, RunFailureSignal)):
        return item, True
    raise _ProtocolViolation


def _run_exception_failure(
    error: Exception,
    after_terminal: bool,
    default_failure: RunFailureCode,
) -> RunFailureSignal:
    """typed 异常只收敛到封闭失败码，不读取异常文本。"""
    if not after_terminal and isinstance(error, RunExecutionError):
        return safe_failure_signal(error.code)
    return safe_failure_signal(default_failure)


def guard_run_stream(
    stream_factory: Callable[[], Iterator[object]],
    *,
    default_failure: RunFailureCode,
) -> Iterator[RunEventSignal | RunDiagnosisResultSignal | RunMainDeliverySignal | RunFailureSignal]:
    """把 typed RunExecutor 输出收敛为 event* + 恰好一个封闭终止 signal。"""

    def exception_failure(error: Exception, after_terminal: bool) -> RunFailureSignal:
        return _run_exception_failure(error, after_terminal, default_failure)

    yield from _guard_finite_stream(
        stream_factory,
        _classify_run_item,
        lambda: safe_failure_signal(default_failure),
        exception_failure,
    )
