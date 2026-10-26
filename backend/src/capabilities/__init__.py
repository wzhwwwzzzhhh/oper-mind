"""V2 Capability 的最小显式注册接缝。

首版只提供不可变声明与显式注册：没有扫描、自动发现、热加载或市场。
组合根必须逐个注册已确认能力，执行器只按注册表解析模型提出的能力引用。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

MaterialSide = Literal["text_a", "text_b"]


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    """单个能力的可信声明；只描述契约，不持有运行期资源。"""

    capability_id: str
    version: int
    rule_version: str
    description: str
    usage_guide: str
    allowed_tools: tuple[str, ...]
    required_materials: tuple[MaterialSide, ...]


class CapabilityRegistry:
    """进程内显式注册表；重复注册同一能力版本直接拒绝。"""

    def __init__(self, definitions: Iterable[CapabilityDefinition] = ()) -> None:
        self._definitions: dict[tuple[str, int], CapabilityDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: CapabilityDefinition) -> None:
        """注册一个能力版本；不做任何隐式发现。"""
        key = (definition.capability_id, definition.version)
        if key in self._definitions:
            raise ValueError("能力版本重复注册。")
        self._definitions[key] = definition

    def get(self, capability_id: str, version: int) -> CapabilityDefinition | None:
        """按能力 ID 与版本读取；未知组合返回 None（调用方安全失败）。"""
        return self._definitions.get((capability_id, version))

    def definitions(self) -> tuple[CapabilityDefinition, ...]:
        """返回已注册能力的不可变快照，供提示词与测试核对。"""
        return tuple(self._definitions.values())
