"""P4.1 订单慢查询三个只读证据源的安全快照。"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvidenceSnapshot(BaseModel):
    """所有外部读取在进入编排前转换成脱敏标量快照。"""

    model_config = ConfigDict(extra="forbid")

    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        """外部证据时间必须是 UTC aware datetime。"""
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("observed_at 必须是 UTC aware datetime。")
        return value


class DatabaseEvidenceSnapshot(EvidenceSnapshot):
    """固定 pg_indexes 与 EXPLAIN 的最小结论。"""

    target_database_confirmed: bool
    target_index_exists: bool
    plan_uses_seq_scan: bool
    plan_uses_target_index: bool


class LogEvidenceSnapshot(EvidenceSnapshot):
    """固定 JSONL 窗口的聚合结论，不携带任何原始日志字段。"""

    matched_query_count: int = Field(ge=0)
    slow_query_count: int = Field(ge=0)
    timeout_count: int = Field(ge=0)


class ServerEvidenceSnapshot(EvidenceSnapshot):
    """固定服务健康和诊断指标端点的脱敏结论。"""

    service_healthy: bool
    window_size: int = Field(ge=0)
    p50_ms: float | None = Field(default=None, ge=0.0)
    p95_ms: float | None = Field(default=None, ge=0.0)
    slow_query_count: int = Field(ge=0)
    timeout_count: int = Field(ge=0)
    slow_query_threshold_ms: float | None = Field(default=None, ge=0.0)
