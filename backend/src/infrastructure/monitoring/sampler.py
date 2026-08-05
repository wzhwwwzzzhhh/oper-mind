"""P5 单进程历史监控采样器。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.domain.monitoring import ServiceMonitorSampleData
from src.domain.services import ServiceConnector
from src.infrastructure.persistence.database import SessionFactory
from src.infrastructure.persistence.monitor_repositories import SqlAlchemyMonitorSampleRepository


LOGGER = logging.getLogger(__name__)


class MonitorSampler:
    """逐个调用静态 Connector 并写入脱敏样本。"""

    def __init__(
        self,
        session_factory: SessionFactory,
        connectors: Sequence[ServiceConnector],
        retention_hours: int,
        sample_interval_seconds: int = 300,
    ) -> None:
        self._session_factory = session_factory
        self._connectors = tuple(connectors)
        self._retention_hours = retention_hours
        self._sample_interval_seconds = sample_interval_seconds

    def sample_once(self) -> list[ServiceMonitorSampleData]:
        """执行一轮采样，单服务失败不影响其他服务。"""
        results: list[ServiceMonitorSampleData] = []
        for connector in self._connectors:
            service_id = connector.definition().id
            observed_at = datetime.now(timezone.utc)
            try:
                sample = ServiceMonitorSampleData.from_snapshot(service_id, connector.health_snapshot())
            except Exception:
                LOGGER.warning("服务历史采样不可用：service_id=%s", service_id)
                sample = ServiceMonitorSampleData.unavailable(service_id, observed_at)
            results.append(sample)

        self._persist(results)
        return results

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
        """异步执行一轮采样，为每个 Connector 单独施加 3 秒超时。"""
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
            results.append(sample)
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
