"""日志工具真实分支与 mock 回归测试（S2）。

覆盖：真实模式走受控日志源并诚实降级、mock 模式（S1–S4）行为不变、
真实分支绝不返回 mock 内容、audit_summary 供 Trace 脱敏摘要。
"""

from datetime import datetime, timedelta
from pathlib import Path

from data.scenarios import set_active_scenario
from src.tools.log_tools import AggregateErrorsTool, QuerySlowLogTool, SearchLogsTool

_INSTANCE = "postgres-production"
_ENV_NAME = "OPERMIND_SERVICE_POSTGRES_PRODUCTION_LOG_DIR"


def _write_logs(tmp_path: Path, content: str | None = None) -> Path:
    """写入带近期时间戳的真实日志；默认内容覆盖检索/聚合/慢查询场景。"""
    if content is None:
        ts = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        content = (
            f"[ERROR] {ts} - Real app error: disk full\n"
            f"[WARN] {ts} - Slow query (5.2s): SELECT * FROM orders\n"
            f"[ERROR] {ts} - Query timeout: SELECT * FROM items\n"
            f"[INFO] {ts} - service restarted\n"
        )
    target = tmp_path / "app.log"
    target.write_text(content, encoding="utf-8")
    return tmp_path


class TestRealModeDegradation:
    """真实模式：未绑定服务 / 未配置 / 不可用 诚实降级，不崩溃不伪造。"""

    def test_no_service_id(self) -> None:
        tool = SearchLogsTool(service_id=None)
        assert tool.execute("error") == "日志源未选择目标服务"

    def test_not_configured(self, monkeypatch) -> None:
        monkeypatch.delenv(_ENV_NAME, raising=False)
        tool = SearchLogsTool(service_id=_INSTANCE)
        assert "未配置" in tool.execute("error")

    def test_unavailable_when_dir_missing(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv(_ENV_NAME, str(tmp_path / "missing"))
        tool = SearchLogsTool(service_id=_INSTANCE)
        assert tool.execute("error") == "日志源不可用"

    def test_all_three_tools_degrade_consistently(self, monkeypatch, tmp_path) -> None:
        monkeypatch.delenv(_ENV_NAME, raising=False)
        assert "未配置" in AggregateErrorsTool(service_id=_INSTANCE).execute()
        assert "未配置" in QuerySlowLogTool(service_id=_INSTANCE).execute()


class TestRealModeSearch:
    """真实模式：search_logs 返回真实日志源只读检索结果，而非场景 mock。"""

    def test_returns_real_results(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv(_ENV_NAME, str(_write_logs(tmp_path)))
        tool = SearchLogsTool(service_id=_INSTANCE)
        output = tool.execute("disk")
        assert "真实日志源" in output
        assert "Real app error" in output
        assert "Connection pool exhausted" not in output  # 绝不泄露 mock 内容

    def test_no_match(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv(_ENV_NAME, str(_write_logs(tmp_path)))
        tool = SearchLogsTool(service_id=_INSTANCE)
        assert "未找到包含" in tool.execute("no-such-term")

    def test_illegal_keyword_rejected(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv(_ENV_NAME, str(_write_logs(tmp_path)))
        tool = SearchLogsTool(service_id=_INSTANCE)
        assert "已拒绝" in tool.execute("../etc")

    def test_time_range_filter_applied(self, monkeypatch, tmp_path) -> None:
        fresh = datetime.now() - timedelta(minutes=5)
        old = datetime.now() - timedelta(days=2)
        _write_logs(
            tmp_path,
            f"[ERROR] {fresh:%Y-%m-%d %H:%M:%S} - Fresh error\n"
            f"[ERROR] {old:%Y-%m-%d %H:%M:%S} - Old error\n",
        )
        monkeypatch.setenv(_ENV_NAME, str(tmp_path))
        tool = SearchLogsTool(service_id=_INSTANCE)
        output = tool.execute("error", time_range="1h")
        assert "Fresh error" in output
        assert "Old error" not in output


class TestRealModeAnalysis:
    """真实模式：错误聚合与慢查询/超时关联。"""

    def test_aggregate_errors(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv(_ENV_NAME, str(_write_logs(tmp_path)))
        tool = AggregateErrorsTool(service_id=_INSTANCE)
        output = tool.execute()
        assert "真实日志源" in output
        assert "Real app error" in output
        assert "共 2 条错误日志" in output

    def test_slow_query_and_timeout(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv(_ENV_NAME, str(_write_logs(tmp_path)))
        tool = QuerySlowLogTool(service_id=_INSTANCE)
        output = tool.execute(limit=5)
        assert "慢查询日志（真实日志源" in output
        assert "5.2s" in output
        assert "超时关联" in output


class TestMockRegression:
    """mock 模式（场景激活）行为与改动前完全一致，真实分支不侵入。"""

    def test_search_logs_s1_exact(self) -> None:
        set_active_scenario("S1")
        tool = SearchLogsTool(service_id=_INSTANCE)
        expected = (
            "找到 2 条相关日志:\n"
            "[ERROR] 2026-07-05 10:23:45 - Connection pool exhausted - unable to get connection from MySQL\n"
            "[ERROR] 2026-07-05 10:23:47 - Thread pool exhausted: 200 threads active"
        )
        assert tool.execute("pool") == expected

    def test_aggregate_errors_s1(self) -> None:
        set_active_scenario("S1")
        tool = AggregateErrorsTool(service_id=_INSTANCE)
        output = tool.execute()
        assert output.startswith("错误聚合统计:")
        assert "共 " in output and "条错误日志" in output
        assert "真实日志源" not in output

    def test_slow_query_s1(self) -> None:
        set_active_scenario("S1")
        tool = QuerySlowLogTool(service_id=_INSTANCE)
        output = tool.execute(limit=5)
        assert output.startswith("慢查询日志 (Top 5):")
        assert "真实日志源" not in output


class TestAuditSummary:
    """audit_summary 提供 Trace 用的脱敏摘要，不含原始日志全文。"""

    def test_real_search_sets_summary(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv(_ENV_NAME, str(_write_logs(tmp_path)))
        tool = SearchLogsTool(service_id=_INSTANCE)
        tool.execute("disk")
        assert "命中" in tool.audit_summary()

    def test_degradation_sets_summary(self) -> None:
        tool = SearchLogsTool(service_id=None)
        tool.execute("error")
        assert tool.audit_summary() == "日志源未选择目标服务"
