"""Redis 只读服务 Connector 的单元测试。"""

from __future__ import annotations

from typing import Any

import pytest

from src.config import load_service_dsn
from src.domain.services import ServiceAvailability, ServiceRegistry, ServiceSourceStatus
from src.infrastructure.services.redis_connector import RedisServiceConnector


class FakeRedisClient:
    """只记录命令调用并返回预设结果的假 Redis 客户端。"""

    def __init__(
        self,
        *,
        ping: Any = True,
        used_memory: int | None = 1024,
        clients: list[dict[str, str]] | None = None,
        slowlog_len: int = 0,
        error: Exception | None = None,
    ) -> None:
        self.commands: list[str] = []
        self._ping = ping
        self._used_memory = used_memory
        self._clients = clients if clients is not None else [{"addr": "127.0.0.1:6379"}]
        self._slowlog_len = slowlog_len
        self._error = error
        self.closed = False

    def ping(self) -> Any:
        self.commands.append("ping")
        if self._error is not None:
            raise self._error
        return self._ping

    def info(self, section: str | None = None) -> dict[str, Any]:
        self.commands.append("info")
        if self._error is not None:
            raise self._error
        if section == "memory":
            return {"used_memory": self._used_memory}
        return {}

    def client_list(self) -> list[dict[str, str]]:
        self.commands.append("client_list")
        if self._error is not None:
            raise self._error
        return self._clients

    def slowlog_len(self) -> int:
        self.commands.append("slowlog_len")
        if self._error is not None:
            raise self._error
        return self._slowlog_len

    def close(self) -> None:
        self.closed = True


def test_无凭据返回未配置快照() -> None:
    """无 DSN 时不创建连接且返回固定未配置状态。"""
    snapshot = RedisServiceConnector(None).health_snapshot()

    assert snapshot.availability == ServiceAvailability.NOT_CONFIGURED
    assert snapshot.server_metrics.source_status == ServiceSourceStatus.NOT_CONFIGURED


def test_连接失败返回不可用快照() -> None:
    """连接异常被收敛为不可用，不向调用方抛出。"""
    snapshot = RedisServiceConnector(
        "redis://:secret@127.0.0.1:6379/0",
        client=FakeRedisClient(error=ConnectionError("connection refused")),
    ).health_snapshot()

    assert snapshot.availability == ServiceAvailability.UNAVAILABLE


def test_超时返回不可用快照() -> None:
    """连接超时被收敛为不可用，不向调用方抛出。"""
    snapshot = RedisServiceConnector(
        "redis://:secret@127.0.0.1:6379/0",
        client=FakeRedisClient(error=TimeoutError("timed out")),
    ).health_snapshot()

    assert snapshot.availability == ServiceAvailability.UNAVAILABLE


def test_非法dsn返回不可用快照() -> None:
    """非 redis 协议的 DSN 被收敛为不可用，不抛异常。"""
    snapshot = RedisServiceConnector(
        "postgresql://user:password@host:5432/database",
        client=FakeRedisClient(error=ValueError("invalid url")),
    ).health_snapshot()

    assert snapshot.availability == ServiceAvailability.UNAVAILABLE


def test_健康快照填充专用标量且pg字段置空() -> None:
    """PING/INFO/CLIENT/SLOWLOG 全部成功时生成健康快照，Redis 指标用专用标量。"""
    client = FakeRedisClient(
        used_memory=1048576,
        clients=[{"addr": "127.0.0.1:6379"}, {"addr": "127.0.0.1:6379"}, {"addr": "127.0.0.1:6379"}],
        slowlog_len=2,
    )
    snapshot = RedisServiceConnector(
        "redis://:secret@127.0.0.1:6379/0",
        client=client,
    ).health_snapshot()

    assert snapshot.availability == ServiceAvailability.HEALTHY
    assert snapshot.server_metrics.source_status == ServiceSourceStatus.AVAILABLE
    assert snapshot.server_metrics.memory_bytes == 1048576
    assert snapshot.server_metrics.client_connections == 3
    assert snapshot.server_metrics.slowlog_count == 2
    assert snapshot.server_metrics.p50_ms is None
    assert snapshot.server_metrics.p95_ms is None
    assert snapshot.server_metrics.slow_query_count is None
    assert snapshot.server_metrics.timeout_count is None
    assert snapshot.performance_signal.value == "slow_query_detected"


def test_无慢日志时性能信号为无慢查询() -> None:
    """SLOWLOG LEN 为 0 时性能信号为未检测到慢查询。"""
    snapshot = RedisServiceConnector(
        "redis://:secret@127.0.0.1:6379/0",
        client=FakeRedisClient(used_memory=512, slowlog_len=0),
    ).health_snapshot()

    assert snapshot.availability == ServiceAvailability.HEALTHY
    assert snapshot.performance_signal.value == "no_slow_query_detected"
    assert snapshot.server_metrics.slowlog_count == 0


def test_只读客户端仅执行只读命令() -> None:
    """快照只调用 PING/INFO/CLIENT LIST/SLOWLOG LEN，不得发出写命令。"""
    client = FakeRedisClient(used_memory=64, clients=[{"addr": "127.0.0.1:6379"}], slowlog_len=0)
    RedisServiceConnector("redis://:secret@127.0.0.1:6379/0", client=client).health_snapshot()

    assert client.commands == ["ping", "info", "client_list", "slowlog_len"]


def test_快照不包含凭据或env名() -> None:
    """快照序列化只含结构化状态，不携带 DSN、密码或环境变量名。"""
    snapshot = RedisServiceConnector(
        "redis://:secret-password@127.0.0.1:6379/0",
        client=FakeRedisClient(used_memory=8),
    ).health_snapshot()
    serialized = str(snapshot.model_dump())

    assert "secret-password" not in serialized
    assert "redis://" not in serialized
    assert "OPERMIND_SERVICE_" not in serialized
    assert "sk-" not in serialized


def test_未配置时指标为null不伪装() -> None:
    """未配置快照的 Redis 专用标量必须为 null，不用 0 代替缺失。"""
    snapshot = RedisServiceConnector(None).health_snapshot()

    assert snapshot.availability == ServiceAvailability.NOT_CONFIGURED
    assert snapshot.server_metrics.memory_bytes is None
    assert snapshot.server_metrics.client_connections is None
    assert snapshot.server_metrics.slowlog_count is None


def test_definition包含静态服务信息且调查未启用() -> None:
    """静态定义包含 Redis 服务 ID、类型与只读边界，调查能力诚实未启用。"""
    definition = RedisServiceConnector(None).definition()

    assert definition.id == "redis-production"
    assert definition.title
    assert definition.kind == "redis"
    assert tuple(item.id for item in definition.supported_investigations) == (
        "service_health_pressure.v1",
    )
    assert definition.action_boundary
    assert definition.session_title


def test_connector_definition使用实例身份() -> None:
    """不同实例的定义只改变服务身份，不改变只读能力声明。"""
    definition = RedisServiceConnector(None, instance_id="redis-staging", title="预发布 Redis 缓存").definition()

    assert definition.id == "redis-staging"
    assert definition.title == "预发布 Redis 缓存"
    assert definition.kind == "redis"


def test_实例凭据环境变量命名空间解析(monkeypatch: Any) -> None:
    """Redis 实例只读取自身命名空间 DSN，与其他实例互不串扰。"""
    monkeypatch.setenv("OPERMIND_SERVICE_REDIS_PRODUCTION_DSN", "redis://:production-secret@h:6379/0")
    monkeypatch.setenv("OPERMIND_SERVICE_REDIS_STAGING_DSN", "redis://:staging-secret@h:6379/0")

    assert load_service_dsn("redis-production") == "redis://:production-secret@h:6379/0"
    assert load_service_dsn("redis-staging") == "redis://:staging-secret@h:6379/0"


def test_生产客户端创建强制只读超时(monkeypatch: Any) -> None:
    """生产创建客户端时固定三秒连接/语句超时并解码响应。"""
    captured: dict[str, Any] = {}

    class FakeFactory:
        @classmethod
        def from_url(cls, dsn: str, **kwargs: Any) -> FakeRedisClient:
            captured["dsn"] = dsn
            captured["kwargs"] = kwargs
            return FakeRedisClient(error=TimeoutError("timed out"))

    monkeypatch.setattr("src.infrastructure.services.redis_connector.redis.Redis.from_url", FakeFactory.from_url)
    snapshot = RedisServiceConnector("redis://:secret@127.0.0.1:6379/0").health_snapshot()

    assert snapshot.availability == ServiceAvailability.UNAVAILABLE
    assert captured["kwargs"]["socket_connect_timeout"] == 3.0
    assert captured["kwargs"]["socket_timeout"] == 3.0
    assert captured["kwargs"]["decode_responses"] is True


def test_注册表拒绝重复实例_id() -> None:
    """重复服务 ID 不能覆盖已注册 Connector。"""
    first = RedisServiceConnector(None, instance_id="redis-production")
    second = RedisServiceConnector(None, instance_id="redis-production")

    with pytest.raises(ValueError):
        ServiceRegistry((first, second))
