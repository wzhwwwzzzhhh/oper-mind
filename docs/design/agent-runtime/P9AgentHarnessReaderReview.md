# P9 Agent Harness · Reader Review

> 状态：Reader Review 与无历史上下文复测已通过，未授权实施
> 更新：2026-08-30
> 审阅对象：[P9AgentHarness正式化Design.md](P9AgentHarness正式化Design.md)、[P9AgentHarness综合设计矩阵.md](P9AgentHarness综合设计矩阵.md)
> 事实边界：`docs/产品定义.md`、`docs/路线图.md`、`docs/开发规范.md`

## 1. 审阅方法

本轮把作者讨论上下文从审阅输入中移除，由三组独立读者分别检查：

1. 新实施者能否仅凭文档准确回答关键问题；
2. 状态所有权、事务、事件、恢复和副作用语义是否闭合；
3. 产品事实、安全边界和 Design 门是否被保持。

主审随后对三组发现去重并重新定级。定级只回答“P9 研究结论能否收口”，不把未来数据库 schema、API 或代码级字段细节错误地要求在本阶段全部完成。

| 级别 | 本轮含义 |
|---|---|
| Blocking | P9 用户确认前必须修正，否则核心结论内部矛盾或存在安全语义空洞 |
| Major | 必须在主 Design 中形成明确原则、门禁或后续 Design 输入，但不要求 P9 直接实现 |
| Minor | 文案、导航或命名问题，不改变总体架构方向 |

## 2. 总体结论

第一轮 Reader Review **未通过最终收口**，但总体架构方向成立；本结论用于保留原始发现，修订后的最终结果见 §10。

读者能够稳定理解：

- P9 是研究与设计收敛，不是已批准路线图或实现 Workpack；
- 业务层级为 `Run → AgentTask → Attempt → ToolCall`；
- Retry 新建 Attempt，Resume 保持原 Attempt，Replay 不重新执行外部操作；
- RunController、Orchestrator、Scheduler、Runtime Adapter 和 ToolGateway 的高层职责不同；
- ToolGateway 是唯一工具入口，Role/Prompt/AgentDefinition/Approval 不能推翻 Hard Policy；
- timeout、cancel、断连和 Worker 失联不能证明外部动作未发生；
- Checkpoint、DomainEvent、ToolResult 和 Safe Trace 的权威级别不同；
- A–E 是建议依赖方向，不是已获批阶段。

读者不能稳定回答的部分集中在四类：建设依赖拓扑、状态/事件的机械映射、dispatch/recovery 原子边界，以及审批和未知副作用的收敛路径。

## 3. Reader Questions 结果

| # | 读者问题 | 结果 | 主要原因 |
|---|---|---|---|
| 1 | 当前是否可以创建 Workpack 或开始实现？ | 通过 | 两份 Design 均明确未授权实施 |
| 2 | Run、Task、Attempt、ToolCall 分别是什么？ | 通过 | 层级与状态权威清楚 |
| 3 | Retry、Resume、Replay、Recovery、Verify 如何区分？ | 通过 | 术语与失败优先级基本一致 |
| 4 | Tool timeout 后为什么不能立即重跑？ | 通过 | unknown outcome 与副作用原则清楚 |
| 5 | 谁推进 Attempt，谁负责 dispatch/lease？ | 部分通过 | 业务状态与 overlay 已区分，但交接事务不完整 |
| 6 | 不需要人工审批的只读 Tool 走哪条合法状态路径？ | 未通过 | ToolCall 图只画出 `awaiting_approval` 路径 |
| 7 | Proposal approved 后、Grant 签发前崩溃怎么办？ | 未通过 | 缺少幂等签发事务与恢复规则 |
| 8 | `partial`、`invalid_output`、`unknown` 属于哪个对象的什么字段？ | 未通过 | FailureCode、Outcome 和 lifecycle state 混用 |
| 9 | A–E 是否满足表中全部硬依赖？ | 未通过 | 多项能力依赖后序能力，并存在 Tool/Policy 环 |
| 10 | Trace、SSE 与 Raw Result 如何证明不会泄漏？ | 部分通过 | 禁限清单清楚，但 typed projection 与持久化前边界不足 |

结果：4 项通过、2 项部分通过、4 项未通过。

## 4. Blocking Findings

### B1：Capability 硬依赖与 A–E 序位不是有效拓扑

证据：

- AgentTask 在 B，却声明依赖 C 的 Event 和 D 的 Policy；
- Orchestrator、Config/Model Routing 在 B，却依赖 C 的 Budget；
- Registry 在 A，却声明依赖 D 的 Policy；
- Middleware 在 A，却依赖 C/D 的 Budget/Policy；
- Tool 依赖 Policy，Policy 又依赖 Tool，形成直接环。

对应位置：综合矩阵 §3.2–§3.3。

最小修正：

1. 将“定义/接口依赖”和“行为激活依赖”分开；
2. 把最小 State/UoW/Event/Policy-core 边界前置；
3. 将 ToolDefinition/effect metadata 与 Tool execution 分开，打破 Tool/Policy 环；
4. A 中的 Middleware 明确只建设不可绕过的骨架，具体 Policy/Budget 阶段随对应能力激活；
5. 重新生成无环的建议序位，不直接把它包装成 Workpack。

### B2：Lifecycle State、Outcome 与 FailureCode 没有正交

Failure 表中的 `partial`、`unknown`、`invalid_output`、`typed runtime failure`、`recovery attempt` 与状态机中的 lifecycle state 混在同一列，导致无法判断它们属于 Run、Task、Attempt、ToolCall，还是失败分类。

同时存在状态/事件覆盖缺口：

- AgentTask proposal 可以被拒绝，但没有 rejected 状态/事件；
- Run 进入 running、ToolCall 进入 scheduled/running 等变化没有完整事件映射；
- Interruption 的 expired/revoked/superseded 缺少对 Attempt 的传播规则；
- 低风险 Tool 缺少 `validating → scheduled` 的审批旁路；
- `outcome_unknown` 和 Action verify 不确定结果缺少完整收敛状态。

对应位置：综合矩阵 §5、§6.2、§7.2。

最小修正：

- 将 `control_state`、`outcome`、`failure_code` 分开；
- 建立“合法转移 → owner → guard → DomainEvent → 下游归约”的覆盖表；
- 每个 current-state 转移要么有唯一 DomainEvent，要么明确只是非领域 overlay；
- Failure 表的最后一列改为明确的对象与字段，不再混用自然语言状态。

### B3：Attempt dispatch、Lease 与 Fencing 缺少可恢复的交接事务

文档规定 RunController 拥有 Attempt 业务状态，Scheduler/ExecutionCoordinator 拥有 dispatch/lease/fencing overlay，但没有定义：

- Acquire/renew/expire/reassign lease 的 CAS；
- dispatch intent、工作命令 Outbox、generation 和 fencing token 的原子提交；
- Worker 回报如何携带并校验 token；
- `AttemptDispatched` 是业务事件还是 overlay 事件；
- Attempt 已提交、Worker 是否启动不明时如何恢复。

对应位置：主 Design D1、D9；综合矩阵 §4.1–§4.2、§6.2、§7.2。

最小修正：补充 dispatch overlay 状态机及事务边界。Scheduler 不能直接推进 Attempt 业务状态；RunController 只接受有效 generation/fencing token 的回报。

### B4：Approval/Grant 与未知副作用的收敛链存在关键 crash window

当前 `RecordApprovalDecision` 提交后才签发 Grant，但没有 `IssueExecutionGrant` 的幂等事务、唯一约束或 approved→issued 崩溃恢复规则。`outcome_unknown` 也只写了“reconciliation/Verify/人工处理”，没有定义证明未执行、确认已执行、Verify 不可判定或人工接管后的目标事实。

此外，现有不变量只禁止有未知高风险动作的 Run 进入 `completed`，没有禁止它伪装成普通 `failed` 终态。

对应位置：主 Design D7、D9、关键不变量；综合矩阵 §4.2、§5.4–§5.5、§7.2、§8。

最小修正：

- 增加幂等 `IssueExecutionGrant` 事务，并与当前 Hard Policy、cancel/deadline、proposal version 和唯一 action identity 做 CAS；
- Grant 必须精确绑定 proposal/version、action digest、目标、Task/Attempt/ToolCall、policy version、审批主体、有效期和一次性 nonce；
- 将 `postcondition_failed` 与 `verification_inconclusive/unavailable` 分开；
- 定义 `outcome_unknown` 的受控收敛结果；
- 为所有 Run 终态增加副作用聚合不变量，未知事实必须保留为可见 limitation/overlay，不能被普通 failed 吞掉。

## 5. Major Findings

### M1：身份与审批人模型必须成为显式外部门禁

正式产品事实仍把身份、租户、角色和审批人模型列为未决事项。P9 不需要在本阶段替它做决定，但必须明确：在该模型独立完成 Design → Review → 用户确认前，不得泛化 Approval/ExecutionGrant；当前只能保持已经确认的固定动作边界和诚实的保证级别。

### M2：Raw Result 的“受限保存”不能被理解为先存后脱敏

当前文字可能让实现者先保存未分类 payload，再生成 Evidence/Trace。这与凭据、原始 SQL、日志和敏感连接信息不得进入普通字段、Event、Trace 或结果的规则存在风险。

P9 应明确：任何持久化前先做类型化字段筛选、classification、凭据检测和脱敏；若未来确需受限 Blob，必须另立数据安全 Design，定义加密、访问控制、服务隔离、TTL/删除、审计和泄漏处置。在此之前不承诺持久化任意 Raw payload。

### M3：Durable SSE 与临时 Runtime progress 没有分流

Domain/Safe Projection 可以按稳定 id 和 sequence 重放；采样的 Runtime event 没有同样的权威序列。需要明确二选一：

- 可重放 SSE 只发布持久化的 Safe Projection；或
- 分为 durable stream 与 ephemeral progress，后者明确不可补播，并定义 gap/reset/retention 语义。

### M4：Budget、Deadline 与 Cancellation 还缺终态 barrier

需要补清：

- Tool 级结算与 Attempt/Task 聚合结算的账本维度，避免重复结算；
- 等待期间 absolute deadline 到期时 Run/Task/Attempt/Interruption 的联动；
- 业务 deadline 与有硬上限的 post-deadline safety reconciliation deadline；
- 多个未知动作如何各自预留 Verify 额度或通过 admission control 限制；
- cancellation barrier 包含哪些在途 Tool、Grant、Interruption 和 Verify。

### M5：Safe Trace 需要 typed deterministic projection 门禁

禁限字段清单本身正确，但 role/task/plan/evidence summary 不能直接复用未经分类的模型文本、异常或 Tool payload。所有 REST/SSE/审计/导出字段应来自 typed facts 与确定性投影，并用恶意 Prompt、凭据、SQL、异常和超长 payload 做负向测试。

### M6：D 在 E 前建设，不等于 D 的副作用路径可以提前激活

Tool/Policy/Approval 的契约可以先于完整跨进程 Recovery 建设，但新的副作用执行路径在最小 reconciliation、unknown outcome 和 kill switch 可用前必须保持禁用或 shadow。分期建议需要区分“契约落地”和“生产激活”。

### M7：规范性 Design 与学习记录的权威关系需要收口

主 Design 通过本机绝对路径引用 Framework-learn，完整契约和 Baseline 不能被仓库内 Reviewer 稳定复核；学习目录的 README、核心契约状态和未决路线仍写着“综合材料尚未形成”。

不需要把全部学习笔记复制进 OperMind，但最终规范性契约、状态覆盖表、Adopt/Adapt/Reject 和阶段输入必须进入 OperMind 的版本化 Design。学习目录继续保存来源、比较过程和被拒绝方案，并在 P9 收口时同步索引状态。

### M8：完成证明仍是测试类别，不是可判定退出条件

`contract suite`、`fault matrix`、`100% 通过` 必须说明分母。最终建议至少为每项能力给出：固定契约版本、必测不变量、负向/竞态/故障场景、预期 oracle、不得 skip/xpass 的硬门禁，以及 Binding/Execution 真实性证据。具体测试文件可留给后续 Workpack Design。

## 6. Minor Findings

1. 主 Design 写“收到取消后先进入 cancelling”，综合矩阵写 `cancel_requested → cancelling`；应统一为先持久化请求，再建立取消 barrier。
2. `Capability` 同时指 Harness 建设能力和 Agent 权限能力；建议分别使用 `Harness Capability` 与 `Agent Capability/Grant`。
3. EventRecorder 是持久化写入协调者，而表中的领域服务是事件事实产生者；应明确两种“产生者”，避免双 owner。
4. 当前 API `queued` 到目标业务状态/dispatch overlay 的兼容映射尚未给出。
5. Runtime signal 与 DomainEvent 存在同名 `AgentTaskProposed`；应使用命名空间或不同后缀。
6. “已经形成一致闭环”早于 Reader Review 修订和用户确认，建议改为“草案已覆盖，待验证闭环”。

## 7. 本轮刻意不要求的内容

以下不是 P9 Reader Review 的 Blocking：

- 立即定义数据库表、迁移和公开 API；
- 立即决定完整身份/RBAC/多租户方案；
- 立即选用 DBOS、CrewAI 或替换 LangGraph；
- 立即实现 durable worker、Raw BlobStore 或新的高风险动作；
- 把全部 Framework-learn 笔记复制到 OperMind。

P9 需要做的是把这些事项变成明确的外部前置条件、激活门禁和后续 Design 输入，而不是在研究阶段顺带实现。

## 8. 修订出口条件

下一步完成修订后，至少满足：

1. A–E 依赖图无环，且区分契约建设与行为激活；
2. lifecycle state、outcome、failure code 分离；
3. 核心状态转移、owner、guard 和 DomainEvent 覆盖闭合；
4. dispatch/lease/fencing 与 Grant 签发 crash window 有明确事务；
5. unknown side effect、Verify 不可判定和 Run 终态不会丢失事实；
6. identity、Raw Result、SSE、Recovery 激活均有显式独立 Design 门；
7. 主 Design、综合矩阵和学习索引不再互相宣称不同进度；
8. 用本文件 §3 的十个问题重新测试，全部通过。

达到这些条件后，才能形成最终 Adopt/Adapt/Reject、建议分期和 P9 用户确认稿。

## 9. 修订记录

2026-08-30 已将第一轮发现写入主 Design 与综合矩阵：

| 发现 | 修订位置 | 当前状态 |
|---|---|---|
| B1 依赖拓扑 | 综合矩阵 §3：拆分定义依赖/行为激活前置，重写 A–E | 通过 |
| B2 State/Outcome/Failure 混用 | 综合矩阵 §5.0、§5、§6、§7.2 | 通过 |
| B3 dispatch/lease/fencing | 综合矩阵 §4.2–§4.3、§6.2 | 通过 |
| B4 Grant/unknown crash window | 综合矩阵 §4.2、§5.4–§5.5、§7.2、§8 | 通过 |
| M1/M2 identity 与 Raw Result | 主 Design D7/D14/D15；综合矩阵 §5.5、§6.4 | 通过 |
| M3/M5 SSE 与 Safe Trace | 主 Design D8；综合矩阵 §6.3–§6.5 | 通过 |
| M4 Budget/Cancel | 综合矩阵 §4.2、§7.3 | 通过 |
| M6 生产激活 | 综合矩阵 §3.3、§8；主 Design §7 | 通过 |
| M7 文档权威 | 主 Design §4；学习索引最终同步仍待 P9 收口 | 部分完成 |
| M8 完成证明 | 综合矩阵 §3.2、§8；主 Design D16 | 通过 |

本轮没有创建 schema、迁移、API、Workpack 或代码实现。复测应使用新的无历史上下文读者，不向其提供第一轮结论。

## 10. 无历史上下文复测结果

修订后使用未读取本文件、未继承此前讨论的新读者重新测试：

| 复测 | 结果 |
|---|---|
| §3 十个 Reader Questions | 10/10 通过，无需作者补充前提 |
| 产品事实与安全治理 | 通过，无 Blocking/Major |
| 运行时依赖、正交字段、owner、事件与 crash window | 最终通过，无 Blocking/Major |

运行时复测曾继续发现并促成三轮精化：

1. 任何现有固定动作迁移也不能早于 E 的最小 Recovery/reconciliation 门；
2. `manual_required` 与 `external_outcome` 分离，并形成对象 × 维度 writer 表；
3. ExecutionCoordinator、ActionExecutionService、RepairCoordinator 成为唯一 writer；
4. Grant 与 `ActionExecution=authorized`、对应事件和 Outbox 同事务创建；
5. persistence invariant 使用独立 fail-closed AutomationGate/RepairCase，不伪造领域历史。

最终复测结论：P9 Reader Review 阶段通过。该结论只证明研究 Design 的原则、边界和门禁可被独立读者稳定理解，不构成代码实施、迁移、API、身份、Raw Blob、durable worker 或新副作用能力的授权。
