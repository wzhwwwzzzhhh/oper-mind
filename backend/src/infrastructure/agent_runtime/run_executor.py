"""MainAgent typed RunExecutor：每 Run 新建模型、Tool、网关、图状态与计数。"""

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
from src.capabilities import CapabilityDefinition, CapabilityRegistry
from src.capabilities.text_compare import TEXT_COMPARE_TOOL_NAME
from src.core.llm import LLMClient
from src.core.main_agent_graph import MainAgentFailure, MainAgentOutcome
from src.core.main_agent_model import MainAgentModelAdapter, MainDecisionMaterialRefs, MainMockScenario
from src.core.tool_gateway import ToolGateway
from src.core.tool_registry import ToolRegistry
from src.domain.diagnosis import RunEventType
from src.domain.main_agent import (
    MAIN_AGENT_CAPABILITY_ID,
    MAIN_AGENT_CAPABILITY_VERSION,
    MAIN_AGENT_RULE_VERSION,
    MainInputSnapshotV1,
    MainMaterialSnapshotV1,
)
from src.tools.text_compare import TextCompareTool

_V2_TOOL_WAIT_SECONDS = 3.0
_DECISION_SUMMARIES = {
    "answer": "决策：普通回答",
    "needs_input": "决策：材料追问",
    "invoke_capability": "决策：能力调用",
}


class MainAgentRunExecutor:
    """把冻结快照装配为一次有界主 Agent 执行；不持有任何持久化端口。"""

    def __init__(
        self,
        *,
        client_factory: Callable[[], LLMClient],
        capabilities: CapabilityRegistry,
        mock_scenario: MainMockScenario | None = None,
    ) -> None:
        self._client_factory = client_factory
        self._capabilities = capabilities
        self._mock_scenario = mock_scenario

    def stream(self, execution_input: RunExecutionInput) -> Iterator[RunSignal]:
        """执行一次 MainAgent Run，输出安全事件与恰好一个终止 signal。"""
        if not isinstance(execution_input, MainAgentRunExecutionInput):
            raise RunExecutionError(RunFailureCode.MAIN_AGENT_FAILED)
        snapshot = execution_input.snapshot
        if snapshot.rule_version != MAIN_AGENT_RULE_VERSION:
            raise RunExecutionError(RunFailureCode.MAIN_AGENT_RULE_UNAVAILABLE)
        capability = self._capabilities.get(
            MAIN_AGENT_CAPABILITY_ID,
            MAIN_AGENT_CAPABILITY_VERSION,
        )
        if capability is None:
            raise RunExecutionError(RunFailureCode.MAIN_AGENT_RULE_UNAVAILABLE)

        try:
            client = self._client_factory()
        except Exception:
            yield _failure(RunFailureCode.MAIN_AGENT_FAILED)
            return
        adapter = MainAgentModelAdapter(client, mock_scenario=self._mock_scenario)
        mode = "mock" if adapter.is_mock else "target"
        registry = _tool_registry(capability, execution_input.run_id, snapshot)
        gateway = ToolGateway(registry, timeout_seconds=_V2_TOOL_WAIT_SECONDS)
        try:
            task = _task(capability, execution_input)
            agent = MainAgent(
                llm=client,
                adapter=adapter,
                tools=registry,
                gateway=gateway,
                capability=capability,
            )
        except (ValidationError, ValueError):
            gateway.shutdown()
            yield _failure(RunFailureCode.MAIN_AGENT_FAILED)
            return

        yield _event(RunEventType.AGENT_START, {"summary": "主 Agent 开始", "mode": mode})
        try:
            outcome = agent.run_task(task)
        finally:
            gateway.shutdown()

        if outcome.decision_kind is not None:
            yield _event(
                RunEventType.ROUTE_DECIDED,
                {"summary": _DECISION_SUMMARIES[outcome.decision_kind], "mode": mode},
            )
        if outcome.tool_invoked:
            yield _event(
                RunEventType.TOOL_INVOKED,
                {"status": _tool_status(outcome), "mode": mode},
            )
        yield _event(
            RunEventType.AGENT_DONE,
            {"summary": "主 Agent 完成" if outcome.delivery is not None else "主 Agent 未生成交付", "mode": mode},
        )
        if outcome.delivery is not None:
            yield RunMainDeliverySignal(delivery=outcome.delivery)
            return
        yield _failure(_failure_code(outcome))


def _tool_registry(
    capability: CapabilityDefinition,
    run_id: UUID,
    snapshot: MainInputSnapshotV1,
) -> ToolRegistry:
    """只注册能力声明的 Tool；材料映射只包含本 Run 冻结材料。"""
    materials: dict[UUID, MainMaterialSnapshotV1] = {}
    if snapshot.text_a is not None:
        materials[snapshot.text_a.material_id] = snapshot.text_a
    if snapshot.text_b is not None:
        materials[snapshot.text_b.material_id] = snapshot.text_b
    registry = ToolRegistry()
    if capability.allowed_tools == (TEXT_COMPARE_TOOL_NAME,):
        registry.register(TextCompareTool(run_id=run_id, materials=materials))
    return registry


def _task(
    capability: CapabilityDefinition,
    execution_input: MainAgentRunExecutionInput,
) -> MainAgentTask:
    """由冻结快照构建 typed 任务；不携带原文。"""
    snapshot = execution_input.snapshot
    return MainAgentTask(
        run_id=execution_input.run_id,
        session_id=execution_input.session_id,
        query=snapshot.query,
        context=snapshot.context,
        material_refs=MainDecisionMaterialRefs(
            text_a=snapshot.text_a.material_id if snapshot.text_a is not None else None,
            text_b=snapshot.text_b.material_id if snapshot.text_b is not None else None,
        ),
        capability_id=MAIN_AGENT_CAPABILITY_ID,
        capability_version=MAIN_AGENT_CAPABILITY_VERSION,
        rule_version=snapshot.rule_version,
        allowed_tools=capability.allowed_tools,
    )


def _tool_status(outcome: MainAgentOutcome) -> str:
    """只把封闭 Tool 状态交给事件投影；未知值统一为 error。"""
    return outcome.tool_status if outcome.tool_status in {"ok", "unavailable", "rejected", "timeout", "error"} else "error"


_FAILURE_CODE_BY_AGENT_FAILURE = {
    MainAgentFailure.MODEL_UNAVAILABLE: RunFailureCode.MAIN_AGENT_MODEL_UNAVAILABLE,
    MainAgentFailure.MODEL_DECISION_INVALID: RunFailureCode.MAIN_AGENT_DECISION_INVALID,
    MainAgentFailure.CAPABILITY_UNAVAILABLE: RunFailureCode.MAIN_AGENT_CAPABILITY_UNAVAILABLE,
    MainAgentFailure.TOOL_FAILED: RunFailureCode.MAIN_AGENT_TOOL_FAILED,
    MainAgentFailure.DELIVERY_INVALID: RunFailureCode.MAIN_AGENT_DELIVERY_INVALID,
}


def _failure_code(outcome: MainAgentOutcome) -> RunFailureCode:
    """把主 Agent 封闭失败映射为固定 Run 失败码；未知失败收敛到兜底码。"""
    if outcome.failure is None:
        return RunFailureCode.MAIN_AGENT_FAILED
    return _FAILURE_CODE_BY_AGENT_FAILURE.get(
        outcome.failure,
        RunFailureCode.MAIN_AGENT_FAILED,
    )


def _event(event_type: RunEventType, data: dict[str, JsonValue]) -> RunEventSignal:
    """构造安全过程事件；data 只含固定摘要、模式与状态。"""
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
