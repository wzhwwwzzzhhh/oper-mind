# P3 独立审查 — 主前端工作台

> 日期：2026-07-28　|　结论：✅ P3.3a 已提交 `dc122cc`；当前进入 P3.3b 实现
>
> P3.3a 提交：`dc122cc feat: 完成P3.3a Run受理与幂等重试`　|　工作分支：`feat/p3-workbench`

## 1. 审查范围

本次审查 P3.3a 的前端实现：`POST /api/v1/sessions/{session_id}/runs`、`Idempotency-Key`、请求/trace 关联、202 深链、未知网络结果的同 key 重试、归档与安全错误。未实现 RunEvent、EventSource、完整结构化结果、Trace 跳转、Mock FastAPI SSE 或真实数据库联调。

## 2. 审查依据

- P2 合同与状态约束：`docs/开发/P0-V1产品化基线/api-v1-contract.md:426-503`；
- P2 路由：`backend/src/api/v1/routes.py:313-340`；
- P3.3 设计与 Step：`docs/开发/P3-主前端工作台/design.md`、`step3-run受理幂等与sse恢复.md`；
- 实现：`frontend/src/api/v1/client.ts`、`queries.ts`、`frontend/src/features/workbench/WorkbenchPage.tsx`；
- 测试：`frontend/src/api/v1/client.test.ts`、`frontend/src/app/App.test.tsx`、`frontend/src/test/handlers.ts`、`frontend/src/test/setup.ts`。

## 3. 独立审查结果

| 检查项 | 结论 | 审查结果 |
|---|---|---|
| v1 POST 契约 | 通过 | 只调用 `/api/v1/sessions/{session_id}/runs`；JSON body 为 `{ query }`，显式发送 `Idempotency-Key`，接受 `202 RunResponse`；未调用旧 `/diagnose` |
| 请求/Trace 关联 | 通过 | 每次 HTTP 尝试通过既有 client 新建 `X-Request-Id`，保持 response header / `meta` 诊断；成功 Run 深链只使用服务端响应的 `run.id` |
| 幂等重试 | 通过 | 网络或非 JSON 的受理结果未知时保存同一 key/query，显式“按原请求重试”复用 key；编辑 query 清除该重试上下文；不会自动 POST 或自动换 key |
| 安全错误 | 通过 | `409 IDEMPOTENCY_KEY_REUSED`、`SESSION_ARCHIVED`、`422`、`503` 均由安全 `ApiClientError` 呈现；`409` 不出现自动重试/换 key行为；SSE/Run failed 未被伪造 |
| 会话与缓存 | 通过 | 仅 active Session 显示输入；202 后失效当前 Session 的 Runs/Messages 与新 Run query，再跳转深链；归档只读 |
| P3.3b 边界 | 通过 | 没有 `GET /events`、EventSource、`after_sequence`、`Last-Event-ID` 或事件 UI；未提前进入 SSE/结果卡/Trace |
| 隔离与真实资产 | 通过 | 无后端、`report/`、`data/`、`frontend/mockup.html` 改动；未连接 8000、真实 DB/数据源，未运行 Alembic |
| 测试与构建 | 通过 | `npm run typecheck` 通过；`npm run test` 为 2 files / 17 passed；`npm run build` 通过。构建仅有非阻断的 chunk 大小提示 |

## 4. 审查发现与处理

- 新增 Ant Design `Input.TextArea` 后，jsdom 缺少 `ResizeObserver`，首次测试发生组件挂载错误。已在 `frontend/src/test/setup.ts` 增加最小测试专用 mock；随后完整前端测试恢复通过。该 mock 不进入生产代码。
- 初次 MSW fixture 漏写 `accepted_run_id` 常量，测试加载阶段立即失败；已补齐 fixture 并重新运行完整验证。最终结果为 17 项测试全部通过。
- P3.3a 没有为 malformed-but-JSON 的 RunResponse 新建第二套运行时 DTO 校验；这与现有 P3.2 OpenAPI 类型 + resource reader 边界一致。若真实契约发现字段缺口，必须先回到后端/合同 Design，不能在 UI 猜测资源。

## 5. 已知风险与非目标

1. 未知网络结果在整页刷新后不会保存幂等键或草稿，因而不会自动重试；这是避免无用户确认的重复 POST 与本地持久化敏感上下文的有意边界。
2. P3.3b 才会读取持久化事件和连接 SSE；P3.3a 的 queued Run 仅通过既有 Run 深链显示，不宣称实时进度。
3. P2 的 BackgroundTasks、SSE 短轮询、SQLite 并发和生产队列问题仍属于 P7。
4. 真实数据库/8000 后端验收仍须用户和数据库所有者后续确认 C1–C8；不得以本次 MSW 成功替代真实成功。

## 6. 结论与下一步

P3.3a 在既定范围内通过独立 Review。实现准确消费 P2 v1 Run 受理与幂等契约，覆盖关键成功、未知网络结果、冲突和归档路径，且没有跨入 Event/SSE、结果、真实基础设施或后续阶段。

**P3.3a 已提交。当前唯一下一步为 P3.3b：持久化事件与 SSE 恢复实现。**
