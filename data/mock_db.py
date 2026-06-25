"""模拟数据库返回结果，开发时不需要连真实数据库"""

import json

# 表结构定义（模拟 MySQL）
TABLES = {
    "orders": {
        "create_table": """
CREATE TABLE `orders` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL,
  `order_no` varchar(32) NOT NULL,
  `status` varchar(16) NOT NULL DEFAULT 'PENDING',
  `total_amount` decimal(10,2) NOT NULL,
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `pay_time` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """.strip(),
        "indexes": [
            {"Key_name": "PRIMARY", "Column_name": "id", "Seq_in_index": 1, "Non_unique": 0, "Cardinality": 50000},
            {"Key_name": "idx_user_id", "Column_name": "user_id", "Seq_in_index": 1, "Non_unique": 1, "Cardinality": 10000},
        ],
    },
    "order_items": {
        "create_table": """
CREATE TABLE `order_items` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `order_id` bigint(20) NOT NULL,
  `product_id` bigint(20) NOT NULL,
  `product_name` varchar(128) NOT NULL,
  `quantity` int(11) NOT NULL,
  `price` decimal(10,2) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_order_id` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """.strip(),
        "indexes": [
            {"Key_name": "PRIMARY", "Column_name": "id", "Seq_in_index": 1, "Non_unique": 0, "Cardinality": 200000},
            {"Key_name": "idx_order_id", "Column_name": "order_id", "Seq_in_index": 1, "Non_unique": 1, "Cardinality": 50000},
        ],
    },
    "products": {
        "create_table": """
CREATE TABLE `products` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `name` varchar(128) NOT NULL,
  `category_id` bigint(20) NOT NULL,
  `price` decimal(10,2) NOT NULL,
  `stock` int(11) NOT NULL,
  `status` tinyint(4) NOT NULL DEFAULT 1,
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """.strip(),
        "indexes": [
            {"Key_name": "PRIMARY", "Column_name": "id", "Seq_in_index": 1, "Non_unique": 0, "Cardinality": 10000},
        ],
    },
}


def get_create_table(table_name: str) -> str | None:
    """返回建表语句"""
    table = TABLES.get(table_name)
    if table:
        return table["create_table"]
    return None


def get_indexes(table_name: str) -> list[dict] | None:
    """返回表的索引信息（SHOW INDEX FROM 的结果）"""
    table = TABLES.get(table_name)
    if table:
        return table["indexes"]
    return None


def explain_sql(sql: str) -> dict:
    """
    模拟 EXPLAIN 返回结果。
    根据 SQL 特征匹配已知的慢查询模式。
    """
    sql_upper = sql.upper()

    # 模式1：WHERE status = 'PENDING' 没索引
    if "STATUS" in sql_upper and "PENDING" in sql_upper:
        return {
            "id": 1,
            "select_type": "SIMPLE",
            "table": "orders",
            "type": "ALL",           # 全表扫描！
            "possible_keys": None,   # 没有可用索引
            "key": None,             # 实际没走索引
            "rows": 50000,
            "Extra": "Using where",
        }

    # 模式2：YEAR(create_time) 函数包裹导致索引失效
    if "YEAR" in sql_upper and "CREATE_TIME" in sql_upper:
        return {
            "id": 1,
            "select_type": "SIMPLE",
            "table": "orders",
            "type": "ALL",
            "possible_keys": "idx_create_time",
            "key": None,             # 函数包裹导致索引失效
            "rows": 50000,
            "Extra": "Using where; Using index",  # 提示用了索引但其实是全扫
        }

    # 模式3：ORDER BY create_time DESC 没索引
    if "ORDER BY" in sql_upper and "CREATE_TIME" in sql_upper:
        return {
            "id": 1,
            "select_type": "SIMPLE",
            "table": "orders",
            "type": "ALL",
            "possible_keys": None,
            "key": None,
            "rows": 50000,
            "Extra": "Using filesort",  # 文件排序，性能杀手！
        }

    # 模式4：JOIN 没索引
    if "JOIN" in sql_upper and "PRODUCT_ID" in sql_upper:
        return {
            "id": 1,
            "select_type": "SIMPLE",
            "table": "order_items",
            "type": "ALL",
            "possible_keys": None,
            "key": None,
            "rows": 200000,
            "Extra": "Using where",
        }

    # 模式5：复合查询，索引不全
    if "STATUS" in sql_upper and "COMPLETED" in sql_upper and "CREATE_TIME" in sql_upper:
        return {
            "id": 1,
            "select_type": "SIMPLE",
            "table": "orders",
            "type": "ref",
            "possible_keys": "idx_status",
            "key": "idx_status",
            "rows": 8000,
            "Extra": "Using where; Using filesort",
        }

    # 模式6：你的新 case
    if "COUNT" in sql_upper and "GROUP BY" in sql_upper:
        return {
            "id": 1,
            "select_type": "SIMPLE",
            "table": "orders",
            "type": "ALL",
            "possible_keys": None,
            "key": None,
            "rows": 50000,
            "Extra": "Using temporary; Using filesort",  # 临时表 + 文件排序！
        }

    # 默认：性能良好
    return {
        "id": 1,
        "select_type": "SIMPLE",
        "table": "(unknown)",
        "type": "ref",
        "possible_keys": "PRIMARY",
        "key": "PRIMARY",
        "rows": 10,
        "Extra": "Using index",
    }


def extract_table_name(sql: str) -> str | None:
    """从 SQL 中提取表名（简单实现，只处理 SELECT FROM 场景）"""
    sql_upper = sql.upper()
    try:
        # 找 FROM 后面的表名
        idx = sql_upper.index("FROM") + 4
        rest = sql[idx:].strip()

        # 处理别名（FROM orders o 或 FROM orders AS o）
        parts = rest.split()
        table_name = parts[0].strip("`;,'\"")
        return table_name
    except (ValueError, IndexError):
        return None

