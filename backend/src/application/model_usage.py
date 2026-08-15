"""P8 模型用量统计应用服务：聚合查询与估算花费。

花费为估算口径（每百万 token 单价 × token），单价来源：app_settings 覆盖（``model.prices``）
→ 内置默认表 → 通用默认；依赖 domain 定义的 ``ModelUsageReader`` / ``PriceOverridesReader``
端口注入（装配在 api/v1/dependencies.py 完成），解析永不 raise，存储不可用时诚实降级。
"""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from sqlalchemy.exc import SQLAlchemyError

from src.domain.model_usage import ModelUsageReader, PriceOverridesReader, resolve_price


class ModelUsageItem(TypedDict):
    """单模型用量聚合结果（含估算花费与单价来源，响应安全视图）。"""

    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float
    price_source: str
    price_per_million_input: float
    price_per_million_output: float


class ModelUsageSummary(TypedDict):
    """用量统计响应内容：按模型分组聚合 + 估算标注。"""

    estimate: bool
    items: list[ModelUsageItem]


class ModelUsageApplicationService:
    """用量统计用例；只读查询，无写路径。"""

    def __init__(self, usage_reader: ModelUsageReader, price_reader: PriceOverridesReader) -> None:
        self._usage_reader = usage_reader
        self._price_reader = price_reader

    def stats(
        self,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
        model: str | None = None,
    ) -> ModelUsageSummary:
        """按时间窗/模型聚合用量并估算花费；无记录返回空 items，永不 raise。"""
        try:
            rows = self._usage_reader.stats(from_at=from_at, to_at=to_at, model=model)
            overrides = self._price_reader.read()
        except SQLAlchemyError:
            # 应用库不可用/未迁移：诚实降级为空统计，不伪造记录。
            rows = []
            overrides = {}
        items: list[ModelUsageItem] = []
        for row in rows:
            price, source = resolve_price(row["model"], overrides)
            estimated_cost = round(
                row["input_tokens"] * price["input"] / 1_000_000
                + row["output_tokens"] * price["output"] / 1_000_000,
                6,
            )
            items.append(
                ModelUsageItem(
                    model=row["model"],
                    input_tokens=row["input_tokens"],
                    output_tokens=row["output_tokens"],
                    total_tokens=row["total_tokens"],
                    estimated_cost=estimated_cost,
                    price_source=source,
                    price_per_million_input=price["input"],
                    price_per_million_output=price["output"],
                )
            )
        return ModelUsageSummary(estimate=True, items=items)
