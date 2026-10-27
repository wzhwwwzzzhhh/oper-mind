"""内置只读排查手册能力：受管静态 Skill，不读取实时数据。"""

from __future__ import annotations

from importlib.resources import files

from src.capabilities.contract import (
    CapabilityDefinition,
    CapabilityInputContract,
    CapabilityKind,
    CapabilityOutputContract,
    CompletionSemantics,
    FailureSemantics,
    SkillDeclaration,
)
from src.capabilities.skill_source import BuiltinSkillSource
from src.domain.main_agent import MAX_SKILL_CODEPOINTS

READONLY_PLAYBOOK_CAPABILITY_ID = "ops.readonly_playbook"
READONLY_PLAYBOOK_SKILL_ID = "ops.readonly_playbook"
READONLY_PLAYBOOK_SKILL_VERSION = 1
READONLY_PLAYBOOK_SHA256 = "3fb07a93ada1dbac327efe23cc0e8808373b65a4a584976815288b4488e34b8c"

READONLY_PLAYBOOK_SKILL = SkillDeclaration(
    source="builtin",
    skill_id=READONLY_PLAYBOOK_SKILL_ID,
    skill_version=READONLY_PLAYBOOK_SKILL_VERSION,
    title="只读排查手册",
    expected_sha256=READONLY_PLAYBOOK_SHA256,
    max_codepoints=MAX_SKILL_CODEPOINTS,
)

READONLY_PLAYBOOK_CAPABILITY = CapabilityDefinition(
    capability_id=READONLY_PLAYBOOK_CAPABILITY_ID,
    version=1,
    kind=CapabilityKind.KNOWLEDGE,
    title="只读排查手册",
    description="提供慢查询、锁等待、连接池、服务健康与日志错误的只读排查步骤。",
    usage_guide=(
        "当用户询问如何排查问题、需要通用排查思路，且没有要求读取实时指标或日志时使用。"
        "给出步骤时必须说明这是内置知识，未读取当前环境的数据。"
    ),
    instruction=(
        "基于装入的内置只读排查手册组织回答。只给只读、可回退的排查步骤；"
        "不得声称读取了实时指标、日志、SQL 结果或服务状态；涉及写操作或权限变更时建议人工升级。"
    ),
    input_contract=CapabilityInputContract(),
    output_contract=CapabilityOutputContract(),
    resources=(),
    permissions=(),
    tool_bindings=(),
    completion=CompletionSemantics.RESPONSE,
    failure=(
        FailureSemantics.INPUT_MISSING,
        FailureSemantics.SOURCE_UNAVAILABLE,
        FailureSemantics.SOURCE_INVALID,
    ),
    skill=READONLY_PLAYBOOK_SKILL,
    rule_version=None,
)


def _read_playbook(_declaration: SkillDeclaration) -> str:
    """从仓库内置资源读取手册；失败由 SkillSource 收敛为不可用。"""
    return files("src.capabilities.playbook").joinpath("readonly_playbook.md").read_text(encoding="utf-8")


READONLY_PLAYBOOK_SOURCE = BuiltinSkillSource(_read_playbook)
