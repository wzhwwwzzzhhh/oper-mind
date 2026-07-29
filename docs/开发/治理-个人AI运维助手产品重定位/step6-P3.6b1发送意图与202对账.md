# P3.6b.1 Step6 — 发送意图与 202 对账

> 日期：2026-07-29　|　状态：✅ Code/Test/Review 与用户边界验收完成，由本提交收口
>
> 范围：active Session 的调查型发送、稳定幂等意图、`202` 后持久化 Run / Message 对账；不含 SSE、Mock API 或后端变更。

## 1. 已实施的最小闭环

```text
用户输入调查问题
→ 写入 tab 限定 sessionStorage 发送意图（UUID Idempotency-Key）
→ POST /api/v1/sessions/{id}/runs
→ 202 返回 Run.id + input_message_id
→ 依次完整读取 Session Runs、Session Messages 的既有 cursor 页面
→ 只在二者均出现对应持久化资源后投影 Conversation Turn
```

实现不创建本地 optimistic Message，也不从 query 文本反推已保存用户消息。成功受理但尚未读到持久化事实时，页面保留“正在恢复已保存的调查”；只有重新读取到 `Run.input_message_id` 和对应 user Message 后才清除发送意图。

## 2. 实现边界

### 2.1 稳定发送意图

新增 `frontend/src/features/workbench/send-intent.ts`：

- 发送前调用 `crypto.randomUUID()` 生成 `Idempotency-Key`；
- 以 `sessionStorage` 的 Session 级 key 保存 version、session、endpoint、key、query、UTC `created_at`、phase；
- 仅合法 `202` 后写入 `accepted_run_id`、`input_message_id`；
- 网络未知、非 JSON、响应中断时仍保留同一意图，按钮只会以同 key / 同 query 重试；
- `IDEMPOTENCY_KEY_REUSED` 不自动换 key，用户必须明确“丢弃当前发送意图”后才能修改并再次发送；
- `VALIDATION_ERROR` 可由用户编辑后生成新意图；sessionStorage 不保存 token、认证、Trace、events、Result 或服务端异常，也不写入 URL/仓库。

### 2.2 202 对账和页面事实

`SessionWorkspace` 新增 active Session 的调查输入区：

- archived Session 继续不显示输入；
- 提交期间禁止第二个本地意图；
- `202` 后按 **Runs → Messages** 的既有正序 cursor 依次读全可用页，使用 `run.id + session_id + input_message_id` 与 user Message ID 做严格校验；
- 对账成功将完整页结果写回 React Query 缓存，由已有 `project_conversation_turns()` 形成 user → queued Investigation；
- 对账读取失败不伪造 Turn，保留 accepted intent 并提供“重新恢复已保存内容”；
- `SESSION_ARCHIVED` 会重新读取 Session；HTTP/协议错误继续复用安全的 request / trace 诊断提示。

为避免当前实现的 Runs、Messages 并行读取在独立数据落盘时捕获不一致快照，对账使用顺序读取：先 Runs，再 Messages。

## 3. 变更文件

```text
frontend/src/features/workbench/send-intent.ts
frontend/src/features/workbench/send-intent.test.ts
frontend/src/features/workbench/WorkbenchPage.tsx
frontend/src/app/App.tsx
frontend/src/app/App.test.tsx
frontend/src/styles/global.css
```

未修改：`frontend/scripts/mock_v1_api.py`、MSW 默认夹具、`report/`、`backend/`、真实资源和旧 `/diagnose*`。

## 4. 自动验证

在 `frontend/` 执行：

```text
npm run typecheck     → passed
npm run test          → 6 files / 40 tests passed
npm run build         → passed
npm run test:mock-api → 11 passed（仅 FastAPI TestClient/httpx 弃用警告）
```

新增覆盖：

- 发送前 intent 的持久化、损坏 storage 拒绝、202 后合法标识写入、Session 级清理；
- active 会话 POST 带 UUID `Idempotency-Key`，202 后只经已保存 Run / Message 显示 queued Turn；
- 网络未知重试复用同一 key；
- `IDEMPOTENCY_KEY_REUSED` 不自动换 key，要求显式丢弃；
- archived 会话无发送输入；既有只读、结果、协议错误、旧深链覆盖仍通过。

构建输出单 JS chunk `851.50 kB`（gzip `272.86 kB`），仍有 Vite 超过 500 kB 的非阻塞警告；性能拆包不在 P3.6b.1 范围。

## 5. 用户验收边界

用户已在独立 8100 Mock + 非 Windows TCP 排除端口完成边界验收：新的 active 输入区、提交中状态、网络/协议错误的诚实提示，以及 archived 无输入均符合本 Step 范围。

不过当前独立 Mock 的 accepted Run 虽可验证 P2 受理/幂等与 events，却尚未把动态 accepted user Message 纳入其 Session Message 列表。因此它会正确触发“已受理但尚未恢复对应已保存问题”的状态，**不能作为 P3.6b.1 成功对账的浏览器通过证据**。完整的动态受理 → Run / Message 对账 → 代理/浏览器成功路径由未开始的 **P3.6b.3 Mock 合同**负责；本 Step 仅用 MSW 组件测试证明该路径。

人工检查：

1. active Session 可看到“发起调查”输入，文案明确为调查而不是普通聊天；
2. archived Session 仍没有输入；
3. 输入为空不发 POST；
4. 受理未知提示要求同 key / 同 query 重试，未出现第二个本地用户 Turn；
5. 没有 SSE、事件时间线、完整 Trace、监控、告警、Action、Approval 或处理入口。

## 6. Review 与下一步

P3.6b.1 仅实现稳定意图和 202 对账，边界审查与用户 UI / 错误边界验收均通过，由本提交收口。

提交后的下一步不是自动开始：用户需确认先授权 **P3.6b.3 Mock 合同**（补动态 accepted user Message，闭合独立 Mock 的浏览器成功对账路径），还是 **P3.6b.2 Fetch SSE 多 Run 恢复**的独立技术验证与实现。P3.6b.3 不得被误作 P3.6b.2 的附属小改动。
