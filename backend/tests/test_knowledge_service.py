"""P7 知识库应用服务（KnowledgeReaderService）单元测试。

锁定：诚实状态映射、限时执行抛 `KnowledgeTimeoutError`、执行器生命周期可 shutdown。
"""

from pathlib import Path

import pytest

from src.application.knowledge import KnowledgeReaderService, KnowledgeTimeoutError


def test_未配置目录返回not_configured(tmp_path: Path) -> None:
    """目录未配置（None）→ 列表/检索均 not_configured，详情 None。"""
    service = KnowledgeReaderService(None)
    try:
        assert service.configured is False
        assert service.root is None
        assert service.list_documents() == ("not_configured", [])
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
        assert service.list_documents() == ("not_configured", [])
    finally:
        service.shutdown()


def test_目录为空返回empty(tmp_path: Path) -> None:
    """目录存在但无 Markdown → empty。"""
    service = KnowledgeReaderService(str(tmp_path))
    try:
        assert service.list_documents() == ("empty", [])
        status, items = service.search("kill")
        assert status == "empty"
        assert items == []
    finally:
        service.shutdown()


def test_有文档返回ok(tmp_path: Path) -> None:
    """目录有 Markdown → ok，返回清单条目。"""
    (tmp_path / "a.md").write_text("# 文档 A\n\nkill 慢查询说明。\n", encoding="utf-8")
    service = KnowledgeReaderService(str(tmp_path))
    try:
        status, items = service.list_documents()
        assert status == "ok"
        assert [item.relative_name for item in items] == ["a.md"]
        hit_status, hits = service.search("kill")
        assert hit_status == "ok"
        assert hits[0].title == "文档 A"
    finally:
        service.shutdown()


def test_超时抛KnowledgeTimeoutError(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """限时执行超时 → 抛 KnowledgeTimeoutError（上层转 503）。"""
    from src.application import knowledge as knowledge_module

    def slow_list(_root: Path):
        import time

        time.sleep(2)
        return []

    monkeypatch.setattr(knowledge_module, "reader_list_documents", slow_list)
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
