# P10 Harness Contract Kernel 与回归基线 · 工作包计划

> 状态：用户已于 2026-09-01 确认；S1 已提交为 `1b91808`；S2 已完成实现、验证与独立 Review（PASS，无 P0–P3）；S3 尚未开始
> PRD：`docs/prd/agent-runtime/P9-harness-contract-kernel.md`（文件名保留 P9 规划来源，正式阶段为 P10）
> Design：`docs/design/agent-runtime/P9HarnessContractKernel实施Design.md`
> Issue：[#113](https://github.com/wzhwwwzzzhhh/oper-mind/issues/113)
> 立项与计划分支：`codex/p10-harness-contract-kernel`
> 立项与计划基线：`main` / `266a920`（PR #115）
> 实施分支：`codex/p10-harness-contract-kernel-impl`
> 实施 worktree：`D:/market-handsome/oper-mind/.tmp/worktrees/p10-harness-contract-kernel`
> 最终实施 base：`main` / `643c2c0c6d5630705ba89251a9cea58c505bb4ce`（PR #119）

状态分层：`docs/路线图.md` 只表示最后已合入 `main` 的阶段状态；本 plan、issue #113 与 evidence 表示当前独立 worktree 的实时实施状态。路线图不在 P10 zero-behavior allowlist 内，禁止为实时回写修改 generator/baseline 或扩大 allowlist；P10 合并后由独立文档收口同步。

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
- [x] 本立项与计划文档已通过 PR #116 Review、CI 并合入 `main`。
- [x] CI 前置 PR #119 已合入，独立实施分支/worktree 已从其 merge commit 重建，并记录最终 base SHA `643c2c0c6d5630705ba89251a9cea58c505bb4ce`。
- [x] 根 `.venv` 使用项目支持的 Python 3.12.13；内容等价 tree 上聚焦 `79 passed`、全量 `647 passed`，ruff 与 mypy 通过。
- [x] `harness_zero_behavior.py` 单文件 bootstrap 经独立子 Agent Review PASS；raw/canonical SHA-256 均为 `0a7a05ed86e139d5528deeae64653e1fc478dba4fbc1ff4afa4429e01d9df5b8`，随后才允许写入 baseline。

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

- [x] 仅先新增 `backend/tests/support/harness_zero_behavior.py`，完成 write/verify 逻辑独立 Review 与 SHA-256 记录。
- [x] 在确定 base、四集合 bootstrap allowlist 和无其他 P10 代码的条件下生成并默认复验 `zero_behavior_baseline.v1.json`。
- [x] 新增 `backend/src/domain/harness_contracts.py` 与 `test_harness_contract_kernel.py`。
- [x] 验证七维 tag 不可串用，value objects 可稳定 round-trip 并拒绝非法值；确认不存在阶段 B 业务实体、ORM 或框架私有类型。

完成证明：PRD AC1–AC3、AC11–AC14 对应门禁通过；baseline 生成器 hash、base SHA 与 bootstrap dirty inventory 进入 evidence。

### S2：Adapter Contract Test Harness

- [x] 新增 `backend/src/application/runtime_contracts.py`、测试 support 与 reference fake contract suite。
- [x] 新增 `current_capability_profile.v1.json`，由独立 observed probe 与 reviewed expected profile 精确比较。
- [x] 分别验证当前 `DiagnosisExecutor` 和 `ToolGateway` 边界；不让二者实现同一职责，不修改生产 DI。
- [x] 不支持能力以结构化 expected gap 表达；新增未知 gap、声明失真、`skip` 或 `xfail` 必须失败。

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

## 开始门预检证据

- PR #116 merge commit：`45f6e934d89c4862b88fa762de920e7e7fc8e6fd`。
- PR #119 merge commit / 最终实施 base：`643c2c0c6d5630705ba89251a9cea58c505bb4ce`；Backend、Frontend 与 Gitleaks CI 全部通过。
- 预检 tree：`890a6d6c85a727b7b188d606e8b463bf6f900c1f`；`7ae80ef` 与 `45f6e93` 的 tree diff 为空。
- 受控环境：Codex bundled Python 3.12.13 创建 worktree 根 `.venv`，满足项目 `requires-python >=3.11`；依赖严格来自 `backend/requirements.txt`，未升级 pip、未修改依赖文件。PR #116 GitHub CI 继续覆盖 Python 3.11。
- 聚焦回归：计划列出的九个既有测试文件，`79 passed`。
- 后端全量：`647 passed`；ruff `All checks passed`；mypy `Success: no issues found in 113 source files`。
- worktree tracked/untracked 状态为空；`.venv` 为 Git ignored 环境产物。
- bootstrap generator 是最终 base 后唯一新增代码文件；独立子 Agent 在不修改文件的前提下完成安全、确定性、Git 四集合、Windows/CRLF、AST inventory、import boundary、profile ratchet 与 baseline immutability Review，最终结论 `PASS`。
- Reviewer 复核对象的 raw/canonical SHA-256 均为 `0a7a05ed86e139d5528deeae64653e1fc478dba4fbc1ff4afa4429e01d9df5b8`；本地 `Get-FileHash -Algorithm SHA256` 结果一致。
- Design §7.1 的 `docs/workpack/harness-contract-kernel/plan.md` 是旧名；生成器按 §7.3、§8.1 与实际 active Workpack 使用精确路径 `docs/workpack/P10-harness-contract-kernel/plan.md`，Reviewer 判断不构成阻断。
- 使用 base `643c2c0c6d5630705ba89251a9cea58c505bb4ce` 与上述 reviewed raw hash 执行唯一一次显式写模式，脚本内置复验与随后独立默认 verify 均为 `PASS`。
- baseline SHA-256 为 `095b21121b58bc1ab2096fc268c6fc47ee1c0a7b1634f85f77850f915c732e65`；记录的 normalized OpenAPI SHA-256 为 `a47be238cb5e3652b382a73a6b48d99af23a26608ec7fcf07b02556bae7b15a3`，Alembic head 为 `20260815_14_merge_p8_heads`，既有 skip/xfail inventory 为 2 条。
- S1 已新增 `backend/src/domain/harness_contracts.py`、`backend/tests/test_harness_contract_kernel.py` 与本 Workpack `evidence.md`；首轮 Review P2 修订后聚焦 `14 passed`、后端全量 `661 passed`，ruff、mypy、默认 zero-behavior 门禁与 `git diff --check` 均通过；重建后提交为 `1b91808`。
- S2 已新增未接入生产的 runtime contract、测试 support、版本化 capability fixture 与契约测试；三轮修订后最终独立 Review PASS、无 P0–P3，本次修复仍不进入 S3。

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
- [x] 立项与计划文档已通过 PR #116 合入 `main`，独立实施 worktree 与受控环境已创建。
- [x] 开始门状态同步已通过 PR #117 合入 `main`，实施 worktree 已快进并记录最终 base。
- [x] S1 Contract Kernel 实现、验证与独立 Review 完成；重建后提交为 `1b91808`。
- [x] S2 Adapter Contract Test Harness 已实现并完成本地验证；独立 Review 最终 PASS，无 P0–P3。
- [ ] S3 Regression、最终独立 Review、提交与交付完成。
