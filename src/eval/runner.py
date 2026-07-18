"""评测 Runner —— 跑用例集过 coordinator，串联确定性指标 + judge，逐条落结果。

只依赖 coordinator 的两个公开接口：route(query) -> str、get_trace() -> list[dict]
（见 src/core/coordinator.py），不关心其内部实现，因此可用假 coordinator 隔离测试。

设计见 docs/开发/M2-评测Harness/design.md 第 4.3 节。
"""

from typing import Any

from data.eval.schema import EvalCase
from src.eval.metrics import compute_deterministic
from src.eval.judge import judge_report


def run_case(coordinator: Any, judge_llm: Any, case: EvalCase) -> dict:
    """跑单条用例：驱动 coordinator，计算确定性指标 + judge 打分。

    coordinator.route() 抛异常不向上传播：记录 error 字段，
    trace 退化为 get_trace() 当前值（通常为空列表），report 置空。
    """
    error: str | None = None
    try:
        report = coordinator.route(case.query)
    except Exception as e:
        report = ""
        error = f"{type(e).__name__}: {e}"

    trace = coordinator.get_trace()
    deterministic = compute_deterministic(trace, case)
    judge = judge_report(judge_llm, report, case)

    result: dict = {
        "case_id": case.case_id,
        "report": report,
        "deterministic": deterministic,
        "judge": judge,
    }
    if error is not None:
        result["error"] = error
    return result


def run_suite(coordinator: Any, judge_llm: Any, cases: list[EvalCase]) -> list[dict]:
    """遍历整套用例。单条崩溃已在 run_case 内部捕获，不影响后续用例。"""
    return [run_case(coordinator, judge_llm, case) for case in cases]
