# V2-B 主 Agent 与文本比较能力闭环 · Design

> 状态：已确认；独立 Review PASS 后，用户于 2026-10-15 明确确认第六节五项决策。工作包计划仍须另行确认。
> 更新：2026-10-19（确认状态与 Workpack 入口续核；设计决策未变）。
> 唯一需求：[已确认 PRD](PRD.md)，[Issue #133](https://github.com/wzhwwwzzzhhh/oper-mind/issues/133)。
> 基线：`main`，`6706caa88c3d73c9f29f65659e033e1c89926c65`。
> 依据：[产品定义](../../../事实源/产品定义.md)、[路线图](../../../事实源/路线图.md)、[开发规范](../../../事实源/开发规范.md)、[架构与开发路径](../../../事实源/架构与开发路径.md)、[准备-1](../准备/现状与复用盘点.md)、[准备-3 静态核查](../准备/候选兼容验证记录.md)。
> 本文只定架构和门禁；没有修改运行时、API、数据库、依赖或前端。候选运行兼容未验证，不宣称已采用成功。
> 独立审查：[Review 记录](Design-Review.md)；首审 1 项 P1／2 项 P2 已修订，独立定点复审 PASS；没有运行兼容结论。
> V2-0 归属：本文件是首个切片的执行设计；V2 的目标执行内核是 ReAct 循环，见 [计划骨架](../方向/计划骨架.md)。

## 1. 目标与范围

在既有会话 → Run → 受控执行 → 已校验交付 → 安全事件主脊上，接入主 Agent 与一项字面文本比较能力，不复制聊天／Run／审计控制面。

做什么：

- 主 Agent 交付直答、材料追问、一个文本能力结果；语义选择由结构化模型决策完成。
- 显式材料快照、版本、幂等、并发隔离、取消、结果接纳与最小会话 UI。
- 保留 V1 入口、历史结果、模型配置、聚合用量和固定动作边界。

明确不做：

- 商业业务、语义分析、文件／网络／数据库访问、新服务接入、任意技能加载或插件市场。
- 子 Agent 委派、独立主 Agent 协作、Task／Attempt 控制面、长期记忆、checkpoint 恢复或分布式调度。
- 全局 deadline、底层线程强杀、逐 Run 成本账本、完整前端重做。

本方案触及公开 API／OpenAPI、应用数据库迁移、编排与结果协议、安全投影，必须独立 Review → 用户确认。纯文本 Tool 不需要 Connector，不能为复用口号强造外部连接层。

## 2. 设计决策

### 2.1 运行组件与职责

拟复用当前 LangGraph `StateGraph`、BaseAgent、模型配置和 ToolGateway 接缝；不新增 `langchain`／`deepagents` 依赖，不直接套旧领域 ReAct 的自由文本终态。V2 的目标执行内核仍是 ReAct 循环，复用其受控工具执行机制，重新定义终态与交付契约。准备-3 给出依据及未验证项；这里是设计提案，激活须通过后续确定性验证。

调用关系如下；箭头表达职责，不是另一套可写状态机：

```text
正式会话输入
  → 既有 RunApplicationService（唯一受理／终态 writer）
  → 按已保存 runtime_kind 选择 typed RunExecutor
      ├─ diagnosis：桥接既有 DiagnosisExecutor／结果组装器
      └─ main_agent：每 Run 新建 MainAgent + LangGraph
          决策 → 校验 → [直答 | 追问 | Capability Workflow]
                                     → ToolGateway → TextCompareTool
                                     → 全量结果／出处校验 → 确定性交付
  → 有限流协议保护 → 同事务写交付／助手消息／终态／最终事件
  → 既有 REST／SSE／会话结果区
```

- `MainAgent` 继承 BaseAgent，保留 `run(str) -> str` 的可调用入口；正式适配器使用新增 typed `run_task(MainAgentTask) -> MainDelivery`。`run` 只将无材料输入包装成同一个 typed 路径并返回安全文案，不形成第二实现。禁用长期记忆，不调用旧标签抽取／领域 mock；可复用初始化、模型及工具收集职责，不继承旧终态判定。
- `MainAgentTask` 只含 run/session 身份、本次目标、冻结上下文、A/B 材料引用、能力及规则版本、允许工具和调用上限；无 Session、ORM、凭据、全局 Registry 或任意资源句柄。
- 图节点只返回工作状态；Agent、Tool 和图都不能写 Run、消息、结果或事件表。
- 一个后端静态注册的 `text.literal_compare@1` Capability：声明 typed 输入输出、规则 `literal-lines@1`、允许 Tool、完成／失败条件。Skill 是同包内可信的使用指引文本；Workflow 只组织这一个比较任务。首版没有通用包扫描器、市场或热加载。
- `TextCompareTool` 继承 Tool；构造时注入本 Run 冻结的材料映射。模型提出材料引用，程序经 Gateway 调用 Tool；不让模型重新提交“权威原文”。

### 2.2 执行端口演进，而非复制控制面

实际 gap：现有 `DiagnosisExecutor.stream(query, service_id)` 无法携带显式材料／规则版本；`DiagnosisExecutionResult` 不能表示非诊断交付。因此新增一条应用层 typed `RunExecutor.stream(RunExecutionInput)` 接缝是必要适配，而不是再建一个 Run 服务。

- 输入为带 `runtime_kind` 的封闭联合：`diagnosis` 包含原 query/service；`main_agent` 包含冻结 `MainAgentTask`。
- 输出为安全事件、typed 完成值或封闭安全失败；完成值只允许 legacy diagnosis 摘要或 `MainDelivery`，禁止隐式字典协议。
- `LegacyDiagnosisRunAdapter` 包装原执行器，原样保留 legacy query/service、事件投影和诊断组装语义；旧 port 继续给既有调用／测试使用，不给新能力强塞诊断字段。
- `RunApplicationService` 只注入这一组合执行端口；取消、受理、事件序号与提交仍用同一服务和数据库事务，不新增 MainRunService／后台事实队列。
- `runtime_safety.py` 提取可复用的有限流校验内核；保留 `guard_runtime_stream` 的既有签名、P10/P11 信号类型和失败映射，新 `guard_run_stream` 只包装新 typed 信号。不放宽未知对象、多终止或 EOF 要求，不修改历史 capability profile／fixture 的协议。
- 两种完成值都必须等正常 EOF 后才交付 writer；一旦收到后续输出，先前暂存结果作废。有限协议保护仍不能中断永不返回的 `next()`。

### 2.3 主 Agent 的最小决策图

本切片不是开放自治循环：一次模型决策，接一次必要能力流程，然后交付。这是为验证 Run 接缝做的有界实现；V2 的目标执行内核是 ReAct 循环（模型决策 → 受控工具 → 观察结果 → 再决策），在后续切片设计。图保留扩展接缝，但不预做复杂计划。

- 模型只看到可信能力说明、本次目标、A/B 是否提供及材料 ID，以及冻结的必要对话上下文；**不接收 A/B 原文**。字面对照无须模型阅读原文，原文中的指令也因此不会进入决策 Prompt。
- 模型完整响应必须是单个 JSON 对象，用严格 Pydantic 判别联合校验：`answer`（用户可见正文）、`needs_input`（缺失材料身份）、`invoke_capability`（能力 ID／版本、材料引用）。拒绝额外字段、多个决策、未知能力和不相符引用；整段 JSON 解析，不做正则提取、代码块剥离或关键词兜底。
- 追问的缺失集合由后端与实际快照对照；两份都存在时不得伪称材料缺失。模型提出已知比较能力但材料不足时，只转为固定材料追问，Tool 调用为零。
- `answer` 是普通模型回答，界面标“普通回答，未执行文本比较”；不是已校验差异，不能进入差异结果面板。材料比较交付只来自 Tool 的结构化事实。
- 比较完成后用确定性模板说明块类型与行号，不再调用模型概括，避免引入未被差异支撑的事实。首版正常路径恰好一次模型调用、比较路径一次 Tool；PRD 的 4 次模型上限是硬上限，不是必须调用 4 次。
- 无效决策／模型不可用安全失败，不重试、不回退 legacy、不切换 mock。预算对象每 Run 独立，调用前扣记；错误也计入尝试数。

必要对话上下文首版仅取受理时已经完成、未归档的 V2 普通回答／追问及对应目标，最多最近 4 条消息、合计 2000 个码点；不注入诊断报告、比较引文、未完成 Run 或其他会话。只选择能完整放入限额的消息，不截半段；按时间和 ID 稳定排序，将实际选中内容与来源 ID 一起冻结。后续完成的并发 Run 不改变已有上下文。模型回答仍可能出错，普通回答标签不表示事实核验。

### 2.4 输入快照、字面对照与接纳契约

输入 `MainInputV1`：`schema_version=1`、目标 query、可缺省的 `text_a/text_b`。字段缺失／null 表示未提供；显式空字符串表示提供了空文本。材料接纳时拒绝非法 Unicode 孤立代理码点，按原始 Unicode 码点数检查上限，随后仅统一换行编码。

- 每份原文 ≤2000 码点、规范化后 ≤100 行，query ≤200 码点。前端用码点数提示，后端是最终裁决，不用 JS UTF-16 长度当后端计数。
- 空字符串是 0 行；其他文本按 LF 分割并保留末尾空行，例如末尾换行属于一个可对照的空行。禁止 trim、大小写折叠或标点归一。
- `MainInputSnapshotV1` 保存原始输入、规范化文本、服务端生成材料 ID、`literal-lines@1` 版本、内容摘要和上述上下文。每个材料 ID 与 Run 绑定，不接受客户端指定跨 Run ID；摘要不出现在 Trace／审计。
- Tool 参数只有当前 A/B 材料引用与固定规则版本；严格校验后从本 Run 构造注入的映射取内容。没有磁盘／网络／历史查询能力。

比较使用 Python 标准库 `difflib.SequenceMatcher`，以完整行列表匹配，`autojunk=False`；按 opcode 顺序产生非 equal 的连续块，不识别 move。insert=新增、delete=删除、replace=修改；每个非 equal opcode 对应一个块，不另外合并跨 equal 的变化。相同输入与版本结果稳定，但不承诺唯一最短编辑序列。

`TextComparisonV1` 含 run/material 身份、能力与规则版本、`no_difference/has_difference`、块列表。每块为 `added/deleted/modified`，适用侧含 1 基闭区间、对应精确行数组和 LF 拼接引文；不适用侧为 null，界面写“无对应片段”。空行引用可以是空字符串，不等同于侧不存在。

接纳必须同时校验：

- 所有身份／版本与冻结输入完全一致；schema、行号、块数、类型与两侧适用关系合法。
- 引文逐字等于对应行切片；顺序、覆盖范围和完整块序列与后端对冻结输入重新求得的规范化结果一致，不能只验已返回的几个合法引用而漏掉其余差异。
- 无差异必须规范化文本相等且零块；有差异必须非零块。超过 50 块失败，不截断成成功。
- 重算用于接纳一致性，不宣称是独立算法正确性证明；正确性另靠手工可核对的确定性样例与负向测试。
- Gateway 脱敏若改变工具 JSON／引文，禁止拼回原文绕过 Gateway，也不能当成功；返回安全结果校验失败。入站拒绝规则降低这种概率，但不放松出站防线。

`MainDeliveryV1` 是封闭联合：普通回答、材料追问、已校验文本比较。Run `succeeded` 仅表示合法交付；只有第三种表示能力完成。失败／取消无交付；不生成任何提案。

### 2.5 模型、mock、配置与超时

- 沿用现有 Provider、mock/real 模式、参数与密钥解析；V2 的 main 使用现有主诊断模型配置，不新增模型角色配置或启用独立 judge。UI 说明该映射，不把名称复用误当多模型支持。
- `LLMClient` 增加向后兼容的可选超时／重试参数：legacy 默认保持原行为；V2 明确 `max_retries=0`、单次模型请求 timeout=30 秒。客户端超时不是服务器计算已停止的证明。
- V2 每次只用上述 JSON 决策，不依赖 Provider 额外的原生结构化输出 API；不符合 JSON 的 Provider 响应失败关闭。保留实际 usage 采集；没有 usage 就不造数，没有逐 Run 成本保证。
- `MainAgentModelAdapter` 是 V2 唯一模型决策边界：先调用既有客户端，再识别其 `error` 响应或调用异常，转换为 typed `ModelDecisionFailure`；只有明确调用成功才解析正文为 typed `ModelDecisionSuccess`。调用失败映射封闭的 `MODEL_UNAVAILABLE`，成功但 JSON／schema 无效映射 `MODEL_DECISION_INVALID`；均用固定安全文案、不携带原始响应／异常、不执行工具。Run 适配器把这两种失败转为对应安全失败信号，legacy 客户端及原失败映射不变。
- V2 ToolGateway 等待为 3 秒，超时关闭结果接纳；无法证明底层停止时保留 unknown。所有资源在 finally 中释放，线程池 shutdown 不等待未知阻塞执行。
- 新 V2 mock 为显式、封闭场景的决策替身；固定场景可执行真实确定性文本 Tool，但界面必须标 mock 模型。未声明场景返回不可用，不靠原文词汇选场景，不调用真实模型；不改 V1 `infer_mock_role` 白名单。
- 首版上述限额／timeout 是服务端版本化常量，暂不新增任意运行参数设置页。既有环境变量优先于 YAML；敏感值仍走批准的环境／加密 Key 路径，不新增敏感配置。

### 2.6 持久化与唯一 writer（需要迁移）

继续使用现有 `diagnosis_runs` 表与五态生命周期，不在此次批量改名。新增：

1. `diagnosis_runs.runtime_kind`：非空，`diagnosis/main_agent` 封闭值；迁移回填并默认 diagnosis。旧记录和旧调用不被解释成 main_agent。
2. `run_inputs`：`run_id` 主键、外键到 diagnosis_runs（RESTRICT），`schema_version`、typed JSON 快照。仅 main_agent 每 Run 一条；受理事务创建后不可覆盖，无单独编辑 API。
3. `run_deliveries`：同样以 run_id 为唯一主键／外键，schema_version、kind、typed JSON 交付、created_at。只在该 Run 成功事务写一次，不另存 status。legacy 仍只写 diagnosis_results。

这些是一套 Run 的 1:1 扩展，不是另一套任务主表。Pydantic 在读写边界严格解析，未知版本／损坏 JSON 安全失败，禁止猜测或套诊断默认值。跨表“只有对应 kind 的结果”由唯一 writer、事务与资源投影强制；不能把它描述成普通 CHECK 已保证跨表互斥。

- 受理事务：安全输入检查 → 会话 active 校验 → 幂等检查 → 用户消息（仅目标）→ Run → 冻结输入 → 幂等记录 → queued 事件。校验失败不留下消息／Run／输入残片。
- 幂等作用域继续为既有的 `(session_id, endpoint, idempotency_key)`，创建与 rerun 使用原各自 endpoint 常量，不新建另一套键库。diagnosis 创建严格保留 `_query_fingerprint(query, service_id)`，diagnosis rerun 严格保留 `_rerun_fingerprint(source_run_id, query, service_id)`；不加新字段重算、不重写历史键。升级前已保存的键仍按旧语义重放。
- main_agent 创建的摘要前像含固定版本标签 `main-agent-create@1`、runtime_kind、输入 schema、原始 query/A/B（区分缺失与空值），固定序列化后存 64 位十六进制 SHA-256，不往既有 64 字符列塞额外前缀。main_agent rerun 使用另一个版本标签 `main-agent-rerun@1`，必须纳入 **source_run_id**、原快照输入／规则版本；相同材料但不同来源不能被当成同一次重放。读取既有键时先核对关联 Run kind；请求 kind 不同直接冲突，不降级尝试另一公式。
- 同键同输入返回原 Run，不重新执行；不同输入／不同 rerun 来源冲突，不记录摘要到日志。上下文只在首次受理时选取，不参与后续同键重放重新计算；rerun 读取原冻结上下文，不重新采样历史。
- 执行从保存的输入读快照，不读取修改后的用户消息。认领仍是 queued→running CAS；不能重复认领。
- 成功事务：复核 running → 校验完整交付 → 写唯一 delivery／助手消息 → running→succeeded CAS → 最终事件，任一步失败整体回滚。CAS 失败不得遗留 delivery 或助手消息。
- 比较助手消息只存固定块数摘要，不复制原文；原文只在输入快照与 typed 比较结果持有。普通回答／追问正文属于会话交付，仍须出站凭据检查。
- cancel／failure 沿用既有 CAS 与终态不可覆盖规则。普通执行事件必须在同一事务通过带 `id=run_id AND status=running` 谓词的原子 UPDATE 增加 next_event_sequence 并返回序号，再写事件；不能采用“先 SELECT 状态再无条件预留序号”。未更新任何行表示接纳关闭，丢弃迟到事件并读取既有终态，不把它改成失败。该 UPDATE 与取消的状态 CAS 操作同一 Run 行：事件先胜则其提交在取消前，取消先胜则事件无序号可用。queued／started／最终事件仍只在各自成功受理／状态 CAS 的同事务预留和提交，不从普通执行事件通道追加终态。唯一序号与唯一结果约束不变。
- `rerun` 为新 Run 复制旧冻结目标／材料／上下文／规则版本，生成本 Run 材料 ID，保留 rerun_of；不从 UI 或最新消息取输入，不复制旧交付。指定规则已不可用则明确拒绝，不暗中升级；模型配置按重跑时有效配置解析。
- 应用数据库仍为已配置的应用元数据库，不借用户业务连接。迁移新增 revision 接当前 Alembic head，文件名在实施时确定；不自动启动迁移。

### 2.7 并发所有权

允许同会话／不同会话两个已受理 Run 交错执行，不新增“整会话锁”。历史上下文按受理时快照，而不是承诺两个任务具备串行因果。

- 每 Run 独立 Agent、模型客户端、Gateway／线程池、只读材料映射、图 State、调用计数和输出缓冲；不缓存闭包中的可变 Agent。框架 `thread_id` 只是关联标识，不当隔离机制。
- 只有 RunApplicationService 写事实，SSE 只读数据库事件；前端以 run_id＋sequence 合并并绑定结果，禁止“当前选中 Run”全局槽接纳所有事件。
- 取消只影响指定 Run；若取消先提交，后续成功／失败 CAS 不覆盖，不创建提案／第二终态。
- 不新增持久化调度或无限并发承诺；现有进程容量不足可显式拒绝受理。进程退出后的 queued/running 不自动恢复，仍保留既有 gap。

### 2.8 API／SSE 与 V1 兼容（需要公开契约变更）

继续 `/api/v1` 和现有 Run 路由，不新增文本比较专属端点／独立页面。

- `POST /sessions/{session_id}/runs` 扩展为带 discriminator 的请求联合：未提供 `runtime_kind` 时按原 diagnosis 请求处理，保持原 query4000/service_id 语义；显式 `main_agent` 接 query200、可缺省 A/B，不接受 service_id。V2 不自动继承会话服务、不调用 `requires_database_context`。
- 现有 Run 资源增加 runtime_kind、可空 delivery；原 result 继续只表示诊断结果。成功 diagnosis 必须 result 非空且 delivery 为空；成功 main_agent 相反；其他状态二者都为空。不得用空 diagnosis result 假装兼容。
- `GET /runs/{id}` 对 main_agent 增加 typed input_snapshot（对应输入展示区域）；全局／会话摘要列表不带 A/B 原文。历史诊断投影保留，无新客户端必须调用新业务 API 的要求。
- 沿用 cancel、rerun、事件列表和 SSE 路由；重跑识别保存的 runtime_kind。未知 kind／版本报安全不可用，不猜测。
- SSE 类型集合不增加；复用 agent_start/done、route_decided、tool_invoked 及生命周期事件，新增受控 main 角色／phase 枚举与安全状态字段。终态事件不携带交付／引文，前端终态后读取详情。
- OpenAPI、后端 schema／投影、前端生成类型、reader、MSW、SSE 解析同时演进；`generated.ts` 由 OpenAPI 生成，不手改。保留旧请求／旧记录可识别，不承诺未升级的第三方旧客户端能展示新结果类型。
- 无效 schema、非法 JSON、敏感输入错误使用固定 code/message 和允许字段名；错误响应、访问日志／异常日志不能回显输入值、请求体或原始 ValidationError。凭据接纳先于任何落库／模型调用，框架校验错误也走安全错误投影。

### 2.9 最小前端与当前事实源修订

继续现有会话工作台、会话管理和模型设置。会话内明确入口选择，不以 query 词汇决定链路：默认“主 Agent”，保留显式“服务调查（V1）”入口；后者仍使用原接口行为。服务页进入调查时明确选择 legacy，不将选服务视为 V2 的隐式资源授权。

主 Agent 输入显示 query 和可展开 A（旧）／B（新）两框；提供／未提供可独立切换，支持显式空文本。材料草稿只在内存中，不写 localStorage／发送意图持久缓存；幂等恢复以已受理 Run 为准，不缓存原文。材料追问后需用户再次显式提交 A/B，不从上一次 Run 自动借用材料。

结果区分别显示普通回答、追问、无差异／差异、失败、取消；文本结果显示材料标识、文字类型、行号／引文，源文只作为转义文本，不渲染为可执行 HTML，不把 URL 当自动访问指令。无诊断严重度、根因或审批按钮。旧结果仍走 DiagnosisResultPanel。

服务／模型／会话管理页保留；“最近调查”、安全审计和 Markdown 导出对 V2 只投影中性任务摘要／状态／块数，不带 query、原文或逐字差异。它们仍是只读投影，不另建业务管理模块。

Design 确认后需要同步的事实源口径 —— **已于 2026-10-19 同步完成**；以下保留为记录，不是待办（`产品定义.md` 的 V2 段、`架构与开发路径.md` 主脊条均已按此口径更新）：

- 产品定义增加“V1 当前能力保留；V2 建设以主 Agent 为基础、Capability 可组合的平台，首项为显式文本比较”的计划／当前状态分栏；不再把未来全部能力限定为 DevOps，但不宣称 V2 已启用。
- §2.2／§3 将多 Agent 从每问必经流程修订为可选组合；子 Agent 与独立主 Agent 协作是平行方向，均仍未启用。
- 路线图登记 V2-B 已确认需求、Design／实施状态，保留 V1 与 P12 AC14 暂停事实；最终启用必须跟随实际验收，不提前勾选。
- 架构路径中“必须 Tool＋Connector”“禁止任何新模式”的旧绝对表述补充适用范围：纯计算 Tool 无 Connector；runtime_kind 是同一 Run 的兼容 discriminator，不是新产品控制面。凭据规则按已批准加密存储口径修正，不推翻安全边界。

### 2.10 凭据接纳、安全投影与权限

不新建权限系统；唯一资源是本 Run 用户显式材料。只注册纯文本 Tool，不装配 DB／网络／文件／Shell；原文与模型输出都不能扩大菜单。

复用 Gateway 现有识别范围，在 query、A/B、待冻结上下文、模型普通回答中检查：

- 以字符 s、k、连字符组成前缀，后接至少 6 个字母／数字／下划线／连字符的密钥形态。
- password／passwd／pwd／token／secret／api_key 或 api-key 等现有凭据赋值形态（大小写不敏感，等号或冒号，非空值）。
- URI 中 `scheme://user:password@host` 的带口令段。

入站命中整体拒绝，不能静默脱敏后声称原文字面一致；回包不回显命中值。合成拒绝样例为上述密钥前缀拼接 `SYNTHETIC_ONLY_123`、`token = SYNTHETIC_VALUE`、`demo://user:NOT_A_SECRET@example.invalid`；全部为假值，测试不得使用真实凭据。规则不是完备敏感信息检测，UI 明示不要提交秘密；不把其误报／漏报隐瞒为普遍安全保证。

Trace／审计／usage 只允许固定字段：身份关联、受控角色／阶段／状态、耗时、工具类别及固定计数摘要。原文、逐字差异、query、模型正文／决策 JSON、Prompt、CoT、异常、输入摘要均不进入这些渠道。不启用框架自动上传 trace/checkpoint；SDK HTTP body debug 日志不得启用。

事件投影按 typed allowlist 重建，不接受 Tool `detail`／模型 summary 直接透传。原文和合法引文仅保留在输入／结果存储及对应会话区域；新错误／schema 投影不应复制这些数据。应用元数据库仍有内容隐私风险，本阶段不新增加密材料方案或用户／租户隔离承诺。

## 3. 文件改动面

以下为未来实施 Design 的明确边界，不是本轮实际改动。新增文件是拟定路径；migration 文件名由 dev-plan 核对单链 head 后确定。

- 新增 `backend/src/domain/main_agent.py`：输入／快照／差异／交付的严格 typed 模型及版本。
- 新增 `backend/src/application/run_execution.py`：唯一组合 RunExecutor 端口、封闭信号／输入联合；不引入第二 writer。
- 新增 `backend/src/infrastructure/agent_runtime/run_executor.py`：legacy bridge 和 main 执行适配；复用原 CoordinatorDiagnosisExecutor。
- 新增 `backend/src/agents/main_agent.py`、`backend/src/core/main_agent_graph.py`：BaseAgent 子类、bounded StateGraph、结构化决策／限额。
- 新增 `backend/src/core/main_agent_model.py`：MainAgentModelAdapter 与 typed 成功／失败边界，调用失败先于 JSON 解析处理。
- 新增 `backend/src/capabilities/text_compare.py`、`backend/src/tools/text_compare.py`：单能力定义／Workflow／Skill 指引、纯计算 Tool、规范结果与校验。
- 新增 `backend/src/infrastructure/persistence/run_delivery_repository.py`；修改 `models.py`、`repositories.py`、`backend/src/domain/records.py`：Run kind、快照与交付读写。新增一条 `backend/migrations/versions/` revision，仅上述列／两表，不改服务／凭据表。
- 修改 `backend/src/application/services.py`、`runtime_safety.py`：受理／认领／提交／取消／rerun／有限流安全适配；保留 `contracts.py`、`runtime_contracts.py` 历史公开契约。
- 修改 `backend/src/core/llm.py`、`backend/src/api/v1/dependencies.py`：V2 客户端／mock／每 Run 装配与显式 timeout／无重试；不放宽 `core/mock_runtime.py`。
- 新增 `backend/src/core/input_admission.py`，修改 `backend/src/core/tool_gateway.py` 仅提供共用规则的纯检测接缝：不复制漂移的检测清单，Gateway 出站规则保持原覆盖范围，不放宽白名单。
- 修改 `backend/src/api/v1/schemas.py`、`resources.py`、`routes.py`、`errors.py`，必要的 `backend/src/app.py` 校验异常投影：请求／资源联合、安全错误、既有路由兼容，不新增业务路由。
- 修改 `backend/src/application/audit_service.py`、`session_export.py` 及 `backend/src/infrastructure/persistence/audit_repositories.py`：V2 中性投影，不将原文送进审计／导出。
- 修改 `frontend/src/api/v1/client.ts`、`queries.ts`，重新生成 `generated.ts`：typed 请求／详情／交付。
- 修改 `frontend/src/features/workbench/WorkbenchPage.tsx`、`send-intent.ts`、`run-events.ts`、`TraceCard.tsx`、`resource-readers.ts`、`conversation-turns.ts`；新增 `MainAgentComposer.tsx`、`MainDeliveryPanel.tsx`、`main-delivery-readers.ts`：双材料录入、按 Run 展示／恢复、无原文持久草稿。
- 修改 `frontend/src/test/handlers.ts`；新增后端 `test_main_agent_runtime.py`、`test_text_compare.py`、`test_main_agent_runs_api.py` 及前端 `main-agent.test.tsx`／`main-delivery.test.tsx`；相关既有取消／重跑／安全／迁移测试由 Workpack 精确列出。
- 同步三份事实源及 `docs/事实源/架构与开发路径.md` 的上述修订口径；不改写 V1 历史基线或宣称未验收能力启用。

无功能改动：服务／Connector／监控／动作执行器／模型凭据方案、P10 历史 fixture、依赖清单、完整管理后台。若落地发现清单外的真实接缝，先补 Design 说明，不能以“相关文件”扩大实现范围。

## 4. 切片与验证（指引，不写死）

建议 Workpack 保持 1–3 个紧密切片，围绕“typed 受理与存储”“主 Agent＋能力接纳”“会话可见与兼容”组织；具体文件顺序、测试命令与提交计划属于 dev-plan，不在此批准。

必须证明的验收语义：

- 正常／缺材料／空文本／无差异／连续块／末尾换行／重复行的可核对字面对照；无效模型、超限、伪造／漏报引文失败关闭。
- 实际模型尝试和 SDK 无重试；显式 mock、缺 usage 的诚实统计；Gateway 不可绕过、没有额外资源工具。
- 同会话与跨会话交错、同键重放／冲突、升级前 diagnosis 幂等键重放、相同材料但不同来源的 rerun 键冲突、rerun 使用快照、取消胜出与迟到事件／结果、有限流协议负向。
- 材料在接纳前拒绝凭据形态；Trace／日志／审计／导出／usage 零原文泄漏；API schema 错误不回显输入。
- 迁移前 V1 旧数据、API、模型设置、诊断结果、取消／重跑和动作边界；迁移 upgrade／受限 downgrade；前端交互和刷新／重连。

不改变 P10/P11 冻结基线去迁就新路径；新路径有独立画像和证据。真实 Provider／业务服务测试不属于默认离线验证，仍需当次明确授权。

## 5. 风险、回滚与门禁

- **兼容风险**：Run 资源与生产端口演进有面，不是“只改服务接入”。保留 legacy bridge、旧 schema 语义及契约基线；无法证明兼容则不激活主 Agent 默认入口。
- **材料隐私**：原文需要持久化才可刷新恢复，不能声称没有保存文本。只限对应输入／结果投影；无登录体系不适合直接暴露到多人公网环境。
- **模型风险**：JSON 失败率／普通回答幻觉不能靠 schema 消除；错误失败关闭，比较事实不用模型生成。没有性能测量前不承诺“更快更准”。
- **控制风险**：模型／工具 timeout 只能关闭等待或接纳，不能证明远端／同步线程停止；保留全局 deadline 和崩溃恢复 gap。
- **算法风险**：行级对齐不等于语义差异或唯一最短 diff；规则版本与手工 oracle 让结果可复验，不扩范围。

回滚：

1. 先停止接纳新的 main_agent Run，并让前端恢复显式 legacy 入口；后端仍保留读取既有 main 数据的投影，不删除用户文本。
2. 新列／扩展表是增量结构，优先保留。迁移 downgrade 在存在 main_agent Run／快照／交付时必须拒绝，不能自动 DROP 丢数据；只有空扩展数据且无 main Run 时才允许回到旧 schema。
3. 完全回退旧应用版本前需确认旧版不会把 main 成功 Run 当成缺失诊断结果；默认不支持直接滚回未识别 kind 的旧二进制。数据保留导出／清理另需授权，不能为回滚擅自删除。

开始门：已确认 PRD（已满足）→ 独立 Design Review（已 PASS）→ 用户确认 Design（已满足）→ 正式 Workpack／计划确认／隔离工作区 → 实施验证。准备-3 静态核查、Review PASS 或 Issue 创建都不等于代码通过。

## 6. 用户已确认的设计决策

以下五项已于 2026-10-15 由用户在独立 Review PASS 后统一确认；不是代码验收结论。

1. 首闭环沿现有 LangGraph 做最小 bounded 主 Agent 图，不引入新框架；一次结构化模型决策，字面比较与解释由确定性程序交付。
2. 继续同一会话／Run 主脊，新增 runtime_kind 与两张 1:1 输入／交付扩展表，保留旧诊断结果，不用根因字段承载文本结果；这需要迁移与公开 schema 演进。
3. 会话的最终默认入口是主 Agent；V2-0 期间保持 V1 服务调查默认、V2 显式切换，V2-2 首批只读调查对等并经用户确认后再切默认。V2 不自动继承服务或旧材料，重跑用冻结快照。正文仅在指定输入／结果区域可见，不持久化浏览器材料草稿。
4. 本切片采用本文的行级对照规则、固定模型 30 秒／工具等待 3 秒、无重试、必要上下文快照和凭据接纳范围；不承诺强制停止／自动恢复。
5. Design 获确认后按 §2.9 修订事实源的 V1／V2 状态表达；实施完成前始终标 V2 未启用。子 Agent 与独立主 Agent 两个平行维度继续后置，不删掉多 Agent 方向。

### 6.1 V2-0 收口补充裁决（2026-10-26）

1. 失败码拆为 `MAIN_AGENT_MODEL_UNAVAILABLE`、`MAIN_AGENT_DECISION_INVALID`、`MAIN_AGENT_CAPABILITY_UNAVAILABLE`、`MAIN_AGENT_TOOL_FAILED`，保留 `MAIN_AGENT_FAILED` 兜底。
2. 交付／冻结输入读取失败不再抛 500；列表和详情返回 `main_delivery_status` / `main_input_status`，损坏行标记 `unavailable`，不带原文或异常。
3. 默认入口按第 3 条执行：V1 默认，V2 显式。
