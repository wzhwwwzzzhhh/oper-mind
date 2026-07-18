"""stats 模块单测 —— 均值/标准差/CI 与 Wilcoxon/Friedman 检验。

纯函数测试，不需要 LLM。运行：python tests/test_stats.py
"""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pytest

from src.eval.stats import describe, compare_two, compare_many, load_metric


def test_describe_基本统计量():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    d = describe(values)
    assert d["n"] == 5
    assert d["mean"] == pytest.approx(3.0)
    assert d["std"] == pytest.approx(1.5811, abs=1e-3)
    assert d["ci_low"] < d["mean"] < d["ci_high"]
    assert isinstance(d["ci_low"], float)
    assert isinstance(d["ci_high"], float)


def test_describe_单样本CI不崩():
    d = describe([2.0])
    assert d["n"] == 1
    assert d["mean"] == 2.0
    assert d["ci_low"] == d["ci_high"] == 2.0


def test_compare_two_几乎一样不显著():
    a = [0.8, 0.81, 0.79, 0.80, 0.82, 0.78, 0.80, 0.81]
    b = [0.80, 0.80, 0.80, 0.79, 0.81, 0.80, 0.79, 0.80]
    r = compare_two(a, b)
    assert r["p_value"] > 0.05


def test_compare_two_明显不同显著():
    a = [0.9, 0.92, 0.88, 0.91, 0.89, 0.93, 0.90, 0.91]
    b = [0.3, 0.32, 0.28, 0.31, 0.29, 0.33, 0.30, 0.31]
    r = compare_two(a, b)
    assert r["p_value"] < 0.05


def test_compare_two_长度不等抛异常():
    with pytest.raises(ValueError):
        compare_two([1.0, 2.0], [1.0])


def test_compare_many_三组检验():
    a = [0.9, 0.85, 0.88, 0.91, 0.87, 0.90, 0.86, 0.89]
    b = [0.5, 0.45, 0.48, 0.51, 0.47, 0.50, 0.46, 0.49]
    c = [0.2, 0.15, 0.18, 0.21, 0.17, 0.20, 0.16, 0.19]
    r = compare_many(a, b, c)
    assert r["p_value"] < 0.05


def test_load_metric_按case_id取值(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    lines = [
        {"case_id": "c1", "root_cause_score": 0.8},
        {"case_id": "c2", "root_cause_score": 0.6},
    ]
    cases_path.write_text(
        "\n".join(json.dumps(line, ensure_ascii=False) for line in lines),
        encoding="utf-8",
    )
    result = load_metric(str(cases_path), "root_cause_score")
    assert result == {"c1": 0.8, "c2": 0.6}


def _run():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for t in tests:
        if "tmp_path" in t.__code__.co_varnames[: t.__code__.co_argcount]:
            continue  # 需要 pytest fixture，跳过独立运行模式
        t()
        print(f"  PASS {t.__name__}")
    print(f"\n✅ stats 单测全部通过（{len(tests)} 个，不含需要 fixture 的用例）")


if __name__ == "__main__":
    _run()
