# P8 会话导出——会话记录留存与分享 · Design

> 状态：已确认
> 更新：2026-08-14
> 关联：`docs/prd/session/P8-session-export.md`（已确认，issue #76）、
> `docs/产品定义.md`（§2.1 会话主入口、§5 安全与诚实性）、`docs/开发规范.md`（§4 凭据隔离、§5 安全投影）、
> `docs/架构与开发路径.md`（一条主脊、只读投影）、
> `docs/接口清单.md`（第一大模块缺表：会话导出 ❌ 欠账）、
> `docs/design/session/P8会话管理Design.md`（已确认 #64，明确排除"会话导出，另行排期"）、
> `backend/src/api/v1/routes.py`（`GET /sessions/{id}/messages` / `GET /sessions/{id}/runs` 先例）、
> `backend/src/application/audit_service.py`（只读聚合服务先例）、
> `backend/src/api/v1/resources.py`（`_safe_run_error` 错误白名单、`result_resource` 结果投影）、
> `backend/src/core/tool_gateway.py`（`desensitize` 兜底脱敏）、
> `backend/src/domain/records.py`、`backend/src/infrastructure/persistence/repositories.py`、
> `frontend/src/features/workbench/WorkbenchPage.tsx`（会话工作区）、
> `frontend/src/api/v1/client.ts`（`request_json` 请求基建）。

## 1. 目标与范围

### 一句话目标

用户能把一段会话（标题、消息时间线、各 Run 结论摘要）**一键导出为只含安全投影的 Markdown 文档**，
用于留存、分享与复盘；导出只读、确定性、可复现，失败时诚实降级，不新增任何暴露面。

### 做什么

1. **后端导出接口**：新增 `GET /sessions/{session_id}/export`，按会话聚合安全摘要，返回
   `text/markdown` 文档；会话不存在 → 404；无可导出内容（无消息无 Run）→ 明确空态文档；读取失败 → 503。
2. **前端导出入口**：会话页工具栏新增「导出」按钮，触发下载；导出中展示进行态；失败展示错误与重试；
   空会话提示「无可导出内容」。

### 明确不做

- 不做"导出原始证据包"：不导出工具原始输出、SQL、日志原文、Trace 内部事件、Prompt/CoT、异常堆栈或凭据。
- 不做批量导出 / 全局导出 / 定时导出 / 导出订阅 / 邮件发送。
- 不做导出后编辑 / 回传（只读快照，单向输出）。
- 不做分页导出（大会话按上限截断并注明，见决策 3）。JSON 变体是否提供见待确认决策 1，
  **确认前不实现**。
- 不改变既有会话 / 消息 / Run 接口契约与留痕；不新增持久化、无迁移。

### 与「一条主脊，能力即插件」硬规则的关系（显式声明）

`docs/架构与开发路径.md` 硬规则 1 禁止「新端点、新流程、新独立脚本/页面」。本 Design 新增 1 个公开端点
（`GET /sessions/{session_id}/export`）——与 P8 会话管理 Design（已确认 #64）、P8 审计检索（#62）同型：
这是 `docs/接口清单.md` 已登记欠账的**只读聚合投影**，不是新能力：

- 导出是对既有 sessions / messages / diagnosis_runs / diagnosis_results 四张表的**只读聚合**
  （消息与 Run 各经新增的有界尾部查询 + 既有 `get_by_run_id`，输出复用既有资源投影纪律），
  不触碰工具网关、凭据、审批/执行白名单，不触发任何 Tool / Connector / 模型调用；
- 输出字段全部来自既有公开投影字段（`MessageResource`、`DiagnosisRunResource`、
  `DiagnosisResultResource` 已外发字段的子集），**不新增暴露面**；
- 本工作包走完整「接口清单欠账 → PRD → Design → Review → 用户确认 → workpack」路径
  （`docs/开发规范.md` §7.1/7.2 门禁），不误入完善类轻流程。

## 2. 设计决策

### 2.1 导出接口（后端）

- **路由**：`GET /sessions/{session_id}/export`（放在 `routes.py` 消息列表路由附近）。
  - 成功：`200`，`Content-Type: text/markdown; charset=utf-8`，
    `Content-Disposition: attachment; filename="opermind-session-<session_id>.md"`，响应体为 Markdown 文本。
  - 会话不存在：`404 SESSION_NOT_FOUND`（复用既有 `SessionNotFoundError` → `raise_application_error`）。
  - 读取失败 / 超时：`503 EXPORT_UNAVAILABLE`（见下），不返回半截文档。
- **应用服务**：新增 `backend/src/application/session_export.py`（对齐 `audit_service.py` 只读服务先例）：
  - `SessionExportApplicationService(session_factory)`，方法
    `render_markdown(session_id: UUID) -> SessionExportDocument`；
    `SessionExportDocument` 为 Pydantic 记录：`markdown: str` + `empty: bool`（空态标记，供测试与前端语义）。
  - 加载顺序（单会话聚合，数量级与 `GET /sessions/{id}/messages` + `GET /sessions/{id}/runs` 相当）：
    1. `SqlAlchemySessionRepository.get_by_id` → 不存在抛 `SessionNotFoundError`；
    2. **新增** `SqlAlchemyMessageRepository.list_latest_by_session(session_id, limit)`
       ——有界单表查询：取该会话**最近 `MESSAGE_EXPORT_CAP = 500` 条消息，按创建时间正序**
       （子查询倒序取尾部再正序重排；不改变既有 `list_by_session` 的 asc 契约，也不复用其语义）；
    3. **新增** `SqlAlchemyDiagnosisRunRepository.list_latest_by_session(session_id, limit)`
       ——取该会话**最近 `RUN_EXPORT_CAP = 200` 个 Run，按创建时间正序**（同上尾部取法）；
    4. 每个 Run `SqlAlchemyDiagnosisResultRepository.get_by_run_id`（成功 Run 必有结果）。
  - 截断注明：任一上限触发时，文档头部注明「仅导出最近 500 条消息 / 仅导出最近 200 次调查」。
  - 错误语义：聚合读取抛 `SQLAlchemyError` 等持久化异常 → 捕获后转
    `SessionExportUnavailableError`（新增于 `application/errors.py`，`code="EXPORT_UNAVAILABLE"`，
    路由经 `APPLICATION_ERROR_STATUS` 映射 503）；**禁止裸 except**，只捕获声明的异常类型。
- **文档构建（纯函数，可独立单测）**：`build_session_export_markdown(session, messages, runs_with_results) -> str`
  （`runs_with_results` 为 `list[tuple[DiagnosisRunData, DiagnosisResultData | None]]`，跨层用显式类型）：
  - 文档结构（确定性，无导出时间戳等不稳定字段）：
    ```markdown
    # <会话标题>

    > 会话导出 · OperMind 安全摘要（仅含脱敏投影，不含原始证据）
    > 创建时间：<created_at ISO 8601 UTC>
    > 状态：<active | archived>
    > 消息 <N> 条 · 调查 <M> 次（如截断：· 仅导出最近 500 条消息 / 仅导出最近 200 次调查）

    ## 对话时间线

    ### 用户
    > <created_at>
    <正文>

    ### OperMind · 普通对话
    > <created_at>
    <正文>

    ### 系统提醒
    > <created_at>
    <正文>

    ## 调查摘要（共 M 次）

    ### 第 N 次调查（<创建时间>）
    **问题**：<该 Run 输入消息正文，经脱敏>
    **状态**：<queued | running | succeeded | failed | cancelled>
    **目标服务**：<service_id 或 "未关联服务">
    **严重度**：<severity>（成功且有结果时）
    **置信度**：<confidence>（成功且有结果时）
    **结论**：<summary>（成功且有结果时）
    **报告**：<report_markdown>（成功且有结果且存在时）
    **证据摘要**：
    - [<source_type>] <title>：<summary>
    （每 Run 上限 50 条，超出注明"…等 N 条证据"）
    **错误**：<经 _safe_run_error 白名单的安全错误>（failed 时）
    ```
  - 角色映射：`user → 用户`、`assistant → OperMind · 普通对话`（run_id 为空的消息）或
    `OperMind · 调查`（run_id 非空的消息不单独成块，见下）、`system → 系统提醒`。
  - **消息与 Run 的关联口径**：时间线只渲染消息；Run 摘要统一收进「调查摘要」区（按创建时间正序），
    Run 的「问题」取自其 `input_message_id` 对应消息正文（找不到输入消息时省略该行，诚实呈现）。
    这样导出内容完全由既有数据确定，不与前端投影逻辑耦合。
  - 空态：`messages` 与 `runs_with_results` 均为空 → 文档只含头部 + `## 无可导出内容` 一行说明
    （`empty=True`），不伪造内容（AC4）。
- **确定性**：文档只含稳定字段（会话标题/创建时间/状态、消息时间线、Run 摘要）；不含导出时间、
  随机标识符或会话内不稳定的字段；同一会话重复导出字节一致（AC7）。

### 2.2 前端导出入口

- **client.ts**：新增内部 `request_text(...)`（与 `request_json` 同构，`Accept: text/markdown`，
  非 2xx 时解析 JSON 错误体抛 `ApiClientError`，沿用 request_id 头约定）与公开方法
  `export_session_markdown(session_id, options?) -> Promise<{ text: string; filename: string }>`
  （文件名取自 `Content-Disposition`，取不到时回退 `opermind-session-<id>.md`）。
- **WorkbenchPage.tsx（SessionWorkspace）**：会话区顶部（调查目标服务行同区）新增工具栏行：
  - 「导出」按钮（复用 `UiButton`）；点击后：
    - 若已加载数据明确为空（消息与 Run 两列表第一页均 `items.length === 0 && !has_more`）→
      提示「该会话无可导出内容」，不发请求（诚实空态，AC4）；
    - 否则发起 `export_session_markdown`：进行中按钮禁用 + 文案「导出中…」；
      成功 → `URL.createObjectURL(new Blob([text], { type: 'text/markdown' }))` + 临时 `<a download>`
      触发下载 + revoke，并提示「已导出」；
      失败 → `ApiErrorNotice` 展示错误 + 「重试」按钮（AC8）。
  - 导出是一次性下载动作，**不走 react-query 缓存**（`useMutation` 即可，不在 `queries.ts` 加 query key）。
- **生成契约**：`frontend/src/api/v1/generated.ts` 经 `npm run generate:api` 重新生成（禁止手编）。

### 2.3 接口契约汇总

| 方法 | 路径 | 说明 | 状态码 |
|---|---|---|---|
| GET | `/sessions/{session_id}/export` | 会话安全摘要 Markdown 文档（只读聚合投影） | 200 / 404 / 503 |

- 兼容性：既有会话 / 消息 / Run 接口契约不变；无新增参数。
- 错误体沿用既有 `ApiV1Error` 安全错误体格式（`code` + `message`），不泄露内部上下文。

### 2.4 安全与脱敏

- **纯只读**：聚合查询不触发任何 Tool / Connector / 外部连接 / 模型调用；不涉及 Agent 装配与工具网关。
- **投影白名单**：导出字段全部来自既有公开资源投影——消息正文按 `MessageResource` 口径、
  Run 按 `DiagnosisRunResource` + `DiagnosisResultResource` 口径的子集；错误经 `_safe_run_error`
  白名单（失败 Run 只显示固定安全文案）；证据仅取 `source_type / source_name / title / summary`
  四个字段（不含 `locator` / `attributes`，更精简，见待确认决策 2）。
- **兜底脱敏**：所有进入文档的文本字段（标题、消息正文、summary、报告、证据标题/摘要）统一过
  `desensitize()`（`sk-` 密钥、`password=/token=` 键值、`scheme://user:pass@` 凭据段）；**叠加导出专用
  连接串兜底规则**（覆盖 `desensitize()` 未命中的无凭据完整 DSN，如 `postgresql://prod-db:5432/app`）：
  `session_export.py` 内置窄 scheme 白名单（`postgres` / `postgresql` / `mysql` / `redis` /
  `mongodb` / `mssql` / `jdbc:` 前缀），命中即整段替换为 `[已脱敏:连接串]`——作为最后一道防线（AC6）。
  **不改动共享 `desensitize()` 的既有规则**（避免影响知识检索等其它输出）。
- **不返回半截文档**：聚合或构建任一步失败 → 503，不落任何响应体（AC5）。
- **参数校验**：路径参数为 UUID，FastAPI 自动 422；无查询参数，无新增配置项。

## 3. 文件改动面

### 后端（修改 + 新增）

- `backend/src/application/session_export.py`（**新增**）：`SessionExportApplicationService`、
  `build_session_export_markdown` 纯函数、`SessionExportDocument`、导出上限常量、
  导出专用连接串兜底脱敏规则（窄 scheme 白名单）。
- `backend/src/application/errors.py`（修改）：新增 `SessionExportUnavailableError`
  （`EXPORT_UNAVAILABLE`，路由映射 503）。
- `backend/src/infrastructure/persistence/repositories.py`（修改）：新增
  `SqlAlchemyMessageRepository.list_latest_by_session` 与
  `SqlAlchemyDiagnosisRunRepository.list_latest_by_session`（有界尾部查询，倒序取尾部再正序重排；
  既有 `list_by_session` 契约不变）。
- `backend/src/api/v1/routes.py`（修改）：新增 `GET /sessions/{session_id}/export` 路由
  （复用 `_load_session` 语义与 `raise_application_error`）。
- 后端测试（新增）：`tests/test_session_export.py`（AC1–AC7 服务端面 + 确定性 + 空态 + 503）。

### 前端（修改）

- `frontend/src/api/v1/client.ts`（修改）：`request_text` + `export_session_markdown`。
- `frontend/src/api/v1/generated.ts`（重新生成，禁止手编）。
- `frontend/src/features/workbench/WorkbenchPage.tsx`（修改）：导出工具栏（按钮/进行态/失败重试/空态提示/下载）。
- `frontend/src/test/handlers.ts`（修改）：`GET /sessions/:session_id/export` 的 MSW mock。
- 前端测试（新增）：`frontend/src/features/workbench/session-export.test.tsx`（AC8：下载/失败/空态）。

### 文档

- `docs/接口清单.md`（修改）：缺表「会话导出」标记 ✅ 已交付，补 `GET /sessions/{id}/export` 行。
- `docs/路线图.md`（修改）：当前阶段登记本工作包（issue #76，进行中；对齐 #64 登记先例）。
- `docs/workpack/README.md` + `docs/workpack/P8-session-export/`（dev-plan 阶段登记与产出）。

### 明确无改动

- 无数据库迁移（复用既有四张表）；无配置项 / 环境变量新增；无 Connector / 凭据 / 权限 / 审批 /
  执行能力变化；SSE、Run 执行链路、知识库、模型域、监控域不动；`data/`、`demo/` 不动。

## 4. 切片与验证（指引，不写死）

建议拆 **2 片**（后端 1 片 + 前端 1 片，各自独立可验收）：

- **S1：导出接口（后端）**。`session_export.py` + 错误类 + 路由 + 后端测试。
  验收语义：AC1（标题与消息时间线）、AC2（Run 结论摘要）、AC3（404）、AC4（空态文档）、
  AC5（读取失败 503）、AC6（无敏感内容）、AC7（重复导出一致）。
- **S2：导出入口（前端）**。client 下载方法与工作台工具栏 + 交互测试。
  验收语义：AC8（下载/失败重试/空态提示）、AC9（前端回归 typecheck/test/build）。

涉及门禁项：**新增公开 API**（`GET /sessions/{session_id}/export`）⇒ 本 Design 经
arch-review PASS + 用户确认后方可开发；无迁移、无 Connector、无凭据、无权限/审批/执行能力扩大。

## 5. 风险、回滚与门禁

| 风险 | 缓解 |
|---|---|
| 大会话聚合慢 / 文档过大 | 单会话聚合（与既有两列表查询同数量级）+ 消息 500 / Run 200 上限，超限截断并在文档注明，不做无界扫描 |
| 消息正文含敏感字面量（`sk-`、DSN） | 全字段过 `desensitize()` 兜底 + 导出专用连接串规则（窄 scheme 白名单，覆盖无凭据完整 DSN）；导出字段为既有投影子集，不新增暴露面 |
| 文档确定性漂移（时间字段/随机值） | 统一 UTC ISO 8601；不含导出时间戳与随机标识符；重复导出字节一致 |
| 消息正文含 Markdown 结构干扰 | 正文原样置于既定标题之下（用户自建内容，属安全投影；仅影响排版不影响安全） |
| 生成契约与后端漂移 | `npm run generate:api` 重新生成，禁止手编 |
| 会话页工具栏改造回归 | 前端 `typecheck`/`test`/`build` 全量回归 |

- 回滚：移除 `GET /sessions/{session_id}/export` 路由与前端导出按钮即回退（无迁移、无配置、无 Connector）。
- 门禁项清单：新增公开 API ⇒ Design → Review → 用户确认；未新增迁移/凭据/权限/审批执行能力。

## 6. 待用户确认的设计决策

1. **格式**：v1 仅 Markdown，不做 JSON 变体（人可读、可分享，JSON 后续按需补）——是否确认？
   （PRD 开放问题 1 推荐方案）
2. **证据摘要粒度**：导出中证据仅取 `source_type / source_name / title / summary` 四字段、
   每 Run 上限 50 条（比 `GET /runs/{id}` 更精简，不含 `locator` / `attributes`）——是否确认？
   （PRD 开放问题 2 推荐方案）
3. **大会话限制**：消息上限 500 条、Run 上限 200 条，超限取最近 N 条并在文档头部注明截断
   （不做分页导出）——是否确认？（PRD 开放问题 3 推荐方案）
4. **导出范围**：当前导出全部既有消息（消息编辑/删除尚未落地，无软删除机制；该 PRD 落地后
   按既有投影排除已删除消息，本 Design 不预埋列）——是否确认？（PRD 开放问题 4 推荐方案）
5. **确定性口径**：导出文档不含「导出时间」等不稳定字段，仅含会话创建时间等稳定字段，
   保证重复导出字节一致（AC7）——是否确认？
