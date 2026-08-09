"""P6 主机指标采集器单元测试。

覆盖：mock 场景确定性解析（S1/S2/S3 格式变体）、psutil 不可用诚实降级（AC2/AC4）、
真实采集（注入假 psutil）、TTL 缓存、异常进程字段可空。
"""

from __future__ import annotations

from datetime import UTC
from types import SimpleNamespace

import pytest
from data.scenarios import set_active_scenario

from src.domain.host_metrics import HostMetricsMode, HostMetricsSourceStatus
from src.infrastructure.monitoring.host_metrics import PsutilHostMetricsCollector


def _fake_psutil() -> SimpleNamespace:
    """返回确定性假 psutil，避免真机采集进入单测。"""
    memory = SimpleNamespace(total=16 * 1024**3, used=13 * 1024**3, percent=81.0)

    def disk_usage(mount: str) -> SimpleNamespace:
        if mount == "C:\\":
            return SimpleNamespace(percent=62.0, used=115 * 1024**3, total=185 * 1024**3)
        return SimpleNamespace(percent=98.0, used=502 * 1024**3, total=512 * 1024**3)

    conns = [
        SimpleNamespace(status="ESTABLISHED"),
        SimpleNamespace(status="ESTABLISHED"),
        SimpleNamespace(status="TIME_WAIT"),
        SimpleNamespace(status="CLOSE_WAIT"),
    ]

    procs = [
        SimpleNamespace(info={"pid": 1234, "name": "mysqld", "cpu_percent": 85.0, "memory_percent": None}),
        SimpleNamespace(info={"pid": 5678, "name": "java", "cpu_percent": 1.0, "memory_percent": 45.0}),
        SimpleNamespace(info={"pid": 9012, "name": "ok", "cpu_percent": 2.0, "memory_percent": 3.0}),
    ]

    return SimpleNamespace(
        cpu_percent=lambda interval=0: 92.0,
        cpu_count=lambda: 4,
        getloadavg=lambda: (3.8, 3.1, 2.4),
        virtual_memory=lambda: memory,
        disk_partitions=lambda: [
            SimpleNamespace(mountpoint="C:\\"),
            SimpleNamespace(mountpoint="D:\\"),
        ],
        disk_usage=disk_usage,
        net_connections=lambda: conns,
        process_iter=lambda fields: procs,
        NoSuchProcess=type("NoSuchProcess", (Exception,), {}),
        AccessDenied=type("AccessDenied", (Exception,), {}),
    )


class TestMockParsing:
    """AC5：mock 模式读确定性场景，返回与场景一致的结构化标量。"""

    def test_s1_parses_all_scalars(self) -> None:
        set_active_scenario("S1")
        result = PsutilHostMetricsCollector().collect()

        assert result.mode is HostMetricsMode.MOCK
        assert result.source_status is HostMetricsSourceStatus.AVAILABLE
        assert result.cpu_percent == 92.0
        assert result.cpu_count == 4
        assert result.load_avg_1m == 3.8
        assert result.memory_percent == 81.0
        assert result.memory_total_bytes == 16 * 1024**3
        assert result.memory_used_bytes == 13 * 1024**3
        assert result.disk_used_percent == 70.0  # 跨分区最大值
        assert result.network_connections == 1024
        assert result.network_established == 512
        assert result.network_time_wait == 256
        assert [p.pid for p in result.abnormal_processes] == [1234, 5678]
        mysqld, java = result.abnormal_processes
        assert mysqld.name == "mysqld"
        assert mysqld.cpu_percent == 85.0
        assert mysqld.memory_percent is None  # 单条进程可只有 CPU
        assert java.name == "java"
        assert java.cpu_percent is None
        assert java.memory_percent == 45.0  # 单条进程可只有内存

    def test_s2_disk_max_and_no_abnormal_process(self) -> None:
        set_active_scenario("S2")
        result = PsutilHostMetricsCollector().collect()

        assert result.disk_used_percent == 98.0
        assert result.network_connections == 210
        assert result.network_time_wait == 20
        assert result.abnormal_processes == ()  # 「未发现异常进程」

    def test_s3_single_memory_process(self) -> None:
        set_active_scenario("S3")
        result = PsutilHostMetricsCollector().collect()

        assert len(result.abnormal_processes) == 1
        assert result.abnormal_processes[0].name == "java"
        assert result.abnormal_processes[0].memory_percent == 78.0
        assert result.abnormal_processes[0].cpu_percent is None

    def test_disk_partitions_exposed(self) -> None:
        set_active_scenario("S1")
        result = PsutilHostMetricsCollector().collect()

        mounts = [part.mount for part in result.disk_top_partitions]
        assert mounts == ["/", "/data"]
        assert result.disk_top_partitions[1].percent == 70.0


class TestHonestDegradation:
    """AC2/AC4：psutil 不可用时返回 unavailable + null，不用 0 代替缺失。"""

    def test_psutil_import_failure_returns_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        collector = PsutilHostMetricsCollector()

        def fail_load():
            raise ImportError("psutil 缺失")

        monkeypatch.setattr(collector, "_load_psutil", fail_load)
        result = collector.collect()

        assert result.source_status is HostMetricsSourceStatus.UNAVAILABLE
        assert result.mode is HostMetricsMode.TARGET
        assert result.cpu_percent is None
        assert result.memory_percent is None
        assert result.disk_used_percent is None
        assert result.network_connections is None
        assert result.abnormal_processes == ()

    def test_collection_exception_returns_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        collector = PsutilHostMetricsCollector()

        def fail():
            raise OSError("采集失败")

        monkeypatch.setattr(collector, "_collect_target_unbounded", fail)
        result = collector.collect()

        assert result.source_status is HostMetricsSourceStatus.UNAVAILABLE
        assert result.cpu_percent is None

    def test_unavailable_never_uses_zero(self) -> None:
        """AC4：不可用状态标量全部为 null，而不是 0 代替缺失。"""
        from datetime import datetime

        from src.domain.host_metrics import HostMetricsData

        unavailable = HostMetricsData.unavailable(
            datetime.now(UTC), mode=HostMetricsMode.TARGET
        )
        scalar_fields = [
            unavailable.cpu_percent,
            unavailable.memory_percent,
            unavailable.disk_used_percent,
            unavailable.network_connections,
            unavailable.memory_used_bytes,
        ]
        assert all(field is None for field in scalar_fields)


class TestRealCollection:
    """真实模式：注入假 psutil，验证结构化收敛与时间预算。"""

    def test_target_collection_structured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        collector = PsutilHostMetricsCollector(cache_seconds=0)
        monkeypatch.setattr(collector, "_load_psutil", lambda: _fake_psutil())

        result = collector.collect()

        assert result.mode is HostMetricsMode.TARGET
        assert result.source_status is HostMetricsSourceStatus.AVAILABLE
        assert result.cpu_percent == 92.0
        assert result.memory_percent == 81.0
        assert result.disk_used_percent == 98.0  # D:\ 分区更高
        assert result.network_connections == 4
        assert result.network_established == 2
        assert result.network_time_wait == 1
        assert [p.pid for p in result.abnormal_processes] == [1234, 5678]  # 只保留高占用

    def test_ttl_cache_reuses_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        collector = PsutilHostMetricsCollector(cache_seconds=10)
        calls = {"count": 0}

        def fake_load():
            calls["count"] += 1
            return _fake_psutil()

        monkeypatch.setattr(collector, "_load_psutil", fake_load)
        first = collector.collect()
        second = collector.collect()

        assert calls["count"] == 1  # 第二次命中缓存
        assert first is second

    def test_时间预算耗尽返回不可用(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """P2：采集超出时间预算时返回 unavailable，不返回部分数据。"""
        # 负数预算把截止时刻推到过去，确定性触发预算超时。
        collector = PsutilHostMetricsCollector(cache_seconds=0, time_budget_seconds=-1.0)
        monkeypatch.setattr(collector, "_load_psutil", lambda: _fake_psutil())

        result = collector.collect()

        assert result.source_status is HostMetricsSourceStatus.UNAVAILABLE
        assert result.cpu_percent is None


class TestDomainModel:
    """领域模型约束：UTC aware、frozen、extra forbid。"""

    def test_observed_at_must_be_utc_aware(self) -> None:
        from datetime import datetime

        from src.domain.host_metrics import HostMetricsData

        with pytest.raises(ValueError):
            HostMetricsData(
                mode=HostMetricsMode.MOCK,
                source_status=HostMetricsSourceStatus.AVAILABLE,
                observed_at=datetime(2026, 8, 6),
                cpu_percent=1.0,
            )
        value = HostMetricsData(
            mode=HostMetricsMode.MOCK,
            source_status=HostMetricsSourceStatus.AVAILABLE,
            observed_at=datetime.now(UTC),
            cpu_percent=1.0,
        )
        assert value.cpu_percent == 1.0
