# P12 PostgreSQL、Redis 与 MySQL 真实只读接入 · 工作包计划

> 状态：active；Design 已确认，实施已获授权
> Issue：[#124](https://github.com/wzhwwwzzzhhh/oper-mind/issues/124)
> PRD：`docs/prd/service-center/P12-three-service-real-readonly-integration.md`
> Design：`docs/design/service-center/P12-three-service-real-readonly-integration-design.md`
> 实施分支：`codex/p12-124-implementation-design`
> 实施 worktree：`D:/market-handsome/oper-mind/.tmp/worktrees/p12-124-design`
> 最终 origin/main base：`73292fbf4bf1a772849c94f54fe0e0b3e2108c08`

## 1. 开始门与授权

- [x] 已执行 `git fetch origin main`；HEAD、origin/main、merge-base 均为最终 base。
- [x] 当前分支精确为 `codex/p12-124-implementation-design`；本 worktree 只有本任务写入。
- [x] P12 PRD 为 `status: 已确认`、`phase: P12`、`issue: 124`；Issue #124 为 OPEN。
- [x] P12 只有一个 PRD、一个 Issue、一个 active Workpack，无平行工作包。
- [x] 实施 Design 已完成独立只读 Review，P0/P1/P2/P3 均为 0。
- [x] 用户已明确确认 Design，并授权创建 active Workpack、实施、离线测试、Review、提交、推送和最终实施 PR。
- [x] 用户明确授权一个最小迁移：仅把 `service_registry_kind_valid` 从 `postgres/redis` 扩展为 `postgres/redis/mysql`。

本授权不包括真实 MySQL/PostgreSQL/Redis、真实模型 Provider、真实凭据、PR 合并、额外服务类型或任何写能力。真实验收软件可实现，但本 Workpack 不实际运行。

## 2. 目标与顺序

严格在一个 Workpack 内顺序实施：

1. **S1：统一服务 Binding 与 PostgreSQL 端到端接线**；
2. **S2：Redis 最小 Agent 只读调查**；
3. **S3：MySQL 最小真实只读接入**。

S1 聚焦测试通过并写 evidence 后才能进入 S2；S2 同理。S3 后统一完成阶段门、全量验证与独立只读代码 Review。

## 3. S1：统一 Binding 与 PostgreSQL

### 3.1 实施项

- 在现有 `ServiceRegistry` 的同一 connector entry 上建立 typed internal binding 与 Agent 窄 capability view，不创建第二 registry/target map。
- 静态 env 和动态密文都只在受信装配边界进入同一 connector/capability factory；DBAgent Tool 不再运行时查询 env DSN。
- Session/Run 的显式 service_id 解析为同一 binding；not-found、type mismatch、session mismatch 和 poisoned entry 在外联前失败，禁止默认目标回退。
- definition、supported investigation、kind profile、Tool 名与 capability 在 entry 暴露前校验；UI 不得先看见半接入 capability。
- 注册 create/update/delete 使用同 service_id mutation guard，候选只在 DB commit 后暴露；不可恢复 CAS 异常只 poison 同一 entry。
- PostgreSQL `service_health_pressure.v1` 固定调用无参数 `check_connection_pool`；既有慢查询 Tool 保持兼容。
- 模型 driver 与 service fact source 完全正交；mock/real 模型配置不能切换或替换 binding。

### 3.2 S1 验收与测试

- `test_p12_service_binding.py`：静态/动态同源、origin、entry contract、并发/commit failure、per-ID poison、无 fallback、模型/事实源 2×2。
- `test_p12_postgres_end_to_end.py`：动态注册 → 连接测试 → Session → Run → fixed Tool → 唯一终态、安全 Trace/Result。
- 相关既有回归：service registration、PostgreSQL connector、DB Tool、session/run、runtime adapter、ToolGateway。
- 所有外部访问由 fake connector/capability/driver 接管；测试中连接尝试必须由 P11 blocker 拒绝。

## 4. S2：Redis 最小 Agent 只读调查

### 4.1 实施项

- 新增无模型参数 `redis_health_overview`，只返回 availability、memory bytes、client connections、slowlog count、observed/source status。
- capability 唯一命令集为 `PING`、`INFO memory`、`CLIENT LIST`、`SLOWLOG LEN`；CLIENT LIST 仅计数后丢弃原始行。
- 禁止 key/value、原始 slowlog、配置正文、任意 Redis command 参数及写命令。
- Redis definition 增加 `service_health_pressure.v1`；API 安全投影、ServiceCenter 入口、Workbench intent/template 与当前卡片 service_id 完整闭合。
- Redis timeout、cleanup、typed failure 与 P11 迟到结果隔离保持诚实。

### 4.2 S2 验收与测试

- `test_p12_redis_investigation.py`：exact command ledger、字段白名单、failure/timeout/cleanup、无参数 Tool、禁止命令负向探针。
- `test_redis_connector.py`、服务 API 与前端 MSW 交互回归。
- tampered/unknown intent 只保留已创建空 Session，不自动填问句、不创建 Run。

## 5. S3：MySQL 最小真实只读接入

### 5.1 实施项

- 依赖只增加 `PyMySQL==1.2.0`，不引入第二 MySQL driver。
- 新增 revision `20260904_15_p12_mysql_kind`，文件 `20260904_15_p12_mysql_service_kind.py`；只替换 named CHECK，不增加表/字段/索引/回填。
- SQLite 使用 batch alter；其他 dialect 使用等价 drop/create。downgrade 先检查 MySQL row，存在则失败关闭且不改数据/约束。
- MySQL DSN 只接受 `mysql+pymysql://`、username/host，database path 必须空、URL query allowlist 为空；timeout/charset 由 factory 固定注入。
- 使用 `NullPool` 和短生命周期连接，只执行两条固定 SHOW，返回 Design 固定标量；不读取业务表、PROCESSLIST、任意 SQL 或管理事实。
- API/前端只把 mysql 加入既有 kind 合法值，不新增 endpoint/field，不手改 OpenAPI generated file。
- 实现纯软件 preflight、非 pytest 人工 Runner、deterministic local scripted driver；Runner 保持未执行。

### 5.2 S3 验收与测试

- `test_p12_mysql_connector.py`：DSN、fixed SHOW、标量校验、timeout、权限、cleanup、禁止 SQL/参数。
- `test_p12_migration.py`：upgrade/downgrade、PG/Redis 数据保留、MySQL unsafe downgrade 拒绝、非 SQLite operation spy、单一 head、revision 长度。
- `test_p12_preflight.py`/`test_p12_manual_runner.py`：缺条件失败、唯一 validator、origin mismatch、CI/pytest/non-TTY 拒绝、无 import side effect、fake orchestration。
- service CRUD/API 与前端 MySQL 入口回归。

## 6. 精确允许修改范围

以下 exact paths 是本 Workpack 上限；不需要的文件保持无 diff，禁止目录通配：

```text
backend/requirements.txt
backend/migrations/versions/20260904_15_p12_mysql_service_kind.py
backend/src/application/service_registration.py
backend/src/api/v1/dependencies.py
backend/src/api/v1/schemas.py
backend/src/domain/services.py
backend/src/infrastructure/persistence/models.py
backend/src/infrastructure/services/service_connector_factory.py
backend/src/infrastructure/services/postgres_connector.py
backend/src/infrastructure/services/redis_connector.py
backend/src/infrastructure/services/mysql_connector.py
backend/src/agents/db_agent.py
backend/src/tools/db_tools.py
backend/src/tools/service_health_tools.py
backend/src/core/agent.py
backend/src/core/bootstrap.py
backend/src/core/graph.py
backend/src/core/mock_runtime.py
backend/src/core/tool_gateway.py
backend/src/scenarios/db_diagnosis.py
backend/scripts/check_p12_real_readonly_preflight.py
backend/scripts/run_p12_real_readonly_acceptance.py
backend/tests/test_p12_service_binding.py
backend/tests/test_p12_postgres_end_to_end.py
backend/tests/test_p12_redis_investigation.py
backend/tests/test_p12_mysql_connector.py
backend/tests/test_p12_migration.py
backend/tests/test_p12_preflight.py
backend/tests/test_p12_manual_runner.py
backend/tests/test_service_registration_api.py
backend/tests/test_postgres_connector.py
backend/tests/test_redis_connector.py
backend/tests/test_db_tools_real.py
backend/tests/test_harness_p12_stage_gate.py
backend/tests/support/harness_p12_stage_gate.py
backend/tests/fixtures/harness/p12_stage_manifest.v1.json
frontend/src/features/services/ServiceCenterPage.tsx
frontend/src/features/workbench/WorkbenchPage.tsx
frontend/src/features/services/ServiceCenterPage.test.tsx
frontend/src/features/workbench/WorkbenchPage.test.tsx
frontend/src/test/handlers.ts
docs/design/service-center/P12-three-service-real-readonly-integration-design.md
docs/workpack/P12-three-service-real-readonly-integration/plan.md
docs/workpack/P12-three-service-real-readonly-integration/evidence.md
docs/workpack/P12-three-service-real-readonly-integration/review.md
docs/workpack/README.md
```

本轮不允许 archive Workpack、修改路线图/PRD 索引或标记 P12 完成，因为 AC14 真实验收尚未执行。

## 7. 禁止范围与停止条件

禁止修改 `backend/tests/conftest.py`、P10/P11 baseline/generator/profile/manifest/gate/归档 Workpack、历史迁移、OpenAPI generated file、公开 endpoint/field、Action/Approval/Executor、CI 外联配置或凭据模型。

出现以下任一项立即停止并报告：

- base/main 或 Alembic head 移动；
- 需要第二事实源、第二 migration、表/字段/回填、新公开 API 或 credential lease；
- MySQL 指标需要 PROCESS/SELECT/管理权限，Redis 需要 key/value/通用命令；
- 必须削弱外联 blocker、P10/P11 gate、断言或负向样例；
- 自动化必须访问真实服务/模型才能通过；
- 目标/凭据/原始异常或目标数据无法安全投影；
- 实际需要修改 §6 之外文件。

## 8. 回退

1. 暂停新 MySQL 注册和统一 health intent，新旧记录均不删除。
2. 仍保留 P12 backend/driver 时检查 MySQL 注册行；存在则停止回退，不撤代码/驱动/约束。
3. 只有零 MySQL row 时 downgrade CHECK；再撤前端入口、Agent/capability/factory、driver 和 binding 接线。
4. 不清理真实目标，不删除 Session/Run/Trace，不覆盖 P10/P11 历史资产。

## 9. 最终验证矩阵

```powershell
# backend/
..\.venv\Scripts\python.exe -m pytest tests/test_p12_service_binding.py tests/test_p12_postgres_end_to_end.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_p12_redis_investigation.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_p12_mysql_connector.py tests/test_p12_migration.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_p12_preflight.py tests/test_p12_manual_runner.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_service_registration_api.py tests/test_postgres_connector.py tests/test_redis_connector.py tests/test_db_tools_real.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_harness_contract_kernel.py tests/test_harness_runtime_adapter_contract.py tests/test_tool_gateway.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_harness_regression_baseline.py tests/test_harness_zero_behavior_gate.py tests/test_harness_p11_stage_gate.py tests/test_harness_p12_stage_gate.py -q
..\.venv\Scripts\python.exe -m pytest tests -q
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m mypy src

# frontend/
npm run typecheck
npm run test
npm run build

# repo root
git diff --check
git status --porcelain=v1 --untracked-files=all
```

另执行敏感字面量、exact-path、skip/xfail/xpass inventory 与 P12 mutation negative probes。

## 10. 交付状态约束

- 实现与离线验证、Review、commit/push/PR 可在本授权下完成。
- PR 关联 Issue #124，但不使用 closing keyword，不关闭 Issue，不合并 PR。
- AC14 真实 PostgreSQL/Redis/MySQL 人工验收全部保持待执行；Workpack 保持 active，P12 不标记完成。
