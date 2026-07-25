"""LLM-as-judge —— 对照 golden 答案为诊断报告打分。"""

import re
from typing import Any

from src.core.graph import _extract_json


# stub 词元命中阈值：关键点按空白/标点切词后，过半词元出现即记为命中。
_STUB_HIT_RATIO = 0.5


def _tokenize(text: str) -> list[str]:
    """按空白与常见中英文标点切分为词元（供 stub 粗粒度重合度用，非质量信号）。"""
    return [tok for tok in re.split(r"[\s，。、；：,.;:]+", text) if tok]


def _is_mock(llm: Any) -> bool:
    """判断裁判客户端是否处于 mock 模式。"""
    return getattr(getattr(llm, "client", None), "api_key", None) == "mock"


def _mock_stub_judge(report: str, case: Any) -> dict[str, Any]:
    """mock 模式下的确定性占位打分。

    ⚠️ 本 stub 仅用于管道联通与冒烟回归，**分数不是质量信号**：mock 报告是
    模板化文本，不会复现 golden 的具体措辞。任何质量结论都以真实 LLM 裁判
    （见 _llm_judge）为准。这里用「词元级重合」替代早期的「整句精确子串匹配」，
    仅为让冒烟数字可读、避免 0.0 假信号（历史上 mean_key_points_recall≈0.015
    即该假信号所致），不代表诊断质量。
    """
    # 根因分数：golden 根因的词元在报告中出现的比例
    root_cause_tokens = _tokenize(case.golden_root_cause)
    if root_cause_tokens:
        root_hit = sum(1 for tok in root_cause_tokens if tok in report)
        root_cause_score = root_hit / len(root_cause_tokens)
    else:
        root_cause_score = 0.0

    # 关键点命中：某关键点的词元过半出现在报告中即记为命中
    key_points_hit: list[str] = []
    for point in case.golden_key_points:
        tokens = _tokenize(point)
        if not tokens:
            continue
        hit_ratio = sum(1 for tok in tokens if tok in report) / len(tokens)
        if hit_ratio >= _STUB_HIT_RATIO:
            key_points_hit.append(point)
    total = len(case.golden_key_points)
    key_points_recall = len(key_points_hit) / total if total else 0.0

    return {
        "method": "mock_stub",
        "root_cause_score": root_cause_score,
        "key_points_recall": key_points_recall,
        "key_points_hit": key_points_hit,
    }


def _format_key_points(case: Any) -> str:
    """将 golden 关键点格式化为稳定编号，供真实裁判选择。"""
    return "\n".join(
        f"KP{index}: {point}"
        for index, point in enumerate(case.golden_key_points, start=1)
    )


def _normalize_score(raw_score: Any) -> float:
    """将裁判根因分数安全转换并裁剪到 0 到 1 之间。"""
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))


def _resolve_key_point_ids(raw_ids: Any, golden_key_points: list[str]) -> list[str]:
    """过滤、去重裁判返回的 ID，并映射回 golden 原文关键点。"""
    if not isinstance(raw_ids, list):
        return []

    id_to_point = {
        f"KP{index}": point
        for index, point in enumerate(golden_key_points, start=1)
    }
    seen_ids: set[str] = set()
    key_points_hit: list[str] = []

    for raw_id in raw_ids:
        if not isinstance(raw_id, str):
            continue
        key_point_id = raw_id.strip().upper()
        if key_point_id not in id_to_point or key_point_id in seen_ids:
            continue
        seen_ids.add(key_point_id)
        key_points_hit.append(id_to_point[key_point_id])

    return key_points_hit


def _empty_judge_result() -> dict[str, Any]:
    """返回真实裁判解析或调用失败时的稳定零分结果。"""
    return {
        "method": "llm_judge",
        "root_cause_score": 0.0,
        "key_points_recall": 0.0,
        "key_points_hit": [],
    }


def _llm_judge(llm: Any, report: str, case: Any) -> dict[str, Any]:
    """调用真实裁判，并将关键点 ID 映射为既有输出字段。"""
    points = _format_key_points(case)
    prompt = f"""你是运维诊断报告的评分裁判。请对照 golden 答案给待评报告打分。

golden 根因：{case.golden_root_cause}
golden 关键结论点：
{points}

待评报告：
{report}

请只返回 JSON，不要解释，格式：
{{"root_cause_score": 0.0到1.0之间的分数（报告是否命中根因）, "key_point_ids": ["KP1", "KP3"]}}
key_point_ids 只能填写上方列出的 KP 编号；未命中时返回空列表。"""

    response = llm.chat([{"role": "user", "content": prompt}], temperature=0.0)
    parsed = _extract_json(response.get("content", "")) if "error" not in response else None
    if not parsed:
        return _empty_judge_result()

    key_points_hit = _resolve_key_point_ids(
        parsed.get("key_point_ids"),
        case.golden_key_points,
    )
    return {
        "method": "llm_judge",
        "root_cause_score": _normalize_score(parsed.get("root_cause_score")),
        "key_points_recall": len(key_points_hit) / len(case.golden_key_points),
        "key_points_hit": key_points_hit,
    }


def judge_report(llm: Any, report: str, case: Any) -> dict[str, Any]:
    """对照 golden 答案评分；mock 走 stub，真实模型走关键点 ID 裁判。"""
    if _is_mock(llm):
        return _mock_stub_judge(report, case)
    return _llm_judge(llm, report, case)
