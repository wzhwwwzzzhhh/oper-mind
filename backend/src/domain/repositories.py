"""P2 会话诊断闭环的 Repository 端口。"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.domain.diagnosis import RunStatus, SessionStatus
from src.domain.records import (
    DiagnosisResultData,
    DiagnosisRunCursor,
    DiagnosisRunData,
    MessageCursor,
    MessageData,
    RepositoryPage,
    RunEventCursor,
    RunEventData,
    RunIdempotencyKeyData,
    SessionCursor,
    SessionData,
)


class SessionRepository(Protocol):
    """Session 持久化端口。"""

    def add(self, session: SessionData) -> None:
        """将会话加入调用方事务，不提交。"""

    def get_by_id(self, session_id: UUID) -> SessionData | None:
        """按主键读取会话。"""

    def save(self, session: SessionData) -> bool:
        """保存已有会话，返回是否找到目标记录，不提交。"""

    def list_page(
        self,
        cursor: SessionCursor | None,
        limit: int,
        status: SessionStatus | None = None,
    ) -> RepositoryPage[SessionData, SessionCursor]:
        """按更新时间倒序读取会话页。"""


class MessageRepository(Protocol):
    """Message 持久化端口。"""

    def add(self, message: MessageData) -> None:
        """将消息加入调用方事务，不提交。"""

    def get_by_id(self, message_id: UUID) -> MessageData | None:
        """按主键读取消息（含已删除消息，供 Run/重跑等历史链路追溯）。"""

    def update_content(self, message_id: UUID, content: str, edited_at: datetime) -> MessageData | None:
        """仅更新消息内容与编辑时间，时间线位置不变；返回更新后的消息，未找到或已删除返回 None。"""

    def archive(self, message_id: UUID, archived_at: datetime) -> bool:
        """软删除消息；返回是否真的执行了标记（已删除或不存在返回 False）。"""

    def list_by_session(
        self,
        session_id: UUID,
        cursor: MessageCursor | None,
        limit: int,
    ) -> RepositoryPage[MessageData, MessageCursor]:
        """按创建时间正序读取会话消息页（不含已删除消息）。"""


class DiagnosisRunRepository(Protocol):
    """DiagnosisRun 持久化端口。"""

    def add(self, run: DiagnosisRunData) -> None:
        """将 Run 加入调用方事务，不提交。"""

    def get_by_id(self, run_id: UUID) -> DiagnosisRunData | None:
        """按主键读取 Run。"""

    def transition_status(
        self,
        run_id: UUID,
        expected_statuses: set[RunStatus],
        status: RunStatus,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> DiagnosisRunData | None:
        """仅在当前状态属于预期集合时更新 Run，返回更新后的值。"""

    def reserve_event_sequence(self, run_id: UUID) -> int | None:
        """原子预留下一事件 sequence，返回预留值，不提交。"""

    def list_by_session(
        self,
        session_id: UUID,
        cursor: DiagnosisRunCursor | None,
        limit: int,
    ) -> RepositoryPage[DiagnosisRunData, DiagnosisRunCursor]:
        """按创建时间倒序读取 Session 下的 Run 页。"""


class RunEventRepository(Protocol):
    """RunEvent 持久化端口。"""

    def add(self, event: RunEventData) -> None:
        """将事件加入调用方事务，不提交。"""

    def list_by_run(
        self,
        run_id: UUID,
        cursor: RunEventCursor | None,
        limit: int,
    ) -> RepositoryPage[RunEventData, RunEventCursor]:
        """按 sequence 正序读取 Run 事件页。"""


class DiagnosisResultRepository(Protocol):
    """DiagnosisResult 持久化端口。"""

    def add(self, result: DiagnosisResultData) -> None:
        """将结果加入调用方事务，不提交。"""

    def get_by_run_id(self, run_id: UUID) -> DiagnosisResultData | None:
        """按 Run 唯一关联读取结果。"""


class RunIdempotencyKeyRepository(Protocol):
    """Run 幂等记录持久化端口。"""

    def add(self, key: RunIdempotencyKeyData) -> None:
        """将幂等记录加入调用方事务，不提交。"""

    def get_by_scope(
        self,
        session_id: UUID,
        endpoint: str,
        idempotency_key: UUID,
    ) -> RunIdempotencyKeyData | None:
        """按 Session、端点和幂等键读取记录。"""


class SessionExportStore(Protocol):
    """会话导出只读聚合端口（消息/Run/结果的安全投影数据源，实现装配在 dependencies.py）。"""

    def get_session(self, session_id: UUID) -> SessionData | None:
        """按主键读取会话。"""

    def list_latest_messages(self, session_id: UUID, limit: int) -> list[MessageData]:
        """读取会话最近 limit 条消息（按创建时间正序）。"""

    def list_latest_runs(self, session_id: UUID, limit: int) -> list[DiagnosisRunData]:
        """读取会话最近 limit 个 Run（按创建时间正序）。"""

    def get_result(self, run_id: UUID) -> DiagnosisResultData | None:
        """按 Run 唯一关联读取结果。"""

    def close(self) -> None:
        """释放数据源连接。"""
