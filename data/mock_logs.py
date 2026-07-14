"""模拟日志数据，用于开发和测试"""

MOCK_LOGS = {
    "system": [
        "[ERROR] 2026-07-05 10:23:45 - Connection pool exhausted - unable to get connection from MySQL",
        "[ERROR] 2026-07-05 10:23:46 - Query timeout: SELECT * FROM orders WHERE status = 'PENDING'",
        "[ERROR] 2026-07-05 10:23:47 - Thread pool exhausted: 200 threads active",
        "[WARN] 2026-07-05 10:23:48 - Slow query (5.2s): SELECT * FROM orders ORDER BY create_time DESC",
        "[ERROR] 2026-07-05 10:24:00 - OOM Killer invoked: process mysqld (PID 1234) killed",
        "[ERROR] 2026-07-05 10:24:05 - Connection refused: too many connections",
        "[INFO] 2026-07-05 10:24:10 - MySQL restarted after crash",
        "[WARN] 2026-07-05 10:25:00 - CPU usage threshold exceeded: 95%",
        "[ERROR] 2026-07-05 10:25:30 - Disk write timeout: /data/mysql",
        "[ERROR] 2026-07-05 10:26:00 - Application exception: java.lang.OutOfMemoryError",
    ],
    "slow_query": [
        {"sql": "SELECT * FROM orders WHERE status = 'PENDING'", "time": 5.2, "rows_examined": 50000},
        {"sql": "SELECT * FROM orders o JOIN order_items i ON o.id = i.order_id", "time": 3.8, "rows_examined": 200000},
        {"sql": "SELECT * FROM orders ORDER BY create_time DESC", "time": 4.1, "rows_examined": 50000},
        {"sql": "SELECT YEAR(create_time), COUNT(*) FROM orders GROUP BY YEAR(create_time)", "time": 6.0, "rows_examined": 50000},
    ],
}


def search_logs(keyword: str, max_results: int = 10) -> list[str]:
    """按关键字检索系统日志"""
    results = []
    for log in MOCK_LOGS["system"]:
        if keyword.lower() in log.lower():
            results.append(log)
    return results[:max_results]


def get_slow_queries(limit: int = 5) -> list[dict]:
    """获取慢查询列表"""
    return MOCK_LOGS["slow_query"][:limit]
