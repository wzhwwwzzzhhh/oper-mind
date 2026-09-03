---
title: P11：Agent Harness 真实运行安全门
status: 已确认
domain: agent-runtime
phase: P11
issue: 121
updated: 2026-09-03
---

# P11 Agent Harness 真实运行安全门 · PRD

## 背景

P10 已完成 Agent Harness 契约内核、当前 Runtime / ToolGateway 兼容性画像和零行为变化回归基线，但刻意没有接管生产调用链。P10 的机器证据同时固定了几个在进一步进行真实服务端到端验证前必须处理的缺口：

- 当前 `DiagnosisExecutor` 允许零个或多个完成结果，也允许完成结果后继续输出事件；`RunApplicationService` 只保留最后一个结果，不能在 Runtime 边界证明“恰好一个终止信号”；
- 非 `DiagnosisExecutionError` 的意外异常会逸出当前执行端口，虽然 Run 外层最终会写入安全失败，但 Runtime 契约本身仍不能给出 typed failure；
- 当前 `ToolGateway` 的 timeout 只停止调用方等待，同步 Tool 线程仍可继续执行；现有文案却可能让读者误以为底层执行已经中止；
- PostgreSQL、Redis 等既有真实技术切片分别配置了驱动级超时和只读边界，但尚未形成一套进入下一次真实端到端验证前可统一复验、默认不访问外部资源的 Harness 安全门。

这些问题不要求立即建设完整的 Task / Attempt、持久化控制面或 Recovery。考虑当前交付时间约束，P11 只把 P10 已记录、且会直接影响真实运行可信度的边界收紧为生产保证；P12 及后续真实 PostgreSQL 端到端目标另行决策。

关联依据：

- `docs/产品定义.md` §3–§5：真实事实只能经受控 Tool / Connector 读取，所有外部访问必须具备参数校验、权限边界、超时、脱敏和审计摘要。
- `docs/路线图.md`：P10 只交付契约与回归基线，后续生产激活必须重新进入 PRD → Design → Review → 用户确认。
- `docs/开发规范.md` §2–§6：多 Agent 编排语义、Connector、外部连接和凭据变化必须先 Design；真实依赖必须保留确定性 mock，真实资源测试必须由用户明确授权。
- `docs/prd/agent-runtime/P9-harness-contract-kernel.md`：固定了 Runtime Adapter v1 目标协议、当前 capability profile 和 ToolGateway timeout expected gap。
- `docs/design/agent-runtime/P9AgentHarness最终取舍与后续建议.md`：确认 OperMind 拥有业务控制面，LangGraph 只处于可替换 Runtime Adapter 之后；deadline、timeout 和 cancel 必须保持正交。

## 目标

1. 在生产 Runtime 边界保证一个正常结束的有限执行流只提交一个受控终止结果；零终止、多终止、终止后输出和意外异常都必须收敛为安全 typed failure，不能形成虚假成功。永不结束的 Runtime 仍诚实保留为 deadline gap。
2. 将 ToolGateway 的“调用方等待超时”和“底层执行是否停止”明确分开，保证超时后的迟到结果不会重新进入 Agent、Run、结果或公开 Trace。
3. 为既有只读目标 Connector 建立可复验的超时、只读、脱敏和默认离线门禁，为后续真实端到端验证提供安全前置条件。
4. 在无新增服务类型、无真实资源访问、无数据库迁移和无公开 API / 前端变化的前提下完成 P11。

## 用户故事

- 作为运维用户，当一次多 Agent 调查异常、超时或输出协议失真时，我希望系统给出唯一且诚实的失败终态，而不是保存最后一个碰巧出现的结果或显示互相矛盾的状态。
- 作为运维用户，当工具调用超时时，我希望系统只陈述能够证明的事实；如果底层任务是否停止未知，系统不能把“停止等待”描述成“执行已中止”。
- 作为后续真实服务接入的开发者，我希望在获得真实资源授权前，先用确定性测试证明 Runtime、ToolGateway 和既有 Connector 的关键安全边界，避免用一次真实环境成功掩盖 Harness 缺口。
- 作为评审者，我希望 P10 的 capability gap 只能依据行为探针升级，不能仅通过修改声明或删除 expected gap 假装完成。

## 范围

### 做什么

P11 是一个 PRD、一个 Issue、一个 active Workpack，最多包含以下两个紧密切片。

#### S1. Runtime 唯一终态与安全失败

- 在现有 `DiagnosisExecutor` 与 Run 执行链之间激活最小 Runtime 执行保护边界；具体采用 Adapter、wrapper 或对现有 port 的兼容演进，由后续 Design 决定，但不得建立第二套业务 Run 事实源。
- 复用 P10 的 typed Runtime contract，校验正常结束的有限执行流只能是“零到多个安全事件 + 恰好一个 result 或 failure”。P11 不宣称可以在没有 Runtime deadline 的情况下终止永不结束的 iterator。
- 将以下协议违例统一映射为受控 typed failure：
  - 执行流结束但没有终止信号；
  - 出现多个 result / failure；
  - result / failure 后继续输出事件；
  - Runtime 抛出未预期异常；
  - Runtime 输出无法通过既有 typed contract 校验的对象。
- Runtime 内部 typed failure 只能携带封闭 failure code 和固定安全文案，不得保存或公开原始异常、堆栈、Prompt、原始 Tool 输出、SQL、路径或凭据。P11 不扩展公开错误码集合：写入现有 Run、RunEvent 和 API 的错误继续统一映射为既有 `DIAGNOSIS_FAILED` 安全码与文案，内部分类只用于执行边界与测试定位。
- Run 仍是现有产品事实源。成功只允许由通过完整流校验的唯一 result 触发；协议违例不得写入成功 Result、助手成功消息、成功终态或后续动作提案。
- 保留现有 CAS 终态保护：Run 已经 `succeeded`、`failed` 或 `cancelled` 后，迟到的 Runtime result / failure 不得覆盖终态或追加第二个终态事件。
- 更新 P10 capability profile 及行为探针，只升级已有证据确实覆盖的能力；未在 P11 实现的 deadline、控制传播和底层取消能力继续诚实保留为 gap。
- 保留 P10 zero-behavior baseline 作为 P10 的不可变历史证据，同时把“P10 阶段只允许零行为变化”的固定 allowlist / protected hash 与新的 P11 实施门分开；不得删除历史基线，也不得让 P10 的阶段性禁改规则永久阻止经 P11 Design 批准的生产边界变化。

#### S2. Tool / Connector 超时与真实验证前门禁

- 将 ToolGateway 的调用方等待状态、工具结果接纳状态和底层执行状态分开表达；timeout 返回后，任何迟到 output、异常或 audit summary 都不得再进入 Agent memory、Run Result、事件或公开 Trace。
- timeout 发生时，尚未开始运行的排队 future 必须被取消并证明对应 Tool 永不执行；已经开始运行且无法协作取消的 Tool 只能标记为停止状态未知，不能因为调用方已返回 timeout 而继续接纳其结果。
- timeout 文案和结构化记录不得宣称底层执行“已中止”“已取消”或“没有产生访问”，除非对应 Connector 的行为探针能够证明这一事实。
- 对会访问目标服务的既有只读 Tool / Connector，机器验证其资源级时间边界，而不只验证 Gateway 的 `future.result(timeout=...)`：
  - PostgreSQL 连接和查询具有驱动 / 服务端限时，并在只读事务内执行；
  - Redis 连接和命令具有客户端限时，只执行既有允许的只读监控命令；
  - 连接、查询或关闭失败统一收敛为安全的 timeout / unavailable / error，不泄漏 DSN、host、用户名、原始异常或目标数据。
- Gateway 超时必须在确定性 fake 场景中有时间上界，测试不得依赖不稳定的长时间 sleep；底层无法被 Python 线程强制停止时，必须保留“停止状态未知”的内部事实，并通过迟到结果隔离保证不会形成业务成功。
- 建立默认离线的真实资源测试入口约束：普通单测、全量测试和 CI 不得因本机存在 DSN 或其他凭据而访问真实网络；软件入口只在显式 opt-in、显式目标和凭据引用同时满足时才具备尝试运行的技术前提。
- 用户对目标、账号权限、数据边界与脱敏方式的当次授权属于运行真实测试前的人工操作前置条件，不伪装成 P11 能自动验证的软件状态；即使软件条件满足，P11 的开发与验收也不得实际访问真实资源。
- P11 只验证门禁的拒绝与确定性 fake 行为，不连接、探测或读取任何真实外部资源；具体真实 PostgreSQL 端到端场景留给后续独立阶段。

### 不做什么（明确排除）

- 不创建 `AgentTask`、`Attempt`、`ContextManifest`、`BindingSnapshot` 或新的业务状态机。
- 不新增数据库表、字段、迁移、DomainEvent、Outbox、UoW、队列、Lease、generation writer、fencing 执行或 Recovery。
- 不实现全局 Run deadline、Budget ledger、跨进程取消、任意同步线程强杀或“外部执行 exactly-once”。
- 不新增或替换 Agent 框架，不把 LangGraph thread、graph state 或 checkpoint 变成业务事实源。
- 不新增服务类型、Connector、Tool、调查能力、监控指标、凭据保存方式或高风险动作权限。
- 不连接、探测、读取、写入或清理 PostgreSQL、Redis、日志系统、模型 Provider 或其他真实外部资源。
- 不新增或修改公开 API、OpenAPI、SSE 字段、前端页面和用户操作入口；安全失败继续映射到既有公开 Run 状态与安全文案。
- 不把 P12、真实 PostgreSQL 端到端、部署演示、Redis 深化或日志深化塞入 P11。
- 不删除 P10 的 expected gap 或放宽回归断言来制造通过；不使用 `skip`、`xfail` / `xpass` 表达应交付能力。
- 不覆盖或重生成 P10 zero-behavior baseline 来吸收 P11 行为变化；P11 必须建立自己的允许范围、行为预期和负向门禁。

## 功能需求

### 1. Runtime 执行流校验

- **输入**：现有 Run 的 query、service context，以及当前 `DiagnosisExecutor` 产生的事件、结果或异常。
- **行为**：生产执行保护边界按 P10 Runtime contract 校验类型、顺序和终止基数；对于正常结束的有限执行流，终止信号只作为候选，完整流合法后才能提交成功。iterator 未结束时不宣称已完成，P11 也不宣称已解决该 deadline gap。
- **输出**：合法流得到唯一成功 result；协议违例得到唯一 typed failure。两种路径都只能推动一个现有 Run 终态。

### 2. 意外异常安全收敛

- **输入**：Runtime 构造、迭代、事件转换或结果转换期间出现的非预期异常。
- **行为**：在 Runtime 边界映射为封闭的 unexpected-exception failure；原始异常只用于进程内安全诊断，不进入业务持久化和公开投影。
- **输出**：Runtime 边界保留内部 typed failure 分类；既有 Run、RunEvent 与 API 继续使用 `DIAGNOSIS_FAILED` 固定安全错误码 / 文案和唯一失败事件；无成功 Result、成功助手消息或动作提案。

### 3. 终态竞争与迟到 Runtime 输出

- **输入**：取消与 Runtime 返回并发，或者已终态 Run 收到迟到 result / failure。
- **行为**：继续以现有 Run CAS 和终态为权威；迟到输出不得覆盖终态、创建结果、追加第二终态事件或触发动作。
- **输出**：Run、Result、Message、Event 和 Proposal 对同一终态保持一致。

### 4. Tool 等待超时与结果接纳

- **输入**：合法 Tool 调用超过 Gateway 等待上限，随后底层 Tool 返回结果或抛出异常。
- **行为**：Gateway 在上限内返回 timeout，并关闭本次调用的结果接纳；尚未开始的排队 future 必须取消且不得稍后执行，已经运行的 future 若无法协作取消则保留停止状态未知。迟到完成只允许释放本次资源，不得重新投递业务输出。
- **输出**：一个安全 timeout 结果和一条安全审计摘要；不得出现第二个 ok / error 结果，也不得把迟到 output 交给模型。

### 5. Connector 资源级时间与只读边界

- **输入**：既有 PostgreSQL / Redis 只读目标访问的连接、查询 / 命令、失败和超时场景。
- **行为**：使用确定性 fake / 配置探针验证连接与操作本身有界、只读命令集合不扩大、失败映射安全；Gateway timeout 不得替代 Connector 自身的资源级限时。
- **输出**：可定位到 Gateway、PostgreSQL 或 Redis 边界的机器验证结果。

### 6. 默认离线与显式真实测试门

- **输入**：普通测试、CI，或缺少 opt-in / 目标 / 凭据引用中任一技术条件的真实测试请求。
- **行为**：默认使用 deterministic fake / mock；真实入口失败关闭，不尝试 DNS、建连、模型调用、文件系统越界或其他外部访问。
- **输出**：普通测试保持离线；不满足软件前置条件时给出不含凭据的明确拒绝原因。用户当次授权继续作为实际运行前必须人工核对的独立操作门，不进入自动化通过结论。

### 7. P10 历史基线与 P11 阶段门分离

- **输入**：P10 不可变 baseline、P10 固定 allowlist / protected hashes，以及经确认的 P11 Design 允许变更面。
- **行为**：继续验证 P10 当时交付内容和历史证据未被改写；另由 P11 阶段门约束本阶段只能修改经 Design 批准的 Runtime / Tool 安全边界。不得通过重算 P10 baseline、扩大 P10 全局白名单或删除测试来接受 P11 变化。
- **输出**：P10 历史结论仍可复验，P11 合法变化可以进入独立测试与 Review，任一越界生产文件仍会被 P11 门禁拒绝。

## 非功能需求

- **安全**：不扩大任何 Agent、Tool、Connector 或高风险动作权限；所有公开与持久化信息继续执行最小披露和脱敏。
- **诚实性**：等待超时不等于底层停止；未被探针证明的保证必须继续记录为 gap，不能通过命名或文案升级能力。
- **确定性**：新增 contract / regression 测试完全离线，同一固定输入重复执行得到一致的状态、错误类别和安全投影。
- **可靠性**：任何有限 Runtime 流 / Tool 协议违例都失败关闭，不能留下成功 Result、成功消息、第二终态、超时后才启动的排队 Tool 或迟到工具事实。
- **兼容性**：合法的现有 Runtime 流、mock 场景、现有只读 Connector 和公开 API 行为保持兼容；只收紧此前未定义或失真的异常路径。
- **可维护性**：失败必须能定位为 Runtime terminal、unexpected exception、late result、Gateway wait timeout、Connector timeout、read-only 或 secret safety 中的明确类别。

## 数据与接口影响

- **数据**：不新增持久化，不做数据库迁移；继续复用现有 Run、Result、Message、RunEvent 和 Proposal 事实。
- **接口**：不新增或修改公开 REST / SSE / OpenAPI 契约；typed Runtime / Tool 执行契约属于后端内部协议。内部 failure code 在 P11 仍映射为公开的 `DIAGNOSIS_FAILED`，不扩展用户可见错误码集合。
- **配置**：不新增生产凭据保存方式。若后续 Design 需要测试专用 opt-in 开关，其默认值必须关闭，且不得接收或输出凭据正文。
- **外部资源**：P11 的实现、测试、Review 和验收均不访问真实外部资源。

## 验收标准

- [ ] AC1：当正常结束的有限 Runtime 流输出零到多个合法事件后输出唯一 result 时，Run 只写入一个 Result、一条成功助手消息、一个 `succeeded` 终态和一条成功终态事件。
- [ ] AC2：当有限 Runtime 流正常结束且没有 result / failure 时，应映射为 typed failure；Run 不得成功，也不得写入 Result、成功助手消息或动作提案。
- [ ] AC3：当有限 Runtime 流输出两个终止信号，或在 result / failure 后继续输出事件时，应按协议违例失败关闭；不得采用最后一个结果，也不得追加终止后的公开事件。永不结束的 iterator 不计为本 AC 已解决，继续记录为 deadline gap。
- [ ] AC4：当 Runtime 在构造、迭代或转换期间抛出未预期异常时，应映射为封闭的 unexpected-exception failure；Run、事件、结果、日志和 API 响应不得包含原始异常、堆栈、路径、SQL、Prompt、Tool 输出或凭据。
- [ ] AC5：当 Runtime 主动产生合法 typed failure 时，Runtime 边界应保留其内部受控类别用于测试与诊断；写入 Run、RunEvent 和 API 时仍映射为既有 `DIAGNOSIS_FAILED` 安全码与文案，并推动唯一失败终态，不得包装为成功或产生第二终态。
- [ ] AC6：当取消与 Runtime 完成竞争，或 Run 已终态后到达迟到 result / failure 时，现有终态保持不变，终态事件总数为一，且无迟到 Result、Message 或 Proposal。
- [ ] AC7：P10 capability profile 必须升级版本，并由行为探针证明 `terminal_cardinality` 与 `unexpected_exception` 的新状态；`deadline`、`control`、`adapter_cancellation` 等未实现项继续保留准确 gap。删除 gap 但探针未通过时测试必须失败。
- [ ] AC8：当同步 Tool 超过 Gateway 等待上限时，Gateway 应在后续 Design 规定的确定性容差内返回唯一 timeout，且公开摘要不得声称未被证明的“底层已中止”。
- [ ] AC9：当已经 timeout 的 Tool 随后返回敏感 output、抛出敏感异常或生成 audit summary 时，这些迟到内容不得进入 Agent memory、Runtime result、RunEvent、公开 Trace 或第二个 GatewayResult。
- [ ] AC10：当 Tool 调用在前一个调用占用 worker 时排队，并在尚未开始执行前达到等待上限，排队 future 必须成功取消且对应 Tool 的执行次数保持为零；不得在 Gateway 已返回 timeout 后补执行该调用。
- [ ] AC11：当 Connector 可证明资源级取消 / 超时时，内部记录可以表达已知结果；不能证明时必须表达停止状态未知。两种情况都不得把未知伪装成 cancelled 或 stopped。
- [ ] AC12：PostgreSQL 确定性探针应证明连接和语句限时已配置、调查在只读事务内运行、非 SELECT / 非法标识符仍被拒绝，且异常或 DSN 不进入结果与 Trace。
- [ ] AC13：Redis 确定性探针应证明连接和命令限时已配置、允许命令集合不扩大、连接失败与关闭失败安全收敛，且凭据不进入结果、日志与 Trace。
- [ ] AC14：当普通单测、后端全量测试或 CI 运行时，即使进程环境意外存在服务 DSN，也不得发生真实 DNS、socket、数据库、Redis、模型或其他外部访问。
- [ ] AC15：当真实测试入口缺少显式 opt-in、显式目标或凭据引用中的任一软件条件时，必须在访问前失败关闭并返回不含敏感信息的拒绝原因；本 AC 不把用户人工授权伪装成软件可自动证明的状态。
- [ ] AC16：新增套件必须包含多终止、终止后事件、未预期异常、Gateway timeout、运行中迟到敏感结果、排队超时后不得执行、只改 capability 声明和真实测试缺少技术前置等负向样例；所有测试自身通过，无新增 `skip`、`xfail` / `xpass`。
- [ ] AC17：P10 Runtime Adapter contract、ToolGateway contract、Run / 取消 / Trace / 固定动作回归和后端全量测试保持通过；合法 mock 行为的归一化双跑结果不变。
- [ ] AC18：机器边界门禁确认无迁移、无公开 API / OpenAPI / SSE、无前端、无新服务类型 / Connector / Tool、无依赖清单或 lockfile、无真实网络访问和无权限扩大。
- [ ] AC19：P10 zero-behavior baseline 的内容与生成器哈希保持不变；P11 使用独立、显式、最小的阶段变更声明替代 P10 固定禁改规则。重算 P10 baseline、删除其负向断言、使用全仓通配白名单或修改未经 P11 Design 批准的生产路径时，门禁必须失败。

## 边界与约束

- **事实源**：现有 Run 及其 Result、Message、RunEvent 仍是业务事实源；Runtime signal 和 Tool future 都不能覆盖已提交终态。
- **Runtime 边界**：本阶段只激活执行协议保护，不把 Adapter 变成业务 Orchestrator，也不让框架类型进入领域模型或公开 API。
- **Tool 边界**：所有工具继续只能经 ToolGateway 执行；Connector 不暴露给模型，Gateway 不把等待超时误当作外部事实。
- **只读边界**：P11 只覆盖既有调查 / 监控的只读路径；现有固定受控动作不迁移到新 timeout / dispatch 语义，也不得借本阶段扩大。
- **真实资源边界**：P11 只交付默认离线门禁。任何实际真实资源验证仍须再次确认目标、账号权限、数据边界、脱敏方式和清理范围。
- **扩范围处理**：若实现需要新迁移、公开接口、新 Connector、凭据方案、全局 deadline / cancellation、持久化执行状态或副作用处置，必须停止并另行立项，不能在 P11 Workpack 内追加。

## 完成定义（DoD）

- [ ] 全部 AC（AC1–AC19）通过，并在 Workpack evidence 中给出可重复执行的命令与结果。
- [ ] S1 Runtime 唯一终态与安全失败、S2 Tool / Connector 超时与真实验证前门禁全部完成，没有第三个隐含切片。
- [ ] P10 capability profile 已按真实行为升级版本；已解决与仍保留的 gap 都有行为探针和 Review 证据。
- [ ] 相关聚焦测试、P10 contract / regression 套件和后端全量测试全部通过，无新增 skip、xfail / xpass。
- [ ] 至少一个负向样例证明：仅修改能力声明、移除 gap 或放宽断言不能让门禁通过。
- [ ] `git diff --check`、敏感字面量扫描和范围门禁通过；无凭据、原始异常、SQL、Prompt、Tool 输出或真实目标数据进入 Git / 测试输出。
- [ ] 无数据库迁移、公开 API / OpenAPI / SSE、前端、依赖清单或 lockfile 变化；无新增服务、Connector、Tool、权限和真实外部访问。
- [ ] 实施 Design 已明确生产接线点、typed failure 映射、完整流校验方式、迟到 Tool 结果隔离、Connector 资源级超时证明和回退方案，并经独立 Review 与用户确认。

## 开放问题

本 PRD 暂无需要扩大产品范围的开放问题。以下实现选择由 Design 定稿，但不得改变本 PRD 的验收语义：

1. 最小生产保护采用兼容 Adapter、wrapper 还是演进现有 `DiagnosisExecutor` port；不得同时保留两条可写业务结果的生产路径。
2. Runtime 完整流校验如何在保留现有事件可见性的同时阻止终止后事件和多终止结果提交。
3. Tool 调用结果接纳 token / gate、线程池隔离与 Connector 资源释放的具体结构；不得宣称 Python 能强杀任意同步线程。
4. 真实测试 opt-in 的命令行 / marker 形态；软件门只证明技术前置已显式提供，不得把用户授权简化为仓库内永久开关、凭据值或自动化通过状态。

## GitHub Issue

- issue：[#121](https://github.com/wzhwwwzzzhhh/oper-mind/issues/121)。
- Issue 只覆盖本 PRD 的 S1–S2 与 AC1–AC19，不创建 P11 总 Issue 之外的重复子 Issue。
- 状态：PRD 已确认，Issue 已创建；当前下一步是实施 Design → 独立 Review → 用户确认，尚未创建 Workpack 或授权生产代码实施。
