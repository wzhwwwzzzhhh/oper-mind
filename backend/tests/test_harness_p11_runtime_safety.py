"""P11 S1 Runtime 唯一终态、安全失败与取消竞态。"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from typing import Literal
from uuid import UUID, uuid4

import pytest

import src.application.runtime_safety as runtime_safety
import tests.support.harness_p11_contracts as p11_contracts
from src.application.contracts import (
    CreateRunCommand,
    CreateSessionCommand,
    DiagnosisExecutionError,
    DiagnosisExecutionEvent,
    DiagnosisExecutionResult,
)
from src.application.runtime_contracts import (
    RuntimeEventSignal,
    RuntimeFailureSignal,
    RuntimeResultSignal,
)
from src.application.runtime_safety import guard_runtime_stream
from src.application.services import RunApplicationService, SessionApplicationService
from src.domain.diagnosis import MessageRole, RunEventType, RunStatus
from src.domain.harness_contracts import CONTRACT_VERSION_V1, FailureCodeId, FailureCodeValue
from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler
from src.infrastructure.persistence.action_repositories import SqlAlchemyActionProposalRepository
from src.infrastructure.persistence.database import PersistenceRuntime, create_persistence_runtime
from src.infrastructure.persistence.repositories import (
    SqlAlchemyDiagnosisResultRepository,
    SqlAlchemyMessageRepository,
    SqlAlchemyRunEventRepository,
)
from tests.support.harness_p11_contracts import (
    assert_p11_behavior_backed,
    assert_p11_profile_transition,
    load_reviewed_profile,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
SENSITIVE_SENTINEL = "postgresql://admin:secret@real-host/prod SELECT password FROM users"
PROFILE_DIR = Path(__file__).parent / "fixtures" / "harness"


def _event() -> DiagnosisExecutionEvent:
    return DiagnosisExecutionEvent(
        type=RunEventType.ROUTE_DECIDED,
        node="route",
        occurred_at=datetime.now(UTC),
        data={"status": "running"},
    )


def _result() -> DiagnosisExecutionResult:
    return DiagnosisExecutionResult(strategy="direct", report="安全诊断结果")


def _typed_failure(message: str = SENSITIVE_SENTINEL) -> RuntimeFailureSignal:
    return RuntimeFailureSignal(
        contract_version=CONTRACT_VERSION_V1,
        code=FailureCodeValue(
            contract_version=CONTRACT_VERSION_V1,
            code=FailureCodeId.TOOL_TIMEOUT,
            namespace=FailureCodeId.TOOL_TIMEOUT.namespace,
        ),
        message=message,
    )


class ScriptedExecutor:
    """输出任意协议对象的确定性执行器。"""

    def __init__(self, items: Sequence[object]) -> None:
        self._items = tuple(items)

    def stream(self, query: str, service_id: str | None = None) -> Iterator[object]:
        del query, service_id
        yield from self._items


class RaisingExecutor:
    """在首次迭代时抛出带敏感详情的意外异常。"""

    def stream(self, query: str, service_id: str | None = None) -> Iterator[object]:
        del query, service_id
        raise RuntimeError(SENSITIVE_SENTINEL)
        yield


class BlockingExecutor:
    """让取消确定发生在 Runtime 终止结果或失败之前。"""

    def __init__(self, outcome: Literal["result", "failure"]) -> None:
        self.outcome = outcome
        self.entered = Event()
        self.release = Event()

    def stream(self, query: str, service_id: str | None = None) -> Iterator[object]:
        del query, service_id
        self.entered.set()
        assert self.release.wait(timeout=5)
        if self.outcome == "failure":
            raise DiagnosisExecutionError(message=SENSITIVE_SENTINEL)
        yield _result()


@pytest.fixture
def persistence_runtime(tmp_path: Path) -> Iterator[PersistenceRuntime]:
    """用临时 SQLite 运行真实 Application transaction，不接触外部资源。"""

    database_path = tmp_path / "p11-runtime.sqlite3"
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.startswith("OPERMIND_SERVICE_"):
            environment.pop(name)
    environment.update(
        {
            "OPERMIND_APP_DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "OPERMIND_API_KEY": "mock",
            "OPERMIND_BASE_URL": "http://mock.invalid",
            "OPERMIND_MODEL": "mock",
            "OPERMIND_PG_DSN": "",
            "OPERMIND_KNOWLEDGE_DIR": "",
            "PYTHONPATH": os.pathsep.join(
                [str(BACKEND_ROOT), str(PROJECT_ROOT), environment.get("PYTHONPATH", "")]
            ),
        }
    )
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    runtime = create_persistence_runtime(f"sqlite:///{database_path.as_posix()}")
    try:
        yield runtime
    finally:
        runtime.engine.dispose()


def _failure_code(signals: list[object]) -> FailureCodeId:
    terminal = signals[-1]
    assert isinstance(terminal, RuntimeFailureSignal)
    return terminal.code.code


def test_有限正常流仅在EOF后交付唯一结果() -> None:
    signals = list(guard_runtime_stream(lambda: iter([_event(), _result()])))

    assert [type(signal) for signal in signals] == [RuntimeEventSignal, RuntimeResultSignal]


@pytest.mark.parametrize(
    ("items", "expected_code"),
    [
        ([], FailureCodeId.INTERNAL_INVARIANT_VIOLATION),
        ([_result(), _result()], FailureCodeId.INTERNAL_INVARIANT_VIOLATION),
        ([_result(), _event()], FailureCodeId.INTERNAL_INVARIANT_VIOLATION),
        ([_typed_failure(), _result()], FailureCodeId.INTERNAL_INVARIANT_VIOLATION),
        ([object()], FailureCodeId.INTERNAL_INVARIANT_VIOLATION),
    ],
)
def test_零多终止终止后输出和非法对象失败关闭(
    items: list[object],
    expected_code: FailureCodeId,
) -> None:
    signals = list(guard_runtime_stream(lambda: iter(items)))

    assert len(signals) == 1
    assert _failure_code(signals) is expected_code


def test_typed_failure保留封闭code但重建安全文案() -> None:
    signals = list(guard_runtime_stream(lambda: iter([_typed_failure()])))

    assert _failure_code(signals) is FailureCodeId.TOOL_TIMEOUT
    assert SENSITIVE_SENTINEL not in signals[-1].model_dump_json()  # type: ignore[union-attr]


@pytest.mark.parametrize("terminal", [_result(), _typed_failure()])
def test_终止候选后再抛typed_error按多终止违例关闭(terminal: object) -> None:
    def stream() -> Iterator[object]:
        yield terminal
        raise DiagnosisExecutionError(message=SENSITIVE_SENTINEL)

    signals = list(guard_runtime_stream(stream))

    assert len(signals) == 1
    assert _failure_code(signals) is FailureCodeId.INTERNAL_INVARIANT_VIOLATION
    assert SENSITIVE_SENTINEL not in signals[-1].model_dump_json()  # type: ignore[union-attr]


@pytest.mark.parametrize("stage", ["factory", "iterator", "next", "conversion"])
def test_各阶段意外异常统一为安全typed_failure(
    stage: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BadIterable:
        def __iter__(self) -> Iterator[object]:
            raise RuntimeError(SENSITIVE_SENTINEL)

    class BadIterator:
        def __iter__(self) -> BadIterator:
            return self

        def __next__(self) -> object:
            raise RuntimeError(SENSITIVE_SENTINEL)

    def raising_factory() -> Iterator[object]:
        raise RuntimeError(SENSITIVE_SENTINEL)

    def bad_iterable_factory() -> object:
        return BadIterable()

    def bad_iterator_factory() -> Iterator[object]:
        return BadIterator()

    def event_factory() -> Iterator[object]:
        return iter([_event()])

    factory: Callable[[], Iterator[object]] = raising_factory
    if stage == "iterator":
        factory = bad_iterable_factory  # type: ignore[assignment]
    elif stage == "next":
        factory = bad_iterator_factory
    elif stage == "conversion":
        factory = event_factory

        def fail_conversion(*args: object, **kwargs: object) -> RuntimeEventSignal:
            del args, kwargs
            raise RuntimeError(SENSITIVE_SENTINEL)

        monkeypatch.setattr(runtime_safety, "RuntimeEventSignal", fail_conversion)

    signals = list(guard_runtime_stream(factory))

    assert len(signals) == 1
    assert _failure_code(signals) is FailureCodeId.RUNTIME_UNEXPECTED_EXCEPTION
    assert SENSITIVE_SENTINEL not in signals[-1].model_dump_json()  # type: ignore[union-attr]


def test_result候选在底层EOF前不可见且保留deadline_gap() -> None:
    entered = Event()
    release = Event()

    def stream() -> Iterator[object]:
        yield _result()
        entered.set()
        assert release.wait(timeout=5)

    guarded = guard_runtime_stream(stream)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(next, guarded)
        assert entered.wait(timeout=2)
        assert not pending.done()
        release.set()
        assert isinstance(pending.result(timeout=2), RuntimeResultSignal)


def test_capability_v2连续且只升级有行为证明的两项() -> None:
    previous = load_reviewed_profile(PROFILE_DIR / "current_capability_profile.v1.json")
    current = load_reviewed_profile(PROFILE_DIR / "current_capability_profile.v2.json")

    assert_p11_profile_transition(previous, current)
    assert_p11_behavior_backed(current)


def test_只改capability声明不能替代行为证明(monkeypatch: pytest.MonkeyPatch) -> None:
    current = load_reviewed_profile(PROFILE_DIR / "current_capability_profile.v2.json")
    declared_result = RuntimeResultSignal(
        contract_version=CONTRACT_VERSION_V1,
        result=_result(),
    )
    monkeypatch.setattr(
        p11_contracts,
        "guard_runtime_stream",
        lambda stream_factory: iter([declared_result]),
    )

    with pytest.raises(AssertionError, match="缺少行为证明"):
        assert_p11_behavior_backed(current)


def _execute(
    runtime: PersistenceRuntime,
    executor: ScriptedExecutor | RaisingExecutor | BlockingExecutor,
) -> tuple[RunApplicationService, UUID, UUID]:
    session_service = SessionApplicationService(runtime.session_factory)
    session_data = session_service.create_session(CreateSessionCommand(title="P11 Runtime"))
    run_service = RunApplicationService(
        runtime.session_factory,
        executor,  # type: ignore[arg-type]
        ConservativeResultAssembler(),
    )
    run_id = run_service.accept_run(
        CreateRunCommand(
            session_id=session_data.id,
            query="执行安全诊断",
            idempotency_key=uuid4(),
        )
    ).run.id
    return run_service, session_data.id, run_id


def _stored_facts(runtime: PersistenceRuntime, session_id: UUID, run_id: UUID) -> dict[str, object]:
    session = runtime.session_factory()
    try:
        messages = SqlAlchemyMessageRepository(session).list_by_session(
            session_id,
            cursor=None,
            limit=20,
        ).items
        events = SqlAlchemyRunEventRepository(session).list_by_run(
            run_id,
            cursor=None,
            limit=20,
        ).items
        return {
            "result": SqlAlchemyDiagnosisResultRepository(session).get_by_run_id(run_id),
            "assistant_count": sum(message.role is MessageRole.ASSISTANT for message in messages),
            "proposal": SqlAlchemyActionProposalRepository(session).get_by_source_run_id(run_id),
            "terminal_events": [
                event.type
                for event in events
                if event.type
                in {RunEventType.RUN_SUCCEEDED, RunEventType.RUN_FAILED, RunEventType.RUN_CANCELLED}
            ],
        }
    finally:
        session.close()


def test_Run正常流只提交一份完整成功事实(persistence_runtime: PersistenceRuntime) -> None:
    service, session_id, run_id = _execute(
        persistence_runtime,
        ScriptedExecutor([_event(), _result()]),
    )

    completed = service.execute_run(run_id)
    facts = _stored_facts(persistence_runtime, session_id, run_id)

    assert completed.status is RunStatus.SUCCEEDED
    assert facts["result"] is not None
    assert facts["assistant_count"] == 1
    assert facts["proposal"] is None
    assert facts["terminal_events"] == [RunEventType.RUN_SUCCEEDED]


@pytest.mark.parametrize(
    "executor",
    [
        ScriptedExecutor([]),
        ScriptedExecutor([_result(), _result()]),
        ScriptedExecutor([_result(), _event()]),
        ScriptedExecutor([object()]),
        ScriptedExecutor([_typed_failure()]),
        RaisingExecutor(),
    ],
)
def test_Run协议与异常失败不形成部分成功(
    persistence_runtime: PersistenceRuntime,
    executor: ScriptedExecutor | RaisingExecutor,
) -> None:
    service, session_id, run_id = _execute(persistence_runtime, executor)

    completed = service.execute_run(run_id)
    facts = _stored_facts(persistence_runtime, session_id, run_id)

    assert completed.status is RunStatus.FAILED
    assert completed.error_code == "DIAGNOSIS_FAILED"
    assert completed.error_message == "诊断执行失败，请稍后重试"
    assert facts["result"] is None
    assert facts["assistant_count"] == 0
    assert facts["proposal"] is None
    assert facts["terminal_events"] == [RunEventType.RUN_FAILED]
    assert SENSITIVE_SENTINEL not in completed.model_dump_json()


@pytest.mark.parametrize("outcome", ["result", "failure"])
def test_取消获胜后迟到终止不能覆盖事实(
    persistence_runtime: PersistenceRuntime,
    outcome: Literal["result", "failure"],
) -> None:
    executor = BlockingExecutor(outcome)
    service, session_id, run_id = _execute(persistence_runtime, executor)

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(service.execute_run, run_id)
        assert executor.entered.wait(timeout=2)
        cancelled = service.cancel_run(run_id)
        executor.release.set()
        completed = pending.result(timeout=3)

    facts = _stored_facts(persistence_runtime, session_id, run_id)
    assert cancelled.status is RunStatus.CANCELLED
    assert completed.status is RunStatus.CANCELLED
    assert facts["result"] is None
    assert facts["assistant_count"] == 0
    assert facts["proposal"] is None
    assert facts["terminal_events"] == [RunEventType.RUN_CANCELLED]
