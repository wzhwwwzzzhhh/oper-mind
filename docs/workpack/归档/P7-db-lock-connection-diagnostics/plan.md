# P7-db-lock-connection-diagnostics · 工作包计划

> PRD：`docs/prd/session/P7-db-lock-connection-diagnostics.md`（已确认，issue #44）
> Design：`docs/design/session/P7DB锁与连接池诊断Design.md`（已确认，7 条技术约束，执行时直接遵守）
> 基线：`backend/src/tools/db_tools.py`、`backend/src/agents/db_agent.py`、`backend/tests/test_db_tools_real.py`
> 专用分支：`feat/P7-db-lock-connection-diagnostics`
> worktree：`D:/market-handsome/oper-mind-worktrees/P7-db-lock-connection-diagnostics`

## 范围

### 只做

- S1（AC1–AC3、AC5–AC7）：新增 `CheckLockStatusTool` / `CheckConnectionPoolTool` 两个只读工具，
  沿用 `get_active_scenario()` 双模式判定；真实分支走 `_real_connection(service_id)`（`load_service_dsn` +
  `create_read_only_postgres_engine` + `SET TRANSACTION READ ONLY`），无 DSN →「数据库未配置，无法查询」、
  连接失败/超时 →「数据库不可用」均不抛异常；锁诊断识别阻塞链、连接池统计与健康档位。
- S2（AC4、AC8、AC9）：mock 分支在工具模块内定义确定性映射（不改 `data/scenarios.py`/`data/mock_db.py`）；
  工具定义 `audit_summary()` 收敛摘要；`DBAgent` 注册两个新工具；补齐单元/API 测试与全量回归。

### 明确不做

- 不杀锁、不 `terminate`、不修改连接（写能力属受控动作）。
- 不做容量诊断、索引效用分析、MySQL/Redis 同型诊断、`EXPLAIN ANALYZE`。
- 不新增公开 REST API、不新增配置项、不新增凭据、不新增数据库迁移。
- 不改 `data/mock_db.py`、`data/scenarios.py`、S1–S4 评测路径。
- 不动前端（接口契约与 Trace 展示字段不变）。
- 不暴露 `pg_stat_activity` 明细行（用户名、客户端 IP、原始 SQL、application_name）到 Trace/事件/结果/前端。

## 切片拆分（2 个独立可验收切片）

- [ ] S1: 两个只读工具（真实分支 + 三态降级 + 只读锁定）→ 覆盖 AC1、AC2、AC3、AC5、AC6、AC7
- [ ] S2: mock 分支确定性 + audit_summary 审计摘要 + DBAgent 注册 + 全量回归 → 覆盖 AC4、AC8、AC9

## 改动面（文件级）

- `backend/src/tools/db_tools.py`（修改）：新增 `LockWaitStatus`/`LockWaitChain`/`ConnectionPoolStatus` Pydantic 模型；
  新增 `CheckLockStatusTool`、`CheckConnectionPoolTool`（mock 分支 + 真实查询分支 + `audit_summary()`）。
- `backend/src/agents/db_agent.py`（修改）：注册两个新工具。
- `backend/src/scenarios/db_diagnosis.py`（修改，可选）：SYSTEM_PROMPT/TOOL_CALLING_EXAMPLE 追加工具引导。
- `backend/tests/test_db_lock_pool_tools.py`（新增）：mock 分支锁定、真实分支假连接/假引擎、降级、只读、脱敏、
  audit_summary。
- 无数据库迁移、无接口契约变更、无前端改动。

## 验证方法

- 后端（worktree 内 `backend/`）：`..\.venv\Scripts\python.exe -m pytest tests/test_db_lock_pool_tools.py -q`
- 回归子集：`..\.venv\Scripts\python.exe -m pytest tests/test_db_tools_real.py tests/test_tool_gateway.py tests/test_agent_gateway.py tests/test_p2b_tool_trace.py -q`
- 全量：`..\.venv\Scripts\python.exe -m pytest tests -q`
- 门禁：`git diff --check`；确认凭据/DSN/原始 SQL 未入日志、Trace、响应、截图

## 提交计划

- 按切片提交（每切片一个）：
  - `feat: P7 锁与连接池只读诊断工具真实分支与降级（AC1-AC3,AC5-AC7）`
  - `feat: P7 锁与连接池诊断 mock 分支与审计摘要及注册（AC4,AC8,AC9）`

## 状态

- [x] Design 已确认（arch-review PASS + 用户确认 6 项决策）
- [x] 专用 worktree 已建（分支 `feat/P7-db-lock-connection-diagnostics`，基线 `main`）
- [ ] 计划待用户确认后进入 dev-execute
