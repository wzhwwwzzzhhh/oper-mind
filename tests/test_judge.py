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
        self.client = type("Client", (), {"api_key": "test-real-key"})()

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


def test_mock_stub_多词元关键点过半即命中():
    # 方案A：关键点按空白切词，过半词元出现即命中；旧版整句精确匹配会漏判此例
    case = _case(golden_key_points=["orders.status 无索引"])
    report = "分析发现 orders.status 上没有建立索引，属于无索引场景"
    result = judge_report(_FakeMockLLM(), report, case)
    assert result["key_points_hit"] == ["orders.status 无索引"]
    assert result["key_points_recall"] == 1.0


def test_mock_stub_词元不足半数不算命中():
    # 4 个词元只命中 1 个（type=ALL），低于 0.5 阈值 → 不记命中
    case = _case(golden_key_points=["type=ALL 全表扫描 需要 加索引"])
    report = "报告里只提到 type=ALL"
    result = judge_report(_FakeMockLLM(), report, case)
    assert result["key_points_hit"] == []
    assert result["key_points_recall"] == 0.0


# ===== 真 LLM 路径 =====

def test_real_llm_解析关键点ID打分():
    case = _case(golden_root_cause="索引缺失", golden_key_points=["全表扫描", "缺少索引"])
    llm = _FakeRealLLM('{"root_cause_score": 0.8, "key_point_ids": ["KP1"]}')
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


def test_real_llm_关键点ID过滤非法与重复项():
    case = _case(golden_key_points=["点1", "点2"])
    llm = _FakeRealLLM(
        '{"root_cause_score": 0.5, "key_point_ids": ["KP1", "KP1", "KP99", "foo", "KP2"]}'
    )
    result = judge_report(llm, "某份报告", case)
    assert result["key_points_hit"] == ["点1", "点2"]
    assert result["key_points_recall"] == 1.0


def test_real_llm_关键点ID缺失或非列表按空处理():
    case = _case(golden_key_points=["点1", "点2"])
    llm = _FakeRealLLM('{"root_cause_score": 0.5, "key_point_ids": "KP1"}')
    result = judge_report(llm, "某份报告", case)
    assert result["key_points_hit"] == []
    assert result["key_points_recall"] == 0.0


@pytest.mark.parametrize(
    ("raw_score", "expected_score"),
    [(1.5, 1.0), (-0.2, 0.0), ("bad", 0.0)],
)
def test_real_llm_根因分数归一化(raw_score, expected_score):
    case = _case(golden_key_points=["点1"])
    json_score = repr(raw_score).replace("'", '"')
    llm = _FakeRealLLM(
        '{"root_cause_score": ' + json_score + ', "key_point_ids": []}'
    )
    result = judge_report(llm, "某份报告", case)
    assert result["root_cause_score"] == expected_score
