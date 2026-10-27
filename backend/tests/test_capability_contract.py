"""V2-1 能力契约 v1：声明约束、版本激活与显式注册表解析。"""

from __future__ import annotations

import re
from hashlib import sha256

import pytest

from src.capabilities import (
    CapabilityDefinition,
    CapabilityInputContract,
    CapabilityKind,
    CapabilityOutputContract,
    CapabilityRegistry,
    CompletionSemantics,
    FailureSemantics,
    MaterialSlot,
    ResolutionKind,
    ResourceDeclaration,
    SkillDeclaration,
    SkillUnavailableError,
    SkillUnavailableReason,
)
from src.capabilities.skill_source import BuiltinSkillSource
from src.capabilities.text_compare import (
    TEXT_COMPARE_CAPABILITY,
    TEXT_COMPARE_TOOL_NAME,
)
from src.domain.main_agent import MAIN_AGENT_RULE_VERSION

_SHA256 = "0" * 64


def _slot(slot: str, label: str | None = None) -> MaterialSlot:
    return MaterialSlot(slot=slot, label=label or f"材料 {slot}")


def _skill(
    *,
    skill_id: str = "ops.readonly_playbook",
    version: int = 1,
    max_codepoints: int = 4000,
    digest: str = _SHA256,
) -> SkillDeclaration:
    return SkillDeclaration(
        source="builtin",
        skill_id=skill_id,
        skill_version=version,
        title="只读排查手册",
        max_codepoints=max_codepoints,
        expected_sha256=digest,
    )


def _knowledge(
    *,
    capability_id: str = "ops.readonly_playbook",
    version: int = 1,
    skill: SkillDeclaration | None = None,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id=capability_id,
        version=version,
        kind="knowledge",
        title="只读排查手册",
        description="提供只读排查步骤，不读取实时数据。",
        usage_guide="当用户询问排查方法且未要求读取实时数据时使用。",
        instruction="基于手册给出可执行步骤，并说明未读取实时数据。",
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
        skill=skill or _skill(),
    )


def _execution(
    *,
    capability_id: str = "demo.echo",
    version: int = 1,
    tool_bindings: tuple[str, ...] = ("demo_echo",),
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id=capability_id,
        version=version,
        kind="execution",
        title="演示执行能力",
        description="经 ToolGateway 执行确定性演示工具。",
        usage_guide="当需要确定性演示结果时使用。",
        instruction="调用声明的工具并返回 typed 结果。",
        input_contract=CapabilityInputContract(
            material_slots=(_slot("text_a", "文本 A（旧）"), _slot("text_b", "文本 B（新）")),
        ),
        output_contract=CapabilityOutputContract(
            delivery_kind="comparison",
            result_schema="text_comparison.v1",
            summary_fields=("status", "blocks"),
        ),
        resources=(ResourceDeclaration(resource="run.material_snapshot"),),
        permissions=("read_only",),
        tool_bindings=tool_bindings,
        completion=CompletionSemantics.TYPED_RESULT,
        failure=(
            FailureSemantics.INPUT_MISSING,
            FailureSemantics.INPUT_INVALID,
            FailureSemantics.TOOL_UNAVAILABLE,
            FailureSemantics.TOOL_TIMEOUT,
            FailureSemantics.RESULT_INVALID,
            FailureSemantics.BUDGET_EXHAUSTED,
        ),
        skill=None,
        rule_version=MAIN_AGENT_RULE_VERSION,
    )


def test_declaration_keeps_knowledge_and_execution_boundaries() -> None:
    knowledge = _knowledge()
    assert knowledge.kind is CapabilityKind.KNOWLEDGE
    assert knowledge.permissions == ()
    assert knowledge.tool_bindings == ()
    assert knowledge.output_contract.delivery_kind is None
    assert knowledge.completion is CompletionSemantics.RESPONSE
    assert knowledge.skill is not None and knowledge.skill.source == "builtin"

    execution = _execution()
    assert execution.kind is CapabilityKind.EXECUTION
    assert execution.permissions == ("read_only",)
    assert execution.output_contract.delivery_kind == "comparison"
    assert execution.completion is CompletionSemantics.TYPED_RESULT
    assert execution.resources == (ResourceDeclaration(resource="run.material_snapshot"),)


@pytest.mark.parametrize(
    "capability_id",
    ["Text.Compare", "text", "text..compare", "1text.compare", "text.Compare", "text.compare-1"],
)
def test_capability_id_must_be_namespaced_lowercase(capability_id: str) -> None:
    with pytest.raises(ValueError):
        _execution(capability_id=capability_id)


def test_capability_id_has_a_hard_length_limit() -> None:
    assert len("a." + "b" * 62) <= 64
    _execution(capability_id="a." + "b" * 62)
    with pytest.raises(ValueError):
        _execution(capability_id="a." + "b" * 63)


def test_knowledge_cannot_declare_tools_permissions_resources_or_skill_source() -> None:
    base = _knowledge()
    with pytest.raises(ValueError):
        CapabilityDefinition(**_replace(base, tool_bindings=("shell",)))
    with pytest.raises(ValueError):
        CapabilityDefinition(**_replace(base, permissions=("read_only",)))
    with pytest.raises(ValueError):
        CapabilityDefinition(**_replace(base, resources=(ResourceDeclaration(resource="network"),)))
    with pytest.raises(ValueError):
        CapabilityDefinition(**_replace(base, skill=None))
    with pytest.raises(ValueError):
        SkillDeclaration(
            source="remote",  # type: ignore[arg-type]
            skill_id="ops.readonly_playbook",
            skill_version=1,
            title="只读排查手册",
            max_codepoints=4000,
            expected_sha256=_SHA256,
        )
    with pytest.raises(ValueError):
        _skill(max_codepoints=4001)
    with pytest.raises(ValueError):
        _skill(digest="not-a-digest")


def test_execution_requires_read_only_single_permission_and_declared_tool() -> None:
    base = _execution()
    with pytest.raises(ValueError):
        CapabilityDefinition(**_replace(base, permissions=()))
    with pytest.raises(ValueError):
        CapabilityDefinition(**_replace(base, permissions=("read_only", "write")))
    with pytest.raises(ValueError):
        CapabilityDefinition(**_replace(base, tool_bindings=()))
    with pytest.raises(ValueError):
        CapabilityDefinition(**_replace(base, skill=_skill()))
    with pytest.raises(ValueError):
        CapabilityDefinition(**_replace(base, output_contract=CapabilityOutputContract()))


def test_declaration_text_limits_are_enforced() -> None:
    base = _knowledge()
    with pytest.raises(ValueError):
        CapabilityDefinition(**_replace(base, title="题" * 41))
    with pytest.raises(ValueError):
        CapabilityDefinition(**_replace(base, description="说" * 281))
    with pytest.raises(ValueError):
        CapabilityDefinition(**_replace(base, usage_guide="指" * 601))
    with pytest.raises(ValueError):
        CapabilityDefinition(**_replace(base, instruction="令" * 401))
    with pytest.raises(ValueError):
        CapabilityDefinition(**_replace(base, version=0))


def test_input_contract_rejects_duplicate_or_malformed_slots() -> None:
    with pytest.raises(ValueError):
        CapabilityInputContract(material_slots=(_slot("text_a"), _slot("text_a")))
    with pytest.raises(ValueError):
        CapabilityInputContract(material_slots=(_slot("Text A"),))
    with pytest.raises(ValueError):
        MaterialSlot(slot="text_a", label="")


def test_registry_registers_explicit_versions_and_activates_highest() -> None:
    v1 = _execution(version=1)
    v2 = _execution(version=2)
    registry = CapabilityRegistry([v1])
    assert registry.resolve("demo.echo", 1).kind is ResolutionKind.RESOLVED
    assert registry.resolve("demo.echo", 1).definition is v1
    assert registry.resolve("demo.echo", 2).kind is ResolutionKind.UNKNOWN_VERSION
    assert registry.resolve("missing.capability", 1).kind is ResolutionKind.UNKNOWN_ID

    registry.register(v2)
    assert registry.active_version("demo.echo") == 2
    assert registry.resolve("demo.echo", 1).kind is ResolutionKind.INACTIVE_VERSION
    assert registry.resolve("demo.echo", 2).definition is v2
    assert registry.catalog() == (v2,)
    # 兼容层保留全部已注册版本，便于审计与直接查找；模型只看到 catalog。
    assert registry.definitions() == (v1, v2)
    assert registry.get("demo.echo", 1) is v1
    assert registry.get("demo.echo", 3) is None
    assert registry.capability_ids() == frozenset({"demo.echo"})


def test_registry_duplicate_same_id_and_version_is_rejected() -> None:
    registry = CapabilityRegistry([_execution()])
    with pytest.raises(ValueError):
        registry.register(_execution())
    # 同 id 不同版本是合法升级，不是重复注册。
    registry.register(_execution(version=2))


def test_registry_rejects_kind_mismatch_without_leaking_definition() -> None:
    registry = CapabilityRegistry([_knowledge()])
    outcome = registry.resolve("ops.readonly_playbook", 1, expected_kind="execution")
    assert outcome.kind is ResolutionKind.KIND_MISMATCH
    assert outcome.definition is None
    assert outcome.expected_kind == "execution"
    assert outcome.actual_kind == "knowledge"
    assert registry.resolve("ops.readonly_playbook", 1, expected_kind="knowledge").resolved


def test_catalog_is_sorted_and_excludes_inactive_versions() -> None:
    registry = CapabilityRegistry(
        [
            _execution(capability_id="z.last", version=1),
            _knowledge(),
            _execution(capability_id="a.first", version=3),
            _execution(capability_id="a.first", version=1),
        ]
    )
    assert [item.capability_id for item in registry.catalog()] == [
        "a.first",
        "ops.readonly_playbook",
        "z.last",
    ]
    assert [item.version for item in registry.catalog() if item.capability_id == "a.first"] == [3]
    summaries = registry.summaries()
    assert summaries[0].capability_id == "a.first"
    assert summaries[1].kind is CapabilityKind.KNOWLEDGE
    assert summaries[1].available is True


def test_text_compare_contract_migration_keeps_compatibility_surface() -> None:
    assert TEXT_COMPARE_CAPABILITY.capability_id == "text.literal_compare"
    assert TEXT_COMPARE_CAPABILITY.version == 1
    assert TEXT_COMPARE_CAPABILITY.kind is CapabilityKind.EXECUTION
    assert TEXT_COMPARE_CAPABILITY.rule_version == MAIN_AGENT_RULE_VERSION
    assert TEXT_COMPARE_CAPABILITY.allowed_tools == (TEXT_COMPARE_TOOL_NAME,)
    assert TEXT_COMPARE_CAPABILITY.required_materials == ("text_a", "text_b")
    assert TEXT_COMPARE_CAPABILITY.output_contract.delivery_kind == "comparison"
    assert TEXT_COMPARE_CAPABILITY.skill is None
    assert re.fullmatch(
        r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$",
        TEXT_COMPARE_CAPABILITY.capability_id,
    )


def _replace(
    capability: CapabilityDefinition,
    **changes: object,
) -> dict[str, object]:
    """按 dataclass 字段整体替换，构造非法声明供边界测试。"""
    values = {field: getattr(capability, field) for field in capability.__dataclass_fields__}
    values.update(changes)
    return values


def _digest(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


def _source_with(content: str | None) -> BuiltinSkillSource:
    def loader(_declaration: SkillDeclaration) -> str:
        if content is None:
            raise FileNotFoundError("missing")
        return content

    return BuiltinSkillSource(loader)


def test_builtin_skill_source_rejects_missing_content() -> None:
    """Skill 缺失只报 MISSING，不泄漏路径或异常文本。"""
    with pytest.raises(SkillUnavailableError) as raised:
        _source_with(None).load(_skill())
    assert raised.value.reason is SkillUnavailableReason.MISSING
    assert "missing" not in str(raised.value)


def test_builtin_skill_source_rejects_oversized_content() -> None:
    declaration = _skill(max_codepoints=3, digest=_digest("1234"))
    with pytest.raises(SkillUnavailableError) as raised:
        _source_with("1234").load(declaration)
    assert raised.value.reason is SkillUnavailableReason.TOO_LARGE


def test_builtin_skill_source_rejects_digest_mismatch() -> None:
    declaration = _skill(digest=_digest("expected"))
    with pytest.raises(SkillUnavailableError) as raised:
        _source_with("tampered").load(declaration)
    assert raised.value.reason is SkillUnavailableReason.DIGEST_MISMATCH


def test_builtin_skill_source_rejects_empty_or_unreadable_content() -> None:
    with pytest.raises(SkillUnavailableError) as empty:
        _source_with("").load(_skill())
    assert empty.value.reason is SkillUnavailableReason.INVALID

    def broken(_declaration: SkillDeclaration) -> str:
        raise OSError("unreadable")

    with pytest.raises(SkillUnavailableError) as unreadable:
        BuiltinSkillSource(broken).load(_skill())
    assert unreadable.value.reason is SkillUnavailableReason.INVALID


def test_builtin_skill_source_returns_verified_managed_skill() -> None:
    content = "只读排查手册：先看连接数，再看慢查询。"
    skill = _source_with(content).load(_skill(digest=_digest(content)))
    assert skill.content == content
    assert skill.content_sha256 == _digest(content)
    assert skill.codepoints == len(content)
    assert skill.skill_id == "ops.readonly_playbook"
    assert skill.skill_version == 1
