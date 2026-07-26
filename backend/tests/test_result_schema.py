"""结果契约单测 —— CaseResult.from_run_result 把 runner 的嵌套字典拼成扁平契约,
build_summary 从一批 CaseResult 聚合出 EvalSummary。

对应 M2 design 第 3.1/6 节。runner.run_case() 返回
{case_id, report, deterministic: {...}, judge: {...}, error?}，
不含 domain/difficulty(那些在 EvalCase 上)，因此需要 case + 原始结果字典两者拼装。
"""

from data.eval.schema import EvalCase
from src.eval.result_schema import CaseResult, build_summary, _case_group


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


def _run_result(**kw) -> dict:
    base = dict(
        case_id="test-001",
        report="报告内容",
        deterministic={
            "actual_strategy": "direct",
            "route_hit": True,
            "target_hit": True,
            "pipeline_complete": True,
            "mechanism_hit": True,
            "condition_complete": True,
        },
        latency_ms=12.5,
        judge={
            "method": "mock_stub",
            "root_cause_score": 0.5,
            "key_points_recall": 1.0,
            "key_points_hit": ["点1"],
        },
    )
    base.update(kw)
    return base


# ===== CaseResult.from_run_result =====

def test_from_run_result_基本字段拼装():
    case = _case()
    result = CaseResult.from_run_result(case, _run_result())

    assert result.case_id == "test-001"
    assert result.domain == "db"
    assert result.difficulty == "easy"
    assert result.route_hit is True
    assert result.target_hit is True
    assert result.pipeline_complete is True
    assert result.mechanism_hit is True
    assert result.condition_complete is True
    assert result.latency_ms == 12.5
    assert result.root_cause_score == 0.5
    assert result.key_points_recall == 1.0
    assert result.key_points_hit == ["点1"]
    assert result.judge_is_stub is True
    assert result.report_text == "报告内容"
    assert result.error == ""


def test_from_run_result_llm_judge_不是stub():
    case = _case()
    result = CaseResult.from_run_result(
        case, _run_result(judge={"method": "llm_judge", "root_cause_score": 0.8,
                                  "key_points_recall": 0.5, "key_points_hit": ["点1"]})
    )
    assert result.judge_is_stub is False


def test_from_run_result_带error字段():
    case = _case()
    result = CaseResult.from_run_result(case, _run_result(error="RuntimeError: 崩溃", report=""))
    assert result.error == "RuntimeError: 崩溃"
    assert result.report_text == ""


# ===== build_summary =====

def test_build_summary_全命中():
    case = _case(case_id="a")
    results = [CaseResult.from_run_result(case, _run_result(case_id="a"))]
    summary = build_summary("hash123", results)

    assert summary.total == 1
    assert summary.route_hit_rate == 1.0
    assert summary.mean_root_cause_score == 0.5
    assert summary.condition_complete_rate == 1.0
    assert summary.mean_latency_ms == 12.5
    assert summary.judge_is_stub is True
    assert summary.error_count == 0
    assert summary.by_domain["db"].count == 1


def test_build_summary_error计数():
    case_a = _case(case_id="a")
    case_b = _case(case_id="b")
    results = [
        CaseResult.from_run_result(case_a, _run_result(case_id="a")),
        CaseResult.from_run_result(case_b, _run_result(case_id="b", error="boom")),
    ]
    summary = build_summary("hash123", results)
    assert summary.error_count == 1


def test_build_summary_按域按难度切片():
    case_db = _case(case_id="a", domain="db", difficulty="easy")
    case_server = _case(case_id="b", domain="server", difficulty="hard")
    results = [
        CaseResult.from_run_result(case_db, _run_result(case_id="a")),
        CaseResult.from_run_result(case_server, _run_result(case_id="b")),
    ]
    summary = build_summary("hash123", results)
    assert set(summary.by_domain.keys()) == {"db", "server"}
    assert set(summary.by_difficulty.keys()) == {"easy", "hard"}


def test_build_summary_空列表不崩():
    summary = build_summary("hash123", [])
    assert summary.total == 0
    assert summary.route_hit_rate == 0.0
    assert summary.by_domain == {}


# ===== M5 step4：token / 用例分组 / 按 scenario·case_group 切片 =====

def test_case_group分类():
    assert _case_group("mislead-001") == "mislead"
    assert _case_group("conflict-003") == "conflict"
    assert _case_group("chain-002") == "legacy_compound"
    assert _case_group("parallel-010") == "legacy_compound"
    assert _case_group("db-001") == "single_domain"


def test_from_run_result_携带token与分组():
    case = _case(case_id="mislead-001", domain="compound", expected_strategy="chain",
                 expected_agents=["server", "db", "log"], scenario="S4")
    result = CaseResult.from_run_result(case, _run_result(case_id="mislead-001", tokens=123))
    assert result.tokens == 123
    assert result.scenario == "S4"
    assert result.case_group == "mislead"


def test_from_run_result_缺token默认0():
    # 旧 runner 结果无 tokens 字段，应默认 0 不报错
    result = CaseResult.from_run_result(_case(), _run_result())
    assert result.tokens == 0


def test_build_summary_按scenario与case_group切片():
    case_db = _case(case_id="db-001", scenario="S1")
    case_ml = _case(case_id="mislead-001", domain="compound", expected_strategy="chain",
                    expected_agents=["server", "db", "log"], scenario="S4")
    results = [
        CaseResult.from_run_result(case_db, _run_result(case_id="db-001", tokens=10)),
        CaseResult.from_run_result(case_ml, _run_result(case_id="mislead-001", tokens=30)),
    ]
    summary = build_summary("hash", results)
    assert summary.mean_tokens == 20.0
    assert set(summary.by_scenario) == {"S1", "S4"}
    assert set(summary.by_case_group) == {"single_domain", "mislead"}
    assert summary.by_case_group["mislead"].mean_tokens == 30.0
