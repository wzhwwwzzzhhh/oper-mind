"""V2 主 Agent 的 typed 输入、ReAct 内核、预算、取消与 Run 生命周期证据。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select

from src.agents.main_agent import MainAgent, MainAgentTask
from src.application.contracts import (
    CreateSessionCommand,
    DiagnosisExecutionEvent,
    DiagnosisExecutionResult,
)
from src.application.errors import IdempotencyKeyReusedError
from src.application.run_execution import (
    CreateMainAgentRunCommand,
    DiagnosisRunExecutionInput,
    LegacyDiagnosisRunAdapter,
    MainAgentInputRejectedError,
    MainAgentRunExecutionInput,
    RunEventSignal,
    RunExecutionError,
    RunFailureCode,
    RunFailureSignal,
    RunMainDeliverySignal,
    build_main_input_snapshot,
    main_agent_create_fingerprint,
    main_agent_rerun_fingerprint,
)
from src.application.runtime_safety import guard_run_stream
from src.application.services import RunApplicationService, SessionApplicationService
from src.capabilities import (
    CapabilityKind,
    CapabilityRegistry,
    ResolutionKind,
    SkillUnavailableError,
    SkillUnavailableReason,
)
from src.capabilities.playbook import (
    READONLY_PLAYBOOK_CAPABILITY,
    READONLY_PLAYBOOK_CAPABILITY_ID,
    READONLY_PLAYBOOK_SKILL_ID,
    READONLY_PLAYBOOK_SKILL_VERSION,
    READONLY_PLAYBOOK_SOURCE,
)
from src.capabilities.text_compare import (
    TEXT_COMPARE_CAPABILITY,
    TEXT_COMPARE_TOOL_NAME,
    compare_materials,
)
from src.core.capability_tools import TextCompareToolBinding, ToolBindingRegistry
from src.core.llm import LLMClient
from src.core.main_agent_budget import MainAgentBudget
from src.core.main_agent_decisions import (
    MainAnswerDecision,
    MainDecisionFailureCode,
    MainDecisionMaterialRefs,
    MainDecisionRequest,
    MainInvokeCapabilityDecision,
    MainLoadSkillDecision,
    MainNeedsInputDecision,
    MainPromptMessage,
    ModelDecisionFailure,
    ModelDecisionResult,
    ModelDecisionSuccess,
)
from src.core.main_agent_model import (
    MOCK_ANSWER_TEXT,
    MOCK_KNOWLEDGE_ANSWER_TEXT,
    MainAgentModelAdapter,
    MainMockScenario,
    parse_main_mock_scenario,
)
from src.core.main_agent_react import (
    MainAgentFailure,
    MainReactKernel,
    MainRouteSignal,
)
from src.core.tool_gateway import GatewayResult, ToolGateway, ToolInvocation
from src.core.tool_registry import ToolRegistry
from src.domain.diagnosis import MessageRole, RunEventType, RunRuntimeKind, RunStatus
from src.domain.main_agent import (
    KNOWLEDGE_GROUNDING_NOTE,
    MAIN_AGENT_RULE_VERSION,
    MAX_KNOWLEDGE_LOADS,
    MAX_MAIN_DECISIONS,
    KnowledgeGroundingV1,
    MainAgentInputUnavailableError,
    MainAnswerDeliveryV1,
    MainComparisonDeliveryV1,
    MainDeliveryV1,
    MainInputSnapshotV1,
    MainInputV1,
    MainMaterialSnapshotV1,
    MainNeedsInputDeliveryV1,
    TextComparisonV1,
    TextDiffBlockV1,
    material_digest,
    normalize_material_text,
)
from src.infrastructure.agent_runtime import MainAgentRunExecutor
from src.infrastructure.agent_runtime.run_executor import _failure_code
from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler
from src.infrastructure.persistence.database import PersistenceRuntime, create_persistence_runtime
from src.infrastructure.persistence.models import DiagnosisRunRecord, MessageRecord, RunInputRecord
from src.infrastructure.persistence.repositories import (
    SqlAlchemyDiagnosisRunRepository,
    SqlAlchemyMessageRepository,
    SqlAlchemyRunEventRepository,
    SqlAlchemyRunInputRepository,
)
from src.infrastructure.persistence.run_delivery_repository import SqlAlchemyRunDeliveryRepository

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def _material(text: str) -> MainMaterialSnapshotV1:
    normalized = normalize_material_text(text)
    return MainMaterialSnapshotV1(
        material_id=uuid4(),
        original_text=text,
        normalized_text=normalized,
        content_sha256=material_digest(normalized),
    )


def _snapshot(text_a: str | None = "旧行", text_b: str | None = "新行") -> MainInputSnapshotV1:
    return MainInputSnapshotV1(
        schema_version=1,
        query="比较两段文本",
        text_a=_material(text_a) if text_a is not None else None,
        text_b=_material(text_b) if text_b is not None else None,
        rule_version=MAIN_AGENT_RULE_VERSION,
    )


def _blocks() -> tuple[TextDiffBlockV1, ...]:
    return (
        TextDiffBlockV1(
            kind="modified",
            a_start=1,
            a_end=1,
            b_start=1,
            b_end=1,
            a_lines=("旧行",),
            b_lines=("新行",),
            a_quote="旧行",
            b_quote="新行",
        ),
    )


def _comparison(snapshot: MainInputSnapshotV1, run_id) -> TextComparisonV1:
    assert snapshot.text_a is not None and snapshot.text_b is not None
    return TextComparisonV1(
        schema_version=1,
        run_id=run_id,
        a_material_id=snapshot.text_a.material_id,
        b_material_id=snapshot.text_b.material_id,
        capability_id="text.literal_compare",
        capability_version=1,
        rule_version=MAIN_AGENT_RULE_VERSION,
        status="has_difference",
        blocks=_blocks(),
    )


def _grounding(version: int = 1) -> KnowledgeGroundingV1:
    return KnowledgeGroundingV1(
        capability_id=READONLY_PLAYBOOK_CAPABILITY_ID,
        capability_version=version,
        skill_id=READONLY_PLAYBOOK_SKILL_ID,
        skill_version=READONLY_PLAYBOOK_SKILL_VERSION,
    )


# ----------------------------------------------------------------------
# 领域契约
# ----------------------------------------------------------------------


def test_main_input_distinguishes_missing_and_explicit_empty_material() -> None:
    missing = MainInputV1(query="比较", text_a=None, text_b="")
    empty = MainInputV1(query="比较", text_a="", text_b="")
    assert missing.text_a is None
    assert missing.text_b == ""
    assert empty.text_a == ""


def test_main_input_normalizes_newlines_and_preserves_trailing_empty_line() -> None:
    snapshot = _snapshot(text_a="a\r\nb\r\n", text_b="a\nb")
    assert snapshot.text_a is not None
    assert snapshot.text_a.normalized_text == "a\nb\n"
    assert snapshot.text_a.normalized_text.split("\n") == ["a", "b", ""]


@pytest.mark.parametrize(
    ("query", "text_a"),
    [
        ("x" * 201, "ok"),
        ("比较", "x" * 2001),
        ("比较", "\n".join("x" for _ in range(101))),
    ],
)
def test_main_input_rejects_over_limit(query: str, text_a: str) -> None:
    with pytest.raises(ValidationError):
        MainInputV1(query=query, text_a=text_a)


def test_main_input_rejects_unpaired_surrogate() -> None:
    with pytest.raises(ValidationError):
        MainInputV1(query="比较", text_a="\ud800")


def test_snapshot_rejects_tampered_digest_and_unknown_rule() -> None:
    material = _material("文本")
    with pytest.raises(ValidationError):
        MainMaterialSnapshotV1(
            material_id=material.material_id,
            original_text=material.original_text,
            normalized_text=material.normalized_text,
            content_sha256="0" * 64,
        )
    with pytest.raises(ValidationError):
        MainInputSnapshotV1(
            schema_version=1,
            query="比较",
            text_a=material,
            text_b=None,
            rule_version="literal-lines@2",
        )


def test_delivery_discriminator_rejects_unknown_or_extra_fields() -> None:
    adapter = TypeAdapter(MainDeliveryV1)
    answer = adapter.validate_python({"kind": "answer", "text": "普通回答"})
    assert answer == MainAnswerDeliveryV1(text="普通回答")
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "unknown", "text": "x"})
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "answer", "text": "x", "extra": True})


def test_knowledge_grounding_is_fixed_and_round_trips_through_union() -> None:
    delivery = MainAnswerDeliveryV1(text="知识辅助回答", knowledge_grounding=_grounding())
    adapter = TypeAdapter(MainDeliveryV1)
    assert adapter.validate_python(delivery.model_dump(mode="json")) == delivery
    with pytest.raises(ValidationError):
        KnowledgeGroundingV1(
            capability_id=READONLY_PLAYBOOK_CAPABILITY_ID,
            capability_version=1,
            skill_id=READONLY_PLAYBOOK_SKILL_ID,
            skill_version=1,
            data_access="read_only",
        )
    with pytest.raises(ValidationError):
        KnowledgeGroundingV1.model_validate(
            {**_grounding().model_dump(mode="json"), "note": "已读取实时数据"}
        )


def test_comparison_requires_both_materials_and_consistent_blocks() -> None:
    snapshot = _snapshot()
    run_id = uuid4()
    comparison = _comparison(snapshot, run_id)
    assert comparison.status == "has_difference"
    with pytest.raises(ValidationError):
        TextComparisonV1(
            schema_version=1,
            run_id=run_id,
            a_material_id=comparison.a_material_id,
            b_material_id=comparison.b_material_id,
            capability_id="text.literal_compare",
            capability_version=1,
            rule_version=MAIN_AGENT_RULE_VERSION,
            status="no_difference",
            blocks=_blocks(),
        )
    with pytest.raises(ValidationError):
        TextDiffBlockV1(
            kind="modified",
            a_start=1,
            a_end=1,
            b_start=1,
            b_end=1,
            a_lines=("旧行",),
            b_lines=("新行",),
            a_quote="被篡改",
            b_quote="新行",
        )


def test_needs_input_requires_unique_missing_sides() -> None:
    assert MainNeedsInputDeliveryV1(
        missing=("text_a", "text_b"),
        prompt="请补充 A／B 原文",
    ).missing == ("text_a", "text_b")
    with pytest.raises(ValidationError):
        MainNeedsInputDeliveryV1(missing=("text_a", "text_a"), prompt="请补充")


# ----------------------------------------------------------------------
# 持久化与 Run 生命周期
# ----------------------------------------------------------------------


@pytest.fixture
def persistence_runtime(tmp_path: Path) -> Iterator[PersistenceRuntime]:
    """在独立临时 SQLite 中执行 migration 并返回应用持久化运行时。"""
    database_path = tmp_path / "main-agent.sqlite3"
    environment = os.environ.copy()
    environment.update(
        {
            "OPERMIND_APP_DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "OPERMIND_API_KEY": "mock",
            "OPERMIND_BASE_URL": "http://mock",
            "OPERMIND_MODEL": "mock",
            "PYTHONPATH": os.pathsep.join([str(BACKEND_ROOT), str(PROJECT_ROOT), environment.get("PYTHONPATH", "")]),
        }
    )
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    runtime = create_persistence_runtime(f"sqlite:///{database_path.as_posix()}")
    try:
        yield runtime
    finally:
        runtime.engine.dispose()


class _UnusedDiagnosisExecutor:
    """主 Agent 用例不得回落到 legacy 诊断执行器。"""

    def stream(self, _query: str) -> Iterator[object]:
        raise AssertionError("主 Agent 用例不得走 legacy 诊断执行器")
        yield


class _StubRunExecutor:
    """输出固定 typed signal 并记录收到的执行输入。"""

    def __init__(self, signals: tuple[object, ...] = ()) -> None:
        self._signals = signals
        self.inputs: list[object] = []

    def stream(self, execution_input: object) -> Iterator[object]:
        self.inputs.append(execution_input)
        yield from self._signals


class _CapturingDiagnosisExecutor:
    """记录 legacy query/service 调用的确定性执行器。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def stream(
        self,
        query: str,
        service_id: str | None = None,
    ) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        self.calls.append((query, service_id))
        yield _event()
        yield DiagnosisExecutionResult(strategy="direct")


def _event(event_type: RunEventType = RunEventType.AGENT_START) -> DiagnosisExecutionEvent:
    return DiagnosisExecutionEvent(
        type=event_type,
        node="main_agent",
        occurred_at=datetime.now(UTC),
        data={"scope": "test"},
    )


def _run_service(
    runtime: PersistenceRuntime,
    run_executor: object | None = None,
    capabilities: CapabilityRegistry | None = None,
) -> RunApplicationService:
    return RunApplicationService(
        runtime.session_factory,
        _UnusedDiagnosisExecutor(),  # type: ignore[arg-type]
        ConservativeResultAssembler(),
        run_executor=run_executor,  # type: ignore[arg-type]
        capability_ids=capabilities.capability_ids() if capabilities is not None else frozenset(),
        capabilities=capabilities,
    )


def _new_session(runtime: PersistenceRuntime) -> UUID:
    return SessionApplicationService(runtime.session_factory).create_session(
        CreateSessionCommand(title="主 Agent 用例")
    ).id


def _accept_main(
    service: RunApplicationService,
    session_id: UUID,
    *,
    value: MainInputV1 | None = None,
    key: UUID | None = None,
):
    return service.accept_main_agent_run(
        CreateMainAgentRunCommand(
            session_id=session_id,
            idempotency_key=key or uuid4(),
            input=value or MainInputV1(query="请比较两段文本", text_a="旧行", text_b="新行"),
        )
    )


def _load_run(runtime: PersistenceRuntime, run_id: UUID):
    session = runtime.session_factory()
    try:
        run = SqlAlchemyDiagnosisRunRepository(session).get_by_id(run_id)
        assert run is not None
        return run
    finally:
        session.close()


def _load_snapshot(runtime: PersistenceRuntime, run_id: UUID) -> MainInputSnapshotV1:
    session = runtime.session_factory()
    try:
        snapshot = SqlAlchemyRunInputRepository(session).get_by_run_id(run_id)
        assert snapshot is not None
        return snapshot
    finally:
        session.close()


def _load_delivery(runtime: PersistenceRuntime, run_id: UUID) -> MainDeliveryV1 | None:
    session = runtime.session_factory()
    try:
        return SqlAlchemyRunDeliveryRepository(session).get_by_run_id(run_id)
    finally:
        session.close()


def _messages(runtime: PersistenceRuntime, session_id: UUID):
    session = runtime.session_factory()
    try:
        return list(SqlAlchemyMessageRepository(session).list_by_session(session_id, cursor=None, limit=20).items)
    finally:
        session.close()


def _events(runtime: PersistenceRuntime, run_id: UUID):
    session = runtime.session_factory()
    try:
        return list(SqlAlchemyRunEventRepository(session).list_by_run(run_id, cursor=None, limit=50).items)
    finally:
        session.close()


def test_accept_main_agent_run_freezes_input_and_replays_same_key(
    persistence_runtime: PersistenceRuntime,
) -> None:
    service = _run_service(persistence_runtime)
    session_id = _new_session(persistence_runtime)
    key = uuid4()
    value = MainInputV1(query="请比较", text_a="旧行", text_b="新行")

    accepted = _accept_main(service, session_id, value=value, key=key)
    assert accepted.run.runtime_kind is RunRuntimeKind.MAIN_AGENT
    assert accepted.run.status is RunStatus.QUEUED
    assert accepted.replayed is False

    snapshot = _load_snapshot(persistence_runtime, accepted.run.id)
    assert snapshot.query == "请比较"
    assert snapshot.text_a is not None and snapshot.text_a.original_text == "旧行"
    assert snapshot.text_b is not None and snapshot.text_b.original_text == "新行"
    assert snapshot.text_a.material_id != snapshot.text_b.material_id
    assert snapshot.rule_version == MAIN_AGENT_RULE_VERSION

    messages = _messages(persistence_runtime, session_id)
    assert [(message.role, message.content) for message in messages] == [(MessageRole.USER, "请比较")]

    replay = _accept_main(service, session_id, value=value, key=key)
    assert replay.replayed is True
    assert replay.run.id == accepted.run.id
    assert len(_messages(persistence_runtime, session_id)) == 1

    with pytest.raises(IdempotencyKeyReusedError):
        _accept_main(
            service,
            session_id,
            value=MainInputV1(query="另一个目标", text_a="旧行", text_b="新行"),
            key=key,
        )


def test_accept_main_agent_run_rejects_sensitive_input_before_any_write(
    persistence_runtime: PersistenceRuntime,
) -> None:
    service = _run_service(persistence_runtime)
    session_id = _new_session(persistence_runtime)

    with pytest.raises(MainAgentInputRejectedError):
        _accept_main(
            service,
            session_id,
            value=MainInputV1(query="请比较", text_a="sk-abcdef123456", text_b="新行"),
        )

    session = persistence_runtime.session_factory()
    try:
        assert session.scalar(select(func.count()).select_from(DiagnosisRunRecord)) == 0
    finally:
        session.close()
    assert _messages(persistence_runtime, session_id) == []


def test_main_agent_answer_delivery_writes_unique_facts_once(
    persistence_runtime: PersistenceRuntime,
) -> None:
    executor = _StubRunExecutor(
        (
            RunEventSignal(event=_event()),
            RunMainDeliverySignal(delivery=MainAnswerDeliveryV1(text="这是普通回答，未执行文本比较。")),
        )
    )
    service = _run_service(persistence_runtime, executor)
    session_id = _new_session(persistence_runtime)
    accepted = _accept_main(service, session_id)

    finished = service.execute_run(accepted.run.id)
    assert finished.status is RunStatus.SUCCEEDED
    assert len(executor.inputs) == 1
    execution_input = executor.inputs[0]
    assert isinstance(execution_input, MainAgentRunExecutionInput)
    assert execution_input.snapshot.text_a is not None
    assert execution_input.snapshot.text_a.original_text == "旧行"

    assert _load_delivery(persistence_runtime, accepted.run.id) == MainAnswerDeliveryV1(
        text="这是普通回答，未执行文本比较。"
    )
    messages = _messages(persistence_runtime, session_id)
    assistants = [message for message in messages if message.role is MessageRole.ASSISTANT]
    assert len(assistants) == 1
    assert assistants[0].run_id == accepted.run.id
    assert assistants[0].content == "这是普通回答，未执行文本比较。"
    events = _events(persistence_runtime, accepted.run.id)
    assert [event.type for event in events] == [
        RunEventType.RUN_QUEUED,
        RunEventType.RUN_STARTED,
        RunEventType.AGENT_START,
        RunEventType.RUN_SUCCEEDED,
    ]
    assert [event.sequence for event in events] == [1, 2, 3, 4]

    again = service.execute_run(accepted.run.id)
    assert again.status is RunStatus.SUCCEEDED
    assert len(executor.inputs) == 1
    assert len(_messages(persistence_runtime, session_id)) == 2


def test_main_agent_needs_input_requires_snapshot_derived_missing_sides(
    persistence_runtime: PersistenceRuntime,
) -> None:
    value = MainInputV1(query="请比较", text_a=None, text_b="新行")
    prompt = "请提供文本 A（旧），我会做逐行字面比较。"

    accepted_executor = _StubRunExecutor(
        (RunMainDeliverySignal(delivery=MainNeedsInputDeliveryV1(missing=("text_a",), prompt=prompt)),)
    )
    service = _run_service(persistence_runtime, accepted_executor)
    session_id = _new_session(persistence_runtime)
    accepted = _accept_main(service, session_id, value=value)
    assert service.execute_run(accepted.run.id).status is RunStatus.SUCCEEDED
    assistants = [message for message in _messages(persistence_runtime, session_id) if message.role is MessageRole.ASSISTANT]
    assert [message.content for message in assistants] == [prompt]

    rejected_executor = _StubRunExecutor(
        (RunMainDeliverySignal(delivery=MainNeedsInputDeliveryV1(missing=("text_b",), prompt=prompt)),)
    )
    rejected_service = _run_service(persistence_runtime, rejected_executor)
    rejected_session = _new_session(persistence_runtime)
    rejected = _accept_main(rejected_service, rejected_session, value=value)
    failed = rejected_service.execute_run(rejected.run.id)
    assert failed.status is RunStatus.FAILED
    assert failed.error_code == RunFailureCode.MAIN_AGENT_DELIVERY_INVALID.value
    assert failed.error_message == RunFailureCode.MAIN_AGENT_DELIVERY_INVALID.safe_message
    assert _load_delivery(persistence_runtime, rejected.run.id) is None
    assert [message for message in _messages(persistence_runtime, rejected_session) if message.role is MessageRole.ASSISTANT] == []
    assert _events(persistence_runtime, rejected.run.id)[-1].type is RunEventType.RUN_FAILED


def test_knowledge_answer_is_prefixed_and_persisted_with_grounding(
    persistence_runtime: PersistenceRuntime,
) -> None:
    capabilities = _capabilities()
    delivery = MainAnswerDeliveryV1(text="先按手册检查。", knowledge_grounding=_grounding())
    executor = _StubRunExecutor((RunMainDeliverySignal(delivery=delivery),))
    service = _run_service(persistence_runtime, executor, capabilities)
    session_id = _new_session(persistence_runtime)
    accepted = _accept_main(service, session_id)

    assert service.execute_run(accepted.run.id).status is RunStatus.SUCCEEDED
    assert _load_delivery(persistence_runtime, accepted.run.id) == delivery
    assistants = [message for message in _messages(persistence_runtime, session_id) if message.role is MessageRole.ASSISTANT]
    assert [message.content for message in assistants] == [f"{KNOWLEDGE_GROUNDING_NOTE}\n\n先按手册检查。"]


def test_knowledge_grounding_is_rechecked_in_write_transaction(
    persistence_runtime: PersistenceRuntime,
) -> None:
    capabilities = _capabilities()
    service = _run_service(persistence_runtime, _StubRunExecutor(), capabilities)
    session_id = _new_session(persistence_runtime)

    for forged in (
        MainAnswerDeliveryV1(text="回答", knowledge_grounding=_grounding().model_copy(update={"skill_version": 2})),
        MainAnswerDeliveryV1(
            text="回答",
            knowledge_grounding=_grounding().model_copy(update={"capability_version": 2}),
        ),
        MainAnswerDeliveryV1(
            text="回答",
            knowledge_grounding=_grounding().model_copy(update={"capability_id": "ops.unknown"}),
        ),
    ):
        accepted = _accept_main(service, session_id)
        rejected_service = _run_service(
            persistence_runtime,
            _StubRunExecutor((RunMainDeliverySignal(delivery=forged),)),
            capabilities,
        )
        failed = rejected_service.execute_run(accepted.run.id)
        assert failed.status is RunStatus.FAILED
        assert failed.error_code == RunFailureCode.MAIN_AGENT_DELIVERY_INVALID.value
        assert _load_delivery(persistence_runtime, accepted.run.id) is None

    unregistered = _accept_main(service, session_id)
    without_registry = _run_service(
        persistence_runtime,
        _StubRunExecutor((RunMainDeliverySignal(delivery=MainAnswerDeliveryV1(text="回答", knowledge_grounding=_grounding())),)),
    )
    failed = without_registry.execute_run(unregistered.run.id)
    assert failed.status is RunStatus.FAILED
    assert failed.error_code == RunFailureCode.MAIN_AGENT_DELIVERY_INVALID.value


def _comparison_for(
    snapshot: MainInputSnapshotV1,
    run_id: UUID,
    *,
    a_lines: tuple[str, ...] = ("旧行",),
    b_lines: tuple[str, ...] = ("新行",),
) -> TextComparisonV1:
    assert snapshot.text_a is not None and snapshot.text_b is not None
    return TextComparisonV1(
        schema_version=1,
        run_id=run_id,
        a_material_id=snapshot.text_a.material_id,
        b_material_id=snapshot.text_b.material_id,
        capability_id="text.literal_compare",
        capability_version=1,
        rule_version=MAIN_AGENT_RULE_VERSION,
        status="has_difference",
        blocks=(
            TextDiffBlockV1(
                kind="modified",
                a_start=1,
                a_end=1,
                b_start=1,
                b_end=1,
                a_lines=a_lines,
                b_lines=b_lines,
                a_quote="\n".join(a_lines),
                b_quote="\n".join(b_lines),
            ),
        ),
    )


def test_main_agent_comparison_is_rejected_when_quote_does_not_match_snapshot(
    persistence_runtime: PersistenceRuntime,
) -> None:
    service = _run_service(persistence_runtime)
    session_id = _new_session(persistence_runtime)
    accepted = _accept_main(service, session_id)
    snapshot = _load_snapshot(persistence_runtime, accepted.run.id)
    executor = _StubRunExecutor(
        (
            RunMainDeliverySignal(
                delivery=MainComparisonDeliveryV1(
                    comparison=_comparison_for(snapshot, accepted.run.id, a_lines=("被篡改",))
                )
            ),
        )
    )
    service = _run_service(persistence_runtime, executor)

    failed = service.execute_run(accepted.run.id)
    assert failed.status is RunStatus.FAILED
    assert failed.error_code == RunFailureCode.MAIN_AGENT_DELIVERY_INVALID.value
    assert _load_delivery(persistence_runtime, accepted.run.id) is None
    assert [message for message in _messages(persistence_runtime, session_id) if message.role is MessageRole.ASSISTANT] == []


def test_main_agent_comparison_delivery_persists_verified_blocks(
    persistence_runtime: PersistenceRuntime,
) -> None:
    service = _run_service(persistence_runtime)
    session_id = _new_session(persistence_runtime)
    accepted = _accept_main(service, session_id)
    snapshot = _load_snapshot(persistence_runtime, accepted.run.id)
    delivery = MainComparisonDeliveryV1(comparison=_comparison_for(snapshot, accepted.run.id))
    executor = _StubRunExecutor((RunMainDeliverySignal(delivery=delivery),))
    service = _run_service(persistence_runtime, executor)

    finished = service.execute_run(accepted.run.id)
    assert finished.status is RunStatus.SUCCEEDED
    assert _load_delivery(persistence_runtime, accepted.run.id) == delivery
    assistants = [message for message in _messages(persistence_runtime, session_id) if message.role is MessageRole.ASSISTANT]
    assert [message.content for message in assistants] == ["文本比较完成：共 1 个差异块。"]


def test_main_agent_rerun_copies_frozen_input_with_new_material_ids(
    persistence_runtime: PersistenceRuntime,
) -> None:
    executor = _StubRunExecutor((RunMainDeliverySignal(delivery=MainAnswerDeliveryV1(text="首次回答")),))
    service = _run_service(persistence_runtime, executor)
    session_id = _new_session(persistence_runtime)
    accepted = _accept_main(service, session_id)
    assert service.execute_run(accepted.run.id).status is RunStatus.SUCCEEDED

    rerun_key = uuid4()
    rerun = service.rerun_run(accepted.run.id, rerun_key)
    assert rerun.replayed is False
    assert rerun.run.rerun_of_run_id == accepted.run.id
    assert rerun.run.runtime_kind is RunRuntimeKind.MAIN_AGENT
    assert rerun.run.status is RunStatus.QUEUED

    original_snapshot = _load_snapshot(persistence_runtime, accepted.run.id)
    rerun_snapshot = _load_snapshot(persistence_runtime, rerun.run.id)
    assert rerun_snapshot.query == original_snapshot.query
    assert rerun_snapshot.rule_version == original_snapshot.rule_version
    assert rerun_snapshot.context == original_snapshot.context
    assert original_snapshot.text_a is not None and rerun_snapshot.text_a is not None
    assert original_snapshot.text_b is not None and rerun_snapshot.text_b is not None
    assert rerun_snapshot.text_a.original_text == original_snapshot.text_a.original_text
    assert rerun_snapshot.text_b.original_text == original_snapshot.text_b.original_text
    assert rerun_snapshot.text_a.material_id != original_snapshot.text_a.material_id
    assert rerun_snapshot.text_b.material_id != original_snapshot.text_b.material_id
    user_messages = [message for message in _messages(persistence_runtime, session_id) if message.role is MessageRole.USER]
    assert [message.content for message in user_messages] == ["请比较两段文本", "请比较两段文本"]
    assert len({message.id for message in user_messages}) == 2

    replay = service.rerun_run(accepted.run.id, rerun_key)
    assert replay.replayed is True
    assert replay.run.id == rerun.run.id


def test_main_agent_run_without_typed_executor_fails_safe(
    persistence_runtime: PersistenceRuntime,
) -> None:
    service = _run_service(persistence_runtime)
    session_id = _new_session(persistence_runtime)
    accepted = _accept_main(service, session_id)

    failed = service.execute_run(accepted.run.id)
    assert failed.status is RunStatus.FAILED
    assert failed.error_code == RunFailureCode.MAIN_AGENT_FAILED.value
    assert failed.error_message == RunFailureCode.MAIN_AGENT_FAILED.safe_message
    assert _load_delivery(persistence_runtime, accepted.run.id) is None
    assert [message for message in _messages(persistence_runtime, session_id) if message.role is MessageRole.ASSISTANT] == []


class _CancelThenDeliverExecutor:
    """在交付前触发取消，验证取消胜出后不写交付。"""

    def __init__(self) -> None:
        self.cancel = None
        self.delivery = MainAnswerDeliveryV1(text="取消后不得交付")

    def stream(self, execution_input: MainAgentRunExecutionInput) -> Iterator[object]:
        assert self.cancel is not None
        self.cancel(execution_input.run_id)
        yield RunMainDeliverySignal(delivery=self.delivery)


class _CancelThenEventExecutor:
    """在普通事件前触发取消，验证 running 谓词拒绝迟到事件。"""

    def __init__(self) -> None:
        self.cancel = None

    def stream(self, execution_input: MainAgentRunExecutionInput) -> Iterator[object]:
        assert self.cancel is not None
        self.cancel(execution_input.run_id)
        yield RunEventSignal(event=_event())


def test_main_agent_cancel_before_delivery_keeps_cancelled_terminal(
    persistence_runtime: PersistenceRuntime,
) -> None:
    executor = _CancelThenDeliverExecutor()
    service = _run_service(persistence_runtime, executor)
    executor.cancel = service.cancel_run
    session_id = _new_session(persistence_runtime)
    accepted = _accept_main(service, session_id)

    finished = service.execute_run(accepted.run.id)
    assert finished.status is RunStatus.CANCELLED
    assert _load_delivery(persistence_runtime, accepted.run.id) is None
    assert [message for message in _messages(persistence_runtime, session_id) if message.role is MessageRole.ASSISTANT] == []
    assert [event.type for event in _events(persistence_runtime, accepted.run.id)] == [
        RunEventType.RUN_QUEUED,
        RunEventType.RUN_STARTED,
        RunEventType.RUN_CANCELLED,
    ]


def test_main_agent_event_after_cancel_is_discarded(
    persistence_runtime: PersistenceRuntime,
) -> None:
    executor = _CancelThenEventExecutor()
    service = _run_service(persistence_runtime, executor)
    executor.cancel = service.cancel_run
    session_id = _new_session(persistence_runtime)
    accepted = _accept_main(service, session_id)

    finished = service.execute_run(accepted.run.id)
    assert finished.status is RunStatus.CANCELLED
    assert [event.type for event in _events(persistence_runtime, accepted.run.id)] == [
        RunEventType.RUN_QUEUED,
        RunEventType.RUN_STARTED,
        RunEventType.RUN_CANCELLED,
    ]


def test_corrupt_or_unknown_run_input_fails_safe(
    persistence_runtime: PersistenceRuntime,
) -> None:
    service = _run_service(persistence_runtime, _StubRunExecutor())
    session_id = _new_session(persistence_runtime)
    unknown_version = _accept_main(service, session_id)
    corrupt_payload = _accept_main(service, session_id)

    session = persistence_runtime.session_factory()
    try:
        unknown_record = session.get(RunInputRecord, unknown_version.run.id)
        assert unknown_record is not None
        unknown_record.schema_version = 2
        corrupt_record = session.get(RunInputRecord, corrupt_payload.run.id)
        assert corrupt_record is not None
        corrupt_record.payload = {
            "schema_version": 1,
            "query": "请比较",
            "rule_version": MAIN_AGENT_RULE_VERSION,
            "unexpected": True,
        }
        session.commit()
    finally:
        session.close()

    for accepted in (unknown_version, corrupt_payload):
        failed = service.execute_run(accepted.run.id)
        assert failed.status is RunStatus.FAILED
        assert failed.error_code == RunFailureCode.MAIN_AGENT_INPUT_UNAVAILABLE.value
        assert failed.error_message == RunFailureCode.MAIN_AGENT_INPUT_UNAVAILABLE.safe_message
        assert _load_delivery(persistence_runtime, accepted.run.id) is None

    session = persistence_runtime.session_factory()
    try:
        with pytest.raises(MainAgentInputUnavailableError):
            SqlAlchemyRunInputRepository(session).get_by_run_id(unknown_version.run.id)
    finally:
        session.close()


def test_create_and_rerun_fingerprints_distinguish_missing_empty_and_source() -> None:
    missing = MainInputV1(query="请比较", text_a=None, text_b="新行")
    empty = MainInputV1(query="请比较", text_a="", text_b="新行")
    assert main_agent_create_fingerprint(missing) != main_agent_create_fingerprint(empty)

    snapshot = build_main_input_snapshot(MainInputV1(query="请比较", text_a="旧行", text_b="新行"))
    source = uuid4()
    assert main_agent_rerun_fingerprint(source, snapshot) != main_agent_rerun_fingerprint(uuid4(), snapshot)


def test_guard_run_stream_requires_single_terminal_at_normal_eof() -> None:
    event_only = list(
        guard_run_stream(
            lambda: iter([RunEventSignal(event=_event())]),
            default_failure=RunFailureCode.MAIN_AGENT_FAILED,
        )
    )
    assert [type(signal) for signal in event_only] == [RunEventSignal, RunFailureSignal]
    assert event_only[-1].code is RunFailureCode.MAIN_AGENT_FAILED

    terminal_then_event = list(
        guard_run_stream(
            lambda: iter(
                [
                    RunMainDeliverySignal(delivery=MainAnswerDeliveryV1(text="回答")),
                    RunEventSignal(event=_event()),
                ]
            ),
            default_failure=RunFailureCode.MAIN_AGENT_FAILED,
        )
    )
    assert [type(signal) for signal in terminal_then_event] == [RunFailureSignal]
    assert terminal_then_event[0].code is RunFailureCode.MAIN_AGENT_FAILED

    unknown_object = list(
        guard_run_stream(lambda: iter([object()]), default_failure=RunFailureCode.MAIN_AGENT_DELIVERY_INVALID)
    )
    assert [type(signal) for signal in unknown_object] == [RunFailureSignal]
    assert unknown_object[0].code is RunFailureCode.MAIN_AGENT_DELIVERY_INVALID


def test_guard_run_stream_maps_exceptions_to_closed_codes() -> None:
    def raise_safe() -> Iterator[object]:
        raise RunExecutionError(RunFailureCode.MAIN_AGENT_DELIVERY_INVALID)
        yield

    preserved = list(guard_run_stream(raise_safe, default_failure=RunFailureCode.MAIN_AGENT_FAILED))
    assert [type(signal) for signal in preserved] == [RunFailureSignal]
    assert preserved[0].code is RunFailureCode.MAIN_AGENT_DELIVERY_INVALID

    def terminal_then_raise() -> Iterator[object]:
        yield RunMainDeliverySignal(delivery=MainAnswerDeliveryV1(text="回答"))
        raise RunExecutionError(RunFailureCode.MAIN_AGENT_DELIVERY_INVALID)

    downgraded = list(guard_run_stream(terminal_then_raise, default_failure=RunFailureCode.MAIN_AGENT_FAILED))
    assert [type(signal) for signal in downgraded] == [RunFailureSignal]
    assert downgraded[0].code is RunFailureCode.MAIN_AGENT_FAILED


def test_legacy_adapter_preserves_query_and_service() -> None:
    executor = _CapturingDiagnosisExecutor()
    adapter = LegacyDiagnosisRunAdapter(executor)

    signals = list(adapter.stream(DiagnosisRunExecutionInput(query="订单服务变慢", service_id="svc.postgres")))

    assert executor.calls == [("订单服务变慢", "svc.postgres")]
    assert [signal.kind for signal in signals] == ["event", "diagnosis_result"]


# ----------------------------------------------------------------------
# 模型边界与 mock 场景
# ----------------------------------------------------------------------


class _ScriptedClient:
    """按顺序返回固定响应的非 mock 模型替身；记录完整请求供安全断言。"""

    def __init__(self, responses: tuple[dict, ...]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    @property
    def is_mock(self) -> bool:
        return False

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **_kwargs: object,
    ) -> dict:
        self.calls.append({"messages": messages, "tools": tools})
        if not self._responses:
            return {"role": "assistant", "content": "", "error": "LLM_UNAVAILABLE"}
        return self._responses.pop(0)


def _capabilities() -> CapabilityRegistry:
    return CapabilityRegistry([TEXT_COMPARE_CAPABILITY, READONLY_PLAYBOOK_CAPABILITY])


def _mock_client() -> LLMClient:
    return LLMClient(api_key="mock", base_url="http://mock", model="mock")


def _mock_executor(
    scenario: MainMockScenario | None,
    *,
    capabilities: CapabilityRegistry | None = None,
    is_cancelled: Callable[[UUID], bool] | None = None,
) -> MainAgentRunExecutor:
    return MainAgentRunExecutor(
        client_factory=lambda _timeout: _mock_client(),
        capabilities=capabilities or _capabilities(),
        mock_scenario=scenario,
        is_cancelled=is_cancelled,
    )


def _scripted_executor(
    responses: tuple[dict, ...],
    *,
    capabilities: CapabilityRegistry | None = None,
    skill_source: object | None = None,
    tool_bindings: ToolBindingRegistry | None = None,
    is_cancelled: Callable[[UUID], bool] | None = None,
) -> tuple[MainAgentRunExecutor, _ScriptedClient]:
    client = _ScriptedClient(responses)
    kwargs: dict = {}
    if skill_source is not None:
        kwargs["skill_source"] = skill_source
    if tool_bindings is not None:
        kwargs["tool_bindings"] = tool_bindings
    executor = MainAgentRunExecutor(
        client_factory=lambda _timeout: client,  # type: ignore[arg-type,return-value]
        capabilities=capabilities or _capabilities(),
        is_cancelled=is_cancelled,
        **kwargs,
    )
    return executor, client


def _json_response(payload: dict) -> dict:
    return {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)}


def _decision_request(
    refs: MainDecisionMaterialRefs,
    *,
    content: str = "请比较两段文本",
    observation_count: int = 0,
) -> MainDecisionRequest:
    return MainDecisionRequest(
        messages=(MainPromptMessage(role="user", content=content),),
        material_refs=refs,
        observation_count=observation_count,
    )


def _refs_for(snapshot: MainInputSnapshotV1) -> MainDecisionMaterialRefs:
    return MainDecisionMaterialRefs(
        text_a=snapshot.text_a.material_id if snapshot.text_a is not None else None,
        text_b=snapshot.text_b.material_id if snapshot.text_b is not None else None,
    )


def _invoke_payload(refs: MainDecisionMaterialRefs) -> dict:
    return {
        "kind": "invoke_capability",
        "capability_id": "text.literal_compare",
        "capability_version": 1,
        "inputs": {
            "text_a": str(refs.text_a),
            "text_b": str(refs.text_b),
        },
    }


def _main_task(
    run_id: UUID,
    refs: MainDecisionMaterialRefs,
    **overrides: object,
) -> MainAgentTask:
    values: dict = {
        "run_id": run_id,
        "session_id": uuid4(),
        "query": "请比较两段文本",
        "material_refs": refs,
    }
    values.update(overrides)
    return MainAgentTask(**values)


def test_model_adapter_returns_typed_answer_without_tools() -> None:
    refs = MainDecisionMaterialRefs(text_a=uuid4(), text_b=uuid4())
    client = _ScriptedClient((_json_response({"kind": "answer", "text": "普通回答"}),))
    adapter = MainAgentModelAdapter(client)  # type: ignore[arg-type]

    result = adapter.decide(_decision_request(refs))

    assert result.outcome == "success"
    assert result.decision.kind == "answer"
    assert result.decision.text == "普通回答"
    assert client.calls[0]["tools"] is None


@pytest.mark.parametrize(
    "content",
    [
        "不是 JSON",
        "[]",
        '{"kind": "answer"}',
        '{"kind": "answer", "text": "x", "extra": true}',
        '{"kind": "unknown", "text": "x"}',
        '{"kind": "needs_input", "slots": ["text_a", "text_a"]}',
        '{"kind": "invoke_capability", "capability_id": "x.y", "capability_version": 1, "inputs": {"text_a": "not-a-uuid"}}',
    ],
)
def test_model_adapter_rejects_invalid_json_or_schema(content: str) -> None:
    refs = MainDecisionMaterialRefs(text_a=uuid4(), text_b=uuid4())
    client = _ScriptedClient(({"role": "assistant", "content": content},))
    adapter = MainAgentModelAdapter(client)  # type: ignore[arg-type]

    result = adapter.decide(_decision_request(refs))

    assert result.outcome == "failure"
    assert result.code is MainDecisionFailureCode.MODEL_DECISION_INVALID


@pytest.mark.parametrize(
    "response",
    [
        {"role": "assistant", "content": "调用失败", "error": "LLM_UNAVAILABLE"},
        {"role": "assistant", "content": None},
        {"role": "assistant", "content": ""},
    ],
)
def test_model_adapter_maps_call_or_content_failure_to_unavailable(response: dict) -> None:
    refs = MainDecisionMaterialRefs()
    client = _ScriptedClient((response,))
    adapter = MainAgentModelAdapter(client)  # type: ignore[arg-type]

    result = adapter.decide(_decision_request(refs))

    assert result.outcome == "failure"
    assert result.code is MainDecisionFailureCode.MODEL_UNAVAILABLE


def test_model_adapter_close_factory_clips_each_call() -> None:
    timeouts: list[float] = []

    class _TimeoutClient(_ScriptedClient):
        def __init__(self) -> None:
            super().__init__((_json_response({"kind": "answer", "text": "回答"}),))

    client = _TimeoutClient()

    def factory(timeout: float) -> _ScriptedClient:
        timeouts.append(timeout)
        return client

    adapter = MainAgentModelAdapter(client_factory=factory)  # type: ignore[arg-type]
    result = adapter.decide(_decision_request(MainDecisionMaterialRefs()), 3.5)

    assert result.outcome == "success"
    assert timeouts == [3.5]
    assert adapter.is_mock is False


def test_mock_scenarios_are_explicit_and_not_inferred_from_query() -> None:
    refs = MainDecisionMaterialRefs(text_a=uuid4(), text_b=uuid4())
    request = _decision_request(refs, content="请比较两段文本并给出差异")

    assert parse_main_mock_scenario(None) is None
    assert parse_main_mock_scenario("unknown") is None
    undeclared = MainAgentModelAdapter(_mock_client()).decide(request)
    assert undeclared.outcome == "failure"
    assert undeclared.code is MainDecisionFailureCode.MODEL_UNAVAILABLE

    answer = MainAgentModelAdapter(_mock_client(), mock_scenario=MainMockScenario.ANSWER).decide(request)
    assert answer.outcome == "success"
    assert answer.decision.text == MOCK_ANSWER_TEXT

    compare = MainAgentModelAdapter(_mock_client(), mock_scenario=MainMockScenario.COMPARE).decide(request)
    assert compare.outcome == "success"
    assert isinstance(compare.decision, MainInvokeCapabilityDecision)
    assert compare.decision.inputs == {"text_a": str(refs.text_a), "text_b": str(refs.text_b)}

    needs = MainAgentModelAdapter(_mock_client(), mock_scenario=MainMockScenario.NEEDS_INPUT).decide(request)
    assert needs.outcome == "failure"
    assert needs.code is MainDecisionFailureCode.MODEL_UNAVAILABLE

    missing_request = _decision_request(MainDecisionMaterialRefs(text_a=refs.text_a, text_b=None))
    needs = MainAgentModelAdapter(_mock_client(), mock_scenario=MainMockScenario.NEEDS_INPUT).decide(missing_request)
    assert needs.outcome == "success"
    assert needs.decision.slots == ("text_b",)
    compare = MainAgentModelAdapter(_mock_client(), mock_scenario=MainMockScenario.COMPARE).decide(missing_request)
    assert compare.outcome == "failure"
    assert compare.code is MainDecisionFailureCode.MODEL_UNAVAILABLE

    knowledge = MainAgentModelAdapter(_mock_client(), mock_scenario=MainMockScenario.KNOWLEDGE).decide(request)
    assert knowledge.outcome == "success"
    assert knowledge.decision.kind == "load_skill"
    knowledge_answer = MainAgentModelAdapter(_mock_client(), mock_scenario=MainMockScenario.KNOWLEDGE).decide(
        _decision_request(refs, observation_count=1)
    )
    assert knowledge_answer.outcome == "success"
    assert knowledge_answer.decision.kind == "answer"
    assert knowledge_answer.decision.text == MOCK_KNOWLEDGE_ANSWER_TEXT

    for scenario in (
        MainMockScenario.UNKNOWN_CAPABILITY,
        MainMockScenario.WRONG_VERSION,
        MainMockScenario.BUDGET_EXHAUSTED,
    ):
        assert parse_main_mock_scenario(scenario.value) is scenario


# ----------------------------------------------------------------------
# ReAct 内核
# ----------------------------------------------------------------------


def _gateway_result(
    status: str = "ok",
    *,
    output: str = "{}",
    duration_ms: int = 1,
) -> GatewayResult:
    return GatewayResult(
        output=output,
        record=ToolInvocation(
            tool=TEXT_COMPARE_TOOL_NAME,
            status=status,  # type: ignore[arg-type]
            started_at="2026-10-26T00:00:00Z",
            duration_ms=duration_ms,
            detail="测试替身",
        ),
    )


def _kernel(
    decide: Callable[[MainDecisionRequest, float], ModelDecisionResult],
    *,
    call_tool: Callable[[str, str, float], GatewayResult] | None = None,
    capabilities: CapabilityRegistry | None = None,
    skill_source: object = READONLY_PLAYBOOK_SOURCE,
    tool_bindings: ToolBindingRegistry | None = None,
    snapshot: MainInputSnapshotV1 | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    budget: MainAgentBudget | None = None,
    run_id: UUID | None = None,
    context: tuple = (),
) -> MainReactKernel:
    snapshot = snapshot or _snapshot()
    refs = _refs_for(snapshot)
    kwargs: dict = {
        "capabilities": capabilities or _capabilities(),
        "skill_source": skill_source,
        "tool_bindings": tool_bindings or ToolBindingRegistry([TextCompareToolBinding()]),
        "decide": decide,
        "call_tool": call_tool or (lambda _name, _args, _timeout: _gateway_result()),
        "run_id": run_id or uuid4(),
        "query": snapshot.query,
        "context": context,
        "material_refs": refs,
        "actual_missing": tuple(side for side in ("text_a", "text_b") if getattr(refs, side) is None),
        "rule_version": snapshot.rule_version,
        "is_cancelled": is_cancelled or (lambda: False),
    }
    if budget is not None:
        kwargs["budget"] = budget
    return MainReactKernel(**kwargs)


def _decide_sequence(*decisions: ModelDecisionResult) -> Callable[[MainDecisionRequest, float], ModelDecisionResult]:
    pending = list(decisions)

    def decide(_request: MainDecisionRequest, _timeout: float) -> ModelDecisionResult:
        if not pending:
            return ModelDecisionFailure(code=MainDecisionFailureCode.MODEL_UNAVAILABLE)
        return pending.pop(0)

    return decide


def _success(decision: object) -> ModelDecisionSuccess:
    return ModelDecisionSuccess(decision=decision)  # type: ignore[arg-type]


def _tools_via_gateway(snapshot: MainInputSnapshotV1, run_id: UUID, calls: list[str]):
    registry = ToolRegistry()
    binding = TextCompareToolBinding()
    registry.register(binding.build_tool(run_id=run_id, snapshot=snapshot))
    gateway = ToolGateway(registry, timeout_seconds=2.0)

    def call_tool(name: str, arguments: str, _timeout: float) -> GatewayResult:
        calls.append(name)
        return gateway.invoke(name, arguments)

    return call_tool


def test_kernel_calls_registered_tool_only_through_gateway() -> None:
    snapshot = _snapshot()
    refs = _refs_for(snapshot)
    run_id = uuid4()
    calls: list[str] = []
    kernel = _kernel(
        _decide_sequence(_success(MainInvokeCapabilityDecision(
            capability_id="text.literal_compare",
            capability_version=1,
            inputs={"text_a": str(refs.text_a), "text_b": str(refs.text_b)},
        ))),
        call_tool=_tools_via_gateway(snapshot, run_id, calls),
        snapshot=snapshot,
        run_id=run_id,
    )

    outcome = kernel.run()

    assert outcome.failure is None
    assert outcome.delivery is not None and outcome.delivery.kind == "comparison"
    assert calls == [TEXT_COMPARE_TOOL_NAME]


def test_decision_cannot_smuggle_a_tool_outside_the_gateway() -> None:
    snapshot = _snapshot()
    refs = _refs_for(snapshot)
    calls: list[str] = []
    client = _ScriptedClient((_json_response({**_invoke_payload(refs), "tool": "shell"}),))
    adapter = MainAgentModelAdapter(client)  # type: ignore[arg-type]
    kernel = _kernel(adapter.decide, call_tool=_tools_via_gateway(snapshot, uuid4(), calls), snapshot=snapshot)

    outcome = kernel.run()

    assert outcome.failure is MainAgentFailure.MODEL_DECISION_INVALID
    assert calls == []


def test_kernel_maps_gateway_status_to_closed_failure() -> None:
    snapshot = _snapshot()
    refs = _refs_for(snapshot)
    kernel = _kernel(
        _decide_sequence(_success(MainInvokeCapabilityDecision(
            capability_id="text.literal_compare",
            capability_version=1,
            inputs={"text_a": str(refs.text_a), "text_b": str(refs.text_b)},
        ))),
        call_tool=lambda _name, _args, _timeout: _gateway_result("timeout"),
        snapshot=snapshot,
    )

    outcome = kernel.run()

    assert outcome.failure is MainAgentFailure.TOOL_FAILED
    assert outcome.delivery is None


def test_foreign_material_refs_are_rejected_without_tool_execution() -> None:
    snapshot = _snapshot()
    foreign = _refs_for(_snapshot("别的旧行", "别的新行"))
    calls: list[str] = []
    kernel = _kernel(
        _decide_sequence(_success(MainInvokeCapabilityDecision(
            capability_id="text.literal_compare",
            capability_version=1,
            inputs={"text_a": str(foreign.text_a), "text_b": str(foreign.text_b)},
        ))),
        call_tool=lambda _name, _args, _timeout: calls.append("called") or _gateway_result(),
        snapshot=snapshot,
    )

    outcome = kernel.run()

    assert outcome.failure is MainAgentFailure.CAPABILITY_UNAVAILABLE
    assert calls == []


def test_same_material_on_both_sides_is_rejected_without_tool_execution() -> None:
    snapshot = _snapshot()
    refs = _refs_for(snapshot)
    calls: list[str] = []
    kernel = _kernel(
        _decide_sequence(_success(MainInvokeCapabilityDecision(
            capability_id="text.literal_compare",
            capability_version=1,
            inputs={"text_a": str(refs.text_a), "text_b": str(refs.text_a)},
        ))),
        call_tool=lambda _name, _args, _timeout: calls.append("called") or _gateway_result(),
        snapshot=snapshot,
    )

    outcome = kernel.run()

    assert outcome.failure is MainAgentFailure.CAPABILITY_UNAVAILABLE
    assert calls == []


def test_missing_tool_binding_fails_closed_without_gateway_call() -> None:
    snapshot = _snapshot()
    refs = _refs_for(snapshot)
    calls: list[str] = []
    kernel = _kernel(
        _decide_sequence(_success(MainInvokeCapabilityDecision(
            capability_id="text.literal_compare",
            capability_version=1,
            inputs={"text_a": str(refs.text_a), "text_b": str(refs.text_b)},
        ))),
        call_tool=lambda _name, _args, _timeout: calls.append("called") or _gateway_result(),
        tool_bindings=ToolBindingRegistry(),
        snapshot=snapshot,
    )

    outcome = kernel.run()

    assert outcome.failure is MainAgentFailure.CAPABILITY_UNAVAILABLE
    assert calls == []


def test_needs_input_slots_must_match_actual_missing_side() -> None:
    snapshot = _snapshot(text_a=None, text_b="新行")
    kernel = _kernel(
        _decide_sequence(_success(MainNeedsInputDecision(slots=("text_b",)))),
        snapshot=snapshot,
    )

    outcome = kernel.run()

    assert outcome.failure is MainAgentFailure.MODEL_DECISION_INVALID
    assert outcome.delivery is None


def test_kernel_rejects_slot_shape_and_unknown_capability() -> None:
    snapshot = _snapshot()
    refs = _refs_for(snapshot)
    shape_kernel = _kernel(
        _decide_sequence(_success(MainInvokeCapabilityDecision(
            capability_id="text.literal_compare",
            capability_version=1,
            inputs={"text_a": str(refs.text_a)},
        ))),
        snapshot=snapshot,
    )
    assert shape_kernel.run().failure is MainAgentFailure.MODEL_DECISION_INVALID

    unknown_kernel = _kernel(
        _decide_sequence(_success(MainInvokeCapabilityDecision(
            capability_id="missing.capability",
            capability_version=1,
            inputs={},
        ))),
        snapshot=snapshot,
    )
    assert unknown_kernel.run().failure is MainAgentFailure.CAPABILITY_UNAVAILABLE

    wrong_version_kernel = _kernel(
        _decide_sequence(_success(MainInvokeCapabilityDecision(
            capability_id="text.literal_compare",
            capability_version=2,
            inputs={"text_a": str(refs.text_a), "text_b": str(refs.text_b)},
        ))),
        snapshot=snapshot,
    )
    assert wrong_version_kernel.run().failure is MainAgentFailure.CAPABILITY_UNAVAILABLE


def test_kind_mismatch_is_rejected_for_both_directions() -> None:
    snapshot = _snapshot()
    load_execution = _kernel(
        _decide_sequence(_success(MainLoadSkillDecision(
            capability_id="text.literal_compare",
            capability_version=1,
        ))),
        snapshot=snapshot,
    )
    load_outcome = load_execution.run()
    assert load_outcome.failure is MainAgentFailure.CAPABILITY_UNAVAILABLE
    assert load_outcome.delivery is None

    invoke_knowledge = _kernel(
        _decide_sequence(_success(MainInvokeCapabilityDecision(
            capability_id=READONLY_PLAYBOOK_CAPABILITY_ID,
            capability_version=1,
            inputs={},
        ))),
        snapshot=snapshot,
    )
    invoke_outcome = invoke_knowledge.run()
    assert invoke_outcome.failure is MainAgentFailure.CAPABILITY_UNAVAILABLE
    assert invoke_outcome.delivery is None


def test_knowledge_load_then_answer_attaches_program_grounding() -> None:
    requests: list[MainDecisionRequest] = []
    pending = iter((_success(_load_skill()), _success(MainAnswerDecision(text="按手册逐项检查。"))))

    def decide(request: MainDecisionRequest, _timeout: float) -> ModelDecisionResult:
        requests.append(request)
        return next(pending, ModelDecisionFailure(code=MainDecisionFailureCode.MODEL_UNAVAILABLE))

    kernel = _kernel(decide)

    signals = list(kernel.stream())
    outcome = kernel.outcome

    assert outcome.failure is None
    assert isinstance(outcome.delivery, MainAnswerDeliveryV1)
    assert outcome.delivery.knowledge_grounding is not None
    assert outcome.delivery.knowledge_grounding.capability_id == READONLY_PLAYBOOK_CAPABILITY_ID
    assert outcome.delivery.knowledge_grounding.skill_id == READONLY_PLAYBOOK_SKILL_ID
    assert outcome.used[0].status == "loaded"
    route_signals = [signal for signal in signals if isinstance(signal, MainRouteSignal)]
    assert [signal.decision for signal in route_signals] == ["load_skill", "answer"]
    assert route_signals[0].status == "ok"
    assert route_signals[0].capability_kind is CapabilityKind.KNOWLEDGE

    # 第二次决策能看到受管 Skill 正文与固定观察行；正文只在已装入后出现。
    second_prompt = "\n".join(message.content for message in requests[1].messages)
    assert "受管 Skill" in second_prompt
    assert f"{READONLY_PLAYBOOK_SKILL_ID}@{READONLY_PLAYBOOK_SKILL_VERSION}" in second_prompt
    assert "status=loaded" in second_prompt
    assert requests[1].observation_count == 1


def _load_skill(version: int = 1) -> MainLoadSkillDecision:
    return MainLoadSkillDecision(
        capability_id=READONLY_PLAYBOOK_CAPABILITY_ID,
        capability_version=version,
    )


class _UnavailableSkillSource:
    """确定性降级来源：只返回封闭原因，不泄露路径或内容。"""

    def __init__(self, reason: SkillUnavailableReason) -> None:
        self.reason = reason

    def load(self, _declaration: object) -> object:
        raise SkillUnavailableError(self.reason)


def test_knowledge_degrade_continues_and_never_fakes_grounding() -> None:
    requests: list[MainDecisionRequest] = []
    pending = iter(
        (
            _success(_load_skill()),
            _success(MainAnswerDecision(text="只能给通用建议。")),
        )
    )

    def decide(request: MainDecisionRequest, _timeout: float) -> ModelDecisionResult:
        requests.append(request)
        return next(pending, ModelDecisionFailure(code=MainDecisionFailureCode.MODEL_UNAVAILABLE))

    kernel = _kernel(
        decide,
        skill_source=_UnavailableSkillSource(SkillUnavailableReason.DIGEST_MISMATCH),
    )

    signals = list(kernel.stream())
    outcome = kernel.outcome

    assert outcome.failure is None
    assert isinstance(outcome.delivery, MainAnswerDeliveryV1)
    assert outcome.delivery.knowledge_grounding is None
    assert outcome.used == ()
    assert [(item.capability_id, item.status) for item in outcome.degraded] == [
        (READONLY_PLAYBOOK_CAPABILITY_ID, "unavailable")
    ]
    route_signals = [signal for signal in signals if isinstance(signal, MainRouteSignal)]
    assert [signal.decision for signal in route_signals] == ["load_skill", "answer"]
    assert route_signals[0].status == "unavailable"
    assert route_signals[1].status == "ok"

    # 降级观察进入下一次决策上下文，且只含封闭 ref，不含路径或异常文本。
    observation_lines = [
        message.content
        for message in requests[1].messages
        if "source_digest_mismatch" in message.content
    ]
    assert observation_lines
    assert READONLY_PLAYBOOK_CAPABILITY_ID in "\n".join(observation_lines)
    assert requests[1].observation_count == 1


def test_repeated_load_of_degraded_capability_fails_without_new_observation() -> None:
    requests: list[MainDecisionRequest] = []
    pending = iter((_success(_load_skill()), _success(_load_skill())))

    def decide(request: MainDecisionRequest, _timeout: float) -> ModelDecisionResult:
        requests.append(request)
        return next(pending, ModelDecisionFailure(code=MainDecisionFailureCode.MODEL_UNAVAILABLE))

    kernel = _kernel(
        decide,
        skill_source=_UnavailableSkillSource(SkillUnavailableReason.MISSING),
    )

    signals = list(kernel.stream())
    outcome = kernel.outcome

    assert outcome.failure is MainAgentFailure.CAPABILITY_UNAVAILABLE
    load_signals = [
        signal
        for signal in signals
        if isinstance(signal, MainRouteSignal) and signal.decision == "load_skill"
    ]
    assert [signal.status for signal in load_signals] == ["unavailable", "unavailable"]
    # 第二次尝试在装入前失败，不追加第二条观察。
    assert requests[1].observation_count == 1


def test_degraded_load_does_not_consume_knowledge_budget() -> None:
    budget = MainAgentBudget()
    kernel = _kernel(
        _decide_sequence(_success(_load_skill()), _success(MainAnswerDecision(text="回答"))),
        skill_source=_UnavailableSkillSource(SkillUnavailableReason.TOO_LARGE),
        budget=budget,
    )

    assert kernel.run().failure is None
    assert budget.knowledge_loads == 0


def test_knowledge_load_budget_is_enforced_before_loading() -> None:
    budget = MainAgentBudget(max_knowledge_loads=0)
    kernel = _kernel(
        _decide_sequence(_success(_load_skill())),
        budget=budget,
    )

    outcome = kernel.run()

    assert outcome.failure is MainAgentFailure.BUDGET_EXHAUSTED
    assert budget.knowledge_loads == 0


def test_decision_budget_is_consumed_before_call_and_degrades_to_closed_failure() -> None:
    budget = MainAgentBudget(max_decisions=1)
    kernel = _kernel(
        _decide_sequence(_success(_load_skill()), _success(MainAnswerDecision(text="不应调用"))),
        budget=budget,
    )

    outcome = kernel.run()

    assert outcome.failure is MainAgentFailure.BUDGET_EXHAUSTED
    assert outcome.delivery is None
    assert budget.decisions == 1


def test_tool_budget_is_consumed_before_call() -> None:
    snapshot = _snapshot()
    refs = _refs_for(snapshot)
    calls: list[str] = []
    budget = MainAgentBudget(max_tool_calls=0)
    kernel = _kernel(
        _decide_sequence(_success(MainInvokeCapabilityDecision(
            capability_id="text.literal_compare",
            capability_version=1,
            inputs={"text_a": str(refs.text_a), "text_b": str(refs.text_b)},
        ))),
        call_tool=lambda _name, _args, _timeout: calls.append("called") or _gateway_result(),
        snapshot=snapshot,
        budget=budget,
    )

    outcome = kernel.run()

    assert outcome.failure is MainAgentFailure.BUDGET_EXHAUSTED
    assert calls == []
    assert budget.tool_calls == 0


def test_clipped_timeout_maps_to_budget_exhausted() -> None:
    snapshot = _snapshot()
    refs = _refs_for(snapshot)
    clock = _FakeClock(0.0)
    budget = MainAgentBudget(clock=clock, wall_clock_seconds=10.0)
    clock.advance(8.0)
    kernel = _kernel(
        _decide_sequence(_success(MainInvokeCapabilityDecision(
            capability_id="text.literal_compare",
            capability_version=1,
            inputs={"text_a": str(refs.text_a), "text_b": str(refs.text_b)},
        ))),
        call_tool=lambda _name, _args, _timeout: _gateway_result("timeout"),
        snapshot=snapshot,
        budget=budget,
    )

    outcome = kernel.run()

    assert outcome.failure is MainAgentFailure.BUDGET_EXHAUSTED


def test_fixed_cap_timeout_stays_tool_failed() -> None:
    snapshot = _snapshot()
    refs = _refs_for(snapshot)
    clock = _FakeClock(0.0)
    budget = MainAgentBudget(clock=clock, wall_clock_seconds=120.0)
    kernel = _kernel(
        _decide_sequence(_success(MainInvokeCapabilityDecision(
            capability_id="text.literal_compare",
            capability_version=1,
            inputs={"text_a": str(refs.text_a), "text_b": str(refs.text_b)},
        ))),
        call_tool=lambda _name, _args, _timeout: _gateway_result("timeout"),
        snapshot=snapshot,
        budget=budget,
    )

    outcome = kernel.run()

    assert outcome.failure is MainAgentFailure.TOOL_FAILED


class _FakeClock:
    def __init__(self, value: float) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_cancel_checked_after_model_call_discards_decision_without_tool() -> None:
    state = {"cancelled": False}
    calls: list[str] = []

    def decide(_request: MainDecisionRequest, _timeout: float) -> ModelDecisionResult:
        state["cancelled"] = True
        return _success(MainInvokeCapabilityDecision(
            capability_id="text.literal_compare",
            capability_version=1,
            inputs={"text_a": str(uuid4()), "text_b": str(uuid4())},
        ))

    kernel = _kernel(decide, call_tool=lambda _n, _a, _t: calls.append("called") or _gateway_result(),
                     is_cancelled=lambda: state["cancelled"])

    signals = list(kernel.stream())

    assert signals == []
    assert kernel.outcome.canceled is True
    assert kernel.outcome.delivery is None
    assert calls == []


def test_cancel_checked_after_tool_call_discards_result() -> None:
    snapshot = _snapshot()
    refs = _refs_for(snapshot)
    state = {"cancelled": False}

    def call_tool(_name: str, _arguments: str, _timeout: float) -> GatewayResult:
        state["cancelled"] = True
        return _gateway_result()

    kernel = _kernel(
        _decide_sequence(_success(MainInvokeCapabilityDecision(
            capability_id="text.literal_compare",
            capability_version=1,
            inputs={"text_a": str(refs.text_a), "text_b": str(refs.text_b)},
        ))),
        call_tool=call_tool,
        snapshot=snapshot,
        is_cancelled=lambda: state["cancelled"],
    )

    signals = list(kernel.stream())

    assert signals == []
    assert kernel.outcome.canceled is True
    assert kernel.outcome.delivery is None


def test_cancel_before_decision_stops_without_any_model_call() -> None:
    calls: list[object] = []

    def decide(request: MainDecisionRequest, _timeout: float) -> ModelDecisionResult:
        calls.append(request)
        return _success(MainAnswerDecision(text="不应调用"))

    kernel = _kernel(decide, is_cancelled=lambda: True)

    assert list(kernel.stream()) == []
    assert kernel.outcome.canceled is True
    assert calls == []


def test_main_agent_run_task_uses_fresh_state_per_run() -> None:
    snapshot = _snapshot()
    client = _ScriptedClient(
        (
            _json_response({"kind": "answer", "text": "第一次回答"}),
            _json_response({"kind": "answer", "text": "第二次回答"}),
        )
    )
    agent = MainAgent(
        llm=client,  # type: ignore[arg-type]
        adapter=MainAgentModelAdapter(client),  # type: ignore[arg-type]
        capabilities=_capabilities(),
        skill_source=READONLY_PLAYBOOK_SOURCE,
        tool_bindings=ToolBindingRegistry([TextCompareToolBinding()]),
        call_tool=lambda _name, _args, _timeout: _gateway_result(),
    )
    task = _main_task(uuid4(), _refs_for(snapshot))

    first = agent.run_task(task)
    second = agent.run_task(task)

    assert first.delivery == MainAnswerDeliveryV1(text="第一次回答")
    assert second.delivery == MainAnswerDeliveryV1(text="第二次回答")
    assert len(client.calls) == 2


# ----------------------------------------------------------------------
# 执行器端到端
# ----------------------------------------------------------------------


def _execute_with(
    runtime: PersistenceRuntime,
    executor: object,
    *,
    value: MainInputV1 | None = None,
    capabilities: CapabilityRegistry | None = None,
):
    service = _run_service(runtime, executor, capabilities or _capabilities())
    session_id = _new_session(runtime)
    accepted = _accept_main(service, session_id, value=value)
    return service, session_id, accepted, service.execute_run(accepted.run.id)


def test_executor_mock_answer_ignores_comparison_and_ops_wording(
    persistence_runtime: PersistenceRuntime,
) -> None:
    value = MainInputV1(query="请排查数据库慢查询并比较两段文本", text_a="旧行", text_b="新行")
    _, session_id, accepted, finished = _execute_with(
        persistence_runtime,
        _mock_executor(MainMockScenario.ANSWER),
        value=value,
    )

    assert finished.status is RunStatus.SUCCEEDED
    assert _load_delivery(persistence_runtime, accepted.run.id) == MainAnswerDeliveryV1(text=MOCK_ANSWER_TEXT)
    assistants = [message for message in _messages(persistence_runtime, session_id) if message.role is MessageRole.ASSISTANT]
    assert [message.content for message in assistants] == [MOCK_ANSWER_TEXT]
    events = _events(persistence_runtime, accepted.run.id)
    assert [event.type for event in events] == [
        RunEventType.RUN_QUEUED,
        RunEventType.RUN_STARTED,
        RunEventType.AGENT_START,
        RunEventType.ROUTE_DECIDED,
        RunEventType.AGENT_DONE,
        RunEventType.RUN_SUCCEEDED,
    ]
    assert [event.data.get("mode") for event in events[2:5]] == ["mock", "mock", "mock"]
    assert not any("旧行" in json.dumps(event.data, ensure_ascii=False) for event in events)
    assert not any(event.type is RunEventType.TOOL_INVOKED for event in events)


def test_executor_mock_needs_input_uses_snapshot_derived_prompt(
    persistence_runtime: PersistenceRuntime,
) -> None:
    value = MainInputV1(query="请比较", text_a=None, text_b="新行")
    _, session_id, accepted, finished = _execute_with(
        persistence_runtime,
        _mock_executor(MainMockScenario.NEEDS_INPUT),
        value=value,
    )

    assert finished.status is RunStatus.SUCCEEDED
    delivery = _load_delivery(persistence_runtime, accepted.run.id)
    assert isinstance(delivery, MainNeedsInputDeliveryV1)
    assert delivery.missing == ("text_a",)
    assistants = [message for message in _messages(persistence_runtime, session_id) if message.role is MessageRole.ASSISTANT]
    assert [message.content for message in assistants] == [delivery.prompt]
    assert not any(event.type is RunEventType.TOOL_INVOKED for event in _events(persistence_runtime, accepted.run.id))

    compare_run = _accept_main(
        _run_service(persistence_runtime, _mock_executor(MainMockScenario.COMPARE), _capabilities()),
        _new_session(persistence_runtime),
        value=value,
    )
    compare_service = _run_service(persistence_runtime, _mock_executor(MainMockScenario.COMPARE), _capabilities())
    failed = compare_service.execute_run(compare_run.run.id)
    assert failed.status is RunStatus.FAILED
    assert failed.error_code == RunFailureCode.MAIN_AGENT_MODEL_UNAVAILABLE.value
    assert _load_delivery(persistence_runtime, compare_run.run.id) is None
    assert not any(
        event.type is RunEventType.TOOL_INVOKED
        for event in _events(persistence_runtime, compare_run.run.id)
    )


def test_executor_mock_compare_runs_real_deterministic_tool(
    persistence_runtime: PersistenceRuntime,
) -> None:
    value = MainInputV1(query="请比较", text_a="旧行\n共同", text_b="新行\n共同")
    _, session_id, accepted, finished = _execute_with(
        persistence_runtime,
        _mock_executor(MainMockScenario.COMPARE),
        value=value,
    )

    assert finished.status is RunStatus.SUCCEEDED
    snapshot = _load_snapshot(persistence_runtime, accepted.run.id)
    assert snapshot.text_a is not None and snapshot.text_b is not None
    expected = compare_materials(run_id=accepted.run.id, text_a=snapshot.text_a, text_b=snapshot.text_b)
    delivery = _load_delivery(persistence_runtime, accepted.run.id)
    assert delivery == MainComparisonDeliveryV1(comparison=expected)
    assert expected.blocks[0].a_quote == "旧行"
    assert expected.blocks[0].b_quote == "新行"

    assistants = [message for message in _messages(persistence_runtime, session_id) if message.role is MessageRole.ASSISTANT]
    assert [message.content for message in assistants] == ["文本比较完成：共 1 个差异块。"]
    events = _events(persistence_runtime, accepted.run.id)
    assert [event.type for event in events] == [
        RunEventType.RUN_QUEUED,
        RunEventType.RUN_STARTED,
        RunEventType.AGENT_START,
        RunEventType.ROUTE_DECIDED,
        RunEventType.TOOL_INVOKED,
        RunEventType.AGENT_DONE,
        RunEventType.RUN_SUCCEEDED,
    ]
    tool_events = [event for event in events if event.type is RunEventType.TOOL_INVOKED]
    assert len(tool_events) == 1
    assert tool_events[0].data.get("status") == "ok"
    assert tool_events[0].data.get("mode") == "mock"
    route_events = [event for event in events if event.type is RunEventType.ROUTE_DECIDED]
    assert route_events[0].data.get("decision") == "invoke_capability"
    assert route_events[0].data.get("capability_kind") == "execution"
    assert route_events[0].data.get("step") == 1


def test_executor_mock_knowledge_loads_skill_and_answers_with_grounding(
    persistence_runtime: PersistenceRuntime,
) -> None:
    _, session_id, accepted, finished = _execute_with(
        persistence_runtime,
        _mock_executor(MainMockScenario.KNOWLEDGE),
    )

    assert finished.status is RunStatus.SUCCEEDED
    delivery = _load_delivery(persistence_runtime, accepted.run.id)
    assert isinstance(delivery, MainAnswerDeliveryV1)
    assert delivery.knowledge_grounding is not None
    assert delivery.knowledge_grounding.capability_id == READONLY_PLAYBOOK_CAPABILITY_ID
    assert delivery.text == MOCK_KNOWLEDGE_ANSWER_TEXT
    assistants = [message for message in _messages(persistence_runtime, session_id) if message.role is MessageRole.ASSISTANT]
    assert assistants[0].content.startswith(f"{KNOWLEDGE_GROUNDING_NOTE}\n\n")
    events = _events(persistence_runtime, accepted.run.id)
    route_events = [event for event in events if event.type is RunEventType.ROUTE_DECIDED]
    assert [event.data.get("decision") for event in route_events] == ["load_skill", "answer"]
    assert route_events[0].data.get("capability_id") == READONLY_PLAYBOOK_CAPABILITY_ID
    assert route_events[0].data.get("capability_kind") == "knowledge"
    assert route_events[0].data.get("status") == "ok"
    done = next(event for event in events if event.type is RunEventType.AGENT_DONE)
    assert done.data.get("outcome") == "answer_with_knowledge"
    assert done.data.get("steps") == 2


def test_executor_mock_knowledge_unavailable_is_degraded_then_answers(
    persistence_runtime: PersistenceRuntime,
) -> None:
    executor, _client = _scripted_executor(
        (
            _json_response(
                {
                    "kind": "load_skill",
                    "capability_id": READONLY_PLAYBOOK_CAPABILITY_ID,
                    "capability_version": 1,
                }
            ),
            _json_response({"kind": "answer", "text": "只能给通用建议。"}),
        ),
        skill_source=_UnavailableSkillSource(SkillUnavailableReason.MISSING),
    )
    _, session_id, accepted, finished = _execute_with(persistence_runtime, executor)

    assert finished.status is RunStatus.SUCCEEDED
    delivery = _load_delivery(persistence_runtime, accepted.run.id)
    assert isinstance(delivery, MainAnswerDeliveryV1)
    assert delivery.knowledge_grounding is None
    route_events = [
        event for event in _events(persistence_runtime, accepted.run.id) if event.type is RunEventType.ROUTE_DECIDED
    ]
    assert route_events[0].data.get("status") == "unavailable"
    assert route_events[0].data.get("decision") == "load_skill"
    assistants = [message for message in _messages(persistence_runtime, session_id) if message.role is MessageRole.ASSISTANT]
    assert assistants[0].content == "只能给通用建议。"


def test_executor_mock_budget_exhaustion_maps_to_new_code(
    persistence_runtime: PersistenceRuntime,
) -> None:
    _, _, accepted, finished = _execute_with(
        persistence_runtime,
        _mock_executor(MainMockScenario.BUDGET_EXHAUSTED),
    )

    assert finished.status is RunStatus.FAILED
    assert finished.error_code == RunFailureCode.MAIN_AGENT_BUDGET_EXHAUSTED.value
    assert finished.error_message == RunFailureCode.MAIN_AGENT_BUDGET_EXHAUSTED.safe_message
    assert _load_delivery(persistence_runtime, accepted.run.id) is None
    done = next(
        event for event in _events(persistence_runtime, accepted.run.id) if event.type is RunEventType.AGENT_DONE
    )
    assert done.data.get("outcome") == "budget_exhausted"


def test_executor_mock_unknown_capability_and_wrong_version_fail_closed(
    persistence_runtime: PersistenceRuntime,
) -> None:
    for scenario in (MainMockScenario.UNKNOWN_CAPABILITY, MainMockScenario.WRONG_VERSION):
        _, _, accepted, finished = _execute_with(persistence_runtime, _mock_executor(scenario))
        assert finished.status is RunStatus.FAILED
        assert finished.error_code == RunFailureCode.MAIN_AGENT_CAPABILITY_UNAVAILABLE.value
        assert _load_delivery(persistence_runtime, accepted.run.id) is None
        assert not any(
            event.type is RunEventType.TOOL_INVOKED
            for event in _events(persistence_runtime, accepted.run.id)
        )


def test_two_runs_with_same_input_have_stable_blocks_but_own_identity(
    persistence_runtime: PersistenceRuntime,
) -> None:
    executor = _mock_executor(MainMockScenario.COMPARE)
    service = _run_service(persistence_runtime, executor, _capabilities())
    session_id = _new_session(persistence_runtime)
    value = MainInputV1(query="请比较", text_a="旧行\n共同", text_b="新行\n共同")

    first = _accept_main(service, session_id, value=value)
    assert service.execute_run(first.run.id).status is RunStatus.SUCCEEDED
    second = _accept_main(service, session_id, value=value)
    assert service.execute_run(second.run.id).status is RunStatus.SUCCEEDED

    first_delivery = _load_delivery(persistence_runtime, first.run.id)
    second_delivery = _load_delivery(persistence_runtime, second.run.id)
    assert isinstance(first_delivery, MainComparisonDeliveryV1)
    assert isinstance(second_delivery, MainComparisonDeliveryV1)
    assert first_delivery.comparison.blocks == second_delivery.comparison.blocks
    assert first_delivery.comparison.status == second_delivery.comparison.status
    assert first_delivery.comparison.run_id == first.run.id
    assert second_delivery.comparison.run_id == second.run.id
    assert first_delivery.comparison.a_material_id != second_delivery.comparison.a_material_id


def test_executor_stream_does_not_write_product_facts_before_service_commit(
    persistence_runtime: PersistenceRuntime,
) -> None:
    executor = _mock_executor(MainMockScenario.ANSWER)
    service = _run_service(persistence_runtime, executor, _capabilities())
    session_id = _new_session(persistence_runtime)
    accepted = _accept_main(service, session_id)
    snapshot = _load_snapshot(persistence_runtime, accepted.run.id)

    signals = list(
        executor.stream(
            MainAgentRunExecutionInput(
                run_id=accepted.run.id,
                session_id=session_id,
                snapshot=snapshot,
            )
        )
    )

    assert sum(isinstance(signal, RunMainDeliverySignal) for signal in signals) == 1
    assert _load_run(persistence_runtime, accepted.run.id).status is RunStatus.QUEUED
    assert _load_delivery(persistence_runtime, accepted.run.id) is None
    assert [message.role for message in _messages(persistence_runtime, session_id)] == [MessageRole.USER]

    assert service.execute_run(accepted.run.id).status is RunStatus.SUCCEEDED
    assert _load_delivery(persistence_runtime, accepted.run.id) is not None


def test_real_client_prompt_carries_material_ids_but_not_material_text(
    persistence_runtime: PersistenceRuntime,
) -> None:
    executor, client = _scripted_executor((_json_response({"kind": "answer", "text": "已收到"}),))
    value = MainInputV1(query="请比较", text_a="合成旧文", text_b="合成新文")
    _, _, accepted, finished = _execute_with(persistence_runtime, executor, value=value)

    assert finished.status is RunStatus.SUCCEEDED
    assert len(client.calls) == 1
    request = client.calls[0]
    assert request["tools"] is None
    prompt = "\n".join(message["content"] for message in request["messages"])
    snapshot = _load_snapshot(persistence_runtime, accepted.run.id)
    assert snapshot.text_a is not None and snapshot.text_b is not None
    assert "合成旧文" not in prompt
    assert "合成新文" not in prompt
    assert str(snapshot.text_a.material_id) in prompt
    assert str(snapshot.text_b.material_id) in prompt
    assert READONLY_PLAYBOOK_CAPABILITY_ID in prompt
    assert any(event.data.get("mode") == "target" for event in _events(persistence_runtime, accepted.run.id))


def test_executor_rejects_material_refs_from_another_run(
    persistence_runtime: PersistenceRuntime,
) -> None:
    first_service = _run_service(persistence_runtime)
    first_session = _new_session(persistence_runtime)
    first = _accept_main(first_service, first_session)
    foreign_snapshot = _load_snapshot(persistence_runtime, first.run.id)
    foreign_refs = _refs_for(foreign_snapshot)

    executor, _client = _scripted_executor((_json_response(_invoke_payload(foreign_refs)),))
    _, session_id, accepted, failed = _execute_with(persistence_runtime, executor)

    assert failed.status is RunStatus.FAILED
    assert failed.error_code == RunFailureCode.MAIN_AGENT_CAPABILITY_UNAVAILABLE.value
    assert _load_delivery(persistence_runtime, accepted.run.id) is None
    assert [message for message in _messages(persistence_runtime, session_id) if message.role is MessageRole.ASSISTANT] == []
    assert not any(
        event.type is RunEventType.TOOL_INVOKED
        for event in _events(persistence_runtime, accepted.run.id)
    )


def test_executor_rejects_credential_in_final_delivery(
    persistence_runtime: PersistenceRuntime,
) -> None:
    executor, _client = _scripted_executor(
        (_json_response({"kind": "answer", "text": "密钥是 sk-abcdef123456"}),)
    )
    _, session_id, accepted, failed = _execute_with(persistence_runtime, executor)

    assert failed.status is RunStatus.FAILED
    assert failed.error_code == RunFailureCode.MAIN_AGENT_DELIVERY_INVALID.value
    assert _load_delivery(persistence_runtime, accepted.run.id) is None
    assert [message for message in _messages(persistence_runtime, session_id) if message.role is MessageRole.ASSISTANT] == []


@pytest.mark.parametrize("tamper", ["omit", "forge"])
def test_comparison_delivery_is_rejected_unless_blocks_recompute_exactly(
    persistence_runtime: PersistenceRuntime,
    tamper: str,
) -> None:
    value = MainInputV1(query="比较", text_a="A\nsame\nB", text_b="X\nsame\nY")
    service = _run_service(persistence_runtime)
    session_id = _new_session(persistence_runtime)
    accepted = _accept_main(service, session_id, value=value)
    snapshot = _load_snapshot(persistence_runtime, accepted.run.id)
    assert snapshot.text_a is not None and snapshot.text_b is not None
    expected = compare_materials(run_id=accepted.run.id, text_a=snapshot.text_a, text_b=snapshot.text_b)
    assert len(expected.blocks) == 2

    if tamper == "omit":
        forged = expected.model_copy(update={"blocks": expected.blocks[:1]})
    else:
        forged = expected.model_copy(
            update={
                "blocks": (
                    *expected.blocks,
                    TextDiffBlockV1(
                        kind="added",
                        b_start=4,
                        b_end=4,
                        b_lines=("伪造",),
                        b_quote="伪造",
                    ),
                )
            }
        )
    executor = _StubRunExecutor(
        (RunMainDeliverySignal(delivery=MainComparisonDeliveryV1(comparison=forged)),)
    )
    rejected_service = _run_service(persistence_runtime, executor)

    failed = rejected_service.execute_run(accepted.run.id)

    assert failed.status is RunStatus.FAILED
    assert failed.error_code == RunFailureCode.MAIN_AGENT_DELIVERY_INVALID.value
    assert _load_delivery(persistence_runtime, accepted.run.id) is None
    assert [message for message in _messages(persistence_runtime, session_id) if message.role is MessageRole.ASSISTANT] == []


def test_context_freezes_last_four_prior_answer_messages(
    persistence_runtime: PersistenceRuntime,
) -> None:
    executor = _mock_executor(MainMockScenario.ANSWER)
    service = _run_service(persistence_runtime, executor, _capabilities())
    session_id = _new_session(persistence_runtime)

    first = _accept_main(service, session_id)
    assert service.execute_run(first.run.id).status is RunStatus.SUCCEEDED
    second = _accept_main(service, session_id)
    second_snapshot = _load_snapshot(persistence_runtime, second.run.id)
    assert [(message.role, message.content) for message in second_snapshot.context] == [
        ("user", "请比较两段文本"),
        ("assistant", MOCK_ANSWER_TEXT),
    ]
    assert service.execute_run(second.run.id).status is RunStatus.SUCCEEDED
    third = _accept_main(service, session_id)
    third_snapshot = _load_snapshot(persistence_runtime, third.run.id)
    assert len(third_snapshot.context) == 4
    assert service.execute_run(third.run.id).status is RunStatus.SUCCEEDED
    fourth = _accept_main(service, session_id)
    fourth_snapshot = _load_snapshot(persistence_runtime, fourth.run.id)
    assert len(fourth_snapshot.context) == 4
    assert all(message.content != "" for message in fourth_snapshot.context)


def test_knowledge_prefix_is_retained_in_next_round_context(
    persistence_runtime: PersistenceRuntime,
) -> None:
    executor = _mock_executor(MainMockScenario.KNOWLEDGE)
    service = _run_service(persistence_runtime, executor, _capabilities())
    session_id = _new_session(persistence_runtime)

    first = _accept_main(service, session_id)
    assert service.execute_run(first.run.id).status is RunStatus.SUCCEEDED
    second = _accept_main(service, session_id)
    snapshot = _load_snapshot(persistence_runtime, second.run.id)

    assert [(message.role, message.content) for message in snapshot.context] == [
        ("user", "请比较两段文本"),
        ("assistant", f"{KNOWLEDGE_GROUNDING_NOTE}\n\n{MOCK_KNOWLEDGE_ANSWER_TEXT}"),
    ]


def test_context_excludes_comparison_runs_and_their_messages(
    persistence_runtime: PersistenceRuntime,
) -> None:
    answer_service = _run_service(persistence_runtime, _mock_executor(MainMockScenario.ANSWER), _capabilities())
    session_id = _new_session(persistence_runtime)
    first = _accept_main(answer_service, session_id)
    assert answer_service.execute_run(first.run.id).status is RunStatus.SUCCEEDED

    compare_service = _run_service(persistence_runtime, _mock_executor(MainMockScenario.COMPARE), _capabilities())
    second = _accept_main(compare_service, session_id)
    assert compare_service.execute_run(second.run.id).status is RunStatus.SUCCEEDED
    third = _accept_main(compare_service, session_id)
    third_snapshot = _load_snapshot(persistence_runtime, third.run.id)

    assert [(message.role, message.content) for message in third_snapshot.context] == [
        ("user", "请比较两段文本"),
        ("assistant", MOCK_ANSWER_TEXT),
    ]
    assert not any("文本比较完成" in message.content for message in third_snapshot.context)


def test_context_selection_keeps_whole_messages_within_codepoint_budget(
    persistence_runtime: PersistenceRuntime,
) -> None:
    long_answer = "长" * 1200
    executor, _client = _scripted_executor(
        (
            _json_response({"kind": "answer", "text": long_answer}),
            _json_response({"kind": "answer", "text": long_answer}),
            _json_response({"kind": "answer", "text": long_answer}),
        )
    )
    service = _run_service(persistence_runtime, executor, _capabilities())
    session_id = _new_session(persistence_runtime)

    first = _accept_main(service, session_id)
    assert service.execute_run(first.run.id).status is RunStatus.SUCCEEDED
    second = _accept_main(service, session_id)
    assert service.execute_run(second.run.id).status is RunStatus.SUCCEEDED
    third = _accept_main(service, session_id)
    snapshot = _load_snapshot(persistence_runtime, third.run.id)

    assert len(snapshot.context) <= 4
    assert sum(len(message.content) for message in snapshot.context) <= 2000
    assert [(message.role, message.content) for message in snapshot.context] == [
        ("user", "请比较两段文本"),
        ("user", "请比较两段文本"),
        ("assistant", long_answer),
    ]


def test_accept_rejects_sensitive_prior_context_before_any_write(
    persistence_runtime: PersistenceRuntime,
) -> None:
    service = _run_service(persistence_runtime, _mock_executor(MainMockScenario.ANSWER), _capabilities())
    session_id = _new_session(persistence_runtime)
    first = _accept_main(service, session_id)
    assert service.execute_run(first.run.id).status is RunStatus.SUCCEEDED

    session = persistence_runtime.session_factory()
    try:
        assistant = session.scalars(
            select(MessageRecord).where(
                MessageRecord.run_id == first.run.id,
                MessageRecord.role == MessageRole.ASSISTANT.value,
            )
        ).one()
        assistant.content = "上一轮回答含 sk-abcdef123456"
        session.commit()
        before_runs = session.scalar(select(func.count()).select_from(DiagnosisRunRecord))
    finally:
        session.close()

    with pytest.raises(MainAgentInputRejectedError):
        _accept_main(service, session_id)

    session = persistence_runtime.session_factory()
    try:
        assert session.scalar(select(func.count()).select_from(DiagnosisRunRecord)) == before_runs
    finally:
        session.close()
    assert len(_messages(persistence_runtime, session_id)) == 2


# ----------------------------------------------------------------------
# 版本激活、并发与取消
# ----------------------------------------------------------------------


def test_rerun_uses_version_active_at_rerun_time(
    persistence_runtime: PersistenceRuntime,
) -> None:
    capabilities = _capabilities()
    client = _ScriptedClient(())
    executor = MainAgentRunExecutor(
        client_factory=lambda _t: client,  # type: ignore[arg-type,return-value]
        capabilities=capabilities,
    )
    service = _run_service(persistence_runtime, executor, capabilities)
    session_id = _new_session(persistence_runtime)
    first = _accept_main(service, session_id)

    client._responses = [
        _json_response(
            {
                "kind": "load_skill",
                "capability_id": READONLY_PLAYBOOK_CAPABILITY_ID,
                "capability_version": 1,
            }
        ),
        _json_response({"kind": "answer", "text": "第一轮回答"}),
    ]
    assert service.execute_run(first.run.id).status is RunStatus.SUCCEEDED
    first_delivery = _load_delivery(persistence_runtime, first.run.id)
    assert isinstance(first_delivery, MainAnswerDeliveryV1)
    assert first_delivery.knowledge_grounding is not None
    assert first_delivery.knowledge_grounding.capability_version == 1

    # 注册 v2 后 v1 变为未激活；重跑在新激活版本上重新装配。
    capabilities.register(replace(READONLY_PLAYBOOK_CAPABILITY, version=2))
    rerun = service.rerun_run(first.run.id, uuid4())
    client._responses = [
        _json_response(
            {
                "kind": "load_skill",
                "capability_id": READONLY_PLAYBOOK_CAPABILITY_ID,
                "capability_version": 2,
            }
        ),
        _json_response({"kind": "answer", "text": "第二轮回答"}),
    ]
    assert service.execute_run(rerun.run.id).status is RunStatus.SUCCEEDED
    rerun_delivery = _load_delivery(persistence_runtime, rerun.run.id)
    assert isinstance(rerun_delivery, MainAnswerDeliveryV1)
    assert rerun_delivery.knowledge_grounding is not None
    assert rerun_delivery.knowledge_grounding.capability_version == 2
    # 历史 Run 的交付不被改写。
    assert _load_delivery(persistence_runtime, first.run.id) == first_delivery


def test_inactive_old_version_is_rejected_even_after_new_version_registration() -> None:
    capabilities = CapabilityRegistry(
        [READONLY_PLAYBOOK_CAPABILITY, replace(READONLY_PLAYBOOK_CAPABILITY, version=2)]
    )
    kernel = _kernel(
        _decide_sequence(_success(_load_skill(version=1))),
        capabilities=capabilities,
    )

    outcome = kernel.run()

    assert outcome.failure is MainAgentFailure.CAPABILITY_UNAVAILABLE
    assert capabilities.active_version(READONLY_PLAYBOOK_CAPABILITY_ID) == 2
    assert capabilities.resolve(
        READONLY_PLAYBOOK_CAPABILITY_ID,
        1,
        expected_kind=CapabilityKind.KNOWLEDGE,
    ).kind is ResolutionKind.INACTIVE_VERSION


_THREAD_REFS = threading.local()


class _BarrierInvokeClient:
    """两个 Run 的模型调用在 Barrier 处交错，决策只引用本线程 Run 的材料。"""

    def __init__(self, refs: MainDecisionMaterialRefs, barrier: threading.Barrier) -> None:
        self._refs = refs
        self._barrier = barrier
        self.calls = 0

    @property
    def is_mock(self) -> bool:
        return False

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **_kwargs: object,
    ) -> dict:
        self.calls += 1
        assert tools is None
        self._barrier.wait(timeout=5.0)
        return _json_response(_invoke_payload(self._refs))


def _stream_in_thread(
    executor: MainAgentRunExecutor,
    execution_input: MainAgentRunExecutionInput,
    refs: MainDecisionMaterialRefs,
) -> list[object]:
    _THREAD_REFS.refs = refs
    return list(executor.stream(execution_input))


def test_two_runs_interleave_without_sharing_agent_or_tool_state() -> None:
    barrier = threading.Barrier(2)
    clients: list[_BarrierInvokeClient] = []

    def factory(_timeout: float) -> _BarrierInvokeClient:
        refs = _THREAD_REFS.refs
        client = _BarrierInvokeClient(refs, barrier)
        clients.append(client)
        return client

    executor = MainAgentRunExecutor(
        client_factory=factory,  # type: ignore[arg-type]
        capabilities=_capabilities(),
    )
    snapshot_a = _snapshot("A 旧行", "A 新行")
    snapshot_b = _snapshot("B 旧行", "B 新行")
    refs_a = _refs_for(snapshot_a)
    refs_b = _refs_for(snapshot_b)
    input_a = MainAgentRunExecutionInput(run_id=uuid4(), session_id=uuid4(), snapshot=snapshot_a)
    input_b = MainAgentRunExecutionInput(run_id=uuid4(), session_id=uuid4(), snapshot=snapshot_b)

    with ThreadPoolExecutor(max_workers=2) as pool:
        future_a = pool.submit(_stream_in_thread, executor, input_a, refs_a)
        future_b = pool.submit(_stream_in_thread, executor, input_b, refs_b)
        signals_a = future_a.result(timeout=20)
        signals_b = future_b.result(timeout=20)

    deliveries_a = [signal.delivery for signal in signals_a if isinstance(signal, RunMainDeliverySignal)]
    deliveries_b = [signal.delivery for signal in signals_b if isinstance(signal, RunMainDeliverySignal)]
    assert len(deliveries_a) == 1 and len(deliveries_b) == 1
    comparison_a = deliveries_a[0].comparison
    comparison_b = deliveries_b[0].comparison
    assert comparison_a.run_id == input_a.run_id
    assert comparison_b.run_id == input_b.run_id
    assert comparison_a.a_material_id == snapshot_a.text_a.material_id
    assert comparison_a.b_material_id == snapshot_a.text_b.material_id
    assert comparison_b.a_material_id == snapshot_b.text_a.material_id
    assert comparison_b.b_material_id == snapshot_b.text_b.material_id
    assert comparison_a.a_material_id != comparison_b.a_material_id
    # 每个 Run 各有两个按超时构造的客户端（初始探测 + 决策调用），但只有后者真正对话。
    assert len(clients) == 4
    assert sum(client.calls for client in clients) == 2
    assert all(client.calls <= 1 for client in clients)


class _BlockingDeliveryExecutor:
    """在执行流中阻塞到取消提交后再交付，验证取消胜出与迟到隔离。"""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.proceed = threading.Event()

    def stream(self, execution_input: object) -> Iterator[object]:
        self.started.set()
        assert self.proceed.wait(timeout=5.0)
        yield RunEventSignal(event=_event())
        yield RunMainDeliverySignal(delivery=MainAnswerDeliveryV1(text="迟到交付"))


def test_cancel_winning_a_concurrent_run_leaves_no_late_delivery(
    persistence_runtime: PersistenceRuntime,
) -> None:
    executor = _BlockingDeliveryExecutor()
    service = _run_service(persistence_runtime, executor)
    session_id = _new_session(persistence_runtime)
    accepted = _accept_main(service, session_id)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.execute_run, accepted.run.id)
        assert executor.started.wait(timeout=5.0)
        cancelled = service.cancel_run(accepted.run.id)
        assert cancelled.status is RunStatus.CANCELLED
        executor.proceed.set()
        result = future.result(timeout=20)

    assert result.status is RunStatus.CANCELLED
    assert _load_delivery(persistence_runtime, accepted.run.id) is None
    assert [message for message in _messages(persistence_runtime, session_id) if message.role is MessageRole.ASSISTANT] == []
    assert [event.type for event in _events(persistence_runtime, accepted.run.id)] == [
        RunEventType.RUN_QUEUED,
        RunEventType.RUN_STARTED,
        RunEventType.RUN_CANCELLED,
    ]


class _CancelDuringModelClient(_ScriptedClient):
    """模型调用期间触发取消，返回本应被丢弃的执行决策。"""

    def __init__(self, cancel: Callable[[], object], response: dict) -> None:
        super().__init__((response,))
        self._cancel = cancel
        self.cancel_error: BaseException | None = None

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **_kwargs: object,
    ) -> dict:
        try:
            self._cancel()
        except BaseException as error:
            self.cancel_error = error
            raise
        return super().chat(messages, tools, **_kwargs)


def test_cancel_during_model_call_discards_decision_and_leaves_no_late_writes(
    persistence_runtime: PersistenceRuntime,
) -> None:
    service = _run_service(persistence_runtime)
    session_id = _new_session(persistence_runtime)
    accepted = _accept_main(service, session_id)
    snapshot = _load_snapshot(persistence_runtime, accepted.run.id)
    refs = _refs_for(snapshot)

    holder: dict[str, object] = {}
    client = _CancelDuringModelClient(
        lambda: holder["cancel"](accepted.run.id),  # type: ignore[operator]
        _json_response(_invoke_payload(refs)),
    )
    executor = MainAgentRunExecutor(
        client_factory=lambda _t: client,  # type: ignore[arg-type,return-value]
        capabilities=_capabilities(),
        is_cancelled=lambda run_id: _load_run(persistence_runtime, run_id).status is RunStatus.CANCELLED,
    )
    holder["cancel"] = service.cancel_run
    typed_service = _run_service(persistence_runtime, executor, _capabilities())

    finished = typed_service.execute_run(accepted.run.id)

    assert client.cancel_error is None, repr(client.cancel_error)
    assert finished.status is RunStatus.CANCELLED
    assert _load_delivery(persistence_runtime, accepted.run.id) is None
    assert [message for message in _messages(persistence_runtime, session_id) if message.role is MessageRole.ASSISTANT] == []
    events = _events(persistence_runtime, accepted.run.id)
    assert not any(event.type is RunEventType.ROUTE_DECIDED for event in events)
    assert not any(event.type is RunEventType.TOOL_INVOKED for event in events)
    assert not any(event.type is RunEventType.AGENT_DONE for event in events)
    assert not any(event.type is RunEventType.RUN_FAILED for event in events)
    assert events[-1].type is RunEventType.RUN_CANCELLED


def test_agent_failures_map_to_specific_public_codes() -> None:
    """每种封闭失败映射到各自公开码；未知失败保留兜底码。"""
    cases = {
        MainAgentFailure.MODEL_UNAVAILABLE: RunFailureCode.MAIN_AGENT_MODEL_UNAVAILABLE,
        MainAgentFailure.MODEL_DECISION_INVALID: RunFailureCode.MAIN_AGENT_DECISION_INVALID,
        MainAgentFailure.CAPABILITY_UNAVAILABLE: RunFailureCode.MAIN_AGENT_CAPABILITY_UNAVAILABLE,
        MainAgentFailure.TOOL_FAILED: RunFailureCode.MAIN_AGENT_TOOL_FAILED,
        MainAgentFailure.DELIVERY_INVALID: RunFailureCode.MAIN_AGENT_DELIVERY_INVALID,
        MainAgentFailure.BUDGET_EXHAUSTED: RunFailureCode.MAIN_AGENT_BUDGET_EXHAUSTED,
    }
    for failure, expected in cases.items():
        assert _failure_code(failure) is expected
    assert _failure_code(None) is RunFailureCode.MAIN_AGENT_FAILED


def test_budget_hard_caps_match_confirmed_limits() -> None:
    budget = MainAgentBudget()
    grants: list[float] = []
    for _ in range(MAX_MAIN_DECISIONS):
        grant = budget.start_decision()
        assert grant is not None
        grants.append(grant.effective_seconds)
    assert budget.start_decision() is None
    assert len(grants) == MAX_MAIN_DECISIONS
    assert budget.decisions == MAX_MAIN_DECISIONS

    knowledge_budget = MainAgentBudget()
    for _ in range(MAX_KNOWLEDGE_LOADS):
        assert knowledge_budget.can_load_knowledge()
        knowledge_budget.record_knowledge_load()
    assert not knowledge_budget.can_load_knowledge()
    with pytest.raises(ValueError):
        knowledge_budget.record_knowledge_load()

    tool_budget = MainAgentBudget()
    for _ in range(3):
        assert tool_budget.start_tool_call() is not None
    assert tool_budget.start_tool_call() is None


def test_budget_clips_blocking_call_to_remaining_wall_clock() -> None:
    clock = _FakeClock(0.0)
    budget = MainAgentBudget(clock=clock, wall_clock_seconds=120.0)

    first = budget.start_decision()
    assert first is not None
    assert first.effective_seconds == 30.0
    assert first.clipped is False

    clock.advance(110.0)
    clipped = budget.start_decision()
    assert clipped is not None
    assert clipped.effective_seconds == pytest.approx(10.0)
    assert clipped.clipped is True

    tool = budget.start_tool_call()
    assert tool is not None
    assert tool.effective_seconds == pytest.approx(3.0)
    assert tool.clipped is False
