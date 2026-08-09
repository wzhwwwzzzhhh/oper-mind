"""高危操作审批机制"""

# 高危操作的关键词
HIGH_RISK_KEYWORDS = [
    "alter table",
    "drop ",
    "truncate ",
    "kill ",
    "shutdown",
    "flush table",
]

# 安全的 SQL 操作白名单
SAFE_SQL_WHITELIST = [
    "select", "explain", "show", "describe",
    "add index",  # ALTER TABLE ADD INDEX 需要审批，但这里标记为工具类操作
]

# 允许的 ALTER TABLE 操作（只允许加索引）
ALLOWED_ALTER_OPERATIONS = [
    "add index",
    "add  index",
    "add unique",
]


class ApprovalRequired(Exception):
    """需要人工审批的异常"""


def is_high_risk_sql(sql: str) -> bool:
    """
    判断 SQL 是否为高危操作。

    检查 SQL 是否包含高危关键词。
    但排除那些虽然匹配关键词但实际上安全的操作。
    """
    sql_lower = sql.lower().strip()

    # 检查是否在白名单中（SELECT/EXPLAIN 直接放行）
    for safe in SAFE_SQL_WHITELIST:
        if sql_lower.startswith(safe):
            return False

    # 检查是否匹配高危操作
    return any(keyword in sql_lower for keyword in HIGH_RISK_KEYWORDS)


def is_alter_table_safe(alter_statement: str) -> bool:
    """
    检查 ALTER TABLE 是否在安全范围内。
    只允许 ADD INDEX，其他 ALTER 操作需要审批。
    """
    alter_lower = alter_statement.lower()
    return any(allowed in alter_lower for allowed in ALLOWED_ALTER_OPERATIONS)


def request_approval(operation: str, reason: str) -> bool:
    """
    请求人工审批。

    生产环境：发消息到审批系统（钉钉/企微/webhook）
    开发环境：CLI 输入 y/n
    """
    print(f"\n{'='*50}")
    print("⚠️  需要审批")
    print(f"操作: {operation}")
    print(f"原因: {reason}")
    print(f"{'='*50}")

    while True:
        choice = input("是否批准？(y/n): ").strip().lower()
        if choice in ("y", "yes"):
            print("✅ 已批准")
            return True
        if choice in ("n", "no"):
            print("❌ 已拒绝")
            return False
        print("请输入 y 或 n")


def check_operation_safety(operation_name: str, args: dict) -> bool:
    """
    检查操作是否需要审批。

    返回 True 表示可以继续，False 表示被拒绝。

    调用示例：
    check_operation_safety("kill_query", {"query_id": 123})
    """
    # 高危操作需要审批
    if operation_name in ("kill_query", "alter_table"):
        op_desc = {
            "kill_query": f"KILL 查询 (ID: {args.get('query_id', 'unknown')})",
            "alter_table": f"ALTER TABLE: {args.get('sql', 'unknown')}",
        }.get(operation_name, operation_name)

        reason = {
            "kill_query": "中断正在执行的查询，可能影响业务",
            "alter_table": "修改表结构，可能造成锁表或数据丢失",
        }.get(operation_name, "高危操作")

        return request_approval(op_desc, reason)

    # 一般操作不需要审批
    return True
