"""评测 Runner —— 驱动 Coordinator、计时并串联确定性指标与 Judge。"""

import time
from typing import Any

from data.eval.schema import EvalCase
from src.core.experiment import get_experiment_condition
from src.eval.judge import judge_report
from src.eval.metrics import compute_deterministic


def run_case(coordinator: Any, judge_llm: Any, case: EvalCase) -> dict:
    """运行单条用例，返回报告、指标、评分和端到端延迟。"""
    started = time.perf_counter()
    error: str | None = None
    try:
        report = coordinator.route(case.query)
    except Exception as error_instance:
        report = ""
        error = f"{type(error_instance).__name__}: {error_instance}"

    trace = coordinator.get_trace()
    condition = getattr(coordinator, "experiment_condition", get_experiment_condition("full"))
    deterministic = compute_deterministic(trace, case, condition)
    judge = judge_report(judge_llm, report, case)
    latency_ms = (time.perf_counter() - started) * 1000

    result: dict = {
        "case_id": case.case_id,
        "report": report,
        "deterministic": deterministic,
        "judge": judge,
        "latency_ms": latency_ms,
    }
    if error is not None:
        result["error"] = error
    return result


def run_suite(coordinator: Any, judge_llm: Any, cases: list[EvalCase]) -> list[dict]:
    """顺序运行整套用例；单条 Coordinator 异常不影响后续用例。"""
    results: list[dict] = []
    for case in cases:
        reset = getattr(coordinator, "reset_for_evaluation", None)
        if callable(reset):
            reset()
        results.append(run_case(coordinator, judge_llm, case))
    return results
