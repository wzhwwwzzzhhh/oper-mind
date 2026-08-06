# P6 知识库——目录内 Markdown 确定性检索 Design

> 状态：已确认
> 更新：2026-08-06
> 关联：`docs/prd/knowledge/P6-knowledge-retrieval.md`、`docs/产品定义.md` §2.2/§6、`docs/开发规范.md` §2/§4、`docs/正式产品架构设计-v1.md` §7.3、`backend/src/core/tool_gateway.py`、`backend/src/core/graph.py`、`backend/src/core/bootstrap.py`。

## 1. 目标与范围

在现有「Coordinator → 领域 Agent → ToolGateway → 受控 Tool」链路中新增一个只读知识检索能力：
在受管 Markdown 目录内做**确定性关键词/标题检索**，返回脱敏摘要，作为 Agent 工具接入现有链路。
不做向量库 / Embedding / RAG；不新增公开 API、前端直连接口与数据库迁移。

### 做什么

- 新增 `search_knowledge` Tool：按检索词在受管目录内匹配 Markdown 文档，返回脱敏摘要
  （文档标题 + 命中片段），按相关度排序，限制条数。
- 新增 knowledge 领域 Agent（`KnowledgeAgent`），继承 `BaseAgent`，沿用 DB/Server/Log 注册模式，
  经 `CoordinatorAgent.register_agent("knowledge", ...)` 接入路由。
- 知识目录经配置读取（环境变量 `OPERMIND_KNOWLEDGE_DIR` 优先，YAML `knowledge.directory` 兜底），
  默认空 → 未配置降级；不硬编码路径，不越权访问目录外文件。
- 确定性检索：标题命中优先、正文命中次数排序、命中片段截取；不引入任何向量/语义能力。
- 结果只进 Agent 上下文；Trace 经既有 `tool_invoked` 事件展示「知识检索」步骤与脱敏摘要
  （命中数与脱敏标题列表，不展示全文/目录结构/凭据），不新增事件字段契约。

### 明确不做

- 不做向量数据库 / Embedding / RAG / 语义检索（后续阶段，需单独 Design）。
- 不做文件管理 / 上传 / 编辑知识文档的前端或接口（只读检索）。
- 不授予对任意文件系统路径的访问；只检索配置的知识目录。
- 不检索非 Markdown 文件、二进制、隐藏文件、`.env`、`*.local.yaml`、密钥文件（含 `sk-` 内容）。
- 不接入外部知识源（网站、Confluence、工单系统等）；不发起任何网络访问。
- 不修改 `data/mock_db.py`、`data/scenarios.py` 与 S1–S4 评测路径。
- 不做知识写入 / 索引构建 / 持久化（本阶段为目录即时确定性检索）。
- 不新增公开 API、数据库表或迁移；不改变既有 Tool 契约与既有 Agent 行为。

## 2. 设计决策

### 2.1 配置

新增配置读取（沿用 `load_service_settings` 模式，环境变量优先于 YAML）：

| 配置 | 默认值 | 约束 |
|---|---:|---|
| `OPERMIND_KNOWLEDGE_DIR`（环境变量） | 空（未配置） | 指向受管 Markdown 目录；缺失/空串视为未配置 |
| `knowledge.directory`（YAML） | 无 | 同上 |

- 新增 `KnowledgeSettings(directory: str | None)` 与 `load_knowledge_settings()`：
  目录未配置返回 `None`；配置值不打印、不写入日志/Trace。
- Tool 构造时注入目录字符串；`None` 或目录不存在 → 诚实返回「知识目录未配置」。
- 不随应用启动创建目录、不写入任何文件；检索全链路只读。

### 2.2 检索 Tool 契约

新增 `SearchKnowledgeTool`（继承 `Tool`，命名 `search_knowledge`）：

| 参数 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `query` | string | 是 | 1–100 字符；拒绝路径注入字符（`/`、`\`、NUL、控制字符）与纯空白 |
| `limit` | integer | 否 | 1–10，默认 5 |

- 参数校验在 Tool `execute` 内实施（网关只校验 JSON Schema 类型），校验失败返回中文拒绝说明，不抛异常。
  检索词只作纯文本匹配（不进文件路径），因此路径防护不依赖字符集穷举，而由「目录来自配置 +
  解析根前缀校验」兜底（见 2.3）；字符集仅拒绝路径分隔与控制字符。
- 执行流程：
  1. 目录未配置/不存在 → 返回「知识目录未配置，请先配置 OPERMIND_KNOWLEDGE_DIR」。
  2. 扫描受管目录下 `.md` 文件（递归子目录，但排除隐藏文件/目录、符号链接与越界解析），
     并排除 `.env`、`*.local.yaml`、`*.key`、`*.pem`、`*.secret` 等凭据文件；
     无候选文档 → 返回「知识目录为空，无 Markdown 文档」。
  3. 逐文档读取（限长 256KB/文档，防止超大文件拖慢检索），计算命中：
     - 标题匹配：首个 `#` 标题行或文件名包含关键词 → 最高优先级；
     - 正文命中：统计关键词出现次数；
  4. 按相关度排序：标题命中优先，其次正文命中次数降序，再按文档名升序；截断到 `limit` 条。
  5. 每篇返回：文档标题 + 相对文件名（相对受管目录，不含绝对路径与上级目录结构）+ 最多 2 个命中片段
     （关键词前后各 60 字符，片段内换行折叠）。
  6. 无匹配 → 返回「未找到与检索词匹配的知识文档」。
- 输出为多行文本（供 Agent 阅读），首行为检索来源标注：
  `知识检索（受管目录确定性检索）：命中 N 篇文档`，后续行为每篇摘要；
  每行整体经网关 `desensitize` 兜底后再进入 Agent 上下文。

### 2.3 安全与脱敏

- **只读受管目录**：所有路径解析用 `Path.resolve()` 后必须以受管目录解析根为前缀，
  越界即拒绝；符号链接解析后越界即跳过；不返回目录树、绝对路径或上级结构。
- **凭据文件排除**：`.env`、`config.local.yaml`、`*.local.yaml`、密钥文件（`.key/.pem/.secret`）、
  隐藏文件一律不进候选集；内容含 `sk-` 的文档即使为 `.md`，其片段经网关脱敏规则兜底替换。
- **脱敏兜底**：Tool 输出与网关 `detail` 均经 `desensitize()`（网关最后一关），
  凭据/DSN/密钥模式一律替换为占位符。
- **不泄漏**：文档全文、目录结构、绝对路径、凭据不进 Trace、事件、日志与接口响应。
- **限时**：检索经 `ToolGateway` 限时执行（默认 3s），超时由网关返回 `timeout` 状态。

### 2.4 Agent 接入

- 新增 `KnowledgeAgent`（`backend/src/agents/knowledge_agent.py`），构造时接收 `knowledge_dir: str | None`，
  内部注册 `SearchKnowledgeTool`，系统提示词明确：
  「你是知识检索 Agent，从受管知识目录检索运维文档/SOP；只能使用提供的检索工具，不得访问目录外文件；
  未配置/无文档/无匹配时如实告知」。
- `bootstrap.build_coordinator` 读取 `load_knowledge_settings()`，创建 `KnowledgeAgent` 并
  `register_agent("knowledge", ...)`。
- 路由（`backend/src/core/graph.py`）：
  - LLM 路由 prompt 的领域取值与 target 枚举扩展为 `db|server|log|knowledge|null`；
  - 关键词兜底新增 `_KNOWLEDGE_KW`（如「知识、文档、SOP、手册、howto、操作指引、检索」），
    `_keyword_target` 支持返回 `knowledge`；关键词判定顺序沿用既有 db/server/log 优先级，
    knowledge 关键词在 log 之后判定（避免「日志分析 SOP」类查询被改道），并保留原上下文命中计数语义；
  - chain 固定顺序保持 server → db → log 不变（排障链路不混入知识检索）；
  - parallel 全面体检按既有逻辑遍历全部已注册 Agent（含 knowledge，无配置时如实返回未配置）。
- 既有 DB/Server/Log 路由行为不变；`direct` 命中 `knowledge` 时按既有 `direct_node` 执行。

### 2.5 Trace 展示

- 复用既有 `tool_invoked` 事件：`tool=search_knowledge`、`role=knowledge`、`status/detail/duration_ms` 按现有模型。
- 网关 `detail` 展示**脱敏摘要**：`知识检索命中 N 篇：<标题1>、<标题2>`（仅标题列表，无全文/片段/目录结构/凭据）；
  实现上为网关 `_finish("ok", ...)` 的 `detail` 支持工具可选提供的脱敏审计摘要
  （工具定义 `audit_summary()` 则用之，否则维持中性「调用 X 成功」，对既有工具零影响、向后兼容）。
- 命中片段与文档全文只存在于 Tool 输出（进入 Agent 上下文）与 `GatewayResult.output`，不进 Trace。
- 不新增前端字段契约；前端 Trace 按既有事件渲染「知识检索」步骤（工具名 + 状态 + 耗时 + 脱敏摘要 detail），
  前端无功能改动，仅回归。

### 2.6 诚实降级

| 场景 | 返回 |
|---|---|
| 目录未配置或不存在 | 「知识目录未配置」 |
| 目录为空（无候选 Markdown） | 「知识目录为空，无 Markdown 文档」 |
| 无匹配 | 「未找到与检索词匹配的知识文档」 |
| 参数非法 | 中文拒绝说明（非异常） |
| 检索超时 | 网关 `timeout` 状态 |

所有空态均为确定性返回，不抛异常、不伪造结果；检索来源始终标注为「受管知识目录」。

## 3. 文件改动面

### 后端

- `backend/src/config.py`：新增 `KnowledgeSettings` 与 `load_knowledge_settings()`（`OPERMIND_KNOWLEDGE_DIR` / `knowledge.directory`）。
- `backend/src/tools/knowledge_tools.py`：新增（`SearchKnowledgeTool`）。
- `backend/src/agents/knowledge_agent.py`：新增（`KnowledgeAgent`）。
- `backend/src/core/bootstrap.py`：装配并注册 `knowledge` Agent。
- `backend/src/core/graph.py`：LLM 路由 prompt 与关键词兜底支持 `knowledge` 目标。
- `backend/src/core/tool_gateway.py`：`_finish("ok", ...)` 支持工具可选 `audit_summary()` 作为脱敏 detail，
  缺省维持中性文案，对既有工具零影响。
- 测试：`backend/tests/test_knowledge_tool.py`（新增）、`backend/tests/test_knowledge_agent.py`（新增），
  以及既有 `test_tool_gateway.py`/`test_diagnosis.py` 仅回归。

### 前端

- 无功能改动；仅回归 `npm run typecheck` / `npm run test` / `npm run build`。

### 工作包文档（实施时）

- `docs/workpack/P6-knowledge-retrieval/plan.md`、`review.md`、`evidence.md`；`docs/workpack/README.md` 登记。

## 4. 切片与验证

### S1：检索 Tool 与配置

- 覆盖 PRD AC1、AC2、AC3（命中返回/相关度排序/limit 截断）、AC4、AC5、AC6。
- 验证：未配置/不存在目录、空目录、无匹配、路径逃逸拒绝（`../`、绝对路径、符号链接越界）、
  凭据文件排除、片段脱敏、limit 截断与相关度排序。
- 执行：`backend/` 下 `..\.venv\Scripts\python.exe -m pytest tests/test_knowledge_tool.py -q`。

### S2：KnowledgeAgent 与路由接入

- 覆盖 PRD AC3、AC7。
- 验证：Tool 经 `ToolGateway` 白名单准入/限时/脱敏；knowledge 路由（direct/parallel）、
  检索结果进入 Agent 上下文并可被引用；mock LLM 下关键词路由确定性。
- 执行：`..\.venv\Scripts\python.exe -m pytest tests/test_knowledge_agent.py tests/test_diagnosis.py -q`。

### S3：全量回归

- 覆盖 PRD AC8、AC9 与 DoD。
- 验证：Trace 事件脱敏（detail 为脱敏标题列表，无全文/目录/凭据）；mock 评测 S1–S4 与既有后端测试全绿
  （含「既有关键词路由结果不变」的显式回归断言：S1–S4 评测文本命中 knowledge 关键词不得改道）；
  前端 `typecheck`/`test`/`build` 通过；`git diff --check` 通过；
  diff 无 DSN、密码、`sk-`、原始异常与 mock 数据源改动。

## 5. 风险、回滚与门禁

- 检索为本地目录只读操作，无外部网络；风险集中于路径逃逸与凭据泄漏，已由「解析根前缀校验 +
  凭据文件排除 + 网关脱敏兜底 + 测试锁定」四层防护。
- 超大/极多文档的性能：逐文档限长读取 + 网关限时 + 返回条数上限；不缓存、不建索引（诚实即时检索）。
- 回滚：本切片不涉及迁移与公开 API，回滚即移除新增 Tool/Agent 注册与路由枚举，既有链路不受影响。
- Review 必须确认：配置命名、Tool 参数契约、路径防护、脱敏规则、Agent 注册方式与路由枚举边界后，
  才能进入 workpack 实施。
- 门禁：新增 Tool/能力需 Design → Review → 用户确认；确认后更新本 Design 状态为「已确认」，
  再创建 `docs/workpack/P6-knowledge-retrieval/plan.md`。

## 6. 待用户确认的设计决策

1. 是否确认知识目录配置命名 `OPERMIND_KNOWLEDGE_DIR`（YAML 键 `knowledge.directory`），默认空 → 未配置。
2. 是否确认新建独立 `KnowledgeAgent` 并注册到 Coordinator（而非复用现有 Agent 路由增强）。
3. 是否确认检索范围为受管目录内递归 `.md`（排除隐藏文件/符号链接越界/凭据文件），每文档读取限长 256KB。
4. 是否确认返回内容为「标题 + 相对文件名 + 最多 2 个命中片段（前后各 60 字符）」，不含绝对路径与目录结构。
5. 是否确认 Trace 复用既有 `tool_invoked` 事件，detail 展示网关支持的脱敏审计摘要（工具可选
   `audit_summary()`，缺省中性）——前端零功能改动，仅回归。
6. 是否确认本 Design Review 通过后，将 P6 PRD 状态保持「已确认」并直接进入 workpack 实现。
