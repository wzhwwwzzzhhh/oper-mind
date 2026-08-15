"""P8 消息编辑与删除的 SQLAlchemy 持久化实现。

供 ``MessageEditingApplicationService`` 的 ``MessageEditingWriter`` 端口装配；
在单短事务内校验归属并完成编辑 / 软删除，删除时按配对规则软删成对的
无 Run 普通回复（该消息之后、下一条 user 消息之前、role=assistant 且
run_id 为空的首条消息），Run 关联的 assistant 输出绝不删除。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from src.application.errors import (
    MessageNotDeletableError,
    MessageNotEditableError,
    MessageNotFoundError,
)
from src.domain.diagnosis import MessageRole
from src.domain.records import MessageCursor, MessageData
from src.infrastructure.persistence.database import SessionFactory
from src.infrastructure.persistence.repositories import SqlAlchemyMessageRepository

# 配对普通回复扫描的每页大小；会话消息量级小，扫描最多几页即可定位。
PAIR_SCAN_PAGE_SIZE = 50


class SqlAlchemyMessageEditingWriter:
    """在单短事务内完成消息编辑 / 软删除的 SQLAlchemy 实现。"""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def edit_message(
        self,
        session_id: UUID,
        message_id: UUID,
        content: str,
        edited_at: datetime,
    ) -> MessageData:
        """单事务编辑 user 消息；归属/角色/已删除校验失败抛对应应用错误。"""
        session: Session = self._session_factory()
        try:
            repository = SqlAlchemyMessageRepository(session)
            current = repository.get_by_id(message_id)
            if current is None or current.session_id != session_id or current.archived_at is not None:
                raise MessageNotFoundError()
            if current.role != MessageRole.USER:
                raise MessageNotEditableError()
            updated = repository.update_content(message_id, content, edited_at)
            if updated is None:
                raise MessageNotFoundError()
            session.commit()
            return updated
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def archive_message(self, session_id: UUID, message_id: UUID, archived_at: datetime) -> None:
        """单事务软删除 user 消息；重复删除幂等；成对普通回复随删，Run 留痕不动。"""
        session: Session = self._session_factory()
        try:
            repository = SqlAlchemyMessageRepository(session)
            current = repository.get_by_id(message_id)
            if current is None or current.session_id != session_id:
                raise MessageNotFoundError()
            if current.role != MessageRole.USER:
                raise MessageNotDeletableError()
            if current.archived_at is not None:
                return
            repository.archive(message_id, archived_at)
            paired = self._paired_plain_reply(repository, current)
            if paired is not None:
                repository.archive(paired.id, archived_at)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _paired_plain_reply(
        self,
        repository: SqlAlchemyMessageRepository,
        target: MessageData,
    ) -> MessageData | None:
        """在未删除视图内扫描目标消息之后、下一条 user 消息之前的第一条无 Run 普通回复。

        有 Run 的 assistant 输出（``run_id`` 非空）与 system 消息跳过；
        遇到下一条 user 消息即停止（配对边界）；找不到配对返回 None。
        """
        cursor = MessageCursor(created_at=target.created_at, id=target.id)
        while True:
            page = repository.list_by_session(target.session_id, cursor, PAIR_SCAN_PAGE_SIZE)
            for item in page.items:
                if item.role == MessageRole.USER:
                    return None
                if item.role == MessageRole.ASSISTANT and item.run_id is None:
                    return item
            if not page.has_more or page.next_cursor is None:
                return None
            cursor = page.next_cursor
