"""P8 独立消息通道——普通消息的轻量回复应用服务。

普通意图消息只落库 user + assistant 两条消息（run_id 为空），
不创建 Run、不触发多 Agent 图、不访问任何 Tool/Connector。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import ConfigDict, Field
from sqlalchemy.orm import Session

from src.application.contracts import ApplicationCommand
from src.application.errors import (
    InvestigationRequiredError,
    SessionArchivedError,
    SessionNotFoundError,
)
from src.application.message_routing import requires_database_context
from src.application.services import _in_transaction, _touch_session
from src.domain.diagnosis import MessageRole, SessionStatus
from src.domain.records import MessageData
from src.infrastructure.persistence.database import SessionFactory
from src.infrastructure.persistence.repositories import (
    SqlAlchemyMessageRepository,
    SqlAlchemySessionRepository,
)

PLAIN_REPLY_PREFIX = "这是普通对话回复："
PLAIN_REPLY_TEMPLATE = (
    "这是普通对话回复：本次未启动调查，也未访问任何外部服务。"
    "如果你想排查慢查询、连接池、索引等问题，可以直接描述，我会发起只读调查。"
)


class SendPlainMessageCommand(ApplicationCommand):
    """发送一条普通对话消息。"""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4000)


class PlainMessageResult:
    """普通消息通道的落库结果（user + assistant 两条消息）。"""

    def __init__(self, user_message: MessageData, assistant_message: MessageData) -> None:
        self.user_message = user_message
        self.assistant_message = assistant_message


class PlainMessageApplicationService:
    """普通消息轻量回复用例。

    服务端权威判定意图：调查意图抛 ``InvestigationRequiredError``（路由层映射 409，
    前端回退到 Run 主链路）；普通意图在单事务内落库 user + assistant 两条消息，
    assistant 时间戳严格晚于 user，保证消息列表顺序稳定（user → assistant）。
    """

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def send_plain_message(
        self,
        session_id: UUID,
        command: SendPlainMessageCommand,
    ) -> PlainMessageResult:
        """在单事务内校验会话并落库普通消息对，返回两条消息。"""

        def operation(session: Session) -> PlainMessageResult:
            session_repository = SqlAlchemySessionRepository(session)
            message_repository = SqlAlchemyMessageRepository(session)
            session_data = session_repository.get_by_id(session_id)
            if session_data is None:
                raise SessionNotFoundError()
            if session_data.status == SessionStatus.ARCHIVED:
                raise SessionArchivedError()

            content = command.content.strip()
            if requires_database_context(content):
                raise InvestigationRequiredError()
            now = _utc_now()
            user_message = MessageData(
                session_id=session_id,
                run_id=None,
                role=MessageRole.USER,
                content=content,
                created_at=now,
            )
            assistant_message = MessageData(
                session_id=session_id,
                run_id=None,
                role=MessageRole.ASSISTANT,
                content=PLAIN_REPLY_TEMPLATE,
                created_at=now + timedelta(microseconds=1),
            )
            message_repository.add(user_message)
            message_repository.add(assistant_message)
            _touch_session(session_repository, session_data, assistant_message.created_at)
            return PlainMessageResult(user_message=user_message, assistant_message=assistant_message)

        return _in_transaction(self._session_factory, operation)


def _utc_now() -> datetime:
    """返回普通消息用例使用的 UTC aware 当前时间。"""
    return datetime.now(UTC)
