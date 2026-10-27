"""MainAgent typed RunExecutor：每 Run 新建模型、Tool、网关、内核状态与预算。

执行器只负责装配与事件投影；能力选择、知识装入和工具调用都在
`core/main_agent_react.py` 的通用路径上完成，不按能力 id 写分支。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue, ValidationError

from src.agents.main_agent import MainAgent, MainAgentTask
from src.application.contracts import DiagnosisExecutionEvent
from src.application.run_execution import (
    MainAgentRunExecutionInput,
    RunEventSignal,
    RunExecutionError,
    RunExecutionInput,
    RunFailureCode,
    RunFailureSignal,
    RunMainDeliverySignal,
    RunSignal,
)
from src.capabilities import CapabilityKind, CapabilityRegistry, SkillSource
from src.capabilities.playbook import READONLY_PLAYBOOK_SOURCE
from src.core.capability_tools import TextCompareToolBinding, ToolBindingRegistry
from src.core.llm import LLMClient
from src.core.main_agent_decisions import MainDecisionMaterialRefs
from src.core.main_agent_model import MainAgentModelAdapter, MainMockScenario
from src.core.main_agent_react import (
    MainAgentFailure,
    MainRouteSignal,
    MainStepSignal,
    MainToolSignal,
)
from src.core.tool_gateway import GatewayResult, ToolGateway
from src.core.tool_registry import ToolRegistry
from src.domain.diagnosis import RunEventType
from src.domain.main_agent import (
    MAIN_AGENT_RULE_VERSION,
    MAX_MODEL_CALL_SECONDS,
    MainAnswerDeliveryV1,
    MainComparisonDeliveryV1,
    MainInputSnapshotV1,
    MainNeedsInputDeliveryV1,
)

_ROUTE_SUMMARIES = {
    "answer": "决策：普通回答",
    "needs_input": "决策：材料追问",
    "load_skill": "决策：知识加载",
    "invoke_capability": "决策：能力调用",
    "budget_exhausted": "决策：预算耗尽",
    "failed": "决策：决策失败",
}
_TOOL_SUMMARIES = {
    "ok": "工具调用：成功",
    "unavailable": "工具调用：不可用",
    "rejected": "工具调用：被拒绝",
    "timeout": "工具调用：超时",
    "error": "工具调用：失败",
}


class MainAgentRunExecutor:
    """把冻结快照装配为一次有界主 Agent 执行；不持有任何持久化端口。"""

    def __init__(
        self,
        *,
        client_factory: Callable[[float], LLMClient],
        capabilities: CapabilityRegistry,
        skill_source: SkillSource = READONLY_PLAYBOOK_SOURCE,
        tool_bindings: ToolBindingRegistry | None = None,
        mock_scenario: MainMockScenario | None = None,
        is_cancelled: Callable[[UUID], bool] | None = None,
    ) -> None:
        self._client_factory = client_factory
        self._capabilities = capabilities
        self._skill_source = skill_source
        self._tool_bindings = tool_bindings or ToolBindingRegistry([TextCompareToolBinding()])
        self._mock_scenario = mock_scenario
        self._is_cancelled = is_cancelled

    def stream(self, execution_input: RunExecutionInput) -> Iterator[RunSignal]:
        """执行一次 MainAgent Run，逐 step 输出事件与恰好一个终止 signal。"""
        if not isinstance(execution_input, MainAgentRunExecutionInput):
            raise RunExecutionError(RunFailureCode.MAIN_AGENT_FAILED)
        snapshot = execution_input.snapshot
        if snapshot.rule_version != MAIN_AGENT_RULE_VERSION:
            raise RunExecutionError(RunFailureCode.MAIN_AGENT_RULE_UNAVAILABLE)

        try:
            client = self._client_factory(MAX_MODEL_CALL_SECONDS)
            adapter = MainAgentModelAdapter(
                client_factory=self._client_factory,
                mock_scenario=self._mock_scenario,
            )
            tool_registry = self._build_tool_registry(execution_input)
        except Exception:
            yield _failure(RunFailureCode.MAIN_AGENT_FAILED)
            return

        mode = "mock" if client.is_mock else "target"

        def call_tool(name: str, arguments: str, timeout_seconds: float) -> GatewayResult:
            """按本次有效超时构造网关；等待上限由剩余预算截断。"""
            gateway = ToolGateway(tool_registry, timeout_seconds=timeout_seconds)
            try:
                return gateway.invoke(name, arguments)
            finally:
                gateway.shutdown()

        def cancelled() -> bool:
            if self._is_cancelled is None:
                return False
            try:
                return self._is_cancelled(execution_input.run_id)
            except Exception:
                return False

        try:
            task = MainAgentTask(
                run_id=execution_input.run_id,
                session_id=execution_input.session_id,
                query=snapshot.query,
                context=snapshot.context,
                material_refs=_material_refs(snapshot),
                rule_version=snapshot.rule_version,
            )
            agent = MainAgent(
                llm=client,
                adapter=adapter,
                capabilities=self._capabilities,
                skill_source=self._skill_source,
                tool_bindings=self._tool_bindings,
                call_tool=call_tool,
                tools=tool_registry,
                is_cancelled=cancelled,
            )
        except (ValidationError, ValueError):
            yield _failure(RunFailureCode.MAIN_AGENT_FAILED)
            return

        yield _event(RunEventType.AGENT_START, {"summary": "主 Agent 开始", "mode": mode})
        try:
            for signal in agent.stream_task(task):
                yield _signal_event(signal, mode)
        except Exception:
            yield _failure(RunFailureCode.MAIN_AGENT_FAILED)
            return

        outcome = agent.outcome
        if outcome is None:
            yield _failure(RunFailureCode.MAIN_AGENT_FAILED)
            return
        if outcome.canceled:
            # 取消已在会话状态中胜出：不写 agent_done、不产交付；
            # 正常 EOF 由运行时守卫补失败，应用服务会因终态短路而不写任何事件。
            return

        yield _event(
            RunEventType.AGENT_DONE,
            {
                "summary": "主 Agent 完成" if outcome.delivery is not None else "主 Agent 未生成交付",
                "mode": mode,
                "steps": outcome.steps,
                "outcome": _agent_outcome(outcome.delivery, outcome.failure),
            },
        )
        if outcome.delivery is not None:
            yield RunMainDeliverySignal(delivery=outcome.delivery)
            return
        yield _failure(_failure_code(outcome.failure))

    def _build_tool_registry(self, execution_input: MainAgentRunExecutionInput) -> ToolRegistry:
        """装配全部已注册执行型能力声明的工具；未绑定工具由网关安全拒绝。"""
        registry = ToolRegistry()
        for definition in self._capabilities.catalog():
            if definition.kind is not CapabilityKind.EXECUTION:
                continue
            for name in definition.tool_bindings:
                binding = self._tool_bindings.get(name)
                if binding is not None and registry.get(name) is None:
                    registry.register(
                        binding.build_tool(
                            run_id=execution_input.run_id,
                            snapshot=execution_input.snapshot,
                        )
                    )
        return registry


def _material_refs(snapshot: MainInputSnapshotV1) -> MainDecisionMaterialRefs:
    """从冻结快照抽取材料引用；不携带原文。"""
    return MainDecisionMaterialRefs(
        text_a=snapshot.text_a.material_id if snapshot.text_a is not None else None,
        text_b=snapshot.text_b.material_id if snapshot.text_b is not None else None,
    )


def _signal_event(signal: MainStepSignal, mode: str) -> RunEventSignal:
    """把内核 step 信号投影为封闭事件字段；不携带任何自由文本。"""
    if isinstance(signal, MainRouteSignal):
        summary = _ROUTE_SUMMARIES.get(signal.decision, "决策：未知")
        data: dict[str, JsonValue] = {
            "summary": summary,
            "mode": mode,
            "step": signal.step,
            "decision": signal.decision,
        }
        if signal.capability_id is not None:
            data["capability_id"] = signal.capability_id
        if signal.capability_version is not None:
            data["capability_version"] = signal.capability_version
        if signal.capability_kind is not None:
            data["capability_kind"] = signal.capability_kind.value
        if signal.status is not None:
            data["status"] = signal.status
        return _event(RunEventType.ROUTE_DECIDED, data)
    if isinstance(signal, MainToolSignal):
        return _event(
            RunEventType.TOOL_INVOKED,
            {
                "summary": _TOOL_SUMMARIES.get(signal.status, "工具调用：失败"),
                "mode": mode,
                "step": signal.step,
                "capability_id": signal.capability_id,
                "capability_version": signal.capability_version,
                "status": signal.status,
                "duration_ms": signal.duration_ms,
            },
        )
    # 未知信号类型只允许安全失败，绝不猜测字段或继续执行。
    raise RunExecutionError(RunFailureCode.MAIN_AGENT_FAILED)


def _agent_outcome(
    delivery: object,
    failure: MainAgentFailure | None,
) -> str:
    """把交付或失败收敛为封闭的 agent_done 标签。"""
    if failure is MainAgentFailure.BUDGET_EXHAUSTED:
        return "budget_exhausted"
    if failure is not None:
        return "failed"
    if isinstance(delivery, MainAnswerDeliveryV1):
        return "answer_with_knowledge" if delivery.knowledge_grounding is not None else "answer"
    if isinstance(delivery, MainNeedsInputDeliveryV1):
        return "needs_input"
    if isinstance(delivery, MainComparisonDeliveryV1):
        return "comparison"
    return "failed"


_FAILURE_CODE_BY_AGENT_FAILURE = {
    MainAgentFailure.MODEL_UNAVAILABLE: RunFailureCode.MAIN_AGENT_MODEL_UNAVAILABLE,
    MainAgentFailure.MODEL_DECISION_INVALID: RunFailureCode.MAIN_AGENT_DECISION_INVALID,
    MainAgentFailure.CAPABILITY_UNAVAILABLE: RunFailureCode.MAIN_AGENT_CAPABILITY_UNAVAILABLE,
    MainAgentFailure.TOOL_FAILED: RunFailureCode.MAIN_AGENT_TOOL_FAILED,
    MainAgentFailure.DELIVERY_INVALID: RunFailureCode.MAIN_AGENT_DELIVERY_INVALID,
    MainAgentFailure.BUDGET_EXHAUSTED: RunFailureCode.MAIN_AGENT_BUDGET_EXHAUSTED,
}


def _failure_code(failure: MainAgentFailure | None) -> RunFailureCode:
    """把主 Agent 封闭失败映射为固定 Run 失败码；未知失败收敛到兜底码。"""
    if failure is None:
        return RunFailureCode.MAIN_AGENT_FAILED
    return _FAILURE_CODE_BY_AGENT_FAILURE.get(failure, RunFailureCode.MAIN_AGENT_FAILED)


def _event(event_type: RunEventType, data: dict[str, JsonValue]) -> RunEventSignal:
    """构造安全过程事件；data 只含固定摘要、模式与封闭枚举。"""
    return RunEventSignal(
        event=DiagnosisExecutionEvent(
            type=event_type,
            node="main_agent",
            occurred_at=datetime.now(UTC),
            data=data,
        )
    )


def _failure(code: RunFailureCode) -> RunFailureSignal:
    """构造封闭失败 signal，不携带上游文案。"""
    return RunFailureSignal(code=code)
