"""显式能力注册表：按 id + version 解析，最高版本激活，不做扫描或热加载。"""

from __future__ import annotations

from collections.abc import Iterable

from src.capabilities.contract import (
    CapabilityDefinition,
    CapabilityKind,
    CapabilityResolution,
    CapabilitySummary,
    ResolutionKind,
)


class CapabilityRegistry:
    """进程内显式注册表；每个版本只允许注册一次。"""

    def __init__(self, definitions: Iterable[CapabilityDefinition] = ()) -> None:
        self._definitions: dict[tuple[str, int], CapabilityDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: CapabilityDefinition) -> None:
        """注册一个能力版本；重复的 (id, version) 失败关闭。"""
        key = (definition.capability_id, definition.version)
        if key in self._definitions:
            raise ValueError("能力版本重复注册。")
        self._definitions[key] = definition

    def resolve(
        self,
        capability_id: str,
        version: int,
        expected_kind: CapabilityKind | None = None,
    ) -> CapabilityResolution:
        """解析一个能力版本，并区分未知 id／版本／未激活／类型不符。"""
        expected = CapabilityKind(expected_kind) if expected_kind is not None else None
        versions = sorted(
            registered_version
            for (registered_id, registered_version) in self._definitions
            if registered_id == capability_id
        )
        if not versions:
            return CapabilityResolution(kind=ResolutionKind.UNKNOWN_ID, expected_kind=expected)
        definition = self._definitions.get((capability_id, version))
        if definition is None:
            return CapabilityResolution(kind=ResolutionKind.UNKNOWN_VERSION, expected_kind=expected)
        active_version = versions[-1]
        if version != active_version:
            return CapabilityResolution(
                kind=ResolutionKind.INACTIVE_VERSION,
                expected_kind=expected,
                actual_kind=definition.kind,
            )
        if expected is not None and definition.kind is not expected:
            return CapabilityResolution(
                kind=ResolutionKind.KIND_MISMATCH,
                expected_kind=expected,
                actual_kind=definition.kind,
            )
        return CapabilityResolution(kind=ResolutionKind.RESOLVED, definition=definition)

    def get(self, capability_id: str, version: int) -> CapabilityDefinition | None:
        """兼容 V2-0 的直接读取：按 id + version 精确返回，不改变激活判定。"""
        return self._definitions.get((capability_id, version))

    def definitions(self) -> tuple[CapabilityDefinition, ...]:
        """兼容 V2-0 的注册审计视图：返回全部已注册版本（含未激活）。"""
        return tuple(self._definitions.values())

    def active_version(self, capability_id: str) -> int | None:
        """返回某个能力的当前激活版本；未知 id 返回 None。"""
        versions = [
            version for (registered_id, version) in self._definitions if registered_id == capability_id
        ]
        return max(versions) if versions else None

    def catalog(self) -> tuple[CapabilityDefinition, ...]:
        """返回每个能力当前激活版本的稳定 catalog，按 id 排序。"""
        active: dict[str, CapabilityDefinition] = {}
        for (capability_id, version), definition in self._definitions.items():
            current = active.get(capability_id)
            if current is None or version > current.version:
                active[capability_id] = definition
        return tuple(active[key] for key in sorted(active))

    def summaries(self) -> tuple[CapabilitySummary, ...]:
        """返回模型可见的安全摘要；不暴露工具实现或资源句柄。"""
        return tuple(
            CapabilitySummary(
                capability_id=definition.capability_id,
                version=definition.version,
                kind=definition.kind,
                title=definition.title,
                description=definition.description,
                usage_guide=definition.usage_guide,
                input_slots=definition.input_contract.material_slots,
            )
            for definition in self.catalog()
        )

    def capability_ids(self) -> frozenset[str]:
        """返回全部已注册能力 id；用于公开事件白名单。"""
        return frozenset(capability_id for capability_id, _version in self._definitions)
