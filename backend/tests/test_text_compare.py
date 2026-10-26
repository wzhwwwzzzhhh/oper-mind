"""`text.literal_compare@1` 的确定性规则、能力声明与 Tool 引用校验。"""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.capabilities import CapabilityRegistry
from src.capabilities.text_compare import (
    TEXT_COMPARE_CAPABILITY,
    TEXT_COMPARE_TOOL_NAME,
    TextComparisonLimitError,
    compare_materials,
)
from src.domain.main_agent import (
    MAIN_AGENT_RULE_VERSION,
    MainMaterialSnapshotV1,
    TextComparisonV1,
    material_digest,
    normalize_material_text,
)
from src.tools.text_compare import TextCompareTool


def _material(text: str) -> MainMaterialSnapshotV1:
    normalized = normalize_material_text(text)
    return MainMaterialSnapshotV1(
        material_id=uuid4(),
        original_text=text,
        normalized_text=normalized,
        content_sha256=material_digest(normalized),
    )


def _compare(text_a: str, text_b: str):
    return compare_materials(
        run_id=uuid4(),
        text_a=_material(text_a),
        text_b=_material(text_b),
    )


def _alternating_lines(count: int, side: str) -> str:
    parts: list[str] = []
    for index in range(count):
        parts.append(f"{side}{index}")
        if index != count - 1:
            parts.append(f"same{index}")
    return "\n".join(parts)


def _unvalidated_material(text: str) -> MainMaterialSnapshotV1:
    """绕过输入边界构造超限材料，只用于验证规则内部上限仍会失败关闭。"""
    return MainMaterialSnapshotV1.model_construct(
        material_id=uuid4(),
        original_text=text,
        normalized_text=text,
        content_sha256="0" * 64,
    )


def test_capability_declaration_is_explicit_and_not_scanned() -> None:
    registry = CapabilityRegistry([TEXT_COMPARE_CAPABILITY])
    assert TEXT_COMPARE_CAPABILITY.capability_id == "text.literal_compare"
    assert TEXT_COMPARE_CAPABILITY.version == 1
    assert TEXT_COMPARE_CAPABILITY.rule_version == MAIN_AGENT_RULE_VERSION
    assert TEXT_COMPARE_CAPABILITY.allowed_tools == (TEXT_COMPARE_TOOL_NAME,)
    assert TEXT_COMPARE_CAPABILITY.required_materials == ("text_a", "text_b")
    assert registry.get("text.literal_compare", 1) is TEXT_COMPARE_CAPABILITY
    assert registry.get("text.literal_compare", 2) is None
    assert registry.definitions() == (TEXT_COMPARE_CAPABILITY,)
    with pytest.raises(ValueError):
        registry.register(TEXT_COMPARE_CAPABILITY)


def test_identical_and_explicit_empty_texts_have_no_difference() -> None:
    assert _compare("相同\n文本", "相同\n文本").status == "no_difference"
    empty = _compare("", "")
    assert empty.status == "no_difference"
    assert empty.blocks == ()


def test_empty_versus_non_empty_is_a_single_added_block() -> None:
    comparison = _compare("", "新行")
    assert comparison.status == "has_difference"
    assert len(comparison.blocks) == 1
    block = comparison.blocks[0]
    assert block.kind == "added"
    assert (block.a_start, block.a_end, block.a_lines, block.a_quote) == (None, None, None, None)
    assert (block.b_start, block.b_end) == (1, 1)
    assert block.b_lines == ("新行",)
    assert block.b_quote == "新行"


def test_added_lines_keep_one_based_ranges_and_exact_quotes() -> None:
    comparison = _compare("a\nc", "a\nb\nc")
    assert comparison.status == "has_difference"
    assert [block.kind for block in comparison.blocks] == ["added"]
    block = comparison.blocks[0]
    assert (block.b_start, block.b_end) == (2, 2)
    assert block.b_lines == ("b",)
    assert block.b_quote == "b"


def test_deleted_lines_keep_one_based_ranges_and_exact_quotes() -> None:
    comparison = _compare("a\nb\nc", "a\nc")
    assert [block.kind for block in comparison.blocks] == ["deleted"]
    block = comparison.blocks[0]
    assert (block.a_start, block.a_end) == (2, 2)
    assert block.a_lines == ("b",)
    assert block.a_quote == "b"


def test_modified_block_carries_both_sides() -> None:
    comparison = _compare("旧行\n共同", "新行\n共同")
    assert comparison.status == "has_difference"
    assert len(comparison.blocks) == 1
    block = comparison.blocks[0]
    assert block.kind == "modified"
    assert (block.a_start, block.a_end, block.a_lines, block.a_quote) == (1, 1, ("旧行",), "旧行")
    assert (block.b_start, block.b_end, block.b_lines, block.b_quote) == (1, 1, ("新行",), "新行")


def test_trailing_newline_preserves_an_empty_last_line() -> None:
    comparison = _compare("a\n", "a")
    assert [block.kind for block in comparison.blocks] == ["deleted"]
    block = comparison.blocks[0]
    assert (block.a_start, block.a_end) == (2, 2)
    assert block.a_lines == ("",)
    assert block.a_quote == ""


def test_only_newline_encoding_is_normalized_not_case_space_or_punctuation() -> None:
    assert _compare("A b,\r\nC", "A b,\nC").status == "no_difference"
    comparison = _compare("A b.", "a b,")
    assert [block.kind for block in comparison.blocks] == ["modified"]
    assert comparison.blocks[0].a_lines == ("A b.",)
    assert comparison.blocks[0].b_lines == ("a b,",)


def test_duplicate_lines_match_deterministically() -> None:
    first = _compare("x\nx", "x")
    second = _compare("x\nx", "x")
    assert [(block.kind, block.a_start, block.a_end) for block in first.blocks] == [("deleted", 2, 2)]
    assert first.blocks == second.blocks


def test_exactly_fifty_blocks_is_accepted() -> None:
    comparison = _compare(_alternating_lines(50, "old"), _alternating_lines(50, "new"))
    assert comparison.status == "has_difference"
    assert len(comparison.blocks) == 50
    assert [block.kind for block in comparison.blocks] == ["modified"] * 50
    assert comparison.blocks[0].a_start == 1
    assert comparison.blocks[-1].a_start == 99


def test_more_than_fifty_blocks_fails_closed_instead_of_truncating() -> None:
    text_a = _unvalidated_material(_alternating_lines(51, "old"))
    text_b = _unvalidated_material(_alternating_lines(51, "new"))
    with pytest.raises(TextComparisonLimitError):
        compare_materials(run_id=uuid4(), text_a=text_a, text_b=text_b)


def _tool(text_a: str = "旧行", text_b: str = "新行") -> tuple[TextCompareTool, MainMaterialSnapshotV1, MainMaterialSnapshotV1]:
    material_a = _material(text_a)
    material_b = _material(text_b)
    tool = TextCompareTool(
        run_id=uuid4(),
        materials={material_a.material_id: material_a, material_b.material_id: material_b},
    )
    return tool, material_a, material_b


def test_tool_returns_typed_comparison_for_own_material_refs() -> None:
    tool, material_a, material_b = _tool()
    result = tool.execute(
        a_material_id=str(material_a.material_id),
        b_material_id=str(material_b.material_id),
        rule_version=MAIN_AGENT_RULE_VERSION,
    )
    assert result.status == "ok"
    assert result.summary == "文本比较完成：1 个差异块"
    comparison = TextComparisonV1.model_validate_json(result.output)
    assert comparison.a_material_id == material_a.material_id
    assert comparison.b_material_id == material_b.material_id
    assert comparison.blocks[0].a_quote == "旧行"


def test_tool_rejects_unknown_rule_version() -> None:
    tool, material_a, material_b = _tool()
    result = tool.execute(
        a_material_id=str(material_a.material_id),
        b_material_id=str(material_b.material_id),
        rule_version="literal-lines@2",
    )
    assert result.status == "unavailable"
    assert "规则版本" in result.summary


def test_tool_rejects_cross_run_or_unknown_material_refs() -> None:
    tool, material_a, _ = _tool()
    unknown = uuid4()
    for a_ref, b_ref in ((unknown, unknown), (material_a.material_id, unknown)):
        result = tool.execute(
            a_material_id=str(a_ref),
            b_material_id=str(b_ref),
            rule_version=MAIN_AGENT_RULE_VERSION,
        )
        assert result.status == "unavailable"
        assert "材料引用" in result.summary


def test_tool_rejects_same_material_on_both_sides() -> None:
    material = _material("同一段文本")
    tool = TextCompareTool(run_id=uuid4(), materials={material.material_id: material})
    result = tool.execute(
        a_material_id=str(material.material_id),
        b_material_id=str(material.material_id),
        rule_version=MAIN_AGENT_RULE_VERSION,
    )
    assert result.status == "unavailable"
    assert "材料引用" in result.summary


def test_tool_reports_block_limit_without_partial_output() -> None:
    material_a = _unvalidated_material(_alternating_lines(51, "old"))
    material_b = _unvalidated_material(_alternating_lines(51, "new"))
    tool = TextCompareTool(
        run_id=uuid4(),
        materials={material_a.material_id: material_a, material_b.material_id: material_b},
    )
    result = tool.execute(
        a_material_id=str(material_a.material_id),
        b_material_id=str(material_b.material_id),
        rule_version=MAIN_AGENT_RULE_VERSION,
    )
    assert result.status == "unavailable"
    assert "上限" in result.summary
