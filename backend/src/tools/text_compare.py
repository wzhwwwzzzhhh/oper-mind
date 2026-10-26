"""纯计算文本比较 Tool：只读本 Run 注入的材料映射，无磁盘／网络能力。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from uuid import UUID

from src.capabilities.text_compare import (
    TEXT_COMPARE_TOOL_NAME,
    TextComparisonLimitError,
    compare_materials,
)
from src.core.tool_registry import Tool, ToolExecutionResult
from src.domain.main_agent import (
    MAIN_AGENT_RULE_VERSION,
    MainMaterialSnapshotV1,
)


class TextCompareTool(Tool):
    """按本 Run 冻结材料执行字面对照；模型只能提交材料引用。"""

    def __init__(
        self,
        *,
        run_id: UUID,
        materials: Mapping[UUID, MainMaterialSnapshotV1],
    ) -> None:
        super().__init__(
            name=TEXT_COMPARE_TOOL_NAME,
            description="比较本 Run 的文本 A（旧）与文本 B（新），返回逐行差异块。",
            parameters={
                "type": "object",
                "properties": {
                    "a_material_id": {
                        "type": "string",
                        "description": "文本 A 的材料引用（本 Run 材料 ID）",
                    },
                    "b_material_id": {
                        "type": "string",
                        "description": "文本 B 的材料引用（本 Run 材料 ID）",
                    },
                    "rule_version": {
                        "type": "string",
                        "description": "固定比较规则版本",
                    },
                },
                "required": ["a_material_id", "b_material_id", "rule_version"],
                "additionalProperties": False,
            },
        )
        self._run_id = run_id
        self._materials = dict(materials)

    def execute(
        self,
        a_material_id: str,
        b_material_id: str,
        rule_version: str,
    ) -> ToolExecutionResult:
        """严格校验引用后计算完整比较结果；失败只返回安全不可用。"""
        if rule_version != MAIN_AGENT_RULE_VERSION:
            return _unavailable("比较规则版本不可用。")
        try:
            material_a = self._materials[UUID(a_material_id)]
            material_b = self._materials[UUID(b_material_id)]
        except (KeyError, ValueError):
            return _unavailable("材料引用不可用。")
        if material_a.material_id == material_b.material_id:
            return _unavailable("材料引用不可用。")
        try:
            comparison = compare_materials(
                run_id=self._run_id,
                text_a=material_a,
                text_b=material_b,
            )
        except TextComparisonLimitError:
            return _unavailable("差异块超过上限。")
        return ToolExecutionResult(
            status="ok",
            output=comparison.model_dump_json(),
            summary=f"文本比较完成：{len(comparison.blocks)} 个差异块",
        )


def _unavailable(message: str) -> ToolExecutionResult:
    """返回不携带原文与内部细节的安全不可用结果。"""
    return ToolExecutionResult(
        status="unavailable",
        output=json.dumps({"error": message}, ensure_ascii=False),
        summary=message,
    )
