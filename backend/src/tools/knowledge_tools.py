"""知识检索工具集 — 受管目录内 Markdown 确定性检索。

按关键词/标题在配置的知识目录内检索 Markdown 文档，返回脱敏摘要（标题 + 命中片段）。
确定性匹配，不引入向量/Embedding/RAG；只读受管目录，不做越权文件访问。
"""

from __future__ import annotations

import re
from pathlib import Path

from src.core.tool_registry import Tool


# 命中片段选取上下文长度（关键词前后各 60 字符）
_SNIPPET_CONTEXT = 60
# 单文档最多返回片段数
_MAX_SNIPPETS = 2
# 单文档读取上限（避免超大文档拖慢检索）
_MAX_DOC_CHARS = 256 * 1024
# 检索词长度上限
_QUERY_MAX_LEN = 100
# 默认/最大返回条数
_DEFAULT_LIMIT = 5
_MAX_LIMIT = 10
# 路径逃逸/注入字符：检索词不允许携带路径分隔符与控制字符
_ILLEGAL_QUERY_RE = re.compile(r"[/\\\x00-\x1f\x7f]")
# 凭据/隐藏类文件后缀与文件名，一律跳过
_EXCLUDED_SUFFIXES = (".env", ".local.yaml", ".key", ".pem", ".secret")
_EXCLUDED_FILENAMES = {".env", "config.local.yaml"}
_MARKDOWN_SUFFIX = ".md"


def _is_markdown(path: Path) -> bool:
    """判断文件是否为 Markdown 文档。"""
    return path.is_file() and path.suffix.lower() == _MARKDOWN_SUFFIX


def _has_hidden_part(path: Path, root: Path) -> bool:
    """判断相对受管目录的路径是否含隐藏文件/目录段（以点开头）。"""
    try:
        rel = path.resolve().relative_to(root)
    except ValueError:
        return True
    return any(part.startswith(".") for part in rel.parts)


def _is_excluded_name(name: str) -> bool:
    """判断文件名是否属于凭据/隐藏类文件（.env、*.local.yaml、密钥文件）。"""
    lowered = name.lower()
    return lowered in _EXCLUDED_FILENAMES or lowered.endswith(_EXCLUDED_SUFFIXES)


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

    def audit_summary(self) -> str:
        """返回最近一次检索的脱敏审计摘要（命中数与标题，供 Trace 展示）。"""
        return self._last_summary

    def execute(self, query: str, limit: int = _DEFAULT_LIMIT) -> str:
        """执行确定性检索，返回脱敏摘要文本。永远不抛异常。"""
        # 参数校验：非空、长度与路径注入字符
        normalized_query = query.strip()
        if not normalized_query:
            return self._finish("检索词为空，已拒绝")
        if len(normalized_query) > _QUERY_MAX_LEN:
            return self._finish(f"检索词超过 {_QUERY_MAX_LEN} 字符，已拒绝")
        if _ILLEGAL_QUERY_RE.search(normalized_query):
            return self._finish("检索词含路径分隔符或控制字符，已拒绝（防路径逃逸）")
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            return self._finish("limit 必须是 1-10 的整数")
        limit = max(1, min(limit, _MAX_LIMIT))

        # 诚实空态：目录未配置 / 不存在
        if not self._directory:
            return self._finish("知识目录未配置：请先配置 OPERMIND_KNOWLEDGE_DIR，检索未启用")
        root = Path(self._directory).resolve()
        if not root.is_dir():
            return self._finish("知识目录未配置/不存在：请检查 OPERMIND_KNOWLEDGE_DIR 指向")

        # 收集受管 Markdown 候选（只读）
        docs = self._collect_docs(root)
        if not docs:
            return self._finish("知识目录为空，无 Markdown 文档")

        keyword = normalized_query.lower()
        ranked = self._match_docs(root, docs, keyword)
        if not ranked:
            return self._finish("无匹配：知识目录中没有与检索词匹配的文档")

        top = ranked[:limit]
        self._last_summary = f"知识检索命中 {len(top)} 篇：" + "、".join(
            doc["title"] for doc in top
        )
        lines = [f"知识检索（受管目录确定性检索）：命中 {len(top)} 篇文档"]
        for doc in top:
            lines.append(f"- 《{doc['title']}》 ({doc['relative_name']}) {doc['snippet_count']} 处命中")
            for snippet in doc["snippets"]:
                lines.append(f"    · {snippet}")
        return "\n".join(lines)

    def _finish(self, message: str) -> str:
        """记录本次检索的审计摘要并返回提示文本。"""
        self._last_summary = message
        return message

    def _collect_docs(self, root: Path) -> list[Path]:
        """收集受管目录下的候选 Markdown 文档，跳过越权/隐藏/凭据路径。"""
        docs: list[Path] = []
        for path in root.rglob("*"):
            if not _is_markdown(path):
                continue
            try:
                path.resolve().relative_to(root)
            except ValueError:
                # 符号链接等解析到受管目录之外：拒绝越权访问
                continue
            if _has_hidden_part(path, root):
                # 隐藏文件/隐藏目录（.git、.notes 等）不进候选集
                continue
            if _is_excluded_name(path.name):
                continue
            docs.append(path)
        # 确定性顺序：按相对路径排序
        docs.sort(key=lambda p: p.resolve().relative_to(root).as_posix())
        return docs

    def _match_docs(self, root: Path, docs: list[Path], keyword: str) -> list[dict]:
        """按标题优先 + 正文命中排序返回匹配结果。"""
        results: list[dict] = []
        for path in docs:
            text = self._read_limited(path)
            if not text or "sk-" in text:
                # 内容为空或含密钥明文（如 sk-xxx）的文档不进检索范围
                continue
            title = self._extract_title(path, text)
            title_hit = keyword in title.lower()
            snippets, hits = self._find_snippets(text, keyword)
            if not title_hit and hits == 0:
                continue
            results.append(
                {
                    "title": title,
                    "relative_name": path.resolve().relative_to(root).as_posix(),
                    "snippet_count": hits,
                    "title_hit": title_hit,
                    "snippets": snippets,
                }
            )
        # 相关度：标题命中优先，其次正文命中次数，再按标题名
        results.sort(key=lambda d: (not d["title_hit"], -d["snippet_count"], d["title"]))
        return results

    def _extract_title(self, path: Path, text: str) -> str:
        """提取 Markdown 首个一级标题作为文档标题；无标题时回退文件名。"""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return path.stem

    def _read_limited(self, path: Path) -> str:
        """读取文档正文，限长避免超大文档拖慢检索。"""
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                return handle.read(_MAX_DOC_CHARS)
        except OSError:
            return ""

    def _find_snippets(self, text: str, keyword: str) -> tuple[list[str], int]:
        """正文命中：定位关键词上下文片段，返回片段列表与命中次数。"""
        lower_text = text.lower()
        positions: list[int] = []
        start = 0
        while start < len(lower_text):
            idx = lower_text.find(keyword, start)
            if idx == -1:
                break
            positions.append(idx)
            start = idx + max(1, len(keyword))

        snippets: list[str] = []
        for idx in positions[:_MAX_SNIPPETS]:
            begin = max(0, idx - _SNIPPET_CONTEXT)
            end = min(len(text), idx + len(keyword) + _SNIPPET_CONTEXT)
            snippet = " ".join(text[begin:end].split())
            if snippet:
                snippets.append(snippet)
        return snippets, len(positions)