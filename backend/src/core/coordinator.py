"""Coordinator Agent —— 动态路由调度器（LangGraph 编排版）。"""

from collections.abc import Iterator
from datetime import datetime, timezone
import logging
from typing import Any, Literal, TypedDict, cast
from typing_extensions import NotRequired

from src.core.graph import build_diagnosis_graph
from src.core.llm import LLMClient


LOGGER = logging.getLogger(__name__)


class TraceRecord(TypedDict):
    """标准化后的诊断编排事件。"""

    type: str
    node: str
    detail: str
    timestamp: str
    status: NotRequired[str]        # 仅 tool_invoked 事件携带
    duration_ms: NotRequired[int]   # 仅 tool_invoked 事件携带


class TraceStreamItem(TypedDict):
    """流式输出的一条编排事件。"""

    kind: Literal["trace"]
    event: TraceRecord


class CompleteStreamItem(TypedDict):
    """流式输出的诊断完成结果。"""

    kind: Literal["complete"]
    result: str
    strategy: str
    trace: list[TraceRecord]


class ErrorStreamItem(TypedDict):
    """流式输出的可安全展示错误。"""

    kind: Literal["error"]
    code: str
    message: str


DiagnosisStreamItem = TraceStreamItem | CompleteStreamItem | ErrorStreamItem


_EVENT_TYPE_BY_NODE = {
    "route": "route_decided",
    "direct": "agent_done",
    "chain": "agent_done",
    "parallel": "agent_done",
    "tool": "tool_invoked",
    "conflict_check": "conflict_checked",
    "debate": "debate_round",
    "report": "report",
    "reflection": "reflection",
}


class CoordinatorAgent:
    """调度中枢：构建并驱动诊断编排图，汇总最终报告。"""

    def __init__(
        self,
        llm: LLMClient,
        debate: object | None = None,
        reflection: object | None = None,
        report: object | None = None,
    ) -> None:
        self.llm = llm
        self.agents: dict[str, object] = {}
        self.debate = debate
        self.reflection = reflection
        self.report = report
        self._graph: Any = None
        self.thinking_log: list[str] = []
        self.trace: list[TraceRecord] = []

    def register_agent(self, name: str, agent: object) -> None:
        """注册领域 Agent，并使已编译的图失效。"""
        self.agents[name] = agent
        self._graph = None

    def set_quality(
        self,
        debate: object | None = None,
        reflection: object | None = None,
        report: object | None = None,
    ) -> None:
        """注入质量保障组件。"""
        if debate is not None:
            self.debate = debate
        if reflection is not None:
            self.reflection = reflection
        if report is not None:
            self.report = report
        self._graph = None

    def _ensure_graph(self) -> Any:
        """在首次调用或依赖变更后编译诊断图。"""
        if self._graph is None:
            self._graph = build_diagnosis_graph(
                llm=self.llm,
                agents=self.agents,
                debate=self.debate,
                reflection=self.reflection,
                report=self.report,
            )
        return self._graph

    def _initial_state(self, user_input: str) -> dict[str, object]:
        """构造同步和流式路径共享的初始图状态。"""
        return {
            "query": user_input,
            "agent_results": {},
            "agent_thinking": {},
            "review_feedback": [],
            "revision_count": 0,
            "trace": [],
        }

    def _normalize_trace(self, raw_trace: list[dict[str, Any]]) -> list[TraceRecord]:
        """补全 API 事件需要的类型与时间戳，同时兼容旧 trace 字段。"""
        normalized: list[TraceRecord] = []
        for event in raw_trace:
            node = str(event.get("node", "unknown"))
            record: TraceRecord = {
                "type": _EVENT_TYPE_BY_NODE.get(node, "report"),
                "node": node,
                "detail": str(event.get("detail", "节点已完成")),
                "timestamp": str(event.get("timestamp") or self._timestamp()),
            }
            if node == "tool":
                status = event.get("status")
                if isinstance(status, str):
                    record["status"] = status
                duration = event.get("duration_ms")
                if isinstance(duration, int) and not isinstance(duration, bool):
                    record["duration_ms"] = duration
            normalized.append(record)
        return normalized

    @staticmethod
    def _timestamp() -> str:
        """生成前端可排序的 UTC ISO 8601 时间戳。"""
        return datetime.now(timezone.utc).isoformat()

    def _create_start_events(self, update: dict[str, Any]) -> list[TraceRecord]:
        """在路由完成后补发领域 Agent 启动事件，供 SSE 前端即时点亮节点。"""
        strategy = str(update.get("strategy", ""))
        if strategy == "direct":
            target = str(update.get("target", "db"))
            detail = f"启动领域 Agent={target}"
        elif strategy == "chain":
            detail = "启动链式诊断，顺序=server → db → log"
        elif strategy == "parallel":
            names = list(self.agents.keys())
            detail = f"启动并发诊断，Agent={names}"
        else:
            return []
        return [
            {
                "type": "agent_start",
                "node": strategy,
                "detail": detail,
                "timestamp": self._timestamp(),
            }
        ]

    @staticmethod
    def _stream_item(**kwargs: Any) -> DiagnosisStreamItem:
        """集中收窄 TypedDict 联合类型，避免公开流接口暴露裸字典。"""
        return cast(DiagnosisStreamItem, kwargs)

    @staticmethod
    def _result_from_state(state: dict[str, Any]) -> str:
        """从最终图状态抽取报告，并保留同步路径的降级逻辑。"""
        report = state.get("final_report") or state.get("report_draft")
        if report:
            return str(report)
        results = state.get("agent_results", {})
        if isinstance(results, dict):
            return "\n\n".join(
                f"### {name}\n{result}" for name, result in results.items()
            ) or "未生成诊断结果"
        return "未生成诊断结果"

    def _store_result(self, trace: list[TraceRecord]) -> None:
        """更新最近一次诊断的 trace 与供旧接口使用的思考摘要。"""
        self.trace = trace
        self.thinking_log = [f"[{event['node']}] {event['detail']}" for event in trace]

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
        final_state = graph.invoke(self._initial_state(user_input))
        trace = self._normalize_trace(final_state.get("trace", []))
        self._store_result(trace)
        return self._result_from_state(final_state)

    def route_stream(self, user_input: str) -> Iterator[DiagnosisStreamItem]:
        """逐节点执行诊断图并产出可供 SSE 转发的增量事件。"""
        final_state: dict[str, Any] = self._initial_state(user_input)
        emitted_trace: list[TraceRecord] = []
        seen_trace_count = 0

        try:
            graph = self._ensure_graph()
            for update_group in graph.stream(
                self._initial_state(user_input),
                stream_mode="updates",
            ):
                for update in update_group.values():
                    if not isinstance(update, dict):
                        continue
                    final_state.update(update)

                    raw_trace = update.get("trace", [])
                    if isinstance(raw_trace, list):
                        new_raw_trace = raw_trace[seen_trace_count:]
                        seen_trace_count = max(seen_trace_count, len(raw_trace))
                        for event in self._normalize_trace(new_raw_trace):
                            emitted_trace.append(event)
                            yield self._stream_item(kind="trace", event=event)

                    if "strategy" in update:
                        for event in self._create_start_events(update):
                            emitted_trace.append(event)
                            yield self._stream_item(kind="trace", event=event)

            result = self._result_from_state(final_state)
            strategy = str(final_state.get("strategy", ""))
            self._store_result(emitted_trace)
            yield self._stream_item(
                kind="complete",
                result=result,
                strategy=strategy,
                trace=emitted_trace,
            )
        except Exception:
            LOGGER.exception("流式诊断执行失败")
            self._store_result(emitted_trace)
            yield self._stream_item(
                kind="error",
                code="DIAGNOSIS_FAILED",
                message="诊断执行失败，请稍后重试",
            )

    def get_thinking(self) -> list[str]:
        """返回最近一次诊断的节点思考摘要。"""
        return self.thinking_log

    def get_trace(self) -> list[TraceRecord]:
        """返回最近一次诊断的全链路事件流。"""
        return self.trace
