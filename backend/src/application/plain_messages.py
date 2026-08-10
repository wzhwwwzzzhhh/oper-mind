"""P8 独立消息通道——普通消息的轻量回复应用服务。

普通意图消息只落库 user + assistant 两条消息（run_id 为空），
不创建 Run、不触发多 Agent 图、不访问任何 Tool/Connector。

持久化经 ``PlainMessageWriter`` 端口注入，具体 SQLAlchemy 实现在
``src.infrastructure.persistence.plain_message_writer``，由 ``dependencies.py`` 装配。
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from pydantic import ConfigDict, Field

from src.application.contracts import ApplicationCommand
from src.application.errors import InvestigationRequiredError
from src.application.message_routing import requires_database_context
from src.domain.records import MessageData

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


class PlainMessageWriter(Protocol):
    """普通消息持久化端口：在单事务内校验会话并落库消息对。"""

    def send_plain_message(
        self,
        session_id: UUID,
        content: str,
        reply_content: str,
    ) -> tuple[MessageData, MessageData]:
        """校验会话并落库 user + assistant 两条消息（run_id 为空）。

        会话不存在或已归档时抛对应应用错误，不落任何消息。
        """
        ...


class PlainMessageApplicationService:
    """普通消息轻量回复用例。

    服务端权威判定意图：调查意图抛 ``InvestigationRequiredError``（路由层映射 409，
    前端回退到 Run 主链路）；普通意图经 ``PlainMessageWriter`` 端口在单事务内落库
    user + assistant 两条消息，assistant 时间戳严格晚于 user，保证顺序稳定。
    """

    def __init__(self, writer: PlainMessageWriter) -> None:
        self._writer = writer

    def send_plain_message(
        self,
        session_id: UUID,
        command: SendPlainMessageCommand,
    ) -> PlainMessageResult:
        """校验意图并落库普通消息对，返回两条消息。"""
        content = command.content.strip()
        if requires_database_context(content):
            raise InvestigationRequiredError()
        user_message, assistant_message = self._writer.send_plain_message(
            session_id,
            content,
            PLAIN_REPLY_TEMPLATE,
        )
        return PlainMessageResult(user_message=user_message, assistant_message=assistant_message)
