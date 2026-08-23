# P8 会话工作台生命周期闭环——归档浏览与恢复 Design

> 状态：已确认（独立 Review PASS，无 P0–P2；用户确认 7 项设计决策）
> 更新：2026-08-23
> 关联：`docs/prd/session/P8-session-lifecycle-management.md`（已确认，issue #96）、
> `docs/产品定义.md`（§2.1 会话主入口、§5 安全与诚实性）、
> `docs/开发规范.md`（§2/§4/§6/§7.2）、`docs/架构与开发路径.md`、
> `docs/接口清单.md`（会话更新契约）、`docs/完善清单.md`（P2-4）、
> `backend/src/application/services.py`、`backend/src/domain/repositories.py`、
> `backend/src/infrastructure/persistence/repositories.py`、`backend/src/api/v1/routes.py`、
> `frontend/src/features/shell/Sidebar.tsx`、`frontend/src/features/session/SessionActions.tsx`、
> `frontend/src/features/workbench/WorkbenchPage.tsx`、`frontend/src/api/v1/queries.ts`。

## 1. 目标与范围

### 一句话目标

复用既有会话状态过滤、标题搜索、cursor 分页和 `PATCH /sessions/{id}`，让用户能在侧栏浏览
archived 会话并将同一个会话原地恢复为 active；恢复具备数据库条件更新保证的幂等语义，前端在
结果不确定时回读服务器事实，不复制会话、不创建 Run，也不触发任何外部访问。

### 做什么

1. 侧栏增加“最近会话 / 已归档”双视图；两边分别读取 `status=active` / `status=archived`，
   均支持既有标题搜索与 cursor 分页，并区分加载、空列表、无匹配、首屏失败和下一页失败。
2. 扩展既有 `PATCH /sessions/{session_id}` 的状态转换语义：允许仅提交
   `{ "status": "active" }` 将 archived 会话原地恢复；首次转换清空 `archived_at` 并更新
   `updated_at`，重复恢复只返回当前 active 事实且不再次更新时间。
3. archived 列表项和 archived 详情均提供恢复入口；确认文案明确“恢复录入能力、不复制内容、
   不启动调查”。成功后刷新所有会话列表/搜索缓存与详情，并切回 active 视图进入同一会话。
4. 对网络中断、5xx 或成功响应丢失等不确定结果回读 `GET /sessions/{id}`：服务器已 active 则
   按幂等成功收敛，仍 archived 则保留原状态并提示重试，回读也失败则明确提示结果尚未确认。
5. 修正 archived 详情的只读边界：仅隐藏重命名、消息编辑/删除、新消息和新调查；Run 取消/重跑、
   提案审批与后台状态刷新继续按各自既有规则工作。
6. 把 Session 活动时间更新从“读整行后全行 save”收敛为单列、单调 `updated_at` 更新，避免 Run
   终态/取消或普通消息事务持有的旧 Session 快照覆盖归档/恢复状态。

### 明确不做

- 不新增恢复端点、表、字段、迁移、会话副本或生命周期业务审计事件。
- 不永久删除、批量归档/恢复、设置保留期限、文件夹/标签/置顶或消息全文搜索。
- 不改变消息接口、Run 取消/重跑、提案审批、审计活动和导出的服务端语义。
- 不在归档/恢复时取消、重跑、复制或启动 Run，不调用 Agent、Tool、Connector、模型或真实外部服务。
- 不引入身份、租户、RBAC 或审批恢复；这些仍是未决产品边界。

### 与既有主脊和设计闸门的关系

本工作包不新增产品能力主脊，只接通既有 archived 查询能力并扩展既有 PATCH 的一个状态转换。
由于公开契约从“archived 不能重新激活”变为“可幂等恢复”，仍属于 `docs/开发规范.md` §7.2 的
Design 门禁项，必须经独立 Review 与用户确认后才进入实现。

## 2. 设计决策

### 2.1 恢复沿用既有 PATCH 契约

| 方法 | 路径 | 请求 | 成功语义 | 错误 |
|---|---|---|---|---|
| PATCH | `/sessions/{session_id}` | `{ "status": "active" }` | 200，返回同 id 的 active `SessionResource` | 404 会话不存在；422 请求非法；409 状态冲突 |

- 不新增 `/restore` 旁路端点。`UpdateSessionRequest.status` 已是 `active | archived`，请求/响应结构
  不变；本次只改变状态机语义，前端生成类型无需手工修改。
- 标准恢复请求必须只带 `status=active`。若当前会话 archived 且同一请求还带 `title`，服务端返回
  409 `SESSION_ARCHIVED`，要求先恢复再走既有重命名，避免一次请求同时突破 archived 录入只读并
  违背“恢复保留原标题”。active 会话既有标题更新/冗余 `status=active` 行为保持兼容。
- 会话不存在返回既有 404 `SESSION_NOT_FOUND`；不把 404 或 409 前端改写为成功。
- `DELETE /sessions/{id}` 的逻辑归档接口保持不变；归档确认文案更新为“可在已归档中找回并恢复”。

### 2.2 后端状态转换与并发幂等

`SessionApplicationService.update_session` 对“仅 `status=active`”使用独立恢复分支；Repository 端口
增加条件更新：

```text
UPDATE sessions
SET status='active', archived_at=NULL, updated_at=:restored_at
WHERE id=:session_id AND status='archived'
```

- 恢复分支的**第一条数据库语句就是条件 UPDATE**，在此前不调用 `get_by_id`，避免 SQLite deferred
  transaction 先读后写的 `BUSY_SNAPSHOT` 风险，也避免 ORM identity map 缓存旧 archived 对象。
- `SqlAlchemySessionRepository.restore(session_id, restored_at) -> bool` 只加入调用方事务，不提交；
  `rowcount == 1` 表示本请求完成唯一一次 archived → active 转换。
- 条件更新后用强制刷新查询（`populate_existing` 或等价显式 SELECT）回读同一记录；标题、服务上下文
  及所有关联表完全不写。
- 条件更新未命中时回读当前事实：不存在 → 404；已经 active → 幂等 200，直接返回当前记录，
  不调用 `_utc_now()` 后的保存路径、不改变 `updated_at`；其他不可能状态 → 409 安全冲突。
- PostgreSQL READ COMMITTED 下，并发 UPDATE 由行锁串行，只有第一个命中 archived；SQLite 文件库下，
  恢复首语句即 UPDATE，第二个短事务等待默认 busy timeout 后观察 active。后续请求均幂等 200，因而
  只有一次生命周期 `updated_at` 变化。不写生命周期业务事件。若 SQLite 锁等待确实超时，服务端返回
  既有安全 500，前端按“不确定结果”强制回读；不伪造成功。
- 现有归档路径继续保持幂等。归档与恢复互相竞争时以数据库实际提交后的状态为准；客户端完成后
  统一重新读取列表/详情，不依赖乐观状态猜测最终结果。

#### 消除旧快照覆盖生命周期状态

现有 `_touch_session` 和 `SqlAlchemyPlainMessageWriter` 会读取完整 `SessionData`，再调用
`repository.save(model_copy(updated_at=...))`，从而把旧的 title/status/archived_at 一并写回。Run
完成/取消与恢复并发时，这会把已恢复的 active 覆盖回 archived，CAS 无法单独防住。

因此 `SessionRepository` 同时增加
`touch_updated_at(session_id, updated_at) -> bool`，实现为**只更新 `updated_at` 且保持单调**：

```text
UPDATE sessions
SET updated_at=:activity_at
WHERE id=:session_id AND updated_at < :activity_at
```

- `_touch_session` 与 `SqlAlchemyPlainMessageWriter` 全部改用该列级方法，不再用全行 `save` 触碰活动时间。
- 较早活动时间即使晚提交也不能覆盖恢复/后续活动的较新时间；较晚的 Run 终态属于真实新活动，可以
  合法把恢复后的会话保持在最近会话顶部。
- `save` 仍只用于显式标题/生命周期写入；本工作包不顺带改变消息或 Run 的业务语义。

该设计只修改应用元数据，无迁移。Repository 测试直接锁定恢复 CAS、单列 touch 的字段集合和时间
单调性；API/应用测试锁定首次/重复恢复、SQLite 文件库两个独立 Session/线程竞争，以及“恢复 vs
Run terminal/cancel touch”时生命周期状态不被旧快照覆盖。

### 2.3 侧栏双视图、搜索与分页

- `Sidebar` 增加可键盘操作的双视图切换，默认 `active`；当前选择用可识别文本和选中状态表达。
- 查询改为 `useInfiniteQuery`：query key 包含 `{limit, status, q}`，cursor 只作为 `pageParam`；
  active / archived 与不同关键词缓存天然隔离，页面合并时按服务端顺序展示。
- 搜索框复用既有 300ms debounce、100 字符服务端边界和 `Ctrl K`/Esc 交互。切换视图时保留当前
  输入，并在新 status 范围内重查；清空只恢复当前视图默认列表，不回退到 active 数据充数。
- 首屏状态分别显示“正在加载会话 / 正在加载归档会话”“还没有会话 / 还没有归档会话”
  “无匹配会话 / 无匹配归档会话”“会话列表暂不可读 / 归档会话暂不可读”。
- `has_more=true` 时显示“加载更多会话”；下一页失败保留已加载内容，显示“加载更多失败”及重试入口，
  不把分页失败伪装成列表结束。
- archived 行展示“已归档”标识并保留进入同一详情的按钮；行尾直接提供“恢复会话”入口。
- 恢复成功后回调 Sidebar：切换到 active 视图并导航到同一 session id。由于服务器已更新
  `updated_at`，该会话在 active 最近会话首位；当前 URL 不需要新路由。

### 2.4 恢复交互、缓存收敛与不确定结果

`SessionActions` 扩展为三种互斥模式：

- active：保留既有重命名/归档菜单；
- archived：只显示“恢复会话”按钮与恢复确认框，不显示重命名/归档；
- unknown/refreshing：不显示任何生命周期动作；不能把“尚未取得新鲜服务器事实”降级解释为 archived。

确认框文本固定说明：

> 恢复后会话将回到最近会话，并重新提供消息与调查录入。恢复不会复制历史内容，也不会创建或启动调查。

提交期间 `confirmLoading` + disabled 阻止同一入口重复请求。结果处理：

1. 200 且响应 session 为 active：成功；
2. 200 但资源缺失、session id 不等于请求 id 或仍 archived：视为协议错误，不宣称成功，回读详情；
3. 明确 4xx 拒绝：保留 archived，显示 `ApiClientError` 的安全 code/message，允许重试；
4. `NETWORK_ERROR` / `REQUEST_ABORTED`（status=0）、5xx、或 2xx 响应无法解析：结果不确定，**直接**
   调用 `api_v1_client.get_session(id)` 发起发生在 mutation 失败之后的新请求，不走 React Query
   `fetchQuery` 去重；校验返回 id 与 status。已 active → 幂等成功，仍 archived → 展示原安全错误并
   允许重试；回读 404 → 明确展示 `SESSION_NOT_FOUND`，不伪装成可重试 archived；其他回读失败 →
   “恢复结果尚未确认，请刷新会话状态后重试”。

无论 PATCH 确定性成功还是经回读收敛成功，在写详情缓存前都先
`await queryClient.cancelQueries({queryKey: api_v1_query_keys.session(id), exact: true})`。详情 queryFn 已
透传 AbortSignal；取消可阻止恢复前在途 GET 晚到后把 authoritative active 缓存覆盖回 archived。
不确定路径的顺序固定为“取消旧详情 GET → direct GET → 校验 id/status → setQueryData”。

成功收敛后执行：

- `setQueryData(api_v1_query_keys.session(id), authoritative_response)` 写入已验证的服务器详情事实；
- 对会话列表前缀 `['api-v1','sessions']` 先 `cancelQueries`；对 inactive 缓存执行 `removeQueries`，
  对 active observer 执行并等待 `resetQueries`（清空旧 data 后重新读取），覆盖 active/archived、所有
  搜索词和所有分页，避免切视图时闪现恢复前数据；
- 用当前 `limit/status=active/q` 的 infinite query 显式预取首屏并等待完成，再切 active/导航；预取失败
  则仍进入详情并让列表显示诚实错误态，不回填旧缓存；最后 invalidate 作为后台事实复核；
- Sidebar 列表恢复成功由 Sidebar 父级 `aria-live` notice 承载，行卸载后仍可读；详情恢复由未卸载的
  工具栏 notice 承载。两者均显示“会话已恢复”。

#### Sidebar 与详情之间的共享状态

`Sidebar` 与 `WorkbenchPage` 是 `ProductShell` 下的兄弟组件。新增轻量
`SessionNavigationContext`（Provider 放 `ProductShell`），集中保存：当前 active/archived 视图、当前
搜索输入/已 debounce 的 q、恢复成功 notice，以及 `handle_session_restored(session_id)` 回调。

- Sidebar 的切换与搜索改读写该 context，既有 `Ctrl K`/Esc/debounce 行为不变；
- 列表和详情的 `SessionActions` 都从 context 取得当前 q 与回调，因而使用同一个 active 首屏预取键；
- `handle_session_restored` 在缓存收敛/预取完成后把 view 设为 active、保留当前 q、写稳定 notice 并
  导航到同一 session id；搜索词来自 archived 标题匹配，恢复后仍会命中同一标题；
- context 只管理前端导航状态，不保存或推断服务器 session 状态；刷新页面仍由 API 重新读取。

不采用乐观更新；失败前端不会自行把 session 改成 active。

### 2.5 archived 详情的只读边界与运行中刷新

现有 `WorkbenchPage` 把一个 `read_only` 同时传给消息、Run 和提案控件，导致 archived 会话隐藏
Run 取消/重跑和提案操作，与 PRD 既有基线不符。本次拆分为：

- `session_input_read_only`：控制会话重命名、消息编辑/删除、Composer、新调查自动提交，以及 URL
  `intent` 预填提示、本地 pending intent 的恢复与展示；
- Run/提案控件：不再由 session archived 状态统一隐藏，继续使用各自既有 Run/提案状态规则。

具体保持：

- archived 不显示重命名、消息编辑/删除、Composer 和新调查入口；恢复后这些 active 控件重新出现。
- queued/running Run 的 SSE/事件刷新继续挂载；状态与安全 Trace 如实更新。取消入口仍按 queued/running
  规则显示；终态重跑入口仍显示，archived 下按既有后端语义返回 `SESSION_ARCHIVED` 而非暗示成功；
  提案审批同理。
- 历史消息、Run、结果、安全 Trace、提案状态与导出入口继续读取；恢复不使这些查询失效或复制。

### 2.6 安全、审计与兼容性

- 恢复只写 `sessions.status/archived_at/updated_at`，不写 messages、runs、action_events、
  service activities 或任何用户服务数据；不新增生命周期业务审计事件。
- 请求/响应继续使用既有 `SessionResource` 白名单，不含 DSN、凭据、原始工具输出、原始异常、
  Prompt 或 CoT。
- 不新增 Tool/Connector/Agent 装配，不触发外部连接。测试通过 fake/SQLite 元数据运行，不访问真实资源。
- active 创建、重命名、归档、标题搜索/分页、直接地址读取、消息编辑/删除、Run 取消/重跑、导出、
  提案审批与审计查询保持契约兼容。

## 3. 文件改动面

### 后端

- `backend/src/domain/repositories.py`：`SessionRepository.restore` / `touch_updated_at` 端口；同时补齐
  现有 `list_page(..., q)` 端口签名。
- `backend/src/infrastructure/persistence/repositories.py`：实现 archived → active CAS 与单列单调 touch。
- `backend/src/application/services.py`：`update_session` 增加恢复分支与幂等回读；`_touch_session` 改为
  列级 touch；更新公开注释。
- `backend/src/infrastructure/persistence/plain_message_writer.py`：活动时间改为列级 touch，禁止旧快照
  回写生命周期列。
- `backend/src/application/contracts.py`、`backend/src/api/v1/schemas.py`：更新会话更新契约注释。
- `backend/src/api/v1/routes.py`：更新 PATCH 路由说明（允许恢复）；请求/响应形状不变。
- `backend/tests/test_p2_repositories.py`：条件更新只改三字段、重复调用不再更新时间。
- `backend/tests/test_p2_application_services.py`：首次/重复恢复、标题/关联保留、归档后 Run 基线。
- `backend/tests/test_p2_api_v1.py` 与新增 `backend/tests/test_session_lifecycle.py`：PATCH 恢复、404/409、
  并发/重复请求、关联记录与无生命周期事件回归；文件型 SQLite 两独立事务与 Run touch 竞态。

### 前端

- `frontend/src/features/shell/Sidebar.tsx`：双视图、archived 搜索/分页/状态、恢复成功导航。
- `frontend/src/features/session/SessionNavigationContext.tsx`（新增）：在 ProductShell 的 Sidebar/
  Workbench 之间共享视图、q、恢复 notice 与成功回调。
- `frontend/src/app/App.tsx`：装配 `SessionNavigationContext` Provider。
- `frontend/src/features/session/SessionActions.tsx`：archived 恢复确认、loading、错误分类与事实回读。
- `frontend/src/features/workbench/WorkbenchPage.tsx`：详情恢复入口；拆分会话录入只读与 Run/提案规则；
  更新 archived 提示。
- `frontend/src/api/v1/queries.ts`：会话 infinite query 选项或等价集中式 query helper；既有 mutation 复用。
- `frontend/src/features/shell/Sidebar.test.tsx`：双视图、archived 搜索/分页/空态/失败态、列表恢复。
- `frontend/src/features/session/SessionActions.test.tsx`：确认文案、重复提交、明确拒绝、不确定结果回读、
  回读 404/错 id/在途旧详情 GET、unknown/refreshing 不显示动作。
- `frontend/src/app/App.test.tsx`：archived 详情恢复、active 控件恢复、Run/提案/导出回归、运行中刷新、
  archived URL intent/pending intent 不展示不提交。
- `frontend/src/test/handlers.ts`：archived 列表与 PATCH 恢复的确定性 mock。
- `frontend/src/styles/app-shell.css`、`frontend/src/styles/workbench.css`：视图切换、归档标识和恢复反馈。

### 文档

- `docs/接口清单.md`：PATCH 会话说明改为支持幂等恢复，前端接线标记完成。
- `docs/完善清单.md`：P2-4 在端到端复验后标 ✅，写日期与验证方式。
- `docs/路线图.md`：登记 issue #96 完成。
- `docs/workpack/P8-session-lifecycle-management/{plan,evidence,review}.md`：计划、证据与独立代码 Review。

### 明确无改动

- 无数据库迁移；不修改 `frontend/src/api/v1/generated.ts` 的字段形状；无新增端点、配置、环境变量、
  Connector、凭据、权限或审批/执行能力。

## 4. 切片与验证

建议拆 2 个紧密切片：

- S1 后端恢复语义：Repository CAS + 单列单调 touch + Application/API 恢复 + 幂等/并发/关联保留
  与 Run touch 竞态测试（AC6、AC8、AC10、AC11、AC13、AC14）。
- S2 前端生命周期闭环：双视图/搜索/分页/恢复/不确定回读 + 详情只读边界修正与交互测试
  （AC1–AC7、AC9、AC12、AC15）。

必须显式覆盖的边界用例：

- 后端：首次/重复恢复；不存在；archived 组合标题冲突；文件型 SQLite 两连接并发恢复；恢复与
  Run 终态/取消 touch 交错；plain message touch 不回写生命周期列；消息、Run、提案、审计、服务关联
  主键集合不变；不新增生命周期事件。
- 侧栏：active/archived 双视图；q 为 100 字符成功、101 字符受既有边界拒绝；各视图无数据/无匹配/
  首屏失败；下一页失败保留已加载页且可重试；active、archived、多 q、多页的 inactive cache 预置后
  恢复无旧行闪现。
- 恢复：双击只发一次 PATCH；明确 4xx；network/5xx/无效 2xx 后的新 GET；已有恢复前在途详情 GET
  不能被复用且旧 GET 最晚返回也不能覆盖 active 缓存；回读 active/archived/404/错 id；Sidebar 行
  卸载后成功 notice 仍存在；列表/详情恢复均通过共享 context 切 active 并使用同一个 q 预取键。
- 详情：active 初载与 background refetch 为 unknown/refreshing，不出现恢复入口；archived 的 URL intent
  与 pending intent 不显示不提交；queued/running 继续刷新且可取消；终态重跑仍显示并诚实收到
  `SESSION_ARCHIVED`；提案与导出入口按既有规则；恢复后录入控件重新出现。

最终执行后端相关与全量测试；前端 `typecheck`、`test`、`build`；`git diff --check`；检查无凭据、
DSN、`sk-`、原始工具输出或原始异常进入改动。

## 5. 风险、回滚与门禁

| 风险 | 缓解 |
|---|---|
| 并发恢复重复更新时间 | 数据库 `WHERE status='archived'` 条件更新，只有一个请求 rowcount=1 |
| Run/普通消息的旧 Session 快照覆盖恢复 | 所有活动时间写入改为单列单调 UPDATE，不再全行 save |
| mutation 成功但响应丢失造成假失败 | 区分明确 4xx 与不确定错误；不确定时强制回读服务器事实 |
| 事实回读复用恢复前在途 GET | 不走 Query 去重，mutation 失败后直接发新 GET 并校验 id/status |
| 恢复前详情 GET 晚到覆盖 active 缓存 | 成功/回读路径均先 cancel 精确详情 query，再 set authoritative data |
| active/archived 或不同搜索缓存混用 | 取消请求，移除 inactive 缓存并 reset/refetch active 缓存，预取目标首屏 |
| 刷新中 active 被当作 archived | `SessionActions` 增 unknown/refreshing 态，不展示恢复入口 |
| 列表恢复后行卸载导致成功提示消失 | Sidebar 回调切 active + 导航同一详情，由稳定页面承载成功反馈 |
| archived 只读误伤 Run/提案既有操作 | 拆分 `session_input_read_only`，交互测试锁定 AC5/AC6 |
| 下一页失败被误判无更多数据 | 保留已加载页，单独展示加载更多失败与重试 |
| 公开契约语义回滚 | 移除恢复分支与前端入口即可；无迁移/新数据结构，但已恢复会话不会自动重新归档 |

门禁：本 Design 需独立 Review PASS + 用户确认后方可开发；实现完成后还需独立代码 Review PASS。

## 6. 待用户确认的设计决策

1. 恢复复用 `PATCH /sessions/{id}` + `{status:"active"}`，不新增 `/restore` 端点。
2. 后端以条件更新实现并发幂等；只有首次 archived → active 更新 `updated_at`，重复恢复返回当前事实。
3. archived + `title` + `status=active` 的组合 PATCH 返回 409，要求先恢复再重命名；标准恢复保留原标题。
4. 侧栏切换 active/archived 时保留搜索词，在新状态范围内重新搜索；恢复成功切回 active 并进入同一会话。
5. 网络/5xx/成功响应解析失败等不确定结果先回读详情；只有服务器事实 active 才显示成功。
6. archived 只限制会话录入；Run 取消/重跑、提案审批继续按既有规则，恢复不改变它们的服务端语义。
7. Session 活动时间统一改为单列、单调 touch，避免 Run/普通消息旧快照覆盖归档/恢复生命周期列。
