""""数据库诊断相关的Tool"""

import json
from unittest import result

from src.core.tool_registry import Tool

class ExplainTool(Tool):
    """执行EXPLAIN分析SQL"""

    def __init__(self):
        super().__init__(
            name="explain_sql",
            description="执行EXPLAIN分析SQL 的执行计划，返回访问类型、扫描行数、索引使用情况",
            parameters={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "要分析的SQL 语句，如 SELECT *FROM orders WHEREid= 1"
                    }
                },
                "required": ["sql"]
            }
        )

    def execute(self, sql: str) -> str:
        """执行EXPLAIN分析SQL 并返回格式化的结果"""
        from data.mock_db import explain_sql,extract_table_name

        plan = explain_sql(sql)
        table_name = extract_table_name(sql)

        result = f"EXPLAIN {table_name or '(unknown)'}:\n"
        result += f" 查询类型：{plan['select_type']}\n"
        result += f" 访问类型：{plan['type']}\n"
        result += f" 可能索引：{plan['possible_keys']}\n"
        result += f" 实际索引：{plan['key']}\n"
        result += f" 扫描行数：{plan['rows']}\n"
        result += f" 额外信息：{plan['Extra']}\n"

        # 附带简要解读
        warnings = []
        if plan["type"] == "ALL":
            warnings.append("⚠️ 全表扫描，性能风险高")
        if plan["Extra"] and "filesort" in plan["Extra"].lower():
            warnings.append("⚠️ 文件排序，数据量大时性能差")
        if plan["key"] is None and plan["possible_keys"]:
            warnings.append(f"⚠️ 有可用索引但没使用，可能是函数包裹或类型转换导致")
        if warnings:
            result += "\n" + "\n".join(warnings)

        return result

class ShowIndexTool(Tool):
    """查询表的索引信息"""

    def __init__(self):
        super().__init__(
            name="show_index",
            description="查询指定表的索引信息，返回索引名称、列名、唯一性、基数等",
            parameters={
                "type": "object",
                "properties": {
                    "table": {
                        "type": "string",
                        "description": "表名，如 orders、order_items",
                    }
                },
                "required": ["table"],
            },
        )

    def execute(self, table: str) -> str:
        """返回指定表的索引信息"""
        from data.mock_db import get_indexes

        indexes = get_indexes(table)
        if indexes is None:
            return f"表 '{table}' 不存在或没有索引信息"

        result = f"表 {table} 的索引:\n"
        result += f"{'索引名':<20} {'列名':<15} {'顺序':>5} {'非唯一':>8} {'基数':>10}\n"
        result += "-" * 60 + "\n"
        for index in indexes:
            result += f"{index['Key_name']:<20} {index['Column_name']:<15} {index['Seq_in_index']:>5} {index['Non_unique']:>8} {index['Cardinality']:>10}\n"

        return result

class ShowCreateTableTool(Tool):
    """查询表的创建语句"""

    def __init__(self):
        super().__init__(
            name="show_create_table",
            description="查看表的建表语句，包含字段定义、索引、引擎等信息",
            parameters={
                "type": "object",
                "properties": {
                    "table": {
                        "type": "string",
                        "description": "表名，如 orders、order_items",
                    }
                },
                "required": ["table"],
            },
        )

    def execute(self, table: str) -> str:
        """返回指定表的建表语句"""
        from data.mock_db import get_create_table

        result = get_create_table(table)
        if result is None:
            return f"表 '{table}' 不存在"

        return result


