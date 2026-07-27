# P3.2c.1 Step — mock FastAPI 联调与刷新/深链验收

> 日期：2026-07-27　|　状态：🟡 Code / Test / 独立 Review 完成，待用户授权暂存/提交
>
> 分支：`feat/p3-workbench`　|　实现基线：`3170e6a feat: 完成P3.2b会话工作台只读恢复`

## 1. 目标与拆分

P3.2c 按风险与环境边界拆为两个独立小步：

1. **P3.2c.1（本 Step）**：使用独立 mock FastAPI 进程验证 Vite `/api` 代理、P2 JSON envelope、刷新与深链恢复；
2. **P3.2c.2（后续）**：仅核对真实读模型的迁移、连接目标、最小权限、可用 mock 数据、接口契约、回退路径与验收场景。

c.1 不连接真实数据库、诊断数据源或认证，不修改真实后端 `/api/v1`、`report/`、`frontend/mockup.html`、Alembic、`data/` 或运行时资产。

## 2. 实现与边界

- `frontend/scripts/mock_v1_api.py` 是**仅本地验收**的独立 FastAPI 进程，默认监听 `127.0.0.1:8100`；只开放：
  - `GET /api/v1/sessions`；
  - `GET /api/v1/sessions/{session_id}`；
  - `GET /api/v1/sessions/{session_id}/runs`；
  - `GET /api/v1/sessions/{session_id}/messages`；
  - `GET /api/v1/runs/{run_id}`；
  - mock 自身 `/health` 与只读 `/__mock__/requests` 验收日志。
- mock 复用 P3.2a 的确定性 UUID、UTC `Z`、不透明 cursor、安全 404/500、`meta.request_id`/`meta.trace_id` 和 `X-Request-Id`/`X-Trace-Id` 语义；没有 POST/PATCH/DELETE、`Idempotency-Key`、SSE/Event、旧 `/diagnose`、认证、数据库或数据源连接。
- `frontend/vite.config.ts` 保持默认代理 `http://127.0.0.1:8000`；仅以 `VITE_API_PROXY_TARGET=http://127.0.0.1:8100` 启动**第二个** Vite 实例时切换代理目标。用户原有 `5174` 前端和 `8000` 后端未停止、未修改。
- `frontend/scripts/test_mock_v1_api.py` 直接验证 mock 进程的五个 GET envelope、请求 ID 回显、安全 404/500、cursor 与恢复请求顺序；它不替代浏览器代理验收。
- `frontend/src/test/handlers.ts` 的 active Session 第二页已校正为另一个 active Session，避免 `status=active` 的 cursor 场景错误混入 archived Session。

## 3. 独立人工验收

临时启动 8100 mock 与 5175 前端实例后，浏览器通过 Vite `/api` 代理完成以下验收；临时进程均已清理：

| 场景 | 结果 |
|---|---|
| `/workbench` | 恢复 active Session 列表；加载更多后显示第二页 active Session |
| Session 深链 | `/workbench/sessions/{session_id}` 在 Message 恢复成功后 replace 为首个 Run URL |
| Run 深链与刷新 | 读取顺序保持 Session → Runs → Message → Run；刷新后仍恢复同一 Run |
| Run 404 | 显示 `RUN_NOT_FOUND`、安全消息、request ID 与 trace ID，不伪造 Run |
| mock 500 | 显示 `INTERNAL_ERROR`、安全消息、request ID 与 trace ID，不伪造 Session 或空列表 |
| archived Session | 显示只读归档提示与真实空 Run/Message，不提供编辑或重新激活 |
| 跨 Session Run | 显示 `RUN_SESSION_MISMATCH`，不渲染跨会话内容 |
| mock 上游中断 | Vite 代理返回非 JSON 错误页，客户端诚实显示 `INVALID_API_RESPONSE`；不伪造成业务成功或空数据 |

开发模式的 React `StrictMode` 会产生重复挂载与重复读取；mock 请求日志显示每一轮读取内部仍按 Session → Runs → Message → Run 顺序执行。浏览器级 fetch 失败的 `NETWORK_ERROR` 已由 P3.2a client/MSW 测试覆盖；代理上游中断实际属于非 JSON 协议错误，二者不可混称。

## 4. 验证

在 `frontend/` 已通过：

```text
npm run test:mock-api  → 4 passed（FastAPI TestClient 有 1 条既有弃用警告）
npm run typecheck      → 通过
npm test               → 2 个测试文件、12 个测试通过
npm run build          → 通过
```

构建仍保留 Ant Design 主 bundle 超过 500 kB 的警告（约 732 kB，gzip 约 234 kB）；本 Step 不通过拆包扩大范围。

## 5. 提交边界与唯一下一步

本 Step 暂存只包含：`frontend/package.json`、`frontend/vite.config.ts`、`frontend/src/test/handlers.ts`、`frontend/scripts/mock_v1_api.py`、`frontend/scripts/test_mock_v1_api.py`、P3 文档/计划与规则镜像。不得包含 `backend/`、`report/`、`data/`、运行时 SQLite、`frontend/mockup.html` 或任何外部隔离文件。

建议提交信息：`feat: 完成P3.2c1 mock FastAPI联调验收`。

**提交后的唯一下一步为 P3.2c.2：真实读模型前置条件核对。**只可确认迁移、连接目标、最小权限、可用 mock 数据、接口契约、回退路径和验收场景；未共同确认前不得连接真实 DB 或数据源。
