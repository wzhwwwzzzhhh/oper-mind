"""FastAPI 入口 — 会话式多 Agent 运维诊断 API。

正式产品主线是 `/api/v1`（会话 / Run / SSE / 审批）。旧的 `/diagnose`
（曾按参数回吐模型思考链）与 `/memory/*` 桩接口已移除：诊断只经由 v1 的
Run 主脊执行，Trace 只展示安全摘要，不暴露 CoT。
"""

import logging
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.api.schemas import ErrorDetail, ErrorResponse, HealthResponse, RootResponse
from src.api.v1.dependencies import build_v1_services
from src.api.v1.errors import ApiV1Error
from src.api.v1.routes import router as v1_router
from src.api.v1.schemas import ApiError as V1ApiError
from src.api.v1.schemas import ErrorEnvelope, FieldIssue, ResponseMeta
from src.core.bootstrap import build_coordinator, build_llm


LOGGER = logging.getLogger(__name__)

@asynccontextmanager
async def _lifespan(application: FastAPI):
    """管理单进程历史监控采样任务的生命周期。"""
    sampler = getattr(application.state.v1_services, "monitor_sampler", None)
    task = None
    if sampler is not None:
        import asyncio
        task = asyncio.create_task(sampler.run_forever())
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title="OperMind — 会话式多 Agent 运维诊断系统",
    description="在会话中提出运维问题，多 Agent 协作调查并给出安全结论",
    version="1.1.0",
    lifespan=_lifespan,
)

# 共享 LLM 客户端（多 Run 间无可变状态，可安全复用）。
_shared_llm = build_llm()
# v1 正式路径：每 Run 现造一套内核，隔离并发 Agent 状态。
app.state.v1_services = build_v1_services(lambda service_id: build_coordinator(_shared_llm, service_id=service_id))


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
    """将 v1 协议异常转换为安全错误包络。"""
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
    """v1 使用安全包络，其余路径输出通用错误体。"""
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


def _service_mode() -> str:
    """返回安全的运行模式标识，不泄露 API Key。"""
    return "mock" if getattr(_shared_llm, "client", None) and getattr(_shared_llm.client, "api_key", None) == "mock" else "real"


@app.get("/", response_model=RootResponse)
def root() -> RootResponse:
    """返回服务基本信息和可用接口。"""
    return RootResponse(
        name="OperMind",
        version="1.1.0",
        description="会话式多 Agent 运维诊断协作系统",
        endpoints={
            "GET /health": "健康检查",
            "/api/v1": "正式产品 API（会话 / Run / SSE / 审批）",
        },
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """返回可用于前端状态栏的非敏感服务状态。"""
    return HealthResponse(
        status="ok",
        mode=_service_mode(),
        model=getattr(_shared_llm, "model", "unknown"),
    )


app.include_router(v1_router)
