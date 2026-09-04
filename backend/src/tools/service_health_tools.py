"""P12 三服务无参数、固定字段的只读健康 Tool。"""

from __future__ import annotations

import json
from typing import Any

from src.core.tool_registry import Tool, ToolExecutionResult
from src.domain.services import ServiceAvailability, ServiceSnapshotData, TypedServiceCapability


class _ServiceHealthTool(Tool):
    """只消费已绑定 capability，不接受目标、命令、SQL 或连接参数。"""

    def __init__(self, name: str, kind: str, capability: TypedServiceCapability) -> None:
        self._kind = kind
        self._capability = capability
        super().__init__(
            name=name,
            description=f"读取已绑定 {kind} 服务的固定只读健康与连接压力标量",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
        )

    def execute(self) -> ToolExecutionResult:
        """读取同一 registry entry 的快照并投影白名单标量。"""
        try:
            snapshot = self._capability.agent_health_snapshot()
        except Exception:
            return self._unavailable("read_failed")
        if not isinstance(snapshot, ServiceSnapshotData):
            return self._unavailable("invalid_fact")
        if snapshot.availability is not ServiceAvailability.HEALTHY:
            code = snapshot.failure_code or (
                "not_configured"
                if snapshot.availability is ServiceAvailability.NOT_CONFIGURED
                else "unavailable"
            )
            return self._unavailable(code)
        payload = self._safe_payload(snapshot)
        if any(value is None for key, value in payload.items() if key not in {"observed_at"}):
            return self._unavailable("malformed_fact")
        return ToolExecutionResult(
            status="ok",
            output=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            summary=f"{self._kind} 固定健康事实读取完成",
        )

    def _safe_payload(self, snapshot: ServiceSnapshotData) -> dict[str, Any]:
        metrics = snapshot.server_metrics
        common: dict[str, Any] = {
            "availability": snapshot.availability.value,
            "observed_at": snapshot.observed_at.isoformat(),
            "source_status": (
                "cleanup_unknown" if snapshot.cleanup_status == "unknown" else metrics.source_status.value
            ),
        }
        if self._kind == "redis":
            return {
                **common,
                "memory_bytes": metrics.memory_bytes,
                "client_connections": metrics.client_connections,
                "slowlog_count": metrics.slowlog_count,
            }
        if self._kind == "mysql":
            return {
                **common,
                "uptime_seconds": metrics.uptime_seconds,
                "current_connections": metrics.client_connections,
                "running_connections": metrics.running_connections,
                "max_connections": metrics.max_connections,
                "slow_query_count": metrics.slow_query_count,
            }
        total = metrics.client_connections
        maximum = metrics.max_connections
        utilization = total / maximum if total is not None and maximum not in {None, 0} else None
        health = None
        if utilization is not None:
            health = "exhausted" if utilization >= 1 else "near_limit" if utilization >= 0.8 else "normal"
        return {
            **common,
            "total_connections": total,
            "active_connections": metrics.active_connections,
            "idle_connections": metrics.idle_connections,
            "waiting_connections": metrics.waiting_connections,
            "max_connections": metrics.max_connections,
            "utilization": utilization,
            "health": health,
        }

    def _unavailable(self, code: str) -> ToolExecutionResult:
        return ToolExecutionResult(
            status="unavailable",
            output=json.dumps(
                {"availability": "unavailable", "failure_code": code},
                ensure_ascii=False,
                sort_keys=True,
            ),
            summary=f"{self._kind} 固定健康事实不可用",
        )


class PostgresHealthOverviewTool(_ServiceHealthTool):
    """PostgreSQL 固定健康 Tool，沿用既有连接池工具名。"""

    def __init__(self, capability: TypedServiceCapability) -> None:
        super().__init__("check_connection_pool", "postgres", capability)


class RedisHealthOverviewTool(_ServiceHealthTool):
    """Redis 固定 PING/INFO/CLIENT LIST/SLOWLOG LEN 投影。"""

    def __init__(self, capability: TypedServiceCapability) -> None:
        super().__init__("redis_health_overview", "redis", capability)


class MySqlHealthOverviewTool(_ServiceHealthTool):
    """MySQL 固定 SHOW STATUS/VARIABLES 投影。"""

    def __init__(self, capability: TypedServiceCapability) -> None:
        super().__init__("mysql_health_overview", "mysql", capability)
