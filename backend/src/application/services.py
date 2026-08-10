"""P2 会话诊断闭环的 Application Service。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from inspect import signature
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.application.action_services import ActionApplicationService
from src.application.contracts import (
    CreateRunCommand,
    CreateSessionCommand,
    DiagnosisExecutionError,
    DiagnosisExecutionEvent,
    DiagnosisExecutionResult,
    DiagnosisExecutor,
    ResultAssembler,
    UpdateSessionCommand,
)
from src.application.errors import (
    IdempotencyKeyReusedError,
    RunAlreadyTerminalError,
    RunInputMessageInvalidError,
    RunNotFoundError,
    ServiceContextRequiredError,
    ServiceNotFoundError,
    SessionArchivedError,
    SessionNotFoundError,
)
from src.application.message_routing import requires_database_context
from src.domain.actions import ActionMode
from src.domain.diagnosis import MessageRole, RunEventType, RunStatus, SessionStatus
from src.domain.records import (
    DiagnosisRunData,
    MessageData,
    RunEventData,
    RunIdempotencyKeyData,
    SessionData,
)
from src.domain.services import REGISTERED_SERVICE_IDS, ServiceRegistry
from src.infrastructure.persistence.database import SessionFactory
from src.infrastructure.persistence.repositories import (
    SqlAlchemyDiagnosisResultRepository,
    SqlAlchemyDiagnosisRunRepository,
    SqlAlchemyMessageRepository,
    SqlAlchemyRunEventRepository,
    SqlAlchemyRunIdempotencyKeyRepository,
    SqlAlchemySessionRepository,
)

TransactionT = TypeVar("TransactionT")
IDEMPOTENCY_RETENTION = timedelta(hours=24)
RUN_CREATE_ENDPOINT = "/api/v1/sessions/{session_id}/runs"


class AcceptedRun(BaseModel):
    """Run 受理结果，标识是否为同键重放。"""

    model_config = ConfigDict(extra="forbid")

    run: DiagnosisRunData
    replayed: bool


class SessionApplicationService:
    """Session 创建与逻辑归档用例。"""

    def __init__(self, session_factory: SessionFactory, registry: ServiceRegistry | None = None) -> None:
        self._session_factory = session_factory
        self._registry = registry

    def create_session(self, command: CreateSessionCommand) -> SessionData:
        """创建 active Session 并在短事务中提交。"""
        service_ids = command.service_ids if command.service_ids is not None else (
            (command.service_id,) if command.service_id is not None else ()
        )
        if service_ids and (
            self._registry is None or not set(service_ids).issubset(self._registry.service_ids())
        ):
            raise ServiceNotFoundError()
        session_data = SessionData(
            title=command.title,
            environment_id=command.environment_id,
            incident_id=command.incident_id,
            service_id=command.service_id if command.service_ids is None else None,
            service_ids=service_ids,
        )

        def operation(session: Session) -> SessionData:
            SqlAlchemySessionRepository(session).add(session_data)
            return session_data

        return _in_transaction(self._session_factory, operation)

    def archive_session(self, session_id: UUID) -> SessionData:
        """逻辑归档 Session；重复归档保持幂等。"""
        return self.update_session(
            UpdateSessionCommand(session_id=session_id, status=SessionStatus.ARCHIVED)
        )

    def update_session(self, command: UpdateSessionCommand) -> SessionData:
        """在一个短事务内更新标题或逻辑归档，不允许重新激活。"""

        def operation(session: Session) -> SessionData:
            repository = SqlAlchemySessionRepository(session)
            current = repository.get_by_id(command.session_id)
            if current is None:
                raise SessionNotFoundError()
            if command.status == SessionStatus.ACTIVE and current.status == SessionStatus.ARCHIVED:
                raise SessionArchivedError("已归档会话不能重新激活。")

            should_archive = command.status == SessionStatus.ARCHIVED
            if command.title is None and (
                current.status == SessionStatus.ARCHIVED
                or command.status == SessionStatus.ACTIVE
            ):
                return current

            now = _utc_now()
            updated = current.model_copy(
                update={
                    "title": command.title if command.title is not None else current.title,
                    "status": SessionStatus.ARCHIVED if should_archive else current.status,
                    "archived_at": now if should_archive and current.archived_at is None else current.archived_at,
                    "updated_at": now,
                }
            )
            repository.save(updated)
            return updated

        return _in_transaction(self._session_factory, operation)


class RunApplicationService:
    """Run 受理、执行、事件与终态写入用例。"""

    def __init__(
        self,
        session_factory: SessionFactory,
        executor: DiagnosisExecutor,
        result_assembler: ResultAssembler,
        action_service: ActionApplicationService | None = None,
        action_mode: ActionMode | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._executor = executor
        self._result_assembler = result_assembler
        self._action_service = action_service
        self._action_mode = action_mode

    def accept_run(self, command: CreateRunCommand) -> AcceptedRun:
        """原子受理 Run，并处理同键重放与冲突。"""
        fingerprint = _query_fingerprint(command.query, command.service_id)
        try:
            return _in_transaction(
                self._session_factory,
                lambda session: self._accept_run_in_transaction(session, command, fingerprint),
            )
        except IntegrityError as error:
            return self._load_idempotency_after_conflict(command, fingerprint, error)

    def _load_idempotency_after_conflict(
        self,
        command: CreateRunCommand,
        fingerprint: str,
        original_error: IntegrityError,
    ) -> AcceptedRun:
        """处理唯一键竞争后的幂等重读。"""

        def operation(session: Session) -> AcceptedRun:
            key = SqlAlchemyRunIdempotencyKeyRepository(session).get_by_scope(
                command.session_id,
                RUN_CREATE_ENDPOINT,
                command.idempotency_key,
            )
            if key is None:
                raise original_error
            if key.request_fingerprint != fingerprint:
                raise IdempotencyKeyReusedError()
            run = SqlAlchemyDiagnosisRunRepository(session).get_by_id(key.run_id)
            if run is None:
                raise RunNotFoundError()
            return AcceptedRun(run=run, replayed=True)

        return _in_transaction(self._session_factory, operation)

    def execute_run(self, run_id: UUID) -> DiagnosisRunData:
        """使用已持久化输入消息执行 Run，并把任何可处理异常收敛为安全终态。"""
        try:
            running, query, claimed = self._claim_run(run_id)
            if not claimed:
                return running

            execution_result: DiagnosisExecutionResult | None = None
            current_run = self._load_run(run_id)
            for item in _stream_with_context(self._executor, query or "", current_run.service_id):
                if isinstance(item, DiagnosisExecutionEvent):
                    self._append_event(
                        run_id,
                        item.type,
                        item.occurred_at,
                        _safe_event_data(item),
                    )
                else:
                    execution_result = item
            if execution_result is None:
                raise DiagnosisExecutionError()
            return self._complete_success(run_id, execution_result)
        except RunNotFoundError:
            raise
        except Exception:
            return self._complete_failure(run_id, *_safe_failure())

    def _accept_run_in_transaction(
        self,
        session: Session,
        command: CreateRunCommand,
        fingerprint: str,
    ) -> AcceptedRun:
        session_repository = SqlAlchemySessionRepository(session)
        idempotency_repository = SqlAlchemyRunIdempotencyKeyRepository(session)
        run_repository = SqlAlchemyDiagnosisRunRepository(session)
        message_repository = SqlAlchemyMessageRepository(session)
        event_repository = SqlAlchemyRunEventRepository(session)

        session_data = session_repository.get_by_id(command.session_id)
        if session_data is None:
            raise SessionNotFoundError()
        if session_data.status == SessionStatus.ARCHIVED:
            raise SessionArchivedError()
        target_service_id = _resolve_run_service_id(session_data, command)
        if target_service_id is None and requires_database_context(command.query):
            raise ServiceContextRequiredError()

        existing = idempotency_repository.get_by_scope(
            command.session_id,
            RUN_CREATE_ENDPOINT,
            command.idempotency_key,
        )
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise IdempotencyKeyReusedError()
            run = run_repository.get_by_id(existing.run_id)
            if run is None:
                raise RunNotFoundError()
            return AcceptedRun(run=run, replayed=True)

        now = _utc_now()
        input_message = MessageData(
            session_id=command.session_id,
            role=MessageRole.USER,
            content=command.query,
            created_at=now,
        )
        run = DiagnosisRunData(
            session_id=command.session_id,
            service_id=target_service_id,
            input_message_id=input_message.id,
            status=RunStatus.QUEUED,
            next_event_sequence=2,
            created_at=now,
        )
        idempotency = RunIdempotencyKeyData(
            session_id=command.session_id,
            endpoint=RUN_CREATE_ENDPOINT,
            idempotency_key=command.idempotency_key,
            request_fingerprint=fingerprint,
            run_id=run.id,
            expires_at=now + IDEMPOTENCY_RETENTION,
            created_at=now,
        )
        queued_event = RunEventData(
            run_id=run.id,
            sequence=1,
            type=RunEventType.RUN_QUEUED,
            occurred_at=now,
            data={"state": RunStatus.QUEUED.value},
        )
        # mapper 不声明 Message/Run relationship；显式 flush 保证外键依赖的插入顺序仍在同一短事务内。
        message_repository.add(input_message)
        session.flush()
        run_repository.add(run)
        session.flush()
        idempotency_repository.add(idempotency)
        event_repository.add(queued_event)
        _touch_session(session_repository, session_data, now)
        return AcceptedRun(run=run, replayed=False)

    def _load_run(self, run_id: UUID) -> DiagnosisRunData:
        """读取执行所需的不可变 Run 上下文。"""
        session = self._session_factory()
        try:
            value = SqlAlchemyDiagnosisRunRepository(session).get_by_id(run_id)
        finally:
            session.close()
        if value is None:
            raise RunNotFoundError()
        return value

    def _claim_run(self, run_id: UUID) -> tuple[DiagnosisRunData, str | None, bool]:
        """在短事务中认领 queued Run，并验证其持久化输入消息。"""

        def operation(session: Session) -> tuple[DiagnosisRunData, str | None, bool]:
            run_repository = SqlAlchemyDiagnosisRunRepository(session)
            current = run_repository.get_by_id(run_id)
            if current is None:
                raise RunNotFoundError()
            if current.status != RunStatus.QUEUED:
                return current, None, False
            input_message = SqlAlchemyMessageRepository(session).get_by_id(current.input_message_id)
            if (
                input_message is None
                or input_message.session_id != current.session_id
                or input_message.role != MessageRole.USER
            ):
                raise RunInputMessageInvalidError()
            updated = run_repository.transition_status(
                run_id,
                expected_statuses={RunStatus.QUEUED},
                status=RunStatus.RUNNING,
                started_at=_utc_now(),
            )
            if updated is None:
                latest = run_repository.get_by_id(run_id)
                if latest is None:
                    raise RunNotFoundError()
                if latest.status != RunStatus.QUEUED:
                    return latest, None, False
                raise RunAlreadyTerminalError()
            self._append_event_in_transaction(session, run_id, RunEventType.RUN_STARTED, {"state": "running"})
            return updated, input_message.content, True

        return _in_transaction(self._session_factory, operation)

    def _append_event(
        self,
        run_id: UUID,
        event_type: RunEventType,
        occurred_at: datetime,
        data: dict[str, JsonValue],
    ) -> None:
        """在独立短事务中持久化一条可重放 RunEvent。"""

        def operation(session: Session) -> None:
            self._append_event_in_transaction(session, run_id, event_type, data, occurred_at)

        _in_transaction(self._session_factory, operation)

    @staticmethod
    def _append_event_in_transaction(
        session: Session,
        run_id: UUID,
        event_type: RunEventType,
        data: dict[str, JsonValue],
        occurred_at: datetime | None = None,
    ) -> None:
        """在调用方事务内预留 sequence 并写入事件。"""
        run_repository = SqlAlchemyDiagnosisRunRepository(session)
        sequence = run_repository.reserve_event_sequence(run_id)
        if sequence is None:
            raise RunNotFoundError()
        SqlAlchemyRunEventRepository(session).add(
            RunEventData(
                run_id=run_id,
                sequence=sequence,
                type=event_type,
                occurred_at=occurred_at or _utc_now(),
                data=data,
            )
        )

    def _complete_success(self, run_id: UUID, execution_result: DiagnosisExecutionResult) -> DiagnosisRunData:
        """原子写入 Result、助手 Message、成功终态和最终事件。"""

        def operation(session: Session) -> DiagnosisRunData:
            run_repository = SqlAlchemyDiagnosisRunRepository(session)
            run = run_repository.get_by_id(run_id)
            if run is None:
                raise RunNotFoundError()
            if run.status != RunStatus.RUNNING:
                if run.status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
                    return run
                raise RunAlreadyTerminalError()
            result = self._result_assembler.assemble(run, execution_result)
            if result.run_id != run.id:
                raise ValueError("ResultAssembler 返回的 run_id 与当前 Run 不一致。")
            SqlAlchemyDiagnosisResultRepository(session).add(result)
            assistant_message = MessageData(
                session_id=run.session_id,
                run_id=run.id,
                role=MessageRole.ASSISTANT,
                content=result.summary,
            )
            _validate_assistant_message_run(assistant_message, run)
            SqlAlchemyMessageRepository(session).add(assistant_message)
            updated = run_repository.transition_status(
                run_id,
                expected_statuses={RunStatus.RUNNING},
                status=RunStatus.SUCCEEDED,
                finished_at=_utc_now(),
            )
            if updated is None:
                raise RunAlreadyTerminalError()
            if self._action_service is not None and self._action_mode in {"mock", "target"}:
                self._action_service.maybe_create_proposal_in_transaction(session, updated, result, self._action_mode)
            self._append_event_in_transaction(
                session,
                run_id,
                RunEventType.RUN_SUCCEEDED,
                {"state": RunStatus.SUCCEEDED.value},
            )
            _touch_session(SqlAlchemySessionRepository(session), run.session_id, _utc_now())
            return updated

        return _in_transaction(self._session_factory, operation)

    def _complete_failure(self, run_id: UUID, error_code: str, error_message: str) -> DiagnosisRunData:
        """原子写入安全失败终态和最终事件。"""

        def operation(session: Session) -> DiagnosisRunData:
            run_repository = SqlAlchemyDiagnosisRunRepository(session)
            run = run_repository.get_by_id(run_id)
            if run is None:
                raise RunNotFoundError()
            if run.status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
                return run
            updated = run_repository.transition_status(
                run_id,
                expected_statuses={RunStatus.RUNNING, RunStatus.QUEUED},
                status=RunStatus.FAILED,
                finished_at=_utc_now(),
                error_code=error_code,
                error_message=error_message,
            )
            if updated is None:
                raise RunAlreadyTerminalError()
            self._append_event_in_transaction(
                session,
                run_id,
                RunEventType.RUN_FAILED,
                {"state": RunStatus.FAILED.value, "code": error_code},
            )
            _touch_session(SqlAlchemySessionRepository(session), run.session_id, _utc_now())
            return updated

        return _in_transaction(self._session_factory, operation)


def _in_transaction(session_factory: SessionFactory, operation: Callable[[Session], TransactionT]) -> TransactionT:
    """创建短生命周期 Session，并由 Application Service 统一控制事务。"""
    session = session_factory()
    try:
        result = operation(session)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _stream_with_context(
    executor: DiagnosisExecutor,
    query: str,
    service_id: str | None,
) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
    """把服务上下文传给新执行器，同时允许旧测试端口继续只接收 query。"""
    stream = executor.stream
    if len(signature(stream).parameters) >= 2:
        return stream(query, service_id)
    return stream(query)


def _resolve_run_service_id(session: SessionData, command: CreateRunCommand) -> str | None:
    """为单个 Run 解析显式服务，绝不在多服务数据库调查中猜测目标。"""
    if command.service_id is not None:
        if command.service_id not in session.service_ids:
            raise ServiceContextRequiredError("目标服务不属于当前诊断会话。")
        return command.service_id
    if len(session.service_ids) == 1:
        return session.service_ids[0]
    if len(session.service_ids) > 1 and requires_database_context(command.query):
        raise ServiceContextRequiredError("数据库调查需要指定目标服务。")
    return None


def _query_fingerprint(query: str, service_id: str | None = None) -> str:
    """计算稳定请求语义指纹；无显式服务时保持既有幂等值。"""
    value = query.strip() if service_id is None else f"{query.strip()}\n{service_id}"
    return sha256(value.encode("utf-8")).hexdigest()


def _safe_failure() -> tuple[str, str]:
    """返回唯一允许写入 Run、事件和 API 的执行失败信息。"""
    return "DIAGNOSIS_FAILED", "诊断执行失败，请稍后重试"


def _safe_event_data(event: DiagnosisExecutionEvent) -> dict[str, JsonValue]:
    """只持久化最小过程摘要白名单，拒绝执行器提供的任意原始读取。"""
    data: dict[str, JsonValue] = {"node": event.node}
    summary = event.data.get("summary")
    if isinstance(summary, str) and 0 < len(summary) <= 280:
        data["summary"] = summary
    role = event.data.get("role")
    if role in {"db", "log", "server"}:
        data["role"] = role
    status = event.data.get("status")
    if status in {"running", "completed", "failed", "skipped", "ok", "rejected", "timeout", "error"}:
        data["status"] = status
    duration_ms = event.data.get("duration_ms")
    if isinstance(duration_ms, int) and not isinstance(duration_ms, bool) and 0 <= duration_ms <= 60_000:
        data["duration_ms"] = duration_ms
    mode = event.data.get("mode")
    if mode in {"mock", "target"}:
        data["mode"] = mode
    service_id = event.data.get("service_id")
    if isinstance(service_id, str) and service_id in REGISTERED_SERVICE_IDS:
        data["service_id"] = service_id
    return data


def _utc_now() -> datetime:
    """返回 Application Service 使用的 UTC aware 当前时间。"""
    return datetime.now(UTC)



def _validate_assistant_message_run(message: MessageData, run: DiagnosisRunData) -> None:
    """显式守卫无物理 FK 的助手消息 Run/Session 应用层关联。"""
    if message.run_id != run.id or message.session_id != run.session_id:
        raise ValueError("助手消息必须关联同一 Session 的 Run。")



def _touch_session(
    repository: SqlAlchemySessionRepository,
    session: SessionData | UUID,
    updated_at: datetime,
) -> None:
    """在 Run 受理或终态写入时更新 Session 活动时间。"""
    current = session if isinstance(session, SessionData) else repository.get_by_id(session)
    if current is None:
        raise SessionNotFoundError()
    repository.save(current.model_copy(update={"updated_at": updated_at}))
