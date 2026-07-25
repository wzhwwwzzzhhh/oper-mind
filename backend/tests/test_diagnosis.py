"""自动化测试：验证 Agent 的诊断能力"""

import json
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.fallback import RuleEngine


def load_test_cases():
    """加载测试用例"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base_dir, "data", "test_cases.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _run_fallback_engine() -> bool:
    """运行规则引擎诊断并返回所有 mock 用例是否通过。"""
    cases = load_test_cases()
    engine = RuleEngine()

    passed = 0
    total = len(cases)

    print("=" * 60)
    print("规则引擎测试报告")
    print("=" * 60)

    for case in cases:
        sql = case["sql"]
        category = case["category"]

        result = engine.diagnose(sql)
        has_diagnosis = len(result) > 20
        is_pass = has_diagnosis

        status = "✅" if is_pass else "❌"
        print(f"\n{status} [{category}] {sql[:60]}...")
        print(f"   诊断结果: {'有输出' if has_diagnosis else '无输出'}")

        if is_pass:
            passed += 1

    print(f"\n{'=' * 60}")
    print(f"总计: {total} | 通过: {passed} | 失败: {total - passed}")
    print(f"通过率: {passed / total * 100:.1f}%")
    print(f"{'=' * 60}")

    return passed == total



def test_fallback_engine() -> None:
    """验证规则引擎能为所有 mock 用例产生诊断结论。"""
    assert _run_fallback_engine()

if __name__ == "__main__":
    success = _run_fallback_engine()
    sys.exit(0 if success else 1)
