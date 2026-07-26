"""FastAPI 入口 — 多智能体运维诊断 API。"""

from collections.abc import Iterator
import logging
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import ValidationError

from src.api.events import (
    DiagnosisCompleteEvent,
    DiagnosisErrorEvent,
    DiagnosisProgressEvent,
    serialize_sse,
)
from src.api.schemas import (
    DiagnoseRequest,
    DiagnoseResponse,
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    MemoryResponse,
    RootResponse,
    StreamQuery,
    TraceEvent,
)
from src.api.v1.dependencies import build_v1_services
from src.api.v1.errors import ApiV1Error
from src.api.v1.routes import router as v1_router
from src.api.v1.schemas import ApiError as V1ApiError
from src.api.v1.schemas import ErrorEnvelope, FieldIssue, ResponseMeta
from src.core.bootstrap import build_system


LOGGER = logging.getLogger(__name__)

app = FastAPI(
    title="OperMind — 多智能体运维诊断系统",
    description="输入运维问题，AI Agent 自动诊断并给出优化建议",
    version="1.1.0",
)

# 系统装配保持单例；测试可替换该变量与 v1_services 以隔离外部依赖。
coordinator = build_system()
app.state.v1_services = build_v1_services(coordinator)


@app.middleware("http")
async def v1_request_id_middleware(request: Request, call_next):
    """仅为 `/api/v1` 验证或生成 request id，并在所有 v1 响应回显。"""
    if not request.url.path.startswith("/api/v1"):
        return await call_next(request)

    supplied_request_id = request.headers.get("X-Request-Id")
    try:
        request_id = UUID(supplied_request_id) if supplied_request_id else uuid4()
    except (TypeError, ValueError, AttributeError):
        request_id = uuid4()
        meta = ResponseMeta(request_id=request_id)
        envelope = ErrorEnvelope(
            error=V1ApiError(code="INVALID_REQUEST_ID", message="请求关联 ID 无效"),
            meta=meta,
        )
        return JSONResponse(
            status_code=400,
            content=envelope.model_dump(mode="json"),
            headers={"X-Request-Id": str(request_id)},
        )

    request.state.v1_request_id = request_id
    response = await call_next(request)
    response.headers.setdefault("X-Request-Id", str(request_id))
    return response


@app.exception_handler(ApiV1Error)
async def api_v1_error_handler(request: Request, exc: ApiV1Error) -> JSONResponse:
    """将 v1 协议异常转换为 P0.3 安全错误包络。"""
    meta = _v1_response_meta(request)
    envelope = ErrorEnvelope(error=V1ApiError(code=exc.code, message=exc.message), meta=meta)
    headers = {"X-Request-Id": str(meta.request_id)}
    if meta.trace_id is not None:
        headers["X-Trace-Id"] = str(meta.trace_id)
    return JSONResponse(status_code=exc.status_code, content=envelope.model_dump(mode="json"), headers=headers)


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """按接口版本输出稳定的字段校验错误体。"""
    if request.url.path.startswith("/api/v1"):
        meta = _v1_response_meta(request)
        envelope = ErrorEnvelope(
            error=V1ApiError(
                code="VALIDATION_ERROR",
                message="请求参数不合法",
                details=_v1_validation_details(exc.errors()),
            ),
            meta=meta,
        )
        return JSONResponse(
            status_code=422,
            content=envelope.model_dump(mode="json"),
            headers={"X-Request-Id": str(meta.request_id)},
        )

    response = ErrorResponse(
        code="VALIDATION_ERROR",
        message="请求参数不合法",
        details=_validation_details(exc.errors()),
    )
    return JSONResponse(status_code=422, content=response.model_dump(mode="json"))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """保留阶段一业务 HTTP 异常输出；v1 使用安全包络。"""
    message = exc.detail if isinstance(exc.detail, str) else "请求处理失败"
    if request.url.path.startswith("/api/v1"):
        meta = _v1_response_meta(request)
        envelope = ErrorEnvelope(error=V1ApiError(code="HTTP_ERROR", message=message), meta=meta)
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope.model_dump(mode="json"),
            headers={"X-Request-Id": str(meta.request_id)},
        )
    response = ErrorResponse(code="HTTP_ERROR", message=message)
    return JSONResponse(status_code=exc.status_code, content=response.model_dump(mode="json"))


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """隐藏内部异常细节，避免通过 API 暴露配置或实现信息。"""
    LOGGER.exception("诊断 API 未处理异常", exc_info=exc)
    if request.url.path.startswith("/api/v1"):
        meta = _v1_response_meta(request)
        envelope = ErrorEnvelope(
            error=V1ApiError(code="INTERNAL_ERROR", message="服务内部错误，请稍后重试"),
            meta=meta,
        )
        return JSONResponse(
            status_code=500,
            content=envelope.model_dump(mode="json"),
            headers={"X-Request-Id": str(meta.request_id)},
        )
    response = ErrorResponse(code="INTERNAL_ERROR", message="服务内部错误，请稍后重试")
    return JSONResponse(status_code=500, content=response.model_dump(mode="json"))


def _v1_response_meta(request: Request) -> ResponseMeta:
    """在 v1 错误分支也稳定提供 request id。"""
    request_id = getattr(request.state, "v1_request_id", None)
    return ResponseMeta(request_id=request_id if isinstance(request_id, UUID) else uuid4())


def _v1_validation_details(errors: list[dict[str, object]]) -> list[FieldIssue]:
    """将框架校验错误收敛为可安全展示的字段和原因。"""
    details: list[FieldIssue] = []
    for error in errors:
        location = [str(part) for part in error.get("loc", ()) if part not in {"body", "query", "path", "header"}]
        field = ".".join(location) or "request"
        details.append(FieldIssue(field=field, reason=str(error.get("msg", "参数不合法"))))
    return details


def _validation_details(errors: list[dict[str, object]]) -> list[ErrorDetail]:
    """将 FastAPI/Pydantic 的原始校验错误转换为稳定公开契约。"""
    return [
        ErrorDetail(
            location=[str(part) if not isinstance(part, int) else part for part in error.get("loc", ())],
            message=str(error.get("msg", "参数不合法")),
            error_type=str(error.get("type", "validation_error")),
        )
        for error in errors
    ]


def _extract_strategy(trace: list[TraceEvent]) -> str:
    """从编排 trace 中提取最终生效的路由策略。"""
    for event in trace:
        if event.node != "route":
            continue
        for strategy in ("direct", "chain", "parallel"):
            if strategy in event.detail:
                return strategy
    return ""


def _service_mode() -> str:
    """返回安全的运行模式标识，不泄露 API Key。"""
    llm = getattr(coordinator, "llm", None)
    client = getattr(llm, "client", None)
    return "mock" if getattr(client, "api_key", None) == "mock" else "real"


def _diagnosis_sse_stream(query: str) -> Iterator[str]:
    """将 Coordinator 的流式编排结果转换为 SSE 帧，并保障异常有标准结束事件。"""
    try:
        for item in coordinator.route_stream(query):
            kind = item["kind"]
            if kind == "trace":
                payload = DiagnosisProgressEvent.model_validate(item["event"])
                yield serialize_sse("progress", payload)
            elif kind == "complete":
                trace = [TraceEvent.model_validate(event) for event in item["trace"]]
                payload = DiagnosisCompleteEvent(
                    result=item["result"],
                    strategy=item["strategy"],
                    trace=trace,
                )
                yield serialize_sse("complete", payload)
            elif kind == "error":
                payload = DiagnosisErrorEvent(code=item["code"], message=item["message"])
                yield serialize_sse("error", payload)
    except (KeyError, TypeError, ValidationError):
        LOGGER.exception("SSE 事件序列化失败")
        payload = DiagnosisErrorEvent(
            code="STREAM_SERIALIZATION_FAILED",
            message="诊断流事件处理失败，请稍后重试",
        )
        yield serialize_sse("error", payload)


@app.get("/", response_model=RootResponse)
def root() -> RootResponse:
    """返回服务基本信息和可用接口。"""
    return RootResponse(
        name="OperMind",
        version="1.1.0",
        description="多智能体运维诊断协作系统",
        endpoints={
            "POST /diagnose": "同步诊断问题",
            "GET /diagnose/stream": "SSE 流式诊断",
            "GET /health": "健康检查",
            "GET /memory/stats": "记忆统计",
            "POST /memory/clear": "清空记忆",
        },
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """返回可用于前端状态栏的非敏感服务状态。"""
    llm = getattr(coordinator, "llm", None)
    return HealthResponse(
        status="ok",
        mode=_service_mode(),
        model=getattr(llm, "model", "unknown"),
    )


@app.post(
    "/diagnose",
    response_model=DiagnoseResponse,
    responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
def diagnose(request: DiagnoseRequest) -> DiagnoseResponse:
    """执行同步诊断；默认仅返回最终报告以控制响应体大小。"""
    result = coordinator.route(request.query)
    trace = [TraceEvent.model_validate(event) for event in coordinator.get_trace()]
    thinking = coordinator.get_thinking() if request.show_thinking else None
    return DiagnoseResponse(
        result=result,
        thinking=thinking,
        trace=trace if request.show_thinking else None,
        strategy=_extract_strategy(trace),
    )


@app.get(
    "/diagnose/stream",
    response_model=None,
    responses={422: {"model": ErrorResponse}},
)
def diagnose_stream(query: str) -> Response:
    """以 SSE 增量推送路由、Agent 与质量保障节点事件。"""
    try:
        validated = StreamQuery(query=query)
    except ValidationError as exc:
        response = ErrorResponse(
            code="VALIDATION_ERROR",
            message="请求参数不合法",
            details=_validation_details(exc.errors()),
        )
        return JSONResponse(status_code=422, content=response.model_dump(mode="json"))

    return StreamingResponse(
        _diagnosis_sse_stream(validated.query),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/memory/stats", response_model=MemoryResponse)
def memory_stats() -> MemoryResponse:
    """保留旧接口，避免在前端切换期间破坏已有调用。"""
    return MemoryResponse(message="记忆系统统计接口待完善")


@app.post("/memory/clear", response_model=MemoryResponse)
def clear_memory() -> MemoryResponse:
    """保留旧接口，避免把未实现的清理动作伪装为成功。"""
    raise HTTPException(status_code=501, detail="记忆清理接口尚未实现")


app.include_router(v1_router)
