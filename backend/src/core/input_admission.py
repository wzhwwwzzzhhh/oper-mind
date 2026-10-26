"""MainAgent 入站检测：复用 Gateway 的凭据识别范围，只返回布尔值。"""

from __future__ import annotations

from collections.abc import Iterable

from src.core.tool_gateway import contains_sensitive_content
from src.domain.main_agent import MainContextMessageV1, MainInputV1


def main_input_has_sensitive_content(value: MainInputV1) -> bool:
    """检查 query 与 A/B 原文；不返回命中片段。"""
    if contains_sensitive_content(value.query):
        return True
    return any(
        text is not None and contains_sensitive_content(text)
        for text in (value.text_a, value.text_b)
    )


def context_has_sensitive_content(context: Iterable[MainContextMessageV1]) -> bool:
    """检查待冻结上下文；命中即整次受理拒绝。"""
    return any(contains_sensitive_content(message.content) for message in context)
