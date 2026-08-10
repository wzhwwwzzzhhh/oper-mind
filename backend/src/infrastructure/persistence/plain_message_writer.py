"""P8 普通消息通道的 SQLAlchemy 持久化实现。

供 ``PlainMessageApplicationService`` 的 ``PlainMessageWriter`` 端口装配；
在单短事务内校验会话并落库 user + assistant 消息对。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from src.application.errors import SessionArchivedError, SessionNotFoundError
from src.domain.diagnosis import MessageRole, SessionStatus
from src.domain.records import MessageData
from src.infrastructure.persistence.database import SessionFactory
from src.infrastructure.persistence.repositories import (
    SqlAlchemyMessageRepository,
    SqlAlchemySessionRepository,
)


class SqlAlchemyPlainMessageWriter:
    """在单短事务内校验会话并落库普通消息对（user → assistant 时间戳递增）。"""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def send_plain_message(
        self,
        session_id: UUID,
        content: str,
        reply_content: str,
    ) -> tuple[MessageData, MessageData]:
        """校验会话、落库两条消息并更新会话活动时间。"""
        session: Session = self._session_factory()
        try:
            session_repository = SqlAlchemySessionRepository(session)
            message_repository = SqlAlchemyMessageRepository(session)
            session_data = session_repository.get_by_id(session_id)
            if session_data is None:
                raise SessionNotFoundError()
            if session_data.status == SessionStatus.ARCHIVED:
                raise SessionArchivedError()

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
                content=reply_content,
                created_at=now + timedelta(microseconds=1),
            )
            message_repository.add(user_message)
            message_repository.add(assistant_message)
            session_repository.save(
                session_data.model_copy(update={"updated_at": assistant_message.created_at})
            )
            session.commit()
            return user_message, assistant_message
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def _utc_now() -> datetime:
    """返回普通消息写入使用的 UTC aware 当前时间。"""
    return datetime.now(UTC)
