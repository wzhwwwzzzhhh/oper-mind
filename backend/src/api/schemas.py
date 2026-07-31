"""非 v1 基础 HTTP 接口（`/`、`/health`）的响应与错误契约。

诊断相关 DTO 已随旧 `/diagnose` 接口移除；正式产品契约见 `src/api/v1/schemas.py`。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """API 数据模型基类，拒绝未约定字段。"""

    model_config = ConfigDict(extra="forbid")


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
