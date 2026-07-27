# P3 独立审查 — 主前端工作台

> 日期：2026-07-27　|　结论：🟡 P3.2b 已提交 `3170e6a`；P3.2c.1 已通过独立 Review，待用户授权暂存/提交
>
> 已提交基线：`12bed37 docs: 完成P3主前端工作台设计`、`4862752 feat: 初始化P3主前端工程与产品外壳`、`ec45ee2 docs: 完成P3.2接口与恢复读模型设计`、`75d6598 feat: 完成P3.2a v1 API客户端与MSW契约`、`3170e6a feat: 完成P3.2b会话工作台只读恢复`

## 1. 审查范围

本次只审查 P3.2c.1：独立 mock FastAPI、可切换 Vite `/api` 代理、刷新/深链与错误态人工验收。它不审查或修复真实 `8000` 后端的持久化 500，也不进入真实读模型、数据源或认证。

## 2. 审查依据

- P2 读取契约：`backend/src/api/v1/routes.py:169-386`、`backend/src/api/v1/schemas.py:27-318`、`docs/开发/P0-V1产品化基线/api-v1-contract.md:426-514`；
- P3.2 已提交基线：`frontend/src/api/v1/client.ts`、`frontend/src/features/workbench/WorkbenchPage.tsx`、`frontend/src/test/handlers.ts`；
- c.1 实现：`frontend/scripts/mock_v1_api.py`、`frontend/scripts/test_mock_v1_api.py`、`frontend/vite.config.ts`、`frontend/package.json`；
- 联调记录：`step2c1-mock-fastapi联调验收.md`、浏览器人工验收与 mock 请求日志。

## 3. 独立审查结果

| 检查项 | 结论 | 审查结果 |
|---|---|---|
| P2 API 契约 | 通过 | mock 只模拟五个既有 GET，保留 UUID、UTC `Z`、opaque cursor、安全 error、`meta` 和关联 headers；未臆造 Result 单端点或写契约 |
| 代理隔离 | 通过 | Vite 默认仍指向 `127.0.0.1:8000`；只在独立 5175 验收实例用 `VITE_API_PROXY_TARGET` 指向 8100；原有 5174/8000 未停止或改写 |
| P3/P4/P5/P6 与旧 API | 通过 | mock 不提供 POST/PATCH/DELETE、Idempotency-Key、SSE/Event、旧 `/diagnose`、`report/`、P4/P5/P6 资源或假数据 |
| 刷新与深链 | 通过 | 浏览器验证根入口、Session 深链 Run URL 回填、Run 深链刷新；每一轮读取保持 Session → Runs → Message → Run |
| cursor / 归档 / 隔离 | 通过 | active cursor 第二页校正为 active Session；归档 Session 为只读真实空状态；跨 Session Run 显示 `RUN_SESSION_MISMATCH`，不展示内容 |
| 错误与断线 | 通过 | Run 404 和 mock 500 均显示安全错误/关联 ID；mock 上游中断经 Vite 时为非 JSON 代理响应，客户端显示 `INVALID_API_RESPONSE`，没有伪造空数据或成功 |
| 测试与构建 | 通过 | mock TestClient 4 passed、前端 typecheck、Vitest 12 passed、Vite build 通过 |
| 运行时资产与隔离 | 通过 | 未改 `backend/`、`report/`、`data/`、`frontend/mockup.html`；未创建 SQLite；8100/5175 临时进程和浏览器 tab 已关闭 |
| 文档与唯一下一步 | 通过 | A/B Plan、P3 design/step/review/HANDOFF、规则镜像均同步为 c.1 待提交，下一步限制为 c.2 前置核对 |

## 4. 发现与处置

1. **发现：开发模式会重复请求。**React `StrictMode` 的开发期双挂载使 mock 日志出现重复轮次。处置：按单轮请求组核对，组内仍严格为 Session → Runs → Message → Run；不将重复读误判为 cursor 或业务重试。
2. **发现：`status=active` 的第二页 mock 曾返回 archived Session。**处置：MSW 与 FastAPI mock 同步改为第二个 active Session，新增 mock 契约断言并完成浏览器“加载更多”验收。
3. **发现：上游 mock 停止后不是浏览器级 fetch 失败。**Vite 代理返回非 JSON 错误页，因此正确分类为 `INVALID_API_RESPONSE`；既有 client/MSW 测试仍负责 `NETWORK_ERROR`。两种传输故障不混称。

## 5. 验证与已知风险

```text
npm run test:mock-api  → 4 passed（FastAPI TestClient 有 1 条既有弃用警告）
npm run typecheck      → 通过
npm test               → 2 个测试文件、12 个测试通过
npm run build          → 通过
```

构建继续提示 Ant Design 主 bundle 超过 500 kB（约 732 kB，gzip 约 234 kB），不属于 c.1 的范围。真实 `GET /api/v1/sessions` 返回安全 500 的根因未读取、未修复；c.1 成功不等价于真实持久化读模型可用。

## 6. 结论与唯一下一步

P3.2c.1 在既定隔离边界内通过独立 Review，可以进入提交候选。建议提交信息：`feat: 完成P3.2c1 mock FastAPI联调验收`。

**P3.2c.1 提交后的唯一下一步为 P3.2c.2：真实读模型前置条件核对。**只可共同确认迁移、连接目标、最小权限、可用 mock 数据、契约、回退路径与验收场景；未确认前不得连接真实 DB 或数据源。
