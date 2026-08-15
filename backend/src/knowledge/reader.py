"""知识库共享读取器 — 受管目录内 Markdown 确定性检索（P6 Tool 与 P7 API 共用）。

提供受管目录内 Markdown 文档的列表、确定性检索与正文读取三类只读能力。
安全规则（隐藏/凭据文件排除、路径越界拒绝）与 P6 `SearchKnowledgeTool` 完全一致，
保证 P6 Tool 对外行为不变；正文、片段与标题统一经 `desensitize()` 脱敏兜底。
不引入向量/Embedding/RAG；只读受管目录，不做越权文件访问。
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from src.core.tool_gateway import desensitize

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
# 文档相对路径不允许携带的字符：反斜杠（Windows 分隔符）与控制字符；正斜杠是相对路径分隔符，允许
_ILLEGAL_PATH_RE = re.compile(r"[\\\x00-\x1f\x7f]")
# 凭据/隐藏类文件后缀与文件名，一律跳过
_EXCLUDED_SUFFIXES = (".env", ".local.yaml", ".key", ".pem", ".secret")
_EXCLUDED_FILENAMES = {".env", "config.local.yaml"}
_MARKDOWN_SUFFIX = ".md"


class KnowledgeDocumentMeta(BaseModel):
    """受管目录内单个 Markdown 文档的清单条目。"""

    title: str
    relative_name: str


class KnowledgeDocumentCursor(BaseModel):
    """知识文档列表键集分页游标：上一页最后一条文档的相对路径。

    仅与候选文档相对路径做字典序比较，绝不用于文件访问（无路径穿越面）。
    """

    relative_path: str


class KnowledgeSearchHit(BaseModel):
    """单篇文档的确定性检索命中结果（标题 + 相对文件名 + 命中片段）。"""

    title: str
    relative_name: str
    snippet_count: int
    title_hit: bool
    snippets: list[str]


def is_markdown(path: Path) -> bool:
    """判断文件是否为 Markdown 文档。"""
    return path.is_file() and path.suffix.lower() == _MARKDOWN_SUFFIX


def has_hidden_part(path: Path, root: Path) -> bool:
    """判断相对受管目录的路径是否含隐藏文件/目录段（以点开头）。"""
    try:
        rel = path.resolve().relative_to(root)
    except ValueError:
        return True
    return any(part.startswith(".") for part in rel.parts)


def is_excluded_name(name: str) -> bool:
    """判断文件名是否属于凭据/隐藏类文件（.env、*.local.yaml、密钥文件）。"""
    lowered = name.lower()
    return lowered in _EXCLUDED_FILENAMES or lowered.endswith(_EXCLUDED_SUFFIXES)


def collect_docs(root: Path) -> list[Path]:
    """收集受管目录下的候选 Markdown 文档，跳过越权/隐藏/凭据路径。

    注意：本函数不做内容级排除（含 `sk-` 的文档在匹配/列表/详情阶段处理），
    与 P6 `SearchKnowledgeTool` 的候选收集语义保持一致。
    """
    docs: list[Path] = []
    for path in root.rglob("*"):
        if not is_markdown(path):
            continue
        try:
            path.resolve().relative_to(root)
        except ValueError:
            # 符号链接等解析到受管目录之外：拒绝越权访问
            continue
        if has_hidden_part(path, root):
            # 隐藏文件/隐藏目录（.git、.notes 等）不进候选集
            continue
        if is_excluded_name(path.name):
            continue
        docs.append(path)
    # 确定性顺序：按相对路径排序
    docs.sort(key=lambda p: p.resolve().relative_to(root).as_posix())
    return docs


def extract_title(path: Path, text: str) -> str:
    """提取 Markdown 首个一级标题作为文档标题；无标题时回退文件名。"""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return path.stem


def read_limited(path: Path) -> str:
    """读取文档正文，限长避免超大文档拖慢检索。"""
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            return handle.read(_MAX_DOC_CHARS)
    except OSError:
        return ""


def find_snippets(text: str, keyword: str) -> tuple[list[str], int]:
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


def match_docs(root: Path, docs: list[Path], keyword: str) -> list[KnowledgeSearchHit]:
    """按标题优先 + 正文命中排序返回匹配结果（与 P6 规则一致）。

    含 `sk-` 明文的文档在匹配时跳过，保持「目录只含含 `sk-` 文档 → 无匹配」的既有语义。
    """
    results: list[KnowledgeSearchHit] = []
    for path in docs:
        text = read_limited(path)
        if not text or "sk-" in text:
            # 内容为空或含密钥明文（如 sk-xxx）的文档不进检索范围
            continue
        title = extract_title(path, text)
        title_hit = keyword in title.lower()
        snippets, hits = find_snippets(text, keyword)
        if not title_hit and hits == 0:
            continue
        results.append(
            KnowledgeSearchHit(
                title=title,
                relative_name=path.resolve().relative_to(root).as_posix(),
                snippet_count=hits,
                title_hit=title_hit,
                snippets=snippets,
            )
        )
    # 相关度：标题命中优先，其次正文命中次数，再按标题名
    results.sort(key=lambda d: (not d.title_hit, -d.snippet_count, d.title))
    return results


def list_documents(root: Path) -> list[KnowledgeDocumentMeta]:
    """受管目录内 Markdown 文档清单（按相对路径确定性排序）。

    排除隐藏/凭据路径，以及内容含 `sk-` 明文的文档；每篇返回标题 + 相对文件名。
    """
    meta: list[KnowledgeDocumentMeta] = []
    for path in collect_docs(root):
        text = read_limited(path)
        if not text or "sk-" in text:
            continue
        meta.append(
            KnowledgeDocumentMeta(
                title=extract_title(path, text),
                relative_name=path.resolve().relative_to(root).as_posix(),
            )
        )
    return meta


def list_documents_page(
    root: Path,
    cursor: KnowledgeDocumentCursor | None,
    limit: int,
) -> tuple[list[KnowledgeDocumentMeta], KnowledgeDocumentCursor | None]:
    """按相对路径确定性排序后分页返回文档清单（`limit` >= 1）。

    沿用 `collect_docs` 的候选收集与排除逻辑（隐藏/凭据路径、越权路径），并跳过内容为空或含
    `sk-` 明文的文档；游标仅与候选相对路径做字典序比较（跳过 `<= cursor` 的条目），绝不用于
    文件访问。返回 `(本页条目, 下一页光标)`：本页满 `limit` 时下一页光标为最后一条相对路径，
    否则为 None（末尾语义，翻页超出末尾返回空条目 + None）。
    """
    limit = max(1, limit)
    items: list[KnowledgeDocumentMeta] = []
    next_cursor: KnowledgeDocumentCursor | None = None
    for path in collect_docs(root):
        relative_name = path.resolve().relative_to(root).as_posix()
        if cursor is not None and relative_name <= cursor.relative_path:
            continue
        text = read_limited(path)
        if not text or "sk-" in text:
            continue
        items.append(
            KnowledgeDocumentMeta(
                title=extract_title(path, text),
                relative_name=relative_name,
            )
        )
        if len(items) >= limit:
            next_cursor = KnowledgeDocumentCursor(relative_path=relative_name)
            break
    return items, next_cursor


def search_documents(root: Path, query: str, limit: int = _DEFAULT_LIMIT) -> list[KnowledgeSearchHit]:
    """在受管目录内按关键词确定性检索，返回按相关度排序的命中结果（条数受限）。"""
    keyword = query.lower()
    ranked = match_docs(root, collect_docs(root), keyword)
    return ranked[:max(1, min(limit, _MAX_LIMIT))]


def read_document(root: Path, relative_name: str) -> str | None:
    """按受管目录内相对路径读取文档正文（脱敏后）；不可访问返回 None。

    仅限受管目录内 Markdown 文档；越界/绝对路径/隐藏/凭据文件或含 `sk-` 内容一律返回 None。
    """
    if not relative_name or relative_name.startswith(("/", "\\")):
        return None
    if _ILLEGAL_PATH_RE.search(relative_name):
        return None
    if any(segment in (".", "..") or segment == "" for segment in relative_name.split("/")):
        return None
    try:
        candidate = (root / relative_name).resolve()
    except (OSError, ValueError):
        return None
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        # 路径逃逸或符号链接越界：拒绝
        return None
    if not is_markdown(candidate):
        return None
    if has_hidden_part(candidate, root) or is_excluded_name(candidate.name):
        return None
    text = read_limited(candidate)
    if not text or "sk-" in text:
        return None
    return desensitize(text)
