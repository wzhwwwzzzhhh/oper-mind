"""确定性指标 —— 纯读 trace 事件流计算，不需要 LLM。

这些指标只依赖 coordinator.get_trace() 产出的节点序列，因此 mock 模式下
即可完整复现。对应 M2 design §4.1。

核心两个入口：
- detect_strategy(trace)：从 trace 里识别实际路由策略
- compute_deterministic(trace, case)：聚合一条用例的全部确定性指标
"""

import re

from data.eval.schema import EvalCase

# 三种路由策略节点名（与 src/core/graph.py 的节点命名一致）
_STRATEGY_NODES = ("direct", "chain", "parallel")

# 从 direct 节点的 detail 里抠出目标 Agent，如 "目标 Agent=db"
_TARGET_RE = re.compile(r"目标 Agent=(\w+)")


def _node_names(trace: list[dict]) -> list[str]:
    """取出 trace 里的节点名序列"""
    return [e.get("node", "") for e in trace]


def detect_strategy(trace: list[dict]) -> str:
    """从 trace 识别实际路由策略。

    返回首个出现的 direct/chain/parallel 节点名；都没有则返回空串。
    """
    for name in _node_names(trace):
        if name in _STRATEGY_NODES:
            return name
    return ""


def _target_agent(trace: list[dict]) -> str | None:
    """从 direct 节点的 detail 解析目标 Agent 名"""
    for e in trace:
        if e.get("node") == "direct":
            m = _TARGET_RE.search(e.get("detail", ""))
            if m:
                return m.group(1)
    return None


def compute_deterministic(trace: list[dict], case: EvalCase) -> dict:
    """聚合一条用例的确定性指标。

    Args:
        trace: coordinator.get_trace() 的事件流
        case: 对应的评测用例（提供 golden 期望）

    Returns:
        指标字典，键见 design §4.1：
        - actual_strategy: 实际路由策略
        - route_hit: 策略是否命中期望
        - target_hit: direct 模式下目标 Agent 是否命中（非 direct 恒 True）
        - pipeline_complete: 是否经过 report + reflection
        - mechanism_hit: 期望的机制是否触发（expects_debate 时要求 debate 节点）
    """
    names = _node_names(trace)
    actual = detect_strategy(trace)

    route_hit = actual == case.expected_strategy

    # target_hit：仅 direct 模式校验目标 Agent；其余策略不适用，恒 True
    if case.expected_strategy == "direct":
        target_hit = _target_agent(trace) == case.expected_agents[0]
    else:
        target_hit = True

    pipeline_complete = "report" in names and "reflection" in names

    # mechanism_hit：期望辩论则要求 trace 里出现 debate 节点；否则恒 True
    if case.expects_debate:
        mechanism_hit = "debate" in names
    else:
        mechanism_hit = True

    return {
        "actual_strategy": actual,
        "route_hit": route_hit,
        "target_hit": target_hit,
        "pipeline_complete": pipeline_complete,
        "mechanism_hit": mechanism_hit,
    }
