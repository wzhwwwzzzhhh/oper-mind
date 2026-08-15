"""P8 模型用量领域模型。

用量是调用副作用的只读事实：真实调用完成后落库，mock 不采集；
单价为估算口径（每百万 token 人民币元），内置默认表 + app_settings 可覆盖。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Protocol, TypedDict

#: app_settings 中存储单价覆盖的键（JSON：{"<model>": {"input": 1.2, "output": 2.4}}）。
MODEL_PRICES_KEY = "model.prices"

#: 未列出模型的通用默认单价（每百万 token 人民币元，保守偏低，估算口径）。
FALLBACK_MODEL_PRICE_INPUT = 1.0
FALLBACK_MODEL_PRICE_OUTPUT = 2.0


class ModelPrice(TypedDict):
    """单模型的估算单价（每百万 token 人民币元）。"""

    input: float
    output: float


#: 常见模型内置默认单价（每百万 token 人民币元；仅估算口径，非精确账单）。
DEFAULT_MODEL_PRICES: dict[str, ModelPrice] = {
    "deepseek-chat": {"input": 1.0, "output": 2.0},
    "deepseek-reasoner": {"input": 4.0, "output": 16.0},
    "qwen2.5:7b": {"input": 0.5, "output": 1.0},
    "qwen-plus": {"input": 0.8, "output": 2.0},
    "gpt-4o": {"input": 15.0, "output": 60.0},
    "gpt-4o-mini": {"input": 1.5, "output": 6.0},
}


class UsageRecord(TypedDict):
    """单次真实 LLM 调用的用量事实；不含调用内容与凭据。"""

    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    occurred_at: datetime


class UsageRecorder(Protocol):
    """用量采集端口：core 只依赖此协议，具体落库实现在 infrastructure。"""

    def record(self, record: UsageRecord) -> None:
        """写入一次用量事实；失败抛异常由调用方降级处理。"""
        ...


class ModelUsageStatsRow(TypedDict):
    """单模型用量聚合结果（库内 GROUP BY 输出）。"""

    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int


class ModelUsageReader(Protocol):
    """用量统计读取端口：application 只依赖此协议，聚合实现在 infrastructure。"""

    def stats(
        self,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
        model: str | None = None,
    ) -> list[ModelUsageStatsRow]:
        """按时间窗/模型过滤，按模型分组聚合 token 用量；无记录返回空列表。"""
        ...


class PriceOverridesReader(Protocol):
    """单价覆盖读取端口：application 只依赖此协议，存储实现在 infrastructure。"""

    def read(self) -> dict[str, ModelPrice]:
        """读取应用库单价覆盖；缺失/损坏时诚实降级为空覆盖。"""
        ...


def encode_prices(prices: dict[str, ModelPrice]) -> str:
    """把单价覆盖序列化为 app_settings 存储值（JSON）。"""
    return json.dumps(prices, ensure_ascii=False)


def decode_prices(raw: str | None) -> dict[str, ModelPrice]:
    """从 app_settings 存储值解析单价覆盖；缺失或损坏时诚实降级为空覆盖。"""
    if raw is None or raw == "":
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    result: dict[str, ModelPrice] = {}
    for model, value in parsed.items():
        if not isinstance(model, str) or not isinstance(value, dict):
            continue
        try:
            input_price = float(value.get("input", 0))
            output_price = float(value.get("output", 0))
        except (TypeError, ValueError):
            continue
        if input_price < 0 or output_price < 0:
            continue
        result[model] = {"input": input_price, "output": output_price}
    return result


def resolve_price(model: str, overrides: dict[str, ModelPrice] | None = None) -> tuple[ModelPrice, str]:
    """解析模型单价与来源：覆盖表精确匹配 → 内置默认 → 通用默认。

    返回 (单价, 来源)：「configured」= 应用库覆盖、「builtin」= 内置默认表、
    「unset」= 两者皆无（通用默认）。
    """
    if overrides is not None and model in overrides:
        return overrides[model], "configured"
    if model in DEFAULT_MODEL_PRICES:
        return DEFAULT_MODEL_PRICES[model], "builtin"
    return (
        {"input": FALLBACK_MODEL_PRICE_INPUT, "output": FALLBACK_MODEL_PRICE_OUTPUT},
        "unset",
    )
