# M7 Step3 — SSE 实时增量与同步降级

> 日期：2026-07-24　|　状态：✅ 通过，待提交　|　分支：`feat/m7-frontend-visualization`
> 稳定基线：`070808c feat: 完成M7三路Trace回放`

## Design

M6 已提供 `GET /diagnose/stream?query=...`：命名事件 `progress` 携带单条 trace，`complete` 携带最终 `result / strategy / trace`，`error` 携带统一错误体。本 Step 将它接入 M7.2 的 TracePlayback，使节点跟随 `progress` 增量点亮；不改变后端契约，不引入 SSE 重连或第二套后端状态机。

SSE 是增强路径而不是单点依赖：流建立失败、网络断流、收到后端 `error`，或用户选择结束流式模式时，关闭 EventSource 并只执行一次已有 `POST /diagnose`，给出明确的“已切换同步诊断”提示。手动取消旧请求不会触发降级，避免新旧请求串扰。

## Step

1. 定义前端 SSE progress / complete / error 类型和运行时校验。
2. 实现可取消、可注入测试的 EventSource 客户端；终态必须关闭连接，避免浏览器自动重连。
3. 将 App 的诊断入口改为优先 SSE，progress 直接更新实时 trace，complete 渲染最终报告。
4. 建立单次降级保护，流异常时关闭连接并使用同步 API；提供“改用同步完成”入口。
5. 让 TracePlayback 支持实时 trace 来源；首条真实事件到达前不显示 fixture，保持 fixture 回放能力。
6. 用 Vitest 覆盖解析、终态关闭、服务错误、浏览器断流、创建失败与取消语义。

## Code

- `src/frontend/src/api/stream.ts:86-150`：基于命名 SSE 事件的订阅客户端；校验 progress / complete / error，所有终态关闭连接，创建失败也交给调用方降级。
- `src/frontend/src/api/stream.test.ts:34-101`：覆盖 query 编码、progress、complete 关闭、服务 error、无 payload 浏览器断流、创建失败和取消后的迟到事件。
- `src/frontend/src/App.tsx:56-131`：以 `runIdRef` 隔离旧请求，以 `fallbackStartedRef` 保证每次诊断最多一次同步 fallback，并提供主动切换同步入口。
- `src/frontend/src/components/trace/TracePlayback.tsx:35-129`：实时 trace 直接点亮；实时开始时自动选择“本次诊断”，尚无事件时保持空过程而不是借用 fixture；完成后保留完整真实 trace。
- `src/frontend/src/styles/global.css:117-121`：同步降级按钮和实时接收状态样式。
- `docs/开发/M7-前端可视化/step4-指标看板ECharts.md`：修正原计划文档的 Step 编号，避免与本 Step 冲突。

## Test

```text
npm.cmd run test       → 3 files / 18 tests passed
npm.cmd run typecheck  → passed
npm.cmd run build      → passed
git diff --check       → passed
```

后端既有 SSE 回归 `tests/test_api.py` 本应同时执行，但本机 `.venv\Scripts\python.exe` 指向不存在的 Python 3.11 解释器，且当前没有可用系统 Python，因环境失效未能启动；本 Step 未改动后端 SSE 契约。前端运行时校验严格消费该既有契约。

## Review

- 独立审查人：Ohm（2026-07-24）。
- 结论：无 P1/P2；确认 EventSource 的 progress / complete / error 解析与终态关闭、创建失败、单次 fallback、旧 run 隔离、实时空态和完成后真实 trace 保留均正确；未混入 ECharts 或后端改动。
- P3 建议：补充浏览器 transport error（无 payload）的测试。已在 `stream.test.ts` 补齐并复验通过。
