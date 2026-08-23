# P8 Agent 运行真实性与评测基线 · Design

> 状态：已确认（独立 Review PASS，无 P0–P3；用户确认 9 项设计决策）
> 更新：2026-08-23
> 关联：`docs/prd/agent-runtime/P8-agent-runtime-truthfulness-evaluation.md`（已确认，issue #98）、
> `docs/产品定义.md`（§2.2、§4、§5）、`docs/路线图.md`（体验驱动完善）、
> `docs/开发规范.md`（§2、§5、§6、§7.2）、`docs/架构与开发路径.md`、
> `backend/src/core/{agent,llm,graph,coordinator,tool_gateway}.py`、
> `backend/src/core/{debate,reflection}.py`、`backend/src/tools/server_tools.py`、
> `backend/src/tools/db_tools.py`、`backend/src/agents/report_agent.py`、
> `backend/src/infrastructure/diagnosis/coordinator_executor.py`、`data/scenarios.py`。

## 1. 目标与范围

### 一句话目标

在不改变 real 模式路由顺序、公开 API 或持久化契约的前提下，把现有 mock 链路收敛为“由当前
Agent 获准工具菜单驱动、按角色与场景返回、质量节点按前置事实运行”的确定性实现；同时移除
Server real 降级中的固定假值，并用 pytest 场景矩阵建立可重复、可分类失败的行为评测门禁。

### 做什么

1. mock LLM 只从本次 `tools` 参数提供的已注册工具中做确定性选择；DB、Server、Log、Knowledge
   分别产生角色化、带“模拟场景”标识且与工具结果一致的结论，不再共享固定数据库答案；DB mock
   事实也统一进入显式场景，不再从独立 `data.mock_db` 或场景外默认数字补造。
2. mock 路由对无领域匹配的问题返回“无适用 Agent / 无证据”，不再默认分派 DB；real 模式既有
   LLM 路由、关键词兜底、direct / chain / parallel 顺序保持不变。
3. mock 冲突检查、Debate、Reflection 使用本次角色结论与证据状态做确定性判断；未满足前置条件时
   公开状态为 skipped/未执行，失败为 failed/error，不再无条件写“通过”。
4. Server 工具只有在 `data.scenarios` 显式激活时返回确定性 mock 指标；real 模式依赖缺失、采集异常
   或超时统一返回中性的不可用状态，不返回固定 CPU、内存、磁盘、进程或网络数值。
5. 收紧公开报告与 Trace：报告不拼接原始 query 或内部 thinking，并经过确定性公开投影；内部记录
   不保存工具实参或原始输出；执行异常只输出安全错误码/文案；Trace 只保留既有角色、节点、状态、
   耗时和脱敏摘要白名单。
6. 建立无需真实外部资源的评测矩阵，覆盖四个单领域场景、跨领域、无匹配、工具拒绝/不可用、
   direct/chain/parallel、质量节点、安全投影、重复运行快照与至少一个可被门禁捕获的负向样例。
7. 让现有会话 TraceCard 消费 `unavailable/skipped/failed` 与 conflict/debate/reflection 安全事件，
   不再把不可用工具统计为“全部通过”，也不再丢弃质量节点状态。

### 明确不做

- 不新增 Agent、Tool、Connector、服务类型、真实外部数据源、网络或文件系统能力。
- 不改变 real 模式的路由策略、Agent 顺序或 Knowledge 在 chain 中的参与规则；不接线 `judge_llm`。
- 不新增评测 API、页面、CLI/独立 Runner、数据库字段、迁移、配置项或持久化记录。
- 不从报告正文推断 severity、root causes、evidence、recommendations 等结构化事实。
- 不实现长期记忆、RAG、向量检索、MCP、任意 SQL/Shell/DDL/DML 或高风险动作。
- 不把一次真实外部环境验证作为门禁；本工作包不访问任何真实服务或凭据。

### 主脊与门禁判断

本设计修复既有“Run → Coordinator → 领域 Agent → ToolGateway → Tool → Report/Trace”主脊中的
真实性与安全投影，不创建旁路。它会修正 mock 下的多 Agent 与质量节点语义，命中多 Agent 编排
Design 门；但不命中新公开 API、迁移、Connector、真实连接、凭据、权限、审批/执行或破坏性变更。

## 2. 设计决策

### 2.1 角色化 mock 由获准工具菜单驱动

新增 `backend/src/core/mock_runtime.py`，集中承载 mock 专属的确定性决策，不把角色判断散落到各
Agent 或 Tool。模块使用 `Literal` / `TypedDict` 定义角色、工具决策和质量状态，核心输入仅为：

- 本次 `LLMClient.chat(..., tools=...)` 收到的工具 schema；
- 已裁剪的用户问题；
- 当前工具返回的脱敏文本；
- `data.scenarios.get_active_scenario()` 的显式 mock 场景事实。

角色由**工具名集合**识别，而不是从 system prompt、Agent 类名或任意全局注册表猜测。每个角色使用
完整且互斥的工具 allowlist；输入菜单中的全部工具必须属于同一个 allowlist 且至少命中一个工具，
空菜单、未知工具或同时命中多个角色一律 fail closed 为“无适用角色/工具”：

| 工具菜单特征 | 角色 | 可选择工具 |
|---|---|---|
| `explain_sql` / `show_index` / `show_create_table` / `check_lock_status` / `check_connection_pool` | db | 仅当前 DB 菜单中的工具 |
| `check_cpu` / `check_memory` / `check_disk` / `check_process` / `check_network` | server | 仅当前 Server 菜单中的工具 |
| `search_logs` / `aggregate_errors` / `query_slow_log` | log | 仅当前 Log 菜单中的工具 |
| `search_knowledge` | knowledge | 仅当前 Knowledge 菜单中的工具 |

确定性规划器先按问题关键词选择一个适用工具；没有精确关键词时，只在“角色识别成功 + 工具存在于
本次菜单 + 当前场景显式提供该类事实”三项都满足时选择本角色安全默认只读工具。规划器在返回 tool
call 前再次校验工具名和 schema；无法构造安全参数、菜单歧义或场景没有对应事实时不调用工具，返回
“无适用工具/无证据”。因此 mock 模型不可能请求另一个角色的工具，也不能靠默认工具补造场景事实。

#### DB mock 事实收敛到场景

`data/scenarios.py` 为 `Scenario` 增加冻结的 `ScenarioDatabaseFacts`，显式承载可选的 EXPLAIN/索引/
表结构/锁/连接池 mock 事实；缺省为 `None`，表示场景未提供该类证据，不等于“健康”或零值。

- S1 只登记既有缺索引、连接池和相关只读事实；S4 只登记连接上限事实；
- S2/S3 不登记 DB 事实，DB Agent 在跨域场景中返回无证据，不调用 DB 默认工具；
- 锁事实未登记时返回“当前模拟场景未提供锁事实”，不得补成“无锁等待”；
- `ExplainTool`、`ShowIndexTool`、`ShowCreateTableTool`、`CheckLockStatusTool`、
  `CheckConnectionPoolTool` 的 mock 分支只读上述场景事实，停止依赖 `data.mock_db` 并删除场景外
  fallback 数字；`data.mock_db` 文件若仍被其他测试/兼容入口引用则保留，不顺带清理；
- real 分支及其只读 SQL、服务绑定、超时和错误映射完全不改。

`ScenarioDatabaseFacts` 使用冻结 dataclass/Pydantic 值对象，不把跨模块协议降级为隐式字典。既有 S1/S4
工具测试更新为显式事实断言，S2/S3 增加“无事实即无证据”的回归。

工具返回后，mock 结论由“角色 + 场景 + 工具结果类别”生成，不回显原始工具输出：

- 结论固定带“模拟场景”与角色标识，避免被误认为 real；
- 未配置、无匹配、拒绝、超时、不可用和错误分别映射为中性状态，不写健康或成功结论；
- DB / Server / Log 只陈述本领域观察，场景根因不在本域时明确“未发现本域根因/仅观察到症状”；
- Knowledge 只提取安全标题，不回显相对路径、受管目录或原始片段；
- 同一输入不使用随机数、当前时间或外部网络，文本顺序固定。

`backend/src/core/llm.py::_mock_chat` 只负责把既有消息格式委托给该策略；真实 OpenAI 调用分支不改。
`_mock_response` 既有死代码不在本工作包顺带清理，避免扩大 P0-6 范围。

### 2.2 路由与无匹配语义

`backend/src/core/graph.py` 保留 direct / chain / parallel 三种图和 real 分支原样。仅在 mock 且关键词
无法识别领域时，`target` 使用显式 `none`，direct 节点输出“无适用 Agent / 无证据”，不运行任何
领域 Agent；real 模式仍保留现有 LLM 决策失败后默认 DB 的兼容兜底。

chain 仍固定 `server → db → log`，parallel 仍使用已注册角色集合；Knowledge 不加入 chain。每个
参与 Agent 继续通过自己的 `ToolRegistry` 和独立 `ToolGateway` 执行，跨域协作不会共享工具菜单。

### 2.3 mock 质量节点使用证据前置条件

`mock_runtime.py` 同时提供纯函数质量策略；输入为本次按角色归属的结论、工具状态和报告，不读取
CoT、Prompt 或原始工具输出。

| 节点 | 触发前置 | mock 决策 | 公开状态 |
|---|---|---|---|
| conflict_check | parallel 且至少两个角色有可用证据 | 比较角色声明的根因域/事实兼容性；互补事实不算冲突 | `ok` + 有/无实质冲突 |
| debate | conflict_check 判定冲突 | 按证据可用性与场景事实生成固定顺序共识；不调用通用 canned 回复 | `ok`；异常为 `error` |
| reflection | 已生成非空报告且至少一个角色有可用证据 | 校验模拟标识、结论与证据状态、禁泄露词和无证据声明 | `ok` / `failed` |
| reflection | 无报告或无可用证据 | 不宣称通过，不触发修订 | `skipped` |

无匹配 direct 不发送 `agent_start`；`CoordinatorAgent._create_start_events` 仅在 target 为已注册角色时
创建启动事件。direct/chain 不进入 conflict_check、parallel 证据不足、parallel 无冲突三种情况，都在
现有 trace 中追加 `conflict_check` / `debate` 的 `skipped` 安全事件（复用现有 RunEventType，不新增
事件类型），明确具体未触发原因；真正进入节点才允许 `ok/failed/error`。mock Reflection 发现确定性
问题时仍沿用现有最多两次 report 修订边，但反馈为有限安全类别，不含内部推理。达到上限仍有问题时
公开为 failed，不改写成“复审通过”。real Debate/Reflection 的调用方式、顺序和模型不变。

为支持机器断言，图内 trace 字典可携带现有白名单字段 `status` 和安全 `detail`；不新增事件类型或
API 字段。`CoordinatorAgent._normalize_trace` 需保留已有 `role/status/duration_ms`，并继续丢弃其他键。

### 2.4 Server real 模式诚实降级

`backend/src/tools/server_tools.py` 保留五个现有 Tool 名称、schema 和 mock 返回格式。每个 Tool 统一遵循：

```text
active scenario 存在 → 返回标注清楚的确定性 mock 场景值
active scenario 不存在 → 尝试 psutil 真实采集
依赖缺失 / 权限失败 / 采集异常 / 超时 → 返回“<指标>不可用”，不含异常文本和任何固定数值
```

为避免“输出不可用但 Trace=status=ok”，`backend/src/core/tool_registry.py` 增加内部 Pydantic
`ToolExecutionResult(output, status, summary)`；既有返回 `str` 的 Tool 保持兼容并映射为 `ok`，Server
工具不可用时返回 `status=unavailable` 的结构化结果。`ToolGateway` 识别该结果并把 record.status、
安全 output 和 summary 原子映射；`ToolInvocation.status` 与既有事件 status 白名单增加
`unavailable`。因此 Coordinator Trace、`DiagnosisExecutionEvent.data` 和持久化 RunEvent 对同一次
调用都表达 unavailable，不依赖 LLM 理解字符串，也不显示“调用成功”。

异常类型可写安全 WARNING 日志，异常文本、主机路径、进程命令行不得写日志或返回。五个工具不新增
能力，也不改为调用新的 Connector；P6 `PsutilHostMetricsCollector` 的结构化服务监控链保持不变。

### 2.5 报告、错误与 Trace 的安全投影

新增 `backend/src/core/public_projection.py` 作为最终用户文本的确定性安全边界：

- `safe_request_topic(query)` 只按已知领域关键词输出“数据库/服务器/日志/知识/综合运维调查”，不把
  原始 query 交给 ReportAgent，因而 SQL、路径、DSN、密钥哨兵不能从“问题描述”回显；
- `safe_finding(text)` 先调用既有 `desensitize`，再删除 fenced code、SQL 语句、连接串、绝对路径和
  已知敏感键值，只保留有界中文安全摘要；清理后为空则用“该角色未返回可安全展示的结论”；
- `project_public_report(text)` 在 CoordinatorExecutor 写入 `DiagnosisExecutionResult.report` 前再次执行
  同一套脱敏/危险片段移除和长度收敛，形成纵深防御；不从文本生成结构化事实。

投影规则以 sentinel 测试锁定原始 SQL、Windows/Unix 路径、受管目录、DSN、API Key 格式、异常
堆栈和 Prompt/CoT 词；mock 与 real 报告走同一最终投影。投影不是任意内容白名单扩权，只会删除或
替换敏感片段；任何无法安全收敛的内容回退为中性报告，不原样持久化。

- `backend/src/core/agent.py` 的内部 `thinking_log` 只记录步骤号、工具名和受控状态，不再拼接工具实参
  或输出片段；该日志不进入公开结果。
- `backend/src/agents/report_agent.py` 接收 `safe_request_topic` 和逐角色 `safe_finding`，不再原样拼接
  query；`backend/src/core/graph.py` 不再传 `agent_thinking`，从用户报告移除“诊断链路”内部步骤。
- `backend/src/core/llm.py` 捕获真实模型异常时只返回安全错误码/文案，不把 `str(exception)` 交给
  BaseAgent、报告、事件或 API。
- `backend/src/core/coordinator.py` 捕获图执行异常时禁止 `LOGGER.exception`、traceback 和
  `str(exception)`；只以 WARNING 记录固定错误码 `DIAGNOSIS_FAILED` 与 `type(error).__name__`，流式
  error 继续返回既有安全码/文案。
- `backend/src/infrastructure/diagnosis/coordinator_executor.py` 对最终报告执行 `project_public_report`，
  并继续白名单映射；工具事件允许 `db/server/log/knowledge` 角色，质量事件只投影安全 summary/status。
  `application.services._safe_event_data` 的最终事件白名单不扩展任意键，只接受既有
  node/summary/role/status/duration/mode/service_id，但 status 允许集合显式增加 `unavailable`，避免在
  持久化边界把 ToolGateway 的诚实状态丢掉。
- 评测安全扫描覆盖 report、标准化 Trace、`DiagnosisExecutionEvent.data`、持久化后的公开资源、
  `caplog` 捕获日志和 pytest 失败输出；禁止词包含 Prompt/CoT、工具实参、原始异常、原始 SQL、
  受管目录路径、DSN 与 API Key 格式。异常注入用例的 message 同时包含上述哨兵，断言日志只出现
  固定错误码与异常类型，不出现 message 或 traceback。

公开 API schema、RunEventType 和数据库结构均不变；这里只修正既有字段实际表达的事实。

#### TraceCard 用户可见状态

`frontend/src/features/workbench/TraceCard.tsx` 扩展既有安全展示，不读取任何新字段：

- 状态闭集为 `ok/rejected/timeout/error/unavailable/skipped/failed`；`unavailable` 显示“不可用”并计入
  需关注，`skipped` 显示“未执行”但不算失败，`failed/error` 使用严重视觉等级；
- 可见事件增加 `conflict_checked/debate_round/reflection`，使用固定中文阶段名，只展示
  `data.summary/status/duration_ms` 白名单；不展示内部 node、Prompt、CoT 或原始输出；
- Knowledge 工具角色增加固定图标映射，未知角色继续使用中性图标；
- 头部汇总同时统计“需关注步骤”和“未执行质量步骤”。只有全部已执行工具均为 ok、且没有
  unavailable/failed/error/rejected/timeout 时才允许显示“工具调用全部通过”；存在 skipped 时另行标明
  “N 个质量步骤未执行”，不得把它折算成通过；
- `run_event_summary` 继续只读安全 summary；缺 summary 时用现有中性兜底，不显示任意 data。

`frontend/src/features/workbench/trace-card.test.tsx` 锁定 unavailable 不显示成功、skipped/failed 质量
节点可见、头部计数、固定中文标签、折叠可访问性和不渲染危险 data。样式优先复用现有 warn/danger，
仅为 skipped/unavailable 增加必要的中性/关注样式，不引入新页面或交互入口。

### 2.6 评测基线是 pytest 研发资产

评测不做产品端点或独立脚本。新增 `backend/tests/support/agent_runtime_evaluation.py`，以 Pydantic 或
TypedDict 定义规范化快照和失败类别；`backend/tests/test_agent_runtime_evaluation.py` 驱动真实
Coordinator/ToolGateway 的离线 mock 链路。

规范化快照只保留稳定事实：strategy、参与角色、每角色工具名/状态、脱敏证据摘要、质量节点状态、
最终报告与安全事件；明确剔除 run id、timestamp、duration。矩阵至少包含：

- DB、Server、Log、Knowledge 四个 direct 场景；
- 一个 chain 与一个 parallel 跨领域场景；
- 一个无匹配/无适用工具场景；
- 一个 ToolGateway 拒绝或工具不可用场景；
- 同一场景连续执行两次并比较规范化快照；
- 合成一份含跨角色工具、未标注 mock、伪成功或敏感文本的坏快照，断言评测器返回对应失败类别。

失败类别固定为 `routing`、`role_tool_boundary`、`evidence_origin`、`quality_state`、`truthfulness`、
`public_safety`、`determinism`，pytest 失败信息直接指出类别与角色/节点，不比较整段自由文本。
Knowledge 用临时受管 Markdown 目录，其他场景使用现有 `data/scenarios.py`；所有用例禁用长期记忆，
不连接真实模型、数据库、日志目录、主机或网络。

## 3. 文件改动面

### 后端生产代码

- **新增** `backend/src/core/mock_runtime.py`：完整角色工具 allowlist、确定性 tool call/结论、冲突/Debate/
  Reflection 纯函数与 TypedDict 状态。
- **新增** `backend/src/core/public_projection.py`：请求主题、领域结论与最终报告的确定性安全投影。
- **修改** `backend/src/core/llm.py`：mock 分支委托角色化策略；真实异常改为安全错误码/文案。
- **修改** `backend/src/core/agent.py`：内部步骤不记录工具实参/原始输出。
- **修改** `backend/src/core/graph.py`：mock 无匹配、质量策略与状态；报告不接收 thinking；real 图顺序不变。
- **修改** `backend/src/core/coordinator.py`：无匹配不发启动事件；标准化 Trace 保留白名单字段；
  图执行异常只记录固定错误码与异常类型，不记录 traceback/message。
- **修改** `backend/src/core/tool_registry.py`、`backend/src/core/tool_gateway.py`：内部结构化工具结果与
  `unavailable` 状态映射；既有字符串 Tool 兼容。
- **修改** `backend/src/tools/server_tools.py`：移除 real 模式固定假值，返回结构化 unavailable。
- **修改** `data/scenarios.py`、`backend/src/tools/db_tools.py`：DB mock 显式场景事实；无事实不补造。
- **修改** `backend/src/agents/report_agent.py`：不原样回显 query/领域文本，不接收公开 thinking。
- **修改** `backend/src/infrastructure/diagnosis/coordinator_executor.py`：Knowledge 角色和质量状态的安全投影。
- **修改** `backend/src/application/services.py`：仅在现有 `_safe_event_data` 白名单中允许 Knowledge 角色；
  status 增加 `unavailable`；不增加新字段。

### 后端测试

- **新增** `backend/tests/support/__init__.py` 与
  `backend/tests/support/agent_runtime_evaluation.py`：规范化快照、分类校验器。
- **新增** `backend/tests/test_agent_runtime_evaluation.py`：完整确定性场景矩阵、重复快照和负向捕获。
- **修改** `backend/tests/test_llm_client.py`：角色工具选择、无跨角色调用、安全异常回归。
- **修改** `backend/tests/test_db_tools_real.py`、`backend/tests/test_db_lock_pool_tools.py`：S1/S4 显式
  DB 事实与 S2/S3 无事实回归。
- **修改** `backend/tests/test_server_tools.py`：mock 保持与场景一致，real 依赖/采集失败不再返回固定数值。
- **修改** `backend/tests/test_p2_diagnosis_adapter.py`、`backend/tests/test_p2b_tool_trace.py`：质量状态、
  Knowledge 角色与公开投影白名单。
- **按需修改** `backend/tests/test_knowledge_agent.py`、`backend/tests/test_tool_gateway.py`：无匹配、拒绝、
  脱敏与目录路径不进入公开快照。
- **新增/修改** 报告与执行器测试：query/结论 sentinel 经最终投影后不进入报告、持久化 Result 或资源。
- **新增/修改** Coordinator 安全日志测试：用 `caplog` 注入含 SQL/路径/DSN/密钥格式的异常，断言日志、
  流式 error、Trace、报告、持久化资源和测试输出均不含哨兵或 traceback。

### 前端

- **修改** `frontend/src/features/workbench/TraceCard.tsx`：消费 unavailable 与质量节点安全状态/摘要，
  修正头部诚实汇总，增加 Knowledge 角色图标。
- **修改** `frontend/src/features/workbench/trace-card.test.tsx`：状态映射、质量节点可见性、计数与安全 data。
- **按需修改** `frontend/src/styles/workbench.css`：unavailable/skipped 徽标视觉等级；复用既有样式优先。

### 文档

- `docs/prd/agent-runtime/P8-agent-runtime-truthfulness-evaluation.md` 与两级索引：确认后推进进行中，
  交付时逐项回填 AC/DoD 与完成状态。
- `docs/workpack/P8-agent-runtime-truthfulness-evaluation/{plan,evidence,review}.md`、
  `docs/workpack/README.md`：执行计划、证据和独立代码 Review。
- `docs/完善清单.md`：P0-3、P1-2 只在评测和相应回归实测通过后标 ✅。
- `docs/跑通验证.md`：C3 只在 mock 全链路复验通过后移入已解决，并记录验证事实。
- `docs/路线图.md`：交付时登记 issue #98 / PR。

### 明确无改动

- 无新前端页面、路由、API 字段或业务操作；只修正既有 TraceCard 对既有事件/data 的安全消费。
- 无公开 API/OpenAPI、`frontend/src/api/v1/generated.ts`、数据库模型或迁移改动。
- 无配置、环境变量、Provider、`judge_llm`、Connector、服务注册、审批/执行或真实资源改动。

## 4. 切片与验证（指引）

建议拆 2 个紧密验收单元：

1. mock 运行真实性、质量状态与 Trace 消费：角色化工具选择/结论、无匹配、质量前置、安全投影，
   以及前端 unavailable/skipped/failed 展示；验收 AC1–AC6、AC10，并确认 real 路由顺序未改。
2. Server/DB 诚实事实与评测门禁：移除固定 Server 假值和场景外 DB 补造，建立场景矩阵、重复快照、
   负向分类与既有工具回归；验收 AC7–AC9、AC11–AC13。

dev-plan 应为每个单元指定后端聚焦/全量测试，以及前端 TraceCard 聚焦测试、typecheck/test/build 门禁。

## 5. 风险、回滚与门禁

| 风险 | 缓解 |
|---|---|
| mock 工具规划再次跨角色 | 工具名必须来自当前 schema 菜单；评测直接断言每角色允许集合 |
| 不同场景仍复用固定 DB 结论 | 结论生成必须输入角色、场景和工具结果类别；四角色 direct 快照分别锁定 |
| 互补结论被误判为冲突 | mock 质量策略比较根因域/证据兼容性，不比较文本前缀 |
| 无证据仍显示 Reflection 通过 | 无可用证据固定 `skipped`；负向样例锁定伪成功分类 |
| 报告或事件泄露工具参数/原始输出 | thinking 不进报告、内部日志不存参数/输出、执行器二次白名单、安全扫描 |
| 图层异常经 traceback 泄露 message | Coordinator 禁用 LOGGER.exception，只记固定错误码 + 异常类型；caplog 哨兵回归 |
| real 行为被 mock 重构改变 | 所有新策略仅在 `_is_mock` 分支调用；real 路由/顺序/模型质量组件回归 |
| Server 降级文案被误当工具成功 | 结构化 ToolExecutionResult 映射 unavailable；Trace/事件/报告三层断言一致 |
| 前端丢弃 unavailable/质量状态 | TraceCard 扩展固定状态/事件闭集，头部关注与 skipped 分开计数 |
| 全局 active scenario 污染用例 | 评测串行设置并在 fixture finally 清除；每用例新建 Coordinator、关闭长期记忆 |

- 回滚：可移除 `mock_runtime.py` 委托和评测矩阵，恢复原 real 质量分支；Server 中性 unavailable 与
  报告安全投影属于不可回退的安全修复，即使回滚 mock 重构也必须保留。无迁移、新配置或公开契约
  需要数据回滚。
- 门禁：Design 独立 Review PASS + 用户确认后才开发；实现后需独立代码 Review、后端全量测试、前端
  既有门禁（若仓库流程要求）、`git diff --check` 与敏感字面量检查。

## 6. 待用户确认的设计决策

1. 评测只作为 pytest 研发门禁，不新增公开 API、页面、CLI 或独立 Runner。
2. mock 角色由本次获准工具 schema 的完整互斥 allowlist 识别，空/未知/混合菜单 fail closed；规划器
   只能在当前场景显式有事实时从该菜单选工具，不靠 system prompt 猜角色。
3. mock 质量节点使用确定性证据前置策略：无足够证据时 skipped，只有实质冲突才触发 Debate，
   Reflection 不再无条件通过；real 质量链路不改。
4. 无领域匹配仅在 mock 下返回“无适用 Agent / 无证据”；real 模式保留现有默认 DB 兼容兜底。
5. DB mock 的 EXPLAIN/索引/表结构/锁/连接池事实统一进入显式场景；没有事实即无证据，DB Tool
   mock 分支停止依赖 `data.mock_db`/默认数字补造，real DB 工具不改。
6. Server 五个既有 Tool 保持名称与 schema；内部增加结构化 `unavailable` 结果，任何依赖/采集失败
   都在 Trace/事件/结论中表达不可用，mock 值只在显式场景激活时存在。
7. 公开报告不回显原始 query，领域结论和最终报告走确定性安全投影；移除 thinking/工具参数/输出，
   真实模型异常改安全码，不新增 API 字段。
8. 现有 TraceCard 增加 unavailable 与 conflict/debate/reflection 的安全状态消费；skipped 明示未执行，
   unavailable/failed/error 计入需关注，只有真实全 ok 才显示工具调用全部通过。
9. Coordinator 图执行异常日志只记录固定错误码和异常类型，不记录 traceback 或异常 message；
   `caplog` 安全扫描与报告/Trace/持久化资源使用同一组敏感哨兵。
