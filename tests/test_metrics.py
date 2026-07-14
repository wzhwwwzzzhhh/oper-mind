"""确定性指标单测 —— 喂造好的 trace，断言 metrics 计算正确。

纯函数测试，不需要 LLM。运行：python tests/test_metrics.py
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from data.eval.schema import EvalCase
from src.eval.metrics import detect_strategy, compute_deterministic


def _case(**overrides) -> EvalCase:
    """构造一条最小合法用例，允许覆盖字段。"""
    base = dict(
        case_id="t-001",
        query="测试",
        domain="db",
        expected_strategy="direct",
        expected_agents=["db"],
        difficulty="easy",
        golden_root_cause="根因",
        golden_key_points=["点1"],
        expects_debate=False,
        source="synthetic",
    )
    base.update(overrides)
    return EvalCase(**base)


def test_detect_strategy():
    assert detect_strategy([{"node": "route"}, {"node": "direct"}]) == "direct"
    assert detect_strategy([{"node": "route"}, {"node": "chain"}]) == "chain"
    assert detect_strategy([{"node": "route"}, {"node": "parallel"}]) == "parallel"
    assert detect_strategy([{"node": "route"}]) == ""


def test_direct_route_hit_and_target():
    case = _case(expected_strategy="direct", expected_agents=["db"])
    trace = [
        {"node": "route", "detail": "兜底关键词路由 → direct"},
        {"node": "direct", "detail": "目标 Agent=db"},
        {"node": "report", "detail": "生成初稿"},
        {"node": "reflection", "detail": "复审通过"},
    ]
    m = compute_deterministic(trace, case)
    assert m["actual_strategy"] == "direct"
    assert m["route_hit"] is True
    assert m["target_hit"] is True
    assert m["pipeline_complete"] is True
    assert m["mechanism_hit"] is True


def test_direct_target_miss():
    case = _case(expected_strategy="direct", expected_agents=["server"])
    trace = [
        {"node": "direct", "detail": "目标 Agent=db"},
        {"node": "report"},
        {"node": "reflection"},
    ]
    m = compute_deterministic(trace, case)
    assert m["route_hit"] is True          # 都是 direct
    assert m["target_hit"] is False        # 期望 server，实际 db


def test_route_miss():
    case = _case(expected_strategy="direct", expected_agents=["db"])
    trace = [{"node": "chain"}, {"node": "report"}, {"node": "reflection"}]
    m = compute_deterministic(trace, case)
    assert m["actual_strategy"] == "chain"
    assert m["route_hit"] is False


def test_debate_mechanism():
    # 期望 debate 但没触发 → mechanism_hit False
    case = _case(
        expected_strategy="parallel",
        expected_agents=["db", "server", "log"],
        expects_debate=True,
    )
    trace_no_debate = [
        {"node": "parallel"},
        {"node": "conflict_check"},
        {"node": "report"},
        {"node": "reflection"},
    ]
    assert compute_deterministic(trace_no_debate, case)["mechanism_hit"] is False

    trace_with_debate = trace_no_debate[:2] + [{"node": "debate"}] + trace_no_debate[2:]
    assert compute_deterministic(trace_with_debate, case)["mechanism_hit"] is True


def test_pipeline_incomplete():
    case = _case()
    trace = [{"node": "direct"}, {"node": "report"}]   # 缺 reflection
    assert compute_deterministic(trace, case)["pipeline_complete"] is False


def _run():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  PASS {t.__name__}")
    print(f"\n✅ metrics 单测全部通过（{len(tests)} 个）")


if __name__ == "__main__":
    _run()
