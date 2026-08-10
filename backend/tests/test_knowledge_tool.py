"""知识检索工具单元测试：诚实空态、确定性检索、路径逃逸、凭据排除与脱敏。

AC1–AC6 覆盖。测试全部使用 tmp_path 确定性目录，不连接任何外部资源。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.tool_gateway import ToolGateway
from src.core.tool_registry import ToolRegistry
from src.tools.knowledge_tools import SearchKnowledgeTool


def _write(base: Path, rel: str, text: str) -> None:
    """在临时知识目录内写入一份测试文档。"""
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def knowledge_dir(tmp_path: Path) -> Path:
    """构造含两篇 Markdown 文档的临时知识目录。"""
    base = tmp_path / "knowledge"
    _write(base, "kill-slow-query.md", "# kill 慢查询 SOP\n\n先确认会话状态，再 kill 慢查询进程。\n")
    _write(base, "index-tuning.md", "# 索引优化手册\n\n慢查询常来自全表扫描，加索引即可。\n")
    return base


def test_未配置知识目录返回未配置状态() -> None:
    """知识目录未配置时应诚实返回「未配置」，不崩溃、不伪造。"""
    tool = SearchKnowledgeTool(directory=None)

    result = tool.execute("慢查询")

    assert "未配置" in result
    assert "慢查询" not in result.splitlines()[0]


def test_knowledge_dir缺失时返回未配置(tmp_path: Path) -> None:
    """目录不存在应同样视为未配置，拒绝任意文件系统访问。"""
    tool = SearchKnowledgeTool(directory=str(tmp_path / "not-exists"))

    result = tool.execute("慢查询")

    assert "未配置" in result


def test_knowledge_dir为空时返回无文档(tmp_path: Path) -> None:
    """目录存在但无候选 Markdown 时应诚实返回「无文档」。"""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    tool = SearchKnowledgeTool(directory=str(empty_dir))

    result = tool.execute("慢查询")

    assert "无 Markdown 文档" in result


def test_命中返回标题文件名与摘要(knowledge_dir: Path) -> None:
    """命中文档应返回标题、文件名和脱敏摘要片段。"""
    tool = SearchKnowledgeTool(directory=str(knowledge_dir))

    result = tool.execute("慢查询")

    assert "命中 2 篇" in result
    assert "kill 慢查询 SOP" in result
    assert "索引优化手册" in result


def test_标题匹配优先于正文命中(knowledge_dir: Path) -> None:
    """标题命中文档应先于仅正文命中的文档返回。"""
    tool = SearchKnowledgeTool(directory=str(knowledge_dir))

    result = tool.execute("慢查询")

    first_line = result.splitlines()[1]
    assert "kill 慢查询 SOP" in first_line


def test_limit截断返回条数(knowledge_dir: Path) -> None:
    """limit 应限制返回文档条数。"""
    tool = SearchKnowledgeTool(directory=str(knowledge_dir))

    result = tool.execute("慢查询", limit=1)

    assert "命中 1 篇" in result
    assert "索引优化手册" not in result


def test_无匹配时返回无匹配文档(knowledge_dir: Path) -> None:
    """检索词无任何命中应如实返回「无匹配」。"""
    tool = SearchKnowledgeTool(directory=str(knowledge_dir))

    result = tool.execute("Kubernetes")

    assert "无匹配" in result


def test_路径分隔符查询被拒绝(knowledge_dir: Path) -> None:
    """查询词含路径分隔符应被参数校验拒绝，不允许作为路径拼接输入。"""
    tool = SearchKnowledgeTool(directory=str(knowledge_dir))

    for bad_query in ("../etc/passwd", "a/b", "a\\b", "/etc/passwd"):
        result = tool.execute(bad_query)
        assert "拒绝" in result, bad_query


def test_点目录查询不作为路径访问(knowledge_dir: Path) -> None:
    """查询词仅作纯文本匹配，`..` 不触发越权，也不被当作路径使用。"""
    tool = SearchKnowledgeTool(directory=str(knowledge_dir))

    result = tool.execute("..")

    assert "无匹配" in result


def test_超长查询被拒绝(knowledge_dir: Path) -> None:
    """超长检索词应被参数校验拒绝。"""
    tool = SearchKnowledgeTool(directory=str(knowledge_dir))

    result = tool.execute("x" * 101)

    assert "拒绝" in result


def test_空查询被拒绝(knowledge_dir: Path) -> None:
    """空白检索词应被拒绝，避免无意义检索。"""
    tool = SearchKnowledgeTool(directory=str(knowledge_dir))

    result = tool.execute("   ")

    assert "拒绝" in result


def test_凭据文件不在检索范围(knowledge_dir: Path) -> None:
    """.env 和 *.local.yaml 等凭据文件不得进入检索候选。"""
    _write(knowledge_dir, ".env", "OPERMIND_PG_DSN=postgresql://user:secret@host/db\n")
    _write(knowledge_dir, "config.local.yaml", "database_url: postgresql://user:secret@host/db\n")
    _write(knowledge_dir, "secret.md", "# 密钥文档\nOPERMIND_API_KEY=sk-abcdef123456\n")
    tool = SearchKnowledgeTool(directory=str(knowledge_dir))

    result = tool.execute("OPERMIND_API_KEY")

    assert "无匹配" in result


def test_命中摘要不含凭据经过网关脱敏(knowledge_dir: Path) -> None:
    """网关应对命中片段内的凭据做兜底脱敏，不泄漏明文连接串口令。"""
    _write(knowledge_dir, "credential-in-doc.md", "# 常见配置项\n认证口令 password=hunter2 用于某环境。\n")
    tool = SearchKnowledgeTool(directory=str(knowledge_dir))
    registry = ToolRegistry()
    registry.register(tool)
    gateway = ToolGateway(registry)
    try:
        result = gateway.invoke("search_knowledge", json.dumps({"query": "password"}))
    finally:
        gateway.shutdown()

    assert result.record.status == "ok"
    assert "password=hunter2" not in result.output
    assert "password=hunter2" not in result.record.detail


def test_审计摘要仅含命中标题不含全文(knowledge_dir: Path) -> None:
    """audit_summary 应只包含命中数与标题列表，不携带正文片段。"""
    tool = SearchKnowledgeTool(directory=str(knowledge_dir))

    tool.execute("慢查询")

    summary = tool.audit_summary()
    assert "命中 2 篇" in summary
    assert "kill 慢查询 SOP" in summary
    assert "索引优化手册" in summary
    assert "先确认会话状态" not in summary


def test_隐藏文件与隐藏目录不在检索范围(knowledge_dir: Path) -> None:
    """隐藏文件/隐藏目录内的 Markdown 一律不进候选集。"""
    _write(knowledge_dir, ".hidden.md", "# 隐藏文档\n内部凭据操作记录\n")
    _write(knowledge_dir, ".notes/secret-ops.md", "# 隐藏目录文档\n隐藏目录里的操作\n")
    tool = SearchKnowledgeTool(directory=str(knowledge_dir))

    result = tool.execute("隐藏")

    assert "无匹配" in result


def test_audit_summary反映最近一次结果(knowledge_dir: Path) -> None:
    """无匹配或拒绝调用后，audit_summary 应更新为新结果，不得返回陈旧命中摘要。"""
    tool = SearchKnowledgeTool(directory=str(knowledge_dir))
    tool.execute("慢查询")
    assert "命中 2 篇" in tool.audit_summary()

    tool.execute("Kubernetes")
    assert "无匹配" in tool.audit_summary()

    tool.execute("../etc/passwd")
    assert "已拒绝" in tool.audit_summary()


def test_符号链接越界不进入检索范围(tmp_path: Path) -> None:
    """指向受管目录之外的符号链接应被跳过，不返回目录外文件。"""
    import os

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    _write(outside_dir, "outside-doc.md", "# 目录外文档\n目录外的敏感内容\n")

    base = tmp_path / "knowledge"
    base.mkdir()
    try:
        os.symlink(outside_dir / "outside-doc.md", base / "escape.md", target_is_directory=False)
    except (OSError, NotImplementedError) as exc:
        # 环境不支持创建符号链接时跳过该用例，避免误报
        pytest.skip(f"无法创建符号链接：{exc}")

    tool = SearchKnowledgeTool(directory=str(base))

    result = tool.execute("目录外")

    assert "目录外的敏感内容" not in result
    assert "目录外文档" not in result
