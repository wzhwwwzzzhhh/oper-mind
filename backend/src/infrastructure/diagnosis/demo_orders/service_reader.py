"""P4.1 固定订单服务健康和指标端点的只读读取器。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Protocol

from src.infrastructure.diagnosis.demo_orders.models import ServerEvidenceSnapshot
from src.infrastructure.diagnosis.demo_orders.postgres_reader import DemoOrdersSourceError
from src.infrastructure.diagnosis.demo_orders.settings import DemoOrdersEvidenceSettings


class DemoOrdersServiceClient(Protocol):
    """限定为健康和诊断指标两个 GET 请求的服务客户端端口。"""

    def health(self) -> Mapping[str, object]:
        """读取固定 health 端点。"""

    def metrics(self) -> Mapping[str, object]:
        """读取固定 diagnostics metrics 端点。"""


class HttpDemoOrdersServiceClient:
    """只允许读取固定本地订单服务端点的 HTTP 客户端。"""

    def __init__(self, settings: DemoOrdersEvidenceSettings) -> None:
        self._base_url = settings.service_base_url.rstrip("/")
        self._timeout_seconds = settings.connection_timeout_seconds

    def health(self) -> Mapping[str, object]:
        """GET 固定健康检查端点。"""
        return self._get_json("/health")

    def metrics(self) -> Mapping[str, object]:
        """GET 固定聚合指标端点。"""
        return self._get_json("/internal/diagnostic/metrics")

    def _get_json(self, path: str) -> Mapping[str, object]:
        """读取并校验 JSON 对象，不返回 HTTP body 原文。"""
        request = urllib.request.Request(f"{self._base_url}{path}", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                payload = response.read()
            decoded = json.loads(payload.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, urllib.error.URLError) as error:
            raise DemoOrdersSourceError("服务只读证据不可用") from error
        if not isinstance(decoded, dict):
            raise DemoOrdersSourceError("服务只读证据不可用")
        return decoded


class OrderServiceEvidenceReader:
    """将健康与聚合指标转换为受控服务证据。"""

    def __init__(self, client: DemoOrdersServiceClient) -> None:
        self._client = client

    def collect(self) -> ServerEvidenceSnapshot:
        """读取服务状态及有限性能计数，不调用会改变靶场状态的端点。"""
        health = self._client.health()
        metrics = self._client.metrics()
        return ServerEvidenceSnapshot(
            observed_at=datetime.now(timezone.utc),
            service_healthy=health.get("status") == "ok" and health.get("service") == "order-service",
            window_size=_nonnegative_int(metrics.get("window_size")),
            p50_ms=_nonnegative_float_or_none(metrics.get("p50_ms")),
            p95_ms=_nonnegative_float_or_none(metrics.get("p95_ms")),
            slow_query_count=_nonnegative_int(metrics.get("slow_query_count")),
            timeout_count=_nonnegative_int(metrics.get("timeout_count")),
            slow_query_threshold_ms=_nonnegative_float_or_none(metrics.get("slow_query_threshold_ms")),
        )


def _nonnegative_int(value: object) -> int:
    """将外部整数字段收敛为非负计数；非法响应安全失败。"""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DemoOrdersSourceError("服务只读证据不可用")
    return value


def _nonnegative_float_or_none(value: object) -> float | None:
    """将外部数值字段收敛为非负浮点数或 None。"""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise DemoOrdersSourceError("服务只读证据不可用")
    return float(value)
