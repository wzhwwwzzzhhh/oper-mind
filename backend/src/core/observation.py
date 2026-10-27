"""主 Agent 安全观察与能力使用摘要；不携带原文、原始工具输出或异常。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.capabilities import CapabilityKind, ManagedSkill, SkillUnavailableReason
from src.domain.main_agent import MAX_PROMPT_CODEPOINTS

ObservationStatus = Literal["loaded", "ok", "unavailable"]

_SLOT_LABELS = {
    "text_a": "文本 A（旧）",
    "text_b": "文本 B（新）",
}

_DEGRADED_REF = {
    SkillUnavailableReason.MISSING: "source_missing",
    SkillUnavailableReason.TOO_LARGE: "source_too_large",
    SkillUnavailableReason.DIGEST_MISMATCH: "source_digest_mismatch",
    SkillUnavailableReason.VERSION_MISMATCH: "version_mismatch",
    SkillUnavailableReason.INVALID: "source_invalid",
}


def degraded_ref(reason: SkillUnavailableReason) -> str:
    """把 Skill 不可用原因投影为封闭观察枚举；不回显路径或异常文本。"""
    return _DEGRADED_REF[reason]


@dataclass(frozen=True, slots=True)
class ObservationSummary:
    """一步之后提供给模型和事件的安全观察。"""

    capability_id: str
    capability_version: int
    kind: CapabilityKind
    step: int
    status: ObservationStatus
    ref: str

    def prompt_line(self) -> str:
        """按 Design §2.3 的固定格式输出；只含封闭状态与 typed 引用。"""
        return (
            f"{self.capability_id}@{self.capability_version} "
            f"step={self.step} status={self.status} ref={self.ref}"
        )


@dataclass(frozen=True, slots=True)
class LoadedSkill:
    """本 Run 已成功装入上下文的知识能力。"""

    capability_id: str
    capability_version: int
    skill: ManagedSkill
    step: int


@dataclass(frozen=True, slots=True)
class DegradedCapability:
    """本 Run 中加载失败并被降级的能力。"""

    capability_id: str
    capability_version: int
    reason: SkillUnavailableReason
    step: int


@dataclass(frozen=True, slots=True)
class CapabilityUse:
    """公开投影使用的能力身份与最终状态。"""

    capability_id: str
    capability_version: int
    kind: CapabilityKind
    status: Literal["loaded", "ok", "unavailable"]


def needs_input_prompt(slots: tuple[str, ...]) -> str:
    """由缺失槽位生成固定追问文案；不复制材料原文。"""
    labels = "和".join(_SLOT_LABELS.get(slot, slot) for slot in slots)
    return f"请提供{labels}，我会做逐行字面比较。"[:MAX_PROMPT_CODEPOINTS]
