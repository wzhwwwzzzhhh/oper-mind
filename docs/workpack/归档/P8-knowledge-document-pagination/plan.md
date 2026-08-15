# P8-knowledge-document-pagination · 工作包计划

## 基线与确认

- PRD：`docs/prd/knowledge/P8-knowledge-document-pagination.md`（状态：已确认，issue #78）
- Design：`docs/design/knowledge/P8知识文档分页Design.md`（状态：已确认，2026-08-15；
  用户已确认全部 6 项设计决策；文档经 docs 分支 PR #81 入库，合并前本工作包以
  `docs/design/` 为参考路径）
- 分支：`feat/p8-knowledge-document-pagination`（基于 `main`，2026-08-15）
- worktree：`D:/market-handsome/oper-mind-worktrees/P8-knowledge-document-pagination`
- 隔离清单：主仓库工作区有他人未提交改动（`AGENTS.md`/`CLAUDE.md`，属
  `chore/backend-guardrails` 工作包），不纳入本工作包、不暂存、不提交。

## 范围

### 只做

- 后端 cursor 分页（PRD 功能需求 1；AC1–AC7）：
  - `backend/src/knowledge/reader.py`：新增 `KnowledgeDocumentCursor { relative_path: str }` 与
    `list_documents_page(root, cursor, limit) -> (items, next_cursor)`：沿用 `collect_docs` 候选收集与
    相对路径确定性排序（隐藏/凭据路径排除）；跳过 `relative_name <= cursor.relative_path`；逐篇限长读取，
    跳过空/含 `sk-` 文档；收集至 `limit` 条即停；满 `limit` 时 `next_cursor = 最后一条 relative_name`，
    否则 `None`。`list_documents()` 保留（应用服务 search 空态判断与既有测试仍用）。AC2/AC6/AC7。
  - `backend/src/application/knowledge.py`：`KnowledgeReaderService.list_documents(cursor=None, limit=50)`
    返回 `(status, items, next_cursor)`；`not_configured` 不变；`empty` 仅当 cursor 为 None 且目录无文档；
    超尾页 `ok` + 空 items + `next_cursor=None`（AC3/AC4）。
  - `backend/src/api/v1/routes.py`：`GET /knowledge/documents` 增加 `cursor: str | None` 与
    `limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = KNOWLEDGE_DEFAULT_PAGE_SIZE`（默认 50）；
    非法 cursor → 400 `INVALID_CURSOR`（复用 `parse_page_cursor`）；**`CursorT` union 扩展
    `KnowledgeDocumentCursor` 并补 import**（arch-review P2）；响应增加 `page: CursorPage(next_cursor, has_more)`
    （`has_more = next_cursor is not None`）。AC1/AC5。
  - `backend/src/api/v1/schemas.py`：`KnowledgeListResponse` 增加 `page: CursorPage`（**接口契约扩展**）。
- 前端分页浏览（PRD 功能需求 2；AC8/AC9）：
  - `frontend/src/api/v1/client.ts`：`list_knowledge_documents(query?, options?)`（cursor/limit，
    对齐 `list_session_runs` 签名）；`queries.ts`：query key 携带 limit、`queryOptions` 支持 cursor 参数。
  - `frontend/src/features/knowledge/KnowledgePage.tsx`：列表改为 `useInfiniteQuery`
    （`initialPageParam: undefined`、`getNextPageParam` 读 `page.has_more` → `page.next_cursor`，
    对齐 WorkbenchPage 先例）；「加载更多」按钮（LoadMoreButton 模式），加载中/失败可重试；
    未配置/空态文案不变；检索与详情视图不动。
  - `frontend/src/test/handlers.ts`：`/knowledge/documents` handler 支持 `cursor`/`limit` 分页切片。
  - `frontend/src/features/knowledge/KnowledgePage.test.tsx`：分页交互用例 + 「翻页超出末尾不误显
    『知识库为空』空态文案」用例（arch-review P3）。
- 类型与测试：`generated.ts` 重新生成（提交前置步骤，不手改）；`test_knowledge_api.py` 分页用例
  （AC1–AC7）；`test_knowledge_service.py` 适配新签名（返回 3 元组）。
- 文档：`docs/workpack/P8-knowledge-document-pagination/{plan,review,evidence}.md`、
  `docs/workpack/README.md` 登记、`docs/接口清单.md` 第三大模块欠账表更新（分页欠账 → 已交付）。

### 明确不做

- 不新增索引/缓存层（仍现场 `rglob`，分页只约束返回体积与前端渲染量；目录规模优化另行评估）。
- 不动 `GET /knowledge/search` 与 `GET /knowledge/documents/{path}` 单篇读取契约。
- 不做上传/新建/编辑/删除；不新增持久化/迁移/凭据/Connector/外部连接。
- 不修改他人工作包文件（主仓库工作区 `AGENTS.md`/`CLAUDE.md` 及其它 P8 切片 worktree）。

## 切片拆分

- [ ] S1：后端分页——reader 分页函数 + 应用服务 + API 契约扩展（cursor/limit + `page` 字段 +
      `CursorT` union）+ `test_knowledge_api.py`（AC1–AC7）+ `test_knowledge_service.py` 适配。
- [ ] S2：前端分页浏览——generated.ts 重新生成 + client/queries + KnowledgePage useInfiniteQuery +
      加载更多 + MSW handler + 交互测试（AC8/AC9）。
- [ ] S3：全量回归与收尾——后端全量 pytest、前端 typecheck/test/build、`git diff --check`、
      敏感字面量门禁、`docs/接口清单.md` 更新、工作包证据表回写。覆盖 DoD 与 AC9。

## 改动面（文件级）

### 后端修改

- `backend/src/knowledge/reader.py`（`KnowledgeDocumentCursor` + `list_documents_page`）。
- `backend/src/application/knowledge.py`（`list_documents` 签名与返回变化）。
- `backend/src/api/v1/routes.py`（分页参数 + `page` 响应 + `CursorT` union 扩展）。**接口契约扩展。**
- `backend/src/api/v1/schemas.py`（`KnowledgeListResponse.page: CursorPage`）。**接口契约扩展。**

### 后端测试

- `backend/tests/test_knowledge_api.py`（分页用例：首页/翻页不重不漏/超尾页/未配置/非法参数/排序/排除）。
- `backend/tests/test_knowledge_service.py`（适配 `list_documents` 3 元组返回与分页行为）。

### 前端修改

- `frontend/src/api/v1/generated.ts`（`npm run generate:api` 重新生成，禁止手编）。
- `frontend/src/api/v1/client.ts`、`frontend/src/api/v1/queries.ts`（分页参数与查询封装）。
- `frontend/src/features/knowledge/KnowledgePage.tsx`（useInfiniteQuery + 加载更多）。
- `frontend/src/features/knowledge/KnowledgePage.test.tsx`（分页交互 + 超尾页空态用例）。
- `frontend/src/test/handlers.ts`（分页 handler）。
- `frontend/src/styles/knowledge-page.css`（加载更多按钮样式，如需）。

### 文档

- `docs/workpack/P8-knowledge-document-pagination/plan.md`（本文件）、`review.md`（dev-execute 回写）、
  `evidence.md`（dev-execute 回写）。
- `docs/workpack/README.md`：登记活跃工作包。
- `docs/接口清单.md`：第三大模块欠账表「文档列表分页」→ 已交付。
- `docs/design/knowledge/P8知识文档分页Design.md`：经 docs 分支 PR #81 入库（本工作包不重复提交；
  若 PR #81 未合并，随本工作包 PR 一并带上）。

## 验证方法

- 后端聚焦：从 `backend/` 执行 `..\.venv\Scripts\python.exe -m pytest tests/test_knowledge_api.py tests/test_knowledge_service.py -q`。
- 后端回归：从 `backend/` 执行 `..\.venv\Scripts\python.exe -m pytest tests -q`。
- 前端：从 `frontend/` 先 `npm install`，再 `npm run typecheck`、`npm run test`、`npm run build`。
- 生成类型：先在 `backend/` 起 `..\.venv\Scripts\python.exe -m uvicorn src.app:app --port 8000`，
  再在 `frontend/` 执行 `npm run generate:api`（提交前置步骤）。
- 门禁：`git diff --check`；检查 diff 无 DSN、密码、`sk-`、原始异常；只暂存本工作包文件；
  提交前 `git fetch origin main && git merge origin/main` 本地解冲突。
- 真实资源门禁：测试全部使用 `tmp_path` 确定性目录与 MSW mock，不连接任何外部资源。

## 提交计划

- S1：`feat: 知识文档列表分页——后端 cursor 分页（issue #78）`
- S2：`feat: 知识文档列表分页——前端分页浏览（issue #78）`
- S3：`test: 知识文档列表分页——回归与收尾（issue #78）`

提交前只暂存本工作包实际修改的文件，不使用 `git add .`。
