"""P5 历史监控样本的 SQLAlchemy 仓储。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.domain.monitoring import ServiceMonitorSampleData
from src.infrastructure.persistence.models import ServiceMonitorSampleRecord


class SqlAlchemyMonitorSampleRepository:
    """读写已收敛为标量的历史样本。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, sample: ServiceMonitorSampleData) -> None:
        """加入一条尚未提交的历史样本。"""
        self._session.add(
            ServiceMonitorSampleRecord(
                service_id=sample.service_id,
                observed_at=sample.observed_at,
                availability=sample.availability.value,
                p50_ms=sample.p50_ms,
                p95_ms=sample.p95_ms,
                slow_query_count=sample.slow_query_count,
                timeout_count=sample.timeout_count,
                memory_bytes=sample.memory_bytes,
                client_connections=sample.client_connections,
                slowlog_count=sample.slowlog_count,
                host_cpu_percent=sample.host_cpu_percent,
                host_memory_percent=sample.host_memory_percent,
                host_memory_bytes=sample.host_memory_bytes,
                host_disk_used_percent=sample.host_disk_used_percent,
                performance_signal=sample.performance_signal.value,
                source_status=sample.source_status.value,
            )
        )

    def list_between(self, service_id: str, from_at: datetime, to_at: datetime) -> list[ServiceMonitorSampleData]:
        """按观测时间升序读取窗口内样本。"""
        rows = self._session.scalars(
            select(ServiceMonitorSampleRecord)
            .where(
                ServiceMonitorSampleRecord.service_id == service_id,
                ServiceMonitorSampleRecord.observed_at >= from_at,
                ServiceMonitorSampleRecord.observed_at <= to_at,
            )
            .order_by(ServiceMonitorSampleRecord.observed_at.asc(), ServiceMonitorSampleRecord.id.asc())
        )
        return [_to_data(row) for row in rows]

    def delete_older_than(self, cutoff: datetime) -> int:
        """删除保留窗口之外的样本并返回删除数量。"""
        result = self._session.execute(
            delete(ServiceMonitorSampleRecord).where(ServiceMonitorSampleRecord.observed_at < cutoff)
        )
        return int(result.rowcount or 0)


def _to_data(row: ServiceMonitorSampleRecord) -> ServiceMonitorSampleData:
    """将 ORM 行收敛为领域样本，阻止原始数据库字段向外泄露。"""
    from src.domain.services import PerformanceSignal, ServiceAvailability, ServiceSourceStatus

    observed_at = row.observed_at
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    else:
        observed_at = observed_at.astimezone(timezone.utc)
    return ServiceMonitorSampleData(
        id=row.id,
        service_id=row.service_id,
        observed_at=observed_at,
        availability=ServiceAvailability(row.availability),
        p50_ms=row.p50_ms,
        p95_ms=row.p95_ms,
        slow_query_count=row.slow_query_count,
        timeout_count=row.timeout_count,
        memory_bytes=row.memory_bytes,
        client_connections=row.client_connections,
        slowlog_count=row.slowlog_count,
        host_cpu_percent=row.host_cpu_percent,
        host_memory_percent=row.host_memory_percent,
        host_memory_bytes=row.host_memory_bytes,
        host_disk_used_percent=row.host_disk_used_percent,
        performance_signal=PerformanceSignal(row.performance_signal),
        source_status=ServiceSourceStatus(row.source_status),
    )
