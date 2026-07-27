# P3 Step2 — v1 API 客户端与会话恢复读模型

> 日期：2026-07-27　|　状态：✅ Design 与独立审查完成，待用户授权暂存/提交　|　实现基线：`4862752 feat: 初始化P3主前端工程与产品外壳`
>
> 范围：只设计 P3.2a/P3.2b 的 v1 读取边界；本轮不修改 `frontend/` 源码、不请求写接口、不改后端、`report/`、真实数据源或运行时资产。

## Design

### 目标与范围

P3.2 把 P3.1 的空产品壳接到已实现的持久化读取契约：显示真实 Session 导航、读取选中 Session 的 Run 列表与 Message 时间线，并在已选 Run 时读取 `DiagnosisRunResource`（含可用的 `result`/`error` 字段，但不在本 Step 做结构化结果视觉完成）。它必须能在刷新或深链接时从服务器事实恢复，而不是把前端本地状态当会话真相。

只读允许的端点：

```text
GET /api/v1/sessions
GET /api/v1/sessions/{session_id}
GET /api/v1/sessions/{session_id}/runs
GET /api/v1/sessions/{session_id}/messages
GET /api/v1/runs/{run_id}
```

禁止：`POST/PATCH/DELETE` Session、`POST /runs`、Run Event/SSE、`report/` 跳转、旧 `/diagnose` 与 `/diagnose/stream`、真实 DB/数据源/认证接入。P3.3 处理 Run 受理和 SSE，P3.4 才完成结构化结果与归档/空/失败交互收口。

### 契约来源与类型策略

- 实施前从已启动后端的 `GET /openapi.json` 生成并提交 `frontend/src/api/v1/generated.ts`，使用 `openapi-typescript`；生成命令必须显式以 OpenAPI 输入和输出路径运行，正常 `typecheck/test/build` 绝不依赖在线抓取。
- 生成文件是 v1 Pydantic/OpenAPI 的前端字段真相，业务代码引用其 `components["schemas"]` 类型或从中派生别名；不得手写第二套 Session/Message/Run/Result 字段接口。
- 少量客户端内部类型仅表示传输外壳：`ApiRequestDiagnostics`（请求/响应 request ID、trace ID、状态码）、`ApiClientError`（安全 code/message/details/diagnostics）和不含业务字段的 cursor 参数；不能重建资源 schema。
- 生成前先对 OpenAPI 路径、资源 schema、`ResponseMeta` 与错误响应进行测试快照/断言。若 OpenAPI 无法表达某个安全错误 schema，客户端仍只按统一 `{ error, meta }` 容器读取，不自行猜测服务端异常内容。

### v1 GET 客户端

在 `frontend/src/api/v1/` 新建 `client.ts`、`queries.ts` 和生成类型文件；不把服务器资源写入 Zustand。

1. 每个 GET 通过统一 `request_json` 生成 UUID `X-Request-Id`（可注入生成器供测试），发送 `Accept: application/json`，支持 `AbortSignal`，不对业务失败自动重试；现有 QueryClient 的 `retry: false` 保持。
2. 读取 HTTP `X-Request-Id`、可用时 `X-Trace-Id`，同时读取 JSON `meta.request_id`/`meta.trace_id`。返回数据连同 diagnostics；header/meta 不一致是安全协议诊断，界面使用响应 `meta` 做关联展示，不把它变成资源状态或泄露原始响应。
3. 非 2xx 先解析安全 `{ error, meta }`；抛出带 HTTP status、安全 code/message/details、request/trace diagnostics 的 `ApiClientError`。非 JSON、网络或 abort 明确标为 transport/protocol 错误，不能伪造成 `INTERNAL_ERROR` 或 Run failed。
4. cursor 用 `URLSearchParams` 原样传递和返回；客户端不解码、拼造或跨 Session 复用。默认读取 limit 在一个常量中固定，并仅在 Query 层传入。
5. 所有日期维持 UTC `Z` 字符串进入资源缓存；显示层才转换为本地可读时间，排序仍使用 API 固定顺序。

### Query、路由与固定恢复顺序

TanStack Query 是唯一的服务器事实缓存；Zustand 仅保留导航折叠等 UI 状态。建议 key：

```text
['api-v1', 'sessions', { status, limit }]
['api-v1', 'session', session_id]
['api-v1', 'session-runs', session_id, { limit }]
['api-v1', 'session-messages', session_id, { limit }]
['api-v1', 'run', run_id]
```

列表使用 `useInfiniteQuery`：`getNextPageParam` 只返回服务端 `page.next_cursor`，`has_more=false` 时不可继续加载。Session、Run、Message cursor 均不跨 Session 或筛选条件复用。

路由收口为：

```text
/workbench
/workbench/sessions/:session_id
/workbench/sessions/:session_id/runs/:run_id
```

刷新/深链接按严格次序：

```text
1. /workbench：GET active Session 列表；无 Session 显示真实空状态。
2. 选中或 URL 指定 session_id：GET Session；失败时显示安全错误并回到可用列表。
3. Session 成功后：先 GET Session Runs，再 GET Session Messages；两者使用独立 cursor/错误状态。
4. URL run_id 优先；否则只从首个已加载 Run 页面选择最新项并更新 URL；无 Run 显示“尚无诊断 Run”。
5. 选中 Run：GET Run，断言其 session_id 与路由 session_id 一致；不一致按安全路由/协议错误处理，绝不展示跨 Session 数据。
6. P3.2 到此结束：不读取 Event、不建立 SSE、不创建 Run、不把 result/error 展开成 P3.4 结果页。
```

`/workbench` 没有可选 Session 时不伪造选中资源；直接无效 Session/Run URL 不自动创建 Session 或执行诊断。已归档 Session 若由直接 URL 读取成功，P3.2 以只读提示展示，不能改造为 active 或显示提交动作。

### MSW、真实 API 与错误状态

P3.2a 先创建严格同名的 MSW handlers，固定 UUID、UTC `Z`、不透明 cursor 与安全错误体。最少场景：

- active Session 空列表；
- 一页 active Session、succeeded Run、按时间 Message、带结构化 `result` 的 Run 资源；
- 多页 Session/Run/Message，验证 `next_cursor` 原样回传；
- `SESSION_NOT_FOUND`、`RUN_NOT_FOUND`、归档 Session、`INTERNAL_ERROR`、网络中断、无效/不一致 request ID 关联信息；
- Run session_id 与 URL session_id 不一致的客户端保护场景。

前端实现先以 MSW 进行确定性组件测试，后续才使用用户启动的 mock FastAPI 做联调。本轮预检结果是 `/health`、`/openapi.json` 可读，但 `GET /api/v1/sessions?limit=1` 返回安全 `500 INTERNAL_ERROR` 且回显 `X-Request-Id`；不在 P3.2 前端范围排查/修复后端。真实 API 验收前必须共同确认应用数据库 URL、显式 Alembic migration 是否完成、连接目标/最小权限、可用 mock 数据、回退和验收场景；不得因 500 在前端静默回退 fake data 或内存会话。

本机 Vite 当前监听 `::1:5174`，本地浏览应使用可达的 IPv6 loopback 或调整开发服务监听策略；P3.2a 仅保留 `/api` 代理到 `http://127.0.0.1:8000`，不改变后端路径和不会使用旧 API。

## Step

| 子 Step | 交付 | 不混入 |
|---|---|---|
| P3.2a | OpenAPI 类型生成命令/产物、统一 v1 GET client、安全错误/diagnostics、MSW handlers 与 client 测试 | 路由工作区、Session UI、写接口、SSE |
| P3.2b | 三层路由、Session 导航、Run/Message 只读恢复查询、空/加载/错误/分页 UI 和组件测试 | Run 受理、Event/SSE、完整结果卡、归档/编辑动作 |
| P3.2c | mock FastAPI 联调、刷新/深链人工验收、独立 Review 与提交 | 真实 DB/数据源/认证、P3.3/P3.4/P4/P5/P6 能力 |

每个子 Step 独立 Design → Code → Test → Review → Commit；P3.2a 是唯一首个实现 Step。

## Test

P3.2a 最低测试：生成类型与 OpenAPI 路径/schema 一致；client 成功/安全错误/网络错误/abort/request ID/cursor 测试；MSW handler 合同测试；typecheck、Vitest、build。

P3.2b 最低测试：空列表、深链 Session、Run 优先选择、Message/Run 分页、Session/Run 404、安全 500、归档只读、跨 Session Run 保护；不得断言或调用 POST/SSE。

P3.2c 人工验收：MSW 与 FastAPI mock 分开执行；刷新时严格按恢复顺序请求；页面明确显示安全错误和 request ID；确认无旧 API 请求、无 sqlite 文件、无真实数据源。后端 500 未解决时，仅记录为真实联调阻塞，MSW 结果不能宣称真实 API 成功。

## Review

- P2 契约：五个 GET 端点、排序、cursor、UTC `Z`、ResponseMeta、X headers 与安全错误均有前端消费映射；未臆造 Result 或 Event 端点。
- 范围：P3.2 仅 read model；创建 Run/SSE/事件/结构化结果视觉、Session 写操作和 report 跳转明确后置。
- 架构：生成 OpenAPI 类型为字段真相；Query 管服务器事实，Zustand 不存资源；MSW 固定契约场景而非前端假业务数据。
- 联调：当前安全 500 与 IPv6 前端监听已记录为环境观察，不被静默掩盖或在前端错误修复。

## 提交边界与唯一下一步

本轮仅提交 P3.2 Design/Review/HANDOFF、计划和规则状态校正；不提交 `frontend/` 源码、依赖、后端、`report/`、数据、运行时 SQLite 或隔离文件。

**用户授权提交本 Design 后，唯一下一步为 P3.2a：OpenAPI 类型、v1 API 客户端与 MSW 契约实现。**