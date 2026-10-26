"""V2 主 Agent 的封闭输入、冻结快照与 typed 交付契约。"""

from __future__ import annotations

from hashlib import sha256
from typing import Annotated, Literal, Self, TypeAlias
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator, model_validator

from src.domain.records import DomainRecord

MAIN_AGENT_RULE_VERSION: Literal["literal-lines@1"] = "literal-lines@1"
MAIN_AGENT_CAPABILITY_ID: Literal["text.literal_compare"] = "text.literal_compare"
MAIN_AGENT_CAPABILITY_VERSION: Literal[1] = 1
MAX_MAIN_QUERY_CODEPOINTS = 200
MAX_MATERIAL_CODEPOINTS = 2_000
MAX_MATERIAL_LINES = 100
MAX_DIFF_BLOCKS = 50
MAX_CONTEXT_MESSAGES = 4
MAX_CONTEXT_CODEPOINTS = 2_000
MAX_ANSWER_CODEPOINTS = 4_000
MAX_PROMPT_CODEPOINTS = 1_000


def _require_scalar_text(value: str, field_name: str) -> None:
    """拒绝 UTF-8 无法编码的孤立代理码点；错误不携带原文。"""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError(f"{field_name} 包含非法 Unicode 码点。") from None


def normalize_material_text(value: str) -> str:
    """仅统一换行编码，不做 trim、大小写或标点归一。"""
    return value.replace("\r\n", "\n").replace("\r", "\n")


def material_line_count(normalized_text: str) -> int:
    """按 LF 计算行数；空字符串是 0 行，末尾换行保留一个空行。"""
    return 0 if normalized_text == "" else normalized_text.count("\n") + 1


def material_digest(normalized_text: str) -> str:
    """计算规范化文本的稳定内容摘要。"""
    return sha256(normalized_text.encode("utf-8")).hexdigest()


def validate_material_text(value: str, field_name: str = "文本") -> str:
    """校验原始材料并返回仅统一换行后的文本。"""
    _require_scalar_text(value, field_name)
    if len(value) > MAX_MATERIAL_CODEPOINTS:
        raise ValueError(f"{field_name} 超过 {MAX_MATERIAL_CODEPOINTS} 码点上限。")
    normalized = normalize_material_text(value)
    if material_line_count(normalized) > MAX_MATERIAL_LINES:
        raise ValueError(f"{field_name} 超过 {MAX_MATERIAL_LINES} 行上限。")
    return normalized


def _validate_query(value: str) -> str:
    """校验目标 query：非空白且不超过 200 码点。"""
    _require_scalar_text(value, "query")
    if not value.strip():
        raise ValueError("query 不能为空。")
    if len(value) > MAX_MAIN_QUERY_CODEPOINTS:
        raise ValueError(f"query 超过 {MAX_MAIN_QUERY_CODEPOINTS} 码点上限。")
    return value


class MainInputV1(DomainRecord):
    """对外受理边界的 MainAgent 输入；缺失与显式空文本必须可区分。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    query: str
    text_a: str | None = None
    text_b: str | None = None

    @field_validator("query")
    @classmethod
    def _check_query(cls, value: str) -> str:
        return _validate_query(value)

    @field_validator("text_a", "text_b")
    @classmethod
    def _check_material(cls, value: str | None) -> str | None:
        if value is None:
            return None
        validate_material_text(value)
        return value


class MainMaterialSnapshotV1(DomainRecord):
    """服务端生成的单侧材料快照；读取时重算摘要防止损坏或篡改。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    material_id: UUID
    original_text: str
    normalized_text: str
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_material(self) -> Self:
        normalized = validate_material_text(self.original_text)
        if normalized != self.normalized_text:
            raise ValueError("材料快照的规范化文本不一致。")
        if material_digest(normalized) != self.content_sha256:
            raise ValueError("材料快照的内容摘要不一致。")
        return self


class MainContextMessageV1(DomainRecord):
    """受理时冻结的一条必要对话上下文。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    message_id: UUID
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_CONTEXT_CODEPOINTS)

    @field_validator("content")
    @classmethod
    def _check_content(cls, value: str) -> str:
        _require_scalar_text(value, "上下文消息")
        return value


class MainInputSnapshotV1(DomainRecord):
    """受理事务内冻结的 MainAgent 输入；受理后不可覆盖。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    query: str
    text_a: MainMaterialSnapshotV1 | None = None
    text_b: MainMaterialSnapshotV1 | None = None
    rule_version: Literal["literal-lines@1"]
    context: tuple[MainContextMessageV1, ...] = ()

    @field_validator("schema_version", mode="before")
    @classmethod
    def _exact_schema_version(cls, value: object) -> object:
        if type(value) is not int or value != 1:
            raise ValueError("不支持的 MainAgent 输入 schema 版本。")
        return value

    @field_validator("query")
    @classmethod
    def _check_query(cls, value: str) -> str:
        return _validate_query(value)

    @model_validator(mode="after")
    def _validate_snapshot(self) -> Self:
        if (
            self.text_a is not None
            and self.text_b is not None
            and self.text_a.material_id == self.text_b.material_id
        ):
            raise ValueError("A／B 材料 ID 必须互不相同。")
        if len(self.context) > MAX_CONTEXT_MESSAGES:
            raise ValueError(f"上下文最多 {MAX_CONTEXT_MESSAGES} 条消息。")
        total = sum(len(item.content) for item in self.context)
        if total > MAX_CONTEXT_CODEPOINTS:
            raise ValueError(f"上下文合计不超过 {MAX_CONTEXT_CODEPOINTS} 码点。")
        return self


class MainAnswerDeliveryV1(DomainRecord):
    """普通回答：是用户可见正文，但不是已校验的文本比较。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    kind: Literal["answer"] = "answer"
    text: str = Field(min_length=1, max_length=MAX_ANSWER_CODEPOINTS)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _exact_schema_version(cls, value: object) -> object:
        if type(value) is not int or value != 1:
            raise ValueError("不支持的交付 schema 版本。")
        return value

    @field_validator("text")
    @classmethod
    def _check_text(cls, value: str) -> str:
        _require_scalar_text(value, "回答")
        return value


class MainNeedsInputDeliveryV1(DomainRecord):
    """材料追问：缺失集合必须由快照对照得出。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    kind: Literal["needs_input"] = "needs_input"
    missing: tuple[Literal["text_a", "text_b"], ...] = Field(min_length=1, max_length=2)
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CODEPOINTS)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _exact_schema_version(cls, value: object) -> object:
        if type(value) is not int or value != 1:
            raise ValueError("不支持的交付 schema 版本。")
        return value

    @field_validator("prompt")
    @classmethod
    def _check_prompt(cls, value: str) -> str:
        _require_scalar_text(value, "追问")
        return value

    @model_validator(mode="after")
    def _unique_missing(self) -> Self:
        if len(set(self.missing)) != len(self.missing):
            raise ValueError("缺失材料不允许重复。")
        return self


class TextDiffBlockV1(DomainRecord):
    """一个连续差异块；行号为 1 基闭区间，引文精确等于对应行。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["added", "deleted", "modified"]
    a_start: int | None = Field(default=None, ge=1)
    a_end: int | None = Field(default=None, ge=1)
    b_start: int | None = Field(default=None, ge=1)
    b_end: int | None = Field(default=None, ge=1)
    a_lines: tuple[str, ...] | None = None
    b_lines: tuple[str, ...] | None = None
    a_quote: str | None = None
    b_quote: str | None = None

    @model_validator(mode="after")
    def _validate_sides(self) -> Self:
        _validate_block_side(
            "a",
            present=self.kind in {"deleted", "modified"},
            start=self.a_start,
            end=self.a_end,
            lines=self.a_lines,
            quote=self.a_quote,
        )
        _validate_block_side(
            "b",
            present=self.kind in {"added", "modified"},
            start=self.b_start,
            end=self.b_end,
            lines=self.b_lines,
            quote=self.b_quote,
        )
        return self


def _validate_block_side(
    side: str,
    *,
    present: bool,
    start: int | None,
    end: int | None,
    lines: tuple[str, ...] | None,
    quote: str | None,
) -> None:
    """校验单侧行号、行数组与 LF 拼接引文完全一致。"""
    values = (start, end, lines, quote)
    if not present:
        if any(value is not None for value in values):
            raise ValueError(f"差异块 {side} 侧不应有内容。")
        return
    if start is None or end is None or lines is None or quote is None:
        raise ValueError(f"差异块 {side} 侧缺少行号、行或引文。")
    if end < start:
        raise ValueError(f"差异块 {side} 侧行号区间无效。")
    if len(lines) != end - start + 1:
        raise ValueError(f"差异块 {side} 侧行数与行号区间不一致。")
    for line in lines:
        if "\n" in line or "\r" in line:
            raise ValueError(f"差异块 {side} 侧单行不得包含换行。")
    if "\n".join(lines) != quote:
        raise ValueError(f"差异块 {side} 侧引文与行内容不一致。")


class TextComparisonV1(DomainRecord):
    """text.literal_compare@1 的 typed 结果；完整重算由执行层负责。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    run_id: UUID
    a_material_id: UUID
    b_material_id: UUID
    capability_id: Literal["text.literal_compare"]
    capability_version: Literal[1]
    rule_version: Literal["literal-lines@1"]
    status: Literal["no_difference", "has_difference"]
    blocks: tuple[TextDiffBlockV1, ...] = Field(default=(), max_length=MAX_DIFF_BLOCKS)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _exact_schema_version(cls, value: object) -> object:
        if type(value) is not int or value != 1:
            raise ValueError("不支持的文本比较 schema 版本。")
        return value

    @model_validator(mode="after")
    def _validate_comparison(self) -> Self:
        if self.a_material_id == self.b_material_id:
            raise ValueError("A／B 材料 ID 必须互不相同。")
        if self.status == "no_difference" and self.blocks:
            raise ValueError("无差异结果不得携带差异块。")
        if self.status == "has_difference" and not self.blocks:
            raise ValueError("有差异结果必须携带差异块。")
        _validate_block_order(self.blocks, "a")
        _validate_block_order(self.blocks, "b")
        return self


def _validate_block_order(blocks: tuple[TextDiffBlockV1, ...], side: str) -> None:
    """同一侧的行号区间必须严格递增且互不重叠。"""
    previous_end = 0
    for block in blocks:
        start = getattr(block, f"{side}_start")
        end = getattr(block, f"{side}_end")
        if start is None or end is None:
            continue
        if start <= previous_end:
            raise ValueError(f"差异块 {side} 侧行号必须递增且不重叠。")
        previous_end = end


class MainComparisonDeliveryV1(DomainRecord):
    """已校验文本比较交付。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    kind: Literal["comparison"] = "comparison"
    comparison: TextComparisonV1

    @field_validator("schema_version", mode="before")
    @classmethod
    def _exact_schema_version(cls, value: object) -> object:
        if type(value) is not int or value != 1:
            raise ValueError("不支持的交付 schema 版本。")
        return value


MainDeliveryV1: TypeAlias = Annotated[
    MainAnswerDeliveryV1 | MainNeedsInputDeliveryV1 | MainComparisonDeliveryV1,
    Field(discriminator="kind"),
]


class MainAgentInputUnavailableError(Exception):
    """冻结输入缺失、损坏或版本未知；调用方只能安全失败。"""


class MainAgentDeliveryUnavailableError(Exception):
    """交付缺失、损坏或版本未知；调用方只能安全失败。"""


def main_delivery_message(delivery: MainAnswerDeliveryV1 | MainNeedsInputDeliveryV1 | MainComparisonDeliveryV1) -> str:
    """生成助手消息：比较结果只保留固定块数摘要，不复制引文。"""
    if isinstance(delivery, MainAnswerDeliveryV1):
        return delivery.text
    if isinstance(delivery, MainNeedsInputDeliveryV1):
        return delivery.prompt
    count = len(delivery.comparison.blocks)
    if count == 0:
        return "文本比较完成：未发现差异。"
    return f"文本比较完成：共 {count} 个差异块。"
