# P10 Harness Contract Kernel 与回归基线 · 工作包计划

> 状态：用户已于 2026-09-01 确认；立项与计划文档合入 `main`、建立干净实施 base 且开始门禁通过前不进入代码实施
> PRD：`docs/prd/agent-runtime/P9-harness-contract-kernel.md`（文件名保留 P9 规划来源，正式阶段为 P10）
> Design：`docs/design/agent-runtime/P9HarnessContractKernel实施Design.md`
> Issue：[#113](https://github.com/wzhwwwzzzhhh/oper-mind/issues/113)
> 立项与计划分支：`codex/p10-harness-contract-kernel`
> 立项与计划基线：`main` / `266a920`（PR #115）
> 实施分支、worktree 与 base：本计划确认并随立项文档合入 `main` 后，从新的干净 `main` 另行创建并记录

## 目标

在不改变任何生产调用链、公开 API、数据库、前端、权限、依赖或用户可见行为的前提下，为现有多 Agent Runtime 建立：

1. 框架无关、typed、versioned 的 Harness Contract Kernel；
2. 可复用的 Runtime Adapter / `DiagnosisExecutor` / `ToolGateway` 契约测试；
3. Run、Tool、安全 Trace、取消和固定动作链的确定性回归基线与不可绕过门禁。

P10 只交付共同语言、测试适配边界和现状保护，不接管生产状态，不新增 AgentTask / Attempt 等业务状态机，也不激活 P9 建议分期 A 的其余内容或 B–E。

## 开始门禁

- [x] P9 研究、综合矩阵、最终取舍与 Reader Review 已收口。
- [x] PRD、实施 Design、结构性独立 Review 与 issue #113 已完成。
- [x] Safe Trace 前置修复已通过 PR #114 合入 `main`；目标 Python 3.11.9 聚焦、全量、mypy/ruff 与 GitHub CI 证据已形成。
- [x] 用户已于 2026-09-01 将首个候选独立立项为 P10。
- [x] 用户已于 2026-09-01 确认本 Workpack 计划。
- [ ] 本立项与计划文档完成 Review、提交并合入 `main`。
- [ ] 从届时最新 `main` 创建干净实施分支/worktree，并记录确定 base SHA。
- [ ] 根 `.venv` 在项目支持的 Python 版本上可执行，现有聚焦测试与后端全量基线通过。
- [ ] `harness_zero_behavior.py` 单文件 bootstrap 经 Review 并记录 raw/canonical SHA-256，随后才允许写入 baseline。

开始门禁未全部满足时，不新增 contract module、Adapter fixture、回归测试或其他 P10 代码。

## 范围

### 只做

- 七类正交状态命名空间，以及通用 identity、contract version、generation / fencing value objects。
- 框架无关的最小 Runtime Adapter contract、reference fake conformance suite，以及当前 `DiagnosisExecutor` 的版本化 capability profile。
- 当前 `ToolGateway` 的允许、拒绝、参数校验与安全失败契约测试，不创建 Runtime 绕过入口。
- Run 生命周期、取消、Safe Trace、固定动作链和确定性重复运行的回归场景。
- 基于确定 base 的 zero-behavior baseline、四集合 diff、依赖/OpenAPI/Alembic/import graph、skip/xfail inventory 门禁。

### 明确不做

- 不修改现有 `DiagnosisExecutor`、`CoordinatorDiagnosisExecutor`、`RunApplicationService`、`ToolGateway`、生产 DI、路由或 Agent 顺序。
- 不新增或修改数据库迁移、公开 API/OpenAPI/SSE、前端、配置、依赖清单或 lockfile。
- 不新增 Agent、Tool、Connector、服务类型、真实外部访问、长期记忆、RAG、MCP、Shell、SQL 或网络执行能力。
- 不实现 AgentTask、Attempt、ContextManifest、BindingSnapshot、Registry、Policy、UoW、Event Pipeline、Recovery、Grant 或 durable worker。
- 不改变权限、审批、固定动作或副作用语义，不顺带修复范围外生产问题。

## 三个实施切片

### S1：Baseline bootstrap 与 Contract Kernel

- [ ] 仅先新增 `backend/tests/support/harness_zero_behavior.py`，完成 write/verify 逻辑 Review 与 SHA-256 记录。
- [ ] 在确定 base、四集合 bootstrap allowlist 和无其他 P10 代码的条件下生成 `zero_behavior_baseline.v1.json`。
- [ ] 新增 `backend/src/domain/harness_contracts.py` 与 `test_harness_contract_kernel.py`。
- [ ] 验证七维 tag 不可串用，value objects 可稳定 round-trip 并拒绝非法值；确认不存在阶段 B 业务实体、ORM 或框架私有类型。

完成证明：PRD AC1–AC3、AC11–AC14 对应门禁通过；baseline 生成器 hash、base SHA 与 bootstrap dirty inventory 进入 evidence。

### S2：Adapter Contract Test Harness

- [ ] 新增 `backend/src/application/runtime_contracts.py`、测试 support 与 reference fake contract suite。
- [ ] 新增 `current_capability_profile.v1.json`，由独立 observed probe 与 reviewed expected profile 精确比较。
- [ ] 分别验证当前 `DiagnosisExecutor` 和 `ToolGateway` 边界；不让二者实现同一职责，不修改生产 DI。
- [ ] 不支持能力以结构化 expected gap 表达；新增未知 gap、声明失真、`skip` 或 `xfail` 必须失败。

完成证明：PRD AC4–AC6、AC11–AC15 对应测试通过；生产 import graph 与受保护文件保持无 diff。

### S3：Regression Baseline 与最终边界门禁

- [ ] 新增 Run、Tool、安全 Trace、取消、固定动作和重复运行场景的稳定 oracle。
- [ ] 归一化 ID、时间与耗时，不快照模型正文、原始 Tool 输出、异常或 LangGraph 私有 state。
- [ ] 负向样例证明跨维度状态误用、ToolGateway 绕过和敏感 Trace 泄漏会被门禁拒绝，而测试用例本身通过。
- [ ] 执行四集合 diff、依赖、OpenAPI、Alembic head、生产 import graph 与 skip/xfail inventory 棘轮。
- [ ] 完成全量测试、独立 Review、AC evidence 与交付归档。

完成证明：PRD AC6–AC16 全部通过；无生产行为、API、迁移、前端、依赖或真实外部访问变化。

## 允许改动面

实现 Workpack 只允许 Design §7.3 的精确路径：

```text
backend/src/domain/harness_contracts.py
backend/src/application/runtime_contracts.py
backend/tests/support/__init__.py
backend/tests/support/harness_contracts.py
backend/tests/support/harness_zero_behavior.py
backend/tests/fixtures/harness/current_capability_profile.v1.json
backend/tests/fixtures/harness/zero_behavior_baseline.v1.json
backend/tests/test_harness_contract_kernel.py
backend/tests/test_harness_runtime_adapter_contract.py
backend/tests/test_harness_regression_baseline.py
backend/tests/test_harness_zero_behavior_gate.py
docs/workpack/P10-harness-contract-kernel/**
docs/workpack/归档/P10-harness-contract-kernel/**
docs/workpack/README.md
docs/design/agent-runtime/P9HarnessContractKernel实施Design.md
docs/prd/agent-runtime/P9-harness-contract-kernel.md
docs/prd/agent-runtime/README.md
docs/prd/README.md
```

allowlist 是上限，不是必须改动清单。若需要增加路径，必须先判断是否命中 PRD 排除项并回到 Design；禁止用宽泛 `docs/**` 或测试通过来豁免越界。

## 验证方法

后端命令从 `backend/` 执行：

```powershell
..\.venv\Scripts\python.exe -m pytest tests/test_harness_contract_kernel.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_harness_runtime_adapter_contract.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_harness_regression_baseline.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_harness_zero_behavior_gate.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_p2_application_services.py tests/test_p2_diagnosis_adapter.py tests/test_p2b_tool_trace.py tests/test_tool_gateway.py tests/test_agent_gateway.py tests/test_run_cancel.py tests/test_p5_controlled_action.py tests/test_action_proposal_list.py tests/test_p43_service_context.py -q
..\.venv\Scripts\python.exe -m pytest tests -q
..\.venv\Scripts\python.exe -m ruff check src/domain/harness_contracts.py src/application/runtime_contracts.py tests/support/harness_contracts.py tests/support/harness_zero_behavior.py tests/test_harness_contract_kernel.py tests/test_harness_runtime_adapter_contract.py tests/test_harness_regression_baseline.py tests/test_harness_zero_behavior_gate.py
..\.venv\Scripts\python.exe -m mypy src/domain/harness_contracts.py src/application/runtime_contracts.py
```

仓库根门禁：

```powershell
git diff --check
git diff --name-only "$baseSha...HEAD"
git diff --cached --name-only
git diff --name-only
git ls-files --others --exclude-standard
git status --porcelain=v1 --untracked-files=all
```

前端必须保持零 diff，因此不以补跑前端命令替代越界失败。所有测试离线执行，不连接真实模型、数据库、主机、日志系统、用户服务或网络。

## Review、证据与提交

- S1 bootstrap generator 必须先完成独立 Review 和 hash 记录，baseline 生成后才能继续其他 P10 文件。
- 每个切片在 `evidence.md` 按 PRD AC 记录命令、结果与稳定证据；只记录安全摘要，不写入原始输出、凭据或敏感哨兵。
- 全部切片完成后进行独立代码 Review；`review.md` 必须 PASS 才能进入交付。
- 工作包控制在 1–3 个紧密提交，建议提交顺序：
  1. `功能: 建立Harness契约内核与零行为基线`
  2. `测试: 建立Runtime适配与回归门禁`
  3. `文档: 收口P10 Harness工作包证据`
- 未经用户明确授权，不提交、推送、创建 PR 或合并。

## 停止条件

出现以下任一情况立即停止并回到 Design：

- 必须修改现有生产 Runtime、Run 服务、ToolGateway、API、迁移、前端、依赖或真实资源访问才能继续；
- 需要新增业务 identity、持久化状态、权限、Recovery、Grant 或 durable worker；
- 现有安全保证缺失且必须改变生产行为才能修复；
- baseline base 不再对应最新已确认主线，或 generator Review 后发生变化；
- 新增未知 capability gap、skip/xfail、越界文件或无法证明的非确定性行为。

停止后不放宽门禁，也不把缺口伪装成已交付能力。

## 状态

- [x] P10 已立项。
- [x] PRD、Design 与结构性 Review 已完成。
- [x] Workpack 计划已起草。
- [x] 用户已于 2026-09-01 确认本计划。
- [ ] 立项与计划文档合入 `main`，创建干净实施 worktree。
- [ ] S1–S3 实现、验证、独立 Review、提交与交付完成。
