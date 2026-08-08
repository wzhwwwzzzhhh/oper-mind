"""P5 单进程历史监控采样器。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.domain.host_metrics import HostMetricsCollector, HostMetricsData, HostMetricsSourceStatus
from src.domain.monitoring import ServiceMonitorSampleData
from src.domain.services import ServiceConnector
from src.infrastructure.persistence.database import SessionFactory
from src.infrastructure.persistence.monitor_repositories import SqlAlchemyMonitorSampleRepository


LOGGER = logging.getLogger(__name__)


class MonitorSampler:
    """逐个调用静态 Connector 并写入脱敏样本，每轮附一次主机指标。"""

    def __init__(
        self,
        session_factory: SessionFactory,
        connectors: Sequence[ServiceConnector],
        retention_hours: int,
        sample_interval_seconds: int = 300,
        host_collector: HostMetricsCollector | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._connectors = tuple(connectors)
        self._retention_hours = retention_hours
        self._sample_interval_seconds = sample_interval_seconds
        self._host_collector = host_collector

    def sample_once(self) -> list[ServiceMonitorSampleData]:
        """执行一轮采样，单服务失败不影响其他服务；每轮附一次主机指标。"""
        host_data = self._collect_host_sync()
        results: list[ServiceMonitorSampleData] = []
        for connector in self._connectors:
            service_id = connector.definition().id
            observed_at = datetime.now(timezone.utc)
            try:
                sample = ServiceMonitorSampleData.from_snapshot(service_id, connector.health_snapshot())
            except Exception:
                LOGGER.warning("服务历史采样不可用：service_id=%s", service_id)
                sample = ServiceMonitorSampleData.unavailable(service_id, observed_at)
            results.append(self._attach_host(sample, host_data))

        self._persist(results)
        return results

    def _collect_host_sync(self) -> HostMetricsData | None:
        """同步采集一次主机指标；失败返回 None，主机字段保持 null，不影响服务状态。"""
        if self._host_collector is None:
            return None
        try:
            return self._host_collector.collect()
        except Exception:
            LOGGER.warning("主机指标采样不可用，本轮样本主机字段保持 null")
            return None

    async def _collect_host_async(self) -> HostMetricsData | None:
        """异步采集一次主机指标，3 秒超时；失败返回 None，只置主机字段为 null。"""
        if self._host_collector is None:
            return None
        try:
            return await asyncio.wait_for(asyncio.to_thread(self._host_collector.collect), timeout=3.0)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.warning("主机指标采样不可用，本轮样本主机字段保持 null")
            return None

    @staticmethod
    def _attach_host(
        sample: ServiceMonitorSampleData,
        host_data: HostMetricsData | None,
    ) -> ServiceMonitorSampleData:
        """把主机标量附加到样本；主机不可用/失败时样本主机字段保持 null，不改服务状态。"""
        if host_data is None or host_data.source_status is not HostMetricsSourceStatus.AVAILABLE:
            return sample
        return sample.model_copy(
            update={
                "host_cpu_percent": host_data.cpu_percent,
                "host_memory_percent": host_data.memory_percent,
                "host_memory_bytes": host_data.memory_used_bytes,
                "host_disk_used_percent": host_data.disk_used_percent,
            }
        )

    def _persist(self, results: list[ServiceMonitorSampleData]) -> None:
        """在独立短事务中写入本轮样本并清理过期数据。"""
        session = self._session_factory()
        try:
            repository = SqlAlchemyMonitorSampleRepository(session)
            for sample in results:
                repository.add(sample)
            repository.delete_older_than(datetime.now(timezone.utc) - timedelta(hours=self._retention_hours))
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    async def sample_once_async(self) -> list[ServiceMonitorSampleData]:
        """异步执行一轮采样，为每个 Connector 单独施加 3 秒超时；每轮附一次主机指标。"""
        host_data = await self._collect_host_async()
        results: list[ServiceMonitorSampleData] = []
        for connector in self._connectors:
            service_id = connector.definition().id
            observed_at = datetime.now(timezone.utc)
            try:
                snapshot = await asyncio.wait_for(asyncio.to_thread(connector.health_snapshot), timeout=3.0)
                sample = ServiceMonitorSampleData.from_snapshot(service_id, snapshot)
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.warning("服务历史采样不可用：service_id=%s", service_id)
                sample = ServiceMonitorSampleData.unavailable(service_id, observed_at)
            results.append(self._attach_host(sample, host_data))
        await asyncio.to_thread(self._persist, results)
        return results

    async def run_forever(self) -> None:
        """在应用生命周期内周期执行采样，不阻塞 API 事件循环。"""
        while True:
            try:
                await self.sample_once_async()
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.warning("服务历史采样轮次未完成")
            await asyncio.sleep(self._sample_interval_seconds)
