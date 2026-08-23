"""知识检索工具集 — 受管目录内 Markdown 确定性检索。

按关键词/标题在配置的知识目录内检索 Markdown 文档，返回脱敏摘要（标题 + 命中片段）。
确定性匹配，不引入向量/Embedding/RAG；只读受管目录，不做越权文件访问。

检索实现复用 `src/knowledge/reader.py`（与 P7 知识库页面 API 共用同一套逻辑），
本工具负责把结构化命中结果格式化为供 Agent 阅读的多行文本，并对外行为保持不变。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from src.core.tool_registry import Tool
from src.knowledge import reader


class SearchKnowledgeTool(Tool):
    """在受管 Markdown 知识目录内做确定性关键词/标题检索。

    - 目录未配置/不存在 → 明确返回「未配置」，绝不访问任意路径。
    - 目录为空 → 明确返回「无文档」。
    - 无匹配 → 明确返回「无匹配」。
    - 命中返回脱敏摘要（标题 + 相对文件名 + 命中片段），相关度排序并限流。
    """

    def __init__(self, directory: str | None = None) -> None:
        super().__init__(
            name="search_knowledge",
            description="在受管知识目录内按关键词检索 Markdown 文档，返回脱敏摘要",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词或短语"},
                    "limit": {"type": "integer", "description": "最多返回条数，默认 5"},
                },
                "required": ["query"],
            },
        )
        self._directory = directory
        self._last_summary = "知识检索未执行"
        self._last_status: Literal["ok", "unavailable", "rejected"] = "ok"

    def audit_summary(self) -> str:
        """返回最近一次检索的脱敏审计摘要（命中数与标题，供 Trace 展示）。"""
        return self._last_summary

    def execution_status(self) -> Literal["ok", "unavailable", "rejected"]:
        """把未配置与参数拒绝诚实投影给 ToolGateway。"""
        return self._last_status

    def execute(self, query: str, limit: int = reader._DEFAULT_LIMIT) -> str:
        """执行确定性检索，返回脱敏摘要文本。永远不抛异常。"""
        # 参数校验：非空、长度与路径注入字符
        normalized_query = query.strip()
        if not normalized_query:
            return self._finish("检索词为空，已拒绝", "rejected")
        if len(normalized_query) > reader._QUERY_MAX_LEN:
            return self._finish(f"检索词超过 {reader._QUERY_MAX_LEN} 字符，已拒绝", "rejected")
        if reader._ILLEGAL_QUERY_RE.search(normalized_query):
            return self._finish("检索词含路径分隔符或控制字符，已拒绝（防路径逃逸）", "rejected")
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            return self._finish("limit 必须是 1-10 的整数", "rejected")
        limit = max(1, min(limit, reader._MAX_LIMIT))

        # 诚实空态：目录未配置 / 不存在
        if not self._directory:
            return self._finish("知识目录未配置：请先配置 OPERMIND_KNOWLEDGE_DIR，检索未启用", "unavailable")
        root = Path(self._directory).resolve()
        if not root.is_dir():
            return self._finish("知识目录未配置/不存在：请检查 OPERMIND_KNOWLEDGE_DIR 指向", "unavailable")

        # 收集受管 Markdown 候选（只读）
        docs = reader.collect_docs(root)
        if not docs:
            return self._finish("知识目录为空，无 Markdown 文档")

        keyword = normalized_query.lower()
        ranked = reader.match_docs(root, docs, keyword)
        if not ranked:
            return self._finish("无匹配：知识目录中没有与检索词匹配的文档")

        top = ranked[:limit]
        self._last_status = "ok"
        self._last_summary = f"知识检索命中 {len(top)} 篇：" + "、".join(
            doc.title for doc in top
        )
        lines = [f"知识检索（受管目录确定性检索）：命中 {len(top)} 篇文档"]
        for doc in top:
            lines.append(f"- 《{doc.title}》 ({doc.relative_name}) {doc.snippet_count} 处命中")
            for snippet in doc.snippets:
                lines.append(f"    · {snippet}")
        return "\n".join(lines)

    def _finish(
        self,
        message: str,
        status: Literal["ok", "unavailable", "rejected"] = "ok",
    ) -> str:
        """记录本次检索的审计摘要并返回提示文本。"""
        self._last_summary = message
        self._last_status = status
        return message
