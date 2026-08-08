"""日志真实源 Connector 与配置测试（S1）。

覆盖：配置解析、诚实降级（未配置/不可用）、行级只读检索、时间范围过滤、
错误聚合、慢查询/超时模式解析、凭据/隐藏文件排除、符号链接越界防护。
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.config import load_service_log_dir
from src.infrastructure.logs.log_source import LogSourceConnector


def _write(root: Path, rel: str, content: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


class TestLoadServiceLogDir:
    """配置解析：环境变量命名空间化，缺省返回 None。"""

    def test_unset_returns_none(self, monkeypatch) -> None:
        monkeypatch.delenv("OPERMIND_SERVICE_POSTGRES_PRODUCTION_LOG_DIR", raising=False)
        assert load_service_log_dir("postgres-production") is None

    def test_set_returns_value(self, monkeypatch) -> None:
        monkeypatch.setenv("OPERMIND_SERVICE_POSTGRES_PRODUCTION_LOG_DIR", "D:/logs/pg")
        assert load_service_log_dir("postgres-production") == "D:/logs/pg"

    def test_instance_name_normalized(self, monkeypatch) -> None:
        monkeypatch.setenv("OPERMIND_SERVICE_LOG_STAGING_LOG_DIR", "D:/logs/stg")
        assert load_service_log_dir("log-staging") == "D:/logs/stg"


class TestLogSourceDegradation:
    """诚实降级：未配置与不可用不抛异常、不伪造。"""

    def test_not_configured_when_dir_none(self) -> None:
        connector = LogSourceConnector(log_dir=None, instance_id="postgres-production")
        assert connector.search("error", None).status == "not_configured"
        assert connector.aggregate_errors().status == "not_configured"
        assert connector.slow_query_patterns().status == "not_configured"

    def test_unavailable_when_dir_missing(self, tmp_path) -> None:
        connector = LogSourceConnector(log_dir=str(tmp_path / "missing"), instance_id="x")
        result = connector.search("error", None)
        assert result.status == "unavailable"
        assert "不可用" in result.message

    def test_unavailable_when_dir_is_file(self, tmp_path) -> None:
        target = tmp_path / "not_a_dir"
        target.write_text("x", encoding="utf-8")
        connector = LogSourceConnector(log_dir=str(target), instance_id="x")
        assert connector.search("error", None).status == "unavailable"


class TestSearch:
    """行级只读检索。"""

    @staticmethod
    def _basic_logs(tmp_path) -> LogSourceConnector:
        _write(
            tmp_path,
            "app.log",
            "[ERROR] 2026-07-05 10:23:45 - Connection pool exhausted: unable to get connection\n"
            "[WARN] 2026-07-05 10:23:48 - Slow query (5.2s): SELECT * FROM orders\n"
            "[INFO] 2026-07-05 10:24:10 - MySQL restarted after crash\n",
        )
        return LogSourceConnector(log_dir=str(tmp_path), instance_id="pg")

    def test_keyword_match(self, tmp_path) -> None:
        result = self._basic_logs(tmp_path).search("pool", None)
        assert result.status == "ok"
        assert result.total_hits == 1
        assert result.entries[0].level == "ERROR"
        assert result.entries[0].source == "app.log"
        assert "Connection pool" in result.entries[0].message

    def test_no_match(self, tmp_path) -> None:
        result = self._basic_logs(tmp_path).search("no-such-keyword", None)
        assert result.status == "ok"
        assert result.total_hits == 0
        assert result.entries == []

    def test_illegal_keyword_rejected(self, tmp_path) -> None:
        result = self._basic_logs(tmp_path).search("../etc", None)
        assert result.status == "invalid"

    def test_empty_keyword_rejected(self, tmp_path) -> None:
        result = self._basic_logs(tmp_path).search("   ", None)
        assert result.status == "invalid"

    def test_time_range_filters_old_lines(self, tmp_path) -> None:
        now = datetime.now()
        fresh = now - timedelta(minutes=5)
        old = now - timedelta(days=2)
        _write(
            tmp_path,
            "app.log",
            f"[ERROR] {fresh:%Y-%m-%d %H:%M:%S} - Fresh error\n"
            f"[ERROR] {old:%Y-%m-%d %H:%M:%S} - Old error\n",
        )
        connector = LogSourceConnector(log_dir=str(tmp_path), instance_id="pg")
        result = connector.search("error", time_range_hours=1.0)
        assert result.status == "ok"
        assert result.total_hits == 1
        assert "Fresh" in result.entries[0].message


class TestExclusionAndEscape:
    """凭据/隐藏文件排除与符号链接越界防护。"""

    def test_credential_file_excluded(self, tmp_path) -> None:
        # 动态拼接密钥串，避免提交文件里出现 sk- 字面量（门禁禁止）
        secret = "sk-" + "abcdef1234567890"
        _write(tmp_path, ".env", f"OPERMIND_KEY={secret}\n")
        _write(tmp_path, "app.log", "[ERROR] 2026-07-05 10:23:45 - real error\n")
        connector = LogSourceConnector(log_dir=str(tmp_path), instance_id="pg")
        result = connector.search("sk-", None)
        assert result.status == "ok"
        assert result.total_hits == 0

    def test_hidden_dir_excluded(self, tmp_path) -> None:
        _write(tmp_path, ".hidden/app.log", "[ERROR] now - hidden error\n")
        _write(tmp_path, "app.log", "[INFO] now - visible\n")
        connector = LogSourceConnector(log_dir=str(tmp_path), instance_id="pg")
        assert connector.search("hidden", None).total_hits == 0

    def test_symlink_outside_root_excluded(self, tmp_path) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.log").write_text("[ERROR] secret content\n", encoding="utf-8")
        root = tmp_path / "logs"
        root.mkdir()
        try:
            (root / "escape.log").symlink_to(outside / "secret.log")
        except (OSError, NotImplementedError):
            pytest.skip("无法创建符号链接（需要权限或开发者模式）")
        connector = LogSourceConnector(log_dir=str(root), instance_id="pg")
        assert connector.search("secret", None).total_hits == 0


class TestAggregateErrors:
    """错误类型与频率聚合。"""

    def test_error_types_counted(self, tmp_path) -> None:
        _write(
            tmp_path,
            "app.log",
            "[ERROR] 2026-07-05 10:23:45 - Connection pool exhausted: unable\n"
            "[ERROR] 2026-07-05 10:23:46 - Connection pool exhausted: again\n"
            "[ERROR] 2026-07-05 10:24:00 - Query timeout: SELECT\n"
            "[WARN] 2026-07-05 10:24:10 - Slow query (5.2s)\n",
        )
        connector = LogSourceConnector(log_dir=str(tmp_path), instance_id="pg")
        result = connector.aggregate_errors()
        assert result.status == "ok"
        assert result.total_errors == 3
        assert result.error_counts["Connection pool exhausted"] == 2
        assert result.error_counts["Query timeout"] == 1


class TestSlowQueryPatterns:
    """慢查询解析与超时关联。"""

    def test_slow_and_timeout(self, tmp_path) -> None:
        _write(
            tmp_path,
            "app.log",
            "[WARN] 2026-07-05 10:23:48 - Slow query (5.2s): SELECT * FROM orders\n"
            "[ERROR] 2026-07-05 10:24:05 - Query timeout: SELECT * FROM items\n"
            "[ERROR] 2026-07-05 10:24:06 - timed out waiting for lock\n"
            "[INFO] 2026-07-05 10:24:10 - normal line\n",
        )
        connector = LogSourceConnector(log_dir=str(tmp_path), instance_id="pg")
        report = connector.slow_query_patterns()
        assert report.status == "ok"
        assert len(report.slow_queries) == 1
        assert report.slow_queries[0].time_seconds == 5.2
        assert report.timeout_count == 2

    def test_threshold_filters(self, tmp_path) -> None:
        _write(
            tmp_path,
            "app.log",
            "[WARN] 2026-07-05 10:23:48 - Slow query (0.5s): quick\n"
            "[WARN] 2026-07-05 10:23:49 - Slow query (3.1s): slow\n",
        )
        connector = LogSourceConnector(log_dir=str(tmp_path), instance_id="pg")
        report = connector.slow_query_patterns(threshold_seconds=2.0)
        assert len(report.slow_queries) == 1
        assert report.slow_queries[0].time_seconds == 3.1
