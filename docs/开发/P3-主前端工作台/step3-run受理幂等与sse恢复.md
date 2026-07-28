# P3.3 Step 设计 — Run 受理、幂等与 SSE 恢复

> 日期：2026-07-28　|　状态：✅ P3.3b 已提交 `e7858ce`；✅ P3.3c 已提交 `ca899e0`；P3.4 Design 待开始
>
> 工作分支：`feat/p3-workbench`　|　设计基线：`87c4f83 docs: 完成P3.2c2离线前置核对`
>
> 关联：`design.md` 第 4–8 节、`docs/开发/P0-V1产品化基线/api-v1-contract.md` 第 5–7 节、`backend/src/api/v1/routes.py:313-429`、`backend/src/api/v1/sse.py:20-65`。

## 1. 目标与边界

本 Step 将 P3.3 拆成三个可独立 Review/Commit 的前端切片，保证“创建 Run、幂等重试、事件恢复、SSE 断线恢复”不会一次混入表单、网络协议、实时连接和 Mock 联调。

共同边界：仅消费 `/api/v1`；不修改 P2 后端、旧 `/diagnose`、`report/`、`data/`、真实数据库/数据源或 8000 后端；不实现 P3.4 结果卡、P4/P5/P6 资源或假数据。所有实际代码 Step 完成后各自 Review，未经用户授权不自动跨 Step。

## 2. P3.3a — Run 受理与幂等重试

### 交付

1. 扩展 `frontend/src/api/v1/client.ts`：基于 OpenAPI 的 `CreateRunRequest`/`RunResponse` 增加 JSON `POST`；每次 HTTP 尝试保留 `X-Request-Id` 校验，显式发送 UUID `Idempotency-Key`。
2. 增加 TanStack Query mutation 和最小 UI 局部状态：active Session 的 query 输入、提交、飞行中禁用、`202` 后以服务端 `run.id` 导航，并失效/刷新 Session Runs、Messages 和 Run。
3. 网络未知结果只显示“可按原请求重试”，复用同一 key 与未变 query；编辑或明确新建请求才换 key。刷新/深链不自动 POST。
4. 用 MSW/RTL 覆盖 POST、202、重试同 key、`409 IDEMPOTENCY_KEY_REUSED`、`409 SESSION_ARCHIVED`、`422`、`503`、归档禁用和导航。

### 不做

不读取 Event、不开 EventSource、不实现结构化结果；不扩展独立 Mock FastAPI；不将 query/幂等键持久化到 localStorage 或运行时文件。

### 建议验证

```powershell
Set-Location frontend
npm run typecheck
npm run test
npm run build
```

## 3. P3.3a 实现记录与验证

### 实际交付

- `frontend/src/api/v1/client.ts` 以 OpenAPI 的 `CreateRunRequest` 和 `RunResponse` 扩展 JSON `POST`，同时发送 `Content-Type`、每次请求独立的 `X-Request-Id` 与调用方明确提供的 `Idempotency-Key`；既有 headers/meta 关联诊断保持生效。
- `frontend/src/api/v1/queries.ts` 增加窄的 `create_run_mutation()`，不复制 Run 服务器状态。
- `frontend/src/features/workbench/WorkbenchPage.tsx` 仅在 active Session 显示问题提交区：飞行中禁用、`202` 后以响应 `run.id` 跳转、失效 Runs/Messages/Run 查询；网络或非 JSON 的受理结果未知时显示“按原请求重试”，复用同一 key/query；`409/422/503` 显示安全错误且不自动换 key 重发；刷新不自动 POST。
- MSW、client 与 App 测试覆盖 POST body/headers、202 深链、同 key 重试且请求 ID 不同、`IDEMPOTENCY_KEY_REUSED` 不盲重试、归档禁用。测试 setup 增加仅 jsdom 使用的 `ResizeObserver` 最小 mock，支持 Ant Design `Input.TextArea` 挂载。

### 已通过验证

```text
frontend: npm run typecheck  → 通过
frontend: npm run test       → 2 files / 17 tests passed
frontend: npm run build      → 通过
```

构建只报告现有单个产物超过 500 kB 的 Vite chunk 提示（主要来自 UI 依赖），没有阻断构建；拆包优化不混入本 Step。

## 4. P3.3b — 持久化事件与 SSE 恢复

### 交付

1. 扩展 v1 client/Query：`GET /runs/{run_id}/events` cursor 读取，保持 opaque cursor；以 `session_id + run_id` 隔离缓存。
2. 建立纯前端事件合并器和窄运行时解析：按 `(run_id, sequence)` 去重、`sequence asc` 排序、拒绝 Run 不匹配或畸形帧，不把未知 data 解释为完整 Trace。
3. 为 queued/running Run 建立可注入、可测试的原生 EventSource 生命周期：初连 URL 不带 `after_sequence`；浏览器自动重连利用 SSE `id` 的 `Last-Event-ID`；组件卸载/切 Run/终态时关闭旧流。
4. `onerror` 显示恢复提示并由 REST Run/Events 重同步；不将连接失败写为 Run failed。`GET /events` 明确 cursor 错误时清空本地事件后重新从首个可用页读取。
5. 以 MSW 和 EventSource fake 覆盖去重、排序、终态关闭、页面卸载、恢复提示、无双流、无 `after_sequence` 和终态重读。

### 不做

不改后端 SSE 协议；不使用 fetch 流替换 EventSource；不读取 SSE response headers、不手工设置 Last-Event-ID/X-Request-Id；不提前制作完整结果或 report 入口。

### 实现记录与验证

- v1 client 增加 `GET /api/v1/runs/{run_id}/events` 和 opaque cursor 类型/Query key；每页仍发送 `X-Request-Id` 并保留 headers/meta 关联诊断。
- 新增纯前端 RunEvent 解析/合并器：只接受当前 Run、正整数 sequence、合同内事件 type、UTC `Z` 时间和对象 data；按 `(run_id, sequence)` 首次合法事件去重并升序排序，REST 与 SSE 共用。
- 仅 queued/running Run 建立原生 `EventSource('/api/v1/runs/{run_id}/stream')`；初始 URL 不带 `after_sequence`，浏览器负责自动重连的 `Last-Event-ID`。切换/卸载/终态均关闭旧连接。
- `error` 仅显示“事件连接中断，正在从持久化记录恢复”，调用 REST Run/Event 重同步且不建立第二条流；不把连接失败写为 Run failed。终态事件关闭流并重读 Run、Event、Session Runs 和 Messages。
- 新增 TestEventSource 和 MSW event fixture，覆盖 REST cursor、合法性拒绝、去重/排序、无 `after_sequence`、断线 REST 重同步不双开、终态关闭/重读。

```text
frontend: npm run typecheck  → 通过
frontend: npm run test       → 3 files / 22 tests passed
frontend: npm run build      → 通过
```

构建仅有既有单一 chunk 超过 500 kB 的非阻断提示；不在本 Step 混入拆包优化。


### 建议验证

```powershell
Set-Location frontend
npm run typecheck
npm run test
npm run build
```

## 5. P3.3c — Mock FastAPI SSE 契约验收

### 交付

1. 在 `frontend/scripts/` 的独立 Mock FastAPI 内以进程内确定性数据扩展 POST Run、同 key 重放/冲突、事件列表和有限 SSE 流；不接入真实 P2 persistence。
2. 对 mock 脚本测试：首次 `202`、相同 key/query 的同 Run/trace、不同 query 的安全 `409`、SSE `id`/`run_event` 帧、Last-Event-ID 续传、终态自动关闭。
3. 启动独立 mock 与独立 Vite 实例，人工验收 active 提交、刷新、断线恢复、终态与安全错误；结束后关闭临时进程，不改用户的 5174/8000 实例。
4. 完成 P3.3c 独立 Review、更新 HANDOFF，并在用户完成可视化主流程验收后等待提交授权。

### 不做

不连接真实数据库、真实后端或数据源；不以 mock 证明真实接入成功；不运行在线 Alembic；不修改 `report/` 或后端业务代码。

## 6. 实现前置与停止条件

- OpenAPI 若缺少 POST header、RunEvent list 或 SSE 字段，先核对真实 `/openapi.json` 与 P2 合同；不能手写漂移 DTO。
- 浏览器 EventSource 无法设置请求 headers/读取响应 headers 是既定平台边界；若未来需要自定义首帧游标或认证，先进行独立协议 Design。
- 任何真实数据库/8000 后端联调仍须用户/数据库所有者重启 C1–C8 确认流程；本 Step 不因用户已启动服务而默认连接。
- 任一测试发现 Run 受理重放、sequence、终态不可逆或安全错误与 P2 不一致，停止前端实现并回写契约差异，不以本地假状态绕过。

## 7. 当前状态与唯一下一步

P3.3b 已完成独立 Review 并提交为 `e7858ce feat: 完成P3.3b持久化事件与SSE恢复`。P3.3c 已仅扩展 `frontend/scripts/mock_v1_api.py` 及其 pytest：Run 受理使用 UUID 幂等键的确定性进程内状态；同 key + 规范化 query 重放同一 Run/trace；不同 query 安全 `409 IDEMPOTENCY_KEY_REUSED`；不同 key 产生不同 Run/trace；RunEvent REST 按 cursor 分页；SSE 返回 `id: sequence`、`event: run_event`、Run 自身 trace，支持 Last-Event-ID / after_sequence、双游标冲突 `400` 和终态关闭。未改后端、真实数据库、8000 或 `report/`。

```text
frontend: npm run test:mock-api → 10 passed（TestClient 的 httpx 弃用警告不阻断）
frontend: npm run typecheck     → 通过
frontend: npm run test          → 3 files / 22 passed
frontend: npm run build         → 通过（仅既有 >500 kB chunk 非阻断提示）
独立验收：8100 mock + 5175 Vite（VITE_API_PROXY_TARGET=http://127.0.0.1:8100）
          根页面/代理、202 受理、同 key 重放、不同 key、Last-Event-ID 续传 2/3、
          REST cursor 恢复 1/2/3、终态 succeeded、双游标 400 均通过；临时进程已关闭。
```

用户已按独立 8100 Mock + 5175 Vite 完成可视化主流程验收，确认“开始诊断 → 事件到 succeeded → 刷新深链恢复”通过。代理 HTTP 验收与可视化验收均不接触 8000/真实数据库。**P3.3c 已提交为 `ca899e0`；P3.4 Design 已完成并独立审查通过，当前唯一下一步为 P3.4a：结构化结果读取模型与摘要面板实现（需用户后续代码授权）。**