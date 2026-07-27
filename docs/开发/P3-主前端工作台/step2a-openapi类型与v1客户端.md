# P3 Step2a — OpenAPI 类型、v1 API 客户端与 MSW 契约

> 日期：2026-07-27　|　状态：✅ Code / Test / Review 完成，待用户授权暂存/提交
>
> 设计基线：`ec45ee2 docs: 完成P3.2接口与恢复读模型设计`　|　分支：`feat/p3-workbench`

## Design

本 Step 落实 P3.2 的第一个独立实现切片，只提供 `/api/v1` 的五个只读读取入口和可测试的契约边界：

```text
GET /api/v1/sessions
GET /api/v1/sessions/{session_id}
GET /api/v1/sessions/{session_id}/messages
GET /api/v1/sessions/{session_id}/runs
GET /api/v1/runs/{run_id}
```

类型从当前本机 FastAPI 的 `GET http://127.0.0.1:8000/openapi.json` 显式生成到 `frontend/src/api/v1/generated.ts`。`npm run generate:api` 是唯一生成命令；`typecheck`、`test`、`build` 均不发起 OpenAPI 网络请求。业务代码只从 `components["schemas"]` 和 `operations` 派生资源/查询类型，不在前端重写 Session、Message、Run 或 Result 字段。

严格非目标：不改任何页面、路由或产品壳；不调用 POST/PATCH/DELETE、Run 受理、Event 或 SSE；不实现结果卡、Trace 跳转、真实 API 读模型联调、P4/P5/P6 资源；不修改 `backend/`、`report/`、数据或运行时 SQLite。

## Code

- `frontend/package.json:7-12` 增加 `generate:api`，并将 `openapi-typescript` 固定在开发依赖；`package-lock.json` 同步锁定版本。
- `frontend/src/api/v1/generated.ts:1` 是生成产物。当前 OpenAPI 将若干 Pydantic 字段输出为 `unknown`，因此前端保留该契约事实，不用手写字段接口掩盖后端 schema 表达能力；后端 OpenAPI 变化时必须重新生成并审查 diff。
- `frontend/src/api/v1/client.ts:1-275` 提供 `create_api_v1_client`、五个 GET 方法和唯一的 `request_json` 路径：请求带 `Accept: application/json` 与可注入 UUID `X-Request-Id`，支持 `AbortSignal`，不做自动业务重试；cursor 由 `URLSearchParams` 原样透传。
- `frontend/src/api/v1/client.ts:25-76,127-164` 将 HTTP header 与响应 `meta` 的 request/trace ID 记录为 diagnostics；header/meta 不一致只进入 `protocol_issues`。安全非 2xx 读取 `{ error, meta }` 并抛出 `ApiClientError`；网络、取消、非 JSON/坏 JSON 分别保持 transport/protocol 分类，不伪造成 `INTERNAL_ERROR` 或 Run 失败。
- `frontend/src/api/v1/queries.ts:1-57` 只给后续 UI 提供 Query key 和 request functions，服务器事实仍归 TanStack Query；未新增 hook、路由或界面。
- `frontend/src/test/handlers.ts:1-171` 提供 MSW 的 active/empty/分页/archived Session、Message、succeeded Run（含结构化 result）、`SESSION_NOT_FOUND`、`RUN_NOT_FOUND`、`INTERNAL_ERROR` 与网络中断场景；每个正常 handler 回显请求 `X-Request-Id` 到 header 与 `meta`。

## Test

已在 `frontend/` 执行并通过：

```text
npm run typecheck  → 通过
npm test           → 2 个测试文件、8 个测试通过
npm run build      → 通过
npm run generate:api → 通过（仅显式命令读取本机 OpenAPI）
```

`frontend/src/api/v1/client.test.ts:7-139` 覆盖 cursor 原样传递、`Accept`、`X-Request-Id`、关联 diagnostics、安全 404、Run 的 `session_id` 保留、网络中断、取消、非 JSON 与 header/meta 不一致。生产构建仍有既有 Ant Design 主包超过 500 kB 的 Vite 警告（约 581 kB，gzip 约 191 kB）；本 Step 未引入页面代码，未处理拆包。

## Review

- 五个公开函数均为已批准的 GET 路由；未出现旧 `/diagnose`、`/diagnose/stream`、POST/PATCH/DELETE、SSE 或 `/events` 调用。
- `X-Request-Id`、`X-Trace-Id`、JSON `meta`、安全错误和 opaque cursor 有明确实现与测试；测试 handler 不把固定 mock ID 当服务端关联语义，而是正常回显客户端请求 ID。
- MSW 是单元/契约测试夹具，不是持久化不可用时的运行时降级；当前本机 `/api/v1/sessions` 安全 500 仍是 P3.2c 真实联调前置，未被前端吞掉。
- `generated.ts` 反映 OpenAPI 的现状；字段大范围为 `unknown` 是后端 OpenAPI 表达质量风险，不在此 Step 用重复 DTO 规避。后续需要更强字段检查时，应先走后端契约 Design。
- `frontend/mockup.html`、`report/`、`backend/`、`data/` 均未改动。

## 提交边界与唯一下一步

本 Step 暂存时只包含本文件、P3 的设计/审查/交接与计划状态回填、`AGENTS.md`/`CLAUDE.md`、以及 `frontend/` 下的 OpenAPI 生成、读取客户端、测试 handler、`package.json` 与 `package-lock.json`。不得包含外部隔离文件。

**用户授权提交后，唯一下一步为 P3.2b：Session 工作台只读 UI 与刷新/深链恢复实现。**
