"""P4.1 只读证据调查的跨层受控数据模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domain.diagnosis import DiagnosisSeverity

EvidenceSourceType = Literal["tool", "log", "metric", "database", "agent", "user"]
EvidenceAttributeValue = str | int | float | bool | None


class EvidenceModel(BaseModel):
    """P4.1 跨层证据对象的严格基类。"""

    model_config = ConfigDict(extra="forbid")


class EvidenceFact(EvidenceModel):
    """可公开、可持久化且不包含原始读取内容的证据事实。"""

    id: UUID = Field(default_factory=uuid4)
    source_type: EvidenceSourceType
    source_name: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=500)
    locator: str | None = Field(default=None, max_length=160)
    observed_at: datetime | None = None
    attributes: dict[str, EvidenceAttributeValue] = Field(default_factory=dict)

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime | None) -> datetime | None:
        """证据观察时间仅接受 UTC aware datetime。"""
        if value is None:
            return value
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("observed_at 必须是 UTC aware datetime。")
        return value


class MissingIndexSignal(EvidenceModel):
    """由只读数据库事实收敛出的缺索引信号。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    service_id: str = Field(min_length=1, max_length=64)
    schema_name: str = Field(alias="schema", min_length=1, max_length=63)
    table: str = Field(min_length=1, max_length=63)
    columns: tuple[str, ...] = Field(min_length=1, max_length=8)
    index_name: str = Field(min_length=1, max_length=63)


class RootCauseFact(EvidenceModel):
    """由确定性规则得出的根因或高风险线索。"""

    id: UUID = Field(default_factory=uuid4)
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[UUID] = Field(default_factory=list)
    missing_index: MissingIndexSignal | None = None


class RiskFact(EvidenceModel):
    """结果解释时需要展示的调查范围或不确定性风险。"""

    id: UUID = Field(default_factory=uuid4)
    level: Literal["low", "medium", "high", "critical"]
    summary: str = Field(min_length=1, max_length=500)
    mitigation: str | None = Field(default=None, max_length=500)


class AgentInvestigationSummary(EvidenceModel):
    """一个受控调查角色的过程摘要。"""

    agent: str = Field(min_length=1, max_length=80)
    status: Literal["completed", "skipped", "failed"]
    summary: str = Field(min_length=1, max_length=500)
    duration_ms: int | None = Field(default=None, ge=0)


class EvidenceInvestigationResult(EvidenceModel):
    """P4.1 执行器输出给 ResultAssembler 的完整安全调查摘要。"""

    summary: str = Field(min_length=1, max_length=1000)
    severity: DiagnosisSeverity
    confidence: float = Field(ge=0.0, le=1.0)
    root_causes: list[RootCauseFact] = Field(default_factory=list)
    evidence: list[EvidenceFact] = Field(default_factory=list)
    missing_index: MissingIndexSignal | None = None
    risks: list[RiskFact] = Field(default_factory=list)
    agent_summary: list[AgentInvestigationSummary] = Field(default_factory=list)
