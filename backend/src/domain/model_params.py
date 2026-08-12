"""P8 模型运行参数领域模型。

参数是全局运行时态（非 Provider 属性）：持久化于 ``app_settings``
（key=``model.params``，JSON），未配置时由后端默认值承担。
"""

from __future__ import annotations

import json
from typing import TypedDict

from pydantic import BaseModel, ConfigDict, Field

#: app_settings 中存储模型运行参数的键。
MODEL_PARAMS_KEY = "model.params"

#: temperature 未配置时的后端默认（保持现状：实验可复现）。
DEFAULT_TEMPERATURE = 0.0

#: max_tokens 未配置时不传 SDK（用模型自身默认）。
DEFAULT_MAX_TOKENS: int | None = None


class ModelParams(BaseModel):
    """已配置的模型运行参数；字段为 None 表示未配置（该项用默认值）。"""

    model_config = ConfigDict(extra="forbid")

    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=102400)


class ModelParamsResolution(TypedDict):
    """参数解析结果：已配置值（未配置为 None）+ 后端默认值（诚实标注用）。"""

    temperature: float | None
    max_tokens: int | None
    temperature_default: float
    max_tokens_default: int | None


def encode_params(params: ModelParams) -> str:
    """把参数序列化为 app_settings 存储值（仅存已配置字段）。"""
    stored: dict[str, int | float] = {}
    if params.temperature is not None:
        stored["temperature"] = params.temperature
    if params.max_tokens is not None:
        stored["max_tokens"] = params.max_tokens
    return json.dumps(stored, ensure_ascii=False)


def decode_params(raw: str | None) -> ModelParams:
    """从 app_settings 存储值解析参数；缺失或损坏时诚实降级为未配置。"""
    if raw is None or raw == "":
        return ModelParams()
    try:
        return ModelParams.model_validate_json(raw)
    except ValueError:
        return ModelParams()


def default_resolution() -> ModelParamsResolution:
    """返回未配置时的参数解析结果（后端默认值）。"""
    return ModelParamsResolution(
        temperature=None,
        max_tokens=None,
        temperature_default=DEFAULT_TEMPERATURE,
        max_tokens_default=DEFAULT_MAX_TOKENS,
    )
