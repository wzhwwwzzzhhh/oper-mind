---
title: P12：PostgreSQL、Redis 与 MySQL 真实只读接入
status: 已确认
domain: service-center
phase: P12
issue: 124
updated: 2026-09-04
---

# P12 PostgreSQL、Redis 与 MySQL 真实只读接入 · PRD

## 背景

P11 已完成 Agent Harness 真实运行安全门，运行时唯一终态、安全失败、Tool 等待超时与迟到结果隔离、既有 PostgreSQL / Redis Connector 的资源级超时证明、默认离线测试和真实验证软件前门均已有机器证据。下一步不继续补齐全部 Harness，而是让现有服务接入骨架真正承载非生产真实服务调查。

当前仓库并非从零开始：

- 服务中心已具备动态注册、DSN 加密落库、掩码展示、编辑/移除、连接测试、`ServiceConnector`、`ServiceRegistry`、监控采样、服务会话和 Run 服务上下文；
- PostgreSQL 已有服务 Connector 和 DBAgent 只读工具，但动态注册服务的加密 DSN 只进入 Connector，DBAgent 工具仍通过环境变量读取 DSN，可能出现“服务中心已接入、Agent 却认为未配置”的双轨状态；
- Redis 已有 Connector、连接测试和内存/连接数/慢日志监控，但 `supported_investigations` 为空，真实事实尚不能由 Agent 调查；
- MySQL 只有产品与展示预留，当前 API、应用白名单和前端表单均拒绝注册，尚无驱动、Connector、受控 Tool 或真实调查链。

用户已确认可提供以下非生产验证环境：本机 MySQL、远端 PostgreSQL、远端 Redis；三个目标均可创建专用只读账号。具体地址、端口、数据库、用户名和凭据不进入本 PRD、Git、日志、Trace、截图或测试夹具。真实访问仍须在实施完成后逐目标获得用户当次明确授权。

关联依据：

- `docs/产品定义.md` §2–§5：服务中心是正式模块，所有外部访问必须经受控 Connector / Tool，并具备参数校验、权限边界、超时、脱敏和审计摘要。
- `docs/开发规范.md` §3–§6：新增 Connector、真实连接、凭据和权限必须先 Design → Review → 用户确认；普通测试使用确定性 mock，真实资源测试必须单独授权。
- `docs/prd/service-center/P8-service-registration.md`：动态服务注册、加密 DSN、连接测试和运行时 Registry 已交付。
- `docs/prd/agent-runtime/P11-harness-real-runtime-safety-gate.md`：默认离线、typed failure、迟到结果隔离与真实验证软件前门已交付，但没有实际访问真实资源。

## 目标

1. 统一服务中心 Connector 与 Agent Tool 的服务绑定事实，使动态注册和环境变量声明的服务都通过同一受控内部端口解析，杜绝 UI 已接入但 Agent 读不到同一目标的双轨状态。
2. 让 PostgreSQL、Redis、MySQL 都达到同一最小真实接入标准：可注册、可安全保存凭据、可测试连接、可读取有限健康事实、可从服务会话发起一次受控只读调查，并形成安全 Trace 与结果留痕。
3. 三类服务只交付有限、类型明确、参数受控的只读事实；不把模型变成任意 SQL、Redis 命令或网络客户端。
4. 普通单测、全量测试和 CI 继续完全离线；最终只在用户逐目标授权后，对三个非生产目标执行一次可审计的真实端到端验收。
5. 将模型 Provider 模式与服务事实来源模式明确解耦：选择 mock、确定性本地驱动或真实模型，不得隐式开启、关闭或替换真实服务访问；真实服务验收不以调用外部模型 Provider 为前提。

## 用户故事

- 作为运维用户，我从服务中心添加 PostgreSQL、Redis 或 MySQL 后，希望“连接测试成功”与“会话中的 Agent 能读取同一服务”表达同一个真实目标，而不是两套互不相通的配置。
- 作为调查用户，我希望对任一已接入服务发起健康调查，得到来源明确、结构化、有限且脱敏的真实事实，以及不可用时诚实的降级结论。
- 作为安全评审者，我希望模型只能选择代码注册的只读能力，不能提交任意 SQL、Redis 命令、凭据、主机地址或跨服务目标。
- 作为开发者，我希望三个 Connector 共享 Harness 的超时、失败、Trace、测试和真实验收门，而不是为每种服务复制一套不一致的执行协议。

## 统一完成标准

一个服务类型只有同时满足以下链路，才算 P12“已接入”：

```text
服务中心添加服务
→ DSN 安全保存并注册 Connector
→ 显式连接测试得到真实状态
→ 从该服务创建或绑定会话
→ Run 精确绑定同一 service_id
→ Agent 通过受控只读 Tool 读取有限真实事实
→ 生成安全 Trace、回答与活动留痕
```

只有服务卡片、连接测试或监控快照，不等于 Agent 调查已接入；只有 Tool 单测，不等于真实端到端已验收。

## 范围

P12 是一个 PRD、一个 Issue、一个 active Workpack，最多包含以下三个顺序切片。S2、S3 必须复用 S1 建立的共同服务绑定边界，不得分别绕回环境变量或自行解密凭据。

### S1. 统一服务绑定与 PostgreSQL 端到端接线

- 建立一个后端内部、typed、按 `service_id` 精确解析的服务绑定端口；具体由 Registry、Connector capability 或其他结构承载，由 Design 决定。
- 动态注册的加密 DSN 只允许在受信后端的装配 / capability 边界解密；P12 沿用现有 Connector 可在后端进程内持有连接配置的生命周期，不强制新建 credential lease。原始 DSN 不得越过该受信边界进入 Agent、模型、Tool 参数、Prompt、Run、事件、结果、日志、异常或公开 API。
- 保留现有 `OPERMIND_SERVICE_<ID>_DSN` 静态实例兼容，但动态注册与静态实例必须收敛到同一读取语义，不能让 DBAgent 直接拥有任意凭据查询能力。
- 复用 PostgreSQL 现有只读 Connector 和 DBAgent 工具能力，完成服务中心 → 会话 → Run → Tool → 真实事实 → 安全结果的单目标链路。
- P12 不扩大 PostgreSQL 任意查询能力；真实验收只使用 Design 固定的安全调查输入和既有只读边界。

### S2. Redis 最小 Agent 只读调查

- 复用 `RedisServiceConnector` 已有 `PING`、`INFO memory`、`CLIENT LIST` 数量和 `SLOWLOG LEN` 能力，形成一个“Redis 健康与压力概览”调查入口。
- Agent 只能获得结构化标量与受控状态：可用性、内存字节数、客户端连接数、慢日志条数和观测时间。
- 禁止读取键名、键值、业务数据、原始慢日志正文、配置正文或任意 Redis 命令；禁止 `SCAN`、`KEYS`、`GET`、`MGET`、`EVAL`、`CONFIG`、`SET`、`DEL`、`FLUSH*` 等能力。
- Redis 不可用、未配置、超时或权限不足时，返回 typed unavailable / not-configured 事实，不伪造健康值或底层已中止。

### S3. MySQL 最小真实只读接入

- 将 `mysql` 纳入动态注册白名单、Connector Factory、前端服务类型和类型能力声明；新增成熟、固定版本的 MySQL 驱动依赖。
- 新增 MySQL 只读 Connector，支持 DSN 方案校验、短连接/命令超时、连接测试和有限健康快照。
- 首版只允许代码固定的健康与连接压力读取，例如连通性、运行时长、当前/运行中连接数、最大连接数、慢查询计数；最终字段和最低账号权限由 Design 定稿。
- 不接受模型生成 SQL，不读取表数据、库表内容、原始 PROCESSLIST SQL、用户信息或配置全文，不执行 DDL、DML、事务控制、kill、flush、set 或管理命令。
- MySQL 使用与 PostgreSQL / Redis 相同的服务绑定、ToolGateway、typed failure、Trace 和真实验收门。

### 不做什么（明确排除）

- 不连接任何生产目标；不把“目前未上生产”等同于免授权，远端非生产服务仍需当次明确授权。
- 不在开发、普通测试、CI、Review 或 Reader Test 中连接、探测、读取、写入或清理真实目标。
- 不新增任意 SQL Tool、通用 Redis 命令执行器、Shell、网络请求工具或模型可编辑连接参数。
- 不读取 PostgreSQL / MySQL 业务表数据，不读取 Redis 键空间或键值，不展示原始 SQL、原始慢日志、原始异常或凭据。
- 不实现写操作、索引创建、配置修改、kill session、缓存清理、故障修复或自动审批；既有受控 PostgreSQL 靶场动作不扩展到本阶段目标。
- 不接入 Prometheus、Loki、Kubernetes、Kafka、RabbitMQ、OpenSearch 或其他新服务类型。
- 不建设 Task / Attempt、Recovery、跨进程取消、全局 Run deadline、长期记忆或新的多 Agent 框架。
- 不新增后台自动真实探测；连接测试和调查只能由用户显式触发，既有监控采样是否读取动态服务维持当前产品行为，不在 P12 扩张。

## 功能需求

### 1. 服务绑定唯一性

- **输入**：已注册 `service_id`、服务类型和受控调用能力。
- **行为**：运行时从唯一服务事实源解析目标与 capability；Connector / Tool 必须验证服务存在、类型匹配、调用能力属于该类型且目标未被替换。
- **输出**：一个不包含凭据正文的 typed binding，或安全的 not-found / type-mismatch / credential-unavailable 失败。

### 2. 凭据与连接生命周期

- **输入**：动态注册的加密 DSN，或兼容保留的实例命名空间环境变量。
- **行为**：只在受信后端装配 / capability 边界解析；允许沿用现有 Connector 在后端进程生命周期内持有连接配置，但不得向 Agent、模型或 Tool 参数暴露。每次外部调用有连接与操作超时，结束后释放连接资源；失败和 cleanup 失败不得泄漏连接信息。
- **输出**：有限事实或 typed failure；不返回完整 DSN、可还原的连接目标、username、password、密文、nonce 或环境变量名。公开服务安全视图继续只允许既有 `has_dsn` 与有限掩码尾号。

### 3. 三服务统一调查入口

- **输入**：绑定一个 PostgreSQL、Redis 或 MySQL 服务的会话与用户健康调查请求。
- **行为**：Coordinator 只路由到服务类型允许的 Tool；Tool 从绑定服务读取类型限定事实；跨服务会话中的数据库调查仍要求用户显式选择单一目标。
- **输出**：真实来源、观测状态和安全摘要明确的回答；RunEvent 只保留角色、工具类别、状态、耗时和 service_id。

### 4. 模型模式与服务事实源正交

- **输入**：模型 Provider 模式、显式绑定的 `service_id` 与明确选择的服务事实来源。
- **行为**：模型模式只决定推理来源，服务目标与访问能力只由显式 binding、capability 和授权边界决定；不得再把 API Key、模型 mock 开关或全局评测场景当作生产服务事实源选择器。普通自动化仍显式注入 deterministic fake；真实服务验收使用确定性本地 scripted model / driver 触发既定调查链，不调用外部模型 Provider。若另做真实模型交互验收，必须把它视为额外外部目标并单独获得 Provider 访问授权。
- **输出**：证据分别标明模型来源与服务事实来源；任何 fake / scenario 事实都不得标为真实服务结果。

### 5. 默认离线与真实验收

- **输入**：普通测试/CI，或最终真实验收请求。
- **行为**：普通 pytest 路径继续由既有 collection-time blocker 和 deterministic fake 保持离线，不得增加解锁 marker、逃生开关或弱化 `tests/conftest.py`。P12 真实验收必须通过不参与 pytest 收集的独立人工 Runner 执行，并先调用 P12 专用 preflight；Runner 必须同时获得显式 opt-in、目标、凭据引用、用户当次授权、只读账号和脱敏边界，缺一项即在访问前失败关闭。
- **输出**：自动化证据与真实验收证据分开记录；preflight 只表达技术前置是否满足，不执行外部访问，也不能被描述为已获得人工授权。实际 Runner 证据只保留脱敏的步骤状态、时间与结果类别。

## 非功能需求

- **安全**：最小权限、最小披露、服务类型白名单、能力白名单、目标绑定、参数校验、连接/操作超时、脱敏和安全审计摘要全部不可绕过。
- **诚实性**：连接测试、监控快照和 Agent 调查分别记录其实际结果；不把连接可达描述为调查完成，不把 Gateway timeout 描述为底层已停止。
- **确定性**：三服务的成功、未配置、不可用、超时、权限不足、类型不匹配和脱敏场景均先由 fake 稳定覆盖。
- **隔离性**：一个服务失败不得影响其他服务；一次 Run 只能读取显式绑定的目标，禁止凭据或结果跨 service_id 串用。
- **兼容性**：现有 PostgreSQL/Redis 服务中心、监控、动态注册、静态环境变量实例、mock 评测、公开 API 和前端现有行为保持兼容。
- **可维护性**：服务差异封装在 Connector / capability 内，共同绑定、Gateway、失败和 Trace 协议不得按服务复制分叉。

## 数据与接口影响

- **应用数据**：原则上复用现有 `service_registry`、Session、Run、Result、Message、RunEvent 和监控样本；若 Design 发现 MySQL 类型需要数据库迁移，必须停止并单独说明，不能把迁移作为默认事实。
- **公开 API**：复用现有服务 CRUD、连接测试、会话、Run 和 SSE；`mysql` 成为已有 `kind` 字段的新合法值，OpenAPI 与前端生成类型可能产生兼容性扩展。
- **依赖**：允许新增一个 Design 明确选定并锁定版本的 MySQL 客户端驱动；不得同时引入多个 MySQL 驱动或完整 ORM 抽象层。
- **配置**：不新增明文凭据文件。动态 DSN 继续加密落库；静态实例继续兼容 `OPERMIND_SERVICE_<ID>_DSN`。
- **真实环境**：最终目标为用户确认的本机 MySQL、远端非生产 PostgreSQL 和远端非生产 Redis；具体连接信息仅在用户本机注入。

## 验收标准

- [ ] AC1：动态注册 PostgreSQL 后，连接测试与 DBAgent Tool 必须解析同一个 service_id 和同一受控凭据来源；不再要求为同一动态服务额外配置环境变量。
- [ ] AC2：既有环境变量声明的 PostgreSQL / Redis 静态实例继续可用，且与动态实例共享相同的 Tool / Connector 绑定语义。
- [ ] AC3：任一 Tool 请求不存在、类型不匹配或不属于会话的 service_id 时，必须在外部访问前失败关闭，不回退到默认目标。
- [ ] AC4：PostgreSQL 受控真实调查能从服务会话创建 Run，调用既有只读能力，写入唯一终态、安全 Trace 和真实来源结果；不得扩大任意 SQL 或写权限。
- [ ] AC5：Redis 服务声明一个最小健康调查能力；Agent 结果只包含可用性、内存、连接数、慢日志计数和观测状态，不包含键名、键值、业务数据或原始慢日志。
- [ ] AC6：Redis Tool 的行为探针证明只调用固定的 `PING`、`INFO memory`、`CLIENT LIST` 和 `SLOWLOG LEN`；删除命令白名单或加入任意命令时门禁失败。
- [ ] AC7：MySQL 可通过现有服务中心表单/API 动态注册、编辑、移除和测试连接；安全视图不返回 DSN 明文。
- [ ] AC8：MySQL Connector 对合法 DSN 建立有连接/操作超时的短生命周期连接；未配置、不可达、超时、权限不足和 cleanup 失败均安全收敛。
- [ ] AC9：MySQL 最小调查只返回 Design 固定的健康与连接压力标量；模型不能提供 SQL、命令名、连接参数、库名或凭据作为 Tool 参数。
- [ ] AC10：PostgreSQL、Redis、MySQL 三类调查都经现有 ToolGateway 和 P11 结果接纳语义；迟到结果、异常和审计摘要不得形成第二结果或泄漏事实。
- [ ] AC11：三类服务的完整 DSN、可还原连接目标、username、password、密文、nonce、原始异常和目标数据均不得进入日志、Trace、RunEvent、Result、Message、API 响应、截图或测试输出；API 只保留既有 `has_dsn` 与有限掩码尾号。
- [ ] AC12：普通测试、后端全量测试和 CI 即使存在真实 DSN 环境变量，也不得执行 DNS、socket、数据库、Redis、模型或其他外部访问。
- [ ] AC13：P12 专用 preflight 缺少 opt-in、目标或凭据引用中的任一项时，必须在访问前失败关闭；它必须复用动态服务注册的唯一 `service_id` validator 与 64 字符上限，正向覆盖数字开头、点号和下划线等现有合法 ID，负向覆盖空值、大写、非法字符和超长 ID，不得直接复用或复制更窄的 P11 正则。软件条件全部满足也只能表达“技术前置满足、尚未访问”，用户当次授权仍由实际 Runner 前独立确认，软件门不得伪造或持久化授权状态。
- [ ] AC14：用户逐目标授权后，本机 MySQL、远端非生产 PostgreSQL、远端非生产 Redis 各通过独立的非 pytest 人工 Runner 完成一次“连接测试 → 服务会话 → Run → 受控 Tool → 安全结果”的真实验收；Runner 使用确定性本地 scripted model / driver 驱动真实 Agent / Tool / Connector 链，不依赖外部模型 Provider，证据只记录脱敏状态和时间，不记录目标数据。若追加真实模型验收，必须另行确认 Provider 授权。
- [ ] AC15：相关后端单元/API 测试、P10/P11 contract 与行为回归、后端全量、前端 typecheck/test/build 和 `git diff --check` 全部通过，无新增 skip、xfail / xpass；P10/P11 阶段 exact-path 门按其历史交付树复验，P12 另建自己的阶段边界门，不放宽或重算历史门禁。
- [ ] AC16：机器边界门证明没有生产目标、写能力、任意 SQL/命令、额外服务类型、高风险动作、凭据泄漏或未经 Design 批准的迁移/API 扩张。
- [ ] AC17：Redis 与 MySQL 的服务类型 capability 均声明非空、类型正确的 `supported_investigations`，并由服务 API 的安全投影返回；服务中心对已配置目标展示可用的“发起调查”入口，选择后创建的 Session / Run 使用对应调查 intent 并精确绑定当前卡片的 `service_id`。未启用能力必须明确显示“未启用”，不得出现按钮可点但后端无法路由的半接入状态。
- [ ] AC18：模型模式与服务事实源正交探针证明，切换 mock / real 模型配置不会隐式改变服务访问目标或把真实 binding 替换为 scenario fake；注册的真实 binding 可由确定性本地驱动完成真实服务链路，同时普通自动化继续显式使用 fake 且保持完全离线。

## 完成定义（DoD）

- [ ] AC1–AC18 全部通过，并在唯一 Workpack evidence 中按 S1–S3 给出可重复的离线命令、结果和真实验收安全摘要。
- [ ] 三个服务均满足统一完成标准，不允许以“仅连接测试”或“仅 Connector 单测”替代 Agent 端到端调查。
- [ ] S1 共同服务绑定先完成并由 S2/S3 复用，没有三套独立凭据解析或目标选择实现。
- [ ] MySQL 驱动、Connector、Redis 最小调查和 PostgreSQL 动态凭据接线均有成功与负向测试。
- [ ] 普通自动化全程离线，既有 pytest collection-time blocker 保持不变；真实验收仅在用户明确授权后通过 P12 专用 preflight 与独立非 pytest Runner 人工运行，自动化、preflight、真实访问三类证据严格分离。
- [ ] Workpack evidence 分别标明模型来源与服务事实来源；确定性本地驱动的真实服务验收不伪装成真实模型调用，额外的真实模型验收也不复用服务授权。
- [ ] 无凭据、连接信息、原始异常、原始 SQL、Redis 键/值、业务表数据或远端目标数据进入 Git 与公开投影。
- [ ] 实施 Design 已明确绑定端口、能力模型、三类只读事实、账号最小权限、超时、cleanup、真实验收命令和回退方案，并经独立 Review 与用户确认。
- [ ] P12 Workpack 已归档，Issue 已关闭，PR 已合入 `main`；路线图、PRD 索引和保留 gap 同步完成。

## 待确认决策

1. 三类服务首个统一调查名称与用户问题。建议统一为“服务健康与连接压力概览”，由类型 capability 决定实际事实字段。
2. MySQL 首版固定指标与最小账号权限。建议只做连通性、运行时长、当前/运行中连接数、最大连接数和慢查询计数，不读取 PROCESSLIST SQL 或业务表。
3. Agent 组织方式。Design 决定复用 DBAgent、增加缓存角色，或增加内部 capability adapter；不得改变统一完成标准或形成第二业务事实源。
4. 真实验收 Runner 的具体命令与凭据注入形态由 Design 定稿；必须采用 P12 专用 preflight、独立非 pytest 人工 Runner 和确定性本地 scripted model / driver。建议优先使用服务中心加密 DSN；环境变量只用于既有静态实例兼容和可恢复回退。

## GitHub Issue

- issue：[#124](https://github.com/wzhwwwzzzhhh/oper-mind/issues/124)。
- Issue 只覆盖 S1–S3 与 AC1–AC18，不拆重复子 Issue，不把 Prometheus、Loki、Kubernetes 或写操作纳入 P12。
