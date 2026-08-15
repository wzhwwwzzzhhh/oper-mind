# P8 知识文档列表分页——目录浏览容量化 · Design

> 状态：已确认
> 更新：2026-08-15
> 关联：`docs/prd/knowledge/P8-knowledge-document-pagination.md`（issue #78，status 已确认）、
> `docs/design/knowledge/P7知识库页面Design.md`、`docs/prd/knowledge/P7-knowledge-page.md`（issue #43）、
> `docs/prd/knowledge/P6-knowledge-retrieval.md`、`docs/接口清单.md`（第三大模块缺表）、
> `docs/产品定义.md` §6（知识库边界）、`docs/开发规范.md` §1/§7、`docs/架构与开发路径.md`、
> `backend/src/knowledge/reader.py`、`backend/src/application/knowledge.py`、
> `backend/src/api/v1/routes.py`/`schemas.py`/`cursors.py`、
> `frontend/src/features/knowledge/KnowledgePage.tsx`、`frontend/src/features/workbench/WorkbenchPage.tsx`（useInfiniteQuery 先例）、
> `frontend/src/api/v1/client.ts`/`queries.ts`、`frontend/src/test/handlers.ts`。

## 1. 目标与范围

一句话目标：让 `GET /knowledge/documents` 支持 **cursor 分页**，目录规模大时按页返回，
单页响应体积与前端渲染量可控；未配置/空目录行为不变，既有调用不带参数仍可用。

### 做什么（映射 PRD 功能需求）

- `GET /knowledge/documents` 增加 `cursor`/`limit` 分页参数，按相对路径确定性排序分页返回
  （PRD 功能需求 1；AC1/AC2/AC6）。
- 响应包含分页信息（`items` + 下一页 cursor / `has_more`），空页与末尾语义明确（AC3）。
- 分页参数非法（limit 超上限、cursor 非法）返回明确错误（AC5）。
- 前端文档知识库目录页适配分页浏览（「加载更多」按钮），加载中/空态/失败态诚实展示（AC8）。
- 未配置/空目录返回不变（`not_configured` + 空列表，诚实降级）（AC4）；分页沿用既有排除逻辑
  （隐藏路径/凭据文件/含 `sk-` 文档不出现）（AC7）。

### 明确不做（对齐 PRD「不做什么」）

- 不新增索引/缓存层：仍每次现场 `rglob` 受管目录，分页只约束返回体积与前端渲染量；
  目录规模优化（缓存/前缀分桶等）另行评估，`docs/接口清单.md` 已注明现状代价。
- 不动 `GET /knowledge/search`（全文检索语义不变）；不改变 `GET /knowledge/documents/{path}` 单篇读取契约。
- 不做上传/新建/编辑/删除（只读浏览边界）。
- 不新增持久化、数据库表、迁移、凭据或 Connector/外部连接。

## 2. 设计决策

### 2.1 分页风格：cursor 键集分页（复用既有 cursor 基础设施）

- 与 `GET /runs`、`/sessions`、`/messages`、`/service-center/services/{id}/activities`、`/runs/{id}/events`
  等全部既有 v1 分页先例一致：**opaque cursor（base64url JSON）+ `limit`**，不引入 offset/limit 新风格。
- **排序键**：相对路径（posix，`as_posix()`，与 `collect_docs` 现状排序一致）升序。
  cursor 承载上一页最后一条的 `relative_path`；下一页取**严格大于** cursor 的条目。
- 新增领域 cursor 模型 `KnowledgeDocumentCursor { relative_path: str }`，定义在
  `backend/src/knowledge/reader.py`——知识域的全部领域模型（`KnowledgeDocumentMeta`/`KnowledgeSearchHit`）
  均聚簇于 reader.py，无独立 domain 模块，故 cursor 模型随领域模型同置（与既有 domain cursor 聚簇
  `src/domain/records.py` 的惯例相比是有意偏离，理由如上，arch-review 已确认不阻断）；
  编解码直接复用 `src/api/v1/cursors.py` 的 `encode_cursor`/`decode_cursor`（对任何 Pydantic 模型泛型可用，
  该模块**无需改动**）。
- **`routes.py` 的 `CursorT` TypeVar（`src/api/v1/routes.py` L162-171）是硬编码 7 类型约束 union**，
  新增 cursor 类型后必须把 `KnowledgeDocumentCursor` 加进该 union 并补 import（否则 `parse_page_cursor`
  类型标注报错）；`parse_page_cursor` 本身无需改动（arch-review P2，实施必做）。
- **cursor 只用于与候选路径做字典序比较，绝不用于文件访问**——不存在经 cursor 的路径穿越面；
  非法 cursor 由 `decode_cursor` 的模型校验拒绝。
- 稳定性语义（如实标注）：翻页期间目录内容不变时，页与页之间不重不漏（确定性，AC6）；
  目录被写入时，光标之前的插入不影响已返回页，光标之后的插入可能出现在后续页（键集分页固有语义）。

### 2.2 页大小与非法参数

- **默认 50、上限 100**（沿用 PRD 建议；上限与全局 `MAX_PAGE_SIZE = 100` 一致）。
  `routes.py` 定义 `KNOWLEDGE_DEFAULT_PAGE_SIZE = 50`，上限复用全局 `MAX_PAGE_SIZE`。
- `limit` 超出 `[1, 100]` → FastAPI `Query(ge=1, le=100)` 自动 **422**（与全部既有分页端点一致，AC5）。
- cursor 非法 → **400 `INVALID_CURSOR`**（复用 `parse_page_cursor` 既有先例；PRD 示例写 422，
  本 Design 定为与全库分页端点一致的 400，见 §6 待确认项 4）。

### 2.3 后端实现（文件级架构）

- `backend/src/knowledge/reader.py` 新增：
  - `KnowledgeDocumentCursor(BaseModel)`：字段 `relative_path: str`；
  - `list_documents_page(root: Path, cursor: KnowledgeDocumentCursor | None, limit: int)`
    → `tuple[list[KnowledgeDocumentMeta], KnowledgeDocumentCursor | None]`：
    - 沿用 `collect_docs` 的候选收集与确定性排序（含隐藏/凭据路径排除，AC7）；
    - 跳过 `relative_name <= cursor.relative_path` 的条目（cursor 为 None 时全量）；
    - 逐篇限长读取（256KB），跳过空文档与含 `sk-` 明文的文档（沿用 `list_documents` 既有过滤时机）；
    - 收集至 `limit` 条即停；返回 `(items, next_cursor)`：本页满 `limit` 时
      `next_cursor = 最后一条 relative_name`，否则 `None`。
  - `list_documents()` 保留不删（应用服务 `search` 的空态判断与既有测试仍使用）。
  - 成本说明：分页只约束**返回体积与前端渲染**；遍历/排序仍为现场全量（与现状一致），
    数千篇目录下首版接受现状成本 + 页上限（PRD 开放问题 3，不引入缓存）。
- `backend/src/application/knowledge.py`：`KnowledgeReaderService.list_documents(cursor, limit)`
  返回 `(status, items, next_cursor)`，限时执行不变；`status` 语义：
  - `not_configured`：目录未配置/不存在（不变）；
  - `empty`：**仅当 cursor 为 None 且目录无任何文档**（首页即空，不变）；
  - `ok`：正常页；翻页超出末尾 → `status=ok` + `items=[]` + `next_cursor=None`
    （「无更多」由 `has_more=false` 明确表达，不抛错，AC3）。
- `backend/src/api/v1/routes.py`：`GET /knowledge/documents` 增加
  `cursor: str | None` 与 `limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = KNOWLEDGE_DEFAULT_PAGE_SIZE`；
  响应增加 `page: CursorPage(next_cursor=..., has_more=...)`（`has_more = next_cursor is not None`），
  与既有分页端点返回结构完全一致。
- `backend/src/api/v1/schemas.py`：`KnowledgeListResponse` 增加
  `page: CursorPage`（`CursorPage{next_cursor, has_more}` 已存在，复用）。
  ——**属既有公开接口契约扩展**（新增字段），前端 `generated.ts` 需重新生成。

### 2.4 前端目录分页适配

- `frontend/src/api/v1/client.ts`：`list_knowledge_documents` 增加 query 参数
  （`cursor?: string, limit?: number`），签名对齐既有 `list_session_runs(session_id, query, options)` 先例；
  `queries.ts` 的 `list_knowledge_documents_query` 同步携带 limit 与 cursor 查询键。
- `frontend/src/features/knowledge/KnowledgePage.tsx`：列表加载从 `useQuery` 改为 `useInfiniteQuery`
  （对齐 `WorkbenchPage` 的 runs/messages 先例）：
  - `initialPageParam: undefined`；`getNextPageParam` 读 `page.has_more` → `page.next_cursor`（否则 undefined）；
  - 列表渲染 `pages` 展平（键集分页保证不重不漏，无需去重）；
  - 「加载更多」按钮（`LoadMoreButton` 模式），`isFetchingNextPage` 时展示加载中，失败可重试；
  - 未配置/空态/失败态文案与现状一致（`not_configured` →「知识库未配置」、`empty` →「暂无文档」）；
  - 页面内检索与文档详情视图**不动**。
- `frontend/src/test/handlers.ts`：`/knowledge/documents` MSW handler 支持 `cursor`/`limit` 参数分页切片。

### 2.5 安全与脱敏

- 分页沿用既有排除逻辑：隐藏路径/凭据文件（`.env`、`*.local.yaml`、密钥文件）/含 `sk-` 明文文档
  不进入任何页（AC7）；不暴露绝对路径与目录外路径。
- cursor 不参与文件访问，仅作排序键比较；非法 cursor 400、limit 超限 422，不泄露目录结构。
- 不新增凭据、不落库、不进日志；响应结构与命名与既有分页先例一致（`page.next_cursor`/`page.has_more`）。

### 2.6 兼容性

- 无分页参数调用 = 首页（AC1，与现状返回语义一致：status + items + 新增 page 字段）；
- `status` 取值不变（`not_configured`/`empty`/`ok`）；单篇读取与搜索契约不变（PRD 边界）。

## 3. 文件改动面

### 后端

- 修改 `backend/src/knowledge/reader.py`（新增 `KnowledgeDocumentCursor` + `list_documents_page`）。
- 修改 `backend/src/application/knowledge.py`（`list_documents` 增加 cursor/limit 参数与 next_cursor 返回）。
- 修改 `backend/src/api/v1/routes.py`（列表端点分页参数 + `page` 响应字段 + **`CursorT` union 扩展
  `KnowledgeDocumentCursor` 与对应 import**，arch-review P2）。
- 修改 `backend/src/api/v1/schemas.py`（`KnowledgeListResponse` 增加 `page: CursorPage`）。**接口契约扩展。**
- 修改 `backend/tests/test_knowledge_api.py`（AC1–AC7 分页用例）、`backend/tests/test_knowledge_service.py`（如适用）。

### 前端

- 重新生成 `frontend/src/api/v1/generated.ts`（后端 OpenAPI 变更后 `npm run generate:api`，禁止手编）。
- 修改 `frontend/src/api/v1/client.ts`、`frontend/src/api/v1/queries.ts`（分页参数与查询封装）。
- 修改 `frontend/src/features/knowledge/KnowledgePage.tsx`（useInfiniteQuery + 加载更多）。
- 修改 `frontend/src/features/knowledge/KnowledgePage.test.tsx`（分页交互用例，AC8）。
- 修改 `frontend/src/test/handlers.ts`（分页 handler）。
- 修改 `frontend/src/styles/knowledge-page.css`（加载更多按钮样式，如需）。

### 文档（实施时）

- `docs/design/knowledge/P8知识文档分页Design.md`（本文件，arch-review PASS + 用户确认后置「已确认」）。
- `docs/workpack/P8-knowledge-document-pagination/{plan,review,evidence}.md`、`docs/workpack/README.md` 登记。
- `docs/接口清单.md` 第三大模块欠账表同步（「文档列表分页」欠账 → 已交付）。

### 无功能改动

- 无数据库迁移、无持久化、无凭据、无 Connector/外部连接、无写操作；`GET /knowledge/search` 与单篇读取契约不变。

## 4. 切片与验证（指引）

建议拆 2 片，每片独立可验收：

- **S1 后端分页**：reader 分页函数 + 应用服务 + API 契约扩展 + `test_knowledge_api.py`（AC1–AC7）。
  门禁项：公开 API 契约扩展（Design → Review → 用户确认，本流程即为此）。
- **S2 前端分页浏览**：generated.ts 重新生成 + client/queries + KnowledgePage useInfiniteQuery + 加载更多
  交互测试 + MSW handler（AC8/AC9）；补一条「翻页超出末尾不误显『知识库为空』空态文案」的交互用例锁定
  超尾页语义（arch-review P3）。

涉及门禁项汇总：公开 API 契约扩展（新增 `page` 字段与分页参数）；无迁移/凭据/写操作/破坏性改动。

## 5. 风险、回滚与门禁

- 技术风险：cursor 字典序比较仅对 posix 相对路径有效——`collect_docs` 已统一 `as_posix()`，无分隔符歧义；
  分页稳定性依赖排序确定性（现状已按相对路径排序，不变）；`generated.ts` 重新生成需后端在 8000 提供
  OpenAPI（列为提交前置步骤）；`page` 字段为响应新增字段，旧前端忽略即可、新前端依赖之。
- 回滚：无迁移、无写能力；回滚即移除分页参数与 `page` 字段并恢复前端一次性加载，既有会话/服务/知识链路不受影响。
- 门禁项：**公开 API 契约扩展**，须 Design → arch-review PASS → 用户确认后才能进入 dev-plan；
  前端契约（generated.ts 重新生成）与页面行为改动，无迁移、无凭据。

## 6. 待用户确认的设计决策

1. 是否确认分页采用 **cursor 键集分页**（按相对路径 posix 升序，opaque base64url cursor，
   与 `GET /runs` 等全部既有分页先例一致），而非 offset/limit？
2. 是否确认页大小 **默认 50 / 上限 100**（沿用 PRD 建议，上限与全局 `MAX_PAGE_SIZE` 一致）？
3. 是否确认响应新增 `page: CursorPage { next_cursor, has_more }` 字段（既有分页端点同构），
   且 `status` 语义保持：`empty` 仅当目录无任何文档；翻页超出末尾返回 `ok` + 空 items +
   `has_more=false`（「无更多」语义，不抛错）？
4. 是否确认非法 cursor 返回 **400 `INVALID_CURSOR`**（与全库分页端点一致，而非 PRD 示例的 422）？
   limit 超上限/非法由 FastAPI 校验返回 422。
5. 是否确认前端采用「**加载更多**」按钮翻页（非滚动加载），加载中/空态/失败态诚实展示，
   检索与详情视图不动？
6. 是否确认本 Design 经 arch-review PASS 且用户确认后，状态置「已确认」并放行 dev-plan？
