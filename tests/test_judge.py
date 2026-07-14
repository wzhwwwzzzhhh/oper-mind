"""LM-as-judge 单测 —— mock stub（关键词重合度，确定性）与真 LLM 路径（解析 JSON 打分）。

对应 M2 design §4.2。mock stub 不调 LLM，只做确定性关键词重合度评分，
保证 mock 模式下 judge 环节可跑通（管道冒烟）；真 LLM 路径解析裁判返回的 JSON 打分。
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from data.eval.schema import EvalCase
from src.eval.judge import judge_report


def _case(**kw) -> EvalCase:
    base = dict(
        case_id="test-001",
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
    base.update(kw)
    return EvalCase(**base)


class _FakeMockLLM:
    """模拟 api_key == 'mock' 的 LLMClient"""

    class client:
        api_key = "mock"


class _FakeRealLLM:
    """模拟真实 LLMClient，chat() 返回预设内容"""

    def __init__(self, content: str):
        self._content = content
        self.client = type("Client", (), {"api_key": "sk-real-key"})()

    def chat(self, messages, temperature=0.0):
        return {"role": "assistant", "content": self._content}


# ===== mock stub 路径 =====

def test_mock_stub_返回合法范围():
    case = _case(golden_root_cause="索引缺失", golden_key_points=["全表扫描", "缺少索引"])
    result = judge_report(_FakeMockLLM(), "毫不相关的报告内容", case)
    assert result["method"] == "mock_stub"
    assert 0.0 <= result["root_cause_score"] <= 1.0
    assert 0.0 <= result["key_points_recall"] <= 1.0


def test_mock_stub_全部命中():
    case = _case(golden_key_points=["全表扫描", "缺少索引"])
    report = "该查询存在全表扫描问题，且缺少索引，建议优化"
    result = judge_report(_FakeMockLLM(), report, case)
    assert result["key_points_recall"] == 1.0
    assert set(result["key_points_hit"]) == {"全表扫描", "缺少索引"}


def test_mock_stub_部分命中():
    case = _case(golden_key_points=["全表扫描", "缺少索引", "建议加索引"])
    report = "该查询存在全表扫描问题"
    result = judge_report(_FakeMockLLM(), report, case)
    assert result["key_points_recall"] == pytest.approx(1 / 3)
    assert result["key_points_hit"] == ["全表扫描"]


def test_mock_stub_root_cause_关键词重合():
    case = _case(golden_root_cause="status 字段缺少索引导致全表扫描")
    hit_report = "问题根因：status 字段缺少索引导致全表扫描"
    miss_report = "完全不相关的内容"
    hit = judge_report(_FakeMockLLM(), hit_report, case)
    miss = judge_report(_FakeMockLLM(), miss_report, case)
    assert hit["root_cause_score"] > miss["root_cause_score"]


# ===== 真 LLM 路径 =====

def test_real_llm_解析JSON打分():
    case = _case(golden_root_cause="索引缺失", golden_key_points=["全表扫描", "缺少索引"])
    llm = _FakeRealLLM('{"root_cause_score": 0.8, "key_points_hit": ["全表扫描"]}')
    result = judge_report(llm, "某份报告", case)
    assert result["method"] == "llm_judge"
    assert result["root_cause_score"] == 0.8
    assert result["key_points_recall"] == pytest.approx(0.5)
    assert result["key_points_hit"] == ["全表扫描"]


def test_real_llm_JSON解析失败兜底为0分():
    case = _case(golden_key_points=["点1", "点2"])
    llm = _FakeRealLLM("裁判返回了不是 JSON 的文本")
    result = judge_report(llm, "某份报告", case)
    assert result["method"] == "llm_judge"
    assert result["root_cause_score"] == 0.0
    assert result["key_points_recall"] == 0.0
    assert result["key_points_hit"] == []


def test_real_llm_hit列表过滤非法项():
    case = _case(golden_key_points=["点1", "点2"])
    llm = _FakeRealLLM('{"root_cause_score": 0.5, "key_points_hit": ["点1", "不存在的点"]}')
    result = judge_report(llm, "某份报告", case)
    # 只认可 golden_key_points 里真实存在的项，防止 LLM 幻觉出不存在的点
    assert result["key_points_hit"] == ["点1"]
    assert result["key_points_recall"] == pytest.approx(0.5)
