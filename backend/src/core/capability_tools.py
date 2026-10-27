"""能力声明的 Tool 绑定：按工具名装配，主循环不按能力 id 分支。"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError

from src.capabilities import CapabilityDefinition
from src.capabilities.text_compare import TEXT_COMPARE_TOOL_NAME
from src.core.tool_registry import Tool, ToolRegistry
from src.domain.main_agent import (
    MainInputSnapshotV1,
    MainMaterialSnapshotV1,
    TextComparisonV1,
)
from src.tools.text_compare import TextCompareTool


@dataclass(frozen=True, slots=True)
class TypedCapabilityResult:
    """一次执行型能力的 typed 结果；V2-1 只有已校验比较结果。"""

    comparison: TextComparisonV1


class ToolBinding(Protocol):
    """能力工具绑定：负责装配 Tool、构造参数与解析 typed 结果。"""

    name: str

    def build_tool(self, *, run_id: UUID, snapshot: MainInputSnapshotV1) -> Tool:
        """按本次 Run 的冻结材料装配只读 Tool。"""

    def build_arguments(
        self,
        *,
        definition: CapabilityDefinition,
        inputs: Mapping[str, UUID],
        rule_version: str | None,
    ) -> str:
        """把已校验的材料引用转换为工具 JSON 参数。"""

    def parse_result(
        self,
        *,
        definition: CapabilityDefinition,
        output: str,
        run_id: UUID,
        inputs: Mapping[str, UUID],
        rule_version: str | None,
    ) -> TypedCapabilityResult | None:
        """解析工具输出；身份或契约不一致返回 None（调用方安全失败）。"""


class TextCompareToolBinding:
    """文本比较工具绑定：材料槽位到工具参数的唯一映射点。"""

    name = TEXT_COMPARE_TOOL_NAME

    def build_tool(self, *, run_id: UUID, snapshot: MainInputSnapshotV1) -> Tool:
        materials: dict[UUID, MainMaterialSnapshotV1] = {}
        if snapshot.text_a is not None:
            materials[snapshot.text_a.material_id] = snapshot.text_a
        if snapshot.text_b is not None:
            materials[snapshot.text_b.material_id] = snapshot.text_b
        return TextCompareTool(run_id=run_id, materials=materials)

    def build_arguments(
        self,
        *,
        definition: CapabilityDefinition,
        inputs: Mapping[str, UUID],
        rule_version: str | None,
    ) -> str:
        return json.dumps(
            {
                "a_material_id": str(inputs["text_a"]),
                "b_material_id": str(inputs["text_b"]),
                "rule_version": rule_version or definition.rule_version,
            },
            ensure_ascii=False,
        )

    def parse_result(
        self,
        *,
        definition: CapabilityDefinition,
        output: str,
        run_id: UUID,
        inputs: Mapping[str, UUID],
        rule_version: str | None,
    ) -> TypedCapabilityResult | None:
        try:
            comparison = TextComparisonV1.model_validate_json(output)
        except ValidationError:
            return None
        if (
            comparison.run_id != run_id
            or comparison.capability_id != definition.capability_id
            or comparison.capability_version != definition.version
            or comparison.a_material_id != inputs.get("text_a")
            or comparison.b_material_id != inputs.get("text_b")
            or comparison.rule_version != (rule_version or definition.rule_version)
        ):
            return None
        return TypedCapabilityResult(comparison=comparison)


class ToolBindingRegistry:
    """工具名到绑定的显式注册表；未绑定的声明由工具网关拒绝。"""

    def __init__(self, bindings: Iterable[ToolBinding] = ()) -> None:
        self._bindings: dict[str, ToolBinding] = {}
        for binding in bindings:
            self.register(binding)

    def register(self, binding: ToolBinding) -> None:
        if not binding.name or binding.name in self._bindings:
            raise ValueError("工具绑定重复或名称为空。")
        self._bindings[binding.name] = binding

    def get(self, name: str) -> ToolBinding | None:
        return self._bindings.get(name)

    def build_tool_registry(
        self,
        definition: CapabilityDefinition,
        *,
        run_id: UUID,
        snapshot: MainInputSnapshotV1,
    ) -> ToolRegistry:
        """只装配能力声明且已绑定的工具；未知绑定留给网关安全拒绝。"""
        registry = ToolRegistry()
        for name in definition.tool_bindings:
            binding = self._bindings.get(name)
            if binding is not None:
                registry.register(binding.build_tool(run_id=run_id, snapshot=snapshot))
        return registry
