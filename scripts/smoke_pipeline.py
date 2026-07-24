"""端到端冒烟测试:mock 模式下跑通 direct / chain / parallel 三条路径。

验证质量保障 pipeline 已接通:
- 三种路由策略都能产出终稿
- parallel 会经过 conflict_check(并按需 debate)
- 每条链路都经过 report + reflection 节点
"""

import sys
import os

# Windows 控制台默认 GBK,无法编码 emoji;统一重配为 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.llm import LLMClient
from src.core.coordinator import CoordinatorAgent
from src.agents.db_agent import DBAgent
from src.agents.server_agent import ServerAgent
from src.agents.log_agent import LogAgent
from src.core.debate import DebateArena
from src.core.reflection import ReflectionEngine
from src.agents.report_agent import ReportAgent


def build_mock_coordinator():
    llm = LLMClient(api_key="mock", base_url="http://mock", model="mock")
    coordinator = CoordinatorAgent(
        llm=llm,
        debate=DebateArena(llm=llm),
        reflection=ReflectionEngine(llm=llm),
        report=ReportAgent(),
    )
    coordinator.register_agent("db", DBAgent(llm=llm, enable_long_term_memory=False))
    coordinator.register_agent("server", ServerAgent(llm=llm, enable_long_term_memory=False))
    coordinator.register_agent("log", LogAgent(llm=llm, enable_long_term_memory=False))
    return coordinator


CASES = [
    ("direct", "帮我分析这个SQL：SELECT * FROM orders WHERE status = 'PENDING'"),
    ("chain", "系统很慢，经常超时，帮我排查一下"),
    ("parallel", "明天大促，帮我全面体检一下系统整体健康度"),
]


class _StubAgent:
    """返回固定结论的桩 Agent,用于制造分歧、验证 debate 分支。"""
    def __init__(self, conclusion):
        self._c = conclusion
    def run(self, _query):
        return self._c
    def get_thinking(self):
        return [self._c[:20]]


def check_debate_branch():
    """并行结论分歧时,应经过 debate 节点。"""
    llm = LLMClient(api_key="mock", base_url="http://mock", model="mock")
    coordinator = CoordinatorAgent(
        llm=llm,
        debate=DebateArena(llm=llm),
        reflection=ReflectionEngine(llm=llm),
        report=ReportAgent(),
    )
    coordinator.register_agent("server", _StubAgent("根因是 CPU 不足,建议扩容。"))
    coordinator.register_agent("db", _StubAgent("根因是慢 SQL 缺索引,与 CPU 无关。"))

    report = coordinator.route("全面体检一下系统健康度")
    trace_nodes = [e["node"] for e in coordinator.get_trace()]
    print(f"\n{'='*60}\n[debate 分支] 结论分歧场景\n{'='*60}")
    print("链路节点:", " → ".join(trace_nodes))
    problems = []
    if "conflict_check" not in trace_nodes:
        problems.append("未经过 conflict_check")
    if "debate" not in trace_nodes:
        problems.append("分歧场景未触发 debate")
    if not report or not report.strip():
        problems.append("终稿为空")
    return problems


def main():
    failures = []
    for expect_hint, query in CASES:
        print(f"\n{'='*60}\n[用例] {query}\n{'='*60}")
        coordinator = build_mock_coordinator()
        report = coordinator.route(query)
        trace_nodes = [e["node"] for e in coordinator.get_trace()]

        print("链路节点:", " → ".join(trace_nodes))
        print("报告前 120 字:", (report or "")[:120].replace("\n", " "))

        # 断言:终稿非空
        if not report or not report.strip():
            failures.append(f"[{query}] 终稿为空")
        # 断言:经过 report 与 reflection
        if "report" not in trace_nodes:
            failures.append(f"[{query}] 未经过 report 节点")
        if "reflection" not in trace_nodes:
            failures.append(f"[{query}] 未经过 reflection 节点")
        # 断言:路由策略命中
        if expect_hint not in trace_nodes:
            failures.append(f"[{query}] 期望经过 {expect_hint} 节点,实际:{trace_nodes}")

    failures.extend(check_debate_branch())

    print(f"\n{'='*60}")
    if failures:
        print("❌ 冒烟失败:")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("✅ 三条路径全部跑通,pipeline 已接通(route → agent → [debate] → report → reflection)")


if __name__ == "__main__":
    main()
