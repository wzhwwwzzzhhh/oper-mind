"""受控动作执行的通用端口、安全异常与结果数据结构。

这是审批闭环骨架依赖的中性抽象：审批状态机只依赖此处的端口与异常，
不依赖任何具体动作实现（如某类数据库的索引修复）。具体执行器由后续
按服务类型和动作模板单独设计后，通过依赖注入提供。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import JsonValue

from src.domain.actions import ActionMode, ActionProposalData


class ControlledActionError(Exception):
    """执行器向应用层报告的安全失败，不携带驱动或网络细节。"""

    code = "ACTION_EXECUTION_FAILED"
    message = "固定修复执行失败，未暴露内部错误详情。"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)


class ActionPreconditionBlockedError(ControlledActionError):
    """执行前重新校验未通过，保证不发送任何变更操作。"""

    code = "ACTION_PRECONDITION_BLOCKED"
    message = "执行前置条件未满足，系统未执行固定修复。"


class ActionVerificationFailedError(ControlledActionError):
    """变更后独立 Verify 未通过。"""

    code = "ACTION_VERIFICATION_FAILED"
    message = "验证未通过；变更可能已提交，系统未自动回滚。"


@dataclass(frozen=True)
class ActionExecutionAttempt:
    """执行器返回给应用层的最小语义化执行结果。"""

    mode: ActionMode
    precondition_summary: str
    action_summary: str


@dataclass(frozen=True)
class ActionVerificationOutcome:
    """不包含 request id、原始日志或 SQL 的 Verify 摘要。"""

    mode: ActionMode
    summary: str
    facts: dict[str, JsonValue]


class ControlledActionExecutor(Protocol):
    """已审批固定动作的执行与独立 Verify 端口。

    实现必须在执行前重新校验前置条件、只执行代码内固定动作、
    并在返回结果和异常里不泄露凭据、连接串或原始外部数据。
    """

    def execute(self, proposal: ActionProposalData) -> ActionExecutionAttempt:
        """重新检查前置条件后执行代码内固定动作。"""

    def verify(self, proposal: ActionProposalData) -> ActionVerificationOutcome:
        """执行独立只读 Verify，不进行回滚。"""
