---
title: Agent Harness 契约内核与回归基线
status: 已确认
domain: agent-runtime
phase: P9（路线图已登记的 Harness 基础工程段）
issue: 113
updated: 2026-08-30
---

# Agent Harness 契约内核与回归基线 · PRD

## 背景

OperMind 已具备正式会话、Run、SSE、`DiagnosisExecutor`、LangGraph 多 Agent 图、`ToolGateway`、安全 Trace、取消和固定动作链，但这些能力仍以现有实现的局部协议协作，缺少一套框架无关、可独立验证的 Harness 最小契约。继续增加 Agent、Tool、Connector 或恢复能力前，需要先固定共同语言与回归护栏，避免后续能力沿不同状态、错误和适配协议继续分叉。

P9 研究阶段已完成七个开源项目的证据对照、当前代码 Baseline Gap Map、十七组目标契约、综合设计矩阵和独立 Reader Review，并由用户确认收口。最终方向是“OperMind 自有业务控制面 + 可替换 Agent Runtime Adapter”，不整体迁移到任何开源框架。研究结论不等于实施授权；本 PRD 只选择建议阶段 A 中第一个零行为变化候选包。

关联依据：

- `docs/产品定义.md`：OperMind 是会话式多 Agent DevOps Copilot；外部访问必须经过受控 Tool，公开 Trace 不展示 CoT、Prompt、原始 Tool 输出或凭据。
- `docs/路线图.md`：已将本候选包登记在当前体验驱动完善收口后、第三阶段能力扩展前；只登记本 PRD，不承诺完整 A–E。
- `docs/开发规范.md`：跨层数据使用 Pydantic 或 TypedDict，Agent 与 Tool 复用约定接口，关键路径必须有确定性测试，编排语义变化必须 Design → Review → 用户确认。
- [P9 Agent Harness 正式化 Design](../../design/agent-runtime/P9AgentHarness正式化Design.md)：给出完整目标架构与安全边界。
- [P9 Agent Harness 综合设计矩阵](../../design/agent-runtime/P9AgentHarness综合设计矩阵.md)：给出七类正交维度、能力依赖和行为激活门。
- [P9 最终取舍与后续建议](../../design/agent-runtime/P9AgentHarness最终取舍与后续建议.md)：确认第一个候选包只建立契约、Adapter 测试与现状回归，不改变生产行为。

## 目标

1. 建立框架无关的 Harness 最小类型语言，使生命周期、结果、外部事实、失败原因、处置责任和执行 overlay 不再混入同一个模糊 `status`。
2. 定义并验证最小 Runtime Adapter 边界，使当前 Runtime 可以被同一套契约测试描述，而不把生产调用链切换到新 Adapter。
3. 固定现有 Run、Tool、Trace、取消和固定动作链的确定性回归基线，为后续 Harness 演进提供不可绕过的行为护栏。
4. 证明该候选包可以在无公开 API、无迁移、无权限变化、无真实外部访问和无用户可见行为变化的前提下交付。

## 用户故事

- 作为后续 Agent Runtime 的开发者，我希望使用统一、typed、versioned 的 Harness 基础契约，而不是猜测不同组件中 `status`、错误和执行身份的隐式含义。
- 作为维护现有 Runtime 的开发者，我希望能用框架无关的契约测试验证当前执行边界，避免替换或包裹 Runtime 时静默改变取消、失败或上下文传播语义。
- 作为评审者，我希望每次 Harness 改动都能自动证明现有 Run、Tool、安全 Trace 和固定动作边界没有回归，也没有偷偷进入阶段 B–E。
- 作为产品用户，我希望这项底层整理不改变当前可见功能、权限、接口和调查行为。

## 范围

### 做什么

本 PRD 只包含一个 Workpack 候选中的三个紧密切片。

#### 1. Harness Contract Kernel

- 建立以下七类正交维度的 typed、封闭、可版本化命名空间：
  - `lifecycle_state`；
  - `result_disposition`；
  - `external_outcome`；
  - `failure_code`；
  - `resolution_disposition`；
  - dispatch overlay；
  - control overlay。
- 建立通用 identity、version、generation / fencing value objects 的最小契约，包括构造校验、比较、序列化边界和无效值拒绝。
- 在现有 `DiagnosisExecutor` port 的基础上，定义框架无关的最小 Runtime Adapter contract、输入输出 envelope、能力声明和 typed failure / signal 边界。后续 Design 必须先完成现有 port 与目标 contract 的逐项映射；没有明确 gap 证据时，不得创建职责重叠的第二套生产 port。
- 契约只作为独立工程结构与测试资产存在；不让新类型接管现有生产状态，不新增 Task / Attempt 等业务对象。

#### 2. Adapter Contract Test Harness

- 建立可复用的 Adapter 契约测试夹具和断言，覆盖正常返回、typed failure、取消、超时、上下文传递及不支持能力的诚实表达。
- 围绕当前 `DiagnosisExecutor` 的 Runtime 边界和当前 `ToolGateway` 的受控工具边界分别建立兼容性测试；二者不被强制实现同一个接口，也不改变生产依赖注入。
- 契约测试分为两层：框架无关的 reference / fake Adapter 必须完整通过目标 contract；当前 `DiagnosisExecutor` 按显式 capability profile 验证最小兼容子集，并把暂不支持项记录为版本化 expected gap。新增未知 gap、已声明支持却不满足，或 expected gap 无证据漂移都必须使测试失败；不得使用 `xfail` 表达 gap。
- 契约测试只能使用确定性 fake / mock，不连接真实模型、数据库、主机、日志系统或其他外部资源。
- 对框架私有状态只验证其不越权成为 OperMind 业务事实，不固化 LangGraph 私有实现细节。

#### 3. Regression Baseline

- 为当前 Run 生命周期与终态、Tool allow / deny、安全 Trace、取消和固定动作链建立确定性回归场景。
- 明确区分必须保持的产品 / 安全保证与可以在后续 Design 中替换的偶然实现细节。
- 至少提供一个负向样例，证明契约或安全边界被破坏时测试门禁会失败。
- 形成“当前行为基线与已知缺口”记录；缺口只作为后续决策输入，不在本 PRD 顺手修复。

### 不做什么（严格排除）

- 不新增或修改数据库迁移、表、列、约束或持久化状态。
- 不新增或修改公开 API、OpenAPI、SSE 协议、前端页面或用户文案。
- 不把生产执行链切换到新 Runtime Adapter，不改变生产依赖注入、路由、Agent 顺序或编排语义。
- 不新增 worker、队列、Outbox、Checkpoint、Lease 持久化、Recovery、Repair 或 durable execution。
- 不引入 AgentTask、Attempt、ContextManifest、BindingSnapshot、ResultAcceptance 等阶段 B 业务对象或状态机。
- 不实现 Registry、动态 ToolDefinition、PolicyBundle、HarnessUnitOfWork、DomainEvent Pipeline、Budget ledger 或 Eval 平台。
- 不修改任何依赖清单或 lockfile，不新增生产、测试或开发依赖；不迁移 LangGraph、DBOS、CrewAI 或其他 Runtime 内核。
- 不新增 Agent、Connector、Tool、服务类型、模型调用或真实外部资源访问。
- 不改变权限、审批、ExecutionGrant、ActionExecution、Verify 或当前固定动作语义。
- 不实现长期记忆、RAG、向量检索、MCP、任意文件系统、Shell、SQL 或网络执行能力。
- 不借机清理、重命名或重构与三个切片无关的 Runtime 代码。

## 功能需求

### 1. 正交状态契约

- **输入**：需要表达生命周期、执行结果、外部事实、失败原因、后续处置或执行所有权的 Harness 测试场景。
- **行为**：每类事实进入自己的 typed 命名空间；同名值不得因字符串相同跨维度互换；枚举或分类须封闭并带显式契约版本。`failure_code` 至少能按 validation、runtime、model、tool、policy、approval、budget、cancel、recovery、persistence 和 internal 分类，但本 PRD 不实现各业务对象状态机。
- **输出**：可被静态类型与运行时校验共同验证的七维最小契约；不存在一个新建的万能 `status` 类型。

### 2. 通用身份、版本和 fencing 值对象

- **输入**：测试或 Adapter envelope 中的通用标识、契约版本、generation 和 fencing token。
- **行为**：拒绝空值、非法格式、无效版本和不允许的比较；明确稳定序列化形式。值对象只表达机械身份与并发校验材料，不推断授权、业务完成或外部副作用事实。
- **输出**：最小、typed、可测试的 value objects；不产生 Run / Task / Attempt / ToolCall 新业务身份，也不写入数据库。

### 3. Runtime Adapter 最小协议

- **输入**：框架无关的测试执行请求、不可变上下文视图、取消 / deadline 信号和能力要求。
- **行为**：Adapter 只返回结构化 runtime signal、候选结果或 typed failure；不得直接推进 OperMind 业务状态、执行 Connector、授予权限或把框架 checkpoint 当作业务完成证明。不支持的能力必须明确返回不支持，不能静默 fallback。
- **输出**：独立于 LangGraph 或其他框架类型的最小协议与契约测试入口，以及现有 `DiagnosisExecutor` → 目标 contract 的映射。若现有 port 足以承载所需 contract，应复用或以测试 companion 约束；若确需新增接口，Design 必须证明职责不重叠且新接口不被生产入口导入。

### 4. 当前 Runtime 边界的兼容性验证

- **输入**：当前 `DiagnosisExecutor` 可离线执行的确定性场景。
- **行为**：reference / fake Adapter 完整验证正常完成、失败映射、不支持能力、超时、取消和上下文传递。当前 `DiagnosisExecutor` 只按版本化 capability profile 验证已声明支持的最小子集；未支持项以结构化 expected gap 被测试主动断言，而不是产生失败测试、`skip` 或 `xfail`。兼容层只存在于测试或未接入生产的参考实现中。
- **输出**：全部测试用例本身通过；已支持能力满足契约，已知缺口与版本化 expected gap 完全一致。新增 gap、gap 无证据消失或 capability 声明失真都会导致测试失败；不得为让测试通过而改写生产行为。

### 5. 当前 ToolGateway 边界的兼容性验证

- **输入**：当前已注册的确定性测试 Tool、允许 / 拒绝策略和受控参数。
- **行为**：验证 Tool 只能经 `ToolGateway` 受控入口执行，拒绝时不触发 Tool，异常映射不泄露原始输出；测试不得建立 Runtime 绕过 ToolGateway 的第二入口。
- **输出**：允许、拒绝、参数无效和安全失败的确定性断言；不新增 Tool 或权限能力。

### 6. 现有行为回归基线

- **输入**：无需真实外部资源的 Run、Tool、Trace、取消和固定动作代表性场景。
- **行为**：对现有公开保证和安全边界建立稳定 oracle；运行 ID、时间和耗时等非确定值必须归一化；不得通过整段脆弱文本快照固化模型文案或框架内部状态。
- **输出**：可重复的通过 / 失败结果，以及产品保证、工程契约和偶然实现细节的分类记录。

### 7. 边界漂移门禁

- **输入**：本候选包的最终变更集。
- **行为**：使用后续 Design 固定的机器门禁检查最终 diff：依赖清单与 lockfile 内容不变；迁移目录、前端目录、API 路由 / schema、生产 DI、当前 `CoordinatorDiagnosisExecutor`、应用 Run 服务和 `ToolGateway` 实现无改动；OpenAPI 规范化快照与迁移 head 不变；新增 Contract Kernel / 测试模块未被生产入口或装配模块导入。任一命中都必须停止并拆出独立 PRD / Design，不能在本包内豁免。
- **输出**：命令、基线和结果均可复验的零行为变化边界证明；只写“人工已审查 diff”不算通过。

## 非功能需求

- **确定性**：契约与回归测试离线运行，相同输入产生相同关键断言；时间、随机值和 ID 使用受控时钟或固定生成器。
- **框架中立**：公开给 Harness 的最小协议不导入 LangGraph、OpenAI Agents SDK、PydanticAI、DBOS、CrewAI 或其他框架私有类型。
- **安全**：测试、日志和失败输出不得包含 CoT、Prompt、原始 Tool 输出、原始异常、原始 SQL、DSN、API Key、路径或凭据。
- **兼容性**：现有生产 Runtime 装配、数据库、API、SSE、权限、取消和固定动作行为保持不变。
- **可维护性**：失败信息必须指出违反的契约类别，不能只给整段快照 diff；测试辅助结构不得形成第二套生产 Runtime。
- **诚实性**：mock / fake 必须明确标识；当前实现无法满足目标契约时记录 gap，不伪装为已实现阶段 B–E 能力。

## 数据与接口影响

- 数据：无新增持久化、无数据库迁移、无现有数据回填。
- 后端公开接口：无新增或变更 API、OpenAPI、SSE 字段或错误契约。
- 前端：无代码和用户可见文案变化。
- 依赖：任何生产、测试或开发依赖清单与 lockfile 均不变化。
- 运行行为：生产依赖注入、Runtime 调用链、Tool 执行链和固定动作链保持原样。

## 验收标准

- [ ] AC1: 当同名值分别用于 lifecycle、result、external outcome、failure、resolution、dispatch 和 control 时，类型与运行时校验应阻止跨维度误用；不得新增万能 `status` 契约。
- [ ] AC2: 当构造 identity、contract version、generation 或 fencing value object 时，合法值可稳定 round-trip，空值、非法格式、无效版本和禁止的比较会被明确拒绝。
- [ ] AC3: 当检查 Contract Kernel 时，不存在 AgentTask、Attempt、ContextManifest、BindingSnapshot 或其他阶段 B 业务实体、状态机和持久化映射。
- [ ] AC4: 当实现一个 reference / fake Runtime Adapter 时，完整 contract suite 应覆盖正常结果、typed failure、不支持能力、取消、超时和上下文传递并全部通过，且协议不导入具体 Agent 框架类型；同时应给出现有 `DiagnosisExecutor` 到目标 contract 的逐项映射，不得无证据创建职责重叠的第二套生产 port。
- [ ] AC5: 当使用当前 `DiagnosisExecutor` 的离线兼容夹具运行 contract suite 时，已声明支持的最小子集必须通过，暂不支持项必须与版本化 expected gap 完全一致；新增未知 gap、已支持能力回归或 capability 声明失真必须失败，不得用 `skip`、`xfail` 或生产行为修改掩盖。
- [ ] AC6: 当测试 `ToolGateway` 的允许、拒绝、参数无效和执行失败场景时，拒绝场景不得触发 Tool，安全结果不得包含原始参数、输出、异常或凭据。
- [ ] AC7: 当运行代表性 Run 场景时，当前生命周期与终态保证应被确定性验证；测试不得把 LangGraph checkpoint 或私有 graph state 当业务完成证明。
- [ ] AC8: 当运行取消场景时，现有取消请求、终态和迟到结果保护应保持当前语义；本包不得新增 cancellation barrier、持久化协调或恢复行为。
- [ ] AC9: 当运行安全 Trace 场景时，公开投影只包含既有允许字段与脱敏摘要，不出现 CoT、Prompt、原始 Tool 输出、原始异常、SQL、路径或凭据。
- [ ] AC10: 当运行当前固定动作代表性场景时，既有 Proposal、Decision、执行和 Verify 边界保持不变；不得签发新 Grant、增加动作或改变审批权限。
- [ ] AC11: 当测试用例向门禁输入至少一个跨维度状态误用、ToolGateway 绕过或敏感 Trace 泄漏的负向样例时，违例输入必须被拒绝并指出契约类别，而承载该断言的测试用例本身必须通过；仓库中不得提交故意失败的测试。
- [ ] AC12: 当相同确定性场景重复运行时，归一化 ID、时间和耗时后，关键契约结果一致；测试不访问真实模型、数据库、主机、日志系统或网络。
- [ ] AC13: 当执行 Contract Kernel / Adapter / Regression 新增套件时应 100% 通过且无 `skip`、`xfail` / `xpass`；后端全量测试应按仓库既有基线通过，本包不得新增或扩大 skip / xfail，也不得放宽既有断言掩盖失败。
- [ ] AC14: 当执行后续 Design 固定的边界门禁时，应机器确认：依赖清单与 lockfile 无变化；迁移、前端、API 路由 / schema、生产 DI、当前 Runtime / Run 服务 / ToolGateway 实现无 diff；规范化 OpenAPI 与迁移 head 不变；新增模块未被生产入口导入。只靠人工审查不能使本 AC 通过。
- [ ] AC15: 当交付本候选包时，应形成版本化“当前行为基线与已知缺口”记录；新增未知 gap 必须失败，gap 变更必须有证据与 Review，并明确后续阶段仍需重新进入 PRD / Design / 用户确认流程。
- [x] AC16: 当进入实施 Design 前，正式路线图应已同步登记“当前完善收口后、第三阶段能力扩展前的 Harness 基础工程段”，且只登记本候选包方向，不把 A–E 整体承诺为已批准阶段。

## 边界与约束

- **唯一事实源**：现有生产 Run、Tool、Action 和数据库仍是当前事实源；Contract Kernel 不成为第二套状态存储。
- **Adapter 边界**：Runtime Adapter 只负责技术执行协议，不拥有 OperMind 业务状态、权限、预算、Tool 副作用或审批事实。
- **Tool 边界**：模型与 Runtime 不获得 Connector；Tool 执行继续只能经过现有 `ToolGateway`。
- **行为边界**：本 PRD 只建独立类型、协议、测试辅助结构和文档，不把新协议接入生产调用链。
- **扩范围处理**：任何迁移、API、生产接线、业务 identity、持久化、Recovery、权限或副作用语义需求必须停止当前包并单独决策，不能以“为未来预留”为由加入。
- **工程闸门**：本 PRD 已由用户确认，并已作为“当前完善收口后、第三阶段扩展前的基础工程段”同步到 `docs/路线图.md`；issue #113、实施 Design、独立 Review 与用户确认均已完成，Safe Trace 前置阻塞也已修复并通过目标 Python 3.11.9 回归。下一步必须先让前置收口与 P9 规划提交形成已 Review、已合并的干净 base，再按实施 Design 创建并确认 Workpack；此前仍不授权 P9 代码开发。

## 完成定义（DoD）

- [ ] 全部 AC（AC1–AC16）通过并在 Workpack evidence 中逐项给出可复验依据。
- [ ] Contract Kernel、Adapter Contract Test Harness、Regression Baseline 三个切片均完成，未出现第四个隐含切片。
- [ ] 相关聚焦测试和后端全量测试全部通过，无 skip、xfail / xpass；若未修改前端，则不为形式要求制造前端改动。
- [ ] 至少一个负向输入被契约 / 安全门禁正确拒绝，承载拒绝断言的测试用例本身通过。
- [ ] `git diff --check` 通过；后续 Design 固定的机器门禁证明依赖、迁移、OpenAPI、前端、生产接线与生产 import graph 未变化，并完成敏感字面量检查。
- [ ] 无数据库迁移、公开 API / SSE / 前端、任何依赖清单或 lockfile 变化、真实外部访问、权限变化或用户可见行为变化。
- [ ] “当前行为基线与已知缺口”记录完整区分现有保证、目标契约和未实现能力，不把 gap 描述为已交付。
- [x] 实施 Design、独立 Review 和用户确认均已完成；Workpack 只在这些门通过后创建。

## 已关闭的实现决策

无产品或实现开放问题。包路径、依赖方向、value objects、`DiagnosisExecutor` 复用边界、兼容夹具、versioned expected capability profile、回归套件和 baseline / evidence 放置方式均已由 `docs/design/agent-runtime/P9HarnessContractKernel实施Design.md` 定稿；任何改变这些决定或本 PRD 严格边界的需求都必须重新进入 Design。

## GitHub Issue

- issue：[#113](https://github.com/wzhwwwzzzhhh/oper-mind/issues/113)——P9 Agent Harness 契约内核与回归基线。
- issue 只描述本 PRD 的三个切片和严格排除项，不把阶段 A 其余内容或 B–E 纳入同一 issue。
- 状态同步：本 PRD、正式路线图与 issue 已同步；实施 Design 已确认，尚未创建 Workpack，issue 与 Design 均不等于 P9 代码开发授权。
