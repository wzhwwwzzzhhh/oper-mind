"""能力声明、受管 Skill 与显式注册表的公开出口。"""

from __future__ import annotations

from typing import Literal

from src.capabilities.contract import (
    CAPABILITY_ID_PATTERN,
    MATERIAL_SLOT_PATTERN,
    CapabilityDefinition,
    CapabilityInputContract,
    CapabilityKind,
    CapabilityOutputContract,
    CapabilityResolution,
    CapabilitySummary,
    CompletionSemantics,
    FailureSemantics,
    MaterialSlot,
    ResolutionKind,
    ResourceDeclaration,
    SkillDeclaration,
)
from src.capabilities.registry import CapabilityRegistry
from src.capabilities.skill_source import (
    BuiltinSkillSource,
    ManagedSkill,
    SkillSource,
    SkillUnavailableError,
    SkillUnavailableReason,
)

MaterialSide = Literal["text_a", "text_b"]

__all__ = [
    "CAPABILITY_ID_PATTERN",
    "MATERIAL_SLOT_PATTERN",
    "BuiltinSkillSource",
    "CapabilityDefinition",
    "CapabilityInputContract",
    "CapabilityKind",
    "CapabilityOutputContract",
    "CapabilityRegistry",
    "CapabilityResolution",
    "CapabilitySummary",
    "CompletionSemantics",
    "FailureSemantics",
    "ManagedSkill",
    "MaterialSide",
    "MaterialSlot",
    "ResolutionKind",
    "ResourceDeclaration",
    "SkillDeclaration",
    "SkillSource",
    "SkillUnavailableError",
    "SkillUnavailableReason",
]
