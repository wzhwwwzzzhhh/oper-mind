# P3 设计 — 主前端工作台

> 日期：2026-07-28　|　状态：✅ P3.4 Design 已完成并通过独立审查；当前等待 P3.4a 代码授权
>
> 工作分支：`feat/p3-workbench`　|　设计基线：`306724d docs: 校正P3.3c提交状态并进入P3.4`
>
> 本轮范围：完成结构化结果、失败/空/归档收口与受控 Trace 入口的前端设计、Step 拆分和独立审查；不修改前端业务代码、后端 `/api/v1`、Mock 行为、`report/` 或运行时资产，也不连接真实数据库或数据源。

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
| P3.4 | ✅ Design 完成：结构化 Result、失败/空/归档收口、受控 Trace 条件与 Step4 边界 | P4/P5/P6 正式资源、任何 Trace 链接或报告能力 |

P3 不修改 `/api/v1`、Application Service、Repository、ORM、Alembic、旧接口或 `report/`。P2 的 `BackgroundTasks`、短连接 SSE 轮询和 SQLite 并发不是生产队列/高吞吐推送；P3 只正确恢复和展示，P7 再处理生产级加固。

## 9. 结论

P3.3a 已提交为 `dc122cc feat: 完成P3.3a Run受理与幂等重试`。P3.3b 已提交为 `e7858ce feat: 完成P3.3b持久化事件与SSE恢复`。P3.3c 已提交为 `ca899e0 feat: 完成P3.3c Mock FastAPI SSE契约验收`，包含确定性 Mock FastAPI 的 Run 幂等、RunEvent/SSE 实现和自动验收：`test:mock-api` 10 项、typecheck、22 项 Vitest、production build，以及独立 Vite 5175 → Mock 8100 的真实 HTTP 代理主流程和用户可视化验收；临时实例均已关闭。真实数据库验收继续延后，C1–C8 不降低。**P3.4 Design 已完成并通过独立审查；当前唯一下一步为 P3.4a：结构化结果读取模型与摘要面板实现（仍需用户后续代码授权）。**

## 10. P3.4 设计 — 结构化结果、终态收口与受控 Trace 边界

### 10.1 目标、唯一事实与协议防线

P3.4 将既有选定 Run 区从“仅有状态与占位”收口为**结果优先的只读诊断结论**。唯一业务事实仍是 `GET /api/v1/runs/{run_id}` 返回的 `DiagnosisRun`：不新增 Result 端点、不从 RunEvent 拼接结果、不从 Message 或 `report_markdown` 推断根因，也不读取旧 `/diagnose*`。

前端在渲染前必须以当前选定 `run_id` 和 Session 路由边界校验 Run；再按以下终态不变量投影。字段矛盾、未知枚举、非 UTC `Z` 时间、`result.run_id !== run.id` 或不完整的 Result 绝不补写为成功，而是显示“结果协议异常”的安全读取错误，并保留可用 request/trace 关联信息。

| Run 状态 | P2 已保证/前端必须核验 | P3.4 表现 | 禁止行为 |
|---|---|---|---|
| `queued` / `running` | `result` 与 `error` 均为 `null` | 保留过程事件与“正在获取已持久化进度”的非终态提示；不显示结果卡 | 不显示旧 Run 的缓存结果，不把 SSE 断线写成失败 |
| `succeeded` | `result` 非空，`error` 为 `null` | 显示完整结构化结果面板；终态后不再打开 SSE | 不通过 Markdown、事件或本地草稿补齐缺失字段 |
| `failed` | `error` 非空，`result` 为 `null` | 显示安全 `error.code`、`error.message` 与关联 ID；允许用户从既有提交区发起**新的**诊断 | 不把网络/协议读取错误伪造成 `run_failed`，不提供重试执行器 |
| `cancelled` | `result` 与 `error` 均为 `null` | 显示已取消终态和已提交事件；不归类为服务端失败 | 不伪造取消原因、恢复、继续或重跑接口 |

读取 API 失败、非 JSON 代理页、网络中断与业务 `Run.error` 是不同状态：前者由既有 `ApiClientError`/诊断信息呈现，后者只来自成功读取的 `DiagnosisRun.error`。`X-Request-Id` 与 `X-Trace-Id`/envelope `meta` 仅作安全关联显示，不能用来推断或请求完整 Trace。

### 10.2 结构化结果面板的信息架构

结果面板仅出现在选定且合法的成功 Run 下，顺序固定为“摘要 → 根因与证据 → 影响 → 建议与风险 → Agent 摘要”。所有文本按普通文本输出；不执行 HTML，不解析/执行 `report_markdown`，不把 `locator` 变成可访问真实资源的链接。

1. **结论摘要**：`summary`、`severity`、`confidence`、结果 `created_at`（UTC `Z` 原样/一致格式显示）和 Run/Trace 安全关联。`severity` 仅映射为视觉级别，不推导告警或 Incident。
2. **根因**：逐项显示 `title`、`summary`、置信度和 `evidence_ids` 的页内关联标记。标记仅定位本 Result 中同 ID 的证据；缺失引用显示“关联证据不可用”，不伪造证据。
3. **证据**：显示 `source_type`、`source_name`、`title`、`summary`、可选 `observed_at`、`locator` 的纯文本和原子 `attributes`。不显示未在契约中的原始工具输出、SQL、连接串、凭证或完整 Agent Trace；不请求任何外部 locator。
4. **影响**：仅当 `impact` 非空时显示 `summary`、`affected_services` 与 `affected_scope`；三个字段均为空/空数组时保留诚实空状态，不引入 Environment 或 Incident。
5. **建议与风险**：建议只读显示标题、描述、优先级、风险等级和关联证据。`requires_approval=true` 只能显示“需审批（P5 未实现）”标签，**不显示**执行、审批、变更或自动化按钮。风险显示等级、摘要与可选缓解建议，不创建告警或任务。
6. **Agent 摘要**：只读显示 `agent`、`status`、`summary` 与可选 `duration_ms`；它是产品摘要，不展开 Graph/工具调用 Trace。
7. **Markdown 补充**：`report_markdown` 保持 Result 的补充字段，但 P3.4 不渲染、不导出、不创建报告页；报告阅读、Markdown/PDF 导出与高级分析仍属于 P6。

每个数组字段允许合法空数组。数组为空时展示该区域的局部空状态（例如“服务未返回结构化证据”），但摘要和其他非空区域照常显示；不能为了“看起来完整”生成根因、证据、建议、风险或 Agent 结论。

### 10.3 刷新、归档与选定 Run 收口

刷新仍遵循 P3.3 的 Session → Session Runs → Message → 选定 Run/Result/Event 顺序。`DiagnosisResult` 嵌入在选定 Run 响应中，故没有额外 Result 请求、cursor 或轮询源；Run 终态后由既有 `get_run` 重读刷新该 Query key，并同步失效/重读对应 Run 列表。非终态才继续消费持久化 SSE；终态事件只触发 Run 重读，不能直接把事件内容当 Result。

- **无 Run**：active Session 显示“尚无诊断运行”和既有问题提交区；不展示空白结果面板。
- **已选 Run 但无事件**：Run/Result 读取仍可独立成功；事件区显示局部空状态，成功 Result 仍可显示。
- **归档 Session**：继续允许只读恢复历史 Run、Event 与成功 Result；提交区维持禁用，且不发送 POST、PATCH、DELETE 或重新激活请求。
- **404、跨 Session 与协议错配**：沿用既有安全错误/返回工作台路径；不借助列表缓存显示不属于当前 Session 的 Result。
- **切换 Run/Session**：Query key、局部展开状态和事件连接必须按 Run 隔离；旧 Run 的 Result 不得闪现到新 Run。

### 10.4 `report/` 与后续 Trace 入口的硬边界

P3.4 只定义**将来**的受控入口条件，不实现入口、不渲染链接、不设置 `VITE_REPORT_URL`、不 iframe `report/`，也不拼接 `trace_id`。P6 以后若要开放完整 Trace，必须先完成并评审：外部目标的显式配置、已确认的 trace deep-link 参数契约、认证/授权、来源与窗口隔离、不可用回退、审计边界和用户可见风险说明。未满足任一条件时，主产品没有 Trace 跳转；这不是错误也不是待填的假链接。

`report/` 仍是阶段一的研发/实验/Trace 可观察性前端。P3 只消费 `/api/v1` 的安全结构化资源，不修改、嵌入、复制或把 `report/` 的路由、状态、依赖、实验数据当成主产品能力。

### 10.5 P3.4 分步实施与验收

| Step | 预期交付 | 提交边界与明确不做 |
|---|---|---|
| **P3.4 Design（本轮）** | Result/终态/归档/Trace 边界、`step4`、Review、HANDOFF、计划与规则同步 | 不改前端/后端/Mock 代码，不启动真实连接，不自动提交 |
| **P3.4a** | `DiagnosisResult` 运行时读取模型、只读摘要/根因/证据面板及单元/组件测试 | 首个实现切片；不混入失败/归档收口、Mock FastAPI 扩展、Trace 链接或 P4–P6 UI |
| **P3.4b** | 将结果面板接入选定 Run；failed/cancelled/queued/running、数组空状态、归档只读、跨 Session 与协议异常的组件/路由回归 | 不新增执行、审批、取消、归档编辑、报告或外部跳转能力 |
| **P3.4c** | MSW 与独立 Mock FastAPI 补齐**完整且合法**的 `DiagnosisResult` 场景，独立 8100→5175 验收和人工结果页验收 | 不连接 8000/真实数据库，不把 Mock 变成后台执行器 |
| **P3.4 Review** | 独立审查契约字段、状态矩阵、数据安全、`report/` 边界、自动/人工验收和文档状态 | 不混入 P4/P5/P6 或 P7 生产加固 |

P3.4a 的测试夹具必须包含 `created_at` 和契约要求的全部 Result 字段；当前 P3.3c 独立 Mock 的成功 Result 仅用于此前的“非空结果占位”验证，缺少 `DiagnosisResultResource.created_at` 且数组内容过于简化，**不得**直接作为 P3.4 结构化结果验收事实。该 Mock 合同补齐明确归入 P3.4c；在此前仅使用完整的本地/ MSW 静态契约夹具，不连接真实服务。

P3.4 最低质量门：Result reader 的合法/缺失/错配/UTC 校验测试；成功、失败、取消、非终态、空数组、归档、404/网络/非 JSON 的组件回归；`npm run typecheck`、`npm run test`、`npm run build`。P3.4c 再增加 `npm run test:mock-api` 与独立 8100 Mock + 5175 Vite 代理 HTTP/人工验收。任何 Result 字段或 Mock 与 P2 OpenAPI 不一致时，先停在契约差异，不在前端猜测字段或悄然降级。

### 10.6 P3.4 设计结论

P3.4 的第一实现 Step 被限定为 **P3.4a：结构化结果读取模型与摘要面板**。它以 P2 嵌入式 `DiagnosisResult` 为唯一事实，先构建可验证的只读展示；失败/空/归档收口、独立 Mock 合同补齐和任何后续 Trace 条件随后拆分。当前不授权任何实现代码、真实后端/数据库访问或 `report/` 集成。
