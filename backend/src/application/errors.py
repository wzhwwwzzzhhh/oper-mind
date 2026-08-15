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


class RunNotTerminalError(ApplicationError):
    """Run 尚未结束，不能发起重跑。"""

    code = "RUN_NOT_TERMINAL"
    message = "诊断运行尚未结束，不能重跑。"


class IdempotencyKeyReusedError(ApplicationError):
    """同一个幂等键被不同请求语义重用。"""

    code = "IDEMPOTENCY_KEY_REUSED"
    message = "幂等键已用于不同的诊断请求。"




class RunInputMessageInvalidError(ApplicationError):
    """Run 输入消息与所属会话不一致或不是用户消息。"""

    code = "RUN_INPUT_MESSAGE_INVALID"
    message = "诊断运行的输入消息无效。"


class InvestigationRequiredError(ApplicationError):
    """消息命中调查意图，应由调用方回退到 Run 主链路。"""

    code = "INVESTIGATION_REQUIRED"
    message = "这属于调查类问题，请使用调查发起。"


class ActionProposalNotFoundError(ApplicationError):
    """指定固定修复提案不存在。"""

    code = "ACTION_PROPOSAL_NOT_FOUND"
    message = "固定修复提案不存在。"


class ActionProposalInvalidStateError(ApplicationError):
    """Proposal 当前状态不允许该操作。"""

    code = "ACTION_PROPOSAL_INVALID_STATE"
    message = "固定修复提案当前状态不允许该操作；请重新调查后生成新提案。"


class ActionProposalExpiredError(ApplicationError):
    """已批准 Proposal 在执行声明时失效。"""

    code = "ACTION_PROPOSAL_EXPIRED"
    message = "固定修复批准已过期，请重新调查后生成新提案。"


class ServiceNotFoundError(ApplicationError):
    """请求的静态服务未注册。"""

    code = "SERVICE_NOT_FOUND"
    message = "已注册服务不存在。"


class ServiceInstanceConflictError(ApplicationError):
    """注册的服务实例 ID 与既有实例冲突。"""

    code = "SERVICE_INSTANCE_CONFLICT"
    message = "服务实例 ID 已存在。"


class ServiceRegistrationNotFoundError(ApplicationError):
    """请求的动态注册服务不存在。"""

    code = "SERVICE_NOT_FOUND"
    message = "动态注册服务不存在。"


class ServiceCenterUnavailableError(ApplicationError):
    """服务中心依赖尚未装配时安全拒绝。"""

    code = "SERVICE_CENTER_UNAVAILABLE"
    message = "服务中心当前不可用，请稍后重试。"


class ServiceContextRequiredError(ApplicationError):
    """数据库调查必须先绑定目标服务。"""

    code = "SERVICE_CONTEXT_REQUIRED"
    message = "数据库调查需要先选择目标服务。"


class ProviderNotFoundError(ApplicationError):
    """指定模型 Provider 不存在。"""

    code = "PROVIDER_NOT_FOUND"
    message = "模型 Provider 不存在。"


class SecretKeyNotConfiguredError(ApplicationError):
    """加密主密钥未配置，禁止保存 API Key。"""

    code = "SECRET_KEY_NOT_CONFIGURED"
    message = "加密主密钥未配置，请设置 OPERMIND_SECRET_KEY。"


class ProviderIdempotencyReusedError(ApplicationError):
    """同一个幂等键被不同 Provider 创建请求语义重用。"""

    code = "PROVIDER_IDEMPOTENCY_REUSED"
    message = "幂等键已用于不同的 Provider 创建请求。"


class ModelModePersistenceError(ApplicationError):
    """模型运行时模式写入应用库失败。"""

    code = "MODEL_MODE_PERSISTENCE_FAILED"
    message = "模型运行模式保存失败，请稍后重试。"


class ModelParamsPersistenceError(ApplicationError):
    """模型运行参数写入应用库失败。"""

    code = "MODEL_PARAMS_PERSISTENCE_FAILED"
    message = "模型运行参数保存失败，请稍后重试。"


class AuditExportLimitExceededError(ApplicationError):
    """审计导出结果超过单次上限；由路由捕获后直抛 422 EXPORT_LIMIT_EXCEEDED。"""

    code = "EXPORT_LIMIT_EXCEEDED"
    message = "导出结果超过单次上限，请收窄时间窗或过滤条件后重试。"
