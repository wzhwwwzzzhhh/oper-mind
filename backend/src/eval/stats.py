"""实验统计工具 —— 均值/标准差/95% CI 与 Wilcoxon/Friedman 检验。

纯函数，不读文件（除 load_metric）、不产副作用、不引入随机源
（CI 用 t 分布参数法，不用 bootstrap 重采样，见 M3 design.md §3.2）。
"""

import json

import numpy as np
from scipy import stats as scipy_stats


def describe(values: list[float]) -> dict:
    """返回 {mean, std, n, ci_low, ci_high}。

    CI 用 t 分布参数法：mean ± t_(0.975, df) * SE。
    n<2 时标准误无定义，CI 退化为 (mean, mean)。
    """
    arr = np.asarray(values, dtype=float)
    n = len(arr)
    mean = float(np.mean(arr))
    if n < 2:
        return {"n": n, "mean": mean, "std": 0.0, "ci_low": mean, "ci_high": mean}
    std = float(np.std(arr, ddof=1))
    se = std / np.sqrt(n)
    t_critical = scipy_stats.t.ppf(0.975, df=n - 1)
    margin = t_critical * se
    return {
        "n": n,
        "mean": mean,
        "std": std,
        "ci_low": mean - margin,
        "ci_high": mean + margin,
    }


def compare_two(a: list[float], b: list[float]) -> dict:
    """Wilcoxon 符号秩检验（配对），返回 {statistic, p_value}。

    要求 len(a) == len(b)（同一批用例的两种配置结果，按 case_id 对齐后传入）。
    """
    if len(a) != len(b):
        raise ValueError(f"配对检验要求两组长度相等，实际 len(a)={len(a)}, len(b)={len(b)}")
    statistic, p_value = scipy_stats.wilcoxon(a, b)
    return {"statistic": float(statistic), "p_value": float(p_value)}


def compare_many(*groups: list[float]) -> dict:
    """Friedman 检验（>=3 个配对条件），返回 {statistic, p_value}。"""
    statistic, p_value = scipy_stats.friedmanchisquare(*groups)
    return {"statistic": float(statistic), "p_value": float(p_value)}


def load_metric(cases_path: str, metric: str) -> dict[str, float]:
    """读 cases.jsonl（CaseResult 的 JSON Lines），返回 {case_id: metric_value}。"""
    result: dict[str, float] = {}
    with open(cases_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            result[record["case_id"]] = record[metric]
    return result
