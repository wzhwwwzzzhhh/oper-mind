"""评测 Runner 单测 —— 跑用例集过 coordinator，串联确定性指标 + judge，逐条落结果。

对应 M2 design §4.3。runner 不关心 coordinator 内部实现，只依赖其
route(query) -> str 与 get_trace() -> list[dict] 两个公开接口（见
src/core/coordinator.py），因此可用一个假 coordinator 隔离测试。
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.eval.schema import EvalCase
from src.eval.runner import run_case, run_suite


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


class _FakeCoordinator:
    """假 coordinator：route() 返回预设报告，get_trace() 返回预设 trace。"""

    def __init__(self, report: str, trace: list[dict]):
        self._report = report
        self._trace = trace
        self.received_queries: list[str] = []

    def route(self, query: str) -> str:
        self.received_queries.append(query)
        return self._report

    def get_trace(self) -> list[dict]:
        return self._trace


class _FakeMockLLM:
    """模拟 api_key == 'mock' 的 LLMClient，驱动 judge 走 mock stub 路径。"""

    class client:
        api_key = "mock"


# ===== run_case =====

def test_run_case_返回结构():
    case = _case(golden_root_cause="索引缺失", golden_key_points=["全表扫描"])
    trace = [
        {"node": "route", "detail": ""},
        {"node": "direct", "detail": "目标 Agent=db"},
        {"node": "report", "detail": ""},
        {"node": "reflection", "detail": ""},
    ]
    coordinator = _FakeCoordinator("报告：存在全表扫描问题", trace)
    llm = _FakeMockLLM()

    result = run_case(coordinator, llm, case)

    assert result["case_id"] == "test-001"
    assert result["report"] == "报告：存在全表扫描问题"
    assert result["deterministic"]["route_hit"] is True
    assert result["deterministic"]["target_hit"] is True
    assert result["judge"]["method"] == "mock_stub"
    assert result["judge"]["key_points_recall"] == 1.0


def test_run_case_把query传给coordinator():
    case = _case(query="这条 SQL 很慢")
    coordinator = _FakeCoordinator("报告", [{"node": "direct"}, {"node": "report"}, {"node": "reflection"}])
    run_case(coordinator, _FakeMockLLM(), case)
    assert coordinator.received_queries == ["这条 SQL 很慢"]


def test_run_case_异常不中断_返回error字段():
    case = _case()

    class _BoomCoordinator:
        def route(self, query):
            raise RuntimeError("模拟运行时崩溃")

        def get_trace(self):
            return []

    result = run_case(_BoomCoordinator(), _FakeMockLLM(), case)
    assert result["case_id"] == "test-001"
    assert "error" in result
    assert result["deterministic"]["route_hit"] is False
    assert result["judge"]["method"] == "mock_stub"


# ===== run_suite =====

def test_run_suite_遍历全部用例():
    cases = [_case(case_id="a"), _case(case_id="b"), _case(case_id="c")]
    trace = [{"node": "direct"}, {"node": "report"}, {"node": "reflection"}]
    coordinator = _FakeCoordinator("报告", trace)

    results = run_suite(coordinator, _FakeMockLLM(), cases)

    assert [r["case_id"] for r in results] == ["a", "b", "c"]
    assert len(coordinator.received_queries) == 3


def test_run_suite_单条失败不影响其他用例():
    good_case = _case(case_id="good")
    bad_case = _case(case_id="bad")

    class _FlakyCoordinator:
        def __init__(self):
            self.calls = 0

        def route(self, query):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("第二条崩溃")
            return "报告"

        def get_trace(self):
            return [{"node": "direct"}, {"node": "report"}, {"node": "reflection"}]

    results = run_suite(_FlakyCoordinator(), _FakeMockLLM(), [good_case, bad_case])

    assert len(results) == 2
    assert "error" not in results[0]
    assert "error" in results[1]
