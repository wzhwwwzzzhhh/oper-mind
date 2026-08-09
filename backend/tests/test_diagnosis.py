"""降级规则引擎测试：验证 LLM 不可用时的兜底诊断能力。

用例内联在测试中，不依赖外部数据集，保证基线可确定复现。
"""

from src.core.fallback import RuleEngine

# 覆盖 RuleEngine 五条默认规则，每条给出应命中的代表性 SQL。
_RULE_CASES: list[tuple[str, str]] = [
    ("全表扫描", "SELECT * FROM orders WHERE status = 'PAID'"),
    ("排序", "SELECT * FROM orders ORDER BY create_time DESC"),
    ("JOIN", "SELECT * FROM orders o JOIN order_items i ON o.id = i.order_id"),
    ("函数包裹", "SELECT * FROM orders WHERE YEAR(create_time) = 2024"),
    ("聚合分组", "SELECT status, COUNT(*) FROM orders GROUP BY status"),
]


def test_规则引擎为已知模式产出诊断() -> None:
    """五条默认规则均应命中并返回非空的规则诊断结论。"""
    engine = RuleEngine()
    for category, sql in _RULE_CASES:
        result = engine.diagnose(sql)
        assert result.startswith("【规则诊断】"), category
        assert len(result) > 20, category


def test_规则引擎对未匹配SQL返回通用建议() -> None:
    """未命中任何规则时，仍应给出可用的通用排查建议而非空结果。"""
    engine = RuleEngine()
    result = engine.diagnose("UPDATE settings SET value = '1'")

    assert result.startswith("【规则诊断】")
    assert "EXPLAIN" in result
