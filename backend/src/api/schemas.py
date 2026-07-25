"""HTTP API 的请求、响应与错误契约。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


TraceEventType = Literal[
    "route_decided",
    "agent_start",
    "agent_done",
    "conflict_checked",
    "debate_round",
    "report",
    "reflection",
]


class ApiModel(BaseModel):
    """API 数据模型基类，拒绝未约定字段。"""

    model_config = ConfigDict(extra="forbid")


class DiagnoseRequest(ApiModel):
    """同步诊断请求。"""

    query: str = Field(..., min_length=1, max_length=4000, description="待诊断的运维问题")
    show_thinking: bool = Field(False, description="是否返回诊断链路")

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        """去除首尾空白，并拒绝空问题。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("query 不能为空")
        return normalized


class TraceEvent(ApiModel):
    """诊断编排中的单条可视化事件。"""

    type: TraceEventType
    node: str = Field(..., min_length=1)
    detail: str = Field(..., min_length=1)
    timestamp: str = Field(..., min_length=1, description="UTC ISO 8601 时间戳")


class DiagnoseResponse(ApiModel):
    """同步诊断响应。"""

    result: str
    thinking: list[str] | None = None
    trace: list[TraceEvent] | None = None
    strategy: str = ""


class ErrorDetail(ApiModel):
    """参数校验失败时的单条字段错误。"""

    location: list[str | int]
    message: str
    error_type: str


class ErrorResponse(ApiModel):
    """统一错误响应。"""

    code: str
    message: str
    details: list[ErrorDetail] | None = None


class HealthResponse(ApiModel):
    """服务健康检查响应。"""

    status: Literal["ok"]
    mode: Literal["mock", "real"]
    model: str


class RootResponse(ApiModel):
    """服务入口说明。"""

    name: str
    version: str
    description: str
    endpoints: dict[str, str]


class MemoryResponse(ApiModel):
    """保留的记忆接口响应。"""

    status: str | None = None
    message: str


class StreamQuery(ApiModel):
    """SSE 诊断请求的查询参数。"""

    query: str = Field(..., min_length=1, max_length=4000)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        """复用同步接口的空白校验语义。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("query 不能为空")
        return normalized
