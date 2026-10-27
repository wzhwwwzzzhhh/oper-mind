"""受管 Skill 来源：只读、版本化、大小与摘要校验，失败不返回任何内容。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Protocol

from src.capabilities.contract import SkillDeclaration


class SkillUnavailableReason(StrEnum):
    """Skill 不可用的封闭原因；不携带路径或内容。"""

    MISSING = "missing"
    TOO_LARGE = "too_large"
    DIGEST_MISMATCH = "digest_mismatch"
    VERSION_MISMATCH = "version_mismatch"
    INVALID = "invalid"


class SkillUnavailableError(Exception):
    """受管 Skill 缺失、损坏或超限；调用方只能降级，不得伪造内容。"""

    def __init__(self, reason: SkillUnavailableReason) -> None:
        super().__init__("受管 Skill 不可用。")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ManagedSkill:
    """已通过版本、大小与摘要校验的知识内容。"""

    skill_id: str
    skill_version: int
    title: str
    content: str
    content_sha256: str

    @property
    def codepoints(self) -> int:
        return len(self.content)


class SkillSource(Protocol):
    """按声明加载受管 Skill；实现不得访问网络或用户数据。"""

    def load(self, declaration: SkillDeclaration) -> ManagedSkill:
        """返回校验通过的 Skill；任何异常收敛为 SkillUnavailableError。"""


class BuiltinSkillSource:
    """仓库内置 Skill 来源：内容由调用方注入，加载时逐项校验。"""

    def __init__(self, loader: Callable[[SkillDeclaration], str]) -> None:
        self._loader = loader

    def load(self, declaration: SkillDeclaration) -> ManagedSkill:
        if declaration.source != "builtin":
            raise SkillUnavailableError(SkillUnavailableReason.VERSION_MISMATCH)
        try:
            content = self._loader(declaration)
        except FileNotFoundError:
            raise SkillUnavailableError(SkillUnavailableReason.MISSING) from None
        except (OSError, UnicodeError):
            raise SkillUnavailableError(SkillUnavailableReason.INVALID) from None
        if not isinstance(content, str) or not content:
            raise SkillUnavailableError(SkillUnavailableReason.INVALID)
        if len(content) > declaration.max_codepoints:
            raise SkillUnavailableError(SkillUnavailableReason.TOO_LARGE)
        digest = sha256(content.encode("utf-8")).hexdigest()
        if digest != declaration.expected_sha256:
            raise SkillUnavailableError(SkillUnavailableReason.DIGEST_MISMATCH)
        return ManagedSkill(
            skill_id=declaration.skill_id,
            skill_version=declaration.skill_version,
            title=declaration.title,
            content=content,
            content_sha256=digest,
        )
