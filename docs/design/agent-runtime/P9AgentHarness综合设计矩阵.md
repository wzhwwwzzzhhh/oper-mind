# P9 Agent Harness 综合设计矩阵

> 状态：Reader Review 已通过，P9 研究与后续开发规划阶段已由用户确认收口，未授权实施
> 更新：2026-08-30
> 主 Design：[P9AgentHarness正式化Design.md](P9AgentHarness正式化Design.md)
> 审阅结果：[P9AgentHarnessReaderReview.md](P9AgentHarnessReaderReview.md)
> 最终取舍：[P9AgentHarness最终取舍与后续建议.md](P9AgentHarness最终取舍与后续建议.md)
> 范围：统一 capability、状态所有权、事件和失败处置语义；不是数据库 schema、公开 API 或 Workpack。

## 1. 文档目的

本文把已经讨论完成的十七组契约压缩成四张能共同工作的设计地图：

```text
Capability Matrix
  决定需要哪些能力、依赖什么、建议按什么顺序建设
        ↓
状态所有权与状态机
  决定谁可以改变什么、什么才是终态
        ↓
Event 字典与投影
  决定状态变化如何留痕、审计和安全展示
        ↓
Failure 决策表
  决定失败后 Retry、Resume、Replay、Recovery、Verify 还是终止
```

本文只收口语义。凡涉及迁移、公开 API、Connector、真实外部连接、权限、审批执行或运行时替换，仍必须单独 Design → Review → 用户确认。

## 2. 统一术语

| 术语 | 本文唯一含义 |
|---|---|
| Run | 一次用户可见的完整调查，不等于一次模型或图执行 |
| Plan | Run 当前采用的语义计划；修改 Plan 不改写已经发生的 Task 历史 |
| AgentTask | 有目标、范围、依赖、权限、输出和接受条件的语义工作单元 |
| Attempt | AgentTask 的一次具体执行；Retry 新建，Resume 保持原 Attempt |
| ToolCall | Attempt 内一次受控工具操作，拥有独立身份和副作用状态 |
| ResultCandidate | Runtime/Agent 产生的候选结果，不代表 Task 已完成 |
| Replay | 重新应用已经持久化的事实或 Outcome，不再次执行模型或 Tool |
| Resume | 在原 Attempt 上消费结构化响应或兼容 Checkpoint 后继续 |
| Retry | 创建新 Attempt，再次尝试同一 TaskSpec；同一 ModelCall/ToolCall 内明确允许的幂等传输重试称为“机械重试” |
| Recovery | 对齐非终态执行与持久化事实，可能选择 Replay、Resume、Retry、Verify 或人工处理 |
| Verify | 通过独立、通常只读的观察确认结果或外部动作后置条件 |
| Checkpoint | Runtime 私有恢复材料，不是业务事实或 Tool 执行证明 |
| Safe Trace | 面向用户的脱敏过程投影，不能驱动业务状态 |
| Harness Capability | Harness 自身需要建设的工程能力，例如 Persistence 或 Recovery |
| Agent Capability | AgentDefinition 声明的服务器能力需求；只有 Policy 产生的 Grant 才构成实际授权 |
| Outcome | 一次执行或外部事实的结果，不等同于对象生命周期状态 |
| FailureCode | 解释未达预期原因的封闭、稳定分类，不直接推进 lifecycle |
| Dispatch overlay | lease、generation、fencing 与 dispatch 的机械执行状态，不替代 Attempt lifecycle |
| Principal | 经过认证且可被 Policy 判断权限的主体；当前正式身份/审批人模型尚未决策 |

`queued` 只表示机械 dispatch 状态，不承担 Run 的业务语义。兼容期内，当前 API `Run.status=queued` 只可安全解释为“Run 尚未开始执行”，可能对应目标 `Run.created/planning + dispatch idle/lease_acquired/dispatch_recorded`；前端不得据此推断具体业务阶段。是否拆为独立 dispatch projection 必须在未来 API/迁移 Design 中决定。

## 3. Capability Matrix

### 3.1 能力成熟度口径

| 等级 | 含义 |
|---|---|
| L0 | 当前没有一等对象或可靠机制 |
| L1 | 有局部实现或可复用基础，但语义未统一 |
| L2 | 具备 typed contract、单组件状态和确定性测试 |
| L3 | 跨组件事务、权限、恢复和故障注入闭环完成 |

P9 只定义目标和依赖，不把任何能力从 L1 宣称为 L2/L3。为了避免把“先定义接口”误解成“能力已经可以运行”，依赖拆为：

- **定义依赖**：能够起草 typed contract 所需的概念，不要求行为已经激活；
- **行为激活前置**：进入正式调用链前必须已经通过测试和 Design 门的能力；
- **最早引入序位**：第一次建立接口或 shadow 记录的序位，不等于达到 L2/L3。

### 3.2 十七组能力总表

| # | 能力 | 当前 | P9 目标 | 定义依赖 | 行为激活前置 | 最早序位 | 必须单独 Design 的部分 | 完成证明 |
|---|---|---|---|---|---|---|---|---|
| 1 | AgentTask | L0：只有固定图节点和 Agent 结果 | 版本化 TaskSpec、控制状态、依赖和 AcceptanceProfile | State/Outcome/Failure 命名空间 | UoW/Event core、Policy decision port | B | 新表、API 投影 | Task 转移/决策/事件覆盖测试 |
| 2 | Attempt | L0：Run 只执行一次 | AttemptSpec、Outcome、Retry/Resume 区分和执行身份 | AgentTask、Binding/Context contract | Budget core、dispatch overlay、UoW/Event | B | 新表、迁移 | Retry/Resume/fencing/CAS 测试 |
| 3 | ToolCall/Result | L1：ToolGateway 与内存审计 | 持久化 ToolCall、四层结果、幂等和 unknown outcome | A 定义 ToolDefinition/effect metadata；B 后绑定 Attempt identity | Policy、Event、Budget；高风险时 Approval/Grant | A metadata，B identity，D 完成契约；只读路径按门禁激活，副作用语义最早 E | Tool 持久化、能力边界 | timeout/crash/duplicate/reconcile 测试 |
| 4 | Context | L1：每 Run 隔离、短期窗口、手工链式摘要 | 不可变 ContextManifest、角色视图、显式历史引用 | Task/Binding contract、classification schema | Policy/Redaction、Budget | B | 历史压缩、记忆和检索 | manifest round-trip/脱敏测试 |
| 5 | Event/Trace/Audit/Checkpoint | L1：RunEvent/ActionEvent/SSE 已存在 | Domain/Runtime/Audit/Trace/SSE/Checkpoint 分层 | 状态所有权与事件 envelope | UoW/Outbox、typed safe projection | A core，C durable | Event 覆盖、Outbox、保留策略 | transition coverage/reducer/reconnect 测试 |
| 6 | Orchestrator | L1：固定图内 LLM/关键词路由 | typed Snapshot/Decision，RunController 校验应用 | AgentTask/State/Snapshot contract | Event core、Budget read model、Policy decision port | B | 编排语义变化 | 决策去重、stall、非法决策测试 |
| 7 | Approval/HITL | L1：正式接口、二次确认、Verify | Proposal、Decision、Grant、ActionExecution 分离 | action identity、Tool effect、PolicyDecision | principal/approver 门、Grant 事务、ToolGateway、Event | D | 身份与审批人、审批/执行状态机 | substitution/forged/expired/consumed/crash 测试 |
| 8 | Recovery | L0：只有终态重读 | Lease、Fencing、对齐、Resume/Replay/Verify | Attempt/overlay、Tool/Approval/Event contract | durable persistence、幂等结果、reconciliation profile | E | durable worker/部署/迁移 | crash-window fault matrix |
| 9 | Budget/Deadline/Cancel | L1：max steps、局部 timeout、usage、直接 cancel | 分层预算、绝对 deadline、持久化 cancellation barrier | Run/Task/Attempt identity、ledger schema | UoW/Event、dispatch/Tool admission | C | 新状态/API/预算记录 | reservation/settlement/race/safety reserve 测试 |
| 10 | Runtime Adapter | L1：已有 DiagnosisExecutor 适配口 | Attempt 级 Adapter、RuntimeSignal、能力声明 | RuntimeExecutionSpec 与 signal namespace | Attempt identity、Tool proxy、fencing validation | A | Runtime 替换另审 | adapter contract suite |
| 11 | Agent/Role/Capability Registry | L1：Agent 类和 ToolRegistry | 版本化 Definition、Role、Agent Capability、Binding 分离 | version/identity schema | Resolver 与 Policy 消费端 | A | 动态插件/注册 | definition/version/capability 测试 |
| 12 | Policy/Grant | L1：安全规则分散在各组件 | 版本化 PolicyBundle、Deny Overrides、最小 Grant | A 使用 Registry/Tool effect metadata 建 port；B 接 Task scope | current Hard Policy adapter、fail-closed、principal gate | A port，B scope，D 完整治理 | 权限模型全部需 Review | deny precedence/substitution/fail-closed 测试 |
| 13 | Verifier/Acceptance | L1：Reflection、保守 Assembler、Action Verify | Contract/Evidence/Safety/Semantic/Action 分层 | Task/Result/Evidence contract | Event、typed validators；L3 需独立 observation | B | 事实来源/Judge | unsupported claim/inconclusive/recursion 测试 |
| 14 | Config/Model Routing | L1：每 Run 执行时解析全局配置 | Attempt 级 BindingSnapshot、确定性 Router、无静默 fallback | Registry、Context requirement | Policy/Budget/Runtime capability | B | 模型控制行为/API | binding/executed truth 测试 |
| 15 | Persistence | L1：当前状态与部分事件同事务 | Current+Immutable+DomainEvent+Outbox+Checkpoint 混合模型 | State/Event/record schema | migration、UoW、repair procedure | A port，C durable | 所有迁移 | transaction/reducer/repair 测试 |
| 16 | Middleware Ordering | L0：安全顺序散落在组件内部 | Command/Runtime/Model/Tool/Acceptance 固定 Pipeline | Adapter port、stage contract | 每个 stage 对应的 Policy/Budget/Redaction 组件 | A 骨架，随阶段激活 | 权限 middleware | 顺序、短路、不可绕过测试 |
| 17 | Eval/Fault Injection | L1：确定性 mock 与聚焦契约测试 | Contract/Security/Recovery 硬门禁和故障矩阵 | invariants 与 deterministic harness | 每序位固定 oracle/场景全集 | A→E | 真实资源测试需单独授权、目标边界与脱敏方案 | 固定分母内硬门禁 100% 通过、无 skip/xpass |

### 3.3 建议未来建设序位

以下只是依赖顺序，不是已批准阶段或 Workpack：

| 序位 | 目标 | 首次建设内容 | 行为激活边界 |
|---|---|---|---|
| A：语义内核与现状保护 | 建立无行为变化的共同语言和不可绕过端口 | State/Outcome/Failure 命名空间、Runtime Adapter port、Registry/ToolDefinition metadata、UoW/Event/Policy core port、Pipeline/Eval 骨架 | 只包裹和 shadow 验证现有链路；当前 ToolGateway、只读边界和固定动作审批不得改变 |
| B：业务执行脊柱 | 建立稳定业务身份和决策协议 | Task、Attempt、Context、Binding、Orchestrator、Acceptance typed contract | 先 shadow record/contract test；未具备 C 的 durable 事务与 overlay 前不接管生产状态 |
| C：可靠控制面 | 建立可持久化、可调度、可取消的事实基础 | Current State、DomainEvent、Outbox、Budget ledger、cancellation barrier、dispatch/lease/fencing overlay | 迁移/API 单独 Design；先 dual-read/shadow，对账通过后再切权威写入 |
| D：工具与安全治理 | 闭合 Tool、Policy、Approval、Grant、Evidence、Action Verify | Tool execution contract、PolicyBundle、Grant 签发/消费事务、typed safe projection | 只定义、测试和 shadow 新语义；现有固定动作继续走现有已确认路径。包括现有动作迁移在内，任何 Grant/dispatch 语义切换都等待 E 的最小 reconciliation/recovery/kill switch 门 |
| E：恢复与受控激活 | 对稳定事实执行恢复并逐项开启新路径 | RecoverySupervisor、fault matrix、backfill/repair、kill switch、逐能力 activation | 只有 crash-window、回滚和安全门禁通过的能力才能启用；不做一次性切换 |

任何序位都不得一次覆盖超过 1–3 个紧密切片。“最早引入”只表示定义接口或记录 shadow 事实；行为必须等“激活前置”全部满足。D 的契约可在 E 前完成，但任何新增或改变副作用 dispatch/Grant 消费语义的切换——包括迁移现有固定动作——都不得在最小 reconciliation/recovery、unknown outcome、kill switch 和回退策略可用前启用。

## 4. 状态所有权

### 4.1 唯一写入者

| 对象 | 权威写入者 | 可以提出变化但不能写入者 | Runtime 是否拥有 |
|---|---|---|---|
| Run / Plan / AgentTask / Attempt | RunController | Orchestrator、Scheduler、AttemptRunner、RecoverySupervisor | 否 |
| Dispatch/Lease/Fencing | ExecutionCoordinator 通过 UoW | AgentTaskScheduler、RecoverySupervisor、Worker | Runtime 只持有收到的 token |
| ToolCall / ToolResult | ToolGateway 通过 UoW | Agent、Runtime Adapter、Connector | 否 |
| ContextManifest | ContextAssembler 通过 UoW | Agent 的 ContextRequest、Orchestrator | 否 |
| AgentBindingSnapshot | ExecutionConfigResolver 通过 UoW | ModelRouter、Registry、PolicyEngine | 否 |
| ApprovalProposal / Decision / Grant | ApprovalCoordinator 通过 UoW | Agent、Human、PolicyEngine | 否 |
| ActionExecution | ActionExecutionService 通过 UoW | ToolGateway、Connector、VerificationService | 否 |
| BudgetLedger | BudgetManager 通过 UoW | Orchestrator、Scheduler、Adapter usage signal | 否 |
| Evidence / VerificationReport | EvidenceService/VerificationService 通过 UoW | Tool、Agent、Verifier | 否 |
| DomainEvent / Outbox | 领域事实 owner 构造，EventRecorder/HarnessUnitOfWork 原子持久化 | 所有领域组件可以提交事实命令 | 否 |
| Checkpoint | CheckpointPort | Runtime Adapter | Runtime 只产生 opaque blob |
| Runtime-private state | AgentRuntimeAdapter | Runtime 实例 | 是，但不能作为业务真相 |
| AutomationGate / RepairCase | RepairCoordinator，经独立 fail-closed 存储 | Persistence invariant monitor、RecoverySupervisor、Operations command | 否；不是领域状态 |

“RunController 是状态权威”只覆盖 Run、Plan、Task 和 Attempt。它通过专用服务与 HarnessUnitOfWork 协调其他对象，不代替 Tool、Approval、Budget、Evidence 的领域所有者。

### 4.2 关键事务边界

| 事务 | 必须原子提交 | 事务外动作 |
|---|---|---|
| CreateRun | Run current state、首个 DomainEvent、Outbox、幂等记录 | 无 |
| ApplyOrchestrationDecision | Run/Plan/Task 版本变化、Decision receipt、DomainEvent、Outbox | 之后再由 Scheduler dispatch |
| CreateAttempt | AttemptSpec、Binding/Context/Pipeline snapshot、预算预留、DomainEvent、Outbox | Runtime start |
| AcquireAttemptLeaseAndDispatch | dispatch id、owner、lease、generation、fencing token、dispatch intent、overlay version、DomainEvent、工作命令 Outbox | Worker 消费命令 |
| AcceptWorkerStarted | 校验 dispatch/generation/token 后的 receipt、Attempt `starting/running`、DomainEvent、Outbox | Worker 继续执行 |
| Renew/Expire/ReassignLease | overlay CAS、lease/generation/token 变化、DomainEvent、Outbox | 需要时发布新的工作命令 |
| RecordToolDispatch | ToolCall state、dispatch intent、幂等键；高风险时消费 Grant、DomainEvent、Audit、Outbox | Connector 调用 |
| RecordToolResult | 已分类安全结果引用、ToolResult、Evidence extraction intent、ToolCall 级 usage ledger、DomainEvent、Outbox | 后续投影/验证 |
| RecordApprovalDecision | immutable Decision、Proposal 状态、DomainEvent、Audit、Outbox | 之后才可签发 Grant |
| IssueExecutionGrant | 当前 Proposal/Decision/Policy/cancel/deadline/version CAS、唯一 action identity、精确 Grant、`ActionExecution=authorized`、`ExecutionGrantIssued`、`ActionAuthorized`、Audit、Outbox | 之后才可调度动作；Grant 与 authorized Action 不存在提交裂缝 |
| FinalizeAttempt | AttemptOutcome、Attempt 级 reservation 结算/释放、DomainEvent、Outbox | Result Acceptance；不得重复结算 Tool ledger |
| AcceptTaskResult | VerificationReport、AcceptedTaskResult、Task completed、Task 级聚合 ledger、DomainEvent、Outbox | 调度下游 Task |
| RequestCancel | cancel_requested、撤销未消费 Grant、DomainEvent、Outbox | cooperative cancellation / Verify |

外部模型、Connector、Runtime 和 Verify 调用不得跨数据库事务。`State + DomainEvent + Outbox` 缺任一项都属于持久化不变量故障。

### 4.3 Dispatch/Lease/Fencing overlay

Dispatch 是机械执行 overlay，不是 Attempt 业务状态：

```text
idle → lease_acquired → dispatch_recorded → worker_started → released
          │                  │                 │
          └──────────────────┴─────────────────┴→ lease_expired
                                                   ↓
                                               reassigning
                                                   ↓
                                             lease_acquired(new generation)
```

规则：

- `AcquireAttemptLeaseAndDispatch` 在一个事务中生成稳定 `dispatch_id`、单调 `generation`、不可猜测 fencing token、lease 和工作命令 Outbox；不能先启动 Worker 再补 intent；
- 工作命令至少一次投递。Worker 使用 `dispatch_id + generation` 去重，所有 heartbeat、RuntimeSignal、Tool proposal 和 AttemptOutcome 都必须携带 fencing token；
- Scheduler 只推进 overlay。Worker started receipt 通过 token/CAS 校验后，由 RunController 推进 Attempt `created → starting → running`；
- lease renewal、expiry 和 reassignment 使用 overlay version CAS；reassign 必须增加 generation 并使旧 token 失效；
- 旧 Worker 的结果可以保存受限诊断摘要，但不能推进 Attempt、Tool、Budget 或 Result 状态；
- `AttemptDispatched` 不再作为 Attempt lifecycle 事件；使用 `AttemptDispatchRecorded` 记录 overlay 事实，避免两个 owner。

### 4.4 Persistence repair gate

`State/DomainEvent/Outbox` 不一致时，不允许通过同一条已失去可信度的领域事务“补写一个正常事件”。Invariant monitor 必须请求 RepairCoordinator 在独立安全存储中原子写入 `AutomationGate=blocked_for_repair` 与 RepairCase：

- AutomationGate 是 fail-closed 运维控制状态，不是 Run/Task/Attempt lifecycle，也不是 dispatch overlay；
- gate 只由 RepairCoordinator 写入；RecoverySupervisor/Operations 只能提交阻断或修复命令。它存入与故障 UoW 隔离的安全控制存储，并发送受限安全告警；
- gate 阻止相关 Run/aggregate 的自动调度、Retry、Grant 签发和 Tool dispatch，但保留只读诊断；
- 只能由授权人工 repair receipt、重新校验 reducer/invariant 并记录独立审计后解除；
- 原领域历史不能伪造或静默补齐，修复方式仍需未来 Persistence Design 明确。

## 5. 完整状态机

### 5.0 七类正交维度

任何对象都不得把生命周期、结果和失败原因写入同一个 `status` 字段：

| 维度 | 回答的问题 | 示例 |
|---|---|---|
| `lifecycle_state` | 对象现在走到哪一步 | `running`、`waiting`、`completed` |
| `result_disposition` | 这次执行是否形成可接受结果 | `complete_result`、`partial_result`、`no_result`、`pending` |
| `external_outcome` | 外部操作是否发生及其可信结论 | `not_executed`、`executed_unverified`、`succeeded`、`failed`、`outcome_unknown` |
| `failure_code` | 为什么未达到预期 | `invalid_output`、`runtime_unavailable`、`budget_exceeded` |
| `resolution_disposition` | 谁负责继续收敛，不改变外部事实 | `automatic`、`manual_required` |
| dispatch overlay | 机械执行由谁持有、是否可重派 | `lease_acquired`、`dispatch_recorded`、`lease_expired` |
| control overlay | 是否允许自动推进 | `normal`、`blocked_for_repair` |

因此：`partial` 是 ResultDisposition，`invalid_output` 是 FailureCode，`typed runtime failure` 是稳定 FailureCode 家族，`outcome_unknown` 是 ExternalOutcome，`manual_required` 是 ResolutionDisposition，`Recovery Attempt` 是 `attempt_kind`，都不是可随意写入任意状态机的 lifecycle state。转人工时仍保持 `external_outcome=outcome_unknown`，不能用 manual_required 覆盖事实。枚举必须封闭并版本化；FailureCode 至少按 validation/runtime/model/tool/policy/approval/budget/cancel/recovery/persistence/internal 分 namespace。

对象与字段适用性固定如下；“—”表示该对象不拥有该维度：

| 对象 | lifecycle writer | ResultDisposition writer | ExternalOutcome writer | FailureCode writer | ResolutionDisposition writer | overlay writer |
|---|---|---|---|---|---|---|
| Run | RunController | RunController 根据 AcceptedTaskResult 聚合 | RunController 只冻结 `side_effect_resolution` 聚合 | RunController | RunController | RepairCoordinator 只写 control gate |
| AgentTask | RunController | RunController 根据 AcceptanceReport 写 TaskResult | — | RunController | — | 继承 Run control gate |
| Attempt | RunController | RunController 根据 AttemptOutcome receipt 写入 | —；只引用 Tool/Action outcome | RunController | — | ExecutionCoordinator 写 dispatch overlay |
| ToolCall | ToolGateway | — | ToolGateway | ToolGateway | ToolGateway | — |
| ApprovalProposal / ExecutionGrant | ApprovalCoordinator | — | — | ApprovalCoordinator | — | — |
| ActionExecution | ActionExecutionService | — | ActionExecutionService | ActionExecutionService | ActionExecutionService | — |
| Interruption | RunController | — | — | RunController | — | — |
| AutomationGate / RepairCase | RepairCoordinator | — | — | RepairCoordinator | RepairCoordinator | RepairCoordinator |

AttemptRunner、Verifier、Connector、Scheduler 和 Operations 都只能提交 typed receipt/report/command；上表 writer 校验 expected version 后才写 current state 与事件。

### 5.1 Run 业务状态

```text
created → planning → running ↔ waiting → completing → completed
   │          │          │          │          │
   ├──────────┴──────────┴──────────┴──────────┴→ cancel_requested → cancelling
   │                                                              └→ cancelled
   └──────────┬──────────┬──────────┬──────────┬→ failing
                                                     └→ failed
```

规则：

- `completed` 需要所有必需 Task 已接受、无待处理请求、无未验证高风险动作；
- `cancel_requested/cancelling` 均非终态；
- `queued/leased/recovering` 属于执行 overlay，不替代业务状态；
- Recovery 不能绕过 planning、acceptance、policy 或 cancellation 前置条件；
- 任一非终态 Run 都可先原子写入 `cancel_requested`；RunController 建立 cancellation barrier 后才进入 `cancelling`；
- Run lifecycle 只保存 `completed/failed/cancelled`，不把 unknown 编进状态名。终态记录同时冻结 `side_effect_resolution=clear/outcome_unknown` 和 `resolution_disposition=automatic/manual_required`；pending 时不得终止。若最终仍不可判定，Safe Projection/API 必须显示复合标签 `failed_with_unknown_outcome/cancelled_with_unknown_outcome`，并永久保留 limitation、审计和 reconciliation 引用；复合标签不是 lifecycle state。

### 5.2 AgentTask

```text
proposed ├→ rejected
         └→ accepted → ready → running ↔ waiting → result_ready
                 │         │        │          │          ├→ completed
                 └─────────┴────────┴──────────┴──────────┼→ cancelled
                                                          ├→ failed
                                                          └→ superseded
```

- TaskSpec 变化必须 supersede，不得原地改写；
- `result_ready` 只表示存在 ResultCandidate；
- `completed` 只能由 RunController 在 Acceptance 通过后写入。
- 任一非终态 Task 都可以进入 `cancelled`，或因新 TaskSpec 进入 `superseded`；已经产生的 Result/Evidence 历史不删除。
- `rejected` 表示 Orchestrator proposal 经 RunController 校验后未被接受；必须保存拒绝原因和 Decision receipt，不能伪装成未发生。

### 5.3 Attempt

```text
created → starting → running ↔ waiting
                         │          │
                         ├──────────┼→ succeeded
                         ├──────────┼→ failed
                         ├──────────┼→ timed_out
                         └──────────┴→ cancelled
```

- Resume：`waiting → running`，保持 Attempt、Binding 和原 ContextManifest；
- Retry：从 Task 创建新 Attempt，不从终态 Attempt 回跳；
- `succeeded` 表示产生结构有效的 AttemptOutcome，不等于 Task completed。
- 任一非终态 Attempt 都可以因有效取消进入 `cancelled`；如果外部 Tool 可能仍在运行，ToolCall 独立保持 `outcome_unknown`。
- `attempt_kind` 至少区分 `initial/retry/recovery`；Recovery Attempt 是新 Attempt，消耗独立 recovery budget，并计入单独的 recovery limit，不与普通 retry limit 混用。
- Attempt 终态只生成结构化 Outcome/FailureCode；Task 是进入 `result_ready`、重新 `ready` 还是 `failed`，由 RunController 应用 Orchestrator/Policy 决策，不能由 Runtime 直接归约。

### 5.4 ToolCall

```text
proposed → validating ───────────────→ scheduled → running ──────────→ terminal
             │              ↑                       │                     ↑
             │              │                       └→ reconciling ───────┘
             ├→ awaiting_approval ─────────────────┘
             └──────────────────────────────────────────────────────→ terminal
```

- terminal 的 `external_outcome` 可以是 `not_executed/succeeded/failed`；只有 `resolution_disposition=manual_required` 时允许以 `external_outcome=outcome_unknown` 终止。`timed_out/cancelled` 是 FailureCode 或控制原因，不能证明 Connector 已停止；
- 有副作用且无法证明结果时，lifecycle 必须进入 `reconciling`，`external_outcome=outcome_unknown`；
- 只读且 Policy 不要求确认的 Tool 使用 `validating → scheduled`；需要正式审批时必须经 `awaiting_approval`，收到精确有效 Grant 后才能 scheduled；
- Policy deny、schema invalid、审批拒绝/过期/撤销在 dispatch 前直接进入 terminal，`external_outcome=not_executed`，但使用不同 FailureCode；
- `external_outcome=outcome_unknown` 只能处于 reconciliation，不能直接 Retry；`not_executed` 必须由幂等查询、外部执行记录或等价的强证据证明，不能由 timeout 推断。

### 5.5 ApprovalProposal、ExecutionGrant 与 ActionExecution

```text
ApprovalProposal:
created ├→ policy_denied
        └→ policy_validated → pending_human
                                  ├→ approved
                                  ├→ rejected
                                  ├→ expired
                                  ├→ revoked
                                  └→ superseded

ExecutionGrant:
issued ├→ consumed
       ├→ expired
       └→ revoked

ActionExecution:
authorized ─────────────────────────────────────────→ terminal
    │
    └→ executing → verifying ───────────────────────→ terminal
                      ↑                                  ↑
                      └──── reconciling ─────────────────┘
```

ApprovalProposal 在 approved 后保持审批历史；不能继续变为 executing/verifying/verified。Grant consumed 后不可恢复为 issued，也不可因结果缺失而重复签发。

ActionExecution 在 `executing` 结果未知时进入 `reconciling + external_outcome=outcome_unknown`；确认已执行后进入 `verifying + external_outcome=executed_unverified`。terminal 的 ExternalOutcome 为 `succeeded/failed/not_executed`；`postcondition_failed`、`execution_failed`、`verification_inconclusive` 都是不同 FailureCode。若仍可安全复核则保持 reconciling/verifying；放弃自动复核时以 `external_outcome=outcome_unknown + resolution_disposition=manual_required` 终止，未知事实不被覆盖。

Grant 在消费前 expired/revoked，或 Run cancel/Hard Policy 使 dispatch 失效时，Action owner 使用 Grant/version CAS 将 `authorized → terminal`，写 `external_outcome=not_executed` 和对应 FailureCode；不能遗留永久 authorized Action。

`IssueExecutionGrant` 必须幂等并原子检查：Proposal/Decision version、当前 Hard Policy 与 revocation generation、Run/Task/Attempt 非终态且未取消、deadline、action identity/digest、service/resource、审批 principal 权限和 Grant 唯一性。任何绑定字段变化均 fail closed。当前身份/审批人模型未完成独立 Design 前，不得泛化该能力，只能保持已经确认的固定动作边界。

### 5.6 Interruption

```text
open → responded → consumed
  ├→ expired
  ├→ revoked
  └→ superseded
```

UserInput、ToolConfirmation 和 ApprovalProposal 使用不同 request type。`responded` 只表示结构化响应已落盘；Attempt 真正消费响应后才进入 `consumed`。

传播规则：

- `responded → consumed` 后 Resume 原 Attempt；
- `expired/revoked/superseded` 必须唤醒等待 Attempt，并写入对应 FailureCode，由 RunController 决定 replan、retry 或受控失败；
- Run cancel 时所有未消费 Interruption 都进入 revoked/superseded，迟到响应只留受限审计，不得恢复 Attempt；
- ToolConfirmation 只适用于经 Policy 定义的低风险确认，不能代替正式 ApprovalProposal。

### 5.7 核心转移覆盖表

下表是语义覆盖要求，不是数据库 schema。后续实现 Design 必须展开为逐转移测试，不能删减 guard：

| 对象 | 转移族 | 权威 owner | 必须 guard/receipt | DomainEvent |
|---|---|---|---|---|
| Run | created/planning/running/waiting/completing | RunController | expected run version、Plan/Task 聚合条件 | 对应 `Run*` lifecycle event |
| Run | 任一非终态 → cancel_requested → cancelling | RunController | cancel idempotency、barrier snapshot、未消费 Grant 撤销 | `RunCancelRequested`、`RunCancelling` |
| Run | cancelling/failing → cancelled/failed | RunController | 同事务冻结 side-effect resolution；unknown/manual 必须带 references | `RunCancelled/RunFailed` + `RunSideEffectResolutionFrozen` |
| AgentTask | proposed → accepted/rejected | RunController | OrchestrationDecision receipt、TaskSpec version、Policy | `AgentTaskAccepted/Rejected` |
| AgentTask | ready/running/waiting/result_ready/终态 | RunController | dependency、Attempt outcome、AcceptanceReport、cancel/supersede version | 对应 `AgentTask*` event |
| Attempt | created → starting/running | RunController | 有效 dispatch id/generation/fencing receipt | `AttemptStarting/Started` |
| Attempt | running ↔ waiting | RunController | typed Interruption id/response version | `AttemptInterrupted/Resumed` |
| Attempt | 非终态 → 终态 | RunController | AttemptOutcome、有效 fencing、预算结算 receipt | 对应 `Attempt*` terminal event |
| Dispatch overlay | lease/dispatch/renew/expire/reassign | ExecutionCoordinator | overlay CAS、单调 generation、lease owner/token | 对应 `AttemptLease*/AttemptDispatch*` event |
| ToolCall | proposed/validating → scheduled 或 terminal | ToolGateway | schema、ToolDefinition version、PolicyDecision；需要时精确 Grant | `ToolCallValidated/Rejected/ApprovalRequired/Scheduled` |
| ToolCall | scheduled/running → terminal/reconciling | ToolGateway | persisted dispatch intent、idempotency、分类结果或 unknown 事实 | `ToolDispatchRecorded/ToolCall*/ToolOutcomeUnknown` |
| ToolCall | reconciling → terminal/manual | ToolGateway/RecoverySupervisor 提议，ToolGateway 写入 | reconciliation profile、强证据或人工接管 receipt | `ToolProvenNotExecuted/ToolOutcomeReconciled/ToolManualRecoveryRequired` |
| ApprovalProposal | created → policy_denied/pending_human/终态 | ApprovalCoordinator | proposal version、PolicyDecision、principal/auth context、expiry | 对应 `Approval*` event |
| ExecutionGrant | issued → consumed/expired/revoked | ApprovalCoordinator；消费由 ToolGateway UoW | action digest、当前 Policy/cancel/deadline、唯一 nonce/version | 对应 `ExecutionGrant*` event |
| ActionExecution | authorized → terminal(not_executed) | ActionExecutionService | 未消费 Grant expired/revoked、cancel/Hard Policy、Grant version CAS | `ActionProvenNotExecuted` |
| ActionExecution | authorized/executing/verifying/reconciling/terminal | ActionExecutionService | consumed Grant、dispatch fact、独立 VerificationReport/ReconciliationReport | 对应 `Action*` event |
| Interruption | open/responded/consumed/expired/revoked/superseded | RunController | request type/schema/version/expiry、Attempt/Run 状态 | 对应 `Interruption*` event |
| AutomationGate | normal → blocked_for_repair → normal | RepairCoordinator | invariant alarm；解除需授权 repair receipt + reducer/invariant 复验 | 独立安全告警/审计，不伪造 DomainEvent |

领域服务是事件事实产生者；EventRecorder/HarnessUnitOfWork 只是原子持久化协调者。二者不构成双 owner。

## 6. Event 字典与投影规则

### 6.1 DomainEvent Envelope

每个业务事件至少包含：

```text
event_id
run_id + run_sequence
aggregate_type + aggregate_id + aggregate_version
event_type + schema_version
actor + source
causation_id + correlation_id + idempotency_key
occurred_at + recorded_at
classification
payload
```

同一 Run 的 `run_sequence` 权威递增；同一 Aggregate 还使用 `aggregate_version` 做乐观并发检查。事件 payload 只保存业务事实和安全引用，不保存凭据、Prompt、CoT、原始异常、原始 SQL 或原始 Tool 输出。

### 6.2 核心 DomainEvent 家族

| 家族 | 核心事件 | 权威产生者 | 最小业务含义 |
|---|---|---|---|
| Run | `RunCreated`、`RunPlanningStarted`、`RunStarted`、`RunWaiting`、`RunCompleting`、`RunCompleted`、`RunFailing`、`RunFailed` | RunController | Run 业务生命周期变化 |
| Cancellation | `RunCancelRequested`、`RunCancelling`、`RunCancelled` | RunController | 取消请求、对齐过程和最终结果 |
| Side-effect resolution | `RunSideEffectResolutionFrozen` | RunController | 终态时冻结 `clear/outcome_unknown`、`automatic/manual_required` 及安全引用；复合 UI 标签由投影生成 |
| Plan/Task | `PlanUpdated`、`AgentTaskProposed`、`AgentTaskRejected`、`AgentTaskAccepted`、`AgentTaskReady`、`AgentTaskStarted`、`AgentTaskWaiting`、`AgentTaskResultReady`、`AgentTaskCompleted`、`AgentTaskFailed`、`AgentTaskCancelled`、`AgentTaskSuperseded` | RunController | 计划与语义 Task 历史 |
| Attempt | `AttemptCreated`、`AttemptStarting`、`AttemptStarted`、`AttemptInterrupted`、`AttemptResumed`、`AttemptSucceeded`、`AttemptFailed`、`AttemptTimedOut`、`AttemptCancelled` | RunController | 一次执行的业务身份与 Outcome |
| Dispatch overlay | `AttemptLeaseAcquired`、`AttemptDispatchRecorded`、`AttemptWorkerReceiptAccepted`、`AttemptLeaseRenewed`、`AttemptLeaseExpired`、`AttemptLeaseReassigned`、`StaleWorkerResultRejected` | ExecutionCoordinator | 机械执行所有权、generation 与 fencing 事实 |
| Tool | `ToolCallProposed`、`ToolCallValidated`、`ToolCallRejected`、`ToolCallApprovalRequired`、`ToolCallScheduled`、`ToolDispatchRecorded`、`ToolCallStarted`、`ToolCallSucceeded`、`ToolCallFailed`、`ToolCallTimedOut`、`ToolCallCancelled`、`ToolOutcomeUnknown`、`ToolReconciliationStarted`、`ToolProvenNotExecuted`、`ToolOutcomeReconciled`、`ToolManualRecoveryRequired` | ToolGateway | 工具调用和副作用事实 |
| Approval | `ApprovalProposalCreated`、`ApprovalPolicyDenied`、`ApprovalDecisionRecorded`、`ApprovalExpired`、`ApprovalRevoked`、`ApprovalSuperseded` | ApprovalCoordinator | 正式人工授权历史 |
| Grant/Action | `ExecutionGrantIssued`、`ExecutionGrantConsumed`、`ExecutionGrantExpired`、`ExecutionGrantRevoked`、`ActionAuthorized`、`ActionExecutionStarted`、`ActionExecutionFailed`、`ActionExecutedUnverified`、`ActionVerified`、`ActionPostconditionFailed`、`ActionVerificationInconclusive`、`ActionOutcomeUnknown`、`ActionReconciliationStarted`、`ActionProvenNotExecuted`、`ActionManualRecoveryRequired` | ApprovalCoordinator 产生 Grant 事件；ActionExecutionService 应用 VerificationReport 并产生 Action 事件 | 授权消费、动作事实与不确定性收敛；ToolGateway/Verifier 只提交 command/report |
| Context/Binding | `ContextManifestCreated`、`AgentBindingCreated` | ContextAssembler / Resolver | 本次执行输入与实际 Binding |
| Interruption | `InterruptionOpened`、`InterruptionResponded`、`InterruptionConsumed`、`InterruptionExpired`、`InterruptionRevoked`、`InterruptionSuperseded` | RunController | 结构化等待与唤醒事实 |
| Budget | `BudgetReserved`、`BudgetSettled`、`BudgetReleased`、`BudgetSoftThresholdReached`、`BudgetExceeded` | BudgetManager | 资源预留与结算事实 |
| Verification | `ResultCandidateRecorded`、`VerificationCompleted`、`VerificationInconclusive`、`ResultAccepted`、`ResultRejected` | VerificationService / RunController | 候选结果、验证和接受 |
| Recovery | `RecoveryDecisionRecorded`、`AttemptReattached`、`RecoveryAttemptCreated`、`ManualRecoveryRequired` | RecoverySupervisor 提议，RunController 应用业务变化 | 恢复判断与对齐结果；lease expiry 只使用 Dispatch overlay 的 `AttemptLeaseExpired` |

不是每个 Runtime signal 都生成 DomainEvent。只有影响业务状态、权限、预算、事实或恢复能力的变化才进入该字典。

覆盖规则：每个 current-state lifecycle 转移必须在实现 Design 中映射为唯一 DomainEvent，并由该 aggregate owner 经 expected version CAS 提交；dispatch overlay 使用自己的事件家族。没有 current-state 变化的高频 Runtime signal 才可不生成 DomainEvent。状态/event 覆盖率必须为 100%，缺失映射时不能激活该状态机。

### 6.3 六类记录的映射

| 来源 | DomainEvent | Runtime Event | Audit Event | Safe Trace | SSE | Checkpoint |
|---|---|---|---|---|---|---|
| 用户创建/取消 Run | 必须 | 否 | 取消可审计 | 用户可见摘要 | 从 Outbox 发布 | 否 |
| Orchestrator Decision | 应用成功后必须 | 可有耗时 signal | 保存决策类型/版本 | 只展示计划变化摘要 | 是 | 否 |
| Model call lifecycle | 通常否；usage 结算可产生预算事件 | 必须/可采样 | 敏感模型路由可审计 | 只展示“模型处理”状态，不展示 Prompt | 可选采样 | Runtime 决定 |
| AgentTask proposal | 接受或拒绝结果必须 | `runtime.AgentTaskProposalObserved` | 可审计来源 | 展示安全角色/任务摘要 | durable projection | 可引用 |
| Tool proposal/dispatch/result | 必须 | Runtime 只提出 | Policy/Grant/敏感调用必须 | 工具类别、状态、耗时、Evidence 摘要 | 是 | 只引用已持久化 ToolResult |
| Approval/Grant | 必须 | interruption signal | 必须 | 展示待审批/决定/执行状态 | 是 | 可记录等待位置，不保存决定真相 |
| Checkpoint 生成 | 仅在影响恢复可用性时记录 metadata event | `runtime.CheckpointProduced` | 通常否 | 不展示 blob | ephemeral 或不发布 | blob 只进 CheckpointPort |
| 原始异常 | 只映射稳定 FailureCode | 受限内部错误 | 安全错误类别 | 中性失败摘要 | 安全终态 | 不保存原始异常 |

### 6.4 Safe Trace 允许字段

```text
role / stage / state / duration_ms
tool_category / safe_evidence_summary
service_safe_id / limitation / user_action_required
```

明确禁止：CoT、Prompt、完整消息上下文、原始工具输入输出、原始异常、原始 SQL、连接串、凭据、未经分类的模型文本、Checkpoint blob 和内部 Policy 细节。

所有用户可见 Trace、REST、SSE、审计摘要和导出字段只能由 typed fact 经确定性 allowlist projection 生成。未经分类的模型文本、异常文本和 Tool payload 默认拒绝；不能把“summary”当成绕过分类的自由文本字段。负向测试必须覆盖 Prompt 注入、凭据、连接信息、原始 SQL、异常、超长文本和跨服务引用。

RawExecutionResult 是进程内受限对象，不等于允许持久化的 Blob。进入任何持久化前必须完成 schema 过滤、classification、secret detection 和 redaction；`RecordToolResult` 只接受已分类安全结构或受控引用。若未来确需保存受限原始 Blob，必须单独完成数据安全 Design，明确加密、访问主体、服务隔离、TTL/删除、审计和泄漏处置；该 Design 获批前不得持久化任意原始 payload。

### 6.5 SSE 与 Outbox

- Domain state、DomainEvent 和 Outbox 在同一事务提交；
- Durable SSE 只承载已持久化 Safe Projection；projection 使用稳定 `projection_id` 和单调 `stream_sequence`，并保存来源 `run_sequence`；
- Outbox 至少一次发布，客户端按 projection id 去重、按 `stream_sequence` 补播；
- 高频 Runtime progress 若确有价值，只能进入显式 `ephemeral` 通道；它不可补播、不参与 durable gap 判断，UI 必须允许丢失并以 durable state 校正；
- SSE 断连只影响传输，不取消 Run；
- Safe Trace 是已提交事实的投影，不能产生新的业务状态；
- State/Event/Outbox 不一致进入 `PersistenceInvariantViolation`，不能静默补写伪造历史。

## 7. Failure 与控制决策

### 7.1 决策优先级

遇到失败或恢复时按以下顺序判断：

1. 当前 Hard Policy、Emergency Revocation、Run cancellation 和领域终态是否允许继续；
2. 是否存在可能已经发生但尚未确认的外部副作用；
3. 是否已有持久化 ToolResult、AttemptOutcome、Decision 或用户响应可以 Replay；
4. 原 Attempt 是否能通过结构化响应或兼容 Checkpoint Resume；
5. 是否满足安全、预算、deadline、attempt limit 和幂等条件创建 Retry；
6. 否则受控失败、暴露 limitation 或进入人工恢复。

绝不能先问“能不能重跑”，再检查副作用和持久化事实。

### 7.2 Retry / Resume / Replay / Recovery / Verify 决策表

| 场景 | 权威事实 | 处置 | Attempt 语义 | Tool 是否可再执行 | 目标 lifecycle | Attempt/Task ResultDisposition | Tool/Action ExternalOutcome | FailureCode owner.code |
|---|---|---|---|---|---|---|---|---|
| ExecutionSpec 校验失败，尚未创建 Attempt | 无外部执行 | 修正输入或拒绝创建 | 不创建 | 无 | Task `ready` 或 `failed` | `no_result` | n/a | `Task.invalid_execution_spec` |
| Runtime 启动前不可用 | 无 runtime dispatch | 若策略允许等待或业务 Retry | 等待，或新建 Attempt | 无 | 原 Attempt `failed` 或尚未创建 | `no_result` | n/a | `Attempt.runtime_unavailable` |
| 模型瞬时传输失败，未提出 Tool | 无副作用 | 有限机械重试；耗尽后业务 Retry | 机械重试保持；业务 Retry 新建 | 不涉及 | 耗尽后原 Attempt `failed` | `no_result` | n/a | `Attempt.model_retryable_exhausted` |
| 模型永久失败/能力不兼容 | Binding 不能完成任务 | 不静默 fallback；replan 或失败 | 新 Task/Attempt 使用显式新 Binding | 不涉及 | Attempt `failed`；Task 可 `superseded` | `no_result` | n/a | `Attempt.runtime_incompatible` |
| 输出 schema 无效 | Candidate 不可接受 | 记录拒绝；有限 correction Retry | 新 Attempt | 已有 ToolResult 必须 Replay | 原 Attempt `failed` | `no_result` | 保持已有 Tool 值 | `Attempt.invalid_output` |
| Evidence 不足 | 候选结论未被支持 | 创建补充只读 Task | 原 Attempt 可 `succeeded`，新 Task 独立 | 只允许明确的新读取 | 原 Task `result_ready` | `partial_result` | n/a | `Task.insufficient_evidence` |
| Context 不足 | 需要用户或上游信息 | 创建结构化 Interruption | 同 Attempt Resume | 不重复既有 Tool | Attempt `waiting` | `pending` | n/a | `Attempt.insufficient_context` |
| Approval pending | Proposal 有效、Grant 未签发 | 等待正式决定 | 同 Attempt Resume | 禁止执行动作 | Attempt `waiting` | `pending` | `not_executed` | `Attempt.approval_pending` |
| Approval rejected/expired/revoked | 正式决定不可用 | 关闭请求并唤醒 Attempt，Orchestrator replan | Resume 后受控结束或走其他路径 | 禁止原动作 | Proposal 终态；Attempt `running/failed` | `no_result或partial_result` | `not_executed` | `Attempt.approval_*` |
| Tool 在 dispatch 前被 Policy 拒绝 | 没有外部调用 | 不机械重试相同请求；replan | 原 Attempt 可继续其他路径 | 否 | ToolCall `terminal` | `pending` | `not_executed` | `ToolCall.policy_denied` |
| 只读 Tool 明确未 dispatch | dispatch intent 未产生 | 可按 Policy 重新调度 | 同 Attempt 机械重试 | 可以 | ToolCall `scheduled` | `pending` | `not_executed` | none |
| Tool timeout，底层停止可证明 | 外部执行已停止 | 按幂等与策略决定 Retry | 同 Attempt 机械重试或结束 | 只在定义允许时 | ToolCall `terminal` | `pending或no_result` | `not_executed` | `ToolCall.tool_timeout` |
| Tool timeout，底层停止不可证明 | 外部执行事实未知 | 进入 reconciliation；不得推断未执行 | Attempt 可结束，Tool 独立对齐 | 否，直到强证据解除 unknown | ToolCall `reconciling` | `pending` | `outcome_unknown` | `ToolCall.tool_timeout` |
| ToolResult 已持久化，Attempt 推进前崩溃 | Tool 事实已知 | Replay persisted result | 原 Attempt Recovery/Resume | 禁止重复 | ToolCall 保持 `terminal` | `pending` | 保持已持久化值 | 保持已持久化值 |
| 高风险 Grant 未消费 | 动作尚未授权 dispatch | 在有效期内重新调度消费 | 同 Attempt | 仅原 Grant 一次 | Grant `issued`；Action `authorized` | `pending` | `not_executed` | none |
| Grant issued 后 expired/revoked/cancel，尚未消费 | 动作未 dispatch | Action owner CAS 收敛 | 原 Attempt 被唤醒后 replan/结束 | 禁止 | Grant 终态；Action `terminal` | `pending或no_result` | `not_executed` | `Action.grant_unavailable` |
| Grant 已消费，dispatch 是否发生不明 | 结果未知 | reconciliation + 独立 Verify | Recovery | 禁止重复签发/执行 | Action `reconciling` | `pending` | `outcome_unknown` | `Action.dispatch_uncertain` |
| 外部系统确认动作已提交，结果落盘前崩溃 | 副作用已发生 | 保存分类事实并 Verify | Recovery | 禁止 | Action `verifying` | `pending` | `executed_unverified` | none |
| Verify 明确确认后置条件不满足 | 独立观察成功且 postcondition false | 新提案或人工处置 | 不 Retry 原动作 | 禁止自动重复 | Action `terminal` | `no_result或partial_result` | `failed` | `Action.postcondition_failed` |
| Verify 自身失败或证据不足 | 无法形成可信判断 | 保持未验证并人工/有限只读复核；停止自动复核时写 `resolution_disposition=manual_required` | 不 Retry 原动作 | 禁止自动重复 | Action `reconciling/verifying`，或显式人工终止 | `pending` | `outcome_unknown` | `Action.verification_inconclusive` |
| Checkpoint 兼容，业务前置条件仍有效 | 恢复材料可用 | Resume 原 Attempt | 同 Attempt | Replay 持久化 ToolResult | Attempt `running` | 保持原值 | 保持原值 | 保持原值 |
| Checkpoint 不兼容但业务状态可重建 | runtime state 不可用 | 创建 `attempt_kind=recovery` | 新 Attempt | 只重建已证明安全步骤 | 原 Attempt `failed`，新 Attempt `created` | `no_result` | 保持已有 Tool/Action 值 | `Attempt.checkpoint_incompatible` |
| Worker Lease 过期 | 旧 Worker 不再可信 | overlay generation+1 并重派 | 业务状态先不变 | 先对齐 Tool | overlay `lease_expired/reassigning` | `pending` | 保持 | `Attempt.worker_lost` |
| 旧 Worker 迟到返回 | fencing token 失效 | 保存受限诊断摘要，拒绝推进 | 不变 | 不触发新执行 | overlay 记录 stale rejection | 保持 | 保持 | `Dispatch.stale_fencing_token` |
| Outbox 未发布 | State/Event 已提交 | 重发 Outbox | 不变 | 不涉及 | 业务 lifecycle 不变 | 保持 | 保持 | none |
| State/Event/Outbox 不一致 | 持久化不变量破坏 | 独立 AutomationGate 阻断，受控 repair | 不自动 Retry | 禁止 | `AutomationGate=blocked_for_repair` | 保持 | 保持 | `RepairCase.persistence_invariant_violation` |
| Budget soft threshold | 仍有可用额度 | 通知 Orchestrator 收缩计划 | 不变 | 限制新调用 | lifecycle 不变 | `pending` | n/a | `Budget.budget_soft_threshold` |
| Budget hard limit | 普通额度耗尽 | 禁止新普通执行；生成部分结果；对齐已 dispatch Tool | 当前 Attempt 失败或完成受限 Outcome | 否；安全 Verify 例外 | Run/Task 按接受结果归约 | `partial_result或no_result` | 按已发生事实 | `Budget.budget_exceeded` |
| 用户取消，尚无副作用 dispatch | cancel 已持久化 | cooperative cancel，撤销未消费 Grant | Attempt `cancelled` | 禁止新 Tool | Run `cancel_requested→cancelling→cancelled` | `no_result或partial_result` | `not_executed` | `Run.user_cancelled` |
| 用户取消，已有可能副作用 | cancel + unknown/executed fact | 使用逐动作 safety reserve 对齐 | Attempt 可终止，Action 继续对齐 | 禁止重放 | Run 保持 `cancelling`，终止时另存 side-effect resolution | `partial_result` | `outcome_unknown` | `Run.user_cancelled` |
| 服务关闭/进程崩溃 | 非用户意图 | Recovery，不写业务 cancelled | 原 Attempt 或 Recovery Attempt | 按持久化事实决定 | overlay `lease_expired/reassigning` | `pending` | 按已发生事实 | `Attempt.worker_lost或process_crash` |

### 7.3 Timeout、Deadline、Budget 与 Cancellation 传播

| 控制 | Run | Task | Attempt | Tool/Model/Verify |
|---|---|---|---|---|
| 绝对 deadline | `expires_at`，包含等待 | 不得晚于 Run | 不得晚于 Task | 单步 deadline 取上层最早值 |
| 活跃执行预算 | 全局上限 | 原子分配 | 预留/结算 | 按实际 usage/duration 结算 |
| 单步 timeout | 不直接替代 deadline | 可声明最大值 | 传入 RuntimeSpec | 执行边界强制 |
| Cancellation | 持久化 cancel_requested | 停止新 Task/取消可取消 Task | 发 cooperative signal | 高风险结果未知时仍需 Verify |
| Safety verify reserve | Run 创建时独立预留 | 普通 Task 不可用 | 仅 Recovery/Verify 申请 | 只读、硬上限内使用 |

等待用户/审批不计 active execution，但仍消耗绝对 deadline。usage 缺失按保守估算结算，不能按零处理。

BudgetLedger 使用稳定 `reservation_id + dimension + scope_id` 幂等记账。ToolCall 写实际 usage entry；FinalizeAttempt/AcceptTaskResult 只聚合和释放父级 reservation，不重复累计子级 usage。重复相同 receipt 返回既有结算，冲突 usage 进入安全故障。

业务 `expires_at` 到期后禁止新普通执行；已发生或可能发生的副作用进入有独立硬上限的 `safety_reconciliation_deadline`。每个可产生高风险副作用的 dispatch 必须提前获得逐动作 Verify reserve；额度不足时禁止 dispatch，而不是事后依赖共享余额。安全对齐仍无法完成时冻结 `side_effect_resolution=outcome_unknown + resolution_disposition=manual_required` 后终止，不无限越过 deadline。

Cancellation barrier 至少包含：活跃 Attempt、在途 ToolCall、未消费 Grant、未消费 Interruption、`executed_unverified/outcome_unknown` Action 和必须完成的只读 Verify。RunController 只有在 barrier 清空或每项都归约为显式 unknown/manual outcome 后，才能写取消终态。

## 8. 不变量与硬门禁

以下任一失败都不能被语义质量分数抵消：

1. 非权威组件不能写 Run/Task/Attempt 状态；
2. Tool 不能绕过 ToolGateway；
3. Role、Prompt、AgentDefinition 和 Approval 不能推翻 Hard Policy；
4. lifecycle state、Outcome、FailureCode 和 dispatch overlay 不得混入同一状态字段；
5. 每个 current-state 转移必须有唯一 owner、guard、CAS 和 DomainEvent；
6. 未原子持久化 dispatch id、lease/generation/fencing token、intent 和工作 Outbox，不得启动 Worker；
7. 未持久化 Tool dispatch intent 不得调用外部 Connector；
8. 已持久化 ToolResult/AttemptOutcome 不得重复执行；
9. Grant 签发必须幂等绑定当前 Policy/cancel/deadline/action digest；consumed Grant 不得恢复、复用或重复签发；
10. timeout/cancel/disconnect 不得被解释为外部动作未发生；
11. `outcome_unknown` 不得直接 Retry，只有强证据可以归约为 `not_executed`；
12. Checkpoint 不得覆盖业务状态、Policy、ToolResult 或 Evidence；
13. ResultCandidate 未经 Acceptance 不得完成 Task；
14. 高风险动作未 Verify 或 outcome_unknown 时 Run 不得 completed；进入 failed/cancelled 时必须同事务冻结显式 side-effect resolution，安全投影不得显示普通终态；
15. State、DomainEvent、sequence、Outbox 必须事务一致；
16. Raw payload 未完成分类、secret detection 和 redaction 前不得持久化；
17. Safe Trace、durable SSE、API、审计和导出只能来自 typed deterministic projection；
18. BindingSnapshot 才能证明 selected/bound，执行记录才能证明 executed；
19. Verifier Task 不得递归要求同级 Semantic Verifier；
20. 旧 Worker 的失效 fencing token 不得推进任何权威状态；
21. 身份/审批人模型获批前不得泛化 ExecutionGrant；
22. 新副作用路径在 reconciliation、unknown outcome、kill switch 和回退门禁通过前不得生产激活。

## 9. Review 入口问题

Reader Review 应至少能仅凭本文回答：

1. 当前是否可以创建 Workpack，A–E 为什么不是获批阶段？
2. Retry、Resume、Replay、Recovery、Verify 分别改变哪个对象，是否重新执行模型或 Tool？
3. RunController 与 Scheduler 如何通过 dispatch/lease/fencing 事务交接 Attempt，旧 Worker 为什么不能推进状态？
4. 不需要审批的只读 Tool 和需要正式审批的高风险 Tool 分别走哪条合法状态路径？
5. Proposal approved 后、Grant 签发前崩溃，或 Grant consumed 后结果不明时分别如何恢复？
6. `partial_result`、`invalid_output`、`outcome_unknown`、`recovery attempt` 分别属于哪个正交维度？
7. Tool/Action 的 unknown outcome 如何收敛，为什么普通 `failed/cancelled` 不能吞掉未知副作用？
8. A–E 如何满足定义依赖与行为激活前置，D 的契约为什么不等于副作用已经启用？
9. Raw Result、Safe Trace、durable SSE 和 ephemeral progress 分别允许保存或展示什么？
10. Identity、Raw Blob、迁移/API、durable worker 和新副作用路径分别需要什么独立 Design 门与完成证明？

如果读者不能稳定回答，优先修改本文，不进入实施规划。

## 10. 当前结论

Capability、状态、事件和失败语义已按 Reader Review 完成修订并通过无历史上下文复测：

- Capability Matrix 给出依赖顺序，不承诺一次完成；
- 状态机为每个对象指定唯一权威写入者；
- Event 字典只记录已发生的业务事实，并将 Safe Trace/SSE 视为投影；
- Failure 表先保护外部事实，再决定 Replay、Resume、Retry、Recovery 或 Verify；
- Recovery 被明确放在稳定身份、持久化和 Tool 副作用语义之后；
- 所有权限、迁移、公开 API 和 durable execution 变化继续受独立 Design 门约束。

Reader Review 已通过：上述十个问题 10/10，产品安全与运行时闭环复核均无 Blocking/Major。最终 Adopt/Adapt/Reject 与建议分期已经形成并获用户确认，P9 研究与后续开发规划阶段已收口；该确认不授权实施。
