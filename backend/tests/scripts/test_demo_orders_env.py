"""PostgreSQL 订单慢 SQL 靶场控制脚本的纯单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import demo_orders_env as demo


def test_数据库环境拒绝非专用目标(monkeypatch: pytest.MonkeyPatch) -> None:
    """任何非固定隧道或数据库配置必须 fail closed。"""
    monkeypatch.setenv("OPERMIND_DEMO_PG_USER", "demo_user")
    monkeypatch.setenv("OPERMIND_DEMO_PG_PASSWORD", "demo_password")
    monkeypatch.setenv("OPERMIND_DEMO_PG_DATABASE", "gongkar")

    with pytest.raises(demo.DemoEnvironmentError, match="仅允许访问"):
        demo.database_settings_from_environment()


def test_percentile稳定计算并拒绝空数据() -> None:
    """延迟计算不依赖第三方统计组件。"""
    assert demo.percentile([1.0, 3.0, 5.0, 7.0], 0.5) == 4.0
    assert demo.percentile([1.0, 3.0, 5.0, 7.0], 0.95) == 6.7
    with pytest.raises(ValueError, match="至少需要"):
        demo.percentile([], 0.95)


def test_执行计划遍历提取索引与顺序扫描() -> None:
    """验证规则必须从固定计划结构而非 Agent 文本判断。"""
    plan = {
        "Node Type": "Limit",
        "Plans": [
            {
                "Node Type": "Index Scan",
                "Index Name": "idx_orders_user_created",
                "Relation Name": "orders",
            }
        ],
    }
    nodes = list(demo.walk_plan_nodes(plan))
    assert [node["Node Type"] for node in nodes] == ["Limit", "Index Scan"]


def test_故障验证要求索引计划延迟日志同时成立(monkeypatch: pytest.MonkeyPatch) -> None:
    """缺少任何故障证据都不能报告靶场故障已成立。"""
    baseline = demo.ProbeMeasurement(
        phase="baseline", observed_at="t", sample_count=3, request_ids=["b"],
        durations_ms=[2.0, 2.1, 2.2], p50_ms=2.1, p95_ms=2.19,
        min_ms=2.0, max_ms=2.2, slow_query_count=0, timeout_count=0,
        slow_query_threshold_ms=3.0,
    )
    degraded = demo.ProbeMeasurement(
        phase="degraded", observed_at="t", sample_count=3, request_ids=["d"],
        durations_ms=[20.0, 21.0, 22.0], p50_ms=21.0, p95_ms=21.9,
        min_ms=20.0, max_ms=22.0, slow_query_count=3, timeout_count=0,
        slow_query_threshold_ms=3.0,
    )
    monkeypatch.setattr(demo, "read_measurement", lambda phase: baseline if phase == "baseline" else degraded)
    monkeypatch.setattr(demo, "index_exists", lambda _settings: False)
    monkeypatch.setattr(demo, "inspect_plan", lambda _settings: (["Seq Scan"], [], False, True))
    monkeypatch.setattr(demo, "read_matching_logs", lambda _ids: [{"slow_query": True, "timeout": False}])

    report = demo.evaluate_verification(object(), "degraded")

    assert report.passed is True
    assert all(report.checks.values())


def test_故障验证以P50抵抗单次隧道P95抖动(monkeypatch: pytest.MonkeyPatch) -> None:
    """P50 明显退化时，单个 baseline P95 尖峰不能掩盖真实故障。"""
    baseline = demo.ProbeMeasurement(
        phase="baseline", observed_at="t", sample_count=10, request_ids=["b"],
        durations_ms=[60.0] * 10, p50_ms=62.0, p95_ms=79.0,
        min_ms=50.0, max_ms=87.0, slow_query_count=0, timeout_count=0,
        slow_query_threshold_ms=90.0,
    )
    degraded = demo.ProbeMeasurement(
        phase="degraded", observed_at="t", sample_count=10, request_ids=["d"],
        durations_ms=[84.0] * 10, p50_ms=84.0, p95_ms=99.0,
        min_ms=76.0, max_ms=101.0, slow_query_count=10, timeout_count=0,
        slow_query_threshold_ms=90.0,
    )
    monkeypatch.setattr(demo, "read_measurement", lambda phase: baseline if phase == "baseline" else degraded)
    monkeypatch.setattr(demo, "index_exists", lambda _settings: False)
    monkeypatch.setattr(demo, "inspect_plan", lambda _settings: (["Seq Scan"], [], False, True))
    monkeypatch.setattr(demo, "read_matching_logs", lambda _ids: [{"slow_query": True, "timeout": False}])

    report = demo.evaluate_verification(object(), "degraded")

    assert report.passed is True
    assert report.baseline_p50_ms == 62.0
    assert report.p50_ms == 84.0
    assert report.latency_ratio == 1.355


def test_恢复验证拒绝当前窗口仍有慢查询日志(monkeypatch: pytest.MonkeyPatch) -> None:
    """索引恢复后有慢日志时绝不能宣称已经恢复。"""
    baseline = demo.ProbeMeasurement(
        phase="baseline", observed_at="t", sample_count=3, request_ids=["b"],
        durations_ms=[2.0, 2.1, 2.2], p50_ms=2.1, p95_ms=2.19,
        min_ms=2.0, max_ms=2.2, slow_query_count=0, timeout_count=0,
        slow_query_threshold_ms=3.0,
    )
    recovered = demo.ProbeMeasurement(
        phase="recovered", observed_at="t", sample_count=3, request_ids=["r"],
        durations_ms=[2.0, 2.1, 2.2], p50_ms=2.1, p95_ms=2.19,
        min_ms=2.0, max_ms=2.2, slow_query_count=1, timeout_count=0,
        slow_query_threshold_ms=3.0,
    )
    monkeypatch.setattr(demo, "read_measurement", lambda phase: baseline if phase == "baseline" else recovered)
    monkeypatch.setattr(demo, "index_exists", lambda _settings: True)
    monkeypatch.setattr(demo, "inspect_plan", lambda _settings: (["Index Scan"], [demo.TARGET_INDEX], True, False))
    monkeypatch.setattr(demo, "read_matching_logs", lambda _ids: [{"slow_query": True, "timeout": False}])

    report = demo.evaluate_verification(object(), "recovered")

    assert report.passed is False
    assert report.checks["no_slow_or_timeout_log"] is False


def test_日志读取只匹配当前请求窗口(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """日志证据不能混入其他阶段的请求。"""
    log_path = tmp_path / "order-service.jsonl"
    log_path.write_text(
        "\n".join(
            json.dumps(item)
            for item in (
                {"request_id": "wanted", "slow_query": True},
                {"request_id": "other", "slow_query": False},
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(demo, "LOG_FILE", log_path)

    assert demo.read_matching_logs(["wanted"]) == [{"request_id": "wanted", "slow_query": True}]


def test_运行态边界拒绝靶场外路径(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """任何清理或状态读写都不能逃逸到 runtime 目录外。"""
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setattr(demo, "RUNTIME_DIR", runtime)

    with pytest.raises(demo.DemoEnvironmentError, match="之外"):
        demo.resolved_runtime_path(tmp_path / "outside.json")


def test_smoke启动失败仍尝试清理(monkeypatch: pytest.MonkeyPatch) -> None:
    """启动失败也必须尝试回收独立 schema。"""
    calls: list[tuple[str, ...]] = []

    def fake_main(argv: list[str]) -> int:
        calls.append(tuple(argv))
        return 1 if argv[0] == "start" else 0

    monkeypatch.setattr("scripts.smoke_demo_orders.demo_orders_env.main", fake_main)
    from scripts import smoke_demo_orders

    assert smoke_demo_orders.main(["--samples", "3"]) == 1
    assert calls[0][0] == "start"
    assert calls[-1] == ("clean",)
