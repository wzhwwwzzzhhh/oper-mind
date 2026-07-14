"""Coordinator Agent —— 动态路由调度器(LangGraph 编排版)

不再自己写死路由分支,而是持有一张 LangGraph 编排图:
    route(LLM决策) → direct/chain/parallel → [分歧→Debate] → Report → Reflection

领域 Agent 通过 register_agent 注册;质量保障组件(Debate/Reflection/Report)
在构造时注入。对外仍暴露 route(query) 接口,保持 CLI / FastAPI 调用不变。
"""

from src.core.llm import LLMClient
from src.core.graph import build_diagnosis_graph


class CoordinatorAgent:
    """调度中枢:构建并驱动诊断编排图,汇总最终报告。"""

    def __init__(self, llm: LLMClient, debate=None, reflection=None, report=None):
        self.llm = llm
        self.agents: dict[str, object] = {}
        self.debate = debate
        self.reflection = reflection
        self.report = report

        self._graph = None            # 懒编译:等 Agent 注册齐再编译
        self.thinking_log: list[str] = []
        self.trace: list[dict] = []

    def register_agent(self, name: str, agent: object):
        """注册一个领域 Agent(会使已编译的图失效,下次 route 重新编译)"""
        self.agents[name] = agent
        self._graph = None

    def set_quality(self, debate=None, reflection=None, report=None):
        """注入质量保障组件"""
        if debate is not None:
            self.debate = debate
        if reflection is not None:
            self.reflection = reflection
        if report is not None:
            self.report = report
        self._graph = None

    def _ensure_graph(self):
        if self._graph is None:
            self._graph = build_diagnosis_graph(
                llm=self.llm,
                agents=self.agents,
                debate=self.debate,
                reflection=self.reflection,
                report=self.report,
            )
        return self._graph

    def route(self, user_input: str) -> str:
        """驱动编排图,返回最终诊断报告。"""
        graph = self._ensure_graph()

        initial_state = {
            "query": user_input,
            "agent_results": {},
            "agent_thinking": {},
            "review_feedback": [],
            "revision_count": 0,
            "trace": [],
        }
        final_state = graph.invoke(initial_state)

        self.trace = final_state.get("trace", [])
        self.thinking_log = [
            f"[{e.get('node')}] {e.get('detail')}" for e in self.trace
        ]

        # 优先终稿;异常兜底为初稿或原始结论
        report = final_state.get("final_report") or final_state.get("report_draft")
        if not report:
            results = final_state.get("agent_results", {})
            report = "\n\n".join(f"### {k}\n{v}" for k, v in results.items()) or "未生成诊断结果"
        return report

    def get_thinking(self) -> list[str]:
        return self.thinking_log

    def get_trace(self) -> list[dict]:
        """返回全链路事件流(供前端可视化)"""
        return self.trace
