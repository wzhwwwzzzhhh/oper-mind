"""会话诊断闭环的领域常量与状态规则。"""

from __future__ import annotations

from enum import Enum


class SessionStatus(str, Enum):
    """诊断会话状态。"""

    ACTIVE = "active"
    ARCHIVED = "archived"


class MessageRole(str, Enum):
    """会话消息角色。"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class RunStatus(str, Enum):
    """诊断运行状态。"""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunEventType(str, Enum):
    """可持久化、可重放的诊断运行事件类型。"""

    RUN_QUEUED = "run_queued"
    RUN_STARTED = "run_started"
    ROUTE_DECIDED = "route_decided"
    AGENT_START = "agent_start"
    AGENT_DONE = "agent_done"
    CONFLICT_CHECKED = "conflict_checked"
    DEBATE_ROUND = "debate_round"
    REPORT = "report"
    REFLECTION = "reflection"
    RUN_SUCCEEDED = "run_succeeded"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"


RUN_TERMINAL_STATUSES = frozenset(
    {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}
)
