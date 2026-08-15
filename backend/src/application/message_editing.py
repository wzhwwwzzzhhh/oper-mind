"""P8 消息编辑与删除——会话消息更正的应用服务。

仅允许编辑/删除 user 角色消息；编辑记录 ``edited_at``、时间线位置不变；
删除为软删除（``archived_at``），会话消息列表不再展示，Run/结果/留痕不受影响。

持久化经 ``MessageEditingWriter`` 端口注入（``SqlAlchemyMessageEditingWriter``，
见 ``src.infrastructure.persistence.message_editing_writer``），由 ``dependencies.py`` 装配；
单事务语义（校验、编辑/软删、成对普通回复随删）在 writer 内完成，服务层不直接接触数据库。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from pydantic import ConfigDict, Field

from src.application.contracts import ApplicationCommand
from src.domain.records import MessageData


class EditMessageCommand(ApplicationCommand):
    """编辑一条用户消息的新内容。"""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4000)


class MessageEditingWriter(Protocol):
    """消息编辑/删除持久化端口：单事务内校验并落库，返回结构化领域对象。"""

    def edit_message(
        self,
        session_id: UUID,
        message_id: UUID,
        content: str,
        edited_at: datetime,
    ) -> MessageData:
        """单事务编辑 user 消息并记录编辑时间。

        消息不存在 / 不属于该会话 / 已删除 → ``MessageNotFoundError``；
        非 user 角色 → ``MessageNotEditableError``。
        """

    def archive_message(self, session_id: UUID, message_id: UUID, archived_at: datetime) -> None:
        """单事务软删除 user 消息；成对的无 Run 普通回复随删；重复删除幂等成功。

        消息不存在 / 不属于该会话 → ``MessageNotFoundError``；
        非 user 角色 → ``MessageNotDeletableError``。
        """


class MessageEditingApplicationService:
    """消息编辑/删除用例。

    归属校验与单事务语义全部由 ``MessageEditingWriter`` 端口实现承担，
    本服务只做输入归一化与时间戳注入，保持用例薄、可测试。
    """

    def __init__(self, writer: MessageEditingWriter) -> None:
        self._writer = writer

    def edit_message(self, session_id: UUID, message_id: UUID, command: EditMessageCommand) -> MessageData:
        """更新 user 消息内容并记录编辑时间，返回更新后的消息（时间线位置不变）。"""
        return self._writer.edit_message(session_id, message_id, command.content.strip(), _utc_now())

    def archive_message(self, session_id: UUID, message_id: UUID) -> None:
        """软删除 user 消息；重复删除幂等成功；成对普通回复随删，Run 留痕不动。"""
        self._writer.archive_message(session_id, message_id, _utc_now())


def _utc_now() -> datetime:
    """返回消息编辑/删除使用的 UTC aware 当前时间。"""
    return datetime.now(UTC)
