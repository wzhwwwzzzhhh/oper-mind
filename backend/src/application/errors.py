"""P2 会话诊断闭环的应用层异常。"""

from __future__ import annotations


class ApplicationError(Exception):
    """可由后续 API 层映射为安全错误体的应用层异常。"""

    code = "APPLICATION_ERROR"
    message = "应用服务执行失败。"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)


class SessionNotFoundError(ApplicationError):
    """指定 Session 不存在。"""

    code = "SESSION_NOT_FOUND"
    message = "诊断会话不存在。"


class SessionArchivedError(ApplicationError):
    """已归档 Session 不可再创建 Run。"""

    code = "SESSION_ARCHIVED"
    message = "诊断会话已归档。"


class RunNotFoundError(ApplicationError):
    """指定 Run 不存在。"""

    code = "RUN_NOT_FOUND"
    message = "诊断运行不存在。"


class RunAlreadyTerminalError(ApplicationError):
    """Run 已处于终态，无法继续执行。"""

    code = "RUN_ALREADY_TERMINAL"
    message = "诊断运行已结束。"


class IdempotencyKeyReusedError(ApplicationError):
    """同一个幂等键被不同请求语义重用。"""

    code = "IDEMPOTENCY_KEY_REUSED"
    message = "幂等键已用于不同的诊断请求。"




class RunInputMessageInvalidError(ApplicationError):
    """Run 输入消息与所属会话不一致或不是用户消息。"""

    code = "RUN_INPUT_MESSAGE_INVALID"
    message = "诊断运行的输入消息无效。"
