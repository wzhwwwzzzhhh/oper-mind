"""降级策略：LLM 不可用时，规则引擎兜底"""

from typing import Callable


class RuleEngine:
    """
    规则引擎：基于关键词匹配的简单诊断。

    当 LLM 不可用时，用规则引擎代替。
    虽然不如 LLM 智能，但能保证核心功能可用。
    这体现了 "fail gracefully" 的工程思维。
    """

    def __init__(self):
        # 注册规则：(条件函数, 回复内容)
        self.rules: list[tuple[Callable[[str], bool], str]] = []
        self._register_default_rules()

    def _register_default_rules(self):
        """注册默认的诊断规则"""

        # 规则1：全表扫描
        self.add_rule(
            lambda sql: "where" in sql.lower() and "status" in sql.lower(),
            "【规则诊断】检测到 status 字段查询。建议添加索引：\n"
            "```sql\nALTER TABLE `orders` ADD INDEX `idx_status` (`status`);\n```\n"
            "添加后 type 将从 ALL（全表扫描）变为 ref（索引查找），"
            "扫描行数从 50000 降至约 8000。"
        )

        # 规则2：排序
        self.add_rule(
            lambda sql: "order by" in sql.lower(),
            "【规则诊断】检测到 ORDER BY 子句。建议添加索引：\n"
            "```sql\nALTER TABLE `orders` ADD INDEX `idx_create_time` (`create_time`);\n```\n"
            "添加后可消除 Using filesort，排序直接在索引上进行。"
        )

        # 规则3：JOIN
        self.add_rule(
            lambda sql: "join" in sql.lower() and "on" in sql.lower(),
            "【规则诊断】检测到 JOIN 操作。请确保被驱动表的关联列有索引：\n"
            "```sql\nALTER TABLE `order_items` ADD INDEX `idx_product_id` (`product_id`);\n```\n"
            "否则 MySQL 需要对被驱动表做全表扫描，影响 JOIN 性能。"
        )

        # 规则4：函数包裹
        self.add_rule(
            lambda sql: "year(" in sql.lower() or "month(" in sql.lower() or "date(" in sql.lower(),
            "【规则诊断】检测到函数包裹索引列（如 YEAR(create_time)）。\n"
            "函数会导致索引失效，建议改为范围查询：\n"
            "```sql\nWHERE create_time >= '2024-01-01' AND create_time < '2025-01-01'\n```"
        )

        # 规则5：COUNT + GROUP BY
        self.add_rule(
            lambda sql: "group by" in sql.lower() and "count" in sql.lower(),
            "【规则诊断】检测到 COUNT + GROUP BY 查询。\n"
            "建议添加复合索引：\n"
            "```sql\nALTER TABLE `orders` ADD INDEX `idx_status_create_time` (`status`, `create_time`);\n```"
        )

    def add_rule(self, condition: Callable[[str], bool], response: str):
        """添加一条规则"""
        self.rules.append((condition, response))

    def match(self, sql: str) -> str | None:
        """
        匹配规则，返回最匹配的诊断结果。
        遍历所有规则，返回第一个匹配的。
        """
        for condition, response in self.rules:
            if condition(sql):
                return response
        return None

    def diagnose(self, sql: str) -> str:
        """
        对 SQL 进行诊断。
        有匹配的规则就返回规则结果，没有就返回通用提示。
        """
        result = self.match(sql)
        if result:
            return result

        return (
            "【规则诊断】未匹配到特定优化规则。\n"
            "建议检查：\n"
            "1. 使用 EXPLAIN 分析执行计划\n"
            "2. 确认大表是否有合适的索引\n"
            "3. 避免 SELECT *，只查询需要的字段"
        )


def analyze_with_fallback(sql: str, llm_available: bool) -> str:
    """
    带降级的诊断入口。

    llm_available: LLM 是否可用
    如果 LLM 不可用，自动降级到规则引擎。
    调用方不需要关心内部逻辑，只需传一个 boolean。
    """
    if llm_available:
        # 走正常 Agent 流程
        return "__USE_AGENT__"

    # LLM 不可用，降级到规则引擎
    engine = RuleEngine()
    return engine.diagnose(sql)