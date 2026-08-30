# P9 Agent Harness 正式化 · Design

> 状态：P9 研究阶段已由用户确认收口，未授权实施
> 更新：2026-08-30
> 阶段说明：P9 研究已收口；首个零行为变化候选包已单独写入 `docs/路线图.md`，建议分期 B–E 未获路线承诺。
> 研究材料：`D:\market-handsome\Framework-learn\学习指南\P9-Agent-Harness-学习路线\学习记录\`
> 权威边界：本 Design 不自行改写 `docs/产品定义.md`、`docs/路线图.md` 或 `docs/开发规范.md`；正式路线只登记已确认 PRD 的首个候选包。
> 最终取舍：[P9AgentHarness最终取舍与后续建议.md](P9AgentHarness最终取舍与后续建议.md)

## 1. 背景与目标

OperMind 已经具备 Agent、ToolGateway、LangGraph、Run、事件、SSE、持久化和取消接口，但这些能力尚未形成统一、可测试、可恢复、可治理的 Harness 契约。

P9 的目标不是选一个开源框架整体替换 OperMind，而是参考 OpenAI Agents SDK、PydanticAI、LangGraph、Deep Agents、Microsoft Agent Framework、DBOS 和 CrewAI，明确 OperMind 自己的：

- 状态所有权；
- Run / AgentTask / Attempt / ToolCall 层级；
- Orchestration 与 Runtime 边界；
- Context、Budget、Approval、Event 和 Recovery 语义；
- 后续实现阶段的拆分依据。

## 2. P9 范围

### 本阶段做什么

- 固定源码基线并完成跨框架综合；
- 建立目标 Harness 架构；
- 定义 typed contract、状态机和失败语义；
- 形成 capability matrix、事件字典、故障矩阵和测试策略；
- 明确 Adopt / Adapt / Reject；
- 给后续实现阶段提出可独立验证、可回退的分期建议。

### 本阶段明确不做

- 不重写现有 Runtime；
- 不替换或升级 LangGraph 主线；
- 不引入 DBOS、CrewAI 或另一套 durable engine；
- 不新增数据库迁移、公开 API、Connector 或真实外部连接；
- 不新增 Shell、filesystem、任意 SQL、任意网络能力；
- 不启用自动长期记忆检索；
- 不实现新的高风险动作执行能力；
- 不创建 Workpack 或进入代码实施。

## 3. 总体架构决策

采用“OperMind 控制面中心 + 可替换 Runtime Adapter”：

```text
API / Application
  └── RunApplicationService
        └── HarnessFacade
              ├── Control Plane
              │     ├── RunController / Orchestrator
              │     ├── AgentTaskScheduler / ExecutionCoordinator
              │     └── RecoverySupervisor / RepairCoordinator
              ├── Contract Services
              │     ├── AgentRegistry / ExecutionConfigResolver
              │     ├── ContextAssembler / PolicyEngine / BudgetManager
              │     ├── ApprovalCoordinator / ActionExecutionService
              │     ├── ResultAcceptanceService
              │     └── EventRecorder
              ├── Execution Plane
              │     └── AttemptRunner / PipelineExecutor
              │           ├── AgentRuntimeAdapter → LangGraphAdapter
              │           └── ToolGateway → Connector
              └── Persistence Ports
                    ├── HarnessUnitOfWork / Outbox
                    ├── EvidenceStore / BlobStore
                    └── CheckpointPort
```

### D1：RunController 是业务状态权威

RunController 是唯一能够推进 Run、AgentTask 和 Attempt lifecycle state 的组件。Orchestrator 只输出结构化语义决策；AgentTaskScheduler 只提出 readiness/调度命令，ExecutionCoordinator 是 dispatch/lease/fencing overlay 的唯一 writer；AttemptRunner 只执行一次 Attempt 并携带有效 fencing token 报告结果。ActionExecutionService 是 ActionExecution 的唯一 writer；RepairCoordinator 是 AutomationGate/RepairCase 的唯一 writer。

这里的权威范围是 Run、Plan、Task 和 Attempt；ToolCall、Approval、Budget 和 Evidence 由专用服务拥有，并通过 HarnessUnitOfWork 保证关键事务一致，避免 RunController 退化成 God Object。

### D2：LangGraph 降为 Runtime Adapter

LangGraph 负责一个 Attempt 内部的模型循环、图执行、stream、interrupt 和 checkpoint。LangGraph thread、state、event 和 checkpoint 都不能成为 OperMind 领域模型或业务事实源。

### D3：业务层级固定

```text
Run
  └── AgentTask
        └── Attempt
              └── ToolCall
```

- Run：一次完整、用户可见的调查；
- AgentTask：具有目标、范围、输出契约、依赖和权限边界的语义任务；
- Attempt：Task 的一次具体执行；
- ToolCall：Attempt 中由 Agent 提出、服务器受控执行的工具调用。

Retry 创建新 Attempt；Approval、用户输入或补充上下文后的 Resume 保持原 Attempt。Task 契约变化时 supersede 原 Task。

Attempt 使用 Prepare/Create 两阶段：先解析 Binding、校验 Policy、组装 ContextManifest、计算 Budget/Deadline，再在单事务中保存 AttemptSpec、Binding/Context/Pipeline Snapshot、预算预留、Domain Event 和 Outbox。之后由 Scheduler 通过独立的 `AcquireAttemptLeaseAndDispatch` 事务原子保存 dispatch id、lease、generation、fencing token、dispatch intent、Domain Event 和工作命令 Outbox；提交前不得启动 Worker。

### D4：Orchestrator 做语义决策，Agent 只能提议

Agent 可以提出子任务、补充上下文、工具调用和完成候选。Orchestrator 接受、拒绝、去重或调整语义提议；RunController 校验并持久化。Agent 或 Runtime 不能直接修改 Task 图和 Run 终态。

### D5：ContextManifest 不可变

完整 SessionHistory 持久化；模型上下文采用：

```text
近期原始对话
+ 更早历史的结构化压缩
+ 用户明确引用的历史 Run
```

不自动检索无关长期记忆。每个 Attempt 使用不可变 ContextManifest；Resume 追加结构化响应，Retry 创建新 Manifest。

### D6：ToolGateway 是唯一工具执行入口

Tool 是 Agent 可见的版本化协议，Connector 是确定性实现。实际权限来自 Server Policy、Run、Task、Role、Service 和 Approval 的交集。Runtime 注册的框架 Tool 只能代理到 ToolGateway。

### D7：高风险动作使用正式 Approval 与独立 Verify

```text
Agent 提议
→ Server ApprovalProposal
→ Policy 校验
→ 人工正式决定
→ 一次性 ExecutionGrant
→ ToolGateway 执行
→ 独立 Verify
```

聊天文本不能直接批准。取消或超时后，已经可能产生副作用的动作仍需完成必要的只读 Verify。

Proposal approved 不直接等于可以执行。`IssueExecutionGrant` 必须幂等检查当前 Proposal/Decision version、Hard Policy、revocation generation、Run/Task/Attempt 状态、cancel/deadline、action digest、目标、审批 principal 权限和 Grant 唯一性。身份/审批人模型完成独立 Design → Review → 用户确认前，不得泛化 ExecutionGrant。D 阶段只定义或 shadow 新 Grant/dispatch 语义；当前固定动作继续走现有已确认路径，连现有动作迁移也必须等待最小 reconciliation/recovery 与 kill switch 门。

### D8：当前状态与 append-only Event 并存

不采用纯 Event Sourcing。当前状态、Domain Event 和 SSE outbox 在同一事务提交，并通过 reducer verification 检查一致性。

Domain Event、Runtime Event、Audit Event、Safe Trace 和 SSE Transport 必须分层。Trace 不展示 CoT、Prompt、原始 Tool 输出、原始异常、原始 SQL、敏感参数或凭据。Durable SSE 只发布持久化 Safe Projection；采样 Runtime progress 若启用，只能进入明确不可补播的 ephemeral 通道。

### D9：Recovery 是事实对齐，不是重跑

RecoverySupervisor 使用 Lease、单调 generation、Fencing Token、Checkpoint 和持久化结果对齐非终态执行。已持久化结果必须复用；外部动作结果未知时禁止自动 Retry，必须进入 reconciliation，并归约为强证据证明的 not-executed、executed-unverified、明确结果或 manual-required。旧 Worker 的失效 token 不能推进任何权威状态。

### D10：Budget、Deadline 和 Cancellation 分层传播

Run、Task、Attempt 和 ToolCall 使用分层预算。并发执行前原子预留，结束后按实际用量结算。绝对截止时间、活跃执行预算和单步 timeout 分开表达。

服务关闭、进程崩溃或 Worker 丢失进入 Recovery，不伪装成业务取消。Cancellation 是持久化状态，不能只依赖进程内取消信号。

Run 收到取消后先原子持久化 `cancel_requested`，建立 cancellation barrier 后进入 `cancelling`。Run lifecycle 终态仍是 `cancelled/failed`，但必须同时冻结独立 `side_effect_resolution`；无法确认时保持 `side_effect_resolution=outcome_unknown`，并另写 `resolution_disposition=manual_required`。Safe Projection/API 必须显示 `cancelled_with_unknown_outcome/failed_with_unknown_outcome` 复合标签，普通终态展示不能吞掉未知副作用。

### D11：Agent、Role、Capability 与 Policy 分离

AgentDefinition 是版本化蓝图，Role 只描述职责，Capability 声明不等于授权。Policy Engine 采用 Deny Overrides 和最小范围 Grant；高风险 Execute 只通过一次性 ExecutionGrant 授予 ToolGateway，模型 Agent 只能提出动作。

### D12：实际配置由 BindingSnapshot 证明

Agent、Model、Runtime、Instruction、Context、Tool、Pipeline 和 AcceptanceProfile 在 Attempt 级冻结。配置状态区分 registered、configured、validated、available/eligible、selected/bound 和 executed；切换 Model/Runtime/Instruction 创建新 Attempt，不能静默 fallback。

### D13：结果分层验证后接受

Agent 只产生 ResultCandidate。Contract、Evidence、Safety、Semantic 和 Action Verification 分层执行；Orchestrator 提出语义接受，RunController 完成 Task。Verifier Task 不得递归要求同等级 Semantic Verifier。

### D14：持久化采用混合真相模型

Current State 负责当前查询，不可变记录保存已经分类的安全事实，Domain Event 保存业务历史，Outbox 负责可靠发布，Checkpoint 只负责 Runtime 恢复。State、Domain Event、Run sequence 和 Outbox 必须同事务。RawExecutionResult 在任何持久化前必须完成 schema 过滤、classification、secret detection 和 redaction；任意原始 Blob 持久化另走数据安全 Design。

### D15：固定 Pipeline 顺序

Command、Runtime、ModelCall、ToolCall 和 ResultAcceptance 使用不同 Pipeline。Identity/version/fencing 在业务执行前，Policy 在 Approval 前，dispatch intent 与 Grant 消费在外部调用前；Tool 结果先完成分类和 secret/redaction 门禁，再保存安全结构或受控引用并生成 Evidence 与安全投影。

### D16：可靠性使用硬门禁验证

Contract、Security 和 Recovery 不变量必须在固定版本、固定场景全集和明确 oracle 的分母内 100% 通过，且不得以 skip/xpass 缩小分母；不能被语义质量平均分覆盖。LLM Judge 只能辅助评估输出质量，不能证明权限、Evidence、状态或外部动作事实。

### D17：跨契约一致性收口

Resume 保持原 ContextManifest，通过 append-only ResumeExecutionInput 追加响应；普通 Policy 固定到 Binding，Hard Policy 与紧急撤销在敏感执行前重校验；普通调查不能消耗 safety verify reserve；目标事务模型不允许把 State/Event/Outbox 不一致当成正常中间态。Lifecycle state、Outcome、FailureCode 与 dispatch overlay 正交；每个 current-state 转移具有唯一 owner、guard、CAS 和 DomainEvent。是否允许继续执行由当前 Policy/状态决定，外部是否已经发生由 ToolResult/Evidence/Verify 决定，二者不能互相抹除。

## 4. 已形成的契约草案

当前已逐项讨论：

1. `AgentTask Contract v0.1`；
2. `Attempt Contract v0.1`；
3. `ToolCall / ToolResult Contract v0.1`；
4. `ContextAssembler Contract v0.1`；
5. `RunEvent / Trace / Audit / Checkpoint Contract v0.1`；
6. `Orchestrator Decision Protocol v0.1`；
7. `Approval / HITL Protocol v0.1`；
8. `Recovery Supervisor Contract v0.1`；
9. `Budget / Deadline / Cancellation Contract v0.1`；
10. `Agent Runtime Adapter Contract v0.1`；
11. `Agent Definition / Role / Capability Registry Contract v0.1`；
12. `Policy Engine / Capability Grant Contract v0.1`；
13. `Verifier / Result Acceptance Contract v0.1`；
14. `Agent Configuration / Model Routing Contract v0.1`；
15. `Persistence Model Contract v0.1`；
16. `Harness Middleware Ordering Contract v0.1`；
17. `Evaluation Contract / Fault Injection Matrix v0.1`。

这些契约的完整研究草案和第一轮跨契约一致性检查保存在 Framework-learn，不在本 Design 重复展开。Capability、状态、事件和失败语义的统一收口见 [P9AgentHarness综合设计矩阵.md](P9AgentHarness综合设计矩阵.md)。Framework-learn 继续保存来源、比较过程和备选方案，不是 OperMind 的规范事实源；P9 收口所需的规范结论必须回写本目录的版本化 Design。它们尚未转换为数据库 schema、API schema 或 Python 类型，也未授权实施。

## 5. 关键不变量

1. RunController 是 Run、Task、Attempt lifecycle state 的唯一权威写入者；Scheduler 只拥有 dispatch overlay。
2. Runtime 成功只产生 ResultCandidate，不等于 Task 完成。
3. Agent 的自然语言角色、Prompt 或 handoff 都不构成权限。
4. 所有 ToolCall 必须通过 ToolGateway。
5. Retry、Resume、Replay 和 Recovery 具有不同语义。
6. 已持久化 ToolResult 和 AttemptOutcome 不得重复执行。
7. Timeout、Cancel、断连和 Worker 失联都不能证明外部动作未发生。
8. 未知副作用只能对齐、Verify 或人工处理，不能直接 Retry；只有强证据可以归约为未执行。
9. Checkpoint 是技术状态，不是业务真相。
10. Trace 只是 typed deterministic 安全投影，不能反向驱动业务状态。
11. Role、Prompt、AgentDefinition 和 Approval 都不能推翻 Hard Policy。
12. BindingSnapshot 证明本次实际配置，配置存在不等于已执行。
13. Run 在高风险 Verify 完成前保持 cancelling；无法确认时 lifecycle 与独立 side-effect resolution 一起终止，安全投影必须显式显示 unknown，不能伪装成普通 failed/cancelled。
14. State、Domain Event 和 Outbox 不一致属于故障，不是正常态。
15. 安全、权限、持久化和恢复硬门禁不能被质量评分覆盖。
16. Run 存在 `executed_unverified/outcome_unknown` 高风险动作时不能普通终止；确实无法继续自动对齐时，必须冻结 `side_effect_resolution=outcome_unknown` 与独立 `resolution_disposition=manual_required`，并生成显式复合安全投影。
17. ApprovalProposal 与 ActionExecution 使用独立状态机。
18. Worker 未持有有效 generation/fencing token 时不能推进任何权威状态。
19. Grant 签发/消费必须与 action digest、当前 Policy、cancel/deadline 和唯一身份原子绑定。
20. Raw payload 未经分类、secret detection 和 redaction 不得持久化。
21. 身份/审批人模型获批前不得泛化 ExecutionGrant。
22. 任何新增或改变副作用 Grant/dispatch 语义的路径，包括迁移现有固定动作，在最小 reconciliation/recovery、unknown outcome、kill switch 和回退门禁通过前不得生产激活。

## 6. 当前代码基线与尚未完成的设计

十七组核心契约、第一轮跨契约一致性检查、七项目源码/测试证据矩阵、当前代码 Baseline Gap Map、capability/state/event/failure 综合设计矩阵，以及最终 Adopt/Adapt/Reject 与建议分期已经完成。

当前实现是 Run 中心的一次性后台执行链：已有 Run CAS、持久化安全事件、SSE 重放、每 Run Agent 隔离、ToolGateway、保守 ResultAssembler 和固定动作审批/Verify；尚无 AgentTask、Attempt、Context/Binding Snapshot、durable recovery、分层 Budget/Cancel、统一 Policy/Grant 或 Harness Middleware。LangGraph 当前没有 checkpointer，因此没有与数据库 Run 双写同一状态，但 Run/Event/Action/Tool/Config 存在多处概念折叠。

综合矩阵已经按独立 Reader Review 修订 Retry/Resume/Replay/Recovery/Verify、业务状态与 dispatch overlay、Domain/Runtime/Audit/Trace/SSE/Checkpoint，以及 ApprovalProposal/ExecutionGrant/ActionExecution 的边界，详见 [P9AgentHarnessReaderReview.md](P9AgentHarnessReaderReview.md)。无历史上下文复测已通过：十个 Reader Questions 10/10，产品安全与运行时闭环均无 Blocking/Major。

## 7. 后续分期原则

P9 完成后再决定具体实现阶段。后续工作包必须满足：

- 每包只收敛 1–3 个紧密契约；
- 先建立类型和契约测试，再替换调用路径；
- Runtime Adapter 与业务状态变更分开；
- 数据迁移、公开 API、Connector、审批执行能力分别走独立 Design 门；
- 每阶段可回退，不进行一次性框架替换。
- 契约建设与生产行为激活分开；任何改变副作用 Grant/dispatch 语义的切换不得早于最小 Recovery/reconciliation 和 kill switch。

## 8. Review 与确认状态

本文件目前只完成研究成果的阶段性保存：

- 架构方向已经过逐项讨论；
- 十七组核心契约已完成第一轮一致性检查；
- 七个参考项目的固定 commit、关键源码和聚焦测试已经形成证据矩阵；
- 当前正式代码主线与十七组目标契约的 Baseline Gap Map 已完成；
- capability matrix、状态所有权与状态机、Event 字典和 failure 决策表已完成统一；
- 独立 Reader Review 的 Blocking/Major 发现已完成修订；
- 无历史上下文复测已通过，Reader Review 阶段收口；
- 最终 Adopt/Adapt/Reject 与建议分期已获用户确认，P9 研究阶段收口；
- 本次确认不等于“可以实施”，也不把 P9 或 A–E 自动写入正式路线图；
- 不得据此创建 Workpack 或修改运行时。
