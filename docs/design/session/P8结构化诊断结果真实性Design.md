# P8 结构化诊断结果真实性——事实来源与安全呈现 Design

> 状态：待用户确认（Design Review PASS，无 P0/P1；2 项 P2 已在本文收口）
> 更新：2026-08-27
> 关联：issue #101、已确认 PRD
> `docs/prd/session/structured-diagnosis-result-truthfulness.md`、
> `docs/产品定义.md`（§2.1、§5）、`docs/路线图.md`（体验驱动完善）、
> `docs/开发规范.md`（§2、§5、§6、§7.2）、
> `docs/prd/approval/P5-controlled-action-real.md`、
> `docs/design/approval/P5受控动作联合索引Design.md`。

## 1. 目标与边界

### 一句话目标

只在既有受控靶场联合索引动作模板被确定性只读事实完整命中时，组装可追溯的影响面与处置建议；
任何事实不足、规则不匹配或只有报告散文的情况都保守留空。前端使用同一个白名单 Markdown 组件
安全呈现助手回答与报告全文，并把全空结构化区收敛为一个诚实空态。

### 做什么

1. 抽出单一的受控动作模板目录，统一固定 action id、目标身份、建议投影和影响投影；既有提案生成与
   结果组装使用同一条精确匹配规则，避免两套触发条件漂移。
2. 只有缺索引信号、关联根因和至少三条真实数据库证据全部一致时，才派生一条建议和一个影响面；
   删除 assembler 为凑数量补写重复证据的行为。
3. 建议通过既有 `evidence_ids` 绑定只读证据，使用由 action id 派生的稳定 UUID，并在安全描述中展示
   既有公开 action id 作为模板来源；不新增公开字段。
4. 新增通用 `SafeMarkdown`，用于助手普通回复、调查回答和结构化结果内的报告全文；支持常用排版，
   禁止原始 HTML、可点击链接、脚本协议和图片加载。
5. 当 root causes / impact / recommendations / evidence / agent summaries / risks 全部为空时，只展示
   “只读调查未产生可展示的结构化证据”，不再逐区输出六个空占位；摘要和报告仍可展示。
6. 补后端负向真实性测试、前端渲染与注入测试，并在真实受控靶场复核后按事实更新完善清单和跑通记录。

### 明确不做

- 不从 `summary`、`report_markdown`、Trace 或 Agent 文本提取根因、影响或建议。
- 不新增/修改公开 API 字段，不迁移数据库，不新增 Connector、服务类型、环境变量或真实连接。
- 不改变 Coordinator、领域 Agent、Debate、Reflection、Report Agent 的顺序或语义。
- 不新增动作模板；只复用 `postgres.orders_compound_index_rebuild.v1`。
- 不自动创建、批准或执行提案；建议只是说明性结果，提案仍由既有服务器流程独立生成。
- 不渲染原始 HTML，不提供 Markdown 外链跳转，不加载 Markdown 图片。
- 未经用户另行明确授权，不连接、修改或清理真实受控靶场资源。

## 2. 设计决策

### 2.1 单一动作模板目录

新增纯确定性模块 `src/application/controlled_action_catalog.py`，包含：

- `COMPOUND_INDEX_ACTION_ID` 与固定目标常量；
- 只读的 `ControlledActionTemplate` 数据模型；
- 固定建议标题、描述、优先级、风险、审批要求和影响范围模板；
- `match_compound_index_facts(...)` 精确匹配函数；
- `recommendation_id(action_id)` 的稳定 UUID 派生函数。

既有 `action_services.py` 继续重导出当前常量，保持内部导入与测试兼容；收集器、结果组装器和提案服务
改为从目录读取同一个模板。目录是代码内白名单，不从配置、数据库、LLM 或请求参数动态扩展。

模板匹配必须同时满足：

1. `MissingIndexSignal` 的 service/schema/table/columns/index_name 与模板完全相等；
2. 恰有可识别根因携带同一 signal；
3. 根因引用的证据 id 均真实存在；
4. 至少三条被引用证据来自 `source_type=database`、`source_name=postgres_read_only`；
5. 证据标题集合包含“目标表存在”“固定联合索引缺失”“顺序扫描信号”；
6. 不读取报告正文、Agent 摘要或 Trace 内容参与匹配。

任何条件失败都返回 `None`，而不是降级为“可能匹配”。提案服务和结果组装器都只消费这个匹配结果，
从而锁定“有建议即可生成同源提案；无完整事实则两者都不触发”的一致性。

### 2.2 建议与影响面的安全投影

命中模板时，结果组装器生成一条既有 `RecommendationResource` 形状的记录：

| 字段 | 来源与语义 |
|---|---|
| `id` | `uuid5` 由固定 action id 派生；跨 Run 稳定，便于审计确认模板来源，不承担实例主键语义 |
| `title` | 代码内模板固定中文标题，不含 SQL |
| `description` | 固定安全摘要，并明确“来源：受控动作模板 `postgres.orders_compound_index_rebuild.v1`”；不含目标 schema/table/columns/index_name |
| `priority` | 模板固定 `p1` |
| `risk_level` | 模板固定 `medium` |
| `requires_approval` | 固定 `true`，只说明动作风险，不改变提案状态机 |
| `evidence_ids` | 精确匹配的三类只读数据库证据 id |

`impact` 只表达已观察到的技术范围，不推断业务影响：

- `summary`：只读事实确认受控靶场固定数据库对象存在缺索引与顺序扫描信号；未采集业务调用方影响；
- `affected_services`：只包含信号中的既有服务 id `postgres-target`；
- `affected_scope`：固定为“受控靶场固定数据库对象（不代表业务影响范围）”。

无完整匹配时 `recommendations=[]`、`impact=None`、`requires_approval=False`。其中
`requires_approval` 表示当前结构化结果存在可审批模板建议，不再只因一个未经证据闭合的 signal 为真。

公开追溯链为：建议安全来源文案 → action id；建议 `evidence_ids` → evidence 的
`source_type/source_name/title/summary`；root cause `evidence_ids` → 同一证据集合。现有公开字段已足够，
因此不增加 `source_template_id` 字段，也不修改 OpenAPI。

### 2.3 停止伪补证据

删除 `KernelReportResultAssembler` 中 `while len(evidence) < 3` 的证据补齐。真实
`PostgresMissingIndexCollector` 本来就一次生成三条不同的确定性事实；测试夹具也必须显式提供这些事实。

- signal 存在但证据不足：保留收集器真正返回的 root cause/evidence，建议与影响面留空，不生成提案；
- 只有报告声称“缺索引”：全部结构化字段保持空；
- signal 与根因、证据不一致：模板匹配失败关闭；
- 不为满足动作门槛复制、猜测或补写任何 EvidenceFact。

### 2.4 安全 Markdown 组件

新增 `frontend/src/features/workbench/SafeMarkdown.tsx`，依赖 `react-markdown`、`remark-gfm` 和
`rehype-sanitize`。固定安全策略：

- 允许：h1–h6、段落、粗体/斜体/删除线、列表、引用、行内/块代码、表格、分隔线、换行；
- 原始 HTML：`skipHtml=true`，不启用 `rehype-raw`；`script/style/iframe/svg/form` 等不会进入 DOM；
- 链接：Markdown 链接只渲染为不可点击文本，不保留 `href/target`；因此 `javascript:`、`data:`、
  外站追踪链接都不能导航；
- 图片：只渲染脱敏 alt 文案，不创建 `img`，不读取 `src`，不会发起外部请求；
- sanitize schema 只允许上述元素与代码语言 class，不允许 `on*`、style、src、href 或任意 data 属性；
- 内容为空时不渲染空容器；组件异常由 React 错误边界回退到同一输入的纯文本节点，不使用 HTML API。

使用点仅限后端已作为用户可见内容返回的：

1. 普通 assistant 消息；
2. 调查关联 assistant 输出；
3. `DiagnosisResultPanel` 的 `report_markdown`。

用户消息和系统消息继续纯文本，避免把用户输入或系统提示扩大为富文本面。知识库页面不在本 issue 范围。

### 2.5 报告与结构化空态

- `DiagnosisResultPanel` 保留摘要、严重度、置信度和结果关联。
- `report_markdown` 非空时增加“完整诊断报告”折叠区，默认收起；即使当前 `summary` 与报告相同，
  也不在首屏重复长文。展开后用 `SafeMarkdown` 完整呈现。
- 定义 `has_structured_details`：六类字段任一非空即为真（impact 非 null 或任一数组非空）。
- 全部为空时只显示一个面板级空态：“只读调查未产生可展示的结构化证据”；不渲染六个空 section。
- 部分有值时只渲染有值的 section；缺失 section 直接省略，不用“服务未返回……”制造噪音。
- `impact.affected_scope` 或 `affected_services` 局部为空时，改为“未采集影响范围/受影响服务”，明确
  是事实未采集，而不是网络或服务端异常。
- 建议旁固定显示“说明性建议，不等同于动作提案”；既有 ActionProposalPanel 继续独立展示审批状态。

### 2.6 负向真实性与安全门禁

后端测试至少覆盖：

- 完整固定事实命中 → 一条建议、impact、稳定模板 UUID、正确 evidence ids；
- 无 investigation、无 signal、证据少于三条、错误 source、缺标题、根因引用不一致、目标任一字段不匹配
  → 建议空、impact null、requires_approval false；
- 报告正文包含 action id、缺索引、影响面、甚至伪造建议，但无确定性事实 → 仍为空；
- 报告正文与确定性事实相冲突 → 结构化结果只服从事实；
- 提案匹配与结果匹配共用同一目录规则，不能一边命中、一边不命中；
- 结果资源序列化不出现额外字段、SQL、凭据或目标对象详情。

前端测试至少覆盖：

- 回答和报告的标题、列表、代码、表格正常渲染；
- `<script>`、事件属性、`javascript:`、`data:`、外链、Markdown 图片均无可执行/可导航/可加载节点；
- 报告默认折叠、可展开且内容完整；
- 全空只有一个诚实空态，部分有值时只显示有值板块；
- impact/recommendations 既有显示、建议/提案区别、协议 reader 错误关闭保持回归。

### 2.7 真实链复核边界

自动化测试全部使用确定性 fake，不访问外部资源。代码和自动化通过后，AC8 还需要一次真实受控靶场复核：

1. 用户另行明确授权目标仅为 `postgres-target` / 本机映射端口和固定对象；
2. 若当前固定索引存在，删除索引属于真实写操作，必须在执行前再次明确说明目标与可恢复方式并取得确认；
3. 调查本身只读；验证 recommendations / impact / evidence / root cause 的公开投影；
4. 不批准或执行提案也能验证本 issue 的结构化结果；如需恢复索引，只能复用既有提案 → 人工批准 →
   二次确认 → 白名单执行 → 独立 Verify，不能用通用 SQL 旁路；
5. 不输出 DSN、凭据、原始 SQL、原始 EXPLAIN 或原始异常；只写脱敏结论。

未完成真实链前，完善清单最多标 `⏳`；只有实测通过后才标 `✅`。

## 3. 文件改动面

### 后端

- `backend/src/application/controlled_action_catalog.py`（新增）：模板、稳定 id 与唯一匹配规则。
- `backend/src/application/action_services.py`：复用目录匹配；兼容重导出现有常量。
- `backend/src/infrastructure/diagnosis/postgres_missing_index.py`：从目录读取固定模板常量。
- `backend/src/infrastructure/diagnosis/result_assembler.py`：派生 impact/recommendations，删除证据补齐。
- `backend/tests/test_p5_controlled_action.py`：完整事实、匹配一致性和负向真实性用例。
- 视实现聚焦度可新增 `backend/tests/test_structured_result_truthfulness.py`，不修改生产外部依赖。

### 前端

- `frontend/package.json`、`frontend/package-lock.json`：Markdown 安全渲染依赖。
- `frontend/src/features/workbench/SafeMarkdown.tsx`（新增）及测试。
- `frontend/src/features/workbench/WorkbenchPage.tsx`：assistant 消息接入安全 Markdown。
- `frontend/src/features/workbench/DiagnosisResultPanel.tsx`：报告、诚实空态、说明性建议标签。
- `frontend/src/features/workbench/diagnosis-result.test.tsx` 与 Workbench 相关测试。
- `frontend/src/styles/workbench.css`：安全 Markdown、报告折叠与空态样式。

### 文档

- 已确认 PRD 与本 Design；
- `docs/workpack/P8-structured-diagnosis-truthfulness/{plan,evidence,review}.md`；
- `docs/完善清单.md`：修正 P0-4 过时描述，按实测更新 P0-2/P0-4/P1-3；
- `docs/跑通验证.md`：按实测更新 C1/C5，C1 既有动作闭环结论不回退；
- `docs/workpack/README.md`：完成后归档登记。

### 明确无改动

- 无 Alembic 迁移、OpenAPI 字段变化、`generated.ts` 变化、Agent 编排变化、Connector/Tool/真实连接新增；
- 不修改动作执行 SQL、审批状态机、执行器白名单和 mock S1–S4 场景事实。

## 4. 切片与验证

工作包拆为两个紧密切片：

- S1 后端真实性：动作模板目录、统一匹配、建议/影响派生、停止伪补证据、负向评测；
- S2 前端安全呈现：SafeMarkdown、报告全文、诚实空态、回答渲染和交互安全测试。

验证顺序：

1. 后端聚焦测试、ruff、mypy；
2. 前端聚焦测试、typecheck、全量 test、build；
3. 后端全量 pytest、`git diff --check`、敏感字面量与改动范围检查；
4. 本地浏览器走普通回答、成功调查、全空/部分空结果和恶意 Markdown fixture；
5. 用户明确授权后执行真实受控靶场只读调查复核；若需删除/恢复固定索引，走单独高风险确认链；
6. 按实测证据更新文档，完成代码 Review 后再 Commit。

## 5. Design Review

### Review 结论：PASS

按产品事实源、开发规范 §7.2、既有受控动作边界和 issue #101 AC 逐项检查，未发现 P0/P1 阻断项。

### 已在设计中收口的 P2

1. **公开契约与“来源模板 id”存在表面冲突**：PRD 同时要求可追溯和不新增公开字段。采用既有
   recommendation description + 稳定 UUID + evidence_ids 追溯，不添加 schema 字段；action id 已是既有
   Proposal 公开常量，不扩大披露面。
2. **当前索引已在 issue #100 成功链后保留**：真实缺失索引复核不能擅自清理。Design 将自动化与
   真实资源验证分开；删除索引和恢复索引均需用户单独授权，恢复只走既有受控动作链。

### 门禁结果

- 产品边界：PASS；没有新增能力承诺。
- 事实来源：PASS；只读事实与代码内白名单模板是唯一输入，散文是显式负向样例。
- 安全：PASS；无任意 SQL/网络能力，Markdown 无 HTML、链接或图片副作用。
- 接口/数据：PASS；无公开字段变化、无迁移、无生成类型改动。
- 动作治理：PASS；建议不自动提案、不自动批准、不执行；真实资源另设确认门。
- 可测性：PASS；正/负匹配、安全渲染、全空/部分空和全量回归均有明确门禁。

## 6. 待用户确认的设计决策

1. 动作模板目录是唯一事实匹配入口，且本 issue 只包含既有联合索引动作。
2. 完整匹配要求 signal + 关联根因 + 三类真实数据库证据；删除 assembler 的重复证据补齐。
3. 建议通过稳定 UUID、固定安全来源文案和 evidence_ids 追溯，不新增公开 API 字段。
4. impact 只声明受控靶场技术范围与“未采集业务影响”，不推断业务损失或调用方。
5. Markdown 允许排版，但链接不可点击、图片不加载、原始 HTML 不执行。
6. 结构化字段全空时只显示一个诚实空态；部分为空时隐藏缺失板块。
7. 真实靶场复核和任何索引删除/恢复不包含在本次设计确认中，届时必须另行确认资源边界与写操作。
