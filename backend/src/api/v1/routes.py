"""P2.4 `/api/v1` 路由：持久化会话、Run、事件和 SSE 重放。"""

from __future__ import annotations

from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request, Response
from fastapi.responses import StreamingResponse

from src.api.v1.cursors import (
    ActionEventCursor,
    DiagnosisRunCursor,
    InvalidCursorError,
    MessageCursor,
    RunEventCursor,
    SessionCursor,
    decode_cursor,
    encode_cursor,
)
from src.api.v1.dependencies import V1Services, get_v1_services
from src.api.v1.errors import ApiV1Error
from src.api.v1.resources import (
    action_event_resource,
    action_execution_resource,
    action_proposal_resource,
    message_resource,
    run_event_resource,
    run_resource,
    service_activity_resource,
    service_resource,
    session_resource,
)
from src.api.v1.schemas import (
    ActionApprovalRequest,
    ActionEventListResponse,
    ActionExecutionRequest,
    ActionExecutionResponse,
    ActionProposalResponse,
    CreateRunRequest,
    CreateSessionRequest,
    CursorPage,
    DiagnosisRunListResponse,
    DiagnosisRunResource,
    MessageListResponse,
    ResponseMeta,
    RunEventEnvelope,
    RunEventListResponse,
    RunActionProposalResponse,
    RunResponse,
    ServiceActivityListResponse,
    ServiceListResponse,
    ServiceResponse,
    SessionListResponse,
    SessionResponse,
    UpdateSessionRequest,
)
from src.api.v1.sse import parse_event_sequence, replay_run_events
from src.application.action_services import DecideActionProposalCommand, RequestActionExecutionCommand
from src.application.contracts import CreateRunCommand, CreateSessionCommand, UpdateSessionCommand
from src.application.service_center import CreateServiceSessionCommand, ServiceCenterApplicationService
from src.application.errors import (
    ActionProposalInvalidStateError,
    ApplicationError,
    RunNotFoundError,
    ServiceCenterUnavailableError,
    SessionNotFoundError,
)
from src.domain.diagnosis import SessionStatus
from src.domain.records import DiagnosisRunData, SessionData
from src.infrastructure.persistence.repositories import (
    SqlAlchemyDiagnosisResultRepository,
    SqlAlchemyDiagnosisRunRepository,
    SqlAlchemyMessageRepository,
    SqlAlchemyRunEventRepository,
    SqlAlchemySessionRepository,
)


CursorT = TypeVar("CursorT", SessionCursor, MessageCursor, DiagnosisRunCursor, RunEventCursor, ActionEventCursor)

router = APIRouter(prefix="/api/v1", tags=["v1"])
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
APPLICATION_ERROR_STATUS = {
    "SESSION_NOT_FOUND": 404,
    "RUN_NOT_FOUND": 404,
    "SESSION_ARCHIVED": 409,
    "RUN_ALREADY_TERMINAL": 409,
    "IDEMPOTENCY_KEY_REUSED": 409,
    "RUN_INPUT_MESSAGE_INVALID": 409,
    "ACTION_PROPOSAL_NOT_FOUND": 404,
    "ACTION_PROPOSAL_INVALID_STATE": 409,
    "ACTION_PROPOSAL_EXPIRED": 409,
    "SERVICE_NOT_FOUND": 404,
    "SERVICE_CENTER_UNAVAILABLE": 503,
}


def response_meta(request: Request, trace_id: UUID | None = None) -> ResponseMeta:
    """读取由 v1 中间件确认的 request id，并按需附加稳定 trace id。"""
    request_id = getattr(request.state, "v1_request_id", None)
    if not isinstance(request_id, UUID):
        raise RuntimeError("v1 request id 尚未初始化")
    return ResponseMeta(request_id=request_id, trace_id=trace_id)


def apply_headers(response: Response, meta: ResponseMeta) -> None:
    """把 v1 关联 ID 回显至 HTTP 头。"""
    response.headers["X-Request-Id"] = str(meta.request_id)
    if meta.trace_id is not None:
        response.headers["X-Trace-Id"] = str(meta.trace_id)


def raise_application_error(error: ApplicationError) -> None:
    """将应用异常转为公开状态码，不泄露内部异常上下文。"""
    raise ApiV1Error(
        APPLICATION_ERROR_STATUS.get(error.code, 500),
        error.code if error.code in APPLICATION_ERROR_STATUS else "INTERNAL_ERROR",
        error.message if error.code in APPLICATION_ERROR_STATUS else "服务内部错误，请稍后重试",
    ) from error


def parse_idempotency_key(value: str) -> UUID:
    """校验 Run 受理必需的 UUID 幂等键。"""
    try:
        return UUID(value)
    except (TypeError, ValueError, AttributeError) as error:
        raise ApiV1Error(422, "VALIDATION_ERROR", "请求参数不合法") from error


def parse_page_cursor(value: str | None, cursor_type: type[CursorT]) -> CursorT | None:
    """把端点 cursor 转为固定排序领域 cursor。"""
    try:
        return decode_cursor(value, cursor_type)
    except InvalidCursorError as error:
        raise ApiV1Error(400, "INVALID_CURSOR", "分页游标无效") from error


def _service_center(services: V1Services) -> ServiceCenterApplicationService:
    """读取已装配的 P4.3 服务中心；旧 P2 测试装配安全拒绝。"""
    if services.service_center is None:
        raise ServiceCenterUnavailableError()
    return services.service_center


def _action_service(services: V1Services):
    """读取已装配的 P4.2 action 服务；旧 P2 测试装配不暴露动作能力。"""
    if services.action_service is None:
        raise ActionProposalInvalidStateError("固定修复能力当前不可用。")
    return services.action_service


def _load_session(services: V1Services, session_id: UUID) -> SessionData:
    session = services.session_factory()
    try:
        value = SqlAlchemySessionRepository(session).get_by_id(session_id)
    finally:
        session.close()
    if value is None:
        raise SessionNotFoundError()
    return value


def _load_run(services: V1Services, run_id: UUID) -> DiagnosisRunData:
    session = services.session_factory()
    try:
        value = SqlAlchemyDiagnosisRunRepository(session).get_by_id(run_id)
    finally:
        session.close()
    if value is None:
        raise RunNotFoundError()
    return value


def _run_response(services: V1Services, run_id: UUID) -> DiagnosisRunResource:
    session = services.session_factory()
    try:
        run = SqlAlchemyDiagnosisRunRepository(session).get_by_id(run_id)
        if run is None:
            raise RunNotFoundError()
        result = SqlAlchemyDiagnosisResultRepository(session).get_by_run_id(run_id)
        return run_resource(run, result)
    finally:
        session.close()


@router.get("/services", response_model=ServiceListResponse)
def list_services(
    request: Request,
    response: Response,
    services: V1Services = Depends(get_v1_services),
) -> ServiceListResponse:
    """读取代码内注册服务及其当前有限快照。"""
    try:
        items = _service_center(services).list_services()
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request)
    apply_headers(response, meta)
    return ServiceListResponse(items=[service_resource(item) for item in items], meta=meta)


@router.get("/services/{service_id}/activities", response_model=ServiceActivityListResponse)
def list_service_activities(
    service_id: str,
    request: Request,
    response: Response,
    cursor: str | None = None,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    services: V1Services = Depends(get_v1_services),
) -> ServiceActivityListResponse:
    """读取服务绑定会话的 Run 与修复闭环安全摘要。"""
    decoded_cursor = parse_page_cursor(cursor, DiagnosisRunCursor)
    try:
        page = _service_center(services).list_activities(service_id, decoded_cursor, limit)
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request)
    apply_headers(response, meta)
    return ServiceActivityListResponse(
        items=[service_activity_resource(item) for item in page.items],
        page=CursorPage(
            next_cursor=encode_cursor(page.next_cursor) if page.next_cursor else None,
            has_more=page.has_more,
        ),
        meta=meta,
    )


@router.post("/services/{service_id}/sessions", response_model=SessionResponse, status_code=201)
def create_service_session(
    service_id: str,
    request: Request,
    response: Response,
    services: V1Services = Depends(get_v1_services),
) -> SessionResponse:
    """创建服务上下文会话；不创建调查、外部读取或任何修复动作。"""
    try:
        created = _service_center(services).create_service_session(
            CreateServiceSessionCommand(service_id=service_id)
        )
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request)
    apply_headers(response, meta)
    return SessionResponse(session=session_resource(created), meta=meta)


@router.get("/services/{service_id}", response_model=ServiceResponse)
def get_service(
    service_id: str,
    request: Request,
    response: Response,
    services: V1Services = Depends(get_v1_services),
) -> ServiceResponse:
    """读取一个静态服务的身份、能力边界和当前有限快照。"""
    try:
        value = _service_center(services).get_service(service_id)
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request)
    apply_headers(response, meta)
    return ServiceResponse(service=service_resource(value), meta=meta)


@router.post("/sessions", response_model=SessionResponse, status_code=201)
def create_session(
    payload: CreateSessionRequest,
    request: Request,
    response: Response,
    services: V1Services = Depends(get_v1_services),
) -> SessionResponse:
    """创建 active Session；P2 仅承诺 Run 的持久化幂等语义。"""
    try:
        created = services.session_service.create_session(
            CreateSessionCommand(
                title=payload.title,
                environment_id=payload.environment_id,
                incident_id=payload.incident_id,
            )
        )
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request)
    apply_headers(response, meta)
    return SessionResponse(session=session_resource(created), meta=meta)


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(
    request: Request,
    response: Response,
    cursor: str | None = None,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    status: SessionStatus | None = None,
    services: V1Services = Depends(get_v1_services),
) -> SessionListResponse:
    """按更新时间倒序读取 Session 页面。"""
    decoded_cursor = parse_page_cursor(cursor, SessionCursor)
    session = services.session_factory()
    try:
        page = SqlAlchemySessionRepository(session).list_page(decoded_cursor, limit, status)
    finally:
        session.close()
    meta = response_meta(request)
    apply_headers(response, meta)
    return SessionListResponse(
        items=[session_resource(item) for item in page.items],
        page=CursorPage(next_cursor=encode_cursor(page.next_cursor) if page.next_cursor else None, has_more=page.has_more),
        meta=meta,
    )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: UUID,
    request: Request,
    response: Response,
    services: V1Services = Depends(get_v1_services),
) -> SessionResponse:
    """读取一个 Session。"""
    try:
        value = _load_session(services, session_id)
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request)
    apply_headers(response, meta)
    return SessionResponse(session=session_resource(value), meta=meta)


@router.patch("/sessions/{session_id}", response_model=SessionResponse)
def update_session(
    session_id: UUID,
    payload: UpdateSessionRequest,
    request: Request,
    response: Response,
    services: V1Services = Depends(get_v1_services),
) -> SessionResponse:
    """更新标题或逻辑归档 Session；已归档记录不能重新激活。"""
    try:
        value = services.session_service.update_session(
            UpdateSessionCommand(
                session_id=session_id,
                title=payload.title,
                status=SessionStatus(payload.status) if payload.status is not None else None,
            )
        )
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request)
    apply_headers(response, meta)
    return SessionResponse(session=session_resource(value), meta=meta)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: UUID,
    request: Request,
    services: V1Services = Depends(get_v1_services),
) -> Response:
    """逻辑归档 Session；重复删除保持 204。"""
    try:
        services.session_service.archive_session(session_id)
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request)
    return Response(status_code=204, headers={"X-Request-Id": str(meta.request_id)})


@router.get("/sessions/{session_id}/messages", response_model=MessageListResponse)
def list_messages(
    session_id: UUID,
    request: Request,
    response: Response,
    cursor: str | None = None,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    services: V1Services = Depends(get_v1_services),
) -> MessageListResponse:
    """按创建时间正序读取一个 Session 的消息。"""
    decoded_cursor = parse_page_cursor(cursor, MessageCursor)
    try:
        _load_session(services, session_id)
    except ApplicationError as error:
        raise_application_error(error)
    session = services.session_factory()
    try:
        page = SqlAlchemyMessageRepository(session).list_by_session(session_id, decoded_cursor, limit)
    finally:
        session.close()
    meta = response_meta(request)
    apply_headers(response, meta)
    return MessageListResponse(
        items=[message_resource(item) for item in page.items],
        page=CursorPage(next_cursor=encode_cursor(page.next_cursor) if page.next_cursor else None, has_more=page.has_more),
        meta=meta,
    )


@router.get("/sessions/{session_id}/runs", response_model=DiagnosisRunListResponse)
def list_session_runs(
    session_id: UUID,
    request: Request,
    response: Response,
    cursor: str | None = None,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    services: V1Services = Depends(get_v1_services),
) -> DiagnosisRunListResponse:
    """按创建时间倒序读取 Session 下的 Run，供刷新后恢复诊断工作区。"""
    decoded_cursor = parse_page_cursor(cursor, DiagnosisRunCursor)
    try:
        _load_session(services, session_id)
    except ApplicationError as error:
        raise_application_error(error)

    session = services.session_factory()
    try:
        run_repository = SqlAlchemyDiagnosisRunRepository(session)
        result_repository = SqlAlchemyDiagnosisResultRepository(session)
        page = run_repository.list_by_session(session_id, decoded_cursor, limit)
        items = [run_resource(run, result_repository.get_by_run_id(run.id)) for run in page.items]
    finally:
        session.close()

    meta = response_meta(request)
    apply_headers(response, meta)
    return DiagnosisRunListResponse(
        items=items,
        page=CursorPage(next_cursor=encode_cursor(page.next_cursor) if page.next_cursor else None, has_more=page.has_more),
        meta=meta,
    )


@router.post("/sessions/{session_id}/runs", response_model=RunResponse, status_code=202)
def create_run(
    session_id: UUID,
    payload: CreateRunRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    services: V1Services = Depends(get_v1_services),
) -> RunResponse:
    """原子受理 Run，成功受理后在 HTTP 响应完成后启动后台执行。"""
    try:
        accepted = services.run_service.accept_run(
            CreateRunCommand(
                session_id=session_id,
                query=payload.query,
                idempotency_key=parse_idempotency_key(idempotency_key),
            )
        )
    except ApplicationError as error:
        raise_application_error(error)

    if not accepted.replayed:
        background_tasks.add_task(services.run_service.execute_run, accepted.run.id)
    resource = _run_response(services, accepted.run.id)
    meta = response_meta(request, resource.trace_id)
    apply_headers(response, meta)
    return RunResponse(run=resource, meta=meta)


@router.get("/runs/{run_id}", response_model=RunResponse)
def get_run(
    run_id: UUID,
    request: Request,
    response: Response,
    services: V1Services = Depends(get_v1_services),
) -> RunResponse:
    """读取 Run 与其成功后的结构化结果。"""
    try:
        resource = _run_response(services, run_id)
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request, resource.trace_id)
    apply_headers(response, meta)
    return RunResponse(run=resource, meta=meta)


@router.get("/runs/{run_id}/action-proposal", response_model=RunActionProposalResponse)
def get_run_action_proposal(
    run_id: UUID,
    request: Request,
    response: Response,
    services: V1Services = Depends(get_v1_services),
) -> RunActionProposalResponse:
    """按成功 Run 读取可选的不可编辑固定修复提案。"""
    try:
        run = _load_run(services, run_id)
        detail = _action_service(services).get_by_run(run_id)
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request, run.trace_id)
    apply_headers(response, meta)
    return RunActionProposalResponse(
        proposal=action_proposal_resource(detail) if detail is not None else None,
        meta=meta,
    )


@router.get("/action-proposals/{proposal_id}", response_model=ActionProposalResponse)
def get_action_proposal(
    proposal_id: UUID,
    request: Request,
    response: Response,
    services: V1Services = Depends(get_v1_services),
) -> ActionProposalResponse:
    """读取 Proposal 及审批、执行和 Verify 的当前安全快照。"""
    try:
        detail = _action_service(services).get_detail(proposal_id)
        run = _load_run(services, detail.proposal.source_run_id)
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request, run.trace_id)
    apply_headers(response, meta)
    return ActionProposalResponse(proposal=action_proposal_resource(detail), meta=meta)


@router.get("/action-proposals/{proposal_id}/events", response_model=ActionEventListResponse)
def list_action_events(
    proposal_id: UUID,
    request: Request,
    response: Response,
    cursor: str | None = None,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    services: V1Services = Depends(get_v1_services),
) -> ActionEventListResponse:
    """按 sequence 分页读取已提交 action 审计事件，不建立第二套 SSE。"""
    decoded_cursor = parse_page_cursor(cursor, ActionEventCursor)
    try:
        detail = _action_service(services).get_detail(proposal_id)
        page = _action_service(services).list_events(proposal_id, decoded_cursor, limit)
        run = _load_run(services, detail.proposal.source_run_id)
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request, run.trace_id)
    apply_headers(response, meta)
    return ActionEventListResponse(
        items=[action_event_resource(item) for item in page.items],
        page=CursorPage(next_cursor=encode_cursor(page.next_cursor) if page.next_cursor else None, has_more=page.has_more),
        meta=meta,
    )


@router.post("/action-proposals/{proposal_id}/approval", response_model=ActionProposalResponse)
def decide_action_proposal(
    proposal_id: UUID,
    payload: ActionApprovalRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    services: V1Services = Depends(get_v1_services),
) -> ActionProposalResponse:
    """由固定 local_operator 明确批准或拒绝不可编辑 Proposal。"""
    try:
        detail = _action_service(services).decide(
            DecideActionProposalCommand(
                proposal_id=proposal_id,
                decision=payload.decision,
                comment=payload.comment,
                idempotency_key=parse_idempotency_key(idempotency_key),
            )
        )
        run = _load_run(services, detail.proposal.source_run_id)
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request, run.trace_id)
    apply_headers(response, meta)
    return ActionProposalResponse(proposal=action_proposal_resource(detail), meta=meta)


@router.post(
    "/action-proposals/{proposal_id}/executions",
    response_model=ActionExecutionResponse,
    status_code=202,
)
def request_action_execution(
    proposal_id: UUID,
    payload: ActionExecutionRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    services: V1Services = Depends(get_v1_services),
) -> ActionExecutionResponse:
    """第二次确认后异步启动唯一白名单修复，不接受任何动作参数。"""
    del payload
    try:
        accepted = _action_service(services).request_execution(
            RequestActionExecutionCommand(
                proposal_id=proposal_id,
                idempotency_key=parse_idempotency_key(idempotency_key),
            )
        )
        detail = _action_service(services).get_detail(proposal_id)
        run = _load_run(services, detail.proposal.source_run_id)
    except ApplicationError as error:
        raise_application_error(error)
    if not accepted.replayed:
        background_tasks.add_task(_action_service(services).execute, proposal_id)
    meta = response_meta(request, run.trace_id)
    apply_headers(response, meta)
    return ActionExecutionResponse(execution=action_execution_resource(accepted.execution), meta=meta)


@router.get("/runs/{run_id}/events", response_model=RunEventListResponse)
def list_run_events(
    run_id: UUID,
    request: Request,
    response: Response,
    cursor: str | None = None,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    services: V1Services = Depends(get_v1_services),
) -> RunEventListResponse:
    """按 sequence 正序读取已提交 RunEvent 页面。"""
    decoded_cursor = parse_page_cursor(cursor, RunEventCursor)
    try:
        run = _load_run(services, run_id)
    except ApplicationError as error:
        raise_application_error(error)
    session = services.session_factory()
    try:
        page = SqlAlchemyRunEventRepository(session).list_by_run(run_id, decoded_cursor, limit)
    finally:
        session.close()
    meta = response_meta(request, run.trace_id)
    apply_headers(response, meta)
    return RunEventListResponse(
        items=[run_event_resource(item) for item in page.items],
        page=CursorPage(next_cursor=encode_cursor(page.next_cursor) if page.next_cursor else None, has_more=page.has_more),
        meta=meta,
    )


@router.get("/runs/{run_id}/stream")
def stream_run_events(
    run_id: UUID,
    request: Request,
    after_sequence: str | None = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    services: V1Services = Depends(get_v1_services),
) -> StreamingResponse:
    """按持久化 sequence 重放事件；不产生即时或未提交 SSE 帧。"""
    try:
        header_cursor = parse_event_sequence(last_event_id)
        query_cursor = parse_event_sequence(after_sequence)
    except ValueError as error:
        raise ApiV1Error(400, "INVALID_EVENT_CURSOR", "事件游标无效") from error
    if header_cursor is not None and query_cursor is not None and header_cursor != query_cursor:
        raise ApiV1Error(400, "INVALID_EVENT_CURSOR", "事件游标无效")
    cursor = header_cursor if header_cursor is not None else query_cursor
    cursor = cursor or 0

    try:
        run = _load_run(services, run_id)
    except ApplicationError as error:
        raise_application_error(error)
    if cursor > run.next_event_sequence - 1:
        raise ApiV1Error(400, "INVALID_EVENT_CURSOR", "事件游标无效")

    meta = response_meta(request, run.trace_id)

    def envelope_factory(event):
        return RunEventEnvelope(event=run_event_resource(event), meta=meta)

    return StreamingResponse(
        replay_run_events(services.session_factory, run_id, cursor, envelope_factory),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Request-Id": str(meta.request_id),
            "X-Trace-Id": str(run.trace_id),
        },
    )
