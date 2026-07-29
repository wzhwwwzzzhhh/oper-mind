# P3.6b Step5 — 调查型发送、稳定幂等键与刷新 / SSE 恢复设计

> 日期：2026-07-29　|　状态：✅ Design / 独立 Review 完成；P3.6b.1 已完成 Code/Test/Review 与用户边界验收，并由本提交收口
>
> 前序：P3.6a 已提交为 `eb664dd feat: 完成P3.6a会话壳与只读Turn投影`
>
> 依据：`step2-会话契约与恢复设计.md`、`step3-后续最小切片与验收设计.md`、P2 `/api/v1` 契约与 `frontend/src/api/v1/client.ts`

## 1. 目标与明确范围

P3.6b 让 active Session 中的用户可以提交一条**调查型问题**，并在刷新、网络未知结果和 SSE 中断后，以 P2 已持久化的 Message / Run / RunEvent / Result 重新恢复事实。

它不是通用聊天：每一次提交都调用既有 `POST /api/v1/sessions/{session_id}/runs`，由后端原子创建 user Message、queued Run 和 `run_queued` 事件；只有 succeeded 后已有 assistant Message 才会显示助手答复。前端不得单独创建或伪造普通 Message。

本 Design 仅定义后续实现，不安装依赖、不写前端/Mock/后端代码、不改 `/api/v1`、`report/`、数据库、数据源、认证、Alembic、旧 `/diagnose*` 或运行时资产。

## 2. 已继承的 P2 契约事实

| 事实 | P3.6b 的使用规则 |
|---|---|
| `POST /sessions/{session_id}/runs` 返回 `202 + Run` | `Run.input_message_id` 是提交后唯一可信的 user Message 对账键；不得按 query 文本猜测或合并 Turn。 |
| `Idempotency-Key` | 必填 UUID，作用域 `session_id + endpoint`；同 key + 同语义 query 重放同一 Run / trace，不重新执行；同 key + 不同 query 是 `409 IDEMPOTENCY_KEY_REUSED`。 |
| Run 生命周期 | `queued → running → succeeded/failed/cancelled`；终态不可逆。成功 Result 不等价于已恢复 assistant Message。 |
| `GET Session Runs` / `GET Session Messages` | 分别按 `created_at desc` / `created_at asc` 的 cursor 返回；刷新和终态都以这些持久化资源重新形成 Conversation Turn。 |
| `GET /runs/{run_id}/events` | `sequence asc` 的持久化事件分页；用于 SSE 连接前、断线后和协议恢复的补偿。 |
| `GET /runs/{run_id}/stream` | 只回放持久化 `run_event`；SSE `id == sequence`；支持 `Last-Event-ID` 或 `after_sequence`；终态后关闭流。 |
| `X-Request-Id` / `X-Trace-Id` / UTC `Z` | JSON 客户端已核对请求/响应诊断；SSE 也必须生成每连接 request ID、验证安全协议字段，且不把 ID 作为默认用户界面内容。 |
| 旧 `/diagnose*` | 不消费、不改造、不把即时 SSE 冒充可恢复产品 Run。 |

路径锚点：`docs/开发/P0-V1产品化基线/api-v1-contract.md:426-503`、`frontend/src/api/v1/client.ts:98-127,228-364`、`frontend/src/features/workbench/conversation-turns.ts`。

## 3. 用户体验与状态模型

### 3.1 发送区域

仅 active Session 显示一个调查型输入框和“开始调查”按钮；归档会话没有输入和发送。发送区域必须明确：

> “每次提问都会创建一次运维调查；当前不提供普通聊天或自动处理。”

最小本地状态：

```text
idle
→ submitting（已写入稳定发送意图，POST 在途）
→ acceptance_unknown（网络/协议未知，必须同 key 重试或刷新恢复）
→ accepted（202 已收到，等待持久化 Message / Run 对账）
→ recovering（非终态 Run 的事件/事实恢复中）
→ terminal（由持久化事实投影为 succeeded / failed / cancelled）
```

一个 Session 同时最多保留一个本地 `submitting / acceptance_unknown / accepted` 发送意图；P3.6b 不在同一会话引入并行发送队列、多条草稿或“普通聊天”并发语义。

### 3.2 稳定发送意图（浏览器 sessionStorage）

在用户按下发送、**发起 POST 前**生成 UUID，并写入受当前浏览器 tab 生命周期限制的 `sessionStorage`：

```ts
{
  version: 1,
  session_id: string,
  endpoint: '/api/v1/sessions/{session_id}/runs',
  idempotency_key: string,
  query: string,                // 原样保存，仅供同 key 重试
  created_at: string,           // UTC Z
  accepted_run_id?: string,
  input_message_id?: string
}
```

规则：

1. `sessionStorage` 不是后端数据源、不会跨浏览器会话同步、不会写入仓库或运行时文件；它只解决当前 tab 刷新后的“网络结果未知仍能使用**相同 key + 相同 query**重试”。
2. 不记录 token、认证、Trace 原文、完整 SSE 事件、Result、数据库信息或服务端异常；禁止把该对象写日志、分析系统或 URL。
3. 已收到合法 `202` 后保存 `accepted_run_id` 和 `input_message_id`，直至 authoritative Messages / Runs 已对账；终态或用户明确丢弃可清理该意图。
4. 编辑问题、主动取消/丢弃未受理意图、切换到另一 Session 后再次发送，必须生成新 key；不得复用旧 key 搭配不同 query。
5. 现有 P2 query 规范化由服务端定义。前端只做空白输入拦截；不得在客户端重实现语义 fingerprint 或宣称两个问题相同。

### 3.3 POST、重试与错误矩阵

| 结果 | 前端行为 | 禁止行为 |
|---|---|---|
| `202` + 合法 Run | 记录 `run_id/input_message_id`，禁止第二次 POST；立即进入 authoritative 恢复。 | 仅靠本地 optimistic Message 形成 Turn。 |
| fetch 超时、断网、非 JSON、响应中断 | 标为 `acceptance_unknown`；“用相同请求重试”只能复用意图中的同 key / 同 query；也可刷新恢复。 | 生成新 key 后盲目重发、假称未创建 Run。 |
| `202` 但 request/trace 协议诊断异常 | 保存原 key，显示安全协议提示，并用 GET Resources 对账；不自动创建新 Run。 | 忽略协议问题后再 POST。 |
| `409 IDEMPOTENCY_KEY_REUSED` | 显示安全冲突；保留意图，要求用户确认丢弃后才可修改问题并生成新 key。 | 自动换 key 重试。 |
| `409 SESSION_ARCHIVED` | 停止提交，重新读取 Session，切换为只读。 | 本地假装接受。 |
| `422` | 显示服务端安全字段错误；用户编辑后创建新发送意图。 | 把服务端 validation 当网络未知继续同 key 循环。 |
| `503` / `429` / `5xx` | 标示未确认/暂不可受理，按安全提示允许用户以**同 key**再次尝试。 | 用假 queued 状态替代服务端事实。 |

## 4. 202 后、刷新后与分页对账

### 4.1 受理后的固定顺序

```text
1. POST Run（稳定 Idempotency-Key）
2. 202 返回 Run.id + input_message_id
3. GET Session Runs：确认 Run 属于当前 Session，读取当前状态
4. GET Session Messages：顺序分页，直到找到 input_message_id 或确认读尽
5. 用 input_message_id / assistant.run_id 重建 Conversation Turn
6. 若 Run 非终态：事件 REST 补偿 → SSE 连接
7. 若 Run 终态：GET Run + 重新读取 Messages / Runs，确认 Result 与 assistant Message
```

P2 Message 是正序 cursor，新 user Message 通常位于后页。因此 P3.6b 不能把新输入仅插入 React state 后称为“已保存”。在当前小规模 MVP 中，恢复器必须按服务端 cursor 顺序补页，直到发现 `input_message_id` 或 `has_more=false`；若分页读取失败，展示“调查已受理，正在恢复已保存的问题”，而不是造一条 user Message。

Runs 也须完整按 cursor 读取以发现**所有**非终态 Run，而非只监督新 Run 或页面首批 Run。若中途读取错误，页面可监督已读取的资源，但必须醒目标记“部分调查尚未完成恢复”，不能声称全量恢复完成。

### 4.2 刷新恢复

浏览器刷新后先读取 session、完整可用的 Runs / Messages，并恢复所有 nonterminal Run：

```text
Session
→ Sessions Runs（遍历 cursor，建立 nonterminal Run 集合）
→ Session Messages（投影已保存 Turn）
→ 对每个 nonterminal Run：Events REST 补偿
→ 为每个 nonterminal Run 建立一个 SSE 恢复器
→ 任一终态：重读 Run、Runs、Messages，最后由持久化事实更新 Turn
```

`sessionStorage` 意图只用于“POST 结果未知”的同 key 重试或接受后精确对账；它不替代 Session / Message / Run，不作为跨设备恢复机制，也不应覆盖服务器终态。

## 5. SSE 传输设计：显式 Last-Event-ID，而不是旧单 Run EventSource

### 5.1 已识别的实现风险

现有 `use-run-event-stream.ts` 使用浏览器 `EventSource`，但它不能显式设置 `X-Request-Id` 或首次/手动重连的 `Last-Event-ID`。若把固定 `after_sequence` 留在 URL，同时浏览器自动重连带回更大的 `Last-Event-ID`，会触发 P2 的 `400 INVALID_EVENT_CURSOR`（两个游标不一致）。此外旧 hook 只服务单个选中 Run，不满足会话内全部 nonterminal Run 的恢复要求。

因此 P3.6b **不得直接复用旧 EventSource hook 作为产品恢复实现**。

### 5.2 后续实现的 transport 边界

P3.6b.2 设计为一个可中止、按 Run 注册的 Fetch SSE 适配器，不新增依赖：

1. 发起 `fetch(GET /api/v1/runs/{run_id}/stream)`，显式带 `Accept: text/event-stream`、`X-Request-Id` 与 `Last-Event-ID: <last_processed_sequence>`；初始无事件时不带该 header。
2. 逐帧解析 `id`、`event`、`data`：仅接受 `event: run_event`，且 `id` 的十进制 sequence 必须与 payload `event.sequence` 一致；使用现有严格 UTC Z / run_id / type 校验和 sequence 去重。
3. 连接错误、读流错误或 visibility/retry 恢复时：先关闭/abort 旧流，再以 `GET events` cursor 补齐持久化事件，最后以最新 sequence 新建 Fetch SSE 并带新的 `Last-Event-ID`。不得让旧连接与新连接同时写同一 Run。
4. `run_succeeded/run_failed/run_cancelled`：停止该 Run 流；刷新 `GET Run`、Session Runs、Session Messages。成功事件不能替代 assistant Message；缺少答复继续显示 `ANSWER_RECOVERY_PENDING`。
5. `400 INVALID_EVENT_CURSOR` / `409 EVENT_CURSOR_EXPIRED`：不重发 POST、不伪造过程。重新从可读 events 页面同步；若历史仍不可补齐，则保留 Run 当前状态并提示“历史调查过程无法完整恢复”，随后以 Run / Message / Result 为最终事实。
6. 生命周期注册表以 `session_id + run_id` 管理；路由切换、Session 切换、Run 终态和组件卸载必须 abort/cleanup。每个 nonterminal Run 同时至多一个恢复器。

事件过程默认只显示简短、可安全理解的“调查进度”摘要；sequence、event ID、Trace、Agent 原始参数、原始日志 / SQL 和完整 Trace 不进入主会话默认视图。完整 Trace 继续是 `report/` 的受控研发边界。

## 6. 代码切片建议（均需单独授权）

### P3.6b.1 — 发送意图与 202 对账

范围：只接入 active Session 输入、sessionStorage 稳定意图、POST Run、错误矩阵和 `input_message_id` 对账；不做 SSE UI 或 Mock 行为扩展。

预期文件：发送意图纯函数/测试、`WorkbenchPage` 拆出的发送组件、React Query mutation/invalidation、组件测试和 step 日志。不得改后端、真实资源或 `report/`。

验收：双击不会双 POST；断网重试复用同 key；202 后不重复显示 user Message；归档会话无输入；409/422/503 安全且诚实。

### P3.6b.2 — 多 Run 事件恢复器与渐进进度

范围：Fetch SSE 适配器、events REST 补偿、全部 nonterminal Run 注册表、终态事实重读和按需进度摘要；替换旧产品路径对单 Run EventSource 的依赖。

验收：刷新恢复多个 nonterminal Run；断流先补 events 再重连；连接实际携带最新 `Last-Event-ID`；终态只以 Run/Message/Result 收口；无 sequence/Trace 默认泄漏。

### P3.6b.3 — Mock 合同、代理和人工验收

范围：只补足 P3.6b.1/.2 已定义行为需要的 MSW / 独立 8100 Mock 状态与验收脚本，不修改真实 8000 或后端业务。若现有 Mock 已能覆盖某项，只添加测试，不重复改夹具。

验收：202、同 key 重放、不同 key、未知响应重试、Session archived、events cursor、`Last-Event-ID`、断线、终态、刷新以及端口代理均可独立复现；浏览器验收仍使用 8100 Mock + 非 `5141–5240` 端口。

## 7. 初始测试与人工验收矩阵

| 层级 | 必验场景 |
|---|---|
| 纯函数 | 发送意图序列化/恢复、同 key 重试、明确丢弃才换 key、事件 frame 解析 / 去重 / cursor 异常。 |
| API client / mutation | `Idempotency-Key`、`X-Request-Id`、202 / 409 / 422 / 503 / 网络未知分类，禁止无 key POST。 |
| 组件 | active / archived、单飞发送、accepted 等待 persisted Message、无假 optimistic Turn、协议错误与安全文案。 |
| 流恢复 | 多个 nonterminal Run、REST events 补偿、Fetch SSE `Last-Event-ID`、abort cleanup、终态重读、历史 events 无法补齐。 |
| 独立 Mock | P2 schema 交叉核对、HTTP 代理、幂等 replay、SSE 断线/终态与刷新。 |
| 人工浏览器 | 8100 Mock + 非排除 Vite 端口：发送、未知响应同 key 重试、刷新、断线恢复、success/failed/cancelled、无假监控/处理。 |

固定质量门：`npm run typecheck`、`npm run test`、`npm run build`、必要时 `npm run test:mock-api`；本 Step 仍不把 Mock 通过误称为真实后端 / 数据库接入。

## 8. 非目标与停止条件

- 不创建普通聊天 Message API、会话创建/编辑/归档 UI、并行多 Turn 队列、草稿同步或跨设备 outbox；
- 不接入真实 DB、监控、环境、数据源、告警、Approval、Action、Incident、多用户或认证；
- 不在主会话伪造实时监控、生产告警、自动处理、完整 Trace 或 Run 结果；
- 不消费旧 `/diagnose`、`/diagnose/stream`；
- 若 P2 OpenAPI / Mock 与以上 `Idempotency-Key`、`input_message_id`、event sequence、Last-Event-ID 或安全错误事实冲突，停止实现，先开契约差异审查；
- 若 Fetch SSE 在目标浏览器无法稳定读取响应流或代理剥离帧，停止在 P3.6b.2，记录浏览器/代理证据并先设计 transport 兼容方案，不退回无 cursor 的临时 EventSource 假恢复。

## 9. Design Review 结论

通过。P3.6b 已把发送、稳定幂等、刷新、全部 nonterminal Run 的事件恢复、Last-Event-ID、终态事实重读和 P4/P5/P6 边界拆为可独立提交的实现步骤。P3.6b.1 已在用户授权后完成实现、自动测试、独立 Review 与用户边界验收；实施记录见 `step6-P3.6b1发送意图与202对账.md`。P3.6b.2 的 SSE 与 P3.6b.3 Mock 合同仍未授权，不能混入当前提交；提交后仍须由用户决定二者优先级。
