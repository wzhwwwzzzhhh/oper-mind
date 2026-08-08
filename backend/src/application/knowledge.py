"""P7 知识库只读访问应用服务。

在受管知识目录上提供文档列表、确定性检索与文档正文读取三类只读能力，
复用 `src/knowledge/reader.py`（与 P6 `SearchKnowledgeTool` 共用同一套检索逻辑），
并做限时执行与诚实降级：目录未配置/不存在 → not_configured；目录空 → empty；
无匹配 → no_match；超时 → 抛 `KnowledgeTimeoutError`。只读，不写任何文件。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Literal

from src.knowledge.reader import (
    KnowledgeDocumentMeta,
    KnowledgeSearchHit,
    list_documents as reader_list_documents,
    read_document as reader_read_document,
    search_documents as reader_search_documents,
)


class KnowledgeTimeoutError(Exception):
    """知识库只读操作超时。"""


class KnowledgeReaderService:
    """按配置的受管目录提供知识库只读查询，全部操作带限时兜底。"""

    def __init__(self, directory: str | None, timeout_seconds: float = 3.0) -> None:
        self._directory = directory
        self._timeout_seconds = timeout_seconds
        # 复用单线程池承载限时执行，避免每请求新建线程；操作只读且受 256KB/文档限长约束。
        self._executor = ThreadPoolExecutor(max_workers=1)

    def shutdown(self) -> None:
        """释放内部线程池。"""
        self._executor.shutdown(wait=False)

    @property
    def configured(self) -> bool:
        """是否已配置且存在可读的受管知识目录。"""
        if not self._directory:
            return False
        return Path(self._directory).resolve().is_dir()

    @property
    def root(self) -> Path | None:
        """受管目录解析根；未配置/不存在返回 None。"""
        if not self._directory:
            return None
        root = Path(self._directory).resolve()
        return root if root.is_dir() else None

    def list_documents(self) -> tuple[Literal["not_configured", "empty", "ok"], list[KnowledgeDocumentMeta]]:
        """返回受管目录文档清单与诚实状态；目录为空返回空清单 + empty。"""
        root = self.root
        if root is None:
            return "not_configured", []
        items = self._run(lambda: reader_list_documents(root))
        return ("ok" if items else "empty"), items

    def search(
        self, query: str, limit: int = 5
    ) -> tuple[Literal["not_configured", "empty", "no_match", "ok"], list[KnowledgeSearchHit]]:
        """在受管目录内确定性检索；无匹配返回空清单 + no_match。"""
        root = self.root
        if root is None:
            return "not_configured", []
        docs = self._run(lambda: reader_list_documents(root))
        if not docs:
            return "empty", []
        hits = self._run(lambda: reader_search_documents(root, query, limit))
        return ("ok" if hits else "no_match"), hits

    def get_document(self, relative_name: str) -> str | None:
        """按受管目录内相对路径读取脱敏正文；不可访问返回 None。"""
        root = self.root
        if root is None:
            return None
        return self._run(lambda: reader_read_document(root, relative_name))

    def _run(self, fn):
        """限时执行只读操作，超时抛 KnowledgeTimeoutError。"""
        future = self._executor.submit(fn)
        try:
            return future.result(timeout=self._timeout_seconds)
        except FutureTimeoutError as error:
            raise KnowledgeTimeoutError() from error
