"""P2 会话诊断闭环的应用命令与执行端口。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from src.domain.diagnosis import RunEventType
from src.domain.records import DiagnosisResultData, DiagnosisRunData


class ApplicationCommand(BaseModel):
    """Application Service 命令基类。"""

    model_config = ConfigDict(extra="forbid")


class CreateSessionCommand(ApplicationCommand):
    """创建诊断会话。"""

    title: str = Field(min_length=1, max_length=200)
    environment_id: UUID | None = None
    incident_id: UUID | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        """去除标题首尾空白并拒绝空标题。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("title 不能为空。")
        return normalized


class CreateRunCommand(ApplicationCommand):
    """受理一次 Session 诊断运行。"""

    session_id: UUID
    query: str = Field(min_length=1, max_length=4000)
    idempotency_key: UUID

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        """去除 query 首尾空白并拒绝空 query。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("query 不能为空。")
        return normalized


class DiagnosisExecutionEvent(BaseModel):
    """诊断执行器向 Application Service 输出的安全事件。"""

    model_config = ConfigDict(extra="forbid")

    type: RunEventType
    node: str = Field(min_length=1, max_length=80)
    occurred_at: datetime
    data: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, value: datetime) -> datetime:
        """执行事件必须携带 UTC aware 时间。"""
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("occurred_at 必须是 UTC aware datetime。")
        return value


class DiagnosisExecutionResult(BaseModel):
    """诊断执行完成后交给结果组装器的安全摘要。"""

    model_config = ConfigDict(extra="forbid")

    strategy: str | None = None


class DiagnosisExecutionError(Exception):
    """执行器可安全暴露给 Run 失败记录的错误。"""

    def __init__(self, code: str = "DIAGNOSIS_FAILED", message: str = "诊断执行失败，请稍后重试") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class DiagnosisExecutor(Protocol):
    """在无数据库事务状态运行的诊断执行端口。"""

    def stream(self, query: str) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        """输出安全事件，最后输出一次完成结果或抛出安全执行错误。"""


class ResultAssembler(Protocol):
    """将安全执行摘要组装为结构化 DiagnosisResult 的端口。"""

    def assemble(self, run: DiagnosisRunData, result: DiagnosisExecutionResult) -> DiagnosisResultData:
        """为成功 Run 构造完整且已校验的结构化结果。"""
