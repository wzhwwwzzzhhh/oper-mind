"""Coordinator Agent —— 动态路由调度器（LangGraph 编排版）。"""

from src.core.experiment import ExperimentCondition, get_experiment_condition
from src.core.graph import build_diagnosis_graph
from src.core.llm import LLMClient


class CoordinatorAgent:
    """调度中枢：构建并驱动诊断编排图，汇总最终报告。"""

    def __init__(
        self,
        llm: LLMClient,
        debate=None,
        reflection=None,
        report=None,
        experiment_condition: ExperimentCondition | None = None,
    ) -> None:
        self.llm = llm
        self.agents: dict[str, object] = {}
        self.debate = debate
        self.reflection = reflection
        self.report = report
        self.experiment_condition = experiment_condition or get_experiment_condition("full")
        self._graph = None
        self.thinking_log: list[str] = []
        self.trace: list[dict] = []

    def register_agent(self, name: str, agent: object) -> None:
        """注册领域 Agent，并使已编译的图失效。"""
        self.agents[name] = agent
        self._graph = None

    def set_quality(self, debate=None, reflection=None, report=None) -> None:
        """注入质量保障组件。"""
        if debate is not None:
            self.debate = debate
        if reflection is not None:
            self.reflection = reflection
        if report is not None:
            self.report = report
        self._graph = None

    def set_experiment_condition(self, condition: ExperimentCondition) -> None:
        """更新实验条件，并使编排图按新条件重新编译。"""
        self.experiment_condition = condition
        self._graph = None

    def _ensure_graph(self):
        if self._graph is None:
            self._graph = build_diagnosis_graph(
                llm=self.llm,
                agents=self.agents,
                debate=self.debate,
                reflection=self.reflection,
                report=self.report,
                experiment_condition=self.experiment_condition,
            )
        return self._graph

    def reset_for_evaluation(self) -> None:
        """在每条评测用例前清空领域 Agent 的短期会话状态。"""
        for agent in self.agents.values():
            reset = getattr(agent, "reset_for_evaluation", None)
            if callable(reset):
                reset()
        self.thinking_log = []
        self.trace = []
    def route(self, user_input: str) -> str:
        """驱动编排图并返回最终诊断报告。"""
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
            f"[{event.get('node')}] {event.get('detail')}" for event in self.trace
        ]
        report = final_state.get("final_report") or final_state.get("report_draft")
        if not report:
            results = final_state.get("agent_results", {})
            report = "\n\n".join(
                f"### {name}\n{result}" for name, result in results.items()
            ) or "未生成诊断结果"
        return report

    def get_thinking(self) -> list[str]:
        """返回最近一次诊断的节点思考摘要。"""
        return self.thinking_log

    def get_trace(self) -> list[dict]:
        """返回最近一次诊断的全链路事件流。"""
        return self.trace
