# M7 Step2 — Trace 回放与三路拓扑

> 日期：2026-07-24　|　状态：✅ 通过，待提交　|　分支：`feat/m7-frontend-visualization`

## Design

同步接口已经返回完整 trace，但 M7.1 只展示统计数量。本 Step 把 trace 变成可回放的固定拓扑，要求 direct / chain / parallel 的差异由事件序列本身决定；不接 SSE，不把“同步返回”伪装成“实时流”。

为了保证未启动后端时也能演示，提供三个与后端 graph trace 语义一致的 fixture；当本次同步诊断有 trace 时，用户可切换到真实结果回放。真实 trace 是过程唯一事实：只有 `conflict_check` 明确为 `分歧=false` 时才跳过 Debate，且真实响应未给 strategy 时仅从 route trace 回退解析，绝不借用 fixture 策略。

## Step

1. 定义 direct / chain / parallel 的固定 trace fixture。
2. 将可见事件前缀映射为 route、领域 Agent、Conflict、Debate、Report、Reflection 的节点状态。
3. 为 direct 标记非目标 Agent 为跳过；为 chain 逐层完成；为 parallel 同时完成全部领域 Agent。
4. 增加“从头播放 / 下一步”控制和事件日志。
5. 在 M7.1 报告下方接入回放组件，保留同步诊断和 fixture 两种来源。
6. 根据独立审查修复 Debate 状态机和真实 trace 的策略回退。

## Code

- `src/frontend/src/trace/replay.ts:1-150`：fixture、纯状态映射、基于 `conflict_check` detail 的 Debate 语义，以及 route trace 策略解析。
- `src/frontend/src/trace/replay.test.ts:1-67`：direct、chain、parallel、`分歧=true/false` 与策略解析测试。
- `src/frontend/src/components/trace/TracePlayback.tsx:1-114`：来源切换、定时回放、真实 response 的 strategy 回退和拓扑节点。
- `src/frontend/src/App.tsx`：在同步报告后接入回放组件，明确 M7.2 不接 SSE。
- `src/frontend/src/styles/global.css`：回放控制、三种领域节点、质量节点和日志样式。

## Test

```text
npm.cmd run test       → 2 files / 12 tests passed
npm.cmd run typecheck  → passed
npm.cmd run build      → passed
```

测试覆盖 direct 单 Agent 跳过、chain 逐层完成、parallel 并发完成、`分歧=true` 时 Debate 保持等待、`分歧=false` 时跳过 Debate，以及从 route trace 解析策略。定时器清理设计已在 effect / replay 路径中覆盖；不为本 Step 引入新的组件测试依赖，留待 M7.5 浏览器验收。

## Review

- 初始独立审查人：Ohm（2026-07-24）。发现：P1（`分歧=true` 被错误显示为 Debate 跳过）、P2（真实 trace strategy 为空时借用 fixture 策略）、P2 非阻塞（建议增加定时器组件测试）。
- 处置：已修复 P1/P2 并扩充纯函数测试；定时器测试列入 M7.5 浏览器验收。最终复审：Ohm（2026-07-24）确认 P1/P2 已正确修复，无 P1/P2/P3 新增问题；允许进入提交阶段。
