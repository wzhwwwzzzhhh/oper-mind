# M7 Step1 — 同步诊断闭环

> 日期：2026-07-24　|　状态：✅ 通过　|　关联 commit：本提交（见 Git 历史）

## Design

在不引入 trace 图或 SSE 的前提下，让用户能通过同步 `POST /diagnose` 走完整链路：输入问题、等待编排完成、查看最终报告、复制报告、处理后端错误。这样即使流式接口暂不可用，答辩演示也已经有稳定主路径。

## Step

1. 扩展 M6 的 TypeScript 契约：`DiagnoseResponse`、`TraceEvent` 与健康检查类型保持同源。
2. 实现带运行时契约校验的 `POST /diagnose` 客户端，固定发送 `show_thinking=true`。
3. 实现输入表单、快速场景、loading、错误提示、报告展示与复制。
4. 增加客户端成功、后端错误、响应漂移三个单元测试。
5. 不渲染 Trace 事件详情、拓扑或过程视图；仅在报告元信息中显示 trace / thinking 数量；不创建 SSE 客户端、不引入图表依赖。

## Code

- `src/frontend/src/types/api.ts:1-30`：补齐 M6 同步诊断与 trace 类型。
- `src/frontend/src/api/diagnosis.ts:1-73`：同步请求、统一错误读取与运行时响应校验。
- `src/frontend/src/api/diagnosis.test.ts:1-99`：成功、422 错误体、缺字段响应的 Vitest 覆盖。
- `src/frontend/src/App.tsx:1-136`：诊断会话状态、AbortController、表单、快速场景、报告与复制。
- `src/frontend/src/styles/global.css:1-76`：输入区、报告区、加载骨架、错误态与桌面布局。
- `src/frontend/package.json:1-24`：新增 `npm run test`（Vitest）。

## Test

```text
npm run test       → 1 file / 6 tests passed
npm run typecheck  → passed
npm run build      → passed
```

构建产物 gzip 后主 JS 约 64 kB；本 Step 未新增 SSE 或 ECharts 依赖。

## Review

- 审查人：Averroes（独立 code-review agent），审查日期：2026-07-24。
- 审查结论：无 P0/P1 阻塞项；确认同步 `POST /diagnose` 与 M6 契约一致，未提前混入 SSE、Trace 拓扑或 ECharts。
- 审查建议与处置：
  1. Trace 的 `node/detail/timestamp` 应匹配后端 `min_length=1`；已在 `src/frontend/src/api/diagnosis.ts:14-27` 收紧为非空文本校验，并补空文本拒绝测试。
  2. 文档“无 Trace”应明确为不渲染事件详情、拓扑或过程视图；保留报告元信息中的 trace / thinking 数量，已修正表述。
  3. 补齐 AbortSignal 透传和非 JSON HTTP 错误响应测试。
- 复验：`npm run test`（6 passed）、`npm run typecheck`、`npm run build` 均通过。
- 结论：**通过**。
