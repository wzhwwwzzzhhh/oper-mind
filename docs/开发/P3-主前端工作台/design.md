# P3 设计 — 主前端工作台

> 日期：2026-07-26　|　状态：✅ Design 与独立审查完成，待用户授权暂存/提交
>
> 工作分支：`feat/p3-workbench`　|　设计基线：`54f02e5 feat: 完成P2.5刷新恢复与闭环验收`
>
> 范围：仅定义后续前端初始化和工作台纵向切片；本轮不初始化工程、不安装依赖、不修改 `frontend/`、`report/`、后端或运行时资产。

## 1. 目标与已核实事实

P3 的目标是将 P2 已持久化的会话诊断闭环呈现为面向运维/SRE 用户的**结果优先工作台**：恢复 Session、Message 和 Run；受理一次幂等诊断；观察已持久化事件；展示安全的结构化结果；完整 Agent Trace 仅受控跳转到 `report/`。

- `frontend/` 当前仅有 `frontend/mockup.html`，没有 `package.json`、React/Vite、npm 脚本或依赖；P0 原型只作视觉/状态参考，P3.1 不得覆盖它。
- `report/` 是阶段一 M7 的独立研发/实验/Trace 前端；P3 不嵌入、不改造、不复用其依赖或路由。
- 已实现 v1 路由在 `backend/src/api/v1/routes.py:146-429`，公开模型在 `backend/src/api/v1/schemas.py:63-318`；P3 字段和协议以 `docs/开发/P0-V1产品化基线/api-v1-contract.md:426-514` 为准。
- 旧 `POST /diagnose` 和 `GET /diagnose/stream` 是阶段一兼容接口，P3 主产品不得调用、包装或以它们模拟 v1 Run。

## 2. P2 v1 契约消费边界

| 产品需要 | 只使用的 API | 前端规则 |
|---|---|---|
| 会话导航 | `POST/GET /api/v1/sessions`、`GET/PATCH/DELETE /sessions/{session_id}` | Session 列表 cursor 原样回传；DELETE 是归档，已归档 Session 不受理 Run |
| 上下文恢复 | `GET /sessions/{session_id}/messages` | 按 `created_at asc, id asc` 分页；临时 SSE 事件不伪装成 Message |
| Run 历史/结果 | `GET /sessions/{session_id}/runs`、`GET /runs/{run_id}` | Run 列表固定 `created_at desc, id desc`；`run.result` 是结构化结果唯一事实来源 |
| 诊断受理 | `POST /sessions/{session_id}/runs` + UUID `Idempotency-Key` | `202` 后以响应 Run 为准；同 key/同 query 重放原 Run，不自动重复执行 |
| 过程摘要/恢复 | `GET /runs/{run_id}/events`、`GET /runs/{run_id}/stream` | 只显示持久化 RunEvent，按 `(run_id, sequence)` 去重/排序 |
| 关联与排障 | JSON `meta` 和 `X-Request-Id`/`X-Trace-Id` | 仅提供安全关联信息，不由这些 ID 猜测业务状态或 Trace 内容 |

所有时间按 API 的 UTC `Z` 解析/显示；cursor 永远不解码、不生成，切换 Session 时清除该 Session 之外的 cursor。安全错误统一使用 `error.code`、`error.message`、安全 `details` 和 `meta.request_id`；网络/协议失败不伪造成业务错误码。

## 3. 后续 P3.1 工程策略（本轮不实施）

P3.1 才在 `frontend/` 建立独立的 **React + TypeScript + Vite** 工程，并锁定与仓库 Node 运行时兼容的具体版本、包管理器和 lockfile。技术职责固定为：

- React Router：URL 定位选中的 Session/Run；
- TanStack Query：v1 服务器资源、cursor 页面、失效和刷新；
- Zustand：仅侧栏、展开状态、草稿、临时连接提示等 UI 状态，不复制 Session/Run/Result 事实；
- Ant Design：产品外壳、表单、状态、空/错误反馈；
- Vitest + React Testing Library + MSW：组件/交互及确定性 v1 mock；Vite build 作为构建质量门。

建议职责目录为 `src/app/`、`src/api/`、`src/features/sessions/`、`src/features/runs/`、`src/features/results/`、`src/components/`、`src/stores/`、`src/test/`；本 Design 不创建任何上述目录。

路由：`/` 重定向工作台；`/workbench` 展示真实空状态；`/workbench/sessions/:session_id` 恢复 Session；`/workbench/sessions/:session_id/runs/:run_id` 恢复选定 Run。外壳为顶部产品栏、左侧会话导航、中心工作区和右侧受控上下文栏，中心顺序固定为 Message → Run 状态/事件摘要 → 结构化结果。

## 4. 信息架构、空状态和阶段边界

| 区域 | P3 展示 | 明确不做 |
|---|---|---|
| 会话导航 | active/archived Session、创建、标题更新、归档、加载更多 | Environment/Incident 选择器或假数据 |
| 诊断工作区 | Message、问题表单、Run 状态、持久化事件摘要 | 真实日志/指标/数据库/K8s 连接器 |
| 结果区域 | summary、severity、confidence、root causes、evidence、impact、recommendations、risks、agent summary、可选 Markdown 补充 | Markdown 正则重建结构化事实；未审查 Trace 当证据 |
| 右侧栏 | 当前 Run、trace/request 关联、SSE 恢复提示、受控 Trace 入口 | Replay、Debate、Reflection、实验指标 |

P4 的 Environment/DataSource/Connector/Runbook/Knowledge，P5 的 Alert/Incident/ActionProposal/Approval/审计，P6 的导出、搜索、通知、偏好、report 深链均不实现。对应位置只允许明确“待 P4/P5/P6 接入”的诚实空状态，不能出现能编辑、提交或伪造这些资源的控件。`requires_approval` 仅展示为结果风险字段，不提供批准/执行动作。

## 5. 幂等、刷新恢复与 SSE

### 5.1 创建 Run

客户端为一次逻辑提交生成 UUID `Idempotency-Key`：`POST /sessions/{session_id}/runs` 返回 `202` 后切换到响应的 `run.id` 并刷新 Message/Run。超时或网络失败的“同一请求重试”必须复用原 key 和相同 query；用户编辑问题或明确开始新诊断才生成新 key。`409 IDEMPOTENCY_KEY_REUSED` 只显示安全冲突，不自动换 key 重发。刷新后优先恢复已受理 Run，绝不无人值守自动 POST。

### 5.2 固定恢复顺序

```text
1. GET Session（或先由 Session 列表定位）
2. GET /sessions/{session_id}/runs，按 cursor 恢复可见 Run
3. GET /sessions/{session_id}/messages，按 cursor 恢复时间线
4. URL run_id 优先；否则选择当前 Run 列表首项；无 Run 则真实空状态
5. GET /runs/{run_id}，读取 status、result/error、trace_id
6. GET /runs/{run_id}/events，按 cursor 汇总持久化事件
7. 仅 queued/running 时连接 /runs/{run_id}/stream；终态不保持 SSE
```

资源不存在、Session 已归档、Run 不属于当前 Session 或 cursor 失败时，清除无效 URL 定位，显示安全错误并回到可恢复列表；不得以缓存伪造资源。P2 cursor 未绑定 Session scope，故 Query key 和 cursor 生命周期必须绑定 Session，切换 Session 必须清空旧链。

### 5.3 SSE/断线

- 首选 `EventSource`，接收固定 `run_event`；浏览器自动重连依赖 SSE `id`（十进制 sequence）形成的 `Last-Event-ID`。
- 同一 EventSource 生命周期不手工追加冲突的 `after_sequence`；主动重建连接前先读取 Run/Events，再以最后确认 sequence 作为 `after_sequence`。
- 以 `(run_id, sequence)` 去重，严格递增渲染。收到 `run_succeeded`、`run_failed` 或 `run_cancelled` 后关闭流、失效并重读 Run/Result/Message。
- `EventSource.onerror` 先提示“正在恢复持久化事件”，再读取 Run/Events。`INVALID_EVENT_CURSOR`、`EVENT_CURSOR_EXPIRED` 或其他安全错误停止盲目重连，清除本地 sequence 并重新同步；不能把连接失败写成 Run failed。
- SSE 终态空流是正常恢复结果；SSE request ID 由服务端生成，客户端从 SSE headers/envelope 关联，不能试图在 EventSource 设置自定义 header。

## 6. `report/` 受控跳转

主产品只消费 `DiagnosisResult` 和安全 RunEvent 摘要。`report_markdown` 是补充，不能替代结构化字段。“完整 Trace”不可嵌入：仅当 `VITE_REPORT_URL` 被明确配置时显示外部入口；否则显示“完整 Trace 仅在研发界面可用”。当前没有确认的 trace deep-link 契约，因此 P3 不拼接 `trace_id`，不 iframe，不共享认证或本地状态；后续深链只能在 P6 另行设计。

## 7. 测试、mock 联调与人工验收

- P3.1：typecheck、Vitest 基础、`npm run build`，并确认 `frontend/mockup.html` 未被覆盖。
- P3.2+：用 MSW 提供严格同名、UTC `Z` 的 `/api/v1` mock，覆盖 Session 空/分页、Message、queued/running/succeeded/failed Run、结构化 Result、安全错误、cursor 与事件 sequence。
- Run/SSE 测试覆盖重复 sequence 去重、终态关闭、断线读恢复、cursor 安全降级、同 key 重试不变。
- 联调先用 MSW；之后仅以 `OPERMIND_API_KEY=mock`、`OPERMIND_BASE_URL=http://mock`、`OPERMIND_MODEL=mock` 启动 FastAPI。需要持久化时仅用 Alembic 临时数据库，禁止产生/提交 `data/opermind.sqlite3`、真实 DB/数据源/认证。
- 每个联调 Step 至少保留前端 build/测试、后端 v1 定向 smoke 与 `backend/scripts/smoke_pipeline.py` direct/chain/parallel/debate 回归。

人工验收：新建/刷新恢复 Session→Run→Message→Result/Event；运行中断线续传；成功结构化结果与失败安全错误均可恢复；超时重试不重复创建 Run；归档/空/无 Trace 配置诚实展示；确认无旧 API、无 P4/P5/P6 假功能、`report/` 仅受控跳转。

## 8. Step 分解和非目标

| Step | 交付 | 不混入 |
|---|---|---|
| P3.0（本轮） | Design、Review、HANDOFF、计划/规则/P2 历史状态校正 | 前端初始化或业务代码 |
| P3.1 | Vite React TS、Router/Query/Zustand/AntD Providers、产品外壳、基础路由、build/test 基线 | Session 恢复、Run 创建、SSE、P4/P5/P6 页面 |
| P3.2 | v1 client/同名类型/错误处理、Session/Message/Run 刷新读模型、MSW | Run 受理、旧 API |
| P3.3 | 诊断受理、幂等重试、状态/事件摘要、SSE 恢复 | Approval、真实连接器、完整 Trace |
| P3.4 | 结构化结果、失败/空/归档、report 受控跳转、交互收口 | P4/P5/P6 正式资源 |
| P3.5 | mock API 联调、人工验收、回归、独立 Review | 真实基础设施/生产认证 |

P3 不修改 `/api/v1`、Application Service、Repository、ORM、Alembic、旧接口或 `report/`；契约缺口必须回到后端 Design，不在前端猜字段。P2 的 BackgroundTasks、短连接 SSE 轮询和 SQLite 并发不是生产队列/高吞吐推送，P3 只正确恢复并展示，P7 处理生产加固。

## 9. 结论

本轮已完成 P3 Design，未初始化前端、安装依赖或修改业务代码。**用户授权提交后，唯一下一步为 P3.1：前端工程初始化与产品外壳。**