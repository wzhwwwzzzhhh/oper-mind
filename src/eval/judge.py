"""LM-as-judge —— 对照 golden 给报告打分。

两条路径（对应 M2 design §4.2）：
- mock_stub：api_key=="mock" 时不调 LLM，用确定性关键词重合度评分，
  保证 mock 模式下 judge 环节可跑通（管道冒烟，可复现）。
- llm_judge：真实 LLM 场景下，让裁判模型输出 JSON 打分并解析；
  解析失败兜底为 0 分；key_points_hit 只认可 golden_key_points 里
  真实存在的项，防止 LLM 幻觉出不存在的点。
"""

from src.core.graph import _extract_json


def _is_mock(llm) -> bool:
    """是否处于 mock 模式（api_key=='mock'）"""
    return getattr(getattr(llm, "client", None), "api_key", None) == "mock"


def _mock_stub_judge(report: str, case) -> dict:
    """确定性关键词重合度评分，不调 LLM。"""
    root_cause_words = set(case.golden_root_cause)
    report_words = set(report)
    overlap = root_cause_words & report_words
    root_cause_score = len(overlap) / len(root_cause_words) if root_cause_words else 0.0

    key_points_hit = [p for p in case.golden_key_points if p in report]
    key_points_recall = len(key_points_hit) / len(case.golden_key_points)

    return {
        "method": "mock_stub",
        "root_cause_score": root_cause_score,
        "key_points_recall": key_points_recall,
        "key_points_hit": key_points_hit,
    }


def _llm_judge(llm, report: str, case) -> dict:
    """真实 LLM 裁判：输出 JSON 打分，解析失败兜底为 0 分。"""
    points = "\n".join(f"- {p}" for p in case.golden_key_points)
    prompt = f"""你是运维诊断报告的评分裁判。请对照 golden 答案给待评报告打分。

golden 根因：{case.golden_root_cause}
golden 关键结论点：
{points}

待评报告：
{report}

请只返回 JSON，不要解释，格式：
{{"root_cause_score": 0.0到1.0之间的分数（报告是否命中根因）, "key_points_hit": [报告中命中的关键点原文列表]}}"""

    resp = llm.chat([{"role": "user", "content": prompt}], temperature=0.0)
    parsed = _extract_json(resp.get("content", "")) if "error" not in resp else None

    if not parsed:
        return {
            "method": "llm_judge",
            "root_cause_score": 0.0,
            "key_points_recall": 0.0,
            "key_points_hit": [],
        }

    root_cause_score = float(parsed.get("root_cause_score", 0.0))
    # 只认可 golden_key_points 里真实存在的项，防止 LLM 幻觉出不存在的点
    raw_hit = parsed.get("key_points_hit", []) or []
    key_points_hit = [p for p in raw_hit if p in case.golden_key_points]
    key_points_recall = len(key_points_hit) / len(case.golden_key_points)

    return {
        "method": "llm_judge",
        "root_cause_score": root_cause_score,
        "key_points_recall": key_points_recall,
        "key_points_hit": key_points_hit,
    }


def judge_report(llm, report: str, case) -> dict:
    """对照 golden 给报告打分，mock 模式走确定性 stub，真实模式走 LLM 裁判。

    Returns:
        {"method": "mock_stub"|"llm_judge", "root_cause_score": float,
         "key_points_recall": float, "key_points_hit": list[str]}
    """
    if _is_mock(llm):
        return _mock_stub_judge(report, case)
    return _llm_judge(llm, report, case)
