# V2-main-agent-capability-loop · 工作包计划

> 状态：用户已确认；三片实施与最终审查完成；V2-0 收口裁决已落地（2026-10-26），待提交与 PR 合入。
> 编制：2026-10-15；续核：2026-10-21（A2 并入实施-2，G2 改为实施-2 出口；G0／G1 完成）。
> 阶段／Issue：V2-B，[#133](https://github.com/wzhwwwzzzhhh/oper-mind/issues/133)（OPEN；未加 in-progress）。
> 阶段定位：本包是 V2-B 的实现工作包，A 不另建 workpack。A1（首切片契约）已完成；A2（运行兼容证据）由本包实施-2 产出并通过 G2 关闭；A3（Skill／Workflow／子 Agent／多主 Agent 边界）不在本包范围。
> 唯一需求：[已确认 PRD](PRD.md)。
> 技术依据：[已确认 Design](Design.md)、[独立架构 Review PASS](Design-Review.md)。
> 执行证据：[evidence.md](Workpack-证据.md)；独立代码审查：[review.md](Workpack-审查.md)（尚未执行，不沿用架构 PASS）。
> 代码基线：本地 `main`，`6706caa88c3d73c9f29f65659e033e1c89926c65`；未 fetch，不宣称是最新远端。
> **分支命名例外**：本包分支为 `codex/v2-main-agent-capability-loop`，前缀 `codex/` 不是 [开发规范](../../../事实源/开发规范.md) 约定的 `<类型>/<切片>` 形式。该分支建立于规范收口前，此处如实记录为已知例外，不追溯改名。
> 专用分支／目录：已于 2026-10-15 创建 `codex/v2-main-agent-capability-loop`，`D:/market-handsome/oper-mind-worktrees/v2-main-agent-capability-loop`；HEAD 与上述 base 一致。文档已于 2026-10-21 交接，环境已建立且基线通过，详见 [evidence.md](Workpack-证据.md) 的 G0／G1 记录。

## 1. 范围

A1（首切片需求／Design／Review／用户确认）已完成，本包不重复。A2（运行兼容证据）不在编码前单独跑探针，由实施-2 在真实装配上产出并作为 G2 出口。A3（Skill／Workflow／子 Agent／多主 Agent 边界）未启动，不在本包；D／E 立项时再收敛。

### 只做

- AC1–4：主 Agent 的普通回答、材料追问、一个已注册能力请求；严格结构化语义决策，无关键词／正则兜底路由。
- AC5–10：显式 A/B 文本快照，确定性字面对照，新增／删除／修改、行号和精确引文，全量结果校验、输入／结果上限。
- AC11–13：模型／Tool 安全失败，有限调用次数、V2 无 SDK 自动重试、显式 mock 和实际 usage 的诚实记录。
- AC14–16：既有 Run 唯一 writer、幂等、冻结输入重跑、交错执行、取消竞争、迟到隔离、有限流唯一终止。
- AC17–18：本 Run 资源范围、凭据接纳、原文与 Trace／日志／审计／用量／导出的隔离。
- AC19–20：正式会话最小录入／交付／恢复，旧 V1 API、诊断结果、模型配置、取消／重跑与动作安全回归。
- 按 Design §2.9 同步事实源的当前能力／V2 已确认方向分栏，不把未实施方案写成启用状态。

### 明确不做

- 不深化运维、不选商业业务、不做第二 Capability／语义分析／文件上传／URL／RAG／MCP。
- 不做子 Agent 委派或独立主 Agent 协作；这两者仍是平行后续维度，不删掉多 Agent 方向。
- 不做任意插件／技能加载器、全局 Task／Attempt、持久化预算账本、长期记忆／Recovery、分布式调度或强制线程停止。
- 不新增真实服务、Connector、凭据方案、租户／RBAC、动作授权，不接通独立 judge。
- 不重写全部前端，不改历史 P10/P11/P12 fixture／归档工作包，不更新依赖／lockfile，不吸收无关素材／临时文件。
- 默认离线验证；不调用真实模型、数据库、Redis、日志资源或外部网络。安装锁定依赖是环境准备，不是业务资源授权。
- 本计划不授权 stage／commit／push／PR／合并；提交须另获用户明确指令。

## 2. 已确认决策的复用

- 沿用本 V2 Design §2.1–2.4：LangGraph + BaseAgent + ToolGateway，增加 typed 组合执行接缝；保留旧 DiagnosisExecutor，而非复制 Run 控制面。
- 沿用 §2.5：主诊断模型配置供 V2 main 使用；一次 JSON 决策、确定性比较交付，V2 timeout=30 秒、SDK retries=0，Tool 等待=3 秒；不改变 legacy 默认参数。
- 沿用 §2.6–2.8：同一 Run 表新增 kind、两张 1:1 扩展表、legacy 指纹不变、V2 rerun 指纹含来源 Run、普通事件原子谓词预留序号、旧结果与新交付互斥。
- 沿用 [P11 Design §1/§3](../../../design/agent-runtime/P11AgentHarness真实运行安全门实施Design.md)：有限流必须正常 EOF 后接纳唯一终止，超时关闭接纳而非宣称底层停止。旧信号／失败映射与对应回归保留。
- 沿用 [P10 Design](../../../design/agent-runtime/P9HarnessContractKernel实施Design.md)：状态正交、框架无关测试与不可改写历史基线。其零行为变化范围只适用于历史 P10，不伪装 V2 无 API／迁移变化。
- 沿用 [模型 Key Design D1/D2](../../../design/model/P6模型Provider与APIKey管理Design.md)：批准的加密 Key、DB 激活 Provider 及既有解析层；无激活时才是 env/YAML 兜底。新能力不复刻密钥存储。

## 3. 门禁（G0／G1 开始，G2 实施-2 出口）

### G0 · 计划、文档交接与单一写入者

- [x] 用户确认本计划的范围、三片、文件面和验证方法；此前只做文档和 Git 工作区准备。
- [x] 专用 worktree／分支存在性已核对（2026-10-15 建立于 `6706caa`）；它尚未包含本轮确认文档，需在 G0 文档提交后更新并重新记录 HEAD。不得在主仓库 `backend/`／`frontend/` 写实现。
- [ ] 首选路径：用户确认本计划并明确授权后，把本轮已确认文档作为独立文档变更提交，再从该 commit 更新专用 worktree；不在主仓库与 worktree 之间手工拷贝文档。该提交不在本计划内自动执行。
- [x] 备选路径（用户暂不授权提交时）：把主工作区中未提交的已确认 PRD、Design、Review、事实源和本工作包文档按明确清单交接到开发目录；逐文件比较内容摘要。不得以全目录复制代替范围核对，不复制 `.env`、`config.local.yaml`、`data/`、`.venv`、`node_modules`、SVG 素材或 `research_tmp/`。
- [x] 文档交接前，主工作区 `D:/market-handsome/oper-mind` 是本轮文档确认源；交接后仅在专用 worktree 写本包，主工作区的同名文档不并行继续改。若源内容与确认快照不符，先报告差异，不覆盖。
- [x] 交接清单至少包括本包 plan/review/evidence、唯一 PRD／双索引、V2 Design/Review、四份事实源、配套架构路径与准备-1／准备-2／准备-3 说明；其版本／学习资料链接可从主工作区只读访问。上下文资料不是本包自动提交清单；发布前必须整理其依赖链接与独立交付范围。
- [x] 在 evidence 记录本地 base、分支、文档 SHA-256、dirty-set；主目录现有其他改动保留。不开通任何提交权限。

### G1 · 独立环境与未修改基线

- [x] 专用 worktree 自建 Python 3.11 venv 和前端依赖，不复用主仓库环境。当前主机已定位 Python311，可用 `python --version` 再确认；Node 按 CI 的 22 系列核对，不擅自升级全局工具。
- [x] 安装只用当前 requirements／lockfile，不新增框架依赖。仓库当前没有 `.Codex/scripts/init-worktree.ps1`，不假设该脚本存在。
- [x] 所有测试及 OpenAPI 导出在受控子进程运行，清除继承的业务 `OPERMIND_*`／自动 tracing 配置，再注入显式 mock 和专用临时应用库；不打印环境，不复制本地私密配置，不碰主仓库数据库。
- [x] 先在未改生产代码的 checkout 运行后端和前端基线，记录实际版本／命令／结果／已知失败；已有失败不隐瞒、不顺带扩大本包修复范围。
- [x] 源码核对的迁移唯一 head 为 `20260905_16_p14_role_models`；实施前用本 worktree 的 Alembic metadata 再核对。若 head 已变化，修订迁移依赖，不创建多 head。

### G2 · 兼容验证与默认入口激活（实施-2 出口，不是开始门）

- [x] 实施-2 完成后，用锁定依赖＋确定性替身证明 typed 模型响应、Gateway 防绕过、有限流终止、每 Run 状态、取消和 usage 接缝；按 evidence 的 A2 取证矩阵逐项记录，结果写回准备-3 记录及 evidence。框架有文档／能 import 不算兼容 PASS；未通过不得进入实施-3 的默认入口切换。（2026-10-21：A2-1～A2-8 均以实际测试运行取证，见 evidence 的实施-2 章节；未新增框架依赖。）
- [x] 接缝不兼容时，停在最小失败证据；不安装 create_agent／Deep Agents 或改历史 baseline 来“修绿”。若需改变已确认设计，重新走 Design 门。（2026-10-21：本轮未出现不兼容项，未安装新框架，未改写历史 baseline／fixture；唯一契约变动是经批准的新增 CHECK 约束期望。）
- [ ] 实施-1／实施-2 是内部实施检查点，不是独立产品阶段完成；实施-3 前端可见＋全包回归前不得宣称首闭环交付或默认入口已验证。

准备阶段留下的运行证据 gap 已由实施-2 补齐，G2 于 2026-10-21 判定通过；G0／G1 是开始门，G2 是默认入口切换前的出口门，不把“已建工作包”写成“兼容完成”。

## 4. 切片拆分（本包实施-1–实施-3，不同于前期准备-1／准备-2／准备-3）

### 实施-1 · typed 输入、持久化与 Run 生命周期

- [x] 定义严格输入／快照／交付、RunExecutionInput 和封闭信号；legacy bridge 继续兼容原 port。
- [x] 增量迁移：Run kind、run_inputs、run_deliveries；typed 仓储读写与未知版本失败关闭；空扩展数据可 downgrade，有 main Run／数据时明确拒绝降级。
- [x] 在唯一 RunApplicationService 适配受理、认领、提交／回滚、重跑；legacy 指纹与作用域不变，V2 创建／来源重跑指纹完整。
- [x] 普通事件通过 running 谓词原子预留序号；有限流共用保护内核保留旧签名，取消 CAS 胜出不留交付／消息／第二终态。
- [x] 用注入的确定性 Executor 测数据归属和事务竞争；此时不将 main Agent 装配为公开默认入口。

验收：AC2、9、10、14–16、17 的接纳／生命周期部分及 AC20 的存储兼容。材料不足可持久化为待执行输入，但不能制造比较结果；越限／凭据输入不落库。具备可独立复验的应用层与迁移证据，不声称 UI 已完成。

### 实施-2 · 主 Agent、能力 Tool 与安全接纳

- [x] BaseAgent 子类与 bounded StateGraph：一次 typed JSON 决策，直答／追问／能力三分支；严格校验，不使用旧 DB 路由。
- [x] 在 `capabilities/` 内提供最小能力声明与执行入口：typed 输入输出、规则版本、允许 Tool、完成条件；组合根显式注册 `text.literal_compare@1`，不引入扫描、自动发现、热加载或市场。
- [x] V2 模型适配先区分调用失败与 JSON 无效，固定安全错误；V2 timeout／SDK 无重试，mock 显式封闭场景，真实 usage 缺失不补造。
- [x] 仅注册文本 Tool；规范化换行、保留其他字符、稳定 opcode 块与出处；重算完整块序列接纳，不只检查局部引文。
- [x] 检验 2000 码点／100 行／query200／50 块／模型4次／Tool1次上限；正常设计路径一次模型，直答追问 Tool 为零。
- [x] 模型不读取 A/B 正文；凭据接纳与 Gateway 使用共用识别范围。脱敏改变结果则失败，不拼回原文绕过。
- [x] 每 Run 独立模型、Agent、State、Gateway、计数／缓冲；用 Event／Barrier 控制交错，不靠长 sleep 或真实外部访问。

验收：AC1–13、17–18 的内核部分，并复验 AC14–16。固定双跑、跨 Run 材料引用／错误引文／漏块／注入指令／调用失败／预算／超时均有负向测试。此片产出 A2／准备-3 所缺的实际兼容证据，经 G2 后才能进入实施-3 的默认入口切换。

实施结果（2026-10-21）：内核片段证据与 A2-1～A2-8 取证见 [Workpack-证据.md](Workpack-证据.md) 的“实施-2”章节；后端全量 `968 passed`。AC18／AC19 仍无证据，归实施-3。

### 实施-3 · 正式 API／会话界面与全包兼容

- [x] 原 Run 路由扩展请求／资源联合；默认 legacy 请求、主 Agent 显式输入、两种结果互斥；schema 错误不回显原文。（受理联合不用 discriminator，理由与证据见证据文档「契约与产品决策」。）
- [x] 装配 main 工厂；query/service 旧接口、纯普通消息旧链、模型管理均保留，V2 不继承服务／旧材料，不走关键词 fallback。（`execute_run` 按 `runtime_kind` 分派修复了曾把 V1 Run 打成失败的缺陷。）
- [x] 会话内主 Agent 默认／V1 服务调查显式入口；A/B 提供开关、空文本、码点提示、转义引文、非诊断交付与取消／失败反馈。（**偏离 1**：默认仍是 V1 录入，主 Agent（V2）为显式切换；AC20 的 V1 已确认行为回归要求优先于计划的默认口径，详见证据文档「与计划原文的偏离」。**偏离 2（已修）**：A/B 提供开关与显式空文本在首轮实现里被塌缩成「留空＝未提供」，是第 2 轮审查判出的 P1，现改为每侧独立复选框并补齐 AC5 公开链与界面用例。）
- [x] Run 详情恢复输入／交付，SSE 只传安全过程并按 Run 隔离；刷新／重连／重跑不依赖材料持久草稿，不写 localStorage 原文。（按 Design §2.8 收口：会话 Run 摘要列表只带交付、`input_snapshot` 恒为 null，冻结输入由前端按需读 `GET /runs/{id}`；刷新实测为列表恢复交付＋1 次详情补齐输入，`localStorage` 为空。）
- [x] 审计、最近调查及导出对 V2 仅中性摘要；日志／usage／Trace 不带 query、引文、Prompt、原始异常。（events／全局摘要泄露探测四项全 false；导出只含脱敏目标与状态。）
- [x] 从 OpenAPI 生成前端类型，更新 MSW／reader／交互测试；跑全量回归及真实本地浏览器的 mock 模型＋确定性纯文本闭环。（收口复跑：后端全量 `984 passed in 668.68s`、前端串行全量 `246 passed`、ruff／mypy／typecheck／build 全绿；浏览器闭环在两轮修复后重跑并补测「提供／未提供开关」与显式空文本，但为隐藏视口内驱动，**未取截图**。）

验收：AC1–20 全部逐项取证，尤其 AC18–20。浏览器证据明确模型为 mock，但纯文本 Tool 是实际确定性计算；它不证明真实 Provider 表现。无法完成浏览器验证时保留未验收，不以 MSW 单测冒充端到端。

实施结果（2026-10-21）：AC1–4、9–10、12、14、17–20 取得公开链／界面片段证据，AC5–8 取得界面＋公开链片段证据（AC5 在第 2 轮补齐显式空文本链）；AC15／AC16 仍只有内核证据（取消未在浏览器内计时验证）。逐条定位、命令输出与保留 gap 见 [Workpack-证据.md](Workpack-证据.md) 的「实施-3」章节，三轮审查分级与 AC 表见 [Workpack-审查.md](Workpack-审查.md)。审查结论：第 1 轮 FAIL（2×P1／4×P2）→ 修复；第 2 轮 FAIL（1×新 P1：显式空文本在产品入口不可达／3×P2）→ 修复 P1 与可自决 P2；第 3 轮增量 **PASS**（0×P0／0×P1，2×P3）。遗留 2 项 P2（失败码分类保真、损坏行的安全不可用投影）属公开契约变更，待用户裁决；默认入口口径冲突同样待裁决。最终交付门未执行，未 stage／commit，不得据此宣称首闭环交付。

三片共享 Run／API／持久化文件，按实施-1→实施-2→实施-3 单写入者推进，不建议为加速同时写同一 worktree。

## 5. 改动面（文件级）

路径均相对仓库根；这里只授权确认后的实施范围，未列文件先说明原因、补计划；架构／权限变化重新走 Design。新增包的 `__init__.py` 仅用于明确包边界。

### 后端生产

- 新增 `backend/src/domain/main_agent.py`。
- 新增 `backend/src/application/run_execution.py`。
- 新增 `backend/src/infrastructure/agent_runtime/__init__.py`、`backend/src/infrastructure/agent_runtime/run_executor.py`。
- 新增 `backend/src/agents/main_agent.py`。
- 新增 `backend/src/core/main_agent_graph.py`、`backend/src/core/main_agent_model.py`、`backend/src/core/input_admission.py`。
- 新增 `backend/src/capabilities/__init__.py`、`backend/src/capabilities/text_compare.py`、`backend/src/tools/text_compare.py`。
- 新增 `backend/src/infrastructure/persistence/run_delivery_repository.py`。
- 修改 `backend/src/domain/records.py`、`backend/src/domain/diagnosis.py`、`backend/src/infrastructure/persistence/models.py`、`backend/src/infrastructure/persistence/repositories.py`。`diagnosis.py` 仅新增 `RunRuntimeKind` 判别值，供同一 Run 主脊区分 legacy 诊断与主 Agent；不新增第二套状态机。
- 修改 `backend/src/application/services.py`、`backend/src/application/runtime_safety.py`；不改历史 `contracts.py`／`runtime_contracts.py` 签名。
- 修改 `backend/src/core/llm.py`；`backend/src/core/tool_gateway.py` 仅暴露共用纯检测，不放宽执行或出站规则。
- 修改 `backend/src/api/v1/dependencies.py`、`schemas.py`、`resources.py`、`routes.py`、`errors.py`、`backend/src/app.py`。
- 修改 `backend/src/application/audit_service.py`、`backend/src/application/session_export.py`、`backend/src/infrastructure/persistence/audit_repositories.py`。

### 数据库迁移（显式执行，只用临时测试库）

- 新增 `backend/migrations/versions/20261015_17_v2_main_agent_delivery.py`；拟 revision=`20261015_17_v2_main_delivery`，down_revision=`20260905_16_p14_role_models`，实施时再次核对唯一 head。
- 只增 runtime_kind 与两张扩展表，不改凭据、服务或动作表；拒绝有 V2 数据时破坏性 downgrade，不能为了回滚自动删文本。

### 前端生产／契约生成

- 修改 `frontend/src/api/v1/client.ts`、`frontend/src/api/v1/queries.ts`；重新生成 `frontend/src/api/v1/generated.ts`，禁止手改。
- 修改 `frontend/src/features/workbench/WorkbenchPage.tsx`、`send-intent.ts`、`run-events.ts`、`TraceCard.tsx`、`resource-readers.ts`、`conversation-turns.ts`。
- 新增 `frontend/src/features/workbench/MainAgentComposer.tsx`、`MainDeliveryPanel.tsx`、`main-delivery-readers.ts`。

### 测试

- 新增 `backend/tests/test_main_agent_runtime.py`、`test_text_compare.py`、`test_main_agent_runs_api.py`、`test_v2_main_agent_migration.py`。
- 修改／补充现有 `backend/tests/test_run_cancel.py`、`test_run_rerun.py`、`test_p2_application_services.py`、`test_p2_api_v1.py`、`test_p2_repositories.py`、`test_p2_schema.py`。`test_p12_migration.py` 仅更新唯一 head 断言到新 revision，不改历史迁移行为假设。
- 修改／补充现有 `backend/tests/test_llm_client.py`、`test_usage_recording.py`、`test_runs_list.py`、`test_audit_api.py`、`test_audit_export_api.py`、`test_session_export.py`、`test_model_config_api.py`，只调整经批准的新增契约期望，不删除旧行为断言。
- 新增 `frontend/src/features/workbench/main-agent.test.tsx`、`main-delivery.test.tsx`；修改 `frontend/src/test/handlers.ts`、`frontend/src/api/v1/client.test.ts`、`frontend/src/features/workbench/WorkbenchPage.test.tsx`、`send-intent.test.ts`、`run-events.test.ts`、`trace-card.test.tsx`、`conversation-turns.test.ts`、`session-export.test.tsx`。
- P10/P11/P12 已冻结测试资产只读执行，不改 fixture／历史 gate／skip 清单；若暴露真实契约冲突，停止并给差异证据。

### 文档

- 当前工作包 `plan.md`、`review.md`、`evidence.md` 与 `docs/workpack/README.md`。
- `docs/进行中/V2-主Agent闭环/首闭环/PRD.md`、`docs/prd/agent-runtime/README.md` 与 `docs/workpack/README.md` 只同步状态／证据，不擅改范围或 AC。
- `docs/进行中/V2-主Agent闭环/首闭环/Design.md`、对应 Review 只同步确认记录；设计实质变化重新审查。
- `docs/事实源/产品定义.md`、`docs/事实源/路线图.md`、`docs/事实源/开发规范.md`、`docs/事实源/架构与开发路径.md` 按已确认 Design 同步 V1／V2 口径。
- `docs/进行中/V2-主Agent闭环/方向/计划骨架.md`、`docs/进行中/V2-主Agent闭环/准备/开发计划.md`、`docs/进行中/V2-主Agent闭环/准备/最小契约与首切片范围.md`、`docs/进行中/V2-主Agent闭环/准备/候选兼容验证记录.md` 只同步入口／实际验证状态，不回写历史“已通过”。

## 6. 验证方法

以下全部是待执行命令／方法，**本计划交付不表示运行过**。从专用 worktree 对应目录执行；所有失败输出只保留安全摘要。

### 环境准备（计划确认后）

仓库根先核对 Python 3.11／Node 22，再执行：

```powershell
python -m venv .venv
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

前端依赖在 `frontend/` 执行 `npm ci`，使用既有 lockfile，不修改依赖。若环境准备失败，记录实际错误并停在环境门；不得改包版本冒充兼容。

### 后端（在 backend/）

```powershell
..\.venv\Scripts\python.exe -m pytest tests -q
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m mypy
```

新增测试文件存在后，聚焦执行：

```powershell
..\.venv\Scripts\python.exe -m pytest tests/test_main_agent_runtime.py tests/test_text_compare.py tests/test_main_agent_runs_api.py tests/test_v2_main_agent_migration.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_run_cancel.py tests/test_run_rerun.py tests/test_p2_application_services.py tests/test_tool_gateway.py tests/test_llm_client.py tests/test_usage_recording.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_harness_contract_kernel.py tests/test_harness_runtime_adapter_contract.py tests/test_harness_regression_baseline.py tests/test_harness_p11_runtime_safety.py tests/test_harness_p11_tool_connector_safety.py -q
```

迁移测试在 `tmp_path` 应用库内完成 old-head → new-head、旧数据 kind 回填、空数据 downgrade／再 upgrade、有 main 数据 downgrade 拒绝且数据不变、未知版本／损坏结果安全失败。不对默认 `data/opermind.sqlite3` 跑 upgrade/downgrade。

并发使用两条实际应用事务和可控同步替身，证明同会话／跨会话、同键竞争、相同输入不同 rerun 来源、取消与序号／结果竞争。验证 rowcount/CAS 后的数据库事实，不仅断言线程返回值。所有上游失败零 Tool、无成功残片；不使用长 sleep 验证超时。

### 前端（在 frontend/）

```powershell
npm run test -- src/features/workbench/main-agent.test.tsx src/features/workbench/main-delivery.test.tsx
npm run typecheck
npm run test
npm run build
```

OpenAPI 生成优先用专用后端 8000 端口的隔离 mock 应用配合 `npm run generate:api`，端口占用先识别不终止他人服务。免端口方式可在清理业务环境后的子进程生成 OpenAPI 到本 worktree 的 `.tmp/v2-main-agent/openapi.json`，再在 frontend 执行 `npx openapi-typescript ../.tmp/v2-main-agent/openapi.json -o src/api/v1/generated.ts`。生成前确认本地工具已安装，禁止 npx 临时拉新版本；临时 JSON 不纳入提交。

浏览器最后复验：A/B 录入及空文本、同／异文本、缺材料、失败／取消、刷新重连、重跑、两个 Run 结果归属、V1 显式入口与模型设置。使用只绑定 loopback 的本地服务、专用临时应用库、显式 mock 模型；不读取本地真实配置／数据，不触发真实监控采样。前端端口 5174，API 指向专用本地后端。实际启服务／浏览器操作时再使用相应测试技能；只读／测试截图也不得含秘密。

### 差异、回归与提交前检查

- `git diff --check`，并分别列 committed/staged/unstaged/untracked 的本包文件，检查明确清单和新增文件；禁止全量暂存。
- 现有 CI 的后端 lint/type/tests 与前端三件套全部保留，不新增 skip／xfail 或改历史画像“修绿”。历史阶段的精确范围 gate 验证原阶段交付，不用它强行宣称 V2 无迁移／无 API 变化。
- 使用合成原文标记和假凭据检测样例，捕获安全错误、Trace／审计／导出／usage／日志；既检查拒绝发生在持久化／模型前，也检查结果区合法引文仍可核对。
- 实施 evidence 逐项记录 AC、命令、输入、实际结论及未覆盖点；mock 单测／本地浏览器不作为真实 Provider／业务资源验收。

## 7. 提交计划（仅拟议，不自动执行）

三片完成后集中 Test → 独立只读代码 Review → 修正／复审；P0/P1 不放行。用户另行明确授权提交后，建议按可核对范围形成：

1. `功能: 增加主Agent输入快照与Run交付契约`。
2. `功能: 接入受控主Agent与文本比较能力`。
3. `功能: 打通主Agent会话交付与V1兼容`。

是否保留三提交或合并整理届时由用户决定。未提交的前期版本／学习文档、素材和临时研究文件不自动吸收入实现提交；不得先清理主工作区来制造干净状态。无用户授权不运行 git add/commit/push，不创建 PR。

## 8. 当前事实与审阅点

- 已满足：A1 首切片需求／Issue、Design 独立 Review PASS、用户确认 Design。
- 待满足：本计划用户确认、G0 文档交接与 worktree、G1 环境与未修改基线、实施-2 产出并经 G2 确认的 A2 兼容证据。
- PRD 仍为“已确认”，Issue 仍 OPEN；计划确认后再按流程同步“进行中”，现在不提前推进。
- 本轮不写生产代码、不运行测试／探针、不安装依赖、不执行迁移、不访问真实资源、不提交。

用户只需确认本计划的三片、文件改动面和验证方法，不必重复批准 PRD 或 Design。确认后先完成 G0／G1，再依次推进实施-1、实施-2；G2 通过后才进入实施-3 的默认入口切换。开始门未过不直接进入默认主 Agent 开发。
