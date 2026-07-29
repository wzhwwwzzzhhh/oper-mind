# P3.6a Step4 — 会话壳与只读 Turn 投影

> 日期：2026-07-29　|　状态：✅ Code/Test/Review/人工验收完成，待提交　|　范围：`frontend/` 只读投影
>
> 设计依据：`step1-个人会话主体验设计.md`、`step2-会话契约与恢复设计.md`、`step3-后续最小切片与验收设计.md`

## 1. 目标与范围

把既有 P2 的 Session、Message、Run、Result **只读**投影为个人会话中的 Conversation Turn：用户问题是主线，关联 Run 表示调查，已持久化 assistant Message 才是助手答复，结构化 Result 仅在答复内按需展开。

本 Step 不发送问题、不调用 `POST /api/v1/sessions/{session_id}/runs`、不创建 Session、不订阅 SSE、不修改 Mock/后端/`report/`，也不接入真实 8000、数据库、数据源、认证或运行时资产。

## 2. 实现设计

### 2.1 恢复顺序和读取边界

`SessionWorkspace` 固定以 `Session → Session Runs → Session Messages` 顺序读取，分别调用既有 P2 的：

- `GET /api/v1/sessions/{session_id}`；
- `GET /api/v1/sessions/{session_id}/runs`；
- `GET /api/v1/sessions/{session_id}/messages`。

三者都沿用既有 request/trace 诊断处理与正序 cursor。Runs 和 Messages 如仍有下一页，用户可以明确继续加载；页面不声称已展示完整长期历史，也不擅自改写为“最近优先”语义。

### 2.2 Turn 投影规则

新增纯前端 `project_conversation_turns()`：

1. 用 `Run.input_message_id` 将调查挂到同一 Session 的 user Message；
2. 用 assistant Message 的 `run_id` 将已保存答复挂回该调查；
3. succeeded + assistant Message + 合法 Result：显示答复，Result 放在“展开结论、证据与建议”；
4. succeeded 缺少 assistant Message：显示 `ANSWER_RECOVERY_PENDING`，绝不根据 Result 合成答复；
5. failed/cancelled/queued/running：只显示对应调查状态，不伪造答复或实时过程；
6. 重复/缺失/跨 Session 关联、非法字段或 Result 结构异常：显示协议异常；重复关联不任意选择某条 Run/Message。即使 Result 不合法，已持久化 assistant Message 仍保留可读。

旧 `/workbench/sessions/:session_id/runs/:run_id` 深链保留兼容，但回到对应会话投影，且本 Step 不再读取单个 Run 或展示选中 Run 面板。

### 2.3 产品与能力边界

- 主导航和页头改为“我的会话 / 个人会话”，明确 P3.6a 是只读 Turn 投影；
- 空会话、归档会话、读取错误、关联/结果协议错误均使用真实状态或安全错误提示；
- 不展示 Run ID、Trace、SSE sequence、Agent 调度或完整 Trace 为默认内容；`report/` 未改动；
- 右侧只陈述事实：发送与实时过程在 P3.6b，监控/数据源在 P4，告警/受控处理在 P5；没有假监控、告警、Action、Approval、Incident 或多人能力。

## 3. 变更文件

- `frontend/src/features/workbench/conversation-turns.ts`：P2 资源到 Turn 的纯投影与协议保护；
- `frontend/src/features/workbench/conversation-turns.test.ts`：正常关联、重复关联不猜测；
- `frontend/src/features/workbench/WorkbenchPage.tsx`：只读会话恢复、时间线、调查状态和按需 Result；
- `frontend/src/app/App.tsx`：个人会话产品壳、诚实能力边界、旧深链兼容；
- `frontend/src/app/App.test.tsx`：读取顺序、深链、Result 展开/异常、缺答复、失败/取消、归档；
- `frontend/src/styles/global.css`：会话 Turn 与调查摘要样式。

## 4. 验证记录

在 `frontend/` 执行：

```text
npm run typecheck  → passed
npm run test       → 5 files, 33 tests passed
npm run build      → passed
```

构建仍有 Vite 的单 chunk `843.21 kB`（gzip `270.26 kB`）大于 500 kB 的**非阻塞告警**；本只读体验切片未引入拆包策略，后续性能收口时单独处理。

本 Step 不改 Mock API，因此不把原有 P3.4c 的 8100 HTTP/SSE 验收冒充为本 Step 的浏览器验收。用户已在独立 Mock + 非 Windows TCP 排除端口完成本 Step 浏览器人工验收，且没有改连真实 8000。

## 5. 人工验收清单

1. 启动独立 8100 Mock，再以非 `5141–5240` 的端口启动 Vite，并令 `VITE_API_PROXY_TARGET=http://127.0.0.1:8100`；
2. 打开“我的会话”，选择已有 active Session；确认按用户问题 → 调查摘要 → 已保存答复阅读；
3. 展开“结论、证据与建议”，确认结构化 Result 不默认占据主界面；
4. 观察空、归档、失败、取消、成功缺答复和协议异常不会伪造 assistant Message；
5. 确认没有输入框、发送按钮、SSE/Trace 默认面板、假监控、假告警或假处理入口；
6. 确认旧 Run 深链回到会话阅读，且不把 Run 作为主对象。

## 6. 下一步与非目标

用户已完成 P3.6a 人工验收并授权提交。本 Step 提交后的唯一下一步是 **P3.6b Design：调查型发送、稳定幂等键与刷新/SSE 恢复**；它不是普通聊天实现，必须另行 Design → Review → 用户授权。
