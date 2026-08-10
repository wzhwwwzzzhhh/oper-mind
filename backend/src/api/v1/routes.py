"""P2.4 `/api/v1` 路由：持久化会话、Run、事件和 SSE 重放。"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Annotated, Literal, TypeVar
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request, Response
from fastapi.responses import StreamingResponse

from src.api.v1.cursors import (
    ActionEventCursor,
    ActionProposalCursor,
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
    action_proposal_summary_resource,
    knowledge_document_resource,
    knowledge_search_hit_resource,
    message_resource,
    monitor_history_resource,
    monitor_overview_resource,
    provider_resource,
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
    ActionProposalListResponse,
    ActionProposalResponse,
    ActivateModelProviderRequest,
    CreateModelProviderRequest,
    CreateRunRequest,
    CreateSessionRequest,
    CursorPage,
    DiagnosisRunListResponse,
    DiagnosisRunResource,
    KnowledgeDocumentDetailResource,
    KnowledgeDocumentResponse,
    KnowledgeListResponse,
    KnowledgeSearchResponse,
    MessageListResponse,
    ModelConfigResource,
    ModelConfigResponse,
    ModelEndpointResource,
    ModelProviderListResponse,
    ModelProviderResponse,
    MonitorHistoryResponse,
    MonitorOverviewResponse,
    PlainMessageResponse,
    ResponseMeta,
    RunActionProposalResponse,
    RunEventEnvelope,
    RunEventListResponse,
    RunResponse,
    SendPlainMessageRequest,
    ServiceActivityListResponse,
    ServiceListResponse,
    ServiceResponse,
    SessionListResponse,
    SessionResponse,
    UpdateModelProviderRequest,
    UpdateSessionRequest,
)
from src.api.v1.sse import parse_event_sequence, replay_run_events
from src.application.action_services import (
    ActionApplicationService,
    DecideActionProposalCommand,
    RequestActionExecutionCommand,
)
from src.application.contracts import CreateRunCommand, CreateSessionCommand, UpdateSessionCommand
from src.application.errors import (
    ActionProposalInvalidStateError,
    ApplicationError,
    RunNotFoundError,
    ServiceCenterUnavailableError,
    SessionNotFoundError,
)
from src.application.knowledge import KnowledgeReaderService, KnowledgeTimeoutError
from src.application.model_providers import (
    ActivateModelProviderCommand,
    CreateModelProviderCommand,
    ModelProviderApplicationService,
    UpdateModelProviderCommand,
    provider_create_fingerprint,
)
from src.application.monitoring import (
    OVERVIEW_READ_TIMEOUT_SECONDS,
    MonitorHistoryApplicationService,
    MonitorOverviewApplicationService,
)
from src.application.plain_messages import PlainMessageApplicationService, SendPlainMessageCommand
from src.application.service_center import CreateServiceSessionCommand, ServiceCenterApplicationService
from src.config import load_monitor_settings
from src.domain.actions import ActionProposalStatus
from src.domain.diagnosis import SessionStatus
from src.domain.model_provider import ProviderEndpoint
from src.domain.records import DiagnosisRunData, RunEventData, SessionData
from src.infrastructure.persistence.repositories import (
    SqlAlchemyDiagnosisResultRepository,
    SqlAlchemyDiagnosisRunRepository,
    SqlAlchemyMessageRepository,
    SqlAlchemyRunEventRepository,
    SqlAlchemySessionRepository,
)
from src.infrastructure.secrets import (
    SecretKeyNotConfiguredError as SecretsSecretKeyNotConfiguredError,
)
from src.infrastructure.secrets import (
    SecretKeyTooShortError,
    load_secret_key,
)
from src.knowledge.reader import _ILLEGAL_PATH_RE, _ILLEGAL_QUERY_RE, KnowledgeDocumentMeta, KnowledgeSearchHit

CursorT = TypeVar(
    "CursorT",
    SessionCursor,
    MessageCursor,
    DiagnosisRunCursor,
    RunEventCursor,
    ActionEventCursor,
    ActionProposalCursor,
)

router = APIRouter(prefix="/api/v1", tags=["v1"])
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
APPLICATION_ERROR_STATUS = {
    "SESSION_NOT_FOUND": 404,
    "RUN_NOT_FOUND": 404,
    "SESSION_ARCHIVED": 409,
    "RUN_ALREADY_TERMINAL": 409,
    "INVESTIGATION_REQUIRED": 409,
    "IDEMPOTENCY_KEY_REUSED": 409,
    "RUN_INPUT_MESSAGE_INVALID": 409,
    "ACTION_PROPOSAL_NOT_FOUND": 404,
    "ACTION_PROPOSAL_INVALID_STATE": 409,
    "ACTION_PROPOSAL_EXPIRED": 409,
    "SERVICE_NOT_FOUND": 404,
    "SERVICE_CENTER_UNAVAILABLE": 503,
    "SERVICE_CONTEXT_REQUIRED": 409,
    "PROVIDER_NOT_FOUND": 404,
    "SECRET_KEY_NOT_CONFIGURED": 409,
    "PROVIDER_IDEMPOTENCY_REUSED": 409,
    "KNOWLEDGE_TIMEOUT": 503,
    "KNOWLEDGE_DOCUMENT_NOT_FOUND": 404,
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


def _monitor_history(services: V1Services) -> MonitorHistoryApplicationService:
    """读取已装配的静态服务注册表，构造历史查询用例。"""
    if services.service_registry is None:
        raise ServiceCenterUnavailableError()
    settings = load_monitor_settings()
    return MonitorHistoryApplicationService(
        session_factory=services.session_factory,
        registry=services.service_registry,
        sample_interval_seconds=settings.sample_interval_seconds,
        retention_hours=settings.retention_hours,
        query_max_hours=settings.query_max_hours,
    )


def _monitor_overview(services: V1Services) -> MonitorOverviewApplicationService:
    """读取已装配的静态服务注册表，构造概览用例。"""
    if services.service_registry is None:
        raise ServiceCenterUnavailableError()
    settings = load_monitor_settings()
    return MonitorOverviewApplicationService(
        session_factory=services.session_factory,
        registry=services.service_registry,
        sample_interval_seconds=settings.sample_interval_seconds,
        retention_hours=settings.retention_hours,
    )


def _action_service(services: V1Services) -> ActionApplicationService:
    """读取已装配的 P4.2 action 服务；旧 P2 测试装配不暴露动作能力。"""
    if services.action_service is None:
        raise ActionProposalInvalidStateError("固定修复能力当前不可用。")
    return services.action_service


def _knowledge_service(services: V1Services) -> KnowledgeReaderService | None:
    """读取已装配的 P7 知识库只读服务；未装配返回 None（诚实降级为未配置）。"""
    return services.knowledge_service


def _model_endpoint_resource(config: dict[str, str] | None) -> ModelEndpointResource | None:
    """把模型配置收敛为不含凭据的主机和模型名。"""
    if config is None:
        return None
    base_url = config.get("base_url")
    model = config.get("model")
    api_key = config.get("api_key")
    if not isinstance(base_url, str) or not isinstance(model, str) or not isinstance(api_key, str):
        return None
    if not (base_url.strip() and model.strip() and api_key.strip()):
        return None
    if any(value.lower().startswith("your-") for value in (api_key, base_url, model)):
        return None
    parsed = urlparse(base_url)
    host = parsed.hostname
    if not host:
        return None
    return ModelEndpointResource(
        provider=host,
        base_url_host=host,
        model=model,
        status="configured",
    )


def _model_config_resource(provider_service: ModelProviderApplicationService) -> ModelConfigResource:
    """读取当前生效配置并构建安全模型配置资源（DB 激活 Provider 优先，env/YAML 兜底）。"""
    config = provider_service.effective_config()
    diagnostic = _model_endpoint_resource(config.get("llm"))
    if diagnostic is None:
        diagnostic = ModelEndpointResource(
            provider="未配置",
            base_url_host="未配置",
            model="未配置",
            status="not_configured",
        )
    judge = _model_endpoint_resource(config.get("judge_llm"))
    api_key = config.get("llm", {}).get("api_key") if isinstance(config.get("llm"), dict) else None
    mode: Literal["mock", "real"] = "mock" if (api_key or os.environ.get("OPERMIND_API_KEY")) == "mock" else "real"
    return ModelConfigResource(
        mode=mode,
        diagnostic_model=diagnostic,
        judge_model=judge,
    )


def _model_provider_service(services: V1Services) -> ModelProviderApplicationService:
    """装配 Provider 应用服务；主密钥未配置时允许只读与无 Key 元数据保存。"""
    try:
        secret_key = load_secret_key()
    except (SecretsSecretKeyNotConfiguredError, SecretKeyTooShortError):
        secret_key = None
    return ModelProviderApplicationService(services.session_factory, secret_key)


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


@router.get("/model/config", response_model=ModelConfigResponse)
def get_model_config(
    request: Request,
    response: Response,
    services: V1Services = Depends(get_v1_services),
) -> ModelConfigResponse:
    """读取当前生效模型配置的脱敏视图（DB 激活 Provider 优先，env/YAML 兜底）。"""
    meta = response_meta(request)
    apply_headers(response, meta)
    return ModelConfigResponse(config=_model_config_resource(_model_provider_service(services)), meta=meta)


@router.get("/model/providers", response_model=ModelProviderListResponse)
def list_model_providers(
    request: Request,
    response: Response,
    services: V1Services = Depends(get_v1_services),
) -> ModelProviderListResponse:
    """列出已配置的模型 Provider 安全视图，不含 API Key 明文。"""
    try:
        items = _model_provider_service(services).list()
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request)
    apply_headers(response, meta)
    return ModelProviderListResponse(items=[provider_resource(item) for item in items], meta=meta)


@router.post("/model/providers", response_model=ModelProviderResponse, status_code=201)
def create_model_provider(
    payload: CreateModelProviderRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    services: V1Services = Depends(get_v1_services),
) -> ModelProviderResponse:
    """新增模型 Provider；API Key 加密后落库，同幂等键同载荷重放。"""
    try:
        created = _model_provider_service(services).create(
            CreateModelProviderCommand(
                name=payload.name,
                base_url=payload.base_url,
                model=payload.model,
                api_key=payload.api_key,
                idempotency_key=parse_idempotency_key(idempotency_key),
                request_fingerprint=provider_create_fingerprint(
                    payload.name, payload.base_url, payload.model, payload.api_key
                ),
            )
        )
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request)
    apply_headers(response, meta)
    return ModelProviderResponse(provider=provider_resource(created), meta=meta)


@router.put("/model/providers/{provider_id}", response_model=ModelProviderResponse)
def update_model_provider(
    provider_id: UUID,
    payload: UpdateModelProviderRequest,
    request: Request,
    response: Response,
    services: V1Services = Depends(get_v1_services),
) -> ModelProviderResponse:
    """编辑 Provider；api_key 不传=保留，空串=清空。"""
    try:
        updated = _model_provider_service(services).update(
            UpdateModelProviderCommand(
                provider_id=provider_id,
                name=payload.name,
                base_url=payload.base_url,
                model=payload.model,
                api_key=payload.api_key,
            )
        )
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request)
    apply_headers(response, meta)
    return ModelProviderResponse(provider=provider_resource(updated), meta=meta)


@router.post("/model/providers/{provider_id}/activate", response_model=ModelProviderResponse)
def activate_model_provider(
    provider_id: UUID,
    payload: ActivateModelProviderRequest,
    request: Request,
    response: Response,
    services: V1Services = Depends(get_v1_services),
) -> ModelProviderResponse:
    """激活 Provider 为指定端点生效配置（单事务原子替换）。"""
    try:
        activated = _model_provider_service(services).activate(
            ActivateModelProviderCommand(
                provider_id=provider_id,
                endpoint=ProviderEndpoint(payload.endpoint),
            )
        )
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request)
    apply_headers(response, meta)
    return ModelProviderResponse(provider=provider_resource(activated), meta=meta)


@router.post("/model/providers/{provider_id}/verify", response_model=ModelProviderResponse)
def verify_model_provider(
    provider_id: UUID,
    request: Request,
    response: Response,
    services: V1Services = Depends(get_v1_services),
) -> ModelProviderResponse:
    """受控、限时验证 Provider 连通；只发最小只读请求，失败返回脱敏原因。"""
    try:
        verified = _model_provider_service(services).verify(provider_id)
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request)
    apply_headers(response, meta)
    return ModelProviderResponse(provider=provider_resource(verified), meta=meta)


@router.delete("/model/providers/{provider_id}", status_code=204)
def delete_model_provider(
    provider_id: UUID,
    request: Request,
    response: Response,
    services: V1Services = Depends(get_v1_services),
) -> Response:
    """删除 Provider；不存在返回 404。"""
    try:
        _model_provider_service(services).delete(provider_id)
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request)
    return Response(status_code=204, headers={"X-Request-Id": str(meta.request_id)})


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


@router.get("/services/{service_id}/monitor/history", response_model=MonitorHistoryResponse)
def get_service_monitor_history(
    service_id: str,
    request: Request,
    response: Response,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    hours: int | None = Query(default=None, ge=1),
    services: V1Services = Depends(get_v1_services),
) -> MonitorHistoryResponse:
    """读取静态服务的定时采样历史，不触发目标连接。"""
    try:
        value = _monitor_history(services).get_history(service_id, from_at=from_, to_at=to, hours=hours)
    except ValueError as error:
        code = str(error)
        if code == "SERVICE_NOT_FOUND":
            raise ApiV1Error(404, code, "已注册服务不存在") from error
        if code in {"WINDOW_CONFLICT", "WINDOW_INVALID", "WINDOW_TOO_LARGE"}:
            raise ApiV1Error(422, "VALIDATION_ERROR", "请求时间窗口不合法") from error
        raise ApiV1Error(500, "INTERNAL_ERROR", "服务内部错误，请稍后重试") from error
    meta = response_meta(request)
    apply_headers(response, meta)
    payload = monitor_history_resource(value)
    payload["meta"] = meta
    return MonitorHistoryResponse.model_validate(payload)


@router.get("/monitor/overview", response_model=MonitorOverviewResponse)
async def get_monitor_overview(
    request: Request,
    response: Response,
    services: V1Services = Depends(get_v1_services),
) -> MonitorOverviewResponse:
    """读取全部已注册服务的监控概览，只读历史样本、不触发目标连接。

    读库限时 3 秒（复用网关超时模式），超时返回 INTERNAL_ERROR 安全错误，不影响既有接口。
    """
    try:
        value = await asyncio.wait_for(
            asyncio.to_thread(_monitor_overview(services).get_overview),
            timeout=OVERVIEW_READ_TIMEOUT_SECONDS,
        )
    except TimeoutError as error:
        raise ApiV1Error(500, "INTERNAL_ERROR", "服务内部错误，请稍后重试") from error
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request)
    apply_headers(response, meta)
    payload = monitor_overview_resource(value)
    payload["meta"] = meta
    return MonitorOverviewResponse.model_validate(payload)


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
                service_id=payload.service_id,
                service_ids=tuple(payload.service_ids) if payload.service_ids is not None else None,
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


@router.post("/sessions/{session_id}/messages", response_model=PlainMessageResponse, status_code=201)
def send_plain_message(
    session_id: UUID,
    payload: SendPlainMessageRequest,
    request: Request,
    response: Response,
    services: V1Services = Depends(get_v1_services),
) -> PlainMessageResponse:
    """普通对话消息走轻量回复，不创建 Run、不触发多 Agent 调查。

    服务端权威判定意图：调查类问题返回 409 INVESTIGATION_REQUIRED，
    由前端回退到既有 ``POST /sessions/{id}/runs`` 主链路。
    """
    plain = services.plain_message_service
    if plain is None:
        raise ApiV1Error(409, "PLAIN_MESSAGE_UNAVAILABLE", "普通消息通道当前不可用。")
    try:
        result = plain.send_plain_message(
            session_id,
            SendPlainMessageCommand(content=payload.content),
        )
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request)
    apply_headers(response, meta)
    return PlainMessageResponse(
        user_message=message_resource(result.user_message),
        assistant_message=message_resource(result.assistant_message),
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
                service_id=payload.service_id,
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


@router.post("/runs/{run_id}/cancel", status_code=204)
def cancel_run(
    run_id: UUID,
    request: Request,
    response: Response,
    services: V1Services = Depends(get_v1_services),
) -> Response:
    """取消运行中的 Run（queued/running）；已结束 Run 返回 409，重复取消幂等 204。"""
    try:
        services.run_service.cancel_run(run_id)
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request)
    return Response(status_code=204, headers={"X-Request-Id": str(meta.request_id)})


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


@router.get("/action-proposals", response_model=ActionProposalListResponse)
def list_action_proposals(
    request: Request,
    response: Response,
    cursor: str | None = None,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    status: ActionProposalStatus | None = None,
    services: V1Services = Depends(get_v1_services),
) -> ActionProposalListResponse:
    """跨会话跨 Run 读取提案安全摘要页（cursor 分页 + 可选状态过滤）。"""
    decoded_cursor = parse_page_cursor(cursor, ActionProposalCursor)
    try:
        page = _action_service(services).list_proposals(decoded_cursor, limit, status)
    except ApplicationError as error:
        raise_application_error(error)
    meta = response_meta(request)
    apply_headers(response, meta)
    return ActionProposalListResponse(
        items=[action_proposal_summary_resource(item) for item in page.items],
        page=CursorPage(next_cursor=encode_cursor(page.next_cursor) if page.next_cursor else None, has_more=page.has_more),
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

    def envelope_factory(event: RunEventData) -> RunEventEnvelope:
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


@router.get("/knowledge/documents", response_model=KnowledgeListResponse)
def list_knowledge_documents(
    request: Request,
    response: Response,
    services: V1Services = Depends(get_v1_services),
) -> KnowledgeListResponse:
    """列出受管知识目录内的 Markdown 文档清单（标题 + 相对路径）。"""
    knowledge = _knowledge_service(services)
    status: Literal["not_configured", "empty", "ok"]
    items: list[KnowledgeDocumentMeta]
    if knowledge is None:
        status, items = "not_configured", []
    else:
        try:
            status, items = knowledge.list_documents()
        except KnowledgeTimeoutError as err:
            # from err 只进服务端日志；响应体由 handler 从 code/message 构造，不含异常链。
            raise ApiV1Error(503, "KNOWLEDGE_TIMEOUT", "知识库读取超时，请稍后重试") from err
    meta = response_meta(request)
    apply_headers(response, meta)
    return KnowledgeListResponse(
        status=status,
        items=[knowledge_document_resource(item) for item in items],
        meta=meta,
    )


@router.get("/knowledge/search", response_model=KnowledgeSearchResponse)
def search_knowledge(
    request: Request,
    response: Response,
    query: Annotated[str, Query(min_length=1, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
    services: V1Services = Depends(get_v1_services),
) -> KnowledgeSearchResponse:
    """在受管知识目录内按关键词确定性检索 Markdown 文档。"""
    normalized_query = query.strip()
    if not normalized_query or _ILLEGAL_QUERY_RE.search(query):
        raise ApiV1Error(422, "VALIDATION_ERROR", "检索词不能为空且不含路径分隔符或控制字符")
    knowledge = _knowledge_service(services)
    status: Literal["not_configured", "empty", "no_match", "ok"]
    items: list[KnowledgeSearchHit]
    if knowledge is None:
        status, items = "not_configured", []
    else:
        try:
            status, items = knowledge.search(normalized_query, limit)
        except KnowledgeTimeoutError as err:
            raise ApiV1Error(503, "KNOWLEDGE_TIMEOUT", "知识库检索超时，请稍后重试") from err
    meta = response_meta(request)
    apply_headers(response, meta)
    return KnowledgeSearchResponse(
        status=status,
        query=normalized_query,
        items=[knowledge_search_hit_resource(item) for item in items],
        meta=meta,
    )


def _knowledge_document_title(content: str, relative_path: str) -> str:
    """从正文提取首个一级标题作为文档标题；无标题时回退文件名。"""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return relative_path.rsplit("/", 1)[-1].removesuffix(".md")


@router.get("/knowledge/documents/{document_path:path}", response_model=KnowledgeDocumentResponse)
def get_knowledge_document(
    document_path: str,
    request: Request,
    response: Response,
    services: V1Services = Depends(get_v1_services),
) -> KnowledgeDocumentResponse:
    """按受管目录内相对路径返回 Markdown 文档正文（脱敏后）。"""
    knowledge = _knowledge_service(services)
    if knowledge is None or knowledge.root is None:
        meta = response_meta(request)
        apply_headers(response, meta)
        return KnowledgeDocumentResponse(status="not_configured", document=None, meta=meta)
    if _ILLEGAL_PATH_RE.search(document_path):
        raise ApiV1Error(404, "KNOWLEDGE_DOCUMENT_NOT_FOUND", "知识文档不存在或不可访问")
    try:
        content = knowledge.get_document(document_path)
    except KnowledgeTimeoutError as err:
        raise ApiV1Error(503, "KNOWLEDGE_TIMEOUT", "知识库读取超时，请稍后重试") from err
    if content is None:
        raise ApiV1Error(404, "KNOWLEDGE_DOCUMENT_NOT_FOUND", "知识文档不存在或不可访问")
    meta = response_meta(request)
    apply_headers(response, meta)
    return KnowledgeDocumentResponse(
        status="ok",
        document=KnowledgeDocumentDetailResource(
            title=_knowledge_document_title(content, document_path),
            relative_path=document_path,
            content=content,
        ),
        meta=meta,
    )
