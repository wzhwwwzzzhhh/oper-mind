# P7-knowledge-page · 工作包计划

## 基线与确认

- PRD：`docs/prd/knowledge/P7-knowledge-page.md`（状态：已确认，issue #43）
- Design：`docs/design/knowledge/P7知识库页面Design.md`（状态：已获用户确认，2026-08-08）
- 分支：`feat/P7-knowledge-page`（基于 `main`，2026-08-08）
- worktree：`D:/market-handsome/oper-mind-worktrees/P7-knowledge-page`
- 隔离清单：主仓库工作区有他人未提交文件（`docs/design/monitor/P7服务监控概览页Design.md`、
  `docs/design/session/P7DB锁与连接池诊断Design.md`），属其他工作包，不纳入本工作包、不暂存、不提交。

## 范围

### 只做

- 共享 reader（`backend/src/knowledge/reader.py`）：把 `SearchKnowledgeTool` 确定性检索逻辑提取为模块级
  纯函数，保留全部既有常量与规则；`SearchKnowledgeTool` 重构为调用 reader，输出格式与 `audit_summary()`
  不变（AC10 回归锁定）。覆盖 PRD AC10。
- 知识库 REST API（3 个只读端点，挂载 `/api/v1`）：
  - `GET /knowledge/documents`：扁平文档清单（`title` + `relative_path`），按相对路径确定性排序；
    `not_configured`/`empty`/`ok` 状态。覆盖 AC1、AC2、AC3。
  - `GET /knowledge/search?query=&limit=`：复用 reader 确定性检索，返回匹配文档
    （`title`/`relative_path`/`snippet_count`/`title_hit`/`snippets`），相关度排序、条数受限 1–10 默认 5；
    无匹配 `no_match`；检索词校验（长度 ≤100、拒绝路径分隔符与控制字符、非纯空白）→ 422。
    覆盖 AC4。
  - `GET /knowledge/documents/{document_path:path}`：返回受管目录内 `.md` 正文（`desensitize()` 后）；
    越界/凭据/不存在 → 404 `KNOWLEDGE_DOCUMENT_NOT_FOUND`；目录空详情一律 404。覆盖 AC5、AC6、AC7。
  - 诚实状态：`status` 字段表达（`not_configured`/`empty`/`no_match`/`ok`）；超时 503 `KNOWLEDGE_TIMEOUT`。
  - 错误码 `KNOWLEDGE_TIMEOUT`/`KNOWLEDGE_DOCUMENT_NOT_FOUND` 注册进 `APPLICATION_ERROR_STATUS`。
  - `document_path` 校验：拒绝绝对路径/`..`/`.` 段/连续斜杠/反斜杠/控制字符 + resolve 根前缀校验 +
    URL 编码穿越测试；静态列表路由先于 path 路由注册，尾斜杠契约测试锁定。
- Application 服务（`backend/src/application/knowledge.py`）：`KnowledgeReaderService` 注入受管目录
  （`load_knowledge_settings()`），限时执行（3s，复用网关模式，实例级共享线程池），超时抛
  `KnowledgeTimeoutError`。覆盖 PRD 非功能「列表与详情接口限时」。
- 装配（`backend/src/api/v1/dependencies.py`）：`V1Services` 新增 `knowledge_service: KnowledgeReaderService | None`，
  `build_v1_services_for_runtime` 按配置装配；`routes.py` 新增 3 端点与 `_knowledge_service` 助手。
- API 契约：`schemas.py` 新增知识库资源/响应契约（`ApiV1Model` + `extra="forbid"`）、`ResponseMeta` 回显；
  `resources.py` 资源映射（`relative_name` → `relative_path` 显式统一）。
- 前端「文档知识库」页面（`/knowledge`）：
  - `GlobalNav` `docs` 启用（`go('docs')` → `/knowledge`，active 前缀判断），`chat` 项同步排除 `/knowledge`；
  - `App.tsx` 新增 `/knowledge` 单路由，`ProductShell` `is_operations` 扩展 `|| is_knowledge`；
  - `ServiceContextNav` 新增 knowledge 分支（数据来源标注「受管知识目录 · 只读」）；
  - `KnowledgePage.tsx`：列表/检索/详情三视图（页内 `view` 状态 + `?doc=` 深度链接），详情 `<pre>` 纯文本；
  - 诚实空态：`not_configured`→「知识库未配置」、`empty`→「暂无文档」、`no_match`→「无匹配文档」；
    请求失败 → 失败空态 + 重试（React Query `isError`/`refetch`）。覆盖 AC8、AC9。
- API 客户端：`client.ts` 新增 3 方法与类型别名，`queries.ts` 新增 query keys/`queryOptions`；
  `generated.ts` 由后端 8000 OpenAPI 重新生成（提交前置步骤，不手改）。
- 测试：新增 `backend/tests/test_knowledge_api.py`、`frontend/src/features/knowledge/KnowledgePage.test.tsx`；
  `backend/tests/test_knowledge_tool.py` 回归（P6 行为不变锁定）；MSW handlers 补知识库端点。
- 工作包文档：`docs/workpack/P7-knowledge-page/{plan,review,evidence}.md`、`docs/workpack/README.md` 登记。

### 明确不做

- 不做向量库 / Embedding / RAG / 语义检索（后续阶段，需单独 Design）。
- 不做文档上传 / 编辑 / 删除 / 管理；不做知识目录配置管理界面。
- 不接入外部知识源（网站、Confluence、工单系统等）；不发起任何网络访问。
- 不展示受管目录外文件/路径；不授予任意文件系统访问；不展示非 Markdown / 二进制 / 隐藏文件。
- 不将凭据文件（`.env`、`config.local.yaml`、`*.local.yaml`、密钥文件、含 `sk-` 内容）纳入列表/检索/详情。
- 不新增持久化 / 数据库表 / 迁移 / 凭据；不修改 `data/mock_db.py`、`data/scenarios.py` 与 S1–S4 评测路径。
- 前端详情不做 Markdown 渲染（纯文本），不引入 Markdown 依赖。
- 不修改 P6 Tool 对外行为；不修改他人工作包文件（monitor/session P7 Design）。

## 切片拆分

- [ ] S1：共享 reader 提取 + `SearchKnowledgeTool` 重构（行为不变）+ 3 个只读端点 + schemas/装配 +
      `test_knowledge_api.py`（AC1–AC7）+ P6 Tool 回归（AC10 部分）。
- [ ] S2：前端 `/knowledge` 页面（路由/导航/三视图/诚实空态/失败重试）+ API 客户端与生成类型 +
      `KnowledgePage.test.tsx`（AC8、AC9）+ 前端回归。
- [ ] S3：全量回归（后端全量 pytest、前端 typecheck/test/build、`git diff --check`、敏感字面量门禁、
      S1–S4 mock 评测路径不变、P6 工具行为不变）。覆盖 AC10 与 DoD。

## 改动面（文件级）

### 后端新增

- `backend/src/knowledge/__init__.py`、`backend/src/knowledge/reader.py`：共享确定性检索 reader。
- `backend/src/application/knowledge.py`：`KnowledgeReaderService` + `KnowledgeTimeoutError`。
- `backend/tests/test_knowledge_api.py`：列表/检索/详情/空态/路径逃逸/凭据排除/脱敏/限时/契约测试。

### 后端修改

- `backend/src/tools/knowledge_tools.py`：改用共享 reader，输出格式与 `audit_summary()` 不变。
- `backend/src/api/v1/schemas.py`：知识库资源/响应契约。
- `backend/src/api/v1/routes.py`：3 个只读端点 + `_knowledge_service` 助手 + 错误码注册。
- `backend/src/api/v1/resources.py`：知识库资源映射。
- `backend/src/api/v1/dependencies.py`：`V1Services.knowledge_service` 字段与装配。
- `config/config.example.yaml`：补 `knowledge.directory` 注释示例（P3 级，可选）。
- `backend/tests/test_knowledge_tool.py`：仅回归，不改断言（行为不变锁定）。

### 前端新增

- `frontend/src/features/knowledge/KnowledgePage.tsx`（含样式）。
- `frontend/src/features/knowledge/KnowledgePage.test.tsx`。

### 前端修改

- `frontend/src/features/shell/GlobalNav.tsx`（`docs` 启用 + `chat` 排除 `/knowledge`）。
- `frontend/src/app/App.tsx`（`/knowledge` 路由 + `ProductShell` `is_operations` 扩展）。
- `frontend/src/features/shell/ServiceContextNav.tsx`（knowledge 分支）。
- `frontend/src/api/v1/client.ts`、`frontend/src/api/v1/queries.ts`（新方法与查询封装）。
- `frontend/src/api/v1/generated.ts`（`npm run generate:api` 重新生成，不手改）。
- `frontend/src/test/handlers.ts`（知识库端点 MSW handlers）。

### 文档

- `docs/design/knowledge/P7知识库页面Design.md`（已确认，随本工作包提交）。
- `docs/workpack/P7-knowledge-page/plan.md`、`review.md`（dev-execute 回写）、`evidence.md`（dev-execute 回写）。
- `docs/workpack/README.md`：登记活跃工作包。

## 验证方法

- 后端聚焦：从 `backend/` 执行 `..\.venv\Scripts\python.exe -m pytest tests/test_knowledge_api.py tests/test_knowledge_tool.py -q`。
- 后端回归：从 `backend/` 执行 `..\.venv\Scripts\python.exe -m pytest tests -q`。
- 前端：从 `frontend/` 先执行 `npm install`，再 `npm run typecheck`、`npm run test`、`npm run build`。
- 生成类型：先在 `backend/` 起 `..\.venv\Scripts\python.exe -m uvicorn src.app:app --port 8000`，
  再在 `frontend/` 执行 `npm run generate:api`（提交前置步骤）。
- 门禁：`git diff --check`；检查 diff 无 DSN、密码、`sk-`、原始异常；不暂存他人工作包文件与无关文件。
- 真实资源门禁：测试全部使用 `tmp_path` 确定性目录与 MSW mock，不连接任何外部资源。

## 提交计划

- S1：`feat: 知识库只读 REST API——文档列表/检索/详情（共享 reader）`
- S2：`feat: 文档知识库页面——列表/检索/详情与诚实空态`
- S3：`test: 知识库页面与检索回归收尾`

提交前只暂存本工作包实际修改的文件，不使用 `git add .`。
