# P8 会话管理——全局 Run 列表与会话搜索 · Design

> 状态：已确认
> 更新：2026-08-12
> 关联：`docs/prd/session/P8-session-management.md`（已确认，issue #64）、
> `docs/产品定义.md`（§2.1 会话主入口、§5 安全边界）、`docs/开发规范.md`（§2/§5/§6/§7.2）、
> `docs/架构与开发路径.md`（一条主脊、能力即插件、只读投影）、
> `docs/接口清单.md`（第一大模块缺表：无全局 Run 列表 / 无会话搜索）、
> `docs/完善清单.md`（P1-12 Ctrl K 假提示）、
> `docs/design/session/P8会话工作台闭环Design.md`（已确认 #54，前序 PRD 明确排除本 PRD 内容）、
> `backend/src/api/v1/routes.py`、`backend/src/domain/records.py`、
> `backend/src/infrastructure/persistence/repositories.py`、
> `backend/src/infrastructure/persistence/service_repositories.py`（`_activity_select` 跨表 join 先例）、
> `backend/src/api/v1/resources.py`（`_safe_run_error` 错误白名单）、
> `frontend/src/features/shell/Sidebar.tsx`、`frontend/src/features/approvals/ApprovalsPage.tsx`（列表页先例）、
> `frontend/src/app/App.tsx`、`frontend/src/api/v1/queries.ts`、`frontend/src/api/v1/client.ts`。

## 1. 目标与范围

### 一句话目标

补上会话主入口的两个管理视角缺口：跨会话跨服务的「最近所有调查」列表（`GET /runs`），
以及按标题搜索会话的真实入口（`GET /sessions?q=` + 侧栏搜索框 + `Ctrl K`），
让管理视角不再靠逐会话翻页，`Ctrl K` 假提示变成真实能力。

### 做什么

1. **全局 Run 列表**：新增 `GET /runs`（跨会话跨服务，cursor 分页，status / service_id 过滤，
   Run 安全摘要：id / 状态 / 发起时间 / 会话 id 与标题 / 关联服务 / 错误摘要）。
2. **会话搜索**：`GET /sessions` 增加可选 `q` 参数（按标题字面关键词匹配，
   与既有 cursor/limit/status 正交组合，兼容扩展）。
3. **前端适配**：会话侧栏「最近会话」区新增搜索框（服务端搜索）；
   `Ctrl K` 全局键盘监听聚焦搜索框（真实可用，替代 P1-12 假提示）；
   「最近调查」入口与列表页（`/workbench/runs`），点击行进入既有 Run 详情。

### 明确不做

- 不做消息编辑/删除、重跑/重新生成、会话导出（接口清单欠账，另行排期）。
- 不改变既有 `GET /sessions` / `GET /sessions/{id}/runs` / `GET /services/{id}/activities`
  的既有契约与行为（`q` 是兼容扩展，无 `q` 时行为与现在完全一致）。
- 不做跨会话的消息全文搜索（只搜会话标题，不搜消息内容）。
- 不暴露证据原文、工具输出、CoT/Prompt、凭据/DSN/`sk-`；不显示原始错误文本。
- 不做命令面板（新建会话/搜索/跳转合一）；首版 `Ctrl K` 只聚焦搜索框。
- 不做 Run 列表的二次排序选项（固定按发起时间倒序，与既有 cursor 固定排序契约一致）。

### 与「一条主脊，能力即插件」硬规则的关系（显式声明）

`docs/架构与开发路径.md` 硬规则 1 禁止「新端点、新流程、新独立脚本/页面」。本 Design 新增
1 个公开端点（`GET /runs`）与 1 个兼容参数（`GET /sessions?q=`）——与 P8 会话工作台闭环
Design（已确认 #54）同型：这是 `docs/接口清单.md` 已登记欠账的**只读检索接线**，不是新能力：

- `GET /runs` 是对既有 sessions / runs 两表的**只读投影**（复用既有 `DiagnosisRunCursor`
  分页 + 会话标题 join，参考 `SqlAlchemyServiceActivityRepository._activity_select` 先例），
  不触碰工具网关、凭据、审批/执行白名单；
- `q` 参数是既有 `list_page` 的兼容扩展，不引入新流程、不改变既有契约行为。

两条均不涉及 Agent / Tool / Connector 装配，纯库内只读查询。

## 2. 设计决策

### 2.1 全局 Run 列表（后端）

- **游标复用**：直接复用既有 `DiagnosisRunCursor`（`created_at` + `id` 倒序）与
  `cursors.py` 既有编解码，**不新增游标类型**（与 `GET /sessions/{id}/runs` 同排序口径，
  PRD 开放问题 3 推荐方案）。
- **领域记录**：新增 `GlobalRunData`（放 `domain/records.py`）：
  `id / session_id / session_title / service_id / status / created_at / error_code / error_message`。
  字段严格对齐 PRD 功能需求 1 的摘要集（run id / 状态 / 发起时间 / 会话 id 与标题 /
  关联服务 / 错误摘要）；`error_*` 为内部原始值，由资源层白名单映射后才外发。
- **Repository**：`SqlAlchemyDiagnosisRunRepository` 新增
  `list_page(cursor, limit, status, service_id) -> RepositoryPage[GlobalRunData, DiagnosisRunCursor]`：
  - `DiagnosisRunRecord INNER JOIN SessionRecord` 取会话标题（Run 必有会话，FK 保证）；
  - 可选过滤：`status`（`RunStatus` 精确匹配）、`service_id`
    （按 **Run 自身 `service_id`** 精确匹配，见待确认决策 4；不存在值自然得空列表，AC3）；
  - 不做会话状态过滤——归档会话的历史调查仍可见（历史视角，见待确认决策 5）；
  - 复用 `_validate_limit` / `_page` 既有分页基建，`limit+1` 判定 `has_more`。
- **路由**：新增 `GET /runs`：`cursor` / `limit`（默认 20，`le=MAX_PAGE_SIZE`）/
  `status: RunStatus | None`（FastAPI 自动校验，非法 422）/ `service_id: str | None`
  （`Query(max_length=64)`）。返回
  `GlobalRunListResponse { items: [GlobalRunSummaryResource], page: CursorPage, meta }`，
  空列表返回空 `items` + `has_more=false`（诚实空态）。
- **资源映射**：新增 `global_run_summary_resource`（放 `resources.py`）：
  `id / status / created_at / session_id / session_title / service_id / error`；
  `error` 仅当 `status == failed` 时经 `_safe_run_error` 白名单映射
  （与既有 Run 详情同口径，绝不透传未经审查的错误文本，AC4）。
- **列表不 join result / proposal**：PRD 摘要字段集最小，详情仍走既有 `GET /runs/{run_id}`。

### 2.2 会话搜索（后端）

- **Repository**：`SqlAlchemySessionRepository.list_page(cursor, limit, status, q)` 增加可选
  `q: str | None`：按标题做**字面关键词匹配**（LIKE，转义 `%`/`_` 通配符，用户输入按字面
  处理）；与既有 `cursor` / `limit` / `status` 正交组合；无 `q` 时行为与既有契约完全一致（AC6）。
- **参数校验**：路由层 `q` 用 `Query(max_length=100)` + 显式控制字符检查
  （拒绝 `ord(c) < 0x20` 与 `0x7f`）；strip 后为空串/纯空白 → 422 明确错误
  （对齐知识检索 `min_length=1` + strip 先例，避免「空搜索=全部列表」歧义）→
  非法一律 422 与明确错误信息（AC7）。
- **响应**：与既有 `SessionListResponse` 结构完全一致（AC5：匹配会话列表，
  复用既有分页/脱敏纪律）；无匹配返回空列表。
- **搜索范围口径**：`q` 与既有 `status` 过滤独立组合——侧栏默认 `status=active` 的
  最近会话，搜索时同样只搜 active 会话；后端不隐含任何状态口径。

### 2.3 前端：侧栏搜索 + Ctrl K + 最近调查

- **侧栏搜索框**（`Sidebar.tsx`）：「最近会话」区上方新增搜索输入框
  （placeholder 含「Ctrl K」提示，`aria-label="搜索会话"`）；输入 → 300ms debounce →
  `list_sessions_query({ q, limit: 20, status: 'active' })` 服务端搜索，结果替换默认最近
  会话列表；无匹配展示诚实空态「无匹配会话」；搜索请求失败如实提示
  「会话搜索暂不可用」；清空输入（Esc 或清空按钮）恢复默认最近会话列表。
- **Ctrl K**（真实键盘监听，AC8）：document 级 `keydown` 监听，仅在 workbench 域生效；
  `Ctrl+K` → `preventDefault()` + `stopPropagation()`（阻止浏览器默认地址栏搜索），
  聚焦侧栏搜索框并全选已有文本；`Esc` 清空搜索。替代 `完善清单.md` P1-12 假提示。
- **「最近调查」入口**（AC9）：`Sidebar` 底部在「待审批」入口旁新增同级
  「最近调查」入口，导航 `/workbench/runs`（与已确认 #54 的「待审批」入口同位置先例）。
- **最近调查页**（新增 `frontend/src/features/runs/RunsPage.tsx`）：
  - 状态过滤标签（全部 / 排队中 / 运行中 / 成功 / 失败 / 已取消）+ 服务下拉过滤
    （复用既有 `list_services`，选项「全部服务」+ 各服务）；
  - cursor 分页（沿用 `fetch_all_pages` 既有模式）；
  - 行展示：会话标题 / 状态 / 发起时间 / 关联服务 / 失败摘要；空列表诚实空态
    「还没有调查」；
  - 点击行 → 既有 `/workbench/sessions/:session_id/runs/:run_id` Run 详情。
- **接线**：`client.ts` 增加 `list_runs`；`queries.ts` 增加 query key 与 query；
  `list_sessions_query` 透传 `q`；`App.tsx` 注册 `/workbench/runs` 路由。

### 2.4 接口契约汇总

| 方法 | 路径 | 说明 | 状态码 |
|---|---|---|---|
| GET | `/runs` | 全局 Run 安全摘要，cursor + status + service_id 过滤 | 200 / 422 |
| GET | `/sessions?q=` | 会话搜索（兼容扩展，无 `q` 行为不变） | 200 / 422 |

- 兼容性：既有 `GET /sessions` / `GET /sessions/{id}/runs` / `GET /services/{id}/activities`
  契约不变；`GET /runs` 与既有 `/runs/{run_id}` 路由并存无冲突（路径形状不同）。
- 生成契约：`frontend/src/api/v1/generated.ts` 经 `npm run generate:api` 重新生成，
  禁止手工编辑。

### 2.5 安全与脱敏

- **纯只读**：两个能力均为库内查询，不触发任何 Tool / Connector / 外部连接 / 模型调用；
  不涉及 Agent 装配与工具网关。
- **摘要白名单**：`GlobalRunSummaryResource` 仅含 §2.1 字段；错误经 `_safe_run_error`
  白名单；不含证据原文、工具输出、CoT/Prompt、凭据/DSN/`sk-`（AC4）。
  会话标题与既有会话列表/服务活动列表同口径（用户自建标题）。
- **参数校验**：`limit` 上限 100、`status` Literal、`service_id` 长度、`q` 长度与
  控制字符 → 非法 422 明确错误（AC7）。
- **诚实降级**：无匹配/空列表 → 诚实空态；搜索不可用（请求失败）→ 如实提示，不伪造结果。

## 3. 文件改动面

### 后端（修改）

- `backend/src/domain/records.py`：新增 `GlobalRunData`。
- `backend/src/infrastructure/persistence/repositories.py`：
  `SqlAlchemyDiagnosisRunRepository.list_page`（跨会话 + join 会话标题 + 双过滤）、
  `SqlAlchemySessionRepository.list_page` 增加 `q` 过滤。
- `backend/src/api/v1/routes.py`：新增 `GET /runs`；`GET /sessions` 增加 `q` 参数校验与透传。
- `backend/src/api/v1/schemas.py`：新增 `GlobalRunSummaryResource`、`GlobalRunListResponse`。
- `backend/src/api/v1/resources.py`：新增 `global_run_summary_resource`（复用 `_safe_run_error`）。
- 后端测试（新增）：`test_runs_list.py`（AC1–AC4 服务端面）、`test_session_search.py`
  （AC5–AC7）；回归：既有 `test_api.py` / `test_p2_api_v1.py`。

### 前端（修改 + 新增）

- `frontend/src/api/v1/generated.ts`（重新生成，禁止手编）。
- `frontend/src/api/v1/client.ts`（修改）：`list_runs` 方法；`list_sessions` 透传 `q`。
- `frontend/src/api/v1/queries.ts`（修改）：`runs_list` query key / query；`sessions` key 含 `q`。
- `frontend/src/features/runs/RunsPage.tsx`（**新增**）：最近调查页。
- `frontend/src/features/shell/Sidebar.tsx`（修改）：搜索框 + Ctrl K + 最近调查入口。
- `frontend/src/app/App.tsx`（修改）：`/workbench/runs` 路由。
- 前端测试：侧栏搜索交互（debounce/空态/恢复）、Ctrl K 聚焦、RunsPage 列表/过滤/空态/跳转。

### 文档

- `docs/接口清单.md`（修改）：缺表「全局 Run 列表」「会话搜索」两行标记为已交付，
  补 `GET /runs` 行与 `GET /sessions?q=` 参数说明。
- `docs/完善清单.md`（修改）：P1-12 标记 ✅（实现并端到端复验后回写，附验证方式）。
- `docs/路线图.md`（修改）：当前阶段登记本工作包（issue #64，进行中；
  对齐 #54 工作包登记先例）。

### 明确无改动

- 无数据库迁移（复用 sessions / runs 既有表）；无配置项/环境变量新增；无 Connector /
  凭据 / 权限 / 审批 / 执行能力变化；SSE 与 Run 执行链路不动；`data/`、`demo/` 不动。

## 4. 切片与验证（指引，不写死）

建议拆 **3 片**（后端 2 片 + 前端 1 片，与 PRD 三个功能需求一一对应，便于独立验收）：

- **S1：全局 Run 列表（后端）**。`GlobalRunData` + `list_page` + `GET /runs` 路由/资源。
  验收语义：AC1（跨会话跨服务摘要分页）、AC2（状态过滤）、AC3（service_id 过滤，
  不存在值空列表）、AC4（摘要无未脱敏内容）。
- **S2：会话搜索（后端）**。`list_page` 增加 `q` + 路由校验与透传。
  验收语义：AC5（标题匹配）、AC6（无 `q` 契约不变）、AC7（超长/控制字符明确错误）。
- **S3：前端适配（前端）**。侧栏搜索框 + Ctrl K + 最近调查页 + 接线。
  验收语义：AC8（搜索框与 Ctrl K 真实可用）、AC9（最近调查入口与列表页）、AC10（前端回归）。

涉及门禁项：**新增公开 API**（`GET /runs`、`GET /sessions?q=`）⇒ 本 Design 经
arch-review PASS + 用户确认后方可开发；无迁移、无 Connector、无凭据、无权限/审批/
执行能力扩大。

## 5. 风险、回滚与门禁

| 风险 | 缓解 |
|---|---|
| `q` 关键词含 LIKE 通配符改变查询语义 | 转义 `%`/`_`，按字面匹配 |
| 搜索输入频率高 / 列表查询规模 | 300ms debounce + cursor 分页 + limit 上限 100；查询为有界过滤（前导通配符 LIKE 不依赖索引），规模受 limit 截断，不提供无界扫描 |
| `Ctrl K` 与浏览器默认行为冲突 | `preventDefault` + `stopPropagation`；仅 workbench 域监听 |
| 归档会话的 Run 出现在全局列表造成误解 | 如实展示（历史视角，待确认决策 5）；列表不暗示会话仍活跃 |
| 生成契约与后端漂移 | `npm run generate:api` 重新生成，禁止手编 |
| 会话投影/侧栏改造回归 | 前端 `typecheck`/`test`/`build` 全量回归 |

- 回滚：移除 `GET /runs` 端点、`q` 参数与前端入口即回退（无迁移、无配置、无 Connector）。
- 门禁项清单：新增公开 API（`GET /runs`、`GET /sessions?q=`）⇒
  Design → Review → 用户确认；未新增迁移/凭据/权限/审批执行能力。

## 6. 待用户确认的设计决策

1. **会话搜索实现方式**：`GET /sessions` 加 `q` 参数（复用既有分页/脱敏/状态过滤，
   兼容扩展，无 `q` 行为不变）而非独立搜索端点——是否确认？（PRD 开放问题 1 推荐方案）
2. **`Ctrl K` 交互范围**：首版只聚焦侧栏搜索框（真实键盘监听，替代假提示），
   不做命令面板（新建会话/搜索/跳转合一）——是否确认？（PRD 开放问题 2 推荐方案）
3. **全局 Run 列表排序**：按发起时间（`created_at`）倒序固定，v1 不支持其他排序
   （与既有 cursor 固定排序契约一致）——是否确认？（PRD 开放问题 3 推荐方案）
4. **服务过滤口径**：`GET /runs` 的 `service_id` 按 **Run 自身 `service_id`** 过滤
   （P6 已确认「会话承载多服务、每服务一个 Run」，Run 级最精确），而非会话的单值
   `service_id`——是否确认？注：未绑定服务的 Run（`service_id` 为 NULL）不会命中任何
   服务过滤，属诚实行为。
5. **归档会话的 Run 出现在全局列表**：全局 Run 列表不做会话状态过滤，归档会话的
   历史调查仍可见（历史视角；搜索/最近会话仍只针对 active）——是否确认？
