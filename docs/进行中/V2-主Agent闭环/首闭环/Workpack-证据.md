# V2 主 Agent 闭环 · 验证证据

> 状态：G0／G1／G2 已完成；实施-1、实施-2、实施-3 开发与验证完成（2026-10-21 收口），后端全量 `984 passed`、前端串行全量 `246 passed`、ruff／mypy／typecheck／build 全绿。主 Agent 已装配为公开 API／会话内显式入口（默认录入仍是 V1 服务调查，待用户裁决）。独立代码审查已跑三轮：第 1／2 轮 FAIL → 修复，第 3 轮针对增量 PASS（0×P0／0×P1，2×P3）；遗留 3 项契约问题（默认入口、失败码保真、损坏行降级投影）交用户裁决。迁移门已在临时库上以 5 条专项测试取证（`5 passed`）。未获用户提交授权，未 stage／commit。
> 续核：2026-10-21；本轮记录实施-2 的 A2 兼容证据与 G2 判定。
> 需求：[PRD](PRD.md)；计划：[plan.md](Workpack-计划.md)。

## 门禁

- [x] G0：计划确认、文档提交或交接、worktree 更新及单一写入者。
- [x] G1：独立环境、临时应用库、未修改代码基线、迁移 head。
- [x] G2（实施-2 出口）：模型／Gateway／Run 安全的实际兼容证据，默认入口激活前门禁。判定依据见下方矩阵结果与“实施-2 · A2 兼容取证矩阵结果”，A2-1～A2-8 全部有实际运行证据。

顺序：G0／G1 → 实施-1 → 实施-2 → G2 → 实施-3 → 最终交付门。

A1 的文档证据在 PRD／Design／Design-Review，不在本表重复；A2 以 G2 取证；A3 不在本包。

## A2 兼容取证矩阵（实施-2 产出，G2 判定）

| 编号 | 接缝 | 取证方式 | 通过条件 |
|---|---|---|---|
| A2-1 | typed 模型响应 | 显式封闭模型替身返回合法／非法 JSON | 合法→typed decision；非法→固定安全失败，零 Tool |
| A2-2 | mock／usage | 显式 mock 开关；usage 缺失／存在 | mock 可识别且封闭；缺失不补造，存在按实际记录 |
| A2-3 | SDK 重试 | V2 客户端显式 retries=0，注入一次失败 | 只发生一次调用，无自动重试 |
| A2-4 | Gateway 防绕过 | 包装／记录 Gateway；尝试旁路 Tool 调用 | 所有 Tool 只经 Gateway；旁路拒绝 |
| A2-5 | 唯一终态 | 有限流正常 EOF、零／多终止、终止后输出、异常 | 仅 EOF 后接纳唯一终态；异常关闭接纳 |
| A2-6 | 每 Run 隔离 | 两个 Run 用 Event／Barrier 交错 | 模型／Agent／State／Gateway 不共享，结果归属正确 |
| A2-7 | 取消与迟到 | 取消 CAS 竞争、迟到结果／事件 | 胜出者不留交付／消息／第二终态；迟到被隔离 |
| A2-8 | 产品事实唯一 writer | 检查 Run 应用服务、DB 事件／交付 | 应用服务唯一 writer；checkpoint 不成为产品事实源 |

本矩阵是 G2 的最小取证清单；任何一项缺少实际运行证据，G2 不通过，实施-3 不切换默认入口。

本地代码 base 为 `6706caa88c3d73c9f29f65659e033e1c89926c65`。2026-10-15 已建立 `D:/market-handsome/oper-mind-worktrees/v2-main-agent-capability-loop`，分支 `codex/v2-main-agent-capability-loop`，实际 HEAD 同 base，初始工作树干净。该检查只是 Git 事实，不是模型／框架兼容测试；文档已于 2026-10-21 交接，环境与基线见下节。兼容证据仍待实施-2 产出。

## G0 文档交接（2026-10-21）

- worktree：`D:/market-handsome/oper-mind-worktrees/v2-main-agent-capability-loop`；分支 `codex/v2-main-agent-capability-loop`；HEAD `6706caa88c3d73c9f29f65659e033e1c89926c65`。
- 来源：主工作区 `D:/market-handsome/oper-mind` 的未提交文档；未提交文档不作为运行证据。
- 交接 35 个文件（V2 进行中文档、四份事实源、双索引、根 README／AGENTS 及 4 处路径修复），逐文件 SHA-256 与源一致，0 mismatch。
- 未交接：图片／SVG／PNG、`.env`、`config.local.yaml`、`data/`、`.venv`、`node_modules`、`research_tmp/`，以及未列入清单的历史归档／学习资料；这些不是本包实施输入。
- 工作树 dirty-set：10 个已跟踪文件修改 + 2 个未跟踪目录（`docs/事实源/`、`docs/进行中/`）；未 stage、未 commit、未 push。
- 单一写入者：后续仅在该 worktree 写本包实现与文档，主工作区同名文档不再并行修改。
- 下表的 `Workpack-证据.md` 哈希是交接时快照；本记录追加后该文件自身哈希会变化，不作为不一致。

```text
18529abee902ea3efa9c71ba3d3637222b57c180abffaa55d838cb11e659da02  AGENTS.md
60e017acfb5b091fbe02947dc82500f084075319fc2ecc27bdaec7a54ab0876a  README.md
b022a4382c4eba19f688f8880daf5f7ed0e2bb50f71fbc3238a403819e4c1fa8  backend/pyproject.toml
9089b8fa1b43b4a9bd090e664ba0eb5a0e4185d4362bba163bed40c289aab092  backend/src/infrastructure/secrets.py
05c85e4d02a447b33603cfadd288b25a5b095817cda989a078a92429ba11910d  backend/tests/test_harness_zero_behavior_gate.py
522bca3b8f25de333918dd21d4eb14f04e4cf1546b823a0c7346463b23c029bd  docs/README.md
0381dcf39672baef52da3fa9009236a6020ffd19d893e35ca96766a7ce7d32f8  docs/prd/README.md
a27dca4f27eef10b8272344f45d5d756c39000bd270ba8aefcf0ccb0970a8860  docs/prd/agent-runtime/README.md
22d5e307955aa34f58061737dc10c4d8f969e73a8a6d08489d0c8bfd8cfe2cec  docs/workpack/README.md
34e2cff4a38e905e7f2a6c3bca01451de0bc98ff8077be2a752bbae06bc6eb61  docs/事实源/产品定义.md
b1349ea40cb88fa684c1c9744eea2616469168bbad9af4aeac62dac3093d34ed  docs/事实源/开发规范.md
2dd4d3ebb3023b44a16a3ef02b851e1bb104ed684d3e8282602d5b8ffd508773  docs/事实源/架构与开发路径.md
bbb98dababc9c88e97eaf68f8d8737278298b84d8bc7d7b99a19559726a001e0  docs/事实源/路线图.md
c2e1fce165d24a7e2d64b390f453ce2ac6cbe838c7c0d72f833cde83c699b173  docs/进行中/V2-主Agent闭环/README.md
6862402956203f49de47e6a17d84d9fa2ffe399dc215180324cd81de1ebef4f5  docs/进行中/V2-主Agent闭环/准备/候选兼容验证记录.md
d4a63a380d4c030fac8d2bdc8c3172236488f1d204b6ddd825f77dc358d7c2f3  docs/进行中/V2-主Agent闭环/准备/开发计划.md
df2fb8ac5913dbcaa4408683febb4d7346203779bdd32b2b3a423922b7deb32c  docs/进行中/V2-主Agent闭环/准备/最小契约与首切片范围.md
2a7793d6d391fba1e7543fd81e9ffc4c1d8785aadfd8f292ccf8e3cbf169a5f1  docs/进行中/V2-主Agent闭环/准备/现状与复用盘点.md
4168781fd2e14987246b753c7bedae3315392ada454b53f4709828bf437bcdd3  docs/进行中/V2-主Agent闭环/方向/图解/01-系统分层与组件分工.md
6688ddd10749cdc97c0feb1b6f4e4c460cb2d26e1685c5708ed3c91e644b6292  docs/进行中/V2-主Agent闭环/方向/图解/02-Agent组合与平行维度.md
935a0f58b3559a1bf3df04245d4411bd7c69a55e58e98ec3f75273a4eb9baccc  docs/进行中/V2-主Agent闭环/方向/图解/03-单次任务与主Agent循环.md
3789b6e98a5e24b7a6a7527617ba24ae9af584634502b2cab0561d28215bc929  docs/进行中/V2-主Agent闭环/方向/图解/04-Capability与业务工作流.md
d9631308d1aa79d6345b52f5d4a219624edc7d8a4595738a84b183bd6aff778d  docs/进行中/V2-主Agent闭环/方向/图解/05-子Agent委派与上下文隔离.md
79d15855a779961fec550cdd3ae506829d9167d0065066667bec6b1e1da0c593  docs/进行中/V2-主Agent闭环/方向/图解/06-独立主Agent协作与交付.md
f16c06206a1e3d2f8f45fbb855e0e113f36e844f6559d2ca0c1a6c017688cc7f  docs/进行中/V2-主Agent闭环/方向/图解/07-上下文任务与结果契约.md
f208f9c032b1dd1bcb9fa911cb68d00dc4a52db1acc807a18493a1fa156c50fb  docs/进行中/V2-主Agent闭环/方向/图解/08-现状复用与建设顺序.md
183535aa26bae5886ddded77fac27e0a480d9b7eca729d5eab571b6d62ab8d69  docs/进行中/V2-主Agent闭环/方向/图解/README.md
de9dc60abd4865762be13dc6183a10df20a5d6c43a74f1a05930d132fa986d13  docs/进行中/V2-主Agent闭环/方向/计划骨架.md
6ba4ac35f366f3983c231a44dd6c0c42b418015667d838fea1e7ab7d8227e434  docs/进行中/V2-主Agent闭环/首闭环/Design-Review.md
35bb21dbc9f5de1ca281455f1ac3d99e06c770da85a67ee318a560755659f928  docs/进行中/V2-主Agent闭环/首闭环/Design.md
d8eb47957fd23a10eb7708af66655a7096a7963f3ca034e6c1788e8d5197bf7b  docs/进行中/V2-主Agent闭环/首闭环/PRD.md
b308ed907ccdfef7eff0a44027ba2e055db117e4d6f4c6cdc7d97b19fc4a06a5  docs/进行中/V2-主Agent闭环/首闭环/Workpack-审查.md
dfc7909eee1597b3ad7d6e8d49a7613898808bdf206bc6da93b80587c075e840  docs/进行中/V2-主Agent闭环/首闭环/Workpack-计划.md
b044d1833ffb8e1faa69b612b3db5c944c4b1259f7b4bf6f9ad1c64b5d6e39a3  docs/进行中/V2-主Agent闭环/首闭环/Workpack-证据.md
89ea1d3a68fef50ecd499e513b5177e3bf0d2311f7ad7c836d83bd6bf7edab73  frontend/src/features/shell/GlobalNav.tsx

## V2-0 收口验证（2026-10-26）

| 项目 | 命令 | 结果 |
|---|---|---|
| 后端聚焦 | `pytest tests/test_main_agent_runtime.py tests/test_main_agent_runs_api.py -q` | `80 passed` |
| 后端全量 | `pytest tests -q` | `988 passed`（含补回的 P10 路线图门禁） |
| 前端全量 | `npm run test` | `247 passed` |
| 前端类型 | `npm run typecheck` | 通过 |
| 前端构建 | `npm run build` | 通过（仅有既有 chunk size 提示） |
| 后端静态 | `ruff check src tests` / `mypy src` | 通过 |
| API 类型 | `npm run generate:api` | 已重新生成 `generated.ts`，未手改 |

覆盖点：

- **失败码**：模型不可用、决策无效、能力不可用、工具失败各自映射到独立公开码；未知失败保留 `MAIN_AGENT_FAILED`；导出与公开资源共用 `RunFailureCode.safe_message`。
- **损坏行**：交付行或冻结输入行损坏时只标记 `main_delivery_status` / `main_input_status` 为 `unavailable`；列表与详情均返回 200，不带原文或原始异常，一条坏行不再拖垮会话列表。
- **默认入口**：保持 V1 服务调查默认，V2 显式切换；既有默认入口测试继续通过。

本轮为 V2-0 收口增量，未重新派独立子代理审查；既有三轮独立审查结论只覆盖其审查时的差异。
```

## G1 环境与未改业务代码基线（2026-10-21）

环境：worktree 自建 `.venv`（Python 3.11.9），后端按 `backend/requirements.txt` 安装；前端 `npm ci`（Node v22.23.1／npm 10.9.8，333 packages）。未新增框架依赖，未复用主仓库环境。

基线 checkout 只含 G0 交接的 4 处路径／注释修复（`backend/pyproject.toml`、`backend/src/infrastructure/secrets.py`、`backend/tests/test_harness_zero_behavior_gate.py`、`frontend/src/features/shell/GlobalNav.tsx`），无业务代码改动。

- 后端全量测试（清除继承的 `OPERMIND_BASE_URL`／`OPERMIND_MODEL`／`OPERMIND_APP_DATABASE_URL`，显式注入 `OPERMIND_API_KEY=mock`，临时应用库）：`884 passed, 2 warnings in 374.40s`。
- 后端 `ruff check .`：`All checks passed!`
- 后端 `mypy`：`Success: no issues found in 120 source files`（另有 2 条 untyped body 提示，非错误）。
- Alembic head：`20260905_16_p14_role_models (head)`，唯一 head，与计划一致。
- 前端 `npm run typecheck`：通过。
- 前端 `npm run test`：22 个测试文件、230 项测试全部通过；存在既有 MSW 未匹配请求与 `act(...)` 警告，本包不扩大处理。
- 前端 `npm run build`：通过（390 modules）；仅有既有的 500 kB chunk 体积提示。

结论：G1 通过。基线无已知失败；这些结果不是 V2 兼容验证，A2 仍需在实施-2 按矩阵取证。

## 实施-1 · typed 输入、持久化与 Run 生命周期（2026-10-21）

状态：开发与聚焦验证完成；主 Agent 仍未装配为公开默认入口，未产出 A2／G2 兼容证据，独立代码审查待三片完成后统一执行。

### 生产改动

- 新增 `backend/src/domain/main_agent.py`：`MainInputV1`、材料／上下文快照、`MainDeliveryV1` 三分支联合、差异块结构校验、固定助手消息与安全错误类型。
- 新增 `backend/src/application/run_execution.py`：MainAgent 受理／重跑命令、`RunExecutionInput` 判别联合、封闭 event／结果／交付／失败 signal、`RunExecutor` 端口、legacy 诊断桥、快照构造与版本化指纹、交付接纳校验。
- 修改 `backend/src/application/runtime_safety.py`：提取共用有限流内核；`guard_runtime_stream` 签名、P10／P11 信号与失败映射保持不变；新增 `guard_run_stream` 只接受 typed signal。
- 修改 `backend/src/application/services.py`：同一 `RunApplicationService` 内的 main Agent 受理、认领、typed 执行、成功／失败／取消与重跑；普通执行事件经 `running` 谓词原子预留序号；legacy 指纹、作用域与执行路径保持不变。
- 修改 `backend/src/infrastructure/persistence/models.py`、`repositories.py`、新增 `run_delivery_repository.py`：`runtime_kind`、`run_inputs`、`run_deliveries` 与严格读写；新增 `reserve_running_event_sequence`。
- 新增迁移 `backend/migrations/versions/20261015_17_v2_main_agent_delivery.py`；down_revision 为 `20260905_16_p14_role_models`。SQLite batch 重建 `diagnosis_runs` 时临时关闭外键检查，避免历史 rerun 行让 `DROP TABLE` 失败；检测到 V2 Run／输入／交付时拒绝 downgrade。
- 修改 `backend/src/domain/diagnosis.py`、`records.py`、`repositories.py`：新增 `RunRuntimeKind`、Run 数据字段与输入／交付仓储端口；`backend/src/core/tool_gateway.py` 只新增复用同一识别范围的纯检测 `contains_sensitive_content`。

### 命令与结果

- `pytest tests/test_main_agent_runtime.py -q`：26 passed（15.33s）。
- `pytest tests/test_v2_main_agent_migration.py tests/test_p12_migration.py -q`：9 passed（17.65s）。
- `pytest tests/test_p2_application_services.py tests/test_run_cancel.py tests/test_run_rerun.py tests/test_harness_p11_runtime_safety.py -q`：61 passed（195.45s）。
- `ruff check .`：All checks passed。
- `mypy`：Success: no issues found in 123 source files（另有既有 untyped body 提示，非错误）。
- `alembic heads`：`20261015_17_v2_main_delivery (head)`，唯一 head。
- `git diff --check`：通过（仅 Git 的 CRLF 转换提示）。
- 更正：实施-1 收尾时此处曾写“后端全量测试：341 passed／0 failed”，该数字来自未跑完的旧记录，从未被日志证实，现作废。实施-1／实施-2 之后的真实全量结果见“实施-2 · 命令与结果”，为 `968 passed, 3 warnings in 679.54s`（`EXIT:0`）。

### 行为证据

- 输入接纳：缺失与显式空文本可区分；仅统一换行并保留末尾空行；query 200／材料 2000 码点／100 行上限、孤立代理码点、摘要篡改与未知规则均被拒绝；交付联合拒绝未知 kind 与额外字段；差异块引文必须逐字等于行数组。
- 受理事务：含 `sk-` 形态的输入在任何消息／Run／快照落库前被拒绝（数据库 0 Run、0 消息）；成功后同一事务写入用户消息（仅目标）、Run kind、冻结快照、幂等记录与 queued 事件；同键同输入重放原 Run，同键不同输入冲突；幂等重读核对 Run kind。
- 执行归属：主 Agent Run 无 typed Executor 时安全失败为 `MAIN_AGENT_FAILED`，不会回落诊断；冻结输入缺失／版本未知／损坏时失败为 `MAIN_AGENT_INPUT_UNAVAILABLE`；ordinary answer 只写一条 delivery、一条助手消息和唯一成功终态；needs_input 的缺失集合必须等于快照缺失侧；被篡改引文的比较交付整事务回滚且无残留。
- 事件与取消：成功事件序列为 `run_queued → run_started → 普通事件 → run_succeeded`，序号连续；取消胜出后交付与助手消息均不写，终态保持 `cancelled`；取消后到达的普通事件被 running 谓词拒绝，不产生第二终态。
- 重跑：复制冻结 query／材料原文／上下文／规则版本，生成本 Run 新材料 ID 与用户消息，保留 `rerun_of_run_id`；重跑指纹含 `source_run_id`，同键重放返回同一 Run。
- 迁移：有历史 rerun 行的非空库可升级并回填 `diagnosis`；CHECK 拒绝非法 kind；无 V2 数据时可 downgrade 且历史行／外键关系保留、可再次 upgrade；存在 main Agent Run 或仅存在 `run_inputs` 行时拒绝 downgrade，版本与数据保持不变。
- 兼容：legacy 四大聚焦套件 61 项与全量测试保持绿色；P10／P11／P12 冻结资产未改写。

### 已知边界（不勾选整条 AC）

- 交付接纳当前已复核身份、材料 ID、能力／规则版本、行号范围与逐字引文，但完整差异块序列重算、50 块上限与实际 Tool 输出接纳归实施-2；当前不具备“比较完成”交付的真实生成路径。
- 受理时上下文选择仍传空元组；最近 4 条／2000 码点选择与冻结归实施-2／实施-3。
- 尚无主 Agent 模型适配、bounded graph、capability 注册、TextCompareTool、公开 API、前端与会话默认入口；不能从正式 REST／SSE 到达主 Agent。
- 未新增 main Agent 专属的同键并发竞争测试；幂等核心与 legacy 共用，A2-6／A2-7 的运行隔离与取消竞争在实施-2 用 Event／Barrier 取证。
- 未执行独立代码审查、未 stage／commit／push；不声称任何 AC 整条通过或首闭环交付。

### 实施-1 对应的 AC 片段

| AC | 已取得的片段证据 | 状态 |
|---|---|---|
| AC2 | 缺材料可冻结为输入，needs_input 缺失集合由快照对照校验；无比较结果伪造 | 片段 |
| AC9 | query／材料码点与行数上限在输入边界拒绝 | 片段 |
| AC10 | 写成功事务逐块复核行号与逐字引文，失败整事务回滚 | 片段（完整序列重算待实施-2） |
| AC14 | 同键重放／冲突、重跑指纹含来源、冻结输入重跑 | 片段（交错执行待实施-2） |
| AC15 | 取消后不写交付／消息／第二终态，迟到事件被丢弃 | 片段 |
| AC16 | 零／多终止、终止后输出、异常均关闭为唯一封闭失败 | 片段 |
| AC17 | 凭据形态输入在落库前拒绝；助手消息出站前检测 | 片段（模型／Tool 路径待实施-2） |
| AC20 | legacy 全量回归与迁移兼容 | 片段（API／前端待实施-3） |

以上片段不作为整条 AC 通过；AC1、3–8、11–13、18–19 仍无实施证据。

## 实施-2 · 主 Agent、能力 Tool 与安全接纳（2026-10-21）

状态：开发与聚焦验证完成，后端全量回归通过，G2 判定见下节。主 Agent 仍未装配进公开 API／前端入口，正式 REST／SSE 尚不能到达主 Agent；独立代码审查待三片完成后统一执行。

### 生产改动

- 新增 `backend/src/core/main_agent_model.py`：`MainDecisionV1` 封闭判别联合（`answer`／`needs_input`／`invoke_capability`，`extra="forbid"` + `frozen=True`）、`MainAgentModelAdapter.decide`（先区分“调用失败”与“JSON／schema 无效”，固定安全错误）、`MainMockScenario` 显式场景与 `parse_main_mock_scenario`（不从 query 词汇推断）。
- 新增 `backend/src/core/main_agent_graph.py`：bounded StateGraph，一次 typed 决策 → 直答／追问／能力三分支；`needs_input_prompt` 只由冻结快照的缺失侧派生；失败码封闭枚举。
- 新增 `backend/src/agents/main_agent.py`：`BaseAgent` 子类 `MainAgent` 与 `MainAgentTask`；构造时校验能力／工具菜单与预算硬上限；提示词只携带 query 与 A／B 材料 ID，不含原文；Tool 调用只能经 Gateway。
- 新增 `backend/src/capabilities/__init__.py`、`backend/src/capabilities/text_compare.py`：不可变 `CapabilityDefinition` ＋显式 `CapabilityRegistry`（重复注册拒绝、未知返回 None、无扫描／热加载／市场）；`TEXT_COMPARE_CAPABILITY`（`text.literal_compare@1`／规则 `literal-lines@1`）与确定性 `compare_materials`（`difflib.SequenceMatcher(autojunk=False)`，1 基行号、LF 精确引文、50 块上限失败关闭）。
- 新增 `backend/src/tools/text_compare.py`：`TextCompareTool` 严格校验材料引用归属、规则版本与同侧引用，只返回 typed JSON 或安全 `unavailable`。
- 新增 `backend/src/infrastructure/agent_runtime/run_executor.py`：`MainAgentRunExecutor.stream` 每 Run 现造 client／adapter／ToolRegistry／Tool／Gateway／MainAgent／graph／计数器；事件 data 只含安全摘要；失败码映射封闭。
- 修改 `backend/src/core/llm.py`：向后兼容新增 `request_timeout`／`max_retries`／`http_client` 与 `is_mock`；legacy 默认为 60s／retries=2，V2 显式 30s／retries=0；非法值拒绝。
- 修改 `backend/src/core/tool_gateway.py`：导出与出站共用同一识别范围的纯检测 `contains_sensitive_content`，未放宽执行或出站规则；等待仍为 3 秒，超时不宣称底层已停止。
- 修改 `backend/src/application/services.py`：受理时冻结最近上下文（只纳入成功且未归档的 V2 `answer`／`needs_input` Run 及其 user 目标，最多 4 条／2000 码点、整条消息、`(created_at, str(id))` 排序、比较交付排除）；上下文命中敏感内容在零写入前拒绝；重跑复制冻结上下文。
- 测试新增／扩充：`tests/test_main_agent_runtime.py`（26→60 项）、`tests/test_text_compare.py`（16 项，新增）、`tests/test_llm_client.py`（V2 重试／超时与 legacy 保持）、`tests/test_p2_schema.py`（补入经批准的新增 CHECK `ck_diagnosis_runs_diagnosis_run_runtime_kind_valid`）。

### 命令与结果

- 后端全量（清除继承的 `OPERMIND_BASE_URL`／`OPERMIND_MODEL`／`OPERMIND_APP_DATABASE_URL`，注入 `OPERMIND_API_KEY=mock` 与临时应用库）：`968 passed, 3 warnings in 679.54s (0:11:19)`，命令退出码 `EXIT:0`。
- `pytest tests/test_main_agent_runtime.py tests/test_text_compare.py tests/test_llm_client.py -q`：`87 passed in 92.77s`。
- `pytest tests/test_p2_schema.py tests/test_v2_main_agent_migration.py tests/test_p12_migration.py tests/test_persistence_infrastructure.py -q`：`26 passed in 23.11s`。
- `pytest tests/test_harness_contract_kernel.py tests/test_harness_runtime_adapter_contract.py tests/test_harness_regression_baseline.py tests/test_harness_p11_runtime_safety.py tests/test_harness_p11_tool_connector_safety.py tests/test_tool_gateway.py tests/test_usage_recording.py -q`：`126 passed in 39.82s`。
- `ruff check .`：`All checks passed!`；`mypy`：`Success: no issues found in 132 source files`（仅 2 条既有 untyped body note）。
- `git diff --check`：通过（仅 Git 的 CRLF 转换提示）。
- 运行事件（如实记录）：第一次全量运行在 89% 处停止推进约 13 分钟、CPU 不再增长。根因是上一次未结束的后台 pytest 进程与本次运行并发使用同一个临时库 `.tmp/full-suite.sqlite3`，SQLite 写锁互相阻塞；旧日志又是块缓冲，卡住的位置被延迟刷出，一度误判为业务测试挂起。处置为终止残留进程、删除该临时库，并以 `python -u` 无缓冲输出、加 `faulthandler_timeout=180`／`faulthandler_exit_on_timeout=true` 重跑，得到上述 `968 passed`。全程只使用临时库，默认应用库 `data/opermind.sqlite3` 未被连接或写入。

### A2 兼容取证矩阵结果（G2 判定输入）

| 编号 | 取证测试 | 实际观测 | 结论 |
|---|---|---|---|
| A2-1 typed 模型响应 | `test_model_adapter_returns_typed_answer_without_tools`、`test_model_adapter_rejects_invalid_json_or_schema`（参数化：非 JSON、缺字段、额外字段、错误 kind）、`test_model_adapter_rejects_invoke_with_same_material_on_both_sides`、`test_model_adapter_maps_call_or_content_failure_to_unavailable` | 合法响应→typed 决策对象；非法响应→固定安全失败，`client.calls` 之后 Tool 调用为零；无关键词／正则／代码围栏兜底 | PASS |
| A2-2 mock／usage | `test_mock_scenarios_are_explicit_and_not_inferred_from_query`、`test_executor_mock_answer_ignores_comparison_and_ops_wording`、`test_executor_mock_needs_input_uses_snapshot_derived_prompt`、`test_executor_mock_compare_runs_real_deterministic_tool`；`tests/test_usage_recording.py::test_mock调用不采集`、`::test_usage缺失时不采集` | mock 只能由显式场景开关产生，事件带 `mode="mock"`；mock 与缺 usage 均不写记录，真实 usage 按实际映射采集 | PASS（V2 复用同一采集路径；逐 Run 成本保证不在范围） |
| A2-3 SDK 重试 | `test_v2_zero_retries_makes_exactly_one_http_attempt`（注入 `httpx.MockTransport`，连接失败一次）、`test_legacy_client_keeps_default_timeout_and_retry_budget`、`test_client_rejects_invalid_timeout_or_retry_values` | V2 客户端 `timeout=30.0`／`max_retries=0`，HTTP 尝试计数恰好 1；legacy 仍为 60.0／2 | PASS（证据为 MockTransport，不证明真实 Provider 网络行为） |
| A2-4 Gateway 防绕过 | `test_agent_calls_registered_tool_only_through_gateway`、`test_decision_cannot_smuggle_a_tool_outside_the_gateway`、`test_agent_fails_when_declared_tool_is_not_registered`、`test_main_agent_task_rejects_foreign_capability_or_tool_menu` | `_RecordingGateway` 记录到唯一一次调用；决策里携带未注册／非白名单工具名时直接 `CAPABILITY_UNAVAILABLE` 且模型无后续 Tool；已注册声明但缺失实现时失败关闭 | PASS |
| A2-5 唯一终态 | `test_guard_run_stream_requires_single_terminal_at_normal_eof`、`test_guard_run_stream_maps_exceptions_to_closed_codes`、`test_agent_maps_gateway_timeout_to_closed_failure`、`test_main_agent_answer_delivery_writes_unique_facts_once` | 零终止／多终止／终止后输出／意外异常均不产生交付；只有正常 EOF 后接纳唯一终态；Gateway 3 秒超时映射为封闭失败且不声称底层已停止 | PASS |
| A2-6 每 Run 隔离 | `test_two_runs_interleave_without_sharing_agent_or_tool_state`（`threading.Barrier(2)` 交错、单 executor 实例）、`test_two_runs_with_same_input_have_stable_blocks_but_own_identity` | 两 Run 的 client／registry／gateway／agent／graph 对象身份互不相同，材料引用按线程隔离，结果与事件归属正确；同输入两次运行块序列一致但 Run 身份独立 | PASS |
| A2-7 取消与迟到 | `test_cancel_winning_a_concurrent_run_leaves_no_late_delivery`（真实 `RunApplicationService` 双线程竞争）、`test_main_agent_cancel_before_delivery_keeps_cancelled_terminal`、`test_main_agent_event_after_cancel_is_discarded` | 取消胜出后事件序列停在 `run_queued → run_started → run_cancelled`，无交付、无助手消息、无第二终态；迟到交付与普通事件被 `running` 谓词拒绝 | PASS |
| A2-8 唯一产品事实 writer | `test_executor_stream_does_not_write_product_facts_before_service_commit`、`test_executor_rejects_material_refs_from_another_run`、`test_comparison_delivery_is_rejected_unless_blocks_recompute_exactly`（omit／forge 参数化）、`test_corrupt_or_unknown_run_input_fails_safe` | executor 单独跑完后 Run 仍 `queued`、`run_deliveries`／`messages` 为 0；交付必须等于服务端完整重算，漏块与伪造块整事务回滚 | PASS |

矩阵八项均有实际运行证据，G2 通过；据此允许进入实施-3 的默认入口切换。A3 委派边界不在本包。

### 行为证据

- 决策语义：普通问题直答且 Tool 调用为零；含“数据库／SQL／查询”字样的比较请求仍选择已注册文本能力，不进入 DB 调查（AC1／AC3／AC4）。
- 能力与规则：`text.literal_compare@1` 只在组合根显式注册；重复注册同一版本被拒；未知规则版本、跨 Run 材料引用、同材料两侧、超 50 块均返回安全 `unavailable` 且无部分输出（AC5–AC9、AC10、AC12）。
- 差异正确性：相同文本与双方显式空文本得到“无差异、零块、正确归属”；新增／删除／修改块的 1 基行号与逐字 LF 引文正确；末尾换行保留空行；仅换行编码归一不吞掉空格／空行／大小写／标点差异；重复行不产生越界出处（AC5–AC8）。
- 输入与出站安全：模型提示词只含材料 ID 不含 A／B 原文；含指令式文本的材料只作为比较对象，不产生文件／网络／DB／Shell 访问；凭据形态在落库、模型调用与交付写库前分别拒绝；历史上下文命中敏感内容在零写入前拒绝（AC17）。
- 上下文冻结：只取最近 4 条未归档的 V2 `answer`／`needs_input` 消息，比较 Run 与其消息被排除；预算不足时保留整条消息而非截断（1200+1200 码点场景得到 3 条整消息）。

### 已知边界（不勾选整条 AC）

- 主 Agent 仍未接入公开 API／SSE／前端，AC18 的 Trace／审计／导出投影与 AC19 的刷新恢复没有实现证据；AC11 的“模型不可用”路径目前由替身与 MockTransport 证明，未做真实 Provider 调用（本包约束禁止外部访问）。
- A2-2 的 usage 证据复用 legacy 采集链路，未新增逐 Run 成本断言。
- 每 Run 隔离测试在同一 executor 实例内用 Barrier 控制交错，属于受控并发，不覆盖真实进程级故障或永不返回的 `next()`；有限流协议保护的 gap 仍按 P11 口径如实保留。
- 未执行独立代码审查，未 stage／commit／push；不声称任何 AC 整条通过或首闭环已交付。

### 实施-2 对应的 AC 片段

| AC | 已取得的片段证据 | 状态 |
|---|---|---|
| AC1 | 直答决策 Tool 为零 | 内核片段（API／UI 待实施-3） |
| AC2 | 追问提示词由冻结缺失侧派生，不产生比较结果 | 内核片段 |
| AC3 | 含运维词汇仍走文本能力 | 内核片段 |
| AC4 | 无效／未知决策失败关闭、零 Tool、无关键词回退 | 内核片段 |
| AC5–AC8 | 确定性比较的行号、引文、换行与重复行规则测试 | 内核片段 |
| AC9 | 上限在执行前拒绝、51 块整事务失败 | 内核片段 |
| AC10 | 跨 Run 引用、伪造／漏块交付重算拒绝 | 内核片段 |
| AC11 | 调用失败／内容失败／Gateway 超时映射为封闭不可用，无自动重试 | 内核片段（真实 Provider 未测） |
| AC12 | 预算硬上限校验、正常路径一次模型＋一次 Tool | 内核片段 |
| AC13 | 固定替身双跑一致、mock／缺 usage 不造数 | 内核片段 |
| AC14 | Barrier 交错运行、同键重放与来源区分 | 内核片段（API 层待实施-3） |
| AC15 | 取消胜出后无交付／消息／第二终态 | 内核片段 |
| AC16 | 零／多终止、终止后输出、异常均关闭 | 内核片段 |
| AC17 | 注入式材料无越权、凭据在落库／调用／出站前拒绝 | 内核片段 |
| AC20 | 全量 968 项与 harness 冻结基线保持绿色 | 片段（API／前端待实施-3） |

## 实施-3 · 正式 API／会话界面与全包兼容（2026-10-21）

状态：开发完成。独立代码审查已执行三轮：第 1 轮 FAIL（2×P1／4×P2）→ 修复；第 2 轮 FAIL（1×新 P1／3×P2）→ 修复其中 1×P1 与可自决的 1×P2；第 3 轮针对增量 **PASS**（0×P0／0×P1，2×P3）。遗留 2 项 P2 属公开契约变更（失败码分类、损坏行的降级投影），交用户裁决，未在实现层擅自发明。当前验证：后端全量 `984 passed`、前端串行全量 `246 passed`、typecheck／build／ruff／mypy 全绿，真实本地浏览器闭环按修正后的契约重跑并补测「提供／未提供开关」。模型为显式 mock，文本比较是服务端实际确定性计算。未 stage／commit；本节日志未勾选任何整条 AC。

### 生产改动

后端 API 与装配：

- `backend/src/api/v1/schemas.py`：`CreateRunRequest` 新增 `runtime_kind: Literal["diagnosis"] = "diagnosis"`（省略即 legacy），新增 `CreateMainAgentRunRequest`（`schemas.py:767`：`runtime_kind` 必填 Literal、query ≤200 码点、`text_a`／`text_b` 用「缺省＝未提供」与「空串＝显式空」区分，并按 `MAX_MATERIAL_CODEPOINTS` 在 schema 就限长，越限 body 不进入受理）；受理请求联合 `CreateRunPayload` 见 `schemas.py:786`。新增 `MainAnswerDeliveryResource`／`MainNeedsInputDeliveryResource`／`MainComparisonDeliveryResource`（按 `kind` 判别）、`TextDiffBlockResource`、`MainMaterialResource`、`MainInputSnapshotResource`。`DiagnosisRunResource`（`schemas.py:865`）新增 `runtime_kind`／`delivery`／`input_snapshot`，`validate_terminal_payload()`（`schemas.py:885`）按 Design §2.8 逐条收口：成功诊断必须有 `result` 且不得携带交付／输入快照，非成功诊断不得携带 `result`；成功主 Agent 必须有交付，非成功主 Agent 不得携带交付且不得携带 `result`；失败必须有安全错误、非终态不得携带安全错误（后两条为独立审查 P1-2／P2-1 补回，历史口径同时恢复）。
- `backend/src/api/v1/resources.py`：`run_resource()`（`resources.py:142`）按契约投影交付与冻结输入；`main_delivery_resource()`／`main_input_snapshot_resource()` 只做领域→资源映射。
- `backend/src/api/v1/routes.py`：`_main_projection()`（`routes.py:465`）只对 `RunRuntimeKind.MAIN_AGENT` 读 `run_deliveries`／`run_inputs`，legacy 直接短路返回 `(None, None)`；`with_snapshot` 开关按 Design §2.8 区分两种投影——Run 详情（`routes.py:490`）为 `True` 返回冻结输入，会话 Run 摘要列表（`routes.py:1459`）为 `False`，只带交付不带 A/B 原文（独立审查 P1-1 修正：我原先让列表同时携带快照，与已确认 Design 冲突）。
- `backend/src/api/v1/dependencies.py`：`_main_agent_run_executor()`（`dependencies.py:172`）装配 `MainAgentRunExecutor`，每 Run 现造 `LLMClient`（`request_timeout=30.0`／`max_retries=0`），能力仅显式注册 `TEXT_COMPARE_CAPABILITY`，mock 场景只来自 `OPERMIND_MAIN_AGENT_MOCK_SCENARIO`；`dependencies.py:364` 把它注入唯一 `RunApplicationService`。
- `backend/src/application/services.py`：`execute_run` 按 `run.runtime_kind` 分派——诊断轨道仍走历史 Coordinator 执行器，主 Agent 轨道才使用 V2 执行器；legacy 链路与普通消息旧链未改。
- `backend/src/application/session_export.py`：`_run_summary_block()` 对 V2 Run 走 `_main_run_summary_block()`（`session_export.py:115`），只输出目标脱敏文本、状态与「运行时：主 Agent」，不导出交付差异块或材料正文；失败错误行改由 `_safe_export_run_error()`（`session_export.py:47`）按 `runtime_kind` 取 `RunFailureCode.safe_message` 白名单文案，与 `resources._safe_run_error` 同一枚举来源，绝不透传原始错误文本（独立审查 P2-3：原先 V2 导出仍写「诊断执行失败」，且注释谎称同口径）。

前端：

- `frontend/src/api/v1/generated.ts`：由本地后端 OpenAPI 重新生成（`npm run generate:api` 口径），新增 V2 请求／交付／快照组件；`GlobalRunSummaryResource` 字段仍因 `ApiV1Model.field_serializer("*", when_used="json")` 退化为 `unknown`（既有全仓事实，前端 readers 负责运行时收敛）。
- `frontend/src/api/v1/client.ts:36`：`CreateRunPayload` 手工联合。后端把 `runtime_kind` 写成带默认值的常量字段，生成类型会强制显式传值；这里把 legacy 分支放开为可选，保持「省略即诊断」的既有调用点语义，V2 分支仍必须显式 `main_agent`。`queries.ts:341` 新增 `create_main_agent_run_mutation()`。
- `frontend/src/features/workbench/MainAgentComposer.tsx`（新增）：主 Agent 录入（`Composer` 可访问名「主 Agent 请求」）＋材料折叠开关＋`提交比较`；每侧一个「提供文本 A／B」复选框独立切换提供／未提供（未勾选提交 `null`，勾选后原样提交内容含空串，`MainAgentComposer.tsx:29`–`45`），未勾选侧文本框 `disabled`；每次点击新生成 `crypto.randomUUID()` 幂等键（`MainAgentComposer.tsx:43`）；错误只映射 `MAIN_AGENT_INPUT_REJECTED` 与 `VALIDATION_ERROR`（后者附「目标不超过 200 字，每段材料不超过 2000 字、100 行」码点提示）；不复用 send-intent、不写 localStorage 草稿。
- `frontend/src/features/workbench/main-delivery-readers.ts`（新增）：运行时收敛 `answer`／`needs_input`／`comparison` 与冻结输入；`read_line_range()`（`main-delivery-readers.ts:108`）对行号倒挂返回 `undefined`，`read_diff_block()` 随之短路。
- `frontend/src/features/workbench/MainDeliveryPanel.tsx`（新增）：`delivery_read.issues.length === 0` 才渲染差异内容（`MainDeliveryPanel.tsx:113`），否则只报「交付数据异常」；`answer`／`needs_input` 不重复渲染正文（正文已由服务端写成助手消息）；「展开本次输入」按需显示冻结 query 与两侧材料原文＋摘要。
- `frontend/src/features/workbench/WorkbenchPage.tsx`：`AssistantReply` 首行按 `runtime_kind` 分派到新的 `MainAgentReply`（`failed`→安全错误＋过程＋重跑，`cancelled`→诚实取消提示，其余→进度／回复／交付面板）；`MainAgentReply` 在「已成功但摘要列表不带冻结输入」时启用 `get_run_query` 懒读 Run 详情（`run_detail_input_snapshot()` 剥 `ApiResponse.data.run.input_snapshot`），交付面板取 `investigation.input_snapshot ?? 详情投影`——列表不带原文、按需读详情，正是 Design §2.8 与 AC19 的兼容做法（独立审查 P1-1 修复）；时间线标签 V2 为「主 Agent · V2」；录入区新增显式入口切换（`WorkbenchPage.tsx:1300`–`1316`）。`conversation-turns.ts` 的 `runtime_kind` 投影与注释同步为「诊断轨道与会话 Run 摘要列表恒为 null，仅 Run 详情返回 A/B 原文」。
- `frontend/src/features/shell/Composer.tsx`：新增可选 `label`（默认仍 `调查问题`），V2 入口用它区分可访问名。
- `frontend/src/styles/workbench.css`：追加 `.entry-mode`／`.main-agent-composer*`／`.main-delivery-panel*`，仅复用既有设计 token。

### 命令与结果

审查修复后的复跑（2026-10-21 收口，全部为本次实际输出）：

- 后端全量（第 2 轮 P1 修复与新增两项测试后最终复跑，2026-10-21）：`984 passed, 3 warnings in 668.68s (0:11:08)`，`EXIT:0`。较上一次记录的 `982` 多出的 2 项是第 2 轮修复补充的 `test_main_agent_explicit_empty_materials_report_no_difference`（显式空文本走公开链）与 `test_session_export_uses_main_agent_safe_error_for_failed_run`（导出白名单错误按 runtime kind 分支）。测试库由 `tests/conftest.py:31` 注入 `OPERMIND_APP_DATABASE_URL=sqlite:///<tmp_path>/…`，默认 `data/opermind.sqlite3` 未被连接或写入（本仓库 conftest 自带隔离，无需手工指定临时库）。
- `pytest tests/test_main_agent_runs_api.py tests/test_session_export.py tests/test_api.py tests/test_runs_list.py -q`：`37 passed in 72.52s`（请求／资源联合、互斥投影、越限不回显＋零写入、凭据零写入、事件／SSE／摘要列表不回显材料正文、详情返回冻结输入、重跑复制冻结输入、终态取消 409、导出中性摘要与白名单错误、OpenAPI 暴露 V2 组件）。第 2 轮修复后单独复跑 `pytest tests/test_main_agent_runs_api.py -q` → `15 passed`（该文件由 13 → 14 → 15 项）。
- 前端全量（第 2 轮修复后最终复跑）：`npm run test -- --no-file-parallelism` → `Test Files 25 passed (25)`、`Tests 246 passed (246)`（较上一记录 +1，即新增「勾选提供文本 A 不填 → 提交 `text_a:""`，且 B 侧仍 disabled」用例）；`src/app` 目录单跑 `48 passed`（V1 默认录入未被翻转）；`npm run typecheck` 无输出通过；`npm run build` 通过（仅既有 chunk 体积提示）；`npx openapi-typescript` 重新生成 `generated.ts`（+376／−3，新增 V2 请求／交付／快照组件）。上一轮串行 `245 passed` 记录保留在首轮证据中。
- `ruff check .`：`All checks passed!`；`mypy src`：`Success: no issues found in 132 source files`（仅 2 条既有 untyped-body note；120→123→132 随三片新增模块与测试增长）。
- 迁移专项复跑：`pytest tests/test_v2_main_agent_migration.py -q` → `5 passed in 11.35s`（upgrade 回填／空数据 downgrade＋重升／有 `main_agent` Run 拒绝回滚／只有 `run_inputs` 拒绝回滚／head 唯一；逐条见「最终交付门」）。每条都在 `tmp_path` 独立 sqlite 上 subprocess 真跑 alembic，默认库未动。
- `git diff --check`：通过（仅 Git 的 CRLF 转换提示）。
- 并行全量偶发超时如实记录：`npx vitest run`（并行）两次分别 `5 failed`／`2 failed`，失败项落在 `ModelSettingsPage`、`ApprovalsPage`、`MonitoringOverviewPage`、`ServiceCenterPage`、`main-agent.test.tsx`，报错形态是 `Test timed out in 5000ms` 与 `findByText` 找不到首个断言文本；同一批文件串行跑全部绿色，`main-agent.test.tsx + WorkbenchPage.test.tsx` 单跑 `7 passed`。判定为 jsdom 用例在本机并行抢占 CPU 后的超时抖动（首轮记录过同类），不是断言本身的回归，但也不宣称并行全量稳定绿。
- 首轮（审查前）记录保留：后端全量 `981 passed in 586.13s`；前端全量 `245 passed`；`test_main_agent_runs_api.py` `13 passed`；第一次前端并行全量 14 项失败中，`WorkbenchPage.test.tsx` 2 项是真实缺陷（固定健康入口），`App.test.tsx` 7 项＋`WorkbenchPage` 1 项是我把 V2 设为默认录入造成的真实回归（见「偏离」），其余 4 项为与后台 pytest 抢 CPU 的超时；修完后合跑 `55 passed`。

### 真实本地浏览器闭环（模型为 mock）

环境与边界：本窗口为「修正契约后」重跑取证共两次进程，都用临时应用库并先 `alembic upgrade head`（末条 `20261015_17_v2_main_delivery`），用完即删，未触碰默认库——第一次 `backend/.tmp/browser-evidence.sqlite3`（会话 `browser-evidence-2`／`browser-evidence-answer`，对应下面第 2–7 条），第二次 `backend/.tmp/browser-evidence2.sqlite3`（会话 `browser-evidence-switch`，对应第 1 与第 8 条：第 1 轮修复「提供／未提供开关」后重跑的录入流程与显式空文本）。后端 `uvicorn src.app:app --port 8000`，`OPERMIND_API_KEY=mock` 使运行时模式解析为 `mock`（`mode_source=env`），`GET /model/config` 实测 `{mode:"mock", mode_available:true}`，差异比较由服务端确定性 Tool 实际执行；顶栏如实显示「当前模型 未配置 · 演示」。前端 `vite --port 5175`（`5174` 已被本机既有 dev server 占用，未动它），`/api` 代理到本地后端。浏览器为 Qoder 内置 in-app Browser（CDP，隐藏视口 0×0，`click`／截图报 `NATIVE_BROWSER_VIEWPORT_UNAVAILABLE`）：交互与断言通过页面内真实事件（React 受控控件走原生 value setter ＋ `input` 事件）与真实网络请求完成，**未取得截图**，DOM 文本原样记录如下。

复跑取证（修正契约后：摘要列表带交付不带冻结输入，输入回看按需读 Run 详情）：

1. 比较交付（场景 `OPERMIND_MAIN_AGENT_MOCK_SCENARIO=compare`，会话 `browser-evidence-switch`）：进入 `/workbench/sessions/{id}`（会话页默认出现「调查问题」文本框，即 V1 录入）→ 点「主 Agent（V2）」→ 出现「主 Agent 请求」输入框与「附加文本材料（比较两段文本时填写）」折叠面板 → 展开后实测 `提供文本 A（旧）`／`提供文本 B（新）` 两个复选框默认未勾选、对应 `文本 A`／`文本 B` 文本框 `disabled=true` → 勾选两测后 `disabled` 解除，填 `文本 A`=`alpha/beta/extra line only in A`、`文本 B`=`alpha/beta/` → 点「提交比较」（`POST /sessions/{id}/runs` → `202`）。页面实际渲染：`主 Agent · V2`、调查过程「4 个事件 · 1 个工具调用／工具调用全部通过」（Agent 启动→路由决策→工具调用成功→Agent 完成）、助手消息「文本比较完成：共 1 个差异块。」、交付面板「存在差异｜能力 text.literal_compare@1 · 规则 literal-lines@1 · 差异块 1 个｜修改 A 第 3 行／B 第 3 行｜extra line only in A」、`展开本次输入`、`重新生成`。差异块与行号是服务端真实 `difflib` 计算结果，不是替身文本。
2. 列表／详情契约实测（同源 `fetch`）：`GET /sessions/{id}/runs?limit=20` 的 `items[0]` 为 `delivery.kind="comparison"`、`input_snapshot=null`，整份响应体只命中差异行 `extra line only in A`（交付按设计只引 differing 行），`alpha`／`beta`／目标原文三项均 `false`；`GET /runs/{id}` 详情返回 `input_snapshot`＝`{query:"比较这两段配置文本", rule_version:"literal-lines@1", text_a:{original_text:"alpha\nbeta\nextra line only in A", content_sha256:"00d00e38ba08…"}, text_b:{original_text:"alpha\nbeta\n", content_sha256:"e49c81e2d2f8…"}}`，且详情 `delivery` 内不含 `alpha`（正文只出现在冻结输入）。
3. 冻结输入的按需读取：提交后的网络清单里 `GET /runs/{id}` 由 `MainAgentReply` 的懒读查询自动发出（列表缺少快照时启用），点击「展开本次输入」后面板实测为「本次目标／比较这两段配置文本／文本 A／alpha beta extra line only in A＋摘要 00d00e38ba08…／文本 B／alpha beta＋摘要 e49c81e2d2f8…」（`.main-delivery-panel__raw` 三个节点）。
4. 刷新恢复（AC19，形态已随 P1-1 修正）：`location.reload()` 后网络清单为 `GET /sessions`、`GET /model/config`、`GET /sessions/{id}`、`GET /sessions/{id}/runs?limit=20`、`GET /sessions/{id}/messages?limit=20`、`GET /runs/{id}/events?limit=100`、`GET /runs/{id}`（1 次）。交付从列表响应即恢复（`存在差异｜能力 text.literal_compare@1 …`），冻结输入由这一条详情请求补齐；**没有** `POST /runs`，也没有第二次 Tool 执行；`Object.keys(localStorage)` 仍为 `[]`。与首轮证据的差别是诚实的：摘要列表不再携带 A/B 原文，因此刷新后确实多一次 Run 详情读取。
5. 直答交付（重启后端换 `OPERMIND_MAIN_AGENT_MOCK_SCENARIO=answer`，同库新建 `browser-evidence-answer`）：只填目标「这段配置该怎么排查」提交，页面显示「（模拟模型）这是一条普通回答，未执行文本比较。」＋调查过程「3 个事件／已完成」（无工具调用事件）；点「展开本次输入」实测为「本次目标／这段配置该怎么排查／文本 A／未提供／文本 B／未提供」，即未提供侧如实显示，不伪造材料。
6. 受理守卫实测（同源 `fetch`，同库）：`query` 201 码点 → `422 VALIDATION_ERROR`，`details` 只给字段与固定原因（`CreateMainAgentRunRequest: String should have at most 200 characters`）；`text_a` 2001 码点 → `422`，`details[0].field="CreateMainAgentRunRequest.text_a"`、原因 `at most 2000 characters`，响应体不含材料字符（`echoed:false`）；含 `sk-` 形态凭据 → `422 MAIN_AGENT_INPUT_REJECTED`，消息固定且不含凭据串。三者之后 `GET /sessions/{id}/runs` 仍只有 1 个 Run，即零 Run／零消息写入。
7. 出站泄露探测（同源 `fetch` 真实响应，探测词 `alpha`／`beta`／`extra line only in A`／目标原文）：`/runs/{id}/events` 与全局 `/runs?limit=20` 四项全 `false`；`/messages` 与 `/export` 只命中用户目标文本（即用户消息本身与导出「**目标**」脱敏行），材料关键字一律 `false`。导出正文实测为「### 第 1 次主 Agent 对话（…）\n**目标**：比较这两段配置文本\n**状态**：succeeded\n**运行时**：主 Agent」，无差异块、无材料、无引文；Run 详情是唯一回显材料正文的接口。
8. 显式空文本走产品入口（AC5，第 2 轮 P1 修复后补测）：同一会话勾选「提供文本 A」「提供文本 B」后把两侧清空，提交目标「两段都是空文本时也要有明确结论」→ 页面第二个交付面板实测「逐行一致｜能力 text.literal_compare@1 · 规则 literal-lines@1 · 差异块 0 个｜两份文本按行完全一致，未发现差异。」；`GET /sessions/{id}/runs` 的 `items` 为 `[[succeeded, no_difference, 0], [succeeded, has_difference, 1]]`，两个 Run 的列表投影都 `input_snapshot=null`；该 Run 详情实测 `input_snapshot.text_a.original_text=""`、`text_b.original_text=""`、两侧 `material_id` 不同、`content_sha256` 均为空串摘要 `e3b0c44298fc…`。「展开本次输入」显示「文本 A｜（空）｜摘要 e3b0c44298fc…／文本 B｜（空）｜摘要 e3b0c44298fc…」，与未提供侧显示的「未提供」可区分，即「显式空」与「未提供」在产品入口上是两条独立路径。
9. 清理：后端与 Vite 进程均已终止（`5175` 上残留的本 worktree vite 子进程经 CIM 确认命令行后用 `taskkill /F /T` 终止，共两次），`8000`／`5175` 释放，`backend/.tmp`、`frontend/.tmp` 内的临时库／日志／`openapi.json` 已删除；本地一次性 `OPERMIND_SECRET_KEY` 只存在于 shell 环境变量，全仓 grep 无残留。

首轮取证（审查前契约，`needs_input`／失败／V1 回切三条不受本次修正影响，保留原样）：

10. 缺材料追问（场景 `needs_input`）：只提交目标不填材料 → 助手消息「请提供文本 A（旧）和文本 B（新），我会做逐行字面比较。」，调查过程「3 个事件」且无工具调用事件，页面无「存在差异」或差异块——不伪造比较结果。
11. 失败反馈（未声明场景，`is_mock` 为真但无可用替身）：提交后页面显示 `OperMind · 主 Agent 请求未完成`＋「本次请求未完成／主 Agent 执行失败，请稍后重试」＋调查过程（2 个事件，无工具调用）＋`重新生成`，没有交付面板、没有编造正文。
12. V1 兼容：同会话点「服务调查（V1）」后 `textarea[aria-label="调查问题"]` 恢复出现、`主 Agent 请求` 输入框消失；前端全量 245 项（含 V1 会话管理、模型设置、取消／重跑、固定 intent、历史诊断结果）保持绿色。

### 契约与产品决策（本轮判定依据）

- 受理请求不用 `Field(discriminator=...)`：判别式要求 `runtime_kind` 必填，会让只带 `query` 的历史 legacy 请求直接 422。改为有序普通联合（主 Agent 分支在前），两成员都 `extra="forbid"` 且 `runtime_kind` 互斥 Literal，仍能无歧义收敛，且 schema 错误不回显材料原文（`test_limit_error_does_not_echo_material_text`）。
- 修复真实缺陷：`RunApplicationService.execute_run` 曾无条件使用 V2 typed 执行器，会把诊断轨道 Run 打成失败。改为按 `runtime_kind` 分派，V1 链恢复。
- 移除 `GlobalRunSummaryResource.runtime_kind`：无 AC 要求、无消费者，且会破坏 `test_runs_list.py` 的摘要字段白名单安全契约；`value.runtime_kind` 仍只用于内部选择安全兜底错误码。
- 会话 Run 摘要列表只携带交付、不携带冻结输入（`routes.py:1459` 传 `with_snapshot=False`）：首轮我曾以「AC19 刷新可省一次详情请求」为理由让列表同时带 A/B 原文，独立审查判定这违反已确认 Design §2.8「全局／会话摘要列表不带 A/B 原文」（P1-1）。已改回：交付留在列表以恢复「本次结果」，输入回看由前端按需读 Run 详情；全局 Run 摘要与事件／SSE 仍不回显正文。刷新形态因此多一条 `GET /runs/{id}`，实测见上第 4 条。
- 修复真实缺陷：`read_line_range()` 原来对行号倒挂只 push issue 却仍返回该块，面板会渲染非法行号；改为返回 `undefined` 并让整块短路，面板要求 `issues.length === 0` 才渲染差异内容。
- 固定健康调查入口（`WorkbenchPage.tsx:1155`）：`main_entry_available = can_send && !fixed_health_investigation`，该会话只允许点固定动作，不出现任何自由文本录入（曾写成 `||` 导致 2 项 `WorkbenchPage` 断言失败，属真实回归）。

### 独立审查与修复（首轮结论 FAIL，逐项处置）

只读子代理对 实施-3 diff 与 Design／PRD 交叉审查，结论 FAIL：2 项 P1、4 项 P2。逐条处置如下（详细分级见 `Workpack-审查.md`）：

- P1-1 会话摘要列表携带 A/B 原文违反 Design §2.8 → 已修（`_main_projection(with_snapshot=…)`，详情 `True`、列表 `False`；前端懒读详情）。
- P1-2 `validate_terminal_payload` 漏掉「非成功 Run 不得携带 `result`／`delivery`」 → 已修，并新增 `test_run_resource_rejects_inconsistent_projection`（6 个 `pytest.raises(ValidationError)` ＋ 1 个合法投影）。
- P2-1 重写校验器时删掉了历史「非终态不得携带安全错误」 → 已恢复在同一校验器内。
- P2-3 导出对 V2 失败 Run 仍写「诊断执行失败」，注释还声称同口径 → `_safe_export_run_error()` 改按 `runtime_kind` 取 `RunFailureCode` 白名单文案。
- P2-4 材料无 schema 级上限（大 body 要先过领域层才被拒） → `text_a`／`text_b` 加 `max_length=MAX_MATERIAL_CODEPOINTS`，`test_limit_error_does_not_echo_material_text` 追加零写入断言，并在浏览器内以真实 `422` 复测（见闭环第 6 条）。
- P2-2 交付／冻结输入行损坏时抛 `MainAgentDeliveryUnavailableError`，会让 Run 详情乃至会话列表 500 → **未在本包擅自发明新的公开降级契约**（需要一个明确的对外错误口径，属 Design 门），作为已知边界保留，复审时如实标注。

### 独立审查与修复（第 2 轮，结论 FAIL，逐项处置）

第 1 轮 5 项修复经复审确认全部真实落地（`with_snapshot` 分派、校验器四向互斥且不误拒 legacy、导出白名单覆盖 5 个 `RunFailureCode`、Pydantic v2 `max_length` 按码点计数与 `MAX_MATERIAL_CODEPOINTS` 同语义）。复审另有 1 项新 P1、3 项 P2：

- 新 P1（已修）：Design §2.9 要求「提供／未提供可独立切换，支持显式空文本」，但 `MainAgentComposer` 原来把留空一律塌缩成 `null`，导致**显式空文本在产品入口不可达**，AC5 的「双方显式为空」只有内核证据、公开链与界面都到不了。修复：每侧改为独立复选框（`提供文本 A`／`提供文本 B`，`MainAgentComposer.tsx:91`、`:110`），未勾选提交 `null`，勾选后原样提交其值（含空串）；新增前端用例「勾选提供后即使文本为空也提交显式空串，未勾选侧仍按未提供提交」与后端公开链用例 `test_main_agent_explicit_empty_materials_report_no_difference`（`text_a=""`／`text_b=""` → `succeeded`＋`comparison`＋`no_difference`＋零差异块＋两侧独立材料 ID 归属）。
- 新 P2（已补测）：导出白名单的 V2 分支没有失败用例覆盖 → 新增 `test_session_export_uses_main_agent_safe_error_for_failed_run`，断言导出含「主 Agent 执行失败，请稍后重试」且不含「诊断执行失败」。
- 新 P2（保留，需 Design 门）：`_failure_code()`（`backend/src/infrastructure/agent_runtime/run_executor.py:169`）把 `MODEL_UNAVAILABLE`／`MODEL_DECISION_INVALID`／`TOOL_FAILED` 一律收敛为 `MAIN_AGENT_FAILED`，与 AC11「显示相应安全失败／不可用」有差距。补开新错误码是公开契约变更（错误码会出现在 API 响应与界面文案），不在本包自行发明；连同上面 P2-2 的降级口径一起交用户裁决。
- 新 P2（保留）：一条损坏／未知版本的交付或冻结输入行会让 Run 详情乃至整个会话列表 500。复审指出 Design §2.8 原文「未知 kind／版本报安全不可用，不猜测」其实已经要求映射为安全不可用投影；但「`succeeded` 而交付不可投影」与刚按 §2.8 收紧的 `validate_terminal_payload`（成功主 Agent 必须有交付）直接冲突，属需求级缺口，需 Design 门而不是我在实现层猜。
- P3（记录未改）：列表逐行读交付的 N+1、`MainAgentComposer` 码点计数只在错误文案提示无实时计数、`schemas.py:767` 的 `max_length` 在 `strip()` 前计数、`LegacyDiagnosisRunAdapter` 命名、V2 新模块零日志（失败不可观测）。

第 2 轮修复后的验证：`pytest tests/test_main_agent_runs_api.py -q` → `15 passed`；`vitest run main-agent.test.tsx + WorkbenchPage.test.tsx`（串行）→ `8 passed`、`vitest run src/app` → `48 passed`。

第 3 轮（只审本轮 P1 修复增量：提供／未提供开关＋前端用例＋两个新后端测试）由只读子代理复审，结论 **PASS**：0×P0／0×P1，2×P3（提交后草稿与勾选态不复位判为可接受、外层 `<label>` 同时包裹两个 labelable 控件）。三轮完整分级、AC 表与遗留三项见 [Workpack-审查.md](Workpack-审查.md)。

### 与计划原文的偏离

计划 实施-3 原句是「会话内主 Agent 默认／V1 服务调查显式入口」，实际实现为**默认仍是 V1 服务调查录入，主 Agent（V2）为显式切换按钮**。理由：把 V2 设为默认后 `App.test.tsx` 7 项与 `WorkbenchPage.test.tsx` 相关项失败，都是「会话页默认出现『调查问题』文本框」这一 V1 已确认行为；PRD AC20 明确要求回归 V1 会话管理、服务调查、模型设置、取消／重跑、历史诊断结果和固定动作安全边界时保持已确认行为。默认口径需要用户另行确认后再改，本包不擅自翻转。

### 已知边界（不勾选整条 AC）

- 浏览器验证在隐藏视口的内置浏览器内完成，无截图；交互由页面内真实事件驱动，未人工目视核对视觉呈现。取消路径（AC15）与「运行中停止」按钮未在真实浏览器内计时验证，仅有内核与 API 层证据。
- 未调用真实 Provider（本包禁止外部访问）；AC11 的真实网络行为、AC13 的逐 Run 成本仍无证据。
- 交付／冻结输入行损坏（数据库行存在但反序列化失败）时对外仍是 500，未定义降级契约（第 1 轮 P2-2／第 2 轮 P2 保留项，复审指出 Design §2.8 其实要求「报安全不可用」，与本包刚收紧的成功态必须有交付的不变量直接冲突，属需求级缺口）；失败码保真同样待裁决：`_failure_code()` 把模型不可用／决策无效／工具失败一律收敛为 `MAIN_AGENT_FAILED`，拆开需要新增公开错误码。`needs_input` 与失败场景的浏览器取证为首轮记录，本轮未按新契约重跑（新契约只改成功态的输入回看路径，二者都不携带冻结输入）。
- SSE 断线重连后的恢复路径无自动化用例，只有事件读取的公开链测试。
- 前端并行全量存在超时抖动（详见「命令与结果」），收口证据以串行全量绿色 ＋ 相关文件单跑绿色为准。
- 首轮独立审查结论 FAIL，P1／P2 修复后复审结果待落盘；未 stage／commit／push；不宣称首闭环已交付。

### 实施-3 对应的 AC 片段

| AC | 已取得的片段证据 | 状态 |
|---|---|---|
| AC1 | 浏览器直答／比较分派仍走文本能力；API `test_main_agent_answer_request_delivers_plain_answer` | 公开链片段 |
| AC2 | 浏览器 `needs_input` 追问、零工具调用、无差异块；API `test_main_agent_missing_material_asks_for_input` | 公开链片段 |
| AC3 | 公开链 `test_main_agent_answer_request_delivers_plain_answer`（不继承服务、走文本能力）；「含运维词汇仍走文本」只有内核 `test_executor_mock_answer_ignores_comparison_and_ops_wording` | 混合（运维词汇半边仅内核） |
| AC4 | 公开链 `test_main_agent_request_rejects_service_id_and_unknown_field`＋schema 错误不回显；无效／夹带决策失败关闭只有内核 `test_model_adapter_rejects_invalid_json_or_schema`、`test_decision_cannot_smuggle_a_tool_outside_the_gateway`、`test_agent_fails_when_declared_tool_is_not_registered` | 混合（失败关闭半边仅内核） |
| AC5 | 公开链 `test_main_agent_explicit_empty_materials_report_no_difference`（双方显式为空 → `no_difference`＋零差异块＋材料归属）＋内核 `test_identical_and_explicit_empty_texts_have_no_difference`；界面新用例「勾选提供后即使文本为空也提交显式空串」 | 公开链片段（第 2 轮补） |
| AC6–AC8 | 浏览器真实差异块（修改／新增行号与逐字引文）＋ `test_main_agent_comparison_delivery_uses_real_deterministic_tool`＋readers／面板测试 | 界面＋公开链片段 |
| AC9 | `test_limit_error_does_not_echo_material_text`（含零写入断言）、浏览器真实 422 实测、前端码点提示文案 | 公开链片段 |
| AC10 | 交付必须由服务端重算（内核 `test_comparison_delivery_is_rejected_unless_blocks_recompute_exactly`）；readers 行号倒挂拒绝 | 片段（仅内核） |
| AC11 | 公开链 `test_model_failure_is_reported_as_safe_unavailable`＋浏览器失败态只显示固定安全错误 | 片段（真实 Provider 未测；失败码分类保真待裁决，见第 2 轮 P2） |
| AC12 | 事件计数实测（比较 4 事件 1 工具、追问 3 事件 0 工具）＋内核 `test_main_agent_task_rejects_budget_above_hard_caps` | 混合（预算上限仅内核） |
| AC13 | 顶栏如实显示「未配置 · 演示」，mock 不写 usage（`tests/` 对 main_agent 无 usage 断言） | 片段（用量半边无证据） |
| AC14 | `test_rerun_main_agent_run_copies_frozen_input`、`test_cancel_terminated_main_agent_run_returns_409`、`test_accept_main_agent_run_freezes_input_and_replays_same_key`；「同键不同输入冲突」公开链无 V2 用例 | API 片段（部分仅内核） |
| AC15 | 内核证据保留；浏览器未计时验证 | 未新增 |
| AC16 | 内核证据保留（`test_guard_run_stream_requires_single_terminal_at_normal_eof` 等） | 未新增（仅内核） |
| AC17 | `test_sensitive_input_is_rejected_before_any_write`＋浏览器真实 422 零写入实测 | API 片段 |
| AC18 | events／SSE／全局摘要／导出泄露探测＋消息列表；`test_session_export_uses_neutral_main_run_summary`、`test_session_export_uses_main_agent_safe_error_for_failed_run`；Trace／审计对 V2 无逐项断言 | 片段（Trace UI 只见安全摘要；审计半边无断言） |
| AC19 | 刷新后从 Run 列表恢复交付、冻结输入按需读 1 次 `GET /runs/{id}` 补齐、无第二次受理或 Tool 执行、`localStorage` 为空；SSE 断线重连恢复仍无用例 | 界面片段（无截图） |
| AC20 | 前端全量 245 项、后端全量 982 项、V1 录入默认保留且切换可回 | 片段 |

## 本轮文档检查（2026-10-19，不是实施验收）

总体：PASS（仅计划／需求状态一致性）。

- 17 份本轮文档的 126 个本地 Markdown 链接有效，无冲突标记；逐文件空白检查和 `git diff --check` 通过。
- 当前 PRD 的 20 条 AC 与 Issue #133 创建时需求快照逐字／顺序一致，全部未执行；按 `prd-reviewing` 核对范围、边界、降级／回归及追溯，没有把实现细节写入需求正文。
- PRD／双索引保持“已确认”，Design 已确认，Workpack 待计划确认；GitHub #133 本次读取为 OPEN，无 in-progress 标签，没有重复 Issue。
- 主工作区 backend／frontend／config 无改动；专用 worktree 干净，基线不变；未 stage／commit／push。

发现：无本轮文档阻塞项。行动：按 `dev-plan` 停在计划审阅点；本结论不勾选下述任何 AC，也不替代独立代码 Review。

## AC 取证清单

本清单是需求原文的验收索引，创建时全部未执行；实施-1／实施-2／实施-3 已逐项取得片段证据，定位与保留 gap 见上面各切片章节。整条 AC 的通过判定留到独立审查与最终交付门，本清单保持未勾选。

- [ ] AC1：普通直答无 Tool。
- [ ] AC2：缺 A/B 追问，不伪造比较完成。
- [ ] AC3：含运维词汇仍按比较目标选择。
- [ ] AC4：无效／未知决策零 Tool，无关键词回退。
- [ ] AC5：相同及显式空文本无差异。
- [ ] AC6：新增／删除及有效出处。
- [ ] AC7：修改双方精确行号／引文。
- [ ] AC8：换行编码、空格／空行／大小写／标点及重复行。
- [ ] AC9：材料／请求上限、差异块超限全量失败。
- [ ] AC10：跨 Run 材料、越界／伪造／漏报引文拒绝。
- [ ] AC11：模型／Tool／结果失败／超时，无重试／隐式 mock。
- [ ] AC12：模型4次／Tool1次硬上限，直答追问零 Tool。
- [ ] AC13：固定双跑及 usage 缺失／mock 不造数。
- [ ] AC14：同／跨会话交错、同键重放／冲突、来源不同 rerun。
- [ ] AC15：取消先提交后的迟到结果／事件隔离和无提案。
- [ ] AC16：有限流零／多终止、终止后输出、意外异常。
- [ ] AC17：材料注入无越权、合成凭据接纳前拒绝。
- [ ] AC18：Trace／日志／审计／导出／usage 不泄露原文及敏感数据。
- [ ] AC19：刷新重连／历史恢复与非诊断呈现。
- [ ] AC20：V1 接口／会话／模型／取消／重跑／结果／固定动作兼容。

## 最终交付门

- [x] 迁移 upgrade／空数据 downgrade／有 V2 数据拒绝 downgrade。证据在 `backend/tests/test_v2_main_agent_migration.py`：本轮独立复跑 `pytest tests/test_v2_main_agent_migration.py -q` → `5 passed in 11.35s`（同时计入全量 `984 passed`）。五条覆盖：① 有历史 Run（含 `rerun_of_run_id` 自引用）的库 upgrade 到 head 后 `runtime_kind` 回填为 `diagnosis`、`run_inputs`／`run_deliveries` 均为 0 行、末条版本为 `20261015_17_v2_main_delivery`，且写入未知 `runtime_kind` 被 CHECK 约束拒绝；② 无 V2 数据时 downgrade 回 `20260905_16_p14_role_models` 保留 legacy 行与自引用重跑关系、列与两张新表都消失，再 upgrade 仍正确回填；③ 存在 `main_agent` Run 时 downgrade 返回非 0、stderr 含「拒绝不安全回滚」、版本与该行不变；④ 只有 `run_inputs` 行时同样拒绝回滚且不删该行；⑤ alembic head 唯一、revision id ≤32 字符。每条都在 `tmp_path` 独立 sqlite 上以 subprocess 真跑 alembic，默认 `data/opermind.sqlite3` 未被连接。
- [x] 后端全量 `984 passed, 3 warnings in 668.68s`；`ruff check .` All checks passed；`mypy src` no issues in 132 source files。前端 `typecheck`／串行全量 `246 passed`／`build` 全通过（2026-10-21 收口复跑）。
- [x] OpenAPI 生成类型（`generated.ts` 重新生成）和受控本地浏览器闭环（模型为显式 mock，两轮取证 9 条记录，未取得截图如实标注）。
- [x] 独立代码 Review：三轮记录见 [Workpack-审查.md](Workpack-审查.md)，第 1／2 轮 FAIL 的 P1／P2 已修复并复跑，第 3 轮针对增量 PASS（0×P0／0×P1，2×P3）；遗留 2 项公开契约问题交用户裁决。历史基线与冻结 fixture 未改写。
- [ ] 差异清单、脱敏检查、实际启用状态和用户提交授权。（`git diff --check` 干净、全仓 grep 无凭据残留已完成；提交授权未获得，未 stage／commit）
