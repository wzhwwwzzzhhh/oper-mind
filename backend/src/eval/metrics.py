"""确定性评测指标 —— 纯读 trace 事件流，不调用 LLM。"""

import re

from data.eval.schema import EvalCase
from src.core.experiment import ExperimentCondition, get_experiment_condition


_STRATEGY_NODES = ("direct", "chain", "parallel")
_TARGET_RE = re.compile(r"目标 Agent=(\w+)")


def _node_names(trace: list[dict]) -> list[str]:
    """返回 trace 中的节点名序列。"""
    return [event.get("node", "") for event in trace]


def detect_strategy(trace: list[dict]) -> str:
    """返回 trace 中首个 direct、chain 或 parallel 节点。"""
    for name in _node_names(trace):
        if name in _STRATEGY_NODES:
            return name
    return ""


def _target_agent(trace: list[dict]) -> str | None:
    """从 direct 节点详情解析实际目标 Agent。"""
    for event in trace:
        if event.get("node") == "direct":
            matched = _TARGET_RE.search(event.get("detail", ""))
            if matched:
                return matched.group(1)
    return None


def _condition_complete(names: list[str], condition: ExperimentCondition) -> bool:
    """按实验条件判断链路是否完成。"""
    if condition.arm == "no_reflection":
        return "report" in names
    if condition.arm == "single_agent":
        return all(node in names for node in ("direct", "report", "reflection"))
    return "report" in names and "reflection" in names


def compute_deterministic(
    trace: list[dict],
    case: EvalCase,
    condition: ExperimentCondition | None = None,
) -> dict:
    """聚合单条用例的路由、机制与按实验条件解释的完成率。"""
    active_condition = condition or get_experiment_condition("full")
    names = _node_names(trace)
    actual_strategy = detect_strategy(trace)

    route_hit = actual_strategy == case.expected_strategy
    if case.expected_strategy == "direct":
        target_hit = _target_agent(trace) == case.expected_agents[0]
    else:
        target_hit = True

    pipeline_complete = "report" in names and "reflection" in names
    if case.expects_debate:
        mechanism_hit = "debate" in names
    else:
        mechanism_hit = True

    return {
        "actual_strategy": actual_strategy,
        "route_hit": route_hit,
        "target_hit": target_hit,
        "pipeline_complete": pipeline_complete,
        "mechanism_hit": mechanism_hit,
        "condition_complete": _condition_complete(names, active_condition),
    }
