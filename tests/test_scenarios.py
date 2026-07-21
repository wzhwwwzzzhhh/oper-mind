"""多故障 mock 世界单测 —— 场景状态机 + 工具在 mock 模式读激活场景。

对应 M5 step2。验证：S1–S4 注册、激活/清除状态机、工具确定性读场景、
以及 S1 与 S3「同表象不同根因」、S4「表象误导」的关键区分点。
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from data import scenarios
from data.scenarios import (
    active_or_default,
    clear_active_scenario,
    get_active_scenario,
    get_scenario,
    set_active_scenario,
    supported_scenarios,
)
from data.eval.schema import EvalCase
from src.tools.log_tools import SearchLogsTool, QuerySlowLogTool
from src.tools.server_tools import CheckDiskTool, CheckCpuTool, CheckProcessTool, CheckNetworkTool


@pytest.fixture(autouse=True)
def _reset_active_scenario():
    """每条用例前后清空激活场景，避免模块级状态在用例间残留。"""
    clear_active_scenario()
    yield
    clear_active_scenario()


# ===== 场景注册与状态机 =====

def test_四起场景齐全且根因分散():
    assert set(supported_scenarios()) == {"S1", "S2", "S3", "S4"}
    domains = {get_scenario(k).root_cause_domain for k in supported_scenarios()}
    # 根因刻意分散在不同域，不都是 db
    assert domains == {"db", "server", "app", "config"}


def test_非法场景key报错():
    with pytest.raises(ValueError):
        get_scenario("S99")


def test_激活与清除():
    assert get_active_scenario() is None
    set_active_scenario("S2")
    assert get_active_scenario().key == "S2"
    clear_active_scenario()
    assert get_active_scenario() is None


def test_active_or_default未激活回落S1():
    assert get_active_scenario() is None
    assert active_or_default().key == "S1"
    set_active_scenario("S4")
    assert active_or_default().key == "S4"


# ===== 工具在 mock 模式读激活场景 =====

def test_日志工具随场景切换():
    set_active_scenario("S2")  # 磁盘写满
    out = SearchLogsTool().execute(keyword="space")
    assert "No space left" in out


def test_慢查询空场景给出正常提示():
    set_active_scenario("S4")  # 连接配置问题，DB 健康、无慢查询
    out = QuerySlowLogTool().execute()
    assert "未发现慢查询" in out


def test_服务器工具激活场景走确定性数据():
    set_active_scenario("S2")  # 磁盘 /data 98%
    assert "98%" in CheckDiskTool().execute()


# ===== 关键区分点：多 Agent 价值的来源 =====

def test_S1与S3同表象不同根因():
    # 都表现为内存/OOM，但热点进程不同：S1 是 mysqld，S3 是 java 应用
    set_active_scenario("S1")
    assert "mysqld" in CheckProcessTool().execute()
    set_active_scenario("S3")
    assert "java" in CheckProcessTool().execute()


def test_S4表象误导_连接卡在配置上限且资源正常():
    set_active_scenario("S4")
    # 连接数正好卡在 max_connections=100
    assert "100" in CheckNetworkTool().execute()
    # 资源正常（CPU 低），排除"资源瓶颈"，指向配置
    cpu = CheckCpuTool().execute()
    assert "30%" in cpu


# ===== step3：EvalCase.scenario 字段与 Runner 按用例切场景 =====


def _eval_case(**kw) -> EvalCase:
    base = dict(
        case_id="t-001", query="测试", domain="db", expected_strategy="direct",
        expected_agents=["db"], difficulty="easy", golden_root_cause="根因",
        golden_key_points=["点1"], expects_debate=False, source="synthetic",
    )
    base.update(kw)
    return EvalCase(**base)


def test_evalcase_scenario_默认S1():
    assert _eval_case().scenario == "S1"
    assert _eval_case(scenario="S3").scenario == "S3"


def test_runner_按用例设置激活场景(monkeypatch):
    from src.eval import runner as rm

    monkeypatch.setattr(rm, "compute_deterministic", lambda *a, **k: {})
    monkeypatch.setattr(rm, "judge_report", lambda *a, **k: {})
    captured = {}

    class _FakeCoord:
        experiment_condition = None

        def route(self, q):
            captured["scenario"] = get_active_scenario().key  # route 时场景已切
            return "报告"

        def get_trace(self):
            return {}

    rm.run_case(_FakeCoord(), object(), _eval_case(scenario="S2"))
    assert captured["scenario"] == "S2"
