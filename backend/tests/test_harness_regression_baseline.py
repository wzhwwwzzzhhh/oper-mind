"""P10 S3 Run、Tool、Trace、取消与固定动作的现状回归基线。"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread
from uuid import UUID, uuid4

import pytest

from src.api.v1.resources import run_event_resource
from src.application.action_execution import (
    ActionExecutionAttempt,
    ActionPreconditionBlockedError,
    ActionVerificationOutcome,
)
from src.application.action_services import (
    ActionApplicationService,
    DecideActionProposalCommand,
    RequestActionExecutionCommand,
)
from src.application.contracts import (
    CreateRunCommand,
    CreateSessionCommand,
    DiagnosisExecutionError,
    DiagnosisExecutionEvent,
    DiagnosisExecutionResult,
)
from src.application.controlled_action_catalog import (
    TARGET_COLUMNS,
    TARGET_INDEX_NAME,
    TARGET_SCHEMA,
    TARGET_SERVICE_ID,
    TARGET_TABLE,
)
from src.application.services import RunApplicationService, SessionApplicationService
from src.domain.actions import (
    ActionEventType,
    ActionExecutionStatus,
    ActionProposalData,
    ActionProposalStatus,
    ActionVerificationStatus,
)
from src.domain.diagnosis import DiagnosisSeverity, RunEventType, RunStatus
from src.domain.evidence import EvidenceFact, EvidenceInvestigationResult, MissingIndexSignal, RootCauseFact
from src.infrastructure.actions.postgres_target_executor import PostgresTargetActionExecutor
from src.infrastructure.diagnosis.coordinator_executor import CoordinatorDiagnosisExecutor
from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler, KernelReportResultAssembler
from src.infrastructure.persistence.database import PersistenceRuntime, create_persistence_runtime
from src.infrastructure.persistence.repositories import (
    SqlAlchemyDiagnosisResultRepository,
    SqlAlchemyRunEventRepository,
)
from tests.support.harness_contracts import (
    ToolGatewayCompatibilityProbe,
    ToolGatewayFact,
    ToolGatewayFactStatus,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
FIXED_OCCURRED_AT = datetime(2026, 9, 2, 0, 0, tzinfo=UTC)


@pytest.fixture
def persistence_runtime(tmp_path: Path) -> Iterator[PersistenceRuntime]:
    """在迁移后的临时 SQLite 应用库中验证现有事务与状态语义。"""

    database_path = tmp_path / "harness-regression.sqlite3"
    environment = os.environ.copy()
    environment.update(
        {
            "OPERMIND_APP_DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "OPERMIND_API_KEY": "mock",
            "OPERMIND_BASE_URL": "http://mock",
            "OPERMIND_MODEL": "mock",
            "PYTHONPATH": os.pathsep.join(
                [str(BACKEND_ROOT), str(PROJECT_ROOT), environment.get("PYTHONPATH", "")]
            ),
        }
    )
    migrated = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert migrated.returncode == 0, "harness.sqlite_migration：临时应用库迁移失败"
    runtime = create_persistence_runtime(f"sqlite:///{database_path.as_posix()}")
    try:
        yield runtime
    finally:
        runtime.engine.dispose()


class _DeterministicExecutor:
    """只返回固定 typed 结果的离线 fake DiagnosisExecutor。"""

    def __init__(self, *, failure: bool = False) -> None:
        self.failure = failure
        self.calls: list[str] = []

    def stream(
        self,
        query: str,
        service_id: str | None = None,
    ) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        del service_id
        self.calls.append(query)
        if self.failure:
            raise DiagnosisExecutionError(code="TEST_FAILURE", message="test-only failure")
        yield DiagnosisExecutionEvent(
            type=RunEventType.ROUTE_DECIDED,
            node="route",
            occurred_at=FIXED_OCCURRED_AT,
        )
        yield DiagnosisExecutionResult(strategy="direct")


def _build_run_service(
    runtime: PersistenceRuntime,
    executor: object,
) -> tuple[SessionApplicationService, RunApplicationService]:
    session_service = SessionApplicationService(runtime.session_factory)
    run_service = RunApplicationService(
        runtime.session_factory,
        executor,  # type: ignore[arg-type]
        ConservativeResultAssembler(),
    )
    return session_service, run_service


def _accept_run(
    session_service: SessionApplicationService,
    run_service: RunApplicationService,
    *,
    title: str,
    query: str,
) -> UUID:
    session = session_service.create_session(CreateSessionCommand(title=title))
    return run_service.accept_run(
        CreateRunCommand(session_id=session.id, query=query, idempotency_key=uuid4())
    ).run.id


def _load_run_events(runtime: PersistenceRuntime, run_id: UUID) -> list:
    session = runtime.session_factory()
    try:
        return SqlAlchemyRunEventRepository(session).list_by_run(run_id, cursor=None, limit=100).items
    finally:
        session.close()


def _terminal_snapshot(runtime: PersistenceRuntime, run_id: UUID) -> dict[str, object]:
    events = _load_run_events(runtime, run_id)
    session = runtime.session_factory()
    try:
        result = SqlAlchemyDiagnosisResultRepository(session).get_by_run_id(run_id)
    finally:
        session.close()
    return {
        "events": [
            {"sequence": event.sequence, "type": event.type.value, "data": event.data}
            for event in events
        ],
        "result": (
            None
            if result is None
            else {
                "id": str(result.id),
                "summary": result.summary,
                "severity": result.severity.value,
            }
        ),
    }


def _assert_no_direct_tool_execute(source: str, *, locator: str) -> None:
    """拒绝 Agent 侧直接调用 Tool.execute 的第二入口。"""

    tree = ast.parse(source, filename=locator)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "execute":
            raise AssertionError(f"tool_gateway.bypass：{locator}:{node.lineno}")


def test_toolgateway拒绝非法请求且负向门禁拒绝绕过() -> None:
    observed = ToolGatewayCompatibilityProbe().observe()

    guaranteed = {
        ToolGatewayFact.UNREGISTERED,
        ToolGatewayFact.INVALID_ARGUMENTS,
        ToolGatewayFact.SUCCESS,
        ToolGatewayFact.SENSITIVE_OUTPUT,
        ToolGatewayFact.EXCEPTION,
    }
    assert all(observed[fact].status is ToolGatewayFactStatus.GUARANTEED for fact in guaranteed)
    assert observed[ToolGatewayFact.TIMEOUT].status is ToolGatewayFactStatus.EXPECTED_GAP
    assert observed[ToolGatewayFact.TIMEOUT].gap_id == "tool_gateway.timeout_does_not_cancel_execution"

    agent_paths = [BACKEND_ROOT / "src" / "core" / "agent.py"]
    agent_paths.extend(sorted((BACKEND_ROOT / "src" / "agents").glob("*.py")))
    for path in agent_paths:
        _assert_no_direct_tool_execute(path.read_text(encoding="utf-8"), locator=path.name)

    bypass_sample = "def invoke(tool):\n    return tool.execute()\n"
    with pytest.raises(AssertionError, match=r"tool_gateway\.bypass"):
        _assert_no_direct_tool_execute(bypass_sample, locator="negative_sample.py")


def test_run代表性生命周期和迟到终态保持现状(persistence_runtime: PersistenceRuntime) -> None:
    assert {status.value for status in RunStatus} == {
        "queued",
        "running",
        "succeeded",
        "failed",
        "cancelled",
    }

    success_executor = _DeterministicExecutor()
    session_service, run_service = _build_run_service(persistence_runtime, success_executor)
    success_id = _accept_run(
        session_service,
        run_service,
        title="成功终态保护",
        query="检查服务状态",
    )
    succeeded = run_service.execute_run(success_id)
    assert succeeded.status is RunStatus.SUCCEEDED
    succeeded_snapshot = _terminal_snapshot(persistence_runtime, success_id)
    assert (
        run_service._complete_success(success_id, DiagnosisExecutionResult(strategy="late")).status
        is RunStatus.SUCCEEDED
    )
    assert run_service._complete_failure(success_id, "LATE_FAILURE", "迟到失败").status is RunStatus.SUCCEEDED
    assert _terminal_snapshot(persistence_runtime, success_id) == succeeded_snapshot

    failure_executor = _DeterministicExecutor(failure=True)
    failed_service = RunApplicationService(
        persistence_runtime.session_factory,
        failure_executor,
        ConservativeResultAssembler(),
    )
    failed_id = _accept_run(
        session_service,
        failed_service,
        title="失败终态保护",
        query="检查失败路径",
    )
    failed = failed_service.execute_run(failed_id)
    assert failed.status is RunStatus.FAILED
    failed_snapshot = _terminal_snapshot(persistence_runtime, failed_id)
    assert (
        failed_service._complete_success(failed_id, DiagnosisExecutionResult(strategy="late")).status
        is RunStatus.FAILED
    )
    assert failed_service._complete_failure(failed_id, "LATE_FAILURE", "迟到失败").status is RunStatus.FAILED
    assert _terminal_snapshot(persistence_runtime, failed_id) == failed_snapshot

    cancelled_id = _accept_run(
        session_service,
        run_service,
        title="取消终态保护",
        query="检查取消路径",
    )
    claimed, _, did_claim = run_service._claim_run(cancelled_id)
    assert did_claim is True
    assert claimed.status is RunStatus.RUNNING
    assert run_service.cancel_run(cancelled_id).status is RunStatus.CANCELLED
    cancelled_snapshot = _terminal_snapshot(persistence_runtime, cancelled_id)
    assert (
        run_service._complete_success(cancelled_id, DiagnosisExecutionResult(strategy="late")).status
        is RunStatus.CANCELLED
    )
    assert (
        run_service._complete_failure(cancelled_id, "LATE_FAILURE", "迟到失败").status
        is RunStatus.CANCELLED
    )
    assert _terminal_snapshot(persistence_runtime, cancelled_id) == cancelled_snapshot


class _BlockingExecutor:
    """用 Event 固定阻塞窗口，证明当前取消不能中断同步 Runtime。"""

    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()
        self.returned_from_block = Event()
        self.calls = 0

    def stream(
        self,
        query: str,
        service_id: str | None = None,
    ) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        del query, service_id
        self.calls += 1
        self.started.set()
        self.release.wait(timeout=2.0)
        self.returned_from_block.set()
        yield DiagnosisExecutionEvent(
            type=RunEventType.ROUTE_DECIDED,
            node="blocked-runtime",
            occurred_at=FIXED_OCCURRED_AT,
        )
        yield DiagnosisExecutionResult(strategy="late")


def test_cancel保持协作式检查点和终态保护(persistence_runtime: PersistenceRuntime) -> None:
    queued_executor = _DeterministicExecutor()
    session_service, queued_service = _build_run_service(persistence_runtime, queued_executor)
    queued_id = _accept_run(
        session_service,
        queued_service,
        title="queued 取消",
        query="执行排队任务",
    )
    queued_service.cancel_run(queued_id)
    assert queued_service.execute_run(queued_id).status is RunStatus.CANCELLED
    assert queued_executor.calls == []

    blocking = _BlockingExecutor()
    running_service = RunApplicationService(
        persistence_runtime.session_factory,
        blocking,
        ConservativeResultAssembler(),
    )
    running_id = _accept_run(
        session_service,
        running_service,
        title="running 取消",
        query="执行阻塞任务",
    )
    outcomes: list[RunStatus] = []
    failures: list[BaseException] = []

    def execute_in_background() -> None:
        try:
            outcomes.append(running_service.execute_run(running_id).status)
        except BaseException as exc:  # pragma: no cover - 只收集线程异常供主线程断言
            failures.append(exc)

    worker = Thread(target=execute_in_background, daemon=True)
    worker.start()
    assert blocking.started.wait(timeout=2.0)
    assert running_service.cancel_run(running_id).status is RunStatus.CANCELLED
    assert worker.is_alive()
    assert not blocking.returned_from_block.is_set()
    blocking.release.set()
    worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert failures == []
    assert outcomes == [RunStatus.CANCELLED]
    assert blocking.returned_from_block.is_set()
    assert [event.type for event in _load_run_events(persistence_runtime, running_id)] == [
        RunEventType.RUN_QUEUED,
        RunEventType.RUN_STARTED,
        RunEventType.RUN_CANCELLED,
    ]
    assert (
        running_service._complete_success(running_id, DiagnosisExecutionResult(strategy="late")).status
        is RunStatus.CANCELLED
    )


class _UnsafeTraceCoordinator:
    """向公开 Coordinator Adapter 注入测试用不安全摘要。"""

    def __init__(self, unsafe_detail: str) -> None:
        self._unsafe_detail = unsafe_detail

    def route_stream(self, query: str) -> Iterator[dict[str, object]]:
        del query
        yield {
            "kind": "trace",
            "event": {
                "type": "tool_invoked",
                "node": "tool",
                "detail": self._unsafe_detail,
                "status": "ok",
                "duration_ms": 7,
                "timestamp": FIXED_OCCURRED_AT.isoformat(),
            },
        }
        yield {"kind": "complete", "result": "安全报告", "strategy": "direct", "trace": []}


def test_tool_invoked公开投影拒绝敏感summary(persistence_runtime: PersistenceRuntime) -> None:
    unsafe_samples = [
        "SELECT password FROM credentials",
        r"C:\review\secret.txt",
        "/" + "var" + "/" + "tmp" + "/review-secret.txt",
        "password=unit-test-secret",
        "Traceback: test-only raw exception",
        "system prompt: test-only instructions",
        "raw tool output: test-only payload",
        "API key " + "s" + "k-review123456",
    ]
    session_service = SessionApplicationService(persistence_runtime.session_factory)

    for index, unsafe_detail in enumerate(unsafe_samples):
        executor = CoordinatorDiagnosisExecutor(
            lambda detail=unsafe_detail: _UnsafeTraceCoordinator(detail)
        )
        run_service = RunApplicationService(
            persistence_runtime.session_factory,
            executor,
            ConservativeResultAssembler(),
        )
        run_id = _accept_run(
            session_service,
            run_service,
            title=f"Trace 安全 {index}",
            query="验证公开事件",
        )

        assert run_service.execute_run(run_id).status is RunStatus.SUCCEEDED
        tool_event = next(
            event
            for event in _load_run_events(persistence_runtime, run_id)
            if event.type is RunEventType.TOOL_INVOKED
        )
        public_payload = run_event_resource(tool_event).model_dump(mode="json")
        expected_data = {
            "node": "tool",
            "summary": "工具调用成功",
            "status": "ok",
            "duration_ms": 7,
        }
        if tool_event.data != expected_data:
            raise AssertionError("safe_trace.persisted_projection：持久化事件不符合固定安全投影")
        if unsafe_detail in json.dumps(public_payload, ensure_ascii=False):
            raise AssertionError("safe_trace.public_projection：公开事件包含不安全自由文本")


def _action_investigation() -> EvidenceInvestigationResult:
    evidence_ids = [
        UUID("62345678-1234-5678-9234-567812345671"),
        UUID("62345678-1234-5678-9234-567812345672"),
        UUID("62345678-1234-5678-9234-567812345673"),
    ]
    evidence = [
        EvidenceFact(
            id=evidence_id,
            source_type="database",
            source_name="postgres_read_only",
            title=title,
            summary="确定性只读事实。",
        )
        for evidence_id, title in zip(
            evidence_ids,
            ("目标表存在", "固定联合索引缺失", "顺序扫描信号"),
            strict=True,
        )
    ]
    signal = MissingIndexSignal(
        service_id=TARGET_SERVICE_ID,
        schema=TARGET_SCHEMA,
        table=TARGET_TABLE,
        columns=TARGET_COLUMNS,
        index_name=TARGET_INDEX_NAME,
    )
    return EvidenceInvestigationResult(
        summary="固定目标存在缺索引信号。",
        severity=DiagnosisSeverity.HIGH,
        confidence=1.0,
        root_causes=[
            RootCauseFact(
                id=UUID("72345678-1234-5678-9234-567812345678"),
                title="缺少固定联合索引",
                summary="只读证据闭合。",
                confidence=1.0,
                evidence_ids=evidence_ids,
                missing_index=signal,
            )
        ],
        evidence=evidence,
        missing_index=signal,
    )


class _ActionDiagnosisExecutor:
    """只产出固定结构化证据的离线 fake DiagnosisExecutor。"""

    def stream(
        self,
        query: str,
        service_id: str | None = None,
    ) -> Iterator[DiagnosisExecutionResult]:
        del query, service_id
        yield DiagnosisExecutionResult(
            report="固定动作测试报告。",
            strategy="direct",
            evidence_investigation=_action_investigation(),
        )


class _RecordingActionExecutor:
    """记录 execute/verify 次数且不访问真实目标的受控 fake。"""

    def __init__(self) -> None:
        self.execute_calls: list[UUID] = []
        self.verify_calls: list[UUID] = []

    def execute(self, proposal: ActionProposalData) -> ActionExecutionAttempt:
        self.execute_calls.append(proposal.id)
        return ActionExecutionAttempt(
            mode=proposal.mode,
            precondition_summary="固定前置条件已通过。",
            action_summary="固定 fake 动作已完成。",
        )

    def verify(self, proposal: ActionProposalData) -> ActionVerificationOutcome:
        self.verify_calls.append(proposal.id)
        return ActionVerificationOutcome(
            mode=proposal.mode,
            summary="独立 Verify 已通过。",
            facts={"verification_passed": True},
        )


def test_固定动作从提案到独立验证保持既有边界(persistence_runtime: PersistenceRuntime) -> None:
    fake_executor = _RecordingActionExecutor()
    action_service = ActionApplicationService(persistence_runtime.session_factory, fake_executor)
    run_service = RunApplicationService(
        persistence_runtime.session_factory,
        _ActionDiagnosisExecutor(),
        KernelReportResultAssembler(),
        action_service=action_service,
        action_mode="target",
    )
    session = SessionApplicationService(persistence_runtime.session_factory).create_session(
        CreateSessionCommand(title="固定动作闭环")
    )
    run_id = run_service.accept_run(
        CreateRunCommand(session_id=session.id, query="生成固定提案", idempotency_key=uuid4())
    ).run.id

    assert run_service.execute_run(run_id).status is RunStatus.SUCCEEDED
    initial = action_service.get_by_run(run_id)
    assert initial is not None
    assert initial.proposal.status is ActionProposalStatus.PENDING_APPROVAL
    assert initial.approval is None and initial.execution is None and initial.verification is None

    decision = DecideActionProposalCommand(
        proposal_id=initial.proposal.id,
        decision="approve",
        comment="确认固定测试动作",
        idempotency_key=UUID("82345678-1234-5678-9234-567812345678"),
    )
    approved = action_service.decide(decision)
    replayed_approval = action_service.decide(decision)
    assert approved.proposal.status is ActionProposalStatus.APPROVED
    assert approved.approval is not None
    assert replayed_approval.approval is not None
    assert replayed_approval.approval.id == approved.approval.id

    execution_command = RequestActionExecutionCommand(
        proposal_id=initial.proposal.id,
        idempotency_key=UUID("92345678-1234-5678-9234-567812345678"),
    )
    requested = action_service.request_execution(execution_command)
    replayed_execution = action_service.request_execution(execution_command)
    assert requested.replayed is False
    assert replayed_execution.replayed is True
    assert replayed_execution.execution.id == requested.execution.id

    action_service.execute(initial.proposal.id)
    action_service.execute(initial.proposal.id)
    completed = action_service.get_detail(initial.proposal.id)
    assert completed.proposal.status is ActionProposalStatus.VERIFIED
    assert completed.execution is not None
    assert completed.execution.status is ActionExecutionStatus.SUCCEEDED
    assert completed.verification is not None
    assert completed.verification.status is ActionVerificationStatus.VERIFIED
    assert fake_executor.execute_calls == [initial.proposal.id]
    assert fake_executor.verify_calls == [initial.proposal.id]

    events = action_service.list_events(initial.proposal.id, cursor=None, limit=100).items
    assert [event.type for event in events] == [
        ActionEventType.PROPOSAL_CREATED,
        ActionEventType.APPROVAL_RECORDED,
        ActionEventType.EXECUTION_REQUESTED,
        ActionEventType.EXECUTION_STARTED,
        ActionEventType.PRECONDITION_CHECKED,
        ActionEventType.EXECUTION_COMPLETED,
        ActionEventType.VERIFICATION_STARTED,
        ActionEventType.VERIFICATION_COMPLETED,
    ]
    assert "grant" not in json.dumps(
        [event.model_dump(mode="json") for event in events],
        ensure_ascii=False,
    ).lower()

    connection_attempts: list[str] = []

    def forbidden_engine_factory(dsn: str) -> object:
        connection_attempts.append(dsn)
        raise AssertionError("不应连接目标")

    production_proposal = initial.proposal.model_copy(
        update={"target": {**initial.proposal.target, "service_id": "postgres-production"}}
    )
    production_executor = PostgresTargetActionExecutor(
        "test-only-dsn",
        engine_factory=forbidden_engine_factory,  # type: ignore[arg-type]
    )
    with pytest.raises(ActionPreconditionBlockedError):
        production_executor.execute(production_proposal)
    assert connection_attempts == []


def _normalized_run(runtime: PersistenceRuntime, *, title: str) -> dict[str, object]:
    executor = _DeterministicExecutor()
    session_service, run_service = _build_run_service(runtime, executor)
    run_id = _accept_run(
        session_service,
        run_service,
        title=title,
        query="相同确定性输入",
    )
    completed = run_service.execute_run(run_id)
    events = _load_run_events(runtime, run_id)
    session = runtime.session_factory()
    try:
        result = SqlAlchemyDiagnosisResultRepository(session).get_by_run_id(run_id)
    finally:
        session.close()
    assert result is not None
    return {
        "status": completed.status.value,
        "executor_calls": list(executor.calls),
        "events": [
            {"sequence": event.sequence, "type": event.type.value, "data": event.data}
            for event in events
        ],
        "result": {
            "summary": result.summary,
            "severity": result.severity.value,
            "confidence": result.confidence,
            "requires_approval": result.requires_approval,
        },
    }


def test_代表性场景归一化后重复运行一致(persistence_runtime: PersistenceRuntime) -> None:
    first = _normalized_run(persistence_runtime, title="确定性运行一")
    second = _normalized_run(persistence_runtime, title="确定性运行二")

    assert first == second
