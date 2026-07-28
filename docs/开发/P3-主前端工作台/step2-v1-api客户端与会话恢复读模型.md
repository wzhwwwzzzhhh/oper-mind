# P3.2 Design — v1 API 客户端与会话恢复读模型

> 日期：2026-07-28　|　状态：✅ P3.2 mock/离线验证完成；真实数据库只读验收延后；当前进入 P3.3 Design
>
> 实现基线：`75d6598 feat: 完成P3.2a v1 API客户端与MSW契约`
>
> 范围：定义并收口 P3.2 的只读 v1 客户端、Session 工作台恢复和后续 mock FastAPI 联调边界；不接入写接口、SSE、真实数据源或运行时资产。

## 1. 目标与已核实事实

P3.2 将 P3.1 的产品外壳连接到 P2 已交付的 `/api/v1` **只读恢复路径**。当前完成的 P3.2b 仅呈现 Session、Run、Message 与选定 Run；它不创建资源、不受理诊断、不消费 Event/SSE，也不展示完整结构化结果。

- P2 v1 契约以 `docs/开发/P0-V1产品化基线/api-v1-contract.md`、`backend/src/api/v1/routes.py`、`backend/src/api/v1/schemas.py` 为准；正式主产品只调用 `/api/v1`。
- 旧 `POST /diagnose`、`GET /diagnose/stream` 仅为兼容接口，P3 页面、客户端、测试和代理均不得调用或包装。
- `frontend/` 是独立主产品工程；`report/` 仍是 M7 的研发/Trace 界面。P3.2 不修改、不嵌入、不跳转 `report/`。
- 本机真实 `GET /api/v1/sessions` 当前返回安全 `500 INTERNAL_ERROR`。P3.2b 只显示安全错误及关联 request ID，不用 MSW 或假数据在运行时降级；真实读取成功只能在 P3.2c 的前置核对后验收。

## 2. P2 v1 契约的精确消费方式

| 读取目标 | P3.2b 使用的 API | 规则 |
|---|---|---|
| active Session 导航 | `GET /api/v1/sessions` | `status=active`、`limit=20`；服务端 cursor 原样回传，绝不解码或自造 |
| Session 深链 | `GET /api/v1/sessions/{session_id}` | URL `session_id` 必须先被读取成功，失败只显示错误资源 |
| Run 历史 | `GET /api/v1/sessions/{session_id}/runs` | 仅当前 Session；按服务端顺序展示，支持服务端 cursor 加载更多 |
| Message 历史 | `GET /api/v1/sessions/{session_id}/messages` | 仅在 Run 列表恢复成功后读取；支持 cursor 加载更多 |
| 选定 Run | `GET /api/v1/runs/{run_id}` | 仅在 Message 恢复成功后读取；若返回的 `run.session_id` 不等于 URL Session，显示 `RUN_SESSION_MISMATCH`，不展示内容 |

客户端为每次请求发送 `Accept: application/json`、UUID `X-Request-Id`，保留服务端 `X-Request-Id`、`X-Trace-Id` 与 JSON `meta` 中的关联值。UTC 时间不由前端重写为本地事实；cursor 只作为不透明 token 传回。错误只展示安全的 `error.code`、`error.message`、`meta.request_id` / `X-Request-Id`、`X-Trace-Id`；网络、协议、Abort 不伪装为业务错误。

`Idempotency-Key`、`POST /sessions/{session_id}/runs`、`GET /runs/{run_id}/events`、SSE `Last-Event-ID` 和持久化 RunEvent 均是后续 P3.3 的边界，P3.2b 没有实现入口。

## 3. 刷新与深链恢复顺序

```text
/workbench/sessions/:session_id[/runs/:run_id]
  1. GET Session
  2. GET Session Runs
  3. GET Session Messages
  4. URL 已有 run_id：保留它；否则取已恢复 Runs 的首项并 replace URL
  5. GET selected Run
  6. 仅后续 P3.3：非终态 Run 才建立 SSE，并以 Last-Event-ID 恢复
```

- 任一上游失败时，不启动或伪造下游资源；页面显示“等待上游恢复”而不是“没有数据”。
- Session 404/500 保持在会话级错误页；Run 404 保持在当前 Run 区域；归档状态只读提示，不提供重新激活或编辑。
- `get_run` 的跨 Session 响应被拒绝展示，避免 URL 或服务端异常造成跨会话内容泄露。

## 4. 已完成的 P3.2a / P3.2b 分解

| Step | 状态 | 产出 | 明确不做 |
|---|---|---|---|
| P3.2a | ✅ 已提交 `75d6598` | OpenAPI 类型、只读 v1 client、TanStack Query 描述、MSW 契约与 client 测试 | 路由、工作台 UI、写接口、SSE |
| P3.2b | ✅ 已提交 `3170e6a` | `/workbench`、Session/Run 深链、Session → Runs → Message → Run 恢复、cursor UI、安全错误与跨 Session 保护 | POST/PATCH/DELETE、Run 受理、Event/SSE、完整结果卡、Trace 跳转 |
| P3.2c.1 | ✅ 已提交 `5491829` | 独立 mock FastAPI、Vite 代理切换、刷新/深链与安全错误人工验收 | 真实 DB/数据源/认证接入、P3.3/P3.4/P4/P5/P6 |
| P3.2c.2 | ✅ 离线核对完成；真实 DB 验收延后 | 真实读模型的迁移、连接目标、最小权限、安全验收数据、契约、回退和验收前置核对 | 真实连接、P3.3/P3.4/P4/P5/P6 |

P3.2b 的实现锚点为：`frontend/src/app/App.tsx`、`frontend/src/features/workbench/WorkbenchPage.tsx`、`frontend/src/features/workbench/resource-readers.ts`、`frontend/src/api/v1/client.ts`、`frontend/src/test/handlers.ts` 与 `frontend/src/app/App.test.tsx`。详细提交边界记录在 `step2b-session工作台只读恢复.md`。

## 5. P3.2c 的隔离验收计划

P3.2c 单独处理，不与 P3.2b 混提交：

1. 使用独立 mock FastAPI 进程验证浏览器代理与 P2 JSON 错误资源，不能用 MSW 代替该项；
2. 人工刷新 `/workbench`、Session 深链和 Run 深链，确认请求顺序、URL 回填、404/500/网络断线提示和不伪造数据；
3. 对真实读模型只做前置条件核对：Alembic 迁移、连接目标、最小权限、可用 mock 数据、API 契约、回退路径与验收场景。未共同确认前不得连接真实 DB 或数据源；
4. 补足 mock 验收场景：空列表、cursor、归档、Run 404、跨 Session Run、网络失败；
5. 检查无旧 API、无 SQLite 运行时资产、无 `report/` 引入，也没有 P4/P5/P6 的假资源。

## 6. 验证与已知风险

P3.2b 已通过 `npm run typecheck`、`npm test`（2 files / 12 tests）和 `npm run build`。页面测试锁定成功深链的 Session → Runs → Message → Run 请求顺序，并回归 Runs 失败时下游不会被错误表示为空状态。构建仍有 Ant Design 主包体积警告（约 732 kB，gzip 约 234 kB），优化归入后续性能切片，不在本步通过拆包掩盖产品边界。

真实 FastAPI 返回的安全 500 不是前端缺陷的替代解释，也不是允许前端内置假数据的理由；它是 P3.2c 的联调前置风险。MSW 成功仅证明前端对已定义的契约响应可恢复，不能证明真实持久化读模型已可用。

## 7. 唯一下一步

P3.2c.2 已完成离线前置核对；用户决定真实数据库只读验收延后，详细 C1–C8 保留在 `step2c2-真实读模型前置条件核对.md` 作为后期强制门槛。

**当前唯一下一步：P3.3 Design：Run 受理、幂等与 SSE 恢复。**真实数据库验收延后；届时仍须先确认 C1–C8。
