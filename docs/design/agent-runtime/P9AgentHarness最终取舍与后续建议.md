# P9 Agent Harness 最终取舍与后续建议

> 状态：已由用户确认，P9 研究与后续开发规划阶段已收口，未授权实施
> 更新：2026-09-01
> 主 Design：[P9AgentHarness正式化Design.md](P9AgentHarness正式化Design.md)
> 综合矩阵：[P9AgentHarness综合设计矩阵.md](P9AgentHarness综合设计矩阵.md)
> Reader Review：[P9AgentHarnessReaderReview.md](P9AgentHarnessReaderReview.md)

## 1. 本文回答什么

本文是 P9 研究与后续开发规划阶段的最终决策入口，回答：

1. 从七个开源项目和当前 OperMind 代码中，哪些模式 **Adopt**；
2. 哪些模式只能经过 OperMind 边界改造后 **Adapt**；
3. 哪些路线明确 **Reject**；
4. 后续如果进入实现，应按什么依赖顺序建设、何时才允许生产激活；
5. P9 研究何时可以收口。

这里的 Adopt 表示“成为目标 Harness 的规范原则”，不表示当前代码已经实现；Adapt 不表示引入对应框架；Reject 只表示不适合 OperMind 的产品、安全或工程边界，不评价开源项目本身。

## 2. 最终总决策

OperMind 不整体迁移到任何一个 Agent 框架。最终选择固定为：

```text
OperMind 自有业务控制面
  ├── Run / AgentTask / Attempt / ToolCall 领域身份
  ├── Policy / Approval / Budget / Event / Recovery 服务器边界
  └── 可替换 AgentRuntimeAdapter
        └── LangGraphAdapter 作为首个现有 Runtime 适配器
```

- OpenAI Agents SDK、PydanticAI、LangGraph、Deep Agents、Microsoft Agent Framework、DBOS 和 CrewAI 都是模式与证据来源，不成为第二套业务真相；
- LangGraph 保留为首个 Runtime Adapter，不再承担 OperMind 控制面或领域状态；
- 不在 P9 引入 DBOS、CrewAI 或另一套 durable/runtime engine；
- 当前 Run/CAS/SSE/ToolGateway/固定动作链路是渐进包裹和替换的资产，不做大爆炸重写；
- Framework-learn 保存研究来源、比较和被拒绝方案；本目录 Design 才是 OperMind 的规范性结论。

## 3. Adopt：直接成为 OperMind 规范原则

| # | Adopt 决策 | 主要来源 | 对 OperMind 的规范含义 |
|---|---|---|---|
| A1 | OperMind 拥有业务状态 | LangGraph、DBOS、Microsoft Agent Framework 对照 | Runtime thread/state/checkpoint 不能成为 Run/Task/Attempt 事实源 |
| A2 | 固定 `Run → AgentTask → Attempt → ToolCall` 层级 | CrewAI、OpenAI Agents SDK | 用户调查、语义任务、一次执行和工具调用拥有不同身份与生命周期 |
| A3 | 关键边界全部 typed、versioned、validated | PydanticAI、Microsoft Agent Framework | Task、Attempt、Context、Binding、Decision、Signal、Result 和 Failure 禁止隐式字典协议 |
| A4 | Agent 提议，服务器裁决 | 多项目综合 | Agent/Runtime 只能提出 Task、Tool、Context 和 Result；Orchestrator/领域 owner 校验并写入 |
| A5 | ToolGateway 是唯一工具执行入口 | 当前 OperMind、OpenAI/PydanticAI 工具边界 | Connector 不暴露给模型，所有调用经过 schema、Policy、Budget、Approval、Audit 和脱敏 |
| A6 | 高风险动作使用 Proposal → Decision → Grant → Action → Verify | PydanticAI deferred、Microsoft HITL、当前固定动作 | 聊天文本不批准；Grant 精确、短期、单次；Verify 是独立只读观察 |
| A7 | Current State + immutable record + DomainEvent + Outbox | DBOS、LangGraph persistence 对照 | 不采用纯 Event Sourcing；状态、事件和发布意图事务一致，Checkpoint 只负责技术恢复 |
| A8 | Recovery 是事实对齐 | DBOS、LangGraph checkpoint/replay | 已持久化结果 Replay；unknown side effect reconciliation/Verify；不能把 Recovery 当重跑 |
| A9 | Lease、generation 和 fencing 保护跨进程执行 | DBOS durable 语义 | Scheduler 不拥有 Attempt lifecycle；旧 Worker 不能推进任何权威状态 |
| A10 | Budget、deadline、timeout、cancel 正交传播 | PydanticAI usage、各框架 cancellation | 预算预留/结算、绝对期限、单步 timeout、取消 barrier 和 safety reserve 分开 |
| A11 | Safe Trace 是 typed deterministic projection | 当前产品事实、各框架 observability 对照 | UI/SSE 不展示 CoT、Prompt、原始 Tool 输出、异常、SQL、凭据或未分类文本 |
| A12 | Contract/Security/Recovery 是硬门禁 | 七项目测试证据与当前 mock 基线 | 固定场景和 oracle 内 100% 通过、无 skip/xpass；LLM Judge 不能证明权限或事实 |
| A13 | ContextManifest 不可变且不自动检索长期记忆 | OpenAI/PydanticAI context、Deep Agents 压缩对照 | 近期上下文 + 更早压缩 + 用户明确引用 Run；Resume 追加响应，Retry 新 Manifest |
| A14 | 配置真实性由 Binding/Execution 证明 | 各框架 provider/runtime 装配对照 | registered/configured 不等于 selected/executed；切换关键 Binding 创建新 Attempt |

## 4. Adapt：吸收模式，但按 OperMind 改造

| 来源/现有资产 | 吸收内容 | OperMind 改造方式 | 明确不继承 |
|---|---|---|---|
| OpenAI Agents SDK | Runner 生命周期、stream 与最终结果一致性 | 映射为 AttemptRunner；SDK Run 不是业务 Run；handoff 转 AgentTaskProposal | SDK/Provider 类型成为领域模型或状态权威 |
| PydanticAI | typed deps/output、usage limit、deferred request | deferred 只表达结构化 Interruption；正式审批和 Grant 仍由服务器生成 | 框架 approval 直接授权外部执行 |
| LangGraph | 图调度、并行汇合、interrupt、checkpoint、reducer | 通过 LangGraphAdapter 转为 RuntimeSignal；Checkpoint 低于业务状态和 ToolResult | LangGraph thread=Run、graph state=业务真相、控制面锁定 |
| Deep Agents | Middleware 组合、Context 治理、subagent 接缝 | 固定多条 Pipeline；subagent 转 Proposal；backend 收敛为显式 Port | 通用 filesystem/shell/network、共享可变 Agent、压缩=长期记忆 |
| Microsoft Agent Framework | Agent/Tool middleware 分离、HITL、workflow event、checkpoint 版本 | 只吸收控制协议和兼容性思想；telemetry 先做安全投影 | 整体 hosting/Provider/企业集成体系和事件混用 |
| DBOS | workflow identity、幂等、队列、crash window、恢复 | 用 UoW/Outbox、ExecutionCoordinator、RecoverySupervisor、Lease/Fencing/Reconciliation 表达 | P9 直接引入 DBOS、第二套业务真相、通过重放未知副作用 |
| CrewAI | AgentTask、goal、expected output、guardrail、确定性 Flow 区分 | AgentTask 成为领域类型；Role 只描述职责，权限来自 Policy/Grant | 自然语言角色授权、自动框架 memory、迁移 Runtime 内核 |
| 当前 Run/CAS/SSE | 现有正式链路和安全事件投影 | 先包裹、shadow、dual-read/对账，再逐项切权威写入 | 删除重建、一次性切换或把 queued 继续当完整业务状态 |
| 当前 ToolGateway/固定动作 | 唯一工具入口、现有审批与 Verify 资产 | 保持现有生产路径；新 Grant/dispatch 语义先 shadow，最小 Recovery 门后再迁移 | 以“动作已存在”为理由绕过新 crash-window 门禁 |

## 5. Reject：明确不走的路线

| Reject | 原因 |
|---|---|
| 选择一个开源框架整体替换 Harness | 无一项目同时满足 OperMind 的业务状态、安全治理、事实诚实性和渐进迁移要求 |
| 同时维护两套 Run/Event/Approval 业务真相 | 会产生状态竞争、恢复歧义和无法审计的分叉 |
| 把 Runtime thread、graph state、checkpoint 当领域事实 | 技术状态不能证明业务完成、权限、Tool 副作用或 Evidence |
| 纯 Event Sourcing 或把 projection 当权威 | 当前查询、外部副作用和修复复杂度不适合只靠事件重建 |
| 任意 SQL、Shell、filesystem、网络或通用执行器 | 违反默认只读、显式 Connector、白名单和服务隔离边界 |
| Prompt、Role、Capability 声明或聊天文字授予权限 | 语义描述不是服务器授权，也不能推翻 Hard Policy |
| 自动批准、重复签发 Grant 或 unknown outcome 自动 Retry | 可能重复产生外部副作用，破坏审计与事实真实性 |
| 宣称外部动作 exactly-once | 数据库事务不能覆盖外部系统；只能使用 intent、幂等、reconciliation 和 Verify |
| 自动长期记忆或直接启用框架 memory | 当前未决，可能造成跨 Run 泄漏、错误召回和不可解释上下文 |
| 展示 CoT、Prompt、原始工具/异常/SQL/凭据 | 违反产品安全边界；Trace 只能是 typed 安全投影 |
| 跨 Attempt 共享可变 Agent 实例 | 容易造成状态串线、并发污染和无法重放的隐藏输入 |
| 一次性大迁移或先接 Recovery 再稳定领域协议 | 会把不稳定身份、事件和副作用语义永久化 |
| 在最小 Recovery/reconciliation 前迁移任何副作用 Grant/dispatch 语义 | 包括现有固定动作也会引入无法安全处理的 crash window |

## 6. 建议后续分期

以下 A–E 整体仍只是依赖建议，不是路线图承诺、阶段编号或 Workpack。首个零行为变化候选包已在本文件确认后的独立决策中立项为 P10；该决定只覆盖三个紧密切片，不扩展到 A 的其余内容或 B–E。每次实际工作仍须完成所需 Design → Review → 用户确认。

| 序位 | 目标 | 建议内容 | 允许的激活 | 退出条件 |
|---|---|---|---|---|
| A：语义内核与现状保护 | 先建立共同语言和回归护栏 | 七维状态命名空间、Runtime Adapter port、Registry/ToolDefinition metadata、UoW/Event/Policy port、Pipeline/Eval skeleton | 仅 adapter 包裹、contract test、shadow；生产行为不变 | 现有 Run/Tool/Trace/固定动作回归全过；无 API/迁移/权限变化 |
| B：业务执行脊柱 | 建立 Task/Attempt/Context/Binding/Acceptance 身份 | typed contract、OrchestrationDecision、ResultCandidate/Acceptance、shadow record | 只允许影子记录和离线对账；不接管生产状态 | Retry/Resume、Task acceptance、Binding/Context truth contract suite 通过 |
| C：可靠控制面 | 固定事实提交、调度和取消语义 | Current State、DomainEvent、Outbox、Budget ledger、cancellation barrier、ExecutionCoordinator overlay | 迁移/API 另审；dual-read/shadow 对账后才逐项切 writer | transaction/reducer/outbox/fencing/cancel race 测试通过，可回退 |
| D：工具与安全治理 | 闭合 Tool/Policy/Approval/Grant/Evidence/Trace 契约 | effect metadata、PolicyBundle、Grant+authorized Action 同事务、typed safe projection | 只读路径按门禁启用；副作用新语义只定义、测试、shadow | substitution/deny/secret leak/unknown outcome/Verify 测试通过；身份门明确 |
| E：恢复与受控激活 | 对齐跨进程事实并逐能力开启新路径 | RecoverySupervisor、RepairCoordinator、fault injection、backfill/repair、kill switch | 只对 crash window、回退和安全门通过的能力逐项激活 | 固定 fault matrix 100% 通过；现有固定动作迁移也需单独确认 |

### 6.1 已选择的第一个实现阶段：P10

用户已于 2026-09-01 从 A 中选择以下不改变产品行为的候选包，并独立立项为 P10：

```text
Harness Contract Kernel + Regression Baseline
```

建议只包含：

1. 通用 Harness identity/version/fencing value object 与七维状态命名空间；Task/Attempt 的业务 identity 和 contract 留在 B；
2. 围绕当前 DiagnosisExecutor/ToolGateway 的 Adapter contract test harness；
3. 当前权限、Trace、取消和固定动作链的确定性回归场景。

P10 不新增数据库迁移、公开 API、Connector、真实连接、审批能力或 durable worker；若实际切片触及这些边界，必须拆出独立 Design。P9 本身没有创建 Workpack；P10 立项与 Workpack 计划现已分别确认，仍须在立项文档合入 `main`、建立干净实施 base 且开始门禁通过后才进入代码实施。

## 7. 独立 Design 与激活门

| 变化 | 必须先完成 |
|---|---|
| P9 产出的首个后续候选独立立项 | 已完成：确定为 P10；只包含已确认 PRD 的三个切片，不包含完整 A–E；Workpack 计划已确认 |
| 新表、列、状态或公开 API | 数据模型/API Design、迁移 upgrade/downgrade、前后端契约确认 |
| 身份、RBAC、审批人 | 独立产品与安全 Design；完成前不泛化 ExecutionGrant |
| 持久化 Raw Blob | 数据安全 Design：分类、加密、访问控制、隔离、TTL/删除、审计、泄漏处置 |
| Durable worker / queue / checkpoint | 部署、兼容、Lease/Fencing、repair/backfill、回退 Design |
| 新/变更副作用 Grant/dispatch | principal、精确 Grant、逐动作 Verify reserve、reconciliation、unknown/manual、kill switch、Recovery 全部通过 |
| 新 Connector、服务类型或真实资源测试 | 目标范围、权限、脱敏、mock、错误映射和用户明确授权 |
| 长期记忆、RAG、向量或 MCP | 独立产品边界和检索/隔离 Design |

## 8. P9 收口判断

P9 已完成：

- 七个开源项目定向学习与固定证据；
- 当前代码 Baseline Gap Map；
- 十七组 Harness 契约与跨契约一致性检查；
- Capability、状态、事件、失败和安全门禁综合矩阵；
- 独立 Reader Review、三轮定向修订与无历史上下文复测；
- 最终 Adopt / Adapt / Reject 与建议分期。

用户已确认本文，P9 研究与后续开发规划阶段据此收口。此后又经独立决策，将首个零行为变化候选包立项为 P10；该决定不表示 P9 进入开发，也不批准完整 A–E。当前边界是：

- 正式路线只把已确认 PRD 的三个切片立项为 P10，不承诺完整 A–E；
- P10 Workpack 计划已经创建并由用户确认；
- 立项与计划文档合入 `main`、建立干净实施 base 且开始门禁通过前不修改 Runtime、数据库、API 或生产行为；
- A 的其余内容与 B–E 仍只能作为未来决策输入。

issue、PRD、实施 Design 与 Workpack 计划均已完成确认，阶段归属已确定为 P10；当前下一工程门是立项与计划文档合入 `main`，随后建立干净实施 base。未来是否继续 A 的其余内容或 B–E 仍须逐项另行决定，不能由本文或 P10 自动触发。
