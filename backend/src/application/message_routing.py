"""P8 会话消息意图判定的单一事实源。

``requires_database_context`` 是「调查意图 vs 普通对话」的唯一关键词判定函数，
供 Run 受理（服务上下文守卫）与独立消息通道共用，避免两处规则漂移。
判定失败一律按普通对话处理（降级策略：不误触发调查）。
"""

from __future__ import annotations


def requires_database_context(query: str) -> bool:
    """识别需要数据库服务上下文的明确调查问题。

    与既有 P2 行为完全一致：含数据库调查关键词视为调查意图，
    否则视为普通对话（感谢/确认/闲聊等轻量消息）。
    """
    lowered = query.lower()
    database_keywords = (
        "select", "sql", "explain", "索引", "慢查询", "数据库", "postgres",
        "连接池", "锁等待", "数据库锁", "pg_stat", "schema",
    )
    if any(keyword in lowered for keyword in ("日志", "log", "错误", "异常", "报错", "超时")):
        return any(keyword in lowered for keyword in database_keywords)
    return any(
        keyword in lowered
        for keyword in (*database_keywords, "查询", "表")
    )
