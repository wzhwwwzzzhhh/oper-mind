# V2-1 单主 Agent 地基 · Design

> 状态：已确认（2026-10-26，用户确认；arch-review 三轮后 PASS，P0/P1=0）
> 更新：2026-10-26
> 关联：[V2-1 PRD](../../prd/agent-runtime/V2-1-main-agent-foundation.md)（已确认，Issue #137）；[计划骨架](../../进行中/V2-主Agent闭环/方向/计划骨架.md)；[V2-0 首闭环 Design](../../进行中/V2-主Agent闭环/首闭环/Design.md)；[产品定义](../../事实源/产品定义.md)、[路线图](../../事实源/路线图.md)、[开发规范](../../事实源/开发规范.md)、[架构与开发路径](../../事实源/架构与开发路径.md)。
> 关键代码：`backend/src/capabilities/`、`core/main_agent_graph.py`、`core/main_agent_model.py`、`agents/main_agent.py`、`infrastructure/agent_runtime/run_executor.py`、`application/run_execution.py`、`application/services.py`、`application/runtime_safety.py`、`api/v1/{dependencies,routes,schemas,resources}.py`、`frontend/src/features/workbench/`。
> 本文只定架构；切片、验证命令与提交计划归 dev-plan。没有修改运行时、API、数据库、依赖或前端。

## 1. 目标与范围

一句话：把 V2-0 的“单能力、一次决策”换成**一份通用 Capability 契约 + 一个有界 ReAct 循环**，并在同一套选择／校验／观察／交付路径上跑通一条知识型链路（只读排查手册）与一条执行型链路（文本比较回归）。

做什么（对齐 PRD 范围）：

- **Capability 契约 v1**：在现有 `CapabilityDefinition` 上补齐类型、输入／输出契约、资源与权限、完成与失败语义、知识型能力的内置 Skill 来源与版本；注册表仍是进程内显式注册 + 按 `capability_id + version` 解析，未知／重复／类型不符安全失败。
- **ReAct 主循环**：每步一次结构化模型决策；决策覆盖普通回答、材料追问、加载知识型能力、调用执行型能力；观察结果以 typed 安全摘要回到模型；循环由程序预算独占控制。
- **知识型能力** `ops.readonly_playbook@1`：装一份仓库内受管的只读排查手册，选中后由程序装入上下文，不调用任何工具。
- **执行型能力** `text.literal_compare@1` 迁移到通用契约，行为不变，作为回归样本。
- **交付与展示**：公开交付区分普通回答、知识辅助回答、材料追问、已校验比较；Run 资源以加法方式暴露能力身份、步骤摘要、知识接地与不可用能力；界面显示能力、步骤与终态。
- **回归**：V2-0 的比较、取消、重跑、幂等、安全投影、损坏行投影与 V1 默认入口全部保持。

明确不做（与 PRD「不做什么」一致，Design 额外钉死几条）：

- 不做子 Agent、多主 Agent、Task／Attempt、长期记忆、Recovery、分布式调度、跨进程通信。
- 不接真实模型、数据库、Redis、日志或网络；手册是仓库内静态受管内容，**不是检索，也不是实时数据**。
- 不做 RAG／Embedding／MCP／插件市场／任意技能目录／用户自定义代码／热加载；**Skill 只允许内置（`builtin`）来源，其他来源不进入契约**，为后续阶段留位但不实现。
- 不新增服务类型、Connector、凭据方案、权限模型、审批动作或高风险执行。
- 不切换默认入口；V1 默认，V2 显式。
- 不重写前端；只加能力／步骤／知识标注与失败／不可用展示。
- **不新增公开端点、数据库表、迁移、事件类型、框架依赖；不改 `run_deliveries.kind` CHECK 约束**（见 §2.5、§2.6）。
- **`core/react_graph.py` 零改动**（V1 `BaseAgent` 共享），不复用、不扩展，理由见 §2.3。
- **输入契约只支持材料槽位（material slots）**：V2-1 的能力输入就是本 Run 冻结快照里的文本材料槽位；服务绑定、资源句柄、查询参数等输入形态**留给 V2-2**，本阶段契约里不出现对应字段（§2.2）。

## 2. 设计决策

### 2.1 文件级架构与职责边界

```text
正式会话输入（既有 POST /api/v1/runs，runtime_kind=main_agent）
  → 既有 RunApplicationService（唯一受理／事件／终态 writer；本 Design 只改事件 data 白名单与上下文类型放行，不按能力分支）
  → typed RunExecutor（按已保存 runtime_kind 选择；本阶段仍只有 LegacyDiagnosisRunAdapter 与 MainAgentRunExecutor）
      └─ MainAgentRunExecutor.stream
           装配：能力目录摘要 ← CapabilityRegistry（组合根显式注册）
                 工具注册 ← ToolBinding（按能力声明装配，无能力 id 分支）
                 知识源   ← ManagedSkillSource（内置受管 Markdown，按版本读取）
                 ReActKernel（LangGraph 有界循环：decide ⇄ act → END）
  → RunEventSignal*（既有事件类型 + 白名单 data）+ 恰好一个 RunMainDeliverySignal / RunFailureSignal
  → 既有 _execute_typed：running 谓词预留序号、_complete_main_success 单事务写交付／助手消息／终态
  → 既有 GET /runs、GET /runs/{id}、SSE、会话导出、前端 MainDeliveryPanel / MainCapabilityStrip / TraceCard
```

与既有链路的接点（全部沿用，不复制控制面）：

| 接点 | 现状 | V2-1 变化 |
|---|---|---|
| 受理 | `accept_main_agent_run` + `MainInputV1` 快照 | 不变 |
| 执行端口 | `RunExecutor.stream(RunExecutionInput) -> Iterator[RunSignal]` | 不变；`RunSignal` 联合不变 |
| 事件 | `RunEventSignal(DiagnosisExecutionEvent)` → `_safe_event_data` 白名单 | 白名单追加少量枚举型字段（§2.6），事件类型不变 |
| 终态 | `RunMainDeliverySignal` → `validate_main_delivery` → `_complete_main_success` | `validate_main_delivery` 泛化为“按能力输出契约复核”（§2.4） |
| 取消 | 运行流循环在写每个事件前检查 `_is_cancelled`（`services.py`）+ 取消 CAS + running 谓词 | 语义不变；执行器改为**边跑边 yield**，每个 step 边界产出一个事件，因此每个 step 边界成为取消检查点；取消粒度=step 边界，内核额外注入 `is_cancelled` 只读查询在决策前自停（§2.8） |
| 重跑／幂等 | `main-agent-create@1` / `main-agent-rerun@1` 指纹 + 快照 `rule_version` 守卫 | 不变；不在快照中新增能力清单（§2.8） |
| Trace | `_safe_event_data` → `TraceCard` | 新增能力／知识／步骤标签渲染（§2.7） |
| V1 | Coordinator / 领域 Agent / `LegacyDiagnosisRunAdapter` | 零改动 |

新增模块（全部在 `backend/src/` 内，无新依赖）：

- `capabilities/contract.py`：契约 v1 的不可变声明类型（能力类型、输入契约、输出契约、安全摘要、完成／失败语义、Skill 引用）。
- `capabilities/registry.py`：显式注册表（从 `capabilities/__init__.py` 迁出并扩展；`__init__` 只做再导出）。
- `capabilities/skill_source.py`：内置受管 Skill 的版本化读取、大小与摘要校验、不可用结果。
- `capabilities/playbook/readonly_playbook.md`：受管只读排查手册（仓库内静态文本，非检索）。
- `capabilities/playbook/__init__.py`：`ops.readonly_playbook@1` 声明。
- `capabilities/text_compare.py` 原地迁移（不新增文件）。
- `core/main_agent_decisions.py`：模型决策封闭联合（从 `main_agent_model.py` 拆出并泛化）。
- `core/main_agent_react.py`：ReAct 有界循环（LangGraph `StateGraph`），取代 `main_agent_graph.py` 的一次性 DAG。
- `core/main_agent_budget.py`：每 Run 预算、截止时间与步骤计数（纯数据 + 判定，无 I/O）。
- `core/capability_tools.py`：执行型能力的 `ToolBinding`（工具构造注册、决策参数 → 网关参数、网关输出 → typed 结果复核），取代 `run_executor._tool_registry` 的能力分支。
- `core/observation.py`：安全观察投影（能力身份、步骤、状态、typed 引用与固定摘要，**不含原文／原始输出／异常**）。
- `core/main_agent_react.py` 内部新增 `MainReactKernel`：`agents/main_agent.py` 的 `MainAgentTask` 去能力字面量后委托给它，`RunExecutor` 仍只接受 `MainAgentTask`。

修改模块：

- `capabilities/text_compare.py`（迁移到契约 v1；比较算法与 `TextComparisonV1` 不变）
- `capabilities/__init__.py`（注册表迁出，只保留再导出；**保留旧名与旧签名作为兼容层**：`CapabilityRegistry([...])` 构造、`get()`、`definitions()` 继续可用并委托到新的 `resolve()`／`catalog()`，避免波及既有用例与 V1 引用；兼容层在下一阶段删除）
- `core/main_agent_model.py`（适配器与 mock 场景）。mock 沿用 `OPERMIND_MAIN_AGENT_MOCK_SCENARIO`（既有显式 mock 标注），新增知识链路与拒绝场景取值（知识回答、知识不可用、未知能力、错误版本、重复加载、预算耗尽）；旧取值语义不变。
- `agents/main_agent.py`（`MainAgentTask` 去掉 `capability_id: Literal["text.literal_compare"]`／`capability_version: Literal[1]` 与 `_decision_request` 中的硬编码能力 id，改为通用形态；编排委托给 `MainReactKernel`）
- `domain/main_agent.py`（交付接地字段、知识接地类型、预算常量）
- `application/run_execution.py`（失败码加法、按能力复核交付、`main_delivery_message` 调用点）
- `application/services.py`（上下文选择与事件白名单）
- `infrastructure/agent_runtime/run_executor.py`（装配、**改为逐步 yield**、注入取消查询）
- `api/v1/{dependencies,routes,schemas,resources}.py`

不改：`application/runtime_safety.py`（`guard_run_stream` 的信号协议不变）、`core/tool_gateway.py`、`core/tool_registry.py`、`core/llm.py`、`core/react_graph.py`、V1 全部模块。

退役／删除：`core/main_agent_graph.py` 的“单能力一次性 DAG”在迁移完成后删除，不保留双内核。

### 2.2 Capability 契约 v1

**字段**（`capabilities/contract.py`，`@dataclass(frozen=True, slots=True)`，构造时做自洽校验，不合法直接 `ValueError`）：

```text
CapabilityDefinition
  capability_id: str                 # 形如 "text.literal_compare"，正则 ^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$，≤64
  version: int                       # ≥1
  kind: CapabilityKind               # "knowledge" | "execution"；“类型与声明不一致”由下面的约束表达
  title: str                         # 模型与界面可见短名，≤40
  description: str                   # 模型可见说明，≤280
  usage_guide: str                   # 模型可见使用指引，≤600（不含 Skill 正文）
  input_contract: CapabilityInputContract   # 必填／可选的输入槽位
  output_contract: CapabilityOutputContract # 成功交付的类型与安全摘要字段
  resources: tuple[ResourceDeclaration, ...]  # 所需资源；知识型必须为空
  permissions: tuple[str, ...]       # 权限标记；本阶段只允许 "read_only"，执行型必须含它
  tool_bindings: tuple[str, ...]     # 允许工具绑定名；知识型必须为空，执行型必须非空
  completion: CompletionSemantics    # 完成条件（封闭枚举）
  failure: FailureSemantics          # 失败语义（封闭枚举集合）
  skill: SkillDeclaration | None     # 知识型必须有；执行型必须为 None
  instruction: str                   # 每次选中时装入上下文的内置指引（如“不得声称已读取实时数据”），≤400
  rule_version: str | None           # 确定性规则版本（执行型可声明）
```

- `CapabilityKind.KNOWLEDGE` 约束：`tool_bindings == ()`、`resources == ()`、`permissions == ()`、`skill is not None`、`completion is CompletionSemantics.RESPONSE`。
- `CapabilityKind.EXECUTION` 约束：`tool_bindings` 非空、`permissions` 含 `"read_only"` 且不含其他值（本阶段拒绝任何非只读权限声明，属安全默认）、`skill is None`、`resources` **必须显式声明**（可以是空元组：纯计算能力如 `text.literal_compare@1` 不依赖外部资源；契约要求的是“显式写出”，不是“必须非空”，这与 PRD「执行型能力必须声明所需资源与权限」一致）。
- `SkillDeclaration`：`source: Literal["builtin"]`（唯一取值，其他来源不进入契约）、`skill_id: str`、`skill_version: int`、`max_codepoints: int = MAX_SKILL_CODEPOINTS`、`expected_sha256: str`（构建期固定摘要，防手册被静默改动或被替换为含凭据内容）、`title: str`。
- `CapabilityInputContract`：`material_slots: tuple[MaterialSlot, ...]`，`MaterialSlot` 为 `(slot: str, label: str)`；`text.literal_compare@1` 声明 `("text_a", "文本 A（旧）")`、`("text_b", "文本 B（新）")`；`ops.readonly_playbook@1` 为空（不需要材料）。必填语义：已声明的槽位全部必填；本阶段不支持可选槽位。**槽位名是能力自己的输入名，不再是全局 `MaterialSide` 字面量**——`MaterialSide` 只在 `MainInputV1`／快照层保留，契约层不再引用。**V2-1 的输入契约只覆盖材料槽位**：没有服务绑定、资源句柄、连接参数、查询语句或任意自由输入；这些输入形态与对应的资源权限模型留给 V2-2，本阶段不在契约里预留半实现的字段。
- `CapabilityOutputContract`：`delivery_kind: Literal["comparison"] | None`——**执行型**能力必须声明且当前唯一取值为 `"comparison"`（V2-1 只有一种 typed 交付形态，见“交付泛化边界”）；**知识型**为 `None`（知识型不产出 typed 结果，交付固定落入 `answer`，是否带接地由程序决定）。另有 `result_schema: str`（结果契约标识，如 `"text_comparison.v1"`）、`summary_fields: tuple[str, ...]`（允许进入观察与过程事件的字段名）。**交付形态只有 `answer`／`needs_input`／`comparison` 三种**，不存在“knowledge_answer 交付 kind”，知识辅助回答只是 `answer` 加接地（§2.5）。
- `CompletionSemantics`：`RESPONSE`（模型基于已装入知识回答即完成）、`TYPED_RESULT`（必须产出经复算通过的结果才能交付）。
- `FailureSemantics`：封闭枚举集合，取值来自 `{input_missing, input_invalid, source_unavailable, source_invalid, tool_unavailable, tool_timeout, result_invalid, budget_exhausted}`；执行器只能按声明映射到既有 `RunFailureCode`（§2.5），不能在代码里临时发明失败语义。

**注册与解析**：

- `CapabilityRegistry.register`：重复 `(id, version)` 直接拒绝；同一 `capability_id` 允许多个版本共存，但**运行时只启用该 id 的最高已注册版本**（`active_version`）。
- `CapabilityRegistry.resolve(capability_id, version) -> ResolutionOutcome`：返回五种封闭结果 `resolved` / `unknown_id` / `unknown_version` / `inactive_version` / `kind_mismatch(expected_kind, actual_kind)`；调用方（执行器）把后四种映射为 `MAIN_AGENT_CAPABILITY_UNAVAILABLE`，**不执行任何工具**。`inactive_version` 表示“该版本存在但未被启用”——避免目录只展示一个版本、执行却接受任意已注册版本的“隐蔽旧版本”问题（AC1 要求按 id+version 选择，也要求不匹配版本安全失败）。
- `CapabilityRegistry.catalog() -> tuple[CapabilitySummary, ...]`：只输出每个 id 的**启用版本**（id 升序），字段为 id、version、kind、title、description、usage_guide、槽位名与标签、是否可用；**不含** Skill 正文、工具实现、资源句柄、路径。`CapabilitySummary` **只用于模型提示与执行器内部选择**，不是公开资源——公开 Run 资源里没有目录（用户决定：不加 `catalog`，§2.6）。
- 组合根（`api/v1/dependencies.py::_main_agent_run_executor`）显式注册 `TEXT_COMPARE_CAPABILITY` 与 `READONLY_PLAYBOOK_CAPABILITY`；没有扫描、自动发现或热加载。

**版本激活策略与 rerun 语义（钉死）**：

- 激活策略是**注册表快照 + 最高版本**：进程启动时组合根显式注册，同一 `capability_id` 若有多个版本，只有最高版本处于启用态；`resolve()` 对非最高版本返回 `inactive_version`。注册表在进程生命周期内不可变（无热加载、无运行时注册），因此“当前启用版本”在单个 Run 内不会漂移。
- **每次 Run 在执行开始时读取当前启用版本**，不把能力版本冻结进 Run 输入快照：`main_agent_rerun_fingerprint` 与 `MainInputV1` 不新增能力清单字段（避免改变既有指纹与旧行语义）。
- **rerun 使用 rerun 时刻的启用版本**：重跑会重建相同的冻结材料快照并重新执行 ReAct 循环；若部署在两次 Run 之间新增并注册了同 id 的更高版本，rerun 的能力目录与解析都以新启用版本为准。这不会让历史交付“改写”——历史 Run 的交付与接地字段原样保留，新 Run 写自己的交付。
- 模型若在决策里引用旧的 `capability_version`，`resolve()` 返回 `inactive_version` → `CAPABILITY_UNAVAILABLE` 安全失败（零工具执行），不会“悄悄执行旧版本”。专项测试：注册新版本后 rerun，断言新 Run 使用新启用版本、旧版本决策被拒（§3）。

**“加能力不改内核”的可判定边界（AC6）**：

- 主循环、会话服务、工具网关中**不允许出现任何具体 `capability_id` 字符串或按能力 id 的 `if/elif`**。能力的差异只能出现在四处：注册（组合根）、该能力自己的声明、该能力的 `ToolBinding` 实现（或 Skill 内容）、以及它的 typed 结果模型。
- 模型侧决策是通用形态：`{"kind":"invoke_capability","capability_id":"...","capability_version":N,"inputs":{...}}`；参数的具体校验在 `ToolBinding.build_arguments` 内完成，主循环只负责“未知能力／缺输入／归属校验”。
- 回归保护：新增一个仅供测试的**合成能力**（测试模块内声明 + 注册 + 一个不触网的 `ToolBinding`），证明在不改 `core/`、`application/`、`gateway` 的前提下即可被选择、校验、执行、观察并复核结果。测试合成能力不进入生产组合根。
- **交付泛化边界（钉死）**：V2-1 的主循环只提供**一条**“通用 typed 结果交付”路径——`ToolBinding` 返回一个 `CapabilityResult`，主循环按 `output_contract.delivery_kind` 把它封成 `MainComparisonDeliveryV1`（当前唯一取值）。因此合成能力只证明“选择→校验→执行→观察→复核”，**不**证明“任意新交付形态免改内核”；新增第二种 typed 交付形态需要扩展契约与交付联合，属下一阶段。这一限制是如实的能力边界，不写成“已支持任意能力”。

**旧字段迁移表（`CapabilityDefinition` 演化）**：

| 现状字段 | 契约 v1 | 说明 |
|---|---|---|
| `capability_id` | 保留，新增正则与长度约束 | 既有取值 `text.literal_compare` 合法 |
| `version` | 保留 | — |
| `allowed_tools: tuple[str, ...]` | 改为 `tool_bindings: tuple[str, ...]` | 值不变（仍是 `TEXT_COMPARE_TOOL_NAME`），仅重命名；`TEXT_COMPARE_TOOL_NAME` 常量仍由该能力模块导出，`CapabilityDefinition` 不再引用工具名语义 |
| `required_materials` | 改为 `input_contract.material_slots` | 旧值 `("text_a","text_b")` 映射为两个带标签的槽位；`MaterialSide` 不再出现在契约层 |
| —（新增） | `kind`、`title`、`description`、`usage_guide`、`output_contract`、`resources`、`permissions`、`completion`、`failure`、`skill`、`instruction`、`rule_version` | 新增必填／可选字段，`text.literal_compare@1` 全部显式补齐 |
| 旧方法 `get(capability_id, version)`、`definitions()` | 新 `resolve(capability_id, version)`、`catalog()`；旧方法保留为兼容层 | 兼容层 `get()` = 对 `resolve()` 只返回 `resolved` 结局的声明（其余 `None`，与现状一致）；`definitions()` = `catalog()` 对应的完整声明；既有调用方与既有用例无需改写 |

### 2.3 ReAct 主循环

**状态**（`core/main_agent_react.py`，`TypedDict`，每 Run 新建，Run 结束即废弃）：

```text
MainReactState
  step: int                      # 已完成的模型决策数
  transcript: list[PromptMessage]  # 系统提示 + 冻结上下文 + 用户目标 + 观察消息（受 §2.8 上限裁剪）
  loaded_skills: set[(str, int)]   # 本次 Run 已装入的知识型能力
  observations: list[ObservationSummary]
  deliveries: list[CapabilityResult]  # 已复算通过的能力结果（当前至多 1 条，见“交付选择”）
  answer: str | None
  needs_input: tuple[str, ...] | None
  failure: MainAgentFailure | None
  canceled: bool
  degraded: list[DegradedCapability]  # 被模型尝试但不可用的能力（知识缺失／超限）
```

**模型的语义决策**（`core/main_agent_decisions.py`，严格 Pydantic 判别联合，`extra="forbid"`）：

| kind | 字段 | 程序侧语义 |
|---|---|---|
| `answer` | `text` | 最终回答。若本次 Run 已成功装入知识，程序据此把它投影为**知识辅助回答**（附接地）；否则是普通回答。 |
| `needs_input` | `slots: tuple[str, ...]` | 材料追问；缺失集合必须与快照实际缺失的不同槽位集合完全一致，否则 `MODEL_DECISION_INVALID`。 |
| `load_skill` | `capability_id`、`capability_version` | 仅知识型能力；程序装入 Skill 并追加观察。 |
| `invoke_capability` | `capability_id`、`capability_version`、`inputs: dict[str, str]` | 仅执行型能力；程序校验后经网关调用（§2.4）。 |

**程序侧事件流**（`RunSignal` 序列，与模型决策区分，不属于决策联合）：执行器每个 step 边界产出一条 `RunEventSignal`（`route_decided`／`tool_invoked`／`agent_done`），外加恰好一个终态信号。`budget_exhausted`／`failed`／`canceled` 是**程序事件的标签**，不是模型可以选择的决策 kind。

刻意**不**引入单独的 `respond` 决策：知识标签由程序按“本 Run 是否真的装入过知识”判定，而不是由模型选择某个决策名来领取。这样模型没有任何词汇或字段可以自称“知识辅助”，也不会因为用错决策名把一次正常回答变成硬失败；模型决策集合严格等于 PRD 列出的四类。

**每步控制流**：

```text
decide ──(失败)──────────────────────────────────────────→ fail
  │
  ├─ answer ──────── loaded_skills 为空 → finalize_answer（普通回答）
  │                  loaded_skills 非空 → finalize_answer（程序附加接地 → 知识辅助回答）
  ├─ needs_input ─── 与实际缺失不符 → MODEL_DECISION_INVALID；相符 → finalize_needs_input
  ├─ load_skill ──── 解析 / 类型 / 预算 / Skill 来源检查 → 失败则 fail 或追加“不可用”观察
  │                  成功 → 追加观察 → 回到 decide
  └─ invoke_capability → 解析 / 类型 / 预算 / 决策字段形状 / 材料归属校验
                        → 调用 ToolBinding（经 ToolGateway）→ 复核 typed 结果
                        → 成功：按 output_contract.delivery_kind 产出确定性交付（当前唯一取值 = comparison），不再询问模型
                        → 失败：fail（封闭码）
```

**交付选择（钉死）**：

- 本阶段每个成功 Run **恰好一个交付**。执行型能力结果复算通过后立即以确定性交付结束 Run，不再让模型“再总结一遍”——V2-0 的规则继续成立：比较交付只能来自工具事实，不能来自模型复述。
- 知识型链路：`load_skill` 成功后不会结束 Run，必须再发生一次模型决策（`answer`／`needs_input`／`invoke_capability`），因此 AC2 的“至少两次模型决策”由状态机结构保证，不依赖提示词自律；知识接地也只在“真的装入过”时才由程序附加。
- 本阶段**不验收**“知识 + 执行组合成一次交付”（PRD 明确排除多能力编排验收）。组合自然发生时的行为：先 `load_skill` 后 `invoke_capability` 成功 → 交付仍是确定性比较结果；先 `invoke_capability` → 立即结束，不会再有 `load_skill`。

**不复用既有 `core/react_graph.py`（结论与理由）**：

- 结论：V2-1 新写 `core/main_agent_react.py`，`core/react_graph.py` **零改动**。
- 理由：① `build_react_graph` 与 V1 `BaseAgent` 共享，`model_node` 直接读写 `agent.short_term`／`thinking_log`／`long_term`，与 V2 的 Run 级状态机不是同一模型；② 它的 `tools_node` 把 `gw_result.output` 原样塞回 `ShortTermMemory`，正是本 Design 禁止的“原始工具输出进模型观察”；③ 它的 `TOOL_INVOCATION_LIMIT_TEXT` 等文案是前端锚定的行为契约，改动即波及 V1；④ 扩展它来做 V2 等于把两代运行时的状态模型焊在一起。
- 约束：实施者不得“顺手”扩 `react_graph.py`；它出现在 §3“不改”清单里。

**模型输入构造**（`MainDecisionRequest`）：系统提示 = 固定角色与决策格式说明 + 能力目录摘要 + 已知静态约束（“不得声称读取实时数据”“只引用列出的材料 ID”“不得复述材料正文”）；然后冻结上下文（≤4 条、≤2000 码点，V2-0 规则不变）；然后用户目标 + 槽位状态（“已提供／未提供 + 槽位名”，执行型能力附本 Run 材料引用 ID）；然后历史观察。

- **观察上限（钉死，替代“滑动窗口”）**：硬上限 `MAX_OBSERVATION_MESSAGES_IN_PROMPT = 6` 条观察消息。V2-1 当前配置下实际最多 **2** 条（只有一个知识型能力、`MAX_KNOWLEDGE_LOADS = 2`；执行型失败直接终止 Run，不产生观察）。6 是单步防御上限，**不是**“每条决策一条”的配比，也不能从 `MAX_MAIN_DECISIONS` 推导。若超限（防御性分支），以 `BUDGET_EXHAUSTED` 安全失败，**不做静默截断**——不让模型在缺观察的情况下继续决策。
- 每条观察：`<capability_id>@<version> step=<n> status=<safe_status> ref=<typed ref>`，无原文。
- **`instruction`／`description`／`usage_guide` 的来源**：这些是注册声明里的模型可见文本，等同 Prompt 注入面，因此**只允许来自内置声明**（与 Skill 同为 `builtin`）；外部来源在契约层不存在，本阶段不存在第三方注册路径（§2.9）。

### 2.4 两类能力共用同一套选择、校验、观察与交付

| 环节 | 知识型 | 执行型 | 共用实现 |
|---|---|---|---|
| 选择 | `load_skill` | `invoke_capability` | `resolve()` + 目录摘要 + `kind` 校验 |
| 校验 | 来源存在、版本一致、≤4000 码点、摘要一致 | 槽位齐全、材料引用属于本 Run、工具绑定已注册 | `validate_selection()`（统一入口，按 `kind` 分派到 skill / tool 校验） |
| 知识 | `status=loaded`，`ref=<skill_id>@<skill_version>` | `status=ok`，`ref=<result_schema>` | `ObservationSummary`（同一类型、同一投影白名单） |
| 交付 | `answer` + 可选 `knowledge_grounding` | `comparison` 交付（原样） | `MainDeliveryV1` 同联合；`validate_main_delivery` 按输出契约复核 |

**统一校验顺序**（任一失败即封闭失败，零工具执行，除非明确标注为“降级观察”）：

1. 能力解析：未知 id／未知版本／未启用版本／类型与决策不符 → `CAPABILITY_UNAVAILABLE`。
2. 预算：本 Run 的步数／知识加载数／工具调用数／总截止时间（§2.8）→ `BUDGET_EXHAUSTED`。
3. 决策形状：未知 `kind`、额外字段、执行型输入槽位与声明不一致（多一个或少一个）→ `MODEL_DECISION_INVALID`，**零工具执行、不重试**（AC9）。
4. 归属：材料引用必须等于本 Run 快照中的对应槽位 ID，否则 `CAPABILITY_UNAVAILABLE`（与 V2-0 一致）。
5. 能力内部：知识源读取失败／超限／摘要不符 → **降级观察**（不终止 Run，见 §2.3 与下段）；工具调用 → 网关状态映射。

**知识型降级语义（钉死 AC4）**：

- Skill 缺失、超限、摘要不符或版本不符时，**该次 `load_skill` 不装入任何内容、不写入 `loaded_skills`**，追加一条 `status=unavailable` 观察，并把能力登记进 `degraded`；Run 继续，模型可以改走 `answer`。由于知识接地是按 `loaded_skills` 由程序附加，此时模型**不可能**拿到知识标注；公开 `main_capabilities.degraded[]`（§2.6）如实列出“`ops.readonly_playbook@1` 不可用”，界面显示“能力不可用”。
- 降级观察**不包含任何 Skill 片段**，也不含原因原文，只含 `reason` 封闭枚举（`source_missing`／`source_too_large`／`source_digest_mismatch`／`version_mismatch`）。
- 降级不消耗知识加载预算（没有装入），但**仍消耗一次模型决策**，因此不会形成无限降级重试，且预算上限仍生效。
- **同一能力在同一 Run 内降级一次后，再次 `load_skill` 该能力直接 → `CAPABILITY_UNAVAILABLE` 安全失败**：第一次降级仍按上一条消耗一次模型决策并写一条降级观察；重复尝试不再追加观察（提出该决策的那次模型调用已经计入决策预算），Run 以封闭失败码结束。这防止“反复尝试一个不可用的能力”把 6 次决策全部吃掉、一次正常回答都没产生；模型仍可在第一次降级后改走 `answer`。

**交付复核泛化（`application/run_execution.py::validate_main_delivery`）**：

- 保留现有 `needs_input`、`answer`、`comparison` 三条复核规则不变（比较仍对冻结输入完整重算并逐块相等）。
- 新增知识辅助回答复核（落在 `MainAnswerDeliveryV1.knowledge_grounding` 上）：接地中的能力必须已注册、版本相符、`kind=knowledge`，`skill_id`／`skill_version` 与声明的 `SkillDeclaration` 一致；`data_access` 必须为 `none`、`note` 必须等于固定常量；`text` 长度与字符合法性复验。执行器在交付前**必须**把接地对象连同“本 Run 实际装入过的 Skill 集合”一并校验；`validate_main_delivery` 只做结构复核（它在写事务中，不重读 Skill 文件——文件摘要与大小在装入时由 `skill_source` 校验一次，写事务只比对声明字段）。
  - 关键区分：**“执行器实际装入过”由执行器在内存中校验并由复核器对交付做结构断言；`validate_main_delivery` 无法仅凭交付判定“模型是否真的装过”**。因此接地**不是**信任来源，最终防线是执行器只在自己维护的 `loaded_skills` 非空时才构造带接地的交付；写事务层的复核防的是“伪造接地对象／错误版本／非知识能力”。两层各负责一半，Design 如实说明这一分工。
- 拒绝条件：接地结构非法、能力未注册／版本不符／类型不是知识、`data_access` 或 `note` 被改写、文本长度或字符非法 → `MAIN_AGENT_DELIVERY_INVALID`。

### 2.5 持久化、交付形态与迁移

**结论：不新增表、不新增迁移、不改 CHECK 约束。**

- **交付形态：复用既有 `run_deliveries` 表与 `MainDeliveryV1` 联合，加法扩展 `answer` 而非新增 kind。** 原因：新增 kind 必须改 `run_delivery_kind_valid` CHECK（PRD 禁止静默改 CHECK），而 `answer` + 可选接地字段可以完全表达知识辅助回答，且旧行（无接地字段）语义不变。`RunDeliveryRecord.schema_version` 仍为 `1`；接地字段是同一 schema 版本内的**加法可选字段**，读写两端都按可选处理。
- **为什么不新增交付 kind**：新增 `knowledge_answer` kind 会让 `kind` 判别值与 DB CHECK、前端 reader、导出逻辑、上下文选择同时分叉，代价是迁移 + 用户确认，而收益（语义更清晰）可以在加法字段里拿到；PRD 的开放问题正是要求 Design 做这个权衡。
- **为什么不需要迁移**：JSON 列 `run_deliveries.payload` 可以容纳新可选字段；严格解析器（`MainAgentDeliveryUnavailableError` 路径）对旧行照常通过；新字段缺省时不产生任何行为变化。
- **上下文选择（用户确认，2026-10-26）**：`_select_main_context` 现在放行 `answer`／`needs_input`；知识辅助回答仍是 `answer` 交付，**继续以“用户目标 + 助手回答”成对进入下一轮上下文，并保留服务端固定前缀**——不拆成“只保留用户目标”。前缀让下一轮模型自己能看到“这是知识辅助回答 · 未读取实时数据”，而不是把建议当成已核实事实。比较交付仍不入上下文。
- **导出**：`session_export.py` 以 `main_delivery_message()` 为准，无需改动；知识辅助回答的助手消息正文包含固定前缀（§2.6）。

**交付类型（`domain/main_agent.py` 加法）**：

```text
MainAnswerDeliveryV1（扩展，向后兼容）
  schema_version: 1
  kind: "answer"
  text: str                                   # ≤4000 码点
  knowledge_grounding: KnowledgeGroundingV1 | None = None   # 缺省 = 普通回答（V2-0 旧行同义）

KnowledgeGroundingV1
  capability_id: str                # 必须在注册表内且 kind=knowledge
  capability_version: int
  skill_id: str
  skill_version: int
  data_access: Literal["none"]      # 固定；界面据此显示“未读取实时数据”
  note: Literal["知识辅助回答 · 未读取实时数据"]  # 固定常量，前端与导出共用，禁止自由文本
```

- **只有一个可选字段**，不用 `authority` + `grounding` 两个半状态字段：`knowledge_grounding is None` 即普通回答，非 None 即知识辅助回答，不存在“有 authority 无 grounding”的矛盾态。`extra="forbid"` 不变，旧行（无该字段）照常解析。
- `KnowledgeGroundingV1` 是知识辅助回答的**唯一**接地来源；`TextComparisonV1.capability_id` 的 `Literal["text.literal_compare"]` 保留（该字面量属于**该能力自己的**结果模型，不是内核分支），仅去掉对 `MAIN_AGENT_CAPABILITY_ID` 常量的内核级引用。
- `main_delivery_message()`：知识辅助回答返回 `"知识辅助回答 · 未读取实时数据\n\n" + text`（助手消息与会话导出自动带标注，且该前缀由**服务端**加，不依赖模型输出）；普通回答与追问不变。
- **上下文回填安全（用户确认，2026-10-26）**：知识辅助回答**照常进入下一轮上下文**，助手消息正文保留固定前缀“知识辅助回答 · 未读取实时数据”，使下一轮模型能识别其非实时、非核验属性；`_select_main_context` 的既有成对加入逻辑**不拆分**。安全性由服务端前缀与 §2.9 的诚实标注承担，而不是靠把回答隐藏起来。
- **交付类型联合不变**：`MainDeliveryV1` 仍是 `answer | needs_input | comparison` 三成员判别联合（`domain/main_agent.py:352-355`），**不新增成员**，只扩展 `MainAnswerDeliveryV1` 的字段。因此 `main_delivery_resource`、导出、上下文选择的 `isinstance` 分派全部继续成立。

**改动点清单（避免遗漏）**：

- `api/v1/schemas.py::MainAnswerDeliveryResource`：加法可选 `knowledge_grounding`（公开字段，§2.6、§6 已确认门禁项）。
- `api/v1/resources.py::main_delivery_resource`：`answer` 分支把接地投影为公开资源（当前只返回 `kind`／`text`，`resources.py:178-179`）。
- `application/run_execution.py::validate_main_delivery`：新增 `answer` 分支的知识接地结构复核（见上段）；`needs_input`／`comparison` 分支不动。
  - **签名扩展**：接地复核需要按 `capability_id + capability_version` 查声明的 `kind`／`SkillDeclaration`，当前签名 `validate_main_delivery(delivery, run, snapshot)`（`run_execution.py:308-312`）没有能力注册表。扩展为 `validate_main_delivery(delivery, run, snapshot, capabilities: CapabilityQuery)`——传入**只读最小接口**（`resolve`／`catalog`，由 `capabilities/registry.py` 实现），由 `RunApplicationService` 构造时注入（与 §2.6 的 `capability_ids` 同源、同一个组合根）。`RunApplicationService` 现有的 `registry` 是**服务**注册表，不能复用。该函数只有 `_complete_main_success` 一个生产调用点（`services.py:832`），波及面小。
  - **未注入时的 fail-closed 行为**：`knowledge_grounding is not None and capabilities is None` → `MAIN_AGENT_DELIVERY_INVALID`（拒收），**不是**“跳过校验后放行”。V1 路径不产生该字段，因此不受影响；任何旁路构造或测试夹具若想通过带接地的交付，必须显式注入能力查询。退化成只校验 `data_access`／`note` 常量而不查声明，等于放行伪造的能力身份——不允许。
- `domain/main_agent.py::main_delivery_message`：`answer` 分支按接地加前缀。
- `application/services.py::_select_main_context`：**本阶段不改选择逻辑**。现有实现对每个 Run 用 `candidates.extend([input_message, assistant_message])` 成对加入（`services.py:930`），知识辅助回答沿用同一条路径；由于 `main_delivery_message()` 已给助手正文加服务端前缀，下一轮上下文里保留的正是带前缀的文本。补测试断言：知识辅助回答后的下一轮 `_select_main_context` 同时包含用户目标与带前缀的助手正文。
- `application/services.py::_complete_main_success` 本身**不改**：继续调用 `validate_main_delivery` 与 `main_delivery_message`，敏感内容检查对加前缀后的正文生效。

**Run 资源（加法字段，§2.6）** 与**事件（复用，不改类型）** 见下。

### 2.6 公开 Run 资源与事件

公开字段全部加法，`DiagnosisRunResource` 现有字段语义不变。

```text
DiagnosisRunResource 新增（均为 Optional，legacy 与旧 V2 行缺省为 null）：
  main_capabilities: MainCapabilitiesResource | None
      used:     list[MainCapabilityUseResource]       # id/version/kind/status(loaded|ok|unavailable)
      degraded: list[MainCapabilityUseResource]       # 模型尝试但不可用的能力
      steps:    int | None                            # 已发生的模型决策数（事件可读出时）
  main_capabilities_status: Literal["available","unavailable","absent"] | None
  main_knowledge: MainKnowledgeGroundingResource | None  # 与 delivery.knowledge_grounding 同源
```

**公开资源不含能力目录（用户确认，2026-10-26）**：不加 `catalog`，也不加任何等价的目录快照字段。`Catalog` 是“当前进程注册表”的视图，不是 Run 历史事实，放进 Run 资源会制造“历史 Run 的能力目录随部署漂移”的假象；模型侧目录摘要只进入 Prompt，界面显示的能力来自 `used`／`degraded`。`CapabilityRegistry.catalog()` 因此只保留内部用途（构造模型提示、导出 id 白名单）。

- **投影策略（钉死）**：
  - `used`／`degraded` 的唯一权威来源是**交付与事件**：成功 Run 里知识型来自 `knowledge_grounding`、执行型来自比较交付的能力身份；`degraded` 来自执行器写入的事件（`route_decided` 的 `status=unavailable`）。失败 Run 没有交付，能力归属**只能**来自事件。
  - **列表与详情同口径读事件，且是批量读**：`list_session_runs`（会话列表）与 `list_runs`（全局列表）在**一次** `SELECT … WHERE run_id IN (…)` 查询里取本页全部 main_agent Run 的 `route_decided`／`agent_done` 事件行（既有 `run_events` 表按 `run_id` 有索引，无 schema 变更），在内存汇总出 `used`／`degraded`／`steps`。**不做逐 Run 查询**——V2-0 已记录的 N+1 不重复；列表与详情返回同一组 `used`／`degraded`／`steps`（已确认，§6）。
  - **公开资源不带目录**：`catalog` 不进入 Run 资源、列表或详情；见本节开头。
  - 事件读取失败（损坏行）不抛错：`steps=null`、`used`／`degraded` 为 `[]`、`main_capabilities_status=unavailable`（与 V2-0 损坏行同口径，一条坏行不拖垮列表）。
- **`used`／`degraded` 只含 id／version／kind／status**（`status` ∈ `loaded`／`ok`／`unavailable`），不含 Skill 正文、路径、工具实现或资源句柄；“哪个能力在第几步失败”由 `steps` 计数与过程事件的 `step`／`capability_id` 承载，不重复放进 `used`。
- **`main_knowledge` 的唯一来源是交付**：`main_knowledge = delivery.knowledge_grounding`（逐字段投影），交付不可读或缺失时恒为 `null`，**不从事件反推**；因此不存在“事件说装过知识、交付没有接地”的双源矛盾。
- 新增读取状态：`main_capabilities_status: Literal["available","unavailable","absent"] | None`——`available` = 交付或事件至少一项可读且已投影；`unavailable` = 该 Run 的能力归属应存在但一行都读不出来（含交付接地非法）；`absent` = 该 Run 确无任何能力使用（直答）。与 V2-0 的 `main_delivery_status` 同口径。
- `validate_terminal_payload` 追加：`main_capabilities`／`main_capabilities_status`／`main_knowledge` 只能出现在 `runtime_kind=main_agent`，且非终态不得携带；`main_capabilities` 出现时 `main_capabilities_status` 必须同时出现。
- **失败与不可用投影（AC12）**：能力失败或能力不可用时，即使用户只看到失败或取消气泡，也必须能读出“哪个能力、什么状态”——失败／取消 Run 的 `used`／`degraded` 由事件 `route_decided`（`capability_id`／`capability_kind`／`status=unavailable`）在列表与详情**都**汇总；成功但知识能力不可用的 Run，`degraded` 只存在于事件（降级不写交付），列表与详情同样读事件汇总。**`degraded` 不进入交付**，交付只表达用户可见的结果。前端在失败／取消／交付不可用三种终态下也挂载能力条（§2.7）。

**事件（不新增类型）**，复用既有五类，`_safe_event_data` 白名单追加下列枚举型字段（值都经封闭校验，长度受限）：

| 事件 | 现有 data | V2-1 追加 |
|---|---|---|
| `agent_start` | summary, mode | `summary` 不变（文案与 V2-0 一致）；能力数量不放入该事件，本阶段界面不展示“可用能力 N 项” |
| `route_decided` | summary, mode | `step`(int 1..6)、`decision`(`answer`/`needs_input`/`load_skill`/`invoke_capability`/`budget_exhausted`/`failed`)、`capability_id`(白名单：必须出现在已注册能力目录中)、`capability_version`(int)、`capability_kind`(`knowledge`/`execution`)、`status`(`ok`/`unavailable`) |
| `tool_invoked` | status, summary（固定文案） | `step`、`capability_id`、`capability_version`、`duration_ms`（已支持） |
| `agent_done` | summary, mode | `steps`、`outcome`(`answer`/`answer_with_knowledge`/`needs_input`/`comparison`/`failed`/`budget_exhausted`/`canceled`)——`answer_with_knowledge` 是**事件标签**（表示“这次回答带了知识接地”），不是交付 kind；交付 kind 仍只有 `answer`／`needs_input`／`comparison`（§2.2、§2.5） |
| `run_failed` / `run_succeeded` / `run_cancelled` | state[, code] | 不变 |

- **白名单接线（本次修正，钉死到构造点）**：`_safe_event_data(event, registered_service_ids)` 目前只收服务白名单（`services.py:1031-1061`），**调用点在 `_execute_typed` 与 `_execute_legacy` 两处（`services.py:347`、`:386`）**。V2-1 给它加第二个参数 `registered_capability_ids: frozenset[str]`：
  - `RunApplicationService.__init__` 新增可选参数 `capability_ids: frozenset[str] = frozenset()`（与 `registry` 同风格）；
  - 唯一生产构造点 `api/v1/dependencies.py:354`（`RunApplicationService(...)`）传入 `capability_ids=frozenset(_MAIN_AGENT_CAPABILITIES)`——**组合根内**的同一个能力元组既构造注册表、又导出这个 id 集合，不存在两份来源；
  - 缺省空集合时所有 `capability_id` 字段被丢弃（安全默认：测试与 V1 路径不受影响）。
- `capability_id` 不在白名单内则丢弃该字段；`capability_kind`、`decision`、`outcome`、`status`、`step`、`capability_version` 都是封闭枚举／受范围整数校验，非法值丢弃。**事件 data 只承载已校验的枚举值，不承载路径、正文或任意字符串。**
- 事件不含 Skill 正文、观察正文、原始工具输出、异常或凭据；`summary` 仍是 ≤280 码点的固定文案。
- **mock 标注（AC17）**：`agent_start` 的 `mode`（`mock`／`target`）沿用 V2-0，`_safe_event_data` 已透传；V2-1 不新增标注字段。前端 mock 标注继续由 shell 顶栏 `TopBar` 承担（`TopBar.tsx:29` 的“当前模型 X · 演示”，数据来自既有 `GET /model-config`），不依赖 Run 事件；`TraceCard` 不新增 mode 展示。测试断言：mock 运行的顶栏标注存在、且知识辅助回答区域同样出现在 mock 模式下而不被隐藏。
- 前端 `RUN_EVENT_TYPES` 不需要变化（类型集合不变）；`TraceCard` 的 `event_detail()`（`TraceCard.tsx:86-91`）目前只对 `tool_invoked`／`conflict_checked`／`debate_round`／`reflection` 取 `summary`，`route_decided`／`agent_done` 不显示细节——V2-1 把这两类加入固定文案渲染（由封闭枚举拼出“决策 · 知识加载 · ops.readonly_playbook@1 · 不可用”这类句子），并补 `trace-card.test.tsx` 断言。

### 2.7 前端展示

全部在 `frontend/src/features/workbench/` 内，不重写页面：

- `main-delivery-readers.ts`：`answer` 投影新增可选 `knowledge_grounding`；严格校验 `data_access="none"`、`note` 等于固定常量、能力身份合法；旧行缺省为普通回答。新增 `read_main_capabilities()`、`read_main_knowledge()`（与后端资源同构，未知字段忽略、非法结构报协议问题不猜测）。
- `MainDeliveryPanel.tsx`：`answer` 且 `knowledge_grounding != null` 时，在正文上方渲染固定徽标“知识辅助回答 · 未读取实时数据”，并附“来源：内置只读排查手册 `ops.readonly_playbook@1`（未检索、未联网）”；比较回答的渲染不变。
- 新增 `MainCapabilityStrip.tsx`：显示本次 Run 的 `used`（`capability_id@version · 知识型/执行型`）、`degraded`（“能力不可用”）、`steps`、`main_capabilities_status` 与终态；`steps` 为 `null` 时显示“步骤未知”而不是 0，不占位伪造。
- **挂载点（钉死，覆盖全部终态）**：能力条挂在 `MainAgentReply` 的**每条终态分支**里——`failed`（`WorkbenchPage.tsx:345`）、`cancelled`（`:361`）、`succeeded` 但交付 `unavailable`（`:371`）、正常成功与实时态（`:387` 起），位置都在 `InvestigationProcess` 之上。V2-0 里失败／取消分支根本不渲染交付面板，若照搬“只在 `!is_live && delivery != null` 时挂载”，AC12 的“失败与不可用显示”就没有落点；本 Design 明确在失败／取消分支也挂载。
- 数据来源：成功 Run 的能力归属来自列表／详情 Run 资源（`main_capabilities`）；实时态只有事件，能力条在收到带 `capability_id` 的 `route_decided` 事件时即时追加（复用既有 SSE 事件流，不额外发请求）。
- `TraceCard.tsx`：`route_decided` 行显示“决策 · 知识加载／能力调用／回答／追问／预算耗尽”+ 能力标签 + 不可用状态；`agent_done` 显示步骤数与终态。仍只展示白名单字段，不展示 CoT／Prompt／原文。
- 词表约束：知识辅助回答区域**不得**出现“已校验”“已读取”“已诊断”；用前端测试断言这组禁词不出现在知识辅助回答的渲染结果中（比较交付区域不受影响）。
- `MainAgentComposer.tsx`：helper 文案从“比较两段文本时填写”改为“比较两段文本时填写；只读排查类问题不需要材料”。不新增输入控件。

### 2.8 预算、截止时间、取消与规则版本

PRD 限额全部作为**服务端版本化常量**（`domain/main_agent.py` 或 `core/main_agent_budget.py`），本阶段不新增运行参数设置页：

```text
MAX_MAIN_DECISIONS = 6          # 每 Run 模型决策次数（含失败尝试）
MAX_KNOWLEDGE_LOADS = 2         # 成功装入次数
MAX_AGENT_TOOL_CALLS = 3        # 经网关的工具调用次数
MAX_RUN_WALL_CLOCK_SECONDS = 120  # 本执行器总时间预算
MAX_MODEL_CALL_SECONDS = 30     # 单次模型调用上限；实际超时 = min(30s, 本 Run 剩余预算)
MAX_TOOL_WAIT_SECONDS = 3.0     # 网关等待上限；实际等待 = min(3.0s, 本 Run 剩余预算)
MAX_SKILL_CODEPOINTS = 4000     # Skill 正文上限，超过即不可用，不截断
MAX_OBSERVATION_MESSAGES_IN_PROMPT = 6   # 观察消息单步防御上限（不是“每条决策一条”的配比，见 §2.3）
```

- **预算判定在执行前扣记**（与 V2-0 “计数先于调用”一致）：模型决策次数、知识加载次数、工具调用次数在发起前检查并加一；失败尝试同样计入。
- **严格 ≤120 秒总预算（用户确认，2026-10-26）**：执行器在 `stream()` 开始时记录 `deadline = monotonic() + 120`，并在两个层面执行：
  1. **每个 step 边界检查**：已超过 deadline → 直接以 `MAIN_AGENT_BUDGET_EXHAUSTED` 安全失败，不再发起任何调用。
  2. **每次阻塞调用前计算剩余预算**：`remaining = deadline - monotonic()`；`remaining <= 0` 时不发起调用，直接 `BUDGET_EXHAUSTED`；否则**实际超时 = `min(能力上限, remaining)`**——模型调用为 `min(30s, remaining)`，工具等待为 `min(3.0s, remaining)`。`LLMClient` 的 `request_timeout` 与网关等待参数都使用这个有效值。
  - 因此不存在“最后一次调用把总时长拖过 120 秒”的路径：任何一次阻塞调用都被剩余预算截断；工具等待也被同样的规则截断，否则严格上界不成立。Design 只承诺 **≤120 秒 + 同步调用返回的调度误差**，不承诺 0 毫秒。
  - 截断仍发生在 step 边界与单次调用的超时上，**不会**在工具执行中途强制终止线程（不复制 V2-0 “底层停止状态未知”的问题）。
- **超时与预算的失败码**：模型调用若因**自身 30 秒上限**超时而失败（`remaining >= 30s`，`LLMClient` 返回 error）→ `MODEL_UNAVAILABLE`；若有效超时已被剩余预算压到 `remaining` 并在该点失败（`remaining < 30s`）→ `BUDGET_EXHAUSTED`，因为失败的直接原因是总预算不足。工具等待同理：固定 3 秒上限先到时 → `TOOL_FAILED`（沿用 V2-0，`RunFailureCode.MAIN_AGENT_TOOL_FAILED`）；被剩余预算截断而超时 → `BUDGET_EXHAUSTED`。总预算／次数耗尽／观察超限 → **新失败码** `MAIN_AGENT_BUDGET_EXHAUSTED`（安全文案“本次主 Agent 运行预算已用尽，请拆分后再试”）。实现上让预算对象返回“本次调用的有效超时 + 是否被预算裁剪”，错误映射只读这个标记，不靠比较浮点时间反推。新增失败码是**加法**：`RunFailureCode` 是封闭枚举，新值在 `_safe_run_error`（`resources.py:244-255`）与 `_safe_export_run_error`（`session_export.py:47-58`）的 `RunFailureCode(code)` 白名单里**自动生效**（二者都按枚举成员校验并回落到通用文案），前端失败态显示 `error.message`，无需新逻辑；`test_main_agent_runtime.py` 里逐项枚举 `RunFailureCode → safe_message` 的测试必须补上新值，否则枚举闭合断言会漏。
- **执行器改为边跑边 yield（取消生效的前提）**：现状 `MainAgentRunExecutor.stream()`（`run_executor.py:62-122`）是“先算出全部结果，再一次性 yield 事件”——会话服务在写第一条事件时检查一次取消，之后没有任何检查点。V2-1 改为**每完成一个 step 就 `yield` 该 step 的事件**。两条消费路径的检查点不同，引用必须分清：`_execute_legacy` 在写事件前显式调用 `_is_cancelled`（`services.py:340-342`）；`_execute_typed` 由 `_append_execution_event` 的 **running 谓词**（`reserve_running_event_sequence`，`repositories.py:441-452`）拒绝已取消 Run 的写入（`services.py:382-389`）。两者都使每个 step 边界成为真实检查点。
- **取消（钉死粒度 = step 边界）**：取消语义不变——会话服务在写入每个运行时事件前检查取消状态，命中即停止消费执行器流。V2-1 额外由组合根注入**只读查询** `is_cancelled: Callable[[], bool]` 给 `MainReactKernel`（`is_cancelled` 只读 `status == CANCELLED`，`repositories.py:454-459`），供它在**每次模型调用之前**和**每次模型调用返回后、分派决策之前**各检查一次；这只是读取同一取消状态，不新增取消端口、不新增写路径、不中断线程。
  - **为什么需要两次检查**：只在调用前检查，模型调用中途发生的取消要等到下一个 step 才被发现，而这期间内核会先分派并执行该决策——可能已经触发一次 `invoke_capability`。**调用返回后的检查**在分派之前丢弃该决策，保证“不触发任何工具”成立。
  - **单次模型调用期间不可中断**（同步生成器 + 同步 HTTP 调用，上限 30 秒）；取消在模型调用中途命中时，该次调用的结果**必须丢弃**：不进入 transcript、不产生决策事件、不触发任何工具，执行器直接结束且不产出交付。这是本 Design 的明确语义，不是隐含行为。
  - 因此对外可承诺的是“取消后不再启动新的 step、不再产出交付、无迟到写入”，**不是**“取消后 0 毫秒停止”。最坏停止延迟 = 当前模型调用剩余时间（≤30 秒或剩余预算，取更小者）或当前工具等待剩余时间（≤3 秒或剩余预算，取更小者）。此粒度已确认（§6）。V2-1 必须补四类取消测试：模型调用期间取消、工具等待期间取消、调用返回后结果丢弃、取消后无迟到写入（§3）。
  - **`_execute_typed` 消费侧怎么接住自停（已按代码核实）**：`RunSignal` 联合（`run_execution.py:169`：`RunEventSignal | RunDiagnosisResultSignal | RunMainDeliverySignal | RunFailureSignal`）**不新增成员**，`runtime_safety.py` 也不改。执行器自查取消时**不产出交付信号**，停止产出事件并让流正常结束；`guard_run_stream` 见正常 EOF 且无终态，会补发 `safe_failure_signal(default_failure)`（`runtime_safety.py:99-105`、`:201-206`），`_execute_typed` 收到 `RunFailureSignal` 后调用 `_complete_failure`（`services.py:391-392`）。
  - **不会多写事件（上一版此处写错，已修正）**：`_complete_failure` 第一步就检查终态——`if run.status in {SUCCEEDED, FAILED, CANCELLED}: return run`（`services.py:867-873`）。而执行器自停的前提是 `is_cancelled()` 为真，即 Run 已是 `CANCELLED`，因此 `_complete_failure` **直接短路**：不写 `run_failed`、不改状态、不追加任何事件。取消后的事件流是干净的；`agent_done` 的 `outcome=canceled` 保留在封闭词表里作防御性取值，但在取消胜出的路径上不会被写入（写入会被 running 谓词拒绝）。
  - 取消胜出后：不再消费后续步骤、不产出交付、不追加事件；`_append_execution_event` 的 running 谓词与 `_complete_main_success` 的 `RUNNING` 谓词继续兜底，保证无迟到交付与第二终态。V2-0 的取消 CAS 行为不变。
- **重跑与规则版本**：`main_agent_rerun_fingerprint` 与 `rebuild_main_input_snapshot` 的规则版本守卫不变（`literal-lines@1` 仍写在快照中），执行器开头的 `UnsupportedMainAgentRuleError`／`MAIN_AGENT_RULE_UNAVAILABLE` 守卫保留。**不**在快照中新增能力清单字段（会改变指纹与旧行语义）。**rerun 使用 rerun 时刻的启用版本**（§2.2 版本激活策略）：每次 Run 重新读取当前注册表，模型提示与 `resolve()` 都以最新启用版本为准；若部署在两次 Run 之间注册了同 id 的更高版本，rerun 使用新版本，历史 Run 的交付与接地字段不改写。能力被移除或版本变化时，在该 Run 模型选择能力的那一步以 `unknown_id`／`unknown_version`／`inactive_version` → `CAPABILITY_UNAVAILABLE` 安全失败，不会执行任何工具。专项测试：注册新版本后 rerun 使用新激活版本，旧版本决策被拒。
- **无自动重试**：模型与工具都不重试；预算耗尽是终态。

### 2.9 安全与脱敏

- **模型可见面**：只有能力摘要、槽位标签与材料 ID、冻结上下文、安全观察；**永远不含 A／B 原文、Skill 之外的文件内容、工具原始输出、原始异常、凭据**。
- **Skill 进入模型**：仅装入声明来源为 `builtin` 且通过版本／摘要／上限校验的手册正文；手册内容在评审时人工确认“无凭据、无用户数据、无实时事实”，构建期摘要固定，运行期只读。
- **模型可见文本的来源**：`description`／`usage_guide`／`instruction`／Skill 正文全部来自内置声明，外部来源在契约层不存在（§2.3），因此本阶段不引入第三方 Prompt 注入面；后续若开放外部能力注册，必须先重新设计这层隔离。
- **执行型能力**：只经既有 `ToolGateway`；模型不能提交任意工具名（网关只注册该能力绑定声明的工具）；参数由 `ToolBinding` 从决策的封闭字段构造，不接受模型拼任意 JSON。
- **观察与事件**：`ObservationSummary` 与 `_safe_event_data` 双层白名单；未知字段丢弃，不报错、不记录原文。
- **助手消息**：沿用 `contains_sensitive_content` 出站检查；知识辅助回答同样受此检查，命中 → `MAIN_AGENT_DELIVERY_INVALID`。
- **日志**：新增日志只记 `capability_id`、`step`、`status`、封闭错误码；不记决策原文、观察正文或 Skill 内容。
- **诚实降级**：知识能力不可用 → 公开投影 `degraded`；模型不可用／预算耗尽／工具失败 → 封闭失败码；任何情况都不把未执行能力写进结果。

## 3. 文件改动面

后端新增：

- `backend/src/capabilities/contract.py`（契约 v1 声明与自洽校验）
- `backend/src/capabilities/registry.py`（显式注册、resolve、catalog、可用性）
- `backend/src/capabilities/skill_source.py`（内置受管 Skill 读取／校验／不可用）
- `backend/src/capabilities/playbook/readonly_playbook.md`（受管手册正文）
- `backend/src/capabilities/playbook/__init__.py`（`ops.readonly_playbook@1` 声明）
- `backend/src/core/main_agent_decisions.py`（决策联合）
- `backend/src/core/main_agent_react.py`（ReAct 有界循环）
- `backend/src/core/main_agent_budget.py`（预算与截止时间）
- `backend/src/core/capability_tools.py`（`ToolBinding` 与工具注册）
- `backend/src/core/observation.py`（安全观察投影）

后端修改：

- `backend/src/capabilities/__init__.py`（注册表迁出；保留 `CapabilityRegistry([])`、`get()`、`definitions()` 兼容层与再导出）
- `backend/src/capabilities/text_compare.py`（迁移声明；算法不变）
- `backend/src/core/main_agent_model.py`（决策总入口与 mock 场景扩展）
- `backend/src/core/main_agent_graph.py`（**删除**，由 `main_agent_react.py` 取代）
- `backend/src/agents/main_agent.py`（`MainAgentTask` 去能力字面量、`_decision_request` 去硬编码能力 id、委托内核）
- `backend/src/domain/main_agent.py`（交付接地字段、知识接地类型、`main_delivery_message` 前缀、预算常量）
- `backend/src/application/run_execution.py`（失败码加法、`validate_main_delivery` 的知识接地复核）
- `backend/src/application/services.py`（`_safe_event_data` 追加能力白名单参数并在 `_execute_typed`／`_execute_legacy` 两处调用点传参、`RunApplicationService.__init__` 新增 `capability_ids` 与 `capabilities` 参数；`_select_main_context` 不改）
- `backend/src/infrastructure/agent_runtime/run_executor.py`（装配能力目录／绑定／Skill 源／`is_cancelled` 只读查询；`stream()` 改为逐步 yield；去能力分支）
- `backend/src/api/v1/dependencies.py`（组合根注册两项能力与内置 Skill 源；`RunApplicationService(..., capability_ids=…, capabilities=…)`——**同一个能力注册表**既导出 id 集合、又作为 `CapabilityQuery` 传入交付复核；`_main_agent_run_executor` 的资源工厂——见下）
- `backend/src/api/v1/schemas.py`（加法资源：`MainAnswerDeliveryResource.knowledge_grounding`、`MainCapabilitiesResource`、`MainKnowledgeGroundingResource`；`validate_terminal_payload`）
- `backend/src/api/v1/resources.py`（`main_delivery_resource` 的 `answer` 分支投影接地；`main_capabilities` 投影）
- `backend/src/api/v1/routes.py`（列表／详情投影：批量事件汇总 `used`／`degraded`／`steps`；不返回能力目录）

- 公开字段：`MainAnswerDeliveryResource`（`schemas.py:795-799`，当前只有 `kind`／`text`）追加**可选** `knowledge_grounding`，缺省 `null` 即普通回答；只有 `answer` 交付上可为非空，与 `DiagnosisRunResource.main_knowledge` 同源。前端 reader 对非 `answer` 交付上的非空接地按协议问题拒绝。
- **资源工厂的接点（设计接缝，实现名由 dev-plan 定）**：`GET /runs`／`GET /sessions/{id}/runs`／`GET /runs/{id}` 的响应投影是全应用共用的（V1 与 V2 都走同一路由），而能力注册表只存在于组合根。为保证“能力投影 = 读注册表目录的 id 白名单 + 只读读事件”且不在 `application` 层引入基础设施依赖，V2-1 给这些端点的应用服务加一个**只读能力归属查询**调用（由 `dependencies.py` 在构造时注入：注册表 id 集合 + 一个批量读 `run_events` 并按 `run_id` 汇总 `used`／`degraded`／`steps` 的函数）。该查询**不写库**、不新增表、不新增端点；未注入时（V1 单元测试、旧测试夹具）投影退化为 `main_capabilities=null`，行为与 V2-0 一致。这是对既有查询服务的最小扩展，不得在主应用服务里直接 `SELECT`。
- **兼容说明**：`application/runtime_safety.py` 不改（新事件 data 仍只经 `_safe_event_data`）；`core/react_graph.py`、`core/tool_gateway.py`、`core/tool_registry.py`、`core/llm.py` 不改。

前端修改：

- `frontend/src/features/workbench/main-delivery-readers.ts`
- `frontend/src/features/workbench/MainDeliveryPanel.tsx`
- `frontend/src/features/workbench/MainCapabilityStrip.tsx`（新增）
- `frontend/src/features/workbench/WorkbenchPage.tsx`（挂载能力条；Run 详情拿到后刷新步数与能力投影）
- `frontend/src/features/workbench/TraceCard.tsx`（`event_detail` 对 `route_decided`／`agent_done` 追加固定文案渲染；`outcome` 词表含 `answer_with_knowledge`）
- `frontend/src/features/workbench/MainAgentComposer.tsx`
- `frontend/src/api/v1/generated.ts`（**只允许** `npm run generate:api` 重新生成）
- `frontend/src/test/handlers.ts`（加法 mock）

测试：

- 后端：`backend/tests/` 下新增契约／注册表、Skill 源、ReAct 内核、预算、绑定、交付复核、API 资源与事件投影、合成能力插件性、导出与上下文选择用例；改造受删除 `main_agent_graph.py` 影响的既有内核用例。
- **必须覆盖的专项用例（用户确认项）**：
  - **取消四类**：模型调用期间取消（结果丢弃、不触发工具）、工具等待期间取消、模型调用返回后才取消（决策在分派前被丢弃）、取消后无迟到写入且无第二终态（运行结束为 `CANCELLED`，不追加 `run_failed`／交付）。
  - **版本激活与 rerun**：注册同 id 新版本后 rerun，新 Run 使用新激活版本；决策引用旧版本 → `inactive_version` → `CAPABILITY_UNAVAILABLE`；历史 Run 交付不被改写。
  - **严格预算**：模型／工具调用的有效超时被 `remaining` 裁剪；裁剪导致的超时 → `BUDGET_EXHAUSTED`；固定上限先到 → `MODEL_UNAVAILABLE`／`TOOL_FAILED`；`remaining <= 0` 时不再发起调用。
  - **知识辅助回答上下文回填**：下一轮 `_select_main_context` 同时包含用户目标与带服务端前缀的助手正文。
  - **输入契约范围**：只接受材料槽位；服务绑定／资源句柄／自由输入字段被 `extra="forbid"` 拒绝。
  - **公开资源不含目录**：列表与详情响应都不存在 `catalog` 字段（序列化后断言）。
- 后端既有用例的**波及面**（注册表 API 变化与任务泛化，必须逐项跑过）：
  - `tests/test_main_agent_runtime.py` 是**唯一**直接导入 `src.core.main_agent_graph` 的测试（`MainAgentFailure`、`MainAgentOutcome`、`needs_input_prompt`，第 52 行）；其中只有 `MainAgentFailure`（`main_agent_graph.py:42`，`StrEnum`）需要留在 `core/` 并迁到 `main_agent_react.py`（`run_executor._failure_code` 仍按它映射）。`MainAgentOutcome` 与 `needs_input_prompt` 属于旧 DAG 的一次性输出形态，随旧 DAG 一起删除；导入它们的测试改写为对新内核输出的等价断言，不允许直接删用例。
  - 同文件 `_main_task()`（~940 行）传入 `capability_id`／`capability_version`／`allowed_tools` 三个字面量字段，`MainAgentTask` 去字面量化后需改为“目录 + 目标”形态。
  - `tests/test_text_compare.py`、`tests/test_main_agent_runs_api.py` 直接构造 `CapabilityRegistry([TEXT_COMPARE_CAPABILITY])`——兼容层保留后预期不改，但必须实测确认。
  - 逐项枚举 `RunFailureCode → safe_message` 的映射测试与 `RunEventType` 封闭断言必须补 `MAIN_AGENT_BUDGET_EXHAUSTED`。
  - **直接构造 `RunApplicationService(...)` 的测试夹具**必须显式传 `capability_ids`／能力查询，否则事件里的 `capability_id` 会被白名单丢弃、交付复核无从查声明（缺省空集合是安全默认，不是测试便利）。涉及的夹具在 `test_main_agent_runtime.py` 的 `_run_service()` 与 `test_main_agent_runs_api.py`。
  - 凡必须改的既有用例，只做**等价改写**，不删断言、不放宽上限。
- 前端：`main-delivery-readers.test.ts`、`main-delivery.test.tsx`、`main-agent.test.tsx`、`trace-card.test.tsx`、`WorkbenchPage.test.tsx` 增量用例（含失败／取消终态下能力条存在、知识徽标禁词断言）。

**数据库变更**：无。**公开端点变更**：无（只加响应字段）。**事件类型**：无新增。**依赖**：无新增。

无功能改动：V1 Coordinator、领域 Agent、诊断链、`LegacyDiagnosisRunAdapter`、V1 默认录入、历史 fixture、审批／执行／Connector 全部不动。

## 4. 切片与验证（指引，不写死）

建议拆 5 片（与 Issue #137 的 S1–S5 同构，dev-plan 可再细化）：

1. **S1 契约与注册表**：`contract.py` / `registry.py` / `text_compare.py` 迁移 / `main_agent_model.py` 泛化决策形态。验收语义：两类能力可注册与解析；未知／重复／类型不符封闭失败；比较路径行为与 V2-0 一致。门禁：无（S1 只改后端内部形态，公开字段在 S4 才出现）。
2. **S2 知识源与知识能力**：`skill_source.py`、手册、`playbook` 声明、`load_skill` 决策与知识辅助交付。验收语义：选中即装、标注、不可用降级不伪造。门禁：**受管内容评审**（无凭据／无实时事实）。
3. **S3 ReAct 内核与预算**：`main_agent_react.py`、`main_agent_budget.py`、`capability_tools.py`、`observation.py`、`run_executor` 装配与逐步 yield、删除旧 DAG。验收语义：多步循环、预算封闭失败、取消粒度=step 边界且中途结果丢弃、工具失败码保真。门禁：无迁移。
4. **S4 公开投影与事件**：`schemas/resources/routes`、`RunApplicationService` 的 `capability_ids` 与能力归属查询、批量事件汇总、`services.py` 事件白名单、`generated.ts` 重生成。验收语义：加法字段（**不含 `catalog`**）、列表与详情同口径读事件（批量、无 N+1）、损坏行 `unavailable`、事件白名单。门禁：**公开 API 响应加法**（`MainAnswerDeliveryResource` 的接地字段、`DiagnosisRunResource` 的三个 `main_*` 字段），已确认（§6）后放行。
5. **S5 前端与端到端证据**：reader／面板／能力条（含失败／取消终态挂载）／Trace／录入提示、前端用例、浏览器两条路径复验。验收语义：AC3／AC12 界面证据、禁词断言、失败态可读能力归属、V1 回归。

每片门禁项：后端聚焦测试 + 全量；前端 typecheck／test／build；`ruff`／`mypy`／`git diff --check`；敏感字面量扫描。具体命令与执行顺序由 dev-plan 写定，本 Design 不列出。

**门禁项清单（本次修正后）**：

- **公开 API 响应加法**（已确认，§6）：`DiagnosisRunResource` 加 `main_capabilities`／`main_capabilities_status`／`main_knowledge`；`MainAnswerDeliveryResource` 加可选 `knowledge_grounding`。无新端点、无请求契约变化；**不包含 `catalog`**。
- **新失败码**的封闭枚举加法（已确认，§6）：`MAIN_AGENT_BUDGET_EXHAUSTED`。
- **不触及**：数据库迁移、新端点、新事件类型、Connector、凭据、权限／审批／动作、真实外部连接。

## 5. 风险、回滚与门禁

**技术风险与缓解**：

| 风险 | 缓解 |
|---|---|
| LangGraph 条件回边导致循环不收敛 | 预算在节点外判定、`recursion_limit` 设为 `2 * MAX_MAIN_DECISIONS + 4` 的硬护栏；任何未知状态返回 END 并安全失败 |
| 严格解析对旧行失效 | 接地字段全部可选；`MainAnswerDeliveryV1` 旧行缺省按普通回答处理；仓储往返测试覆盖旧 payload |
| 事件白名单遗漏导致能力标签丢失／任意字符串混入 | 白名单字段与前端 reader 由同一份封闭枚举表驱动测试；`capability_id` 经组合根导出的 id 集合过滤，缺省空集合时整字段丢弃 |
| 120 秒上界不严格 | 每次阻塞调用的有效超时 = `min(能力上限, remaining)`（模型 30 秒、工具 3 秒），调用前 `remaining <= 0` 直接失败，step 边界再检查 deadline（§2.8）；严格 ≤120 秒 + 同步调用调度误差 |
| 取消在模型调用中途不生效 | 明确粒度为 step 边界 + 中途结果丢弃；执行器逐步 yield 使检查点真实存在（§2.8、§6） |
| 列表批量事件查询导致列表变慢 | 只查本页 main_agent Run 的 `route_decided`／`agent_done` 行、单条 `IN (…)` 查询；事件损坏时降级为 `unavailable` 而非抛错；用例断言查询次数为 1 |
| 删除 `main_agent_graph.py` 波及既有用例 | S3 内一次性迁移：`MainAgentFailure` 迁入新内核，其余改写为等价断言；波及文件清单见 §3，不允许删用例 |
| 手册内容被改坏/含敏感内容 | 构建期固定摘要 + 单测断言摘要；评审门禁人工确认 |
| 合成能力测试掩盖真实分支 | 合成能力只进测试，不进组合根；只证明“选择→校验→执行→观察→复核”，不宣称“任意新交付形态免改内核”（§2.2）；再加一条“生产注册表无能力 id 分支”的静态断言 |

**回滚**：无数据库迁移、无新端点、无新事件类型。回滚 = 回退提交；公开字段为可选，旧前端与旧客户端读取不受影响。**已知数据兼容边界**：知识辅助回答会以新增的 `knowledge_grounding` 字段写入 `run_deliveries.payload`，而交付模型是严格解析（`extra="forbid"`），回滚后的旧代码不认识该字段，会把该行判为 `unavailable`（与 V2-0 损坏行同口径：安全不可用投影，不 500、不伪造）。比较与追问行不含新字段，回滚后照常可读。缓解：不混跑、合入前完成验收；记录在 Workpack 已知边界。

**门禁项**：

- 触及公开 API 响应字段（加法：`DiagnosisRunResource.main_*` 三项 + `MainAnswerDeliveryResource.knowledge_grounding`）——已确认（§6）。
- 触及 `RunFailureCode` 封闭枚举加值（`MAIN_AGENT_BUDGET_EXHAUSTED`）——已确认（§6）。
- 不触及：数据库迁移、新端点、新事件类型、Connector、凭据、权限／审批／动作、真实外部连接。
- 与 PRD 范围一致性：本 Design 未扩大 PRD 范围；§2.5 的“answer + 接地字段”、§2.3 不复用 `react_graph.py` 已经用户确认，无需回写 PRD。

## 6. 已确认的设计决策（2026-10-26）

以下八项已由用户确认，作为实现闸门；不再保留“待确认”状态。

1. **知识辅助回答交付形态**：采用“复用 `answer` + 可选 `knowledge_grounding`”，不新增交付 kind，不做数据库迁移，不改 `run_deliveries.kind` CHECK。
2. **知识判定与强制标注**：`answer` 决策 + 程序按本 Run 实际加载状态附加接地，不引入 `respond` 决策；助手消息由服务端加固定前缀“知识辅助回答 · 未读取实时数据”。**知识辅助回答继续以成对形式进入下一轮上下文，前缀保留**（不拆成只保留用户目标）。
3. **预算**：严格 ≤120 秒；每次模型调用超时 = `min(30 秒, 剩余预算)`；为维持严格上界，工具等待同样取 `min(3.0 秒, 剩余预算)`；剩余预算不足时不发起调用，直接 `BUDGET_EXHAUSTED`（§2.8）。
4. **新失败码**：允许新增 `MAIN_AGENT_BUDGET_EXHAUSTED`（封闭枚举加法）。
5. **Skill 来源**：只允许 `builtin`；其他来源不进入契约，为后续阶段留位但不实现。
6. **公开字段**：只加 `knowledge_grounding`、`main_capabilities`（`used`／`degraded`／`steps`）、`main_capabilities_status`、`main_knowledge`；**不加 `catalog`**。列表与详情返回同一组能力归属字段，批量读事件。
7. **`ops.readonly_playbook@1` 默认可见**：随 V2-1 上线，不做启用开关，作为 V2 显式入口下唯一的知识型能力出现在能力摘要里。
8. **取消粒度 = step 边界**：取消后不再启动新 step、不产出交付、无迟到写入；当前模型调用或工具等待不会被线程级打断，其结果在返回后丢弃；补四类取消测试（§3）。

**附带确认**：

- **能力版本激活策略**：同一 `capability_id` 只有最高已注册版本启用；**rerun 使用 rerun 时刻的启用版本**；快照不冻结能力清单；补“注册新版本后 rerun 使用新激活版本”的测试（§2.2、§2.8）。
- **输入契约范围**：V2-1 只支持 material slots；服务／资源输入留给 V2-2（§1、§2.2）。
- **回滚已知边界**：旧代码会把带 `knowledge_grounding` 的交付行判为 `unavailable`，该边界须写入 Workpack 已知边界（§5）。

> 实施时以符号名为准：本文引用的构造点行号来自 2026-10-26 的 main，行号漂移不改变设计。
