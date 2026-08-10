"""P2.4 v1 API 的不透明 cursor 编解码。"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from src.domain.actions import ActionEventCursor
from src.domain.records import (
    ActionProposalCursor,
    DiagnosisRunCursor,
    MessageCursor,
    RunEventCursor,
    SessionCursor,
)

CursorT = TypeVar("CursorT", bound=BaseModel)


class InvalidCursorError(ValueError):
    """客户端提供的 cursor 不符合当前端点固定排序契约。"""


def encode_cursor(cursor: BaseModel) -> str:
    """将已解码领域 cursor 转为客户端不可依赖的 URL 安全字符串。"""
    payload = cursor.model_dump(mode="json")
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(value: str | None, cursor_type: type[CursorT]) -> CursorT | None:
    """解码并校验端点专属 cursor，拒绝可猜测的无效输入。"""
    if value is None:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
        cursor = cursor_type.model_validate(payload)
    except (UnicodeEncodeError, UnicodeDecodeError, ValueError, json.JSONDecodeError, ValidationError) as error:
        raise InvalidCursorError("分页游标无效") from error
    return _normalize_cursor_datetime(cursor)


def _normalize_cursor_datetime(cursor: CursorT) -> CursorT:
    """把 JSON 解码的 `Z` 时间恢复为 UTC aware datetime。"""
    values = cursor.model_dump()
    for key, value in values.items():
        if not key.endswith("_at") or not isinstance(value, datetime):
            continue
        values[key] = value.astimezone(UTC)
    return cursor.__class__.model_validate(values)


__all__ = [
    "ActionEventCursor",
    "ActionProposalCursor",
    "DiagnosisRunCursor",
    "InvalidCursorError",
    "MessageCursor",
    "RunEventCursor",
    "SessionCursor",
    "decode_cursor",
    "encode_cursor",
]
