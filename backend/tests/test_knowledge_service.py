"""P7/P8 知识库应用服务（KnowledgeReaderService）单元测试。

锁定：诚实状态映射（含 P8 分页语义）、限时执行抛 `KnowledgeTimeoutError`、执行器生命周期可 shutdown。
"""

from pathlib import Path

import pytest

from src.application.knowledge import KnowledgeReaderService, KnowledgeTimeoutError
from src.knowledge.reader import KnowledgeDocumentCursor


def test_未配置目录返回not_configured(tmp_path: Path) -> None:
    """目录未配置（None）→ 列表/检索均 not_configured，详情 None。"""
    service = KnowledgeReaderService(None)
    try:
        assert service.configured is False
        assert service.root is None
        assert service.list_documents() == ("not_configured", [], None)
        status, items = service.search("kill")
        assert status == "not_configured"
        assert items == []
        assert service.get_document("x.md") is None
    finally:
        service.shutdown()


def test_目录不存在返回not_configured(tmp_path: Path) -> None:
    """目录路径存在但目录不存在 → not_configured。"""
    missing = tmp_path / "no-such-dir"
    service = KnowledgeReaderService(str(missing))
    try:
        assert service.list_documents() == ("not_configured", [], None)
    finally:
        service.shutdown()


def test_目录为空返回empty(tmp_path: Path) -> None:
    """目录存在但无 Markdown → empty。"""
    service = KnowledgeReaderService(str(tmp_path))
    try:
        assert service.list_documents() == ("empty", [], None)
        status, items = service.search("kill")
        assert status == "empty"
        assert items == []
    finally:
        service.shutdown()


def test_有文档返回ok(tmp_path: Path) -> None:
    """目录有 Markdown → ok，返回清单条目（单页不足 limit 时无下一页）。"""
    (tmp_path / "a.md").write_text("# 文档 A\n\nkill 慢查询说明。\n", encoding="utf-8")
    service = KnowledgeReaderService(str(tmp_path))
    try:
        status, items, next_cursor = service.list_documents()
        assert status == "ok"
        assert [item.relative_name for item in items] == ["a.md"]
        assert next_cursor is None
        hit_status, hits = service.search("kill")
        assert hit_status == "ok"
        assert hits[0].title == "文档 A"
    finally:
        service.shutdown()


def test_分页按相对路径翻页不重不漏(tmp_path: Path) -> None:
    """超过页大小的目录 → 每页不超 limit，页间不重不漏，末页后无下一页。"""
    for name in ("b.md", "a.md", "c.md", "e.md", "d.md"):
        (tmp_path / name).write_text(f"# 文档 {name}\n\n内容。\n", encoding="utf-8")
    service = KnowledgeReaderService(str(tmp_path))
    try:
        first_status, first_items, first_next = service.list_documents(limit=2)
        assert first_status == "ok"
        assert [item.relative_name for item in first_items] == ["a.md", "b.md"]
        assert first_next is not None
        assert first_next.relative_path == "b.md"

        second_status, second_items, second_next = service.list_documents(first_next, limit=2)
        assert second_status == "ok"
        assert [item.relative_name for item in second_items] == ["c.md", "d.md"]
        assert second_next is not None
        assert second_next.relative_path == "d.md"

        third_status, third_items, third_next = service.list_documents(second_next, limit=2)
        assert third_status == "ok"
        assert [item.relative_name for item in third_items] == ["e.md"]
        assert third_next is None

        # 翻页超出末尾：ok + 空清单 + 无下一页（不抛错，「无更多」语义）
        beyond_status, beyond_items, beyond_next = service.list_documents(
            KnowledgeDocumentCursor(relative_path="e.md"), limit=2
        )
        assert beyond_status == "ok"
        assert beyond_items == []
        assert beyond_next is None
    finally:
        service.shutdown()


def test_超时抛KnowledgeTimeoutError(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """限时执行超时 → 抛 KnowledgeTimeoutError（上层转 503）。"""
    from src.application import knowledge as knowledge_module

    def slow_list_page(_root: Path, _cursor, _limit):
        import time

        time.sleep(2)
        return [], None

    monkeypatch.setattr(knowledge_module, "reader_list_documents_page", slow_list_page)
    service = KnowledgeReaderService(str(tmp_path), timeout_seconds=0.1)
    try:
        with pytest.raises(KnowledgeTimeoutError):
            service.list_documents()
    finally:
        service.shutdown()


def test_shutdown可释放线程池(tmp_path: Path) -> None:
    """shutdown 后仍可再次安全调用（不会复用已关线程池）。"""
    service = KnowledgeReaderService(str(tmp_path))
    service.shutdown()


def test_read_document路径逃逸直接拒绝(tmp_path: Path) -> None:
    """reader 层直接锁定路径逃逸防护（不经 HTTP 客户端规范化），覆盖段级/字符级/前缀校验。"""
    (tmp_path / "inside.md").write_text("# 内部\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "doc.md").write_text("# 子文档\n", encoding="utf-8")
    outside = tmp_path.parent / "outside.md"
    outside.write_text("# 外部\n", encoding="utf-8")
    service = KnowledgeReaderService(str(tmp_path))
    try:
        assert service.get_document("inside.md") is not None
        assert service.get_document("sub/doc.md") is not None
        # 段级拒绝：绝对路径 / `..`/`.` 段 / 空段 / 反斜杠 / 控制字符
        for bad in (
            "/etc/passwd",
            "\\etc\\passwd",
            "../outside.md",
            "sub/../inside.md",
            "sub/./inside.md",
            "sub//inside.md",
            "sub\\..\\outside.md",
            "sub\x00.md",
        ):
            assert service.get_document(bad) is None, bad
        # 非 markdown / 隐藏 / 凭据文件
        (tmp_path / "note.txt").write_text("x\n", encoding="utf-8")
        (tmp_path / ".env").write_text("TOKEN=x\n", encoding="utf-8")
        (tmp_path / "config.local.yaml").write_text("p: x\n", encoding="utf-8")
        assert service.get_document("note.txt") is None
        assert service.get_document(".env") is None
        assert service.get_document("config.local.yaml") is None
        assert outside.exists()
    finally:
        service.shutdown()
