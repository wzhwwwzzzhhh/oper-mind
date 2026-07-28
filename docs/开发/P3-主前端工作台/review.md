# P3 独立审查 — 主前端工作台

> 日期：2026-07-28　|　结论：✅ P3.3c Mock FastAPI SSE 通过代码、自动、独立代理与用户可视化验收的独立 Review，等待提交授权
>
> 审查基线：`e7b34a5 docs: 校正P3.3b提交状态并进入P3.3c`　|　待审文件：`frontend/scripts/mock_v1_api.py`、`frontend/scripts/test_mock_v1_api.py` 及本轮状态文档　|　工作分支：`feat/p3-workbench`

## 1. 审查范围

本次审查 P3.3c 的独立 Mock FastAPI：P2 Run 受理幂等、RunEvent REST cursor、有限 SSE 重放、Last-Event-ID 续传、终态关闭和 Vite 代理边界。未修改 P2 后端协议、旧接口、`report/`、真实数据库/8000，也未进入 P3.4 结构化结果。

## 2. 审查依据

- 合同与恢复语义：`docs/开发/P0-V1产品化基线/api-v1-contract.md:426-503`；
- P2 路由/SSE：`backend/src/api/v1/routes.py:313-429`、`backend/src/api/v1/sse.py:20-65`；
- P3.3 设计与 Step：`docs/开发/P3-主前端工作台/design.md`、`step3-run受理幂等与sse恢复.md`；
- 本轮实现与测试：`frontend/scripts/mock_v1_api.py`、`frontend/scripts/test_mock_v1_api.py`；
- 自动验证：`npm run test:mock-api`、`npm run typecheck`、`npm run test`、`npm run build`；
- 独立代理验收：临时 `8100` Mock + `5175` Vite（明确 `VITE_API_PROXY_TARGET=http://127.0.0.1:8100`）。

## 3. P3.3c 独立审查结果

| 检查项 | 结果 | 审查结论 |
|---|---|---|
| Run 受理与幂等 | 通过 | 首次 `202` 为 queued；同 key + 规范化 query 重放同 Run/trace；不同 query 为安全 `409 IDEMPOTENCY_KEY_REUSED`；不同 key 稳定产生不同 Run/trace，且不同 Run 的首条 RunEvent ID 不复用 |
| RunEvent REST | 通过 | 仅进程内确定性事件；按 sequence 升序，`event-page-2` 补齐 2/3；RunEvent envelope 的 `meta.trace_id` 使用所属 Run，而不是静态全局 trace |
| SSE 合同 | 通过 | 帧固定 `id: sequence`、`event: run_event`；Last-Event-ID=1 仅重放 2/3；Run ID/trace 与事件 envelope 一致；`run_succeeded` 后生成器结束 |
| 事件游标安全 | 通过 | `after_sequence` 与 Last-Event-ID 同值可用；不一致或超界/非法值返回安全 `400 INVALID_EVENT_CURSOR`；未引入浏览器 EventSource 的双游标行为变更 |
| 独立代理边界 | 通过 | 临时 `8100` Mock 与 `5175` Vite（代理显式指向 8100）完成根页、读取、POST、SSE、恢复、终态和安全错误的真实 HTTP 验收；临时进程和端口均已关闭；没有访问 8000/5174 |
| 自动质量门 | 通过 | `npm run test:mock-api` 10 passed；`npm run typecheck`；`npm run test` 3 files / 22 passed；`npm run build` 通过 |
| P3/P4–P6 与真实资产边界 | 通过 | 仅改 `frontend/scripts/` mock 与测试；未改后端、`report/`、数据库、Alembic、旧 `/diagnose*` 或真实数据源 |
| 可视化人工验收 | 通过 | 用户已在独立 8100 Mock + 5175 Vite 下确认“开始诊断 → 事件到 succeeded → 刷新深链恢复”主流程通过；未使用或改动 8000/5174 |

## 4. 审查发现与处理

1. 初版 mock 把 `StreamingResponse | JSONResponse` 标注为 FastAPI 路由响应模型，FastAPI 在收集阶段拒绝该 Union；已在 SSE 路由显式 `response_model=None`，mock 测试恢复通过。
2. 初版 mock 对不同幂等键使用固定 Run/trace，不能准确模拟 P2 的“不同 key 创建不同 Run”；现已用 UUID5 从 key 确定性派生 Run/trace/input message，并增加不同 key 及跨 Run RunEvent ID 唯一性断言。
3. 初版新受理 Run 的 REST RunEvent envelope 使用静态 trace；已改为对应 Run trace，并通过独立 5175→8100 代理验收验证 SSE event/meta 与 Run 一致。
4. Vite production build 仍有单一 chunk 大于 500 kB 的既有非阻断提示；本 Step 不混入拆包优化。

## 5. 已知风险、非目标与待确认项

1. Mock 是进程内确定性验收夹具，不是 P2 persistence、后台执行器或真实队列；通过 mock 不代表真实数据库/8000 联调成功。
2. 用户可视化验收已通过；后续回归仍应保持独立 8100/5175，不以用户运行中的 5174/8000 取代。
3. 真实数据库和真实数据源验收继续严格延后，C1–C8 不降低；不运行在线 Alembic、不修改 8000 后端。
4. P3.4 以前不实现结构化结果卡、Trace 跳转、环境/数据源/告警/Incident/Approval/知识等能力。

## 6. 结论与下一步

P3.3c 的代码、自动测试、独立 Mock/Vite 代理契约和用户可视化主流程验收均通过，未发现阻止提交的协议或边界问题。

**当前唯一下一步：等待用户提交授权；提交后进入 P3.4 Design：结构化结果、失败/空/归档收口与受控 Trace 入口。**
