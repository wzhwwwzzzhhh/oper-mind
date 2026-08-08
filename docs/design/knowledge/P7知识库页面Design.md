# P7 文档知识库页面——知识目录浏览与确定性检索 · Design

> 状态：已确认
> 更新：2026-08-08
> 关联：`docs/prd/knowledge/P7-knowledge-page.md`（issue #43）、`docs/prd/knowledge/P6-knowledge-retrieval.md`、
> `docs/产品定义.md` §2.2/§6、`docs/路线图.md` 第二阶段 P7 批次、`docs/开发规范.md` §1/§4/§6、
> `docs/design/knowledge/P6知识检索Design.md`、`backend/src/tools/knowledge_tools.py`、
> `backend/src/api/v1/routes.py`/`schemas.py`/`resources.py`/`dependencies.py`、`backend/src/config.py`、
> `frontend/src/features/shell/GlobalNav.tsx`、`frontend/src/app/App.tsx`、`frontend/src/api/v1/client.ts`/`queries.ts`。

## 1. 目标与范围

把 P6 已交付的「目录内 Markdown 确定性检索」能力**页面化**：新增只读知识库 REST API（文档列表 / 检索 /
文档详情），并在全局导航「文档知识库」落地 `/knowledge` 页面，提供列表浏览、页面内检索与详情查看。
全程诚实空态（未配置/无文档/无匹配/失败）与安全边界（只读受管目录、参数校验防路径逃逸、凭据文件排除、
正文脱敏兜底）沿 P6 不变；不做 RAG/向量、不做文档写入与管理、不接入外部知识源、不改 mock 数据源。

### 做什么

- 新增知识库 REST API（只读，挂载 `/api/v1`）：
  - `GET /api/v1/knowledge/documents`：受管目录内 Markdown 文档清单（相对路径 + 标题），扁平排序；
  - `GET /api/v1/knowledge/search?query=&limit=`：复用 P6 确定性检索（标题/正文关键词匹配），
    返回匹配文档（标题 + 相对路径 + 命中片段），相关度排序、条数受限；
  - `GET /api/v1/knowledge/documents/{document_path:path}`：按受管目录内相对路径返回文档正文（脱敏后）。
- 新增前端「文档知识库」页面（`/knowledge`）：文档列表视图 / 页面内检索 + 结果列表 / 文档详情视图；
  空态诚实、失败可重试、数据来源标注「受管知识目录 · 只读」。
- 复用 P6 检索能力：把 `SearchKnowledgeTool` 的确定性检索逻辑提取为**共享 reader 模块**，Tool 与 API
  共用同一套实现，避免两套检索逻辑；P6 Tool 对外行为（文本输出与 `audit_summary()`）保持不变。

### 明确不做

- 不做向量数据库 / Embedding / RAG / 语义检索（后续阶段，需单独 Design）。
- 不做文档上传 / 编辑 / 删除 / 管理（只读浏览，写能力不在本 PRD）。
- 不接入外部知识源（网站、Confluence、工单系统等）；不发起任何网络访问。
- 不展示受管目录外文件/路径；不授予任意文件系统访问；不展示非 Markdown / 二进制 / 隐藏文件。
- 不将凭据文件（`.env`、`config.local.yaml`、`*.local.yaml`、密钥文件、含 `sk-` 内容）纳入列表/检索/详情。
- 不做知识目录配置管理界面（目录仍由 `OPERMIND_KNOWLEDGE_DIR` / YAML `knowledge.directory` 提供）。
- 不新增持久化 / 数据库表 / 迁移 / 凭据；不修改 `data/mock_db.py`、`data/scenarios.py` 与 S1–S4 评测路径。
- 前端详情不做 Markdown 渲染（见 §2.4 决策），本切片以纯文本渲染正文。

## 2. 设计决策

### 2.1 共享 reader：单一检索实现（P6 Tool 与 API 共用）

新增 `backend/src/knowledge/reader.py`，把 `SearchKnowledgeTool` 中确定性检索的纯函数逻辑
（目录收集、标题提取、正文命中定位、片段截取、凭据/隐藏/越界排除、相关度排序、限长读取）提取为模块级函数，
并保留全部既有常量（`_SNIPPET_CONTEXT=60`、`_MAX_SNIPPETS=2`、`_MAX_DOC_CHARS=256KB`、
`_QUERY_MAX_LEN=100`、`_DEFAULT_LIMIT=5`、`_MAX_LIMIT=10`、非法字符与凭据后缀规则）。

reader 提供三类只读能力：

| 函数 | 返回 | 说明 |
|---|---|---|
| `list_documents(root) -> list[KnowledgeDocumentMeta]` | `title` + `relative_name`（posix 相对路径） | 扁平、按相对路径确定性排序；不含凭据/隐藏文件 |
| `search_documents(root, query, limit) -> list[KnowledgeSearchHit]` | `title`/`relative_name`/`snippet_count`/`title_hit`/`snippets` | 与 P6 排序/片段规则完全一致 |
| `read_document(root, relative_name) -> str \| None` | 脱敏后正文 | 仅限受管目录内 `.md`；越界/凭据/不存在返回 `None` |

- `SearchKnowledgeTool` 重构为调用 reader，保留原有多行文本输出格式与 `audit_summary()`，**对外行为不变**
  （AC10 回归锁定）。
- **`sk-` 内容排除时机与 P6 完全一致**：P6 现状是候选收集阶段不做内容级排除，仅在**匹配时**跳过含 `sk-`
  的文档（`_match_docs` 内 `"sk-" in text`）。reader 必须保持该时机——「目录只含含 `sk-` 文档」时
  检索返回「无匹配」而非「无文档」；列表与详情按不可访问处理。新增该边界回归用例锁定 AC10。
- API 侧 application 服务复用同一 reader，输出结构化结果；检索词校验沿用 P6（长度 ≤100、拒绝路径分隔符
  与控制字符、非纯空白），拒绝输入由 API 返回 `422 VALIDATION_ERROR`（API 标准，不再复用 Tool 的文本拒绝）。
- `desensitize()`（`backend/src/core/tool_gateway.py`）作为脱敏兜底：详情正文、检索片段、标题与检索词回显
  在返回前统一过 `desensitize()`，与网关规则一致（`sk-*`、`password=...`、连接串凭据段全部替换为占位符）。
  `desensitize()` 是正则最佳努力（非 `sk-`/`password=`/连接串模式不覆盖），与 P6/网关同一局限性，如实标注。
- **跨层数据契约**：reader 返回 `KnowledgeDocumentMeta` / `KnowledgeSearchHit` / 详情为 **Pydantic 模型**
  （非裸 dict，对齐「禁止隐式跨层字典协议」）；API 响应 schema 继承 `ApiV1Model`（`extra="forbid"`）。
  reader 的 `relative_name` 与 API schema 的 `relative_path` 命名在资源映射层显式统一（值同为 posix 相对路径）。

### 2.2 知识库 REST API 契约（只读，`/api/v1`）

沿用 v1 契约模式：`ApiV1Model`（`extra="forbid"` + UTC Z 序列化）、`ResponseMeta` +
`X-Request-Id` 回显；诚实状态用响应体 `status` 字段表达（对齐 `MonitorHistoryResponse` 先例），
非配置/数据状态**不抛异常**。

| 端点 | 请求 | 成功响应（200） | 错误 |
|---|---|---|---|
| `GET /knowledge/documents` | 无 | `KnowledgeListResponse { status, items:[{title, relative_path}], meta }` | 超时 503 |
| `GET /knowledge/search` | `query`（1–100，拒绝路径分隔符/控制字符）、`limit`（1–10，默认 5） | `KnowledgeSearchResponse { status, query, items:[{title, relative_path, snippet_count, title_hit, snippets[]}], meta }` | 校验失败 422；超时 503 |
| `GET /knowledge/documents/{document_path:path}` | URL 路径 = 受管目录内相对 posix 路径 | `KnowledgeDocumentResponse { status, document:{title, relative_path, content}, meta }` | 不存在/越界 404；超时 503 |

`status` 取值（诚实降级，均不伪造）：

| 场景 | 列表 | 检索 | 详情 |
|---|---|---|---|
| 目录未配置或不存在 | `not_configured`（items 空） | `not_configured`（items 空） | `not_configured` |
| 目录内无 Markdown 文档 | `empty`（items 空） | `empty`（items 空） | — |
| 无匹配 | — | `no_match`（items 空） | — |
| 正常 | `ok` | `ok` | `ok` |
| 超时 | 503 `KNOWLEDGE_TIMEOUT` | 503 `KNOWLEDGE_TIMEOUT` | 503 `KNOWLEDGE_TIMEOUT` |

- `document_path` 参数校验（防路径逃逸，AC5）：拒绝绝对路径（以 `/` 开头）、`..`/`.` 段、连续斜杠、
  **反斜杠 `\`**（Windows 分隔符）与控制字符；URL 编码穿越（`%2e%2e%2f`、`%5c`、`%2f` 等）在
  FastAPI 解参后同样命中上述段级/字符级校验，并叠加 resolve 根前缀校验兜底；越界统一按「不存在」处理
  （404，不暴露目录结构）；凭据/隐藏文件或含 `sk-` 内容的文档同样 404。
- `relative_path` 统一使用 posix 分隔（`as_posix()`），与 P6 reader 相对文件名一致；响应不包含绝对路径。
- **错误码定稿**：503 超时 → code `KNOWLEDGE_TIMEOUT`；详情不存在/越界/凭据 → 404 code `KNOWLEDGE_DOCUMENT_NOT_FOUND`；
  两者注册进 `APPLICATION_ERROR_STATUS`（routes.py）或直接以 `ApiV1Error` 抛安全包络。
- **路由注册顺序与尾斜杠契约**：静态路由 `GET /knowledge/documents` 先于
  `GET /knowledge/documents/{document_path:path}` 注册；`/knowledge/documents/`（尾斜杠）行为由契约测试锁定。

### 2.3 Application 服务与装配

- 新增 `backend/src/application/knowledge.py`：`KnowledgeReaderService`，构造注入受管目录
  （`load_knowledge_settings().directory`，未配置为 `None`），暴露 `list_documents()` / `search(query, limit)` /
  `get_document(relative_path)`，内部调用 reader 并做限时（复用网关 3s 超时模式，超时抛 `KnowledgeTimeoutError`）。
  **执行器生命周期**：服务持有单一共享 `ThreadPoolExecutor`（实例级，如 `ToolGateway` 的 `max_workers=1`
  线程池），不每请求新建避免线程泄漏；配合 256KB/文档限长保证超时可期；服务可 `shutdown()` 释放。
- `backend/src/api/v1/dependencies.py`：`V1Services` 新增字段 `knowledge_service: KnowledgeReaderService | None`，
  在 `build_v1_services_for_runtime` 中按 `load_knowledge_settings()` 装配（默认 `None`，向后兼容既有测试）；
  路由用 `_knowledge_service(services)` 助手读取，`None` 即未配置状态。
- 路由与 schema：`routes.py` 新增 3 个只读端点；`schemas.py` 新增知识库资源/响应契约；
  `resources.py` 新增资源映射（或路由内直接映射）。

### 2.4 前端「文档知识库」页面

- **导航与路由**：`GlobalNav` `docs` 项从死占位改为可用——`go('docs')` → `/knowledge`，`active` 判断
  `/knowledge` 前缀；**`chat` 项的 active 条件同步排除 `/knowledge`**（避免 `/knowledge` 页面上 `chat` 与
  `docs` 同时高亮）；`App.tsx` 在 `ProductShell` 内新增 `/knowledge` 单路由；`ProductShell` 的
  `is_operations` 扩展为 `is_services || is_models || is_knowledge`（运维模式壳），
  `ServiceContextNav` 新增 knowledge 分支（简单上下文导航 + 数据来源标注，沿用 models 分支模式）。
- **页面结构**：`frontend/src/features/knowledge/KnowledgePage.tsx` 单页面内部管理
  `view: 'list' | 'detail'` 状态（列表/检索结果/详情三视图），详情通过点击列表或检索结果项进入，
  提供返回列表按钮；支持 `?doc=<url-encoded relative path>` 深度链接（避免 react-router 路径参数含斜杠问题）。
- **视图**：
  - 列表视图：加载 `GET /knowledge/documents`，展示标题 + 相对路径，点击进入详情；
  - 检索框：输入检索词调用 `GET /knowledge/search`，展示结果项（标题 + 命中片段），点击进入详情；
  - 详情视图：按选中文档调用详情接口，`<pre>` 纯文本渲染正文；
  - 数据来源标注「受管知识目录 · 只读」。
- **诚实空态与失败恢复（AC1/AC2/AC4/AC9）**：`not_configured` →「知识库未配置」；`empty` →「暂无文档」；
  `no_match` →「无匹配文档」；网络/请求失败 → 失败空态 + 重试按钮（React Query `useQuery` 的
  `isError`/`refetch`），不崩溃、不伪造。
- **API 客户端**：`client.ts` 新增 `list_knowledge_documents` / `search_knowledge` / `get_knowledge_document`
  方法与类型别名；`queries.ts` 新增 query keys 与 `queryOptions`；`generated.ts` 由后端 OpenAPI 重新生成
  （**作为提交前置步骤：先在 8000 起后端跑 `npm run generate:api` 再提交**，否则前端 typecheck/build 缺文件，
  不手改）。

### 2.5 安全与脱敏

- 只读受管目录：所有路径解析 `resolve()` 后以受管根为前缀，越界即拒绝；符号链接解析越界即跳过（沿用 P6）。
- 凭据文件排除：`.env`、`*.local.yaml`、`.key/.pem/.secret`、隐藏文件不进列表/检索/详情；
  内容含 `sk-` 的文档视为不可访问（列表/检索排除、详情 404）。
- 脱敏兜底：详情正文、检索片段、标题统一过 `desensitize()`；凭据/DSN 不进响应、日志、Trace。
- 不泄漏：不返回绝对路径、目录结构、受管目录外内容；超时/内部异常统一 503/500 中性文案。

### 2.6 诚实降级汇总

| 场景 | API | 前端 |
|---|---|---|
| 目录未配置/不存在 | `not_configured` | 「知识库未配置」空态 |
| 目录空 | 列表/检索 `empty`；详情一律 404 | 「暂无文档」 |
| 无匹配 | `no_match` | 「无匹配文档」 |
| 请求失败/超时 | 503（超时） | 失败空态 + 重试 |
| 详情不存在/越界 | 404 | 「文档不存在」+ 返回列表 |

## 3. 文件改动面

### 后端

- 新增 `backend/src/knowledge/__init__.py`、`backend/src/knowledge/reader.py`（共享确定性检索 reader）。
- 新增 `backend/src/application/knowledge.py`（`KnowledgeReaderService` + `KnowledgeTimeoutError`）。
- 修改 `backend/src/tools/knowledge_tools.py`（`SearchKnowledgeTool` 改用 reader，输出格式与 `audit_summary()` 不变）。
- 修改 `backend/src/api/v1/schemas.py`（知识库资源/响应契约）。
- 修改 `backend/src/api/v1/routes.py`（3 个只读端点 + `_knowledge_service` 助手）。
- 修改 `backend/src/api/v1/resources.py`（知识库资源映射，如需）。
- 修改 `backend/src/api/v1/dependencies.py`（`V1Services.knowledge_service` 字段与装配）。
- 修改 `config/config.example.yaml`（补 `knowledge.directory` 注释示例，可选，P3 级）。
- 测试：新增 `backend/tests/test_knowledge_api.py`；`backend/tests/test_knowledge_tool.py` 回归（行为不变锁定）。

### 前端

- 新增 `frontend/src/features/knowledge/KnowledgePage.tsx` 及其样式（沿用现有 CSS 模式）。
- 新增 `frontend/src/features/knowledge/KnowledgePage.test.tsx`（交互测试：列表/检索/详情/空态/失败重试）。
- 修改 `frontend/src/features/shell/GlobalNav.tsx`（`docs` 启用 + `/knowledge` active）。
- 修改 `frontend/src/app/App.tsx`（`/knowledge` 路由 + `ProductShell` `is_operations` 扩展）。
- 修改 `frontend/src/features/shell/ServiceContextNav.tsx`（knowledge 分支）。
- 修改 `frontend/src/api/v1/client.ts`、`frontend/src/api/v1/queries.ts`（新方法与查询封装）。
- 修改 `frontend/src/api/v1/generated.ts`（由 `npm run generate:api` 重新生成，不手改）。
- 修改 `frontend/src/test/handlers.ts`（知识库端点 MSW handlers）。

### 文档

- `docs/design/knowledge/P7知识库页面Design.md`（本文件，arch-review PASS + 用户确认后置「已确认」）。
- 实施时 `docs/workpack/P7-knowledge-page/{plan,review,evidence}.md`、`docs/workpack/README.md` 登记。

## 4. 切片与验证（指引）

建议拆 3 片，每片独立可验收：

- **S1 后端 reader 与 API**：共享 reader 提取 + `SearchKnowledgeTool` 重构（行为不变）+ 3 个只读端点 +
  schemas/装配 + `test_knowledge_api.py`（AC1–AC7）+ P6 Tool 回归。涉及门禁项：新增公开 API。
- **S2 前端页面**：`/knowledge` 路由 + 列表/检索/详情三视图 + 诚实空态/失败重试 + 导航启用 +
  `KnowledgePage.test.tsx`（AC8/AC9）+ API 客户端与生成类型。
- **S3 全量回归**：AC10 与 DoD（后端全量 pytest、前端 typecheck/test/build、`git diff --check`、
  敏感字面量门禁、S1–S4 mock 评测路径不变、P6 工具行为不变）。

## 5. 风险、回滚与门禁

- 技术风险：`{document_path:path}` 通配路径与 `/knowledge/documents` 静态路由的匹配顺序（先注册静态列表
  路由再注册 path 路由，尾斜杠行为契约测试锁定）；`document_path` 需严格防逃逸（解析根前缀 + 段级拒绝
  `..`/`.`/绝对路径/反斜杠/控制字符 + URL 编码穿越测试），配测试锁定；`generated.ts` 重新生成需后端在
  8000 提供 OpenAPI（列为提交前置步骤，缺失会导致前端 typecheck/build 红）。
- 回滚：本切片无数据库迁移、无写能力、无凭据新增；回滚即移除新增 3 个端点与前端页面/导航分支，
  既有会话/服务/监控链路不受影响；P6 Tool 行为不变（有回归锁定）。
- 门禁项：**新增公开 REST API + 前端页面**，须 Design → arch-review → 用户确认后才能进入 dev-plan；
  涉及前端契约（generated.ts 重新生成）与导航改动，无迁移、无凭据、无写操作。
- Review 必须确认：API 契约与 `status` 取值、错误码（`KNOWLEDGE_TIMEOUT`/`KNOWLEDGE_DOCUMENT_NOT_FOUND`）、
  `document_path` 校验规则（段级拒绝 + 反斜杠 + URL 编码穿越 + resolve 根前缀）、路由注册顺序与尾斜杠契约、
  共享 reader 重构不改变 P6 行为（含 `sk-` 排除时机一致）、`KnowledgeReaderService` 执行器生命周期、
  前端详情纯文本渲染、`is_operations` 壳扩展与 knowledge 导航分支、`generated.ts` 重新生成前置步骤。

## 6. 待用户确认的设计决策

1. 是否确认知识库 REST API 采用 3 个只读端点（列表 / 检索 / 详情）与上述契约，诚实状态用响应体
   `status` 字段表达（`not_configured`/`empty`/`no_match`/`ok`，超时 503），不抛异常、不伪造？
2. 是否确认把 P6 `SearchKnowledgeTool` 的确定性检索逻辑提取为共享 `backend/src/knowledge/reader.py`，
   由 Tool 与 API 共用（统一实现避免两套检索逻辑），并保证 P6 Tool 对外行为不变？
3. 是否确认文档详情扩展 P6「全文不暴露前端」边界为「受管目录内 `.md` 正文可读」（脱敏兜底、
   凭据文件排除），详情以**纯文本**渲染（不引入 Markdown 渲染依赖，降低 XSS/依赖面）？
4. 是否确认文档列表采用**扁平列表**（按相对路径确定性排序，`title + relative_path`），不按目录层级
   做树形展示？
5. 是否确认 `document_path` 采用 URL 路径参数（`{document_path:path}`，相对 posix 路径），
   参数校验防路径逃逸（绝对路径/`..`/`.`/连续斜杠/控制字符拒绝，解析根前缀校验，越界统一 404）？
6. 是否确认前端 `/knowledge` 单路由 + 页内 `view` 状态切换三视图（列表/检索/详情），详情经
   `?doc=` 深度链接；全局导航 `docs` 启用，`ProductShell` `is_operations` 扩展并新增 knowledge 导航分支？
7. 是否确认本 Design 经 arch-review PASS 且用户确认后，将 P7 PRD 状态保持「已确认」并直接进入 workpack 实现？
