# P3 设计 — 主前端工作台

> 日期：2026-07-28　|　状态：✅ P3.3b 已提交 `e7858ce`；✅ P3.3c 已提交 `ca899e0`；当前进入 P3.4 Design
>
> 工作分支：`feat/p3-workbench`　|　设计基线：`87c4f83 docs: 完成P3.2c2离线前置核对`
>
> 本轮范围：完成 Run 受理、幂等重试、持久化 RunEvent 与 SSE 恢复的前端设计、Step 拆分和独立审查；不修改前端业务代码、后端 `/api/v1`、`report/`、运行时资产，也不连接真实数据库或数据源。

## 1. 目标与已核实事实

P3 的目标是把 P2 已持久化的会话诊断闭环呈现为面向运维/SRE 用户的**结果优先工作台**：恢复 Session、Message 和 Run；受理一次幂等诊断；观察已提交的过程事件；在 P3.4 展示结构化结果；完整 Agent Trace 仅保留受控跳转边界。

- `frontend/` 已由 P3.1 建立 React + TypeScript + Vite 主产品工程；`frontend/mockup.html` 保留且不在本轮改动。
- `report/` 是阶段一 M7 的独立研发/实验/Trace 前端；P3 不嵌入、不改造、不复用其依赖或路由。
- P2 v1 路由已提供 `POST /api/v1/sessions/{session_id}/runs`、`GET /api/v1/runs/{run_id}`、`GET /api/v1/runs/{run_id}/events` 与持久化 SSE `GET /api/v1/runs/{run_id}/stream`；公开字段以 `docs/开发/P0-V1产品化基线/api-v1-contract.md` 和 OpenAPI 生成类型为准。
- 现有 P3.2 已只读恢复 Session → Runs → Message → 选定 Run；没有创建 Run、读取事件或接入 SSE。
- 旧 `POST /diagnose` 和 `GET /diagnose/stream` 是阶段一兼容接口，P3 主产品不得调用、包装或拿来模拟 v1 Run。
- 真实数据库只读验收按用户决定延后；C1–C8 仍保留为后期强制门槛。本轮与后续 P3.3 的默认测试均使用 MSW / 独立 Mock FastAPI，不连接真实 DB、数据源或用户启动的 8000 后端。

## 2. P2 v1 契约消费边界

| 产品需要 | 只使用的 API | 前端规则 |
|---|---|---|
| 会话导航 | `GET /api/v1/sessions`、`GET /sessions/{session_id}` | cursor 不解码、不伪造；切换 Session 时隔离 Query key 和 cursor |
| 恢复上下文 | `GET /sessions/{session_id}/runs`、`GET /sessions/{session_id}/messages` | 分别遵守 Run 倒序、Message 正序；刷新不触发 POST |
| Run 受理 | `POST /sessions/{session_id}/runs` + `Idempotency-Key` | 只在用户明确提交后调用；`202` 的响应 Run 是唯一受理事实 |
| Run 状态与结果 | `GET /runs/{run_id}` | 读取 `queued/running/succeeded/failed/cancelled`、安全 `error`、`trace_id`；完整结果卡留给 P3.4 |
| 事件历史 | `GET /runs/{run_id}/events` | 仅处理已提交 RunEvent；cursor 按 API 原样回传，按 `sequence asc` 汇总 |
| 实时恢复 | `GET /runs/{run_id}/stream` | SSE 固定监听 `run_event`；以 `(run_id, sequence)` 去重，不以连接顺序或临时 UI 状态造事件 |
| 关联与排障 | JSON `meta`、HTTP `X-Request-Id`/`X-Trace-Id`、SSE envelope `meta` | 仅显示/记录安全关联标识；不由 ID 推断 Trace 内容或业务状态 |

所有 API 时间按 UTC `Z` 处理和显示。安全错误只显示 `error.code`、`error.message`、安全 `details` 与可用 request/trace ID；网络、代理 HTML、非 JSON 或 SSE 连接中断必须区别于后端业务失败，不能伪造成 `run_failed`。

## 3. 固定工程职责与页面信息架构

P3.1 的工程基线继续有效：React Router 负责 Session/Run 深链；TanStack Query 管理 v1 服务器资源、cursor 页和失效；Zustand 仅存放草稿、展开和连接提示等 UI 状态，不复制 Session/Run/Result 事实；Ant Design 提供表单、状态、空/错误反馈；Vitest、RTL、MSW 和 Vite build 是质量门。

路由不扩张：`/` 重定向工作台，`/workbench` 进入会话导航，`/workbench/sessions/:session_id` 恢复 Session，`/workbench/sessions/:session_id/runs/:run_id` 定位选定 Run。P3.3 在既有工作区中增加下列受控区域，不新增 P4/P5/P6 页面：

1. **问题提交区**：只在 active Session 显示查询输入、提交和同一逻辑请求的安全重试提示；归档 Session 明确禁用且不发送请求。
2. **Run 列表/选定 Run**：显示状态、受理时间与安全关联；`202` 后立即跳转至返回的 `run.id`，不靠本地生成 ID。
3. **事件摘要区**：按 sequence 显示已提交事件的简短状态，不显示原始工具输出、凭证、SQL、连接串或完整 Trace。
4. **连接恢复提示**：只在 queued/running Run 展示“正在同步持久化事件/连接中断后正在恢复”；终态关闭流并重读 Run。
5. **结果区域**：P3.3 仅保留状态与“结果将在 P3.4 结构化展示”的诚实占位；不提前实现 root cause、证据、建议、风险卡片或 report 跳转。

P4 的 Environment/DataSource/Connector/Runbook/Knowledge，P5 的 Alert/Incident/ActionProposal/Approval/审计，P6 的导出、搜索、通知、偏好和 report 深链均不实现。`requires_approval` 即使已出现在 Run 的最终 result 中，也不产生批准、执行或假审批按钮。

## 4. Run 受理与幂等状态机

### 4.1 请求及客户端职责

一次用户明确发起的逻辑提交按以下顺序执行：

```text
编辑 query
→ 为该逻辑请求生成 UUID Idempotency-Key
→ POST /api/v1/sessions/{session_id}/runs
   Headers: X-Request-Id（每次 HTTP 尝试）+ Idempotency-Key（逻辑请求不变）
   Body: { query }
→ 202：以响应 run.id / trace_id 为准，失效并恢复 Runs、Messages、Run
→ 跳转 /workbench/sessions/:session_id/runs/:run_id
→ Run 非终态时再执行事件读取与 SSE 恢复
```

- 现有 v1 client 的 `X-Request-Id` 机制应扩展到 JSON POST；每一次网络请求生成新的 request ID，并继续校验响应 headers 与 `meta` 的一致性。
- `Idempotency-Key` 由浏览器 `crypto.randomUUID()` 生成。其作用域是 `session_id + POST /runs`；同 key、同规范化 query 必须重放同一个 Run 和原始 trace，不重新执行 Agent。
- 提交按钮在请求飞行中禁用，防止双击；这只是 UX 防护，不能代替后端幂等约束。
- 发生网络超时、浏览器网络错误或非 JSON 代理失败时，页面保留同一 key 和未改动 query，并仅提供“按原请求重试”动作；该动作必须复用 key。用户编辑 query 或明确选择“开始新的诊断”才废弃旧 key 并生成新 key。
- 不把 query、幂等键或可能含运维上下文的草稿写入 localStorage/运行时资产；整页刷新后不自动 POST。用户可先刷新 Run 列表寻找已受理 Run，无法确认时必须明确提示用户重新发起一条**新的**逻辑请求。
- `409 IDEMPOTENCY_KEY_REUSED` 显示安全冲突，禁止自动换 key 重发；`409 SESSION_ARCHIVED` 禁止继续提交；`422` 展示字段校验；受理前 `503 DIAGNOSIS_UNAVAILABLE` 允许用户在明确操作后重新开始一条逻辑请求；已收到 `202` 后的执行失败只能从 Run 的 `failed/error` 和终态事件读取。

### 4.2 前端局部状态

提交状态仅服务 UI，不覆盖服务器事实：

```text
idle
→ submitting(key, query)
→ accepted(run_id)
→ observing（由 GET Run / Events / SSE 的服务器状态决定）

submitting
→ retryable_unknown(key, unchanged query)   # 网络/超时/非 JSON，尚未确认是否受理
submitting
→ rejected_safe_error                        # 4xx/503；不伪造 Run
```

`accepted` 之后立即以 URL 和 TanStack Query 的 Run 数据为准，删除临时“运行中”假对象。页面刷新、深链、切换 Session 或组件卸载均不得自动恢复 POST。

## 5. 刷新、事件列表与 SSE 恢复

### 5.1 固定恢复顺序

```text
1. GET Session（或由 Session 列表定位）
2. GET /sessions/{session_id}/runs，按 cursor 恢复可见 Run
3. GET /sessions/{session_id}/messages，按 cursor 恢复消息时间线
4. URL run_id 优先；否则选择恢复列表的首项；无 Run 显示真实空状态
5. GET /runs/{run_id}，读取最终服务器 status、result/error、trace_id
6. GET /runs/{run_id}/events，按 cursor 读取已提交事件并取最大 sequence
7. 仅 queued/running：打开持久化 SSE；终态不保持连接
```

资源不存在、Run 与当前 Session 不匹配、归档 Session、cursor 失败或安全 404 时，清除无效定位并回到能恢复的列表/错误态；不能以缓存伪造资源。P2 cursor 尚未绑定 Session scope，因此 Query key、事件集合和 cursor 生命周期必须同时绑定 `session_id + run_id`。

### 5.2 EventSource 的游标规则（本轮审查修正）

P2 后端规定：`Last-Event-ID` 与 `after_sequence` 同时存在且值不同即返回 `400 INVALID_EVENT_CURSOR`。原生 `EventSource` 会在自动重连时携带最新收到的 `Last-Event-ID`，但会保留原始 URL。因此 P3.3 固定采用以下策略：

- 原生 `EventSource` **初次连接 URL 不附加 `after_sequence`**。服务端会重放最早可用事件，客户端按 `(run_id, sequence)` 去重；这比双游标冲突更安全。
- 浏览器自动重连仅依赖 SSE 帧的十进制 `id` 形成 `Last-Event-ID`。前端不得尝试在 EventSource 设置 `X-Request-Id`、`Last-Event-ID` 或读取响应 headers；浏览器 API 不支持这些能力。
- SSE `event` 固定为 `run_event`。解析 `data.event` 后验证 `run_id`、正整数 `sequence`、类型、UTC `occurred_at` 和安全 `data` 的最小形状；未知/畸形帧只记录协议恢复提示，不改写 Run 状态。
- 收到 `run_succeeded`、`run_failed` 或 `run_cancelled` 后关闭流，失效并重读 `GET /runs/{run_id}`、Run 列表和 Message；只有 GET Run 的终态/安全 `error` 才能决定页面最终状态。
- `EventSource.onerror` 只将 UI 标为“事件连接中断，正在从持久化记录恢复”，不等同于诊断失败。自动重连持续时不并行创建第二条流；达到受控的恢复阈值或切回页面时，关闭旧流、重新 GET Run 与 Events，再建立一条无 `after_sequence` 的 EventSource。
- REST `GET /events` 遇到 `INVALID_EVENT_CURSOR`、`EVENT_CURSOR_EXPIRED` 或其他安全错误时，清空该 Run 的本地事件序列并从首个可用页面重新同步；不能盲目递增游标或把错误吞成空事件。
- P2 的事件保留、短连接轮询、取消/慢客户端/高吞吐能力仍属于 P7；P3.3 仅正确消费已提交事件，不承诺生产级持续推送。

### 5.3 事件合并与 UI 规则

事件列表和 SSE 共用单一前端合并器：key 为 `(run_id, sequence)`，只接受同一 Run 且 sequence 为正整数的事件；重复 sequence 保留首次合法内容并记录协议问题；渲染按 sequence 升序。事件摘要只使用公开 type 和脱敏 `data` 的允许字段，不能反序列化为 Agent 内部 Trace 或执行指令。新事件到达后只更新对应 Run 的缓存；切换 Run 时必须关闭旧连接并清理其临时连接提示。

## 6. `report/` 受控跳转

P3.3 不实现 Trace 跳转。主产品只消费安全 `DiagnosisRun`、`RunEvent` 和之后 P3.4 的 `DiagnosisResult`。`report_markdown` 是补充，不能替代结构化字段。后续只有在 P6 明确 `VITE_REPORT_URL`、trace deep-link 契约、认证与状态隔离后，才可显示外部入口；不得拼接未确认的 `trace_id`、iframe `report/`、共享本地状态或复用 M7 路由。

## 7. 测试、Mock 联调与人工验收策略

P3.3 默认使用 MSW 和独立 Mock FastAPI；不得将真实 8000 后端或真实数据库失败伪造成 mock 成功。

- **P3.3a 单元/组件测试**：验证 POST body、`Idempotency-Key` 在同一逻辑重试中稳定、每次 HTTP 尝试 `X-Request-Id` 独立、`202` 以响应 Run 导航、`409/422/503` 安全反馈、归档禁用、刷新不自动 POST。
- **P3.3b 单元/组件测试**：验证 Event cursor 分页、事件去重/排序、终态关闭、页面卸载关闭、SSE `onerror` 不写成 `failed`、无 `after_sequence` 的原生 EventSource URL、自动重连与 REST 重同步不并发双流。
- **P3.3c Mock FastAPI 验收**：已扩展独立 mock（仅进程内确定性状态）覆盖 `POST Run` 的首次受理/同 key 重放/同 key 不同 query `409`、不同 key 创建不同 Run/trace、RunEvent REST cursor、有限持久化 SSE 帧、Last-Event-ID 恢复、双游标 `400` 和终态关闭；`test:mock-api`、前端 build/Vitest 与独立 5175→8100 代理 HTTP 主流程已通过。浏览器/UI 控制不可用，仍待用户完成可视化主流程。
- 后端 P2 契约没有变更时不修改后端；如 OpenAPI/Mock 发现字段或事件缺口，先停在契约差异并另开后端 Design，禁止前端猜字段。

人工验收依次覆盖：active Session 提交 → `202` 深链 → queued/running 事件摘要 → 刷新恢复 → 断线恢复 → succeeded/failed/cancelled 终态；网络未知结果使用同 key 重试；归档、空 Run、404、非 JSON 代理失败和无 report 配置均诚实展示。确认不存在旧 API、真实 DB、P4/P5/P6 假能力或 `report/` 混入。

## 8. Step 分解与非目标

| Step | 交付 | 明确不混入 |
|---|---|---|
| P3.3（本轮） | Design、`step3` 边界、Review、HANDOFF、计划/规则同步 | 任何业务代码、真实连接或 mock 行为变更 |
| P3.3a | ✅ 已完成：v1 POST Run client/mutation、受理表单、同 key 重试、安全错误、202 深链与 MSW/组件回归 | Event 列表/SSE、完整结果卡、Mock FastAPI 扩展 |
| P3.3b | ✅ 已完成：RunEvent REST cursor、事件合并/去重、原生 EventSource 生命周期、断线 REST 重同步、终态重读与测试 | 结果卡、Trace 跳转、真实 DB、P4/P5/P6 |
| P3.3c | MSW/独立 Mock FastAPI 的 POST/SSE 契约验收、浏览器主流程、Review | 真实后端/数据库联调、后端业务代码 |
| P3.4 | 结构化结果、失败/空/归档收口和后续受控 Trace 设计入口 | P4/P5/P6 正式资源 |

P3 不修改 `/api/v1`、Application Service、Repository、ORM、Alembic、旧接口或 `report/`。P2 的 `BackgroundTasks`、短连接 SSE 轮询和 SQLite 并发不是生产队列/高吞吐推送；P3 只正确恢复和展示，P7 再处理生产级加固。

## 9. 结论

P3.3a 已提交为 `dc122cc feat: 完成P3.3a Run受理与幂等重试`。P3.3b 已提交为 `e7858ce feat: 完成P3.3b持久化事件与SSE恢复`。P3.3c 已提交为 `ca899e0 feat: 完成P3.3c Mock FastAPI SSE契约验收`，包含确定性 Mock FastAPI 的 Run 幂等、RunEvent/SSE 实现和自动验收：`test:mock-api` 10 项、typecheck、22 项 Vitest、production build，以及独立 Vite 5175 → Mock 8100 的真实 HTTP 代理主流程和用户可视化验收；临时实例均已关闭。真实数据库验收继续延后，C1–C8 不降低。**当前唯一下一步为 P3.4 Design：结构化结果、失败/空/归档收口与受控 Trace 入口。**