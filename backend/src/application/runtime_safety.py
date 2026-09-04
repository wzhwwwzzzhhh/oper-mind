"""P11 Runtime 输出协议保护：只校验信号，不拥有 Run 业务事实。"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from src.application.contracts import (
    DiagnosisExecutionError,
    DiagnosisExecutionEvent,
    DiagnosisExecutionResult,
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


def guard_runtime_stream(
    stream_factory: Callable[[], Iterator[object]],
) -> Iterator[RuntimeSignal]:
    """把当前执行器输出收敛为 event* + 恰好一个安全终止 signal。

    result/failure 只有在观察到正常 EOF 后才会交付。协议失败不等待不受信任的
    iterator cleanup；无限流与阻塞迭代仍诚实保留为 deadline gap。
    """

    try:
        iterator = iter(stream_factory())
    except DiagnosisExecutionError:
        yield _failure(FailureCodeId.MODEL_EXECUTION_FAILED)
        return
    except Exception:
        yield _failure(FailureCodeId.RUNTIME_UNEXPECTED_EXCEPTION)
        return

    terminal: RuntimeResultSignal | RuntimeFailureSignal | None = None
    while True:
        try:
            item = next(iterator)
        except StopIteration:
            if terminal is None:
                yield _failure(FailureCodeId.INTERNAL_INVARIANT_VIOLATION)
            else:
                yield terminal
            return
        except DiagnosisExecutionError:
            if terminal is None:
                yield _failure(FailureCodeId.MODEL_EXECUTION_FAILED)
            else:
                yield _failure(FailureCodeId.INTERNAL_INVARIANT_VIOLATION)
            return
        except Exception:
            yield _failure(FailureCodeId.RUNTIME_UNEXPECTED_EXCEPTION)
            return

        if terminal is not None:
            yield _failure(FailureCodeId.INTERNAL_INVARIANT_VIOLATION)
            return

        try:
            if isinstance(item, DiagnosisExecutionEvent):
                event_signal = RuntimeEventSignal(
                    contract_version=CONTRACT_VERSION_V1,
                    event=item,
                )
            elif isinstance(item, DiagnosisExecutionResult):
                terminal = RuntimeResultSignal(
                    contract_version=CONTRACT_VERSION_V1,
                    result=item,
                )
                continue
            elif isinstance(item, RuntimeFailureSignal):
                terminal = _safe_runtime_failure(item)
                continue
            else:
                yield _failure(FailureCodeId.INTERNAL_INVARIANT_VIOLATION)
                return
        except Exception:
            yield _failure(FailureCodeId.RUNTIME_UNEXPECTED_EXCEPTION)
            return

        yield event_signal
