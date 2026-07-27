# P3 Step2b — Session 工作台只读 UI 与刷新/深链恢复

> 日期：2026-07-27　|　状态：✅ Code / Test / 独立 Review 完成，待用户授权暂存/提交
>
> 实现基线：`75d6598 feat: 完成P3.2a v1 API客户端与MSW契约`　|　分支：`feat/p3-workbench`

## Design

### 目标

把 P3.2a 的只读 v1 client 接入现有产品壳，提供 Session 导航、Session 详情、Run 列表、Message 时间线和已选 Run 的只读状态视图。页面既可从 `/workbench` 选择真实 Session，也可恢复以下深链：

```text
/workbench/sessions/:session_id
/workbench/sessions/:session_id/runs/:run_id
```

### 固定恢复顺序

对于 Session 深链，UI 只在前置读取成功后启动下一段：

```text
1. GET /sessions/{session_id}
2. GET /sessions/{session_id}/runs
3. GET /sessions/{session_id}/messages
4. URL run_id 优先；若没有则选 Run 列表首项并 replace 到 Run URL
5. GET /runs/{run_id}
```

根路由只读取 active Session 列表；无 Session 显示真实空状态，不自动创建或伪造数据。Session、Run、Message 的“加载更多”只使用相同资源列表返回的 opaque `page.next_cursor`，不会跨 Session 或筛选条件复用。

### 页面边界

- 左侧：active Session 列表、真实空状态、加载更多和安全读取错误。
- 主区：未选择 Session 的引导；Session 标题/归档只读状态；Run 列表；Message 时间线；选定 Run 的 status、关联 trace ID 和安全错误。Run result 只标记“结构化结果已持久化/待 P3.4 展示”，不绘制结果卡。
- Run 的 `session_id` 必须等于当前 URL Session；不一致时不显示跨会话内容，显示安全提示并保留可恢复的 Session 页面入口。
- 右栏仍只陈述 P4/P5/P6 未实现状态；不生成 Environment、DataSource、Alert、Incident、Approval、Knowledge、Report 或 Trace 的假内容。

### 错误与非目标

- `ApiClientError` 仅展示安全 `code`、message、request ID/trace ID；网络、取消和非 JSON 维持 transport/protocol 语义。
- Session/Run 404、归档、空列表与加载失败必须诚实显示；不能 fallback 为本地 mock、不能从 Zustand 恢复资源事实。
- 不接入写 API、SSE、RunEvent、完整结构化结果卡、Trace 跳转、后端、`report/`、`frontend/mockup.html`、真实 DB/数据源/认证。

## Code

- `frontend/src/app/App.tsx:1-86` 将产品壳收口为三个只读路由：`/workbench`、Session 深链和 Run 深链；右栏明确 P3.3/P3.4/P4/P5/P6 边界。
- `frontend/src/features/workbench/WorkbenchPage.tsx:91-429` 以 TanStack Query 恢复 active Session、指定 Session、分页 Run、分页 Message 和指定 Run。深链链式启用顺序是 Session → Runs → Message → Run；当 URL 无 Run 时，仅在 Message 恢复完成后选择首个已加载 Run 并 replace URL。
- `frontend/src/features/workbench/WorkbenchPage.tsx:250-313` 校验 `run.session_id`，不匹配时显示 `RUN_SESSION_MISMATCH`，不渲染跨会话内容；只显示 status/trace/安全 Run error 与“结构化结果待 P3.4 展示”提示。
- `frontend/src/features/workbench/resource-readers.ts:1-34` 只从生成 OpenAPI 类型的 `unknown` 字段安全读取显示值，不建立第二套 Session/Message/Run/Result DTO。
- `frontend/src/api/v1/client.ts:150-308` 在每次请求时读取当前 `fetch`，并将空 base URL 解析为浏览器同源 URL；这保证页面 MSW 测试和 Vite `/api` 代理使用同一客户端语义，不改变任何 v1 endpoint、verb 或重试行为。
- `frontend/src/test/handlers.ts:76-128` 的 mock handler 改为端口无关的 `/api/v1` URL 正则匹配，避免测试浏览器 origin 影响契约场景；仍只模拟五个 GET。

## Test 与人工验收

已在 `frontend/` 通过：

```text
npm run typecheck  → 通过
npm test           → 2 个测试文件、12 个测试通过
npm run build      → 通过
```

- `frontend/src/app/App.test.tsx:19-65` 覆盖 active Session 入口、Run 深链恢复、严格请求顺序、Session 404 安全错误和无创建控件。
- `frontend/src/api/v1/client.test.ts:50-55` 覆盖默认 client 在请求时读取当前 fetch，防止全局实例绕过 MSW；现有 request ID、cursor、安全错误、网络/abort/协议错误测试继续通过。
- 本机人工验收访问 `http://[::1]:5174/workbench`：当前真实后端仍返回安全 `INTERNAL_ERROR`，工作台显示通用错误、错误码与请求 ID；没有伪造 Session 或静默 fallback。此结果不等于真实读取成功，MSW 成功路径和真实错误路径分别验收。
- 构建仍有 Ant Design 主 bundle 超过 500 kB 的警告：约 732 kB（gzip 约 234 kB）。本 Step 增加工作台 UI，未做拆包优化。

## 独立 Review

- P2 契约：只有五个已批准 GET；列表 cursor 原样传递；ResponseMeta/X headers 错误语义沿用 P3.2a client。
- 刷新恢复：深链的请求顺序由页面测试锁定为 Session → Runs → Message → Run；无 Run URL 时才选择首个 Run，未越级读取 SSE/Event。
- 边界：未调用旧 `/diagnose` 或 `/diagnose/stream`，未调用 POST/PATCH/DELETE，不含 Run 受理、SSE、结构化结果卡、Trace 跳转或 P4/P5/P6 页面/假数据。
- 真实数据：MSW 仅供确定性测试；真实 FastAPI 返回安全 500 时页面如实展示，并未将它改写成空列表或本地数据。
- 隔离：未修改 `report/`、后端、数据、运行时 SQLite 或 `frontend/mockup.html`；三个外部隔离改动未读取、未暂存。

## 提交边界与唯一下一步

本 Step 暂存时仅包含 P3.2b 页面/测试/样式、为页面测试修正的 v1 client/MSW/Vitest 配置，以及文档、计划与镜像状态。不得包含任何隔离文件。

**用户授权提交后，唯一下一步为 P3.2c：mock FastAPI 联调、刷新/深链人工验收与真实读模型前置条件核对。**在访问真实持久化 API 前，必须共同确认应用数据库迁移、连接目标、最小权限、可用 mock 数据、接口契约、回退路径与验收场景；当前 `/api/v1/sessions` 安全 500 不是前端静默降级条件。
