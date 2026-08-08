"""P7 知识库只读 REST API 测试。

覆盖：诚实状态（not_configured/empty/no_match/ok）、文档列表、确定性检索、文档详情、
路径逃逸拒绝、凭据文件与 `sk-` 内容排除、正文脱敏兜底。全部使用 tmp 确定性目录，不连接外部资源。
"""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
# 知识库应用依赖在模块导入时按 OPERMIND_KNOWLEDGE_DIR 装配，因此用模块级环境注入 + 目录操作切换状态。
# 服务每次请求即时读取目录，因此测试通过创建/删除/写入目录内容来切换 not_configured/empty/ok。


@pytest.fixture(scope="module")
def knowledge_env(tmp_path_factory) -> Iterator[tuple[TestClient, Path]]:
    """构造只读知识库 API 测试环境。

    直接向全局应用注入知识库服务（目录路径尚未创建，模拟未配置），避免依赖
    模块导入顺序导致的全局装配差异；测试通过创建/删除目录与写入文件切换状态。
    退出时恢复全局服务，避免污染其他测试模块。
    """
    knowledge_dir = tmp_path_factory.getbasetemp() / "knowledge-api-dir"
    if knowledge_dir.exists():
        shutil.rmtree(knowledge_dir)

    from src import app as api_module
    from src.api.v1.dependencies import V1Services
    from src.application.knowledge import KnowledgeReaderService

    original_services = api_module.app.state.v1_services
    # 覆盖全局装配：知识库服务独立注入，其他字段置空（本套测试只走知识库路由）。
    api_module.app.state.v1_services = V1Services(
        session_factory=None,  # type: ignore[arg-type]
        session_service=None,  # type: ignore[arg-type]
        run_service=None,  # type: ignore[arg-type]
        knowledge_service=KnowledgeReaderService(str(knowledge_dir)),
    )

    try:
        with TestClient(api_module.app, raise_server_exceptions=False) as client:
            yield client, knowledge_dir
    finally:
        api_module.app.state.v1_services = original_services


def _seed_docs(root: Path) -> None:
    """写入受管目录内的确定性测试文档。"""
    (root / "sop").mkdir(parents=True, exist_ok=True)
    (root / "sop" / "kill-slow-query.md").write_text(
        "# kill 慢查询 SOP\n\n执行 kill 慢查询前先确认会话。\n", encoding="utf-8"
    )
    (root / "sop" / "index-tuning.md").write_text(
        "# 索引优化手册\n\n通过 EXPLAIN 判断是否使用索引。\n", encoding="utf-8"
    )


def test_列表与详情接口目录未配置返回not_configured(knowledge_env) -> None:
    """目录不存在 → 列表/详情均返回 not_configured 诚实空态，不崩溃。"""
    client, root = knowledge_env
    if root.exists():
        for child in root.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        root.rmdir()
    list_response = client.get("/api/v1/knowledge/documents")
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["status"] == "not_configured"
    assert body["items"] == []
    assert "meta" in body

    detail_response = client.get("/api/v1/knowledge/documents/sop/kill-slow-query.md")
    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "not_configured"
    root.mkdir(parents=True, exist_ok=True)


def test_列表接口目录为空返回empty(knowledge_env) -> None:
    """目录存在但无 Markdown 文档 → empty。"""
    client, root = knowledge_env
    root.mkdir(parents=True, exist_ok=True)
    response = client.get("/api/v1/knowledge/documents")
    assert response.status_code == 200
    assert response.json()["status"] == "empty"


def test_列表接口返回受管文档清单(knowledge_env) -> None:
    """目录有文档 → 返回标题 + 相对路径，确定性排序。"""
    client, root = knowledge_env
    _seed_docs(root)
    response = client.get("/api/v1/knowledge/documents")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["items"] == [
        {"title": "索引优化手册", "relative_path": "sop/index-tuning.md"},
        {"title": "kill 慢查询 SOP", "relative_path": "sop/kill-slow-query.md"},
    ]


def test_检索接口命中返回匹配文档与片段(knowledge_env) -> None:
    """检索词有匹配 → 返回标题 + 命中片段，相关度排序。"""
    client, _ = knowledge_env
    response = client.get("/api/v1/knowledge/search", params={"query": "kill"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["title"] == "kill 慢查询 SOP"
    assert item["relative_path"] == "sop/kill-slow-query.md"
    assert item["snippet_count"] >= 1
    assert any("kill 慢查询" in snippet for snippet in item["snippets"])


def test_检索接口无匹配返回no_match(knowledge_env) -> None:
    """检索词无匹配 → no_match 诚实空态。"""
    client, _ = knowledge_env
    response = client.get("/api/v1/knowledge/search", params={"query": "不存在的关键词"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "no_match"
    assert body["items"] == []


def test_检索接口limit截断返回条数(knowledge_env) -> None:
    """limit 参数限制返回条数。"""
    client, root = knowledge_env
    (root / "sop" / "slow-query-a.md").write_text("# 慢查询 A\n\nkill 相关\n", encoding="utf-8")
    (root / "sop" / "slow-query-b.md").write_text("# 慢查询 B\n\nkill 相关\n", encoding="utf-8")
    response = client.get("/api/v1/knowledge/search", params={"query": "kill", "limit": 2})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert len(response.json()["items"]) <= 2


def test_检索接口非法检索词返回422(knowledge_env) -> None:
    """路径分隔符/控制字符检索词 → 422，拒绝路径注入。"""
    client, _ = knowledge_env
    for bad in ("../etc/passwd", "a/b", "a\\b", "/etc/passwd"):
        response = client.get("/api/v1/knowledge/search", params={"query": bad})
        assert response.status_code == 422, bad


def test_详情接口返回脱敏正文(knowledge_env) -> None:
    """详情返回受管目录内 Markdown 正文（经 desensitize 脱敏兜底）。"""
    client, root = knowledge_env
    (root / "sop" / "credentials.md").write_text(
        "# 连接文档\n\n数据库连接 postgres://user:pass@db.example/app，口令 token=abc123xyz。\n",
        encoding="utf-8",
    )
    response = client.get("/api/v1/knowledge/documents/sop/credentials.md")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["document"]["title"] == "连接文档"
    assert body["document"]["relative_path"] == "sop/credentials.md"
    text = response.text
    assert "abc123xyz" not in text
    assert "user:pass" not in text
    assert "pass@db.example" not in text


def test_详情接口路径逃逸被拒绝(knowledge_env) -> None:
    """目录外路径/绝对路径/`..` 段 → 404，不返回目录外文件。"""
    client, root = knowledge_env
    # 在受管目录外放一个文件
    outside = root.parent / "outside-secret.md"
    outside.write_text("# 目录外内容\n", encoding="utf-8")
    for bad in ("../outside-secret.md", "sop/../kill-slow-query.md", "/etc/passwd", "sop//kill-slow-query.md"):
        response = client.get(f"/api/v1/knowledge/documents/{bad}")
        assert response.status_code == 404, bad


def test_详情接口非markdown被拒绝(knowledge_env) -> None:
    """非 Markdown 文件（如 .txt/.env）→ 404。"""
    client, root = knowledge_env
    (root / "note.txt").write_text("plain text\n", encoding="utf-8")
    (root / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    response = client.get("/api/v1/knowledge/documents/note.txt")
    assert response.status_code == 404
    response = client.get("/api/v1/knowledge/documents/.env")
    assert response.status_code == 404


def test_凭据文件不进入列表检索与详情(knowledge_env) -> None:
    """.env、config.local.yaml、*.local.yaml、密钥文件不在任何视图出现。"""
    client, root = knowledge_env
    (root / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    (root / "config.local.yaml").write_text("password: x\n", encoding="utf-8")
    (root / "dev.local.yaml").write_text("token: y\n", encoding="utf-8")
    (root / "key.pem").write_text("PRIVATE KEY\n", encoding="utf-8")

    list_body = client.get("/api/v1/knowledge/documents").json()
    paths = {item["relative_path"] for item in list_body["items"]}
    assert ".env" not in paths
    assert "config.local.yaml" not in paths
    assert "dev.local.yaml" not in paths
    assert "key.pem" not in paths

    search_body = client.get("/api/v1/knowledge/search", params={"query": "secret"}).json()
    assert all("secret" not in item["relative_path"] for item in search_body["items"])

    for path in (".env", "config.local.yaml", "dev.local.yaml", "key.pem"):
        response = client.get(f"/api/v1/knowledge/documents/{path}")
        assert response.status_code == 404, path


def test_含sk内容文档不进入列表检索与详情(knowledge_env) -> None:
    """正文含 sk- 明文的文档视为不可访问：列表/检索排除、详情 404。"""
    client, root = knowledge_env
    (root / "leak.md").write_text("# 泄漏文档\n\nkey 是 sk-abc123def456。\n", encoding="utf-8")
    list_body = client.get("/api/v1/knowledge/documents").json()
    assert "leak.md" not in {item["relative_path"] for item in list_body["items"]}
    search_body = client.get("/api/v1/knowledge/search", params={"query": "泄漏"}).json()
    assert all("leak.md" not in item["relative_path"] for item in search_body["items"])
    response = client.get("/api/v1/knowledge/documents/leak.md")
    assert response.status_code == 404


def test_检索与列表结果不含凭据明文(knowledge_env) -> None:
    """检索片段与标题经脱敏兜底，不包含 sk-/连接串凭据。"""
    client, root = knowledge_env
    (root / "ops.md").write_text(
        "# 排障手册\n\n连接串 postgres://admin:pw@host/app，token 是 sk-aaaa1111bbbb。\n",
        encoding="utf-8",
    )
    response = client.get("/api/v1/knowledge/search", params={"query": "排障"})
    assert response.status_code == 200
    text = response.text
    assert "sk-aaaa1111bbbb" not in text
    assert "admin:pw" not in text
    assert "pw@host" not in text
