# P11 Agent Harness 真实运行安全门 · 工作包计划

> 状态：active；S1/S2 已实施，全量验证与独立只读 Review 均 PASS，待用户验收
> PRD：`docs/prd/agent-runtime/P11-harness-real-runtime-safety-gate.md`
> Design：`docs/design/agent-runtime/P11AgentHarness真实运行安全门实施Design.md`
> Issue：[#121](https://github.com/wzhwwwzzzhhh/oper-mind/issues/121)
> 实施分支：`codex/p11-harness-real-runtime-safety-gate`
> 实施 worktree：`D:/market-handsome/oper-mind`
> 最终 origin/main base：`602323899595e2db34876d6cfc2f47e38ae74096`

## 目标与边界

在现有 `RunApplicationService` 唯一业务写路径上激活最小 Runtime 输出保护，并补齐 ToolGateway 等待超时、结果接纳、底层停止状态的诚实语义；以 deterministic fake 证明既有 PostgreSQL/Redis 资源级超时、只读、命令集合和脱敏，建立默认离线及真实验证软件前门。

不进入 P12，不新增 Task/Attempt、Recovery、全局 Run deadline、跨进程取消、迁移、公开 API、SSE、前端、新服务、新 Connector、新 Tool、权限或真实 PostgreSQL E2E。实施与验收不得连接、探测、读取、写入或清理真实外部资源。

## 开始门

- [x] `origin/main` 已 fetch 并固定为 `602323899595e2db34876d6cfc2f47e38ae74096`。
- [x] PRD 为 `status: 已确认`、`phase: P11`、`issue: 121`。
- [x] Issue #121 唯一，未拆平行工作包。
- [x] 实施 Design 已完成独立只读 Review，结论 PASS、无 P0–P3。
- [x] 用户于 2026-09-03 明确确认 Design。
- [x] 独立 `codex/` 分支从最终 base 创建；当前 worktree 只有本任务写入。
- [x] 使用 Codex bundled Python 3.12.13 按 `backend/requirements.txt` 重建根 `.venv`，并先复跑 P10 Contract Kernel、Runtime Adapter、ToolGateway 与 regression baseline：`75 passed`。

最后一项未满足前不修改生产 Runtime、ToolGateway 或 Connector；不得修改依赖清单迁就本机环境。

## 两个紧密切片

### S1：Runtime 唯一终态与安全失败

1. [x] 新增无状态 Runtime signal guard，把 executor factory、iterator 构造、迭代与信号转换纳入同一安全边界。
2. [x] 在 `RunApplicationService` 现有消费点单点接线；只有正常 EOF 后的唯一 result 可进入现有 `_complete_success()`。
3. [x] 零终止、多终止、终止后输出、非法对象与意外异常统一形成安全 typed failure，并由现有公开错误映射为 `DIAGNOSIS_FAILED`。
4. [x] 保留无限流、阻塞 cleanup、全局 deadline 与 adapter cancellation gap；补 capability v2 和行为探针。

### S2：Tool/Connector 超时与真实验证前门

1. [x] ToolGateway 增加等待、接纳、底层执行三维内部状态；timeout 后显式 cancel 排队 future，并隔离运行中 future 的迟到结果、异常和 audit summary。
2. [x] 修复 PostgreSQL owned-engine dispose 的安全收敛；用 fake 精确验证 PostgreSQL/Redis 超时、只读、允许命令、主流程失败与 finalizer cleanup。
3. [x] 在 pytest collection 前建立默认离线环境与外部入口 blocker；新增只校验 opt-in、目标和凭据引用的软件 preflight。
4. [x] 保持 P10 baseline/generator/v1 原字节，转换为历史树复验，并建立独立 exact-path P11 stage gate。

## 精确允许范围

允许范围严格等于已确认 Design §8.1；allowlist 是上限，不需要的文件保持无 diff。生产文件最多只有：

```text
backend/src/application/runtime_safety.py
backend/src/application/services.py
backend/src/core/tool_gateway.py
backend/src/infrastructure/services/postgres_connector.py
```

其余允许项只限 Design 列出的 P11 scripts/tests/fixtures/support、P10 gate 转换、本 Design 与本 Workpack。禁止修改 P10 baseline、generator、v1 profile、runtime contracts、生产 DI、PostgreSQL engine、Redis connector、既有 Tool、迁移、API、前端、依赖和 CI。

如需扩大 exact path 或触及禁止项，立即停止并回到 Design/用户确认。

## 验证矩阵

至少执行：

```powershell
# backend/
..\.venv\Scripts\python.exe -m pytest tests/test_harness_p11_runtime_safety.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_harness_p11_tool_connector_safety.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_harness_contract_kernel.py tests/test_harness_runtime_adapter_contract.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_tool_gateway.py tests/test_agent_gateway.py tests/test_postgres_connector.py tests/test_redis_connector.py tests/test_db_tools_real.py tests/test_db_lock_pool_tools.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_harness_regression_baseline.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_harness_zero_behavior_gate.py tests/test_harness_p11_stage_gate.py -q
..\.venv\Scripts\python.exe -m pytest tests -q
..\.venv\Scripts\python.exe -m ruff check .

# repo root
git diff --check
git status --porcelain=v1 --untracked-files=all
```

阶段门另检查 committed/staged/unstaged/untracked 四集合、敏感字面量、P10 历史 hash、OpenAPI/Alembic/依赖/注册集合、skip/xfail inventory 和 exact path 范围。

## Review 与交付

- S1、S2 均完成后集中验证。
- 允许唯一独立子 Agent 做只读实现 Review；所有 P0–P3 必须修复并重新验证。
- `evidence.md` 逐条记录 AC1–AC19 的可重复命令与安全摘要；`review.md` 记录最终 Review。
- 未经用户明确要求，不提交、推送、创建 PR 或合并。
