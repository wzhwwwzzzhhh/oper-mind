# P3.5b Step2 — 会话契约、恢复与 Investigation 关系设计

> 日期：2026-07-29　|　状态：✅ Design 完成，未授权实现　|　依赖：`step1-个人会话主体验设计.md`

## Design

本 Step 不修改任何 API。它定义 P3.6 前必须遵守的**契约决策**：如何在不破坏已交付 P2 v1 行为的情况下，让 Session/Message 成为用户主线，并保持 Run/SSE 的可恢复性。

## 1. 已确认的最小 P3.6 策略：调查型多轮对话

P3.6 不宣称实现了通用聊天助手。首个会话体验是“**每次用户发送的问题都可触发一次调查型答复**”：

```text
用户 Message
→ P2 POST /sessions/{id}/runs（原子创建 user Message + DiagnosisRun）
→ Run 成功后持久化 assistant Message + DiagnosisResult
→ UI 将三者折叠为一个可读的会话 Turn
```

这条策略可复用 P2 已完成的事务、幂等、刷新恢复和 SSE，不需要在前端伪造普通聊天服务。用户体验上是多轮对话；技术上仍是受控的 AI 运维调查。

**非调查的普通问答、澄清、总结、草稿、编辑、撤回和多个并行 Turn 不进入 P3.6。**若后续产品验证证明必须支持，再新增独立用例与 API，不以 `POST /runs` 偷换语义。

## 2. Conversation Turn 的投影规则

`ConversationTurn` 是 P3.6 前端的**派生视图模型**，不是本 Step 新建的后端实体：

```text
Turn
├── input: Message(role=user, id=Run.input_message_id)
├── investigation: DiagnosisRun
├── progress: RunEvent[]（仅当前/展开时）
└── output: Message(role=assistant, run_id=DiagnosisRun.id)，仅 success 时存在
```

### 2.1 关联算法

1. 先读取 Message 列表，按 `created_at` 正序显示；
2. 读取 Session Runs；将每个 Run 关联到 `input_message_id`；
3. 将 `assistant.run_id == run.id` 的消息作为该调查的成功输出；
4. `result` 必须从 `GET /runs/{id}` 或 Session Runs 返回的合法 `DiagnosisRun.result` 读取，不能从 assistant Message 的纯文本反推；
5. 无 Run 的 system Message 原样显示为系统提醒；当前不伪造 Monitor/Alert 来源；
6. orphan Message、找不到 input Message 的 Run、多个 assistant Message 对应同一 Run 都是协议异常：显示安全读取错误与关联 ID，不由 UI 自行择一修复。

### 2.2 终态规则

| 情况 | Message 投影 | Investigation 投影 |
|---|---|---|
| succeeded + assistant Message | 用户消息后显示助手答复 | Result 作为答复的可展开证据层 |
| succeeded 但 assistant Message 未读取到 | 不凭 Result 伪造已持久化助手消息 | 显示“答复正在恢复”，重新读取 Message；若持续不一致，协议错误 |
| failed | 保留用户消息 | 在其后显示失败调查卡；不创建假助手消息 |
| cancelled | 保留用户消息 | 在其后显示取消调查卡；不创建假助手消息 |
| queued/running | 保留用户消息 | 在其后显示调查摘要、合并持久化事件并订阅 SSE |

## 3. 刷新恢复顺序

页面恢复时不得按旧 P3 “先选 Run，再看消息”组织用户体验；但数据读取必须完整：

```text
1. GET Session（确认 active/archived 与标题）
2. GET Session Messages（建立可见消息流）
3. GET Session Runs（把 Investigation 挂回 input_message_id）
4. 对每个未终态 Run：GET events(after_sequence=最后已知 sequence)
5. 对每个未终态 Run：SSE 订阅，并携带 Last-Event-ID
6. 收到终态事件后：GET Run + 重新读取 Messages，确认 assistant Message/Result 的最终事实
```

### 3.1 SSE 规则

- 事件 ID 与 `sequence` 一一对应；`Last-Event-ID` 只用于恢复，不作为默认 UI 内容；
- EventSource 断开后，必须先以 cursor/`after_sequence` 拉取持久化 events，再重连 SSE；
- 不能只订阅“当前选中的一个 Run”：发现的全部未终态 Run 都必须恢复；
- `run_succeeded` 事件不能单独证明助手消息已经显示，必须重新读取 P2 Message/Run 事实；
- 终态后关闭对应 SSE；不可继续把新事件追加到终态调查卡。

## 4. 分页与长期会话的关键缺口

P2 `GET /sessions/{id}/messages` 使用正序 cursor。这对首次短会话足够，但“像常见 AI 网站一样先打开最近消息、向上加载历史”缺少明确定义。

### P3.6 的临时且诚实限制

在没有新的后端契约前，P3.6 只能：

- 使用 P2 的正序 cursor，依次读取可用页面形成完整短会话；
- 明确限制为个人 MVP 的小规模历史验证；
- 若无法在一次恢复中读全消息，不得假称已显示完整历史，也不得按不透明 cursor 反向构造请求。

### 后续 API 设计要求（实现阻塞门）

在会话量/消息量需要扩展前，必须新增并测试一种明确契约，二选一或等效方案：

1. `GET /sessions/{id}/messages?before=<opaque_cursor>&limit=N`：按时间倒序取最近 N 条并向前翻页；或
2. `GET /sessions/{id}/messages?order=desc&cursor=<opaque_cursor>&limit=N`：明确排序与 cursor 含义。

任何方案都必须保留 opaque cursor、UTC `Z`、稳定排序、删除/归档后的行为、OpenAPI 与前端类型一致性；不得让前端解析 cursor 内容。

## 5. 幂等、草稿与错误边界

### 5.1 发送

```text
点击发送
→ 生成 UUID Idempotency-Key
→ POST /sessions/{id}/runs { query }
→ 若网络未知，保存 key + 规范化 query + session_id 到本地短期恢复状态
→ 用同 key、同 query 重试
→ 202 后以返回 Run.input_message_id 对账
```

- 同 key、不同 query 的 `409 IDEMPOTENCY_KEY_REUSED` 必须显示为发送冲突，不能静默换 key；
- 本地草稿不含服务端事实，不进入 Message 历史；
- 浏览器刷新后若存在未知结果，先以同 key 重试/确认，再读 Message/Run，不能自动产生第二次调查。

### 5.2 API 错误与业务失败

- HTTP/代理/协议错误：由 `ApiClientError` 等读取错误路径呈现，和 `DiagnosisRun.status=failed` 分开；
- Run 失败：仅使用安全 `error.code`、`error.message`，不泄露工具/连接/模型细节；
- Message/Run 对账不一致：协议错误，不降级为“AI 已回答”；
- 归档 Session：是否允许发起新 Run 必须由 API Design 明确定义；P3.6 不通过前端绕过归档状态。

## 6. 未来普通对话、监控、告警和处理的契约预留

它们不是 P3.6 的实现内容，但不能被错误混入当前 `CreateRunRequest`：

| 未来能力 | 需要的独立设计，不得先假装存在 |
|---|---|
| 普通 assistant 回复 | 新的消息/turn 受理用例、持久化回复状态、与调查的关联和幂等语义 |
| Monitor 发现 | 监控对象、数据来源、检测规则、证据引用、系统消息来源和最小权限 |
| Alert 进入 | Alert 资源、来源/去重、关联会话策略、可审计 system Message |
| 处理 | ActionProposal、授权、执行器权限、审计、回滚和验证结果 |
| 多人协作 | 成员、共享、访问控制、冲突和审计；当前 V1 明确排除 |

## 7. 需要新增/调整 API 时的 Design → Code 门

P3.6 可以先做纯 UI 投影与现有 P2 契约的 Mock 验证；但一旦触及以下任一项，必须先开新的 API Design / Review，不得在前端补丁中完成：

- 反向消息分页；
- 普通消息受理或 assistant 非调查回复；
- Message 与 Result 的新引用字段；
- 归档会话的发送策略；
- Monitor/Alert/system Message；
- Action/Approval/Execution。

## Review

本 Step 确认了一个安全可行的 P3.6 最小策略：把 P2 既有诊断闭环投影为长期会话中的调查型 Turn。它同时明确了消息反向分页和普通聊天语义不是前端可自行解决的问题。独立审查见 `review.md`。
