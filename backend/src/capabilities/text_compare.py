"""文本字面对照能力：规则、能力声明与确定性结果计算。

首版只有 `text.literal_compare@1`：按完整行列表做序列匹配，
`autojunk=False`，不识别 move，不做语义归一。模型不得提交权威原文，
Tool 只接收本 Run 的材料引用并从注入映射取内容。
"""

from __future__ import annotations

import difflib
from uuid import UUID

from src.capabilities import (
    CapabilityDefinition,
    CapabilityInputContract,
    CapabilityKind,
    CapabilityOutputContract,
    CompletionSemantics,
    FailureSemantics,
    MaterialSide,
    MaterialSlot,
)
from src.domain.main_agent import (
    MAIN_AGENT_CAPABILITY_ID,
    MAIN_AGENT_CAPABILITY_VERSION,
    MAIN_AGENT_RULE_VERSION,
    MAX_DIFF_BLOCKS,
    MainMaterialSnapshotV1,
    TextComparisonV1,
    TextDiffBlockV1,
)

TEXT_COMPARE_TOOL_NAME = "text_literal_compare"
TEXT_COMPARE_REQUIRED_MATERIALS: tuple[MaterialSide, ...] = ("text_a", "text_b")

TEXT_COMPARE_CAPABILITY = CapabilityDefinition(
    capability_id=MAIN_AGENT_CAPABILITY_ID,
    version=MAIN_AGENT_CAPABILITY_VERSION,
    kind=CapabilityKind.EXECUTION,
    title="文本字面比较",
    description="对两份文本做逐行字面对照，返回新增、删除、修改块及精确行号与引文。",
    usage_guide=(
        "当用户要求比较文本 A（旧）与文本 B（新）时，提出该能力引用；"
        "不要自行编造差异，也不要试图改写或省略行。"
    ),
    instruction="调用声明的文本比较工具，返回确定性 typed 结果；不要自行生成差异块。",
    input_contract=CapabilityInputContract(
        material_slots=(
            MaterialSlot(slot="text_a", label="文本 A（旧）"),
            MaterialSlot(slot="text_b", label="文本 B（新）"),
        )
    ),
    output_contract=CapabilityOutputContract(
        delivery_kind="comparison",
        result_schema="text_comparison.v1",
        summary_fields=("status", "blocks"),
    ),
    resources=(),
    permissions=("read_only",),
    tool_bindings=(TEXT_COMPARE_TOOL_NAME,),
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


class TextComparisonRuleError(Exception):
    """比较规则无法产出合法结果；调用方只能安全失败。"""


class TextComparisonLimitError(TextComparisonRuleError):
    """差异块超过上限；不截断成成功。"""


def compare_materials(
    *,
    run_id: UUID,
    text_a: MainMaterialSnapshotV1,
    text_b: MainMaterialSnapshotV1,
) -> TextComparisonV1:
    """按 `literal-lines@1` 计算完整 typed 比较结果。"""
    a_lines = _material_lines(text_a)
    b_lines = _material_lines(text_b)
    matcher = difflib.SequenceMatcher(a=a_lines, b=b_lines, autojunk=False)
    blocks: list[TextDiffBlockV1] = []
    for tag, a_start, a_end, b_start, b_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        blocks.append(_block(tag, a_lines, b_lines, a_start, a_end, b_start, b_end))
        if len(blocks) > MAX_DIFF_BLOCKS:
            raise TextComparisonLimitError("差异块超过上限。")
    return TextComparisonV1(
        schema_version=1,
        run_id=run_id,
        a_material_id=text_a.material_id,
        b_material_id=text_b.material_id,
        capability_id=MAIN_AGENT_CAPABILITY_ID,
        capability_version=MAIN_AGENT_CAPABILITY_VERSION,
        rule_version=MAIN_AGENT_RULE_VERSION,
        status="has_difference" if blocks else "no_difference",
        blocks=tuple(blocks),
    )


def _material_lines(material: MainMaterialSnapshotV1) -> list[str]:
    """空文本是 0 行；其他文本按 LF 分割并保留末尾空行。"""
    return material.normalized_text.split("\n") if material.normalized_text else []


def _block(
    tag: str,
    a_lines: list[str],
    b_lines: list[str],
    a_start: int,
    a_end: int,
    b_start: int,
    b_end: int,
) -> TextDiffBlockV1:
    """把一个非 equal opcode 转成带 1 基行号与精确引文的差异块。"""
    if tag == "insert":
        return TextDiffBlockV1(
            kind="added",
            b_start=b_start + 1,
            b_end=b_end,
            b_lines=tuple(b_lines[b_start:b_end]),
            b_quote="\n".join(b_lines[b_start:b_end]),
        )
    if tag == "delete":
        return TextDiffBlockV1(
            kind="deleted",
            a_start=a_start + 1,
            a_end=a_end,
            a_lines=tuple(a_lines[a_start:a_end]),
            a_quote="\n".join(a_lines[a_start:a_end]),
        )
    if tag == "replace":
        return TextDiffBlockV1(
            kind="modified",
            a_start=a_start + 1,
            a_end=a_end,
            a_lines=tuple(a_lines[a_start:a_end]),
            a_quote="\n".join(a_lines[a_start:a_end]),
            b_start=b_start + 1,
            b_end=b_end,
            b_lines=tuple(b_lines[b_start:b_end]),
            b_quote="\n".join(b_lines[b_start:b_end]),
        )
    raise TextComparisonRuleError("未知的行匹配操作。")
