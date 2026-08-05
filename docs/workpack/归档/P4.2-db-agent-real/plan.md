# P4.2-db-agent-real · 工作包计划

> PRD：`docs/prd/session/P4.2-db-agent-real.md`（已确认）
> Design：`docs/P4.2DBAgent真库Design.md`（已确认，6 条技术约束，执行时直接遵守）
> 基线：`test_postgres_connector.py` / `test_p4_service_center.py` / `test_agent_gateway.py` / `test_tool_gateway.py` 24 passed 全绿
> 专用分支：`feat/p4.2-db-agent-real`（从当前状态创建，保留并隔离其他工作包改动）

## 范围

### 只做
- S1（AC1–AC3、AC9）：`ExplainTool`/`ShowIndexTool`/`ShowCreateTableTool` 增加「真实模式」分支，模式判定复用 `get_active_scenario()`（None ⇒ 真实模式）；懒加载 P4 只读引擎，无 DSN → 「数据库未配置」、连接失败/超时 → 「数据库不可用」，均不抛异常；输出经 `desensitize()` 兜底
- S2（AC4）：`explain_sql` 真实分支：仅接受 `SELECT` 开头、执行只读 `EXPLAIN`、格式化有限字段、不回显完整 SQL 原文
- S3（AC5–AC8）：`show_index`/`show_create_table` 真实分支：表名标识符校验、查只读系统目录（参数化）、表不存在/无索引降级文案
- 为上述分支补齐单元测试（mock 引擎 + 确定性假行）

### 明确不做
- 不接 MySQL / Redis
- 不做写操作 / DDL / DML / `EXPLAIN ANALYZE`
- 不新增配置项、不新增凭据、不做表名白名单映射
- 不改 `data/mock_db.py`、`data/scenarios.py`、S1–S4 评测路径
- 不动前端（接口契约与 Trace 展示不变）
- 不改动 `.codex-tasks/`、`docs/`、`AGENTS.md`、`CLAUDE.md`、原型 HTML 等与本工作包无关的现有改动

## 切片拆分

- [x] S1: 三工具双模式判定 + 只读引擎懒加载 + 三态降级 + desensitize（AC1/2/3/9）
- [x] S2: explain_sql 真实 EXPLAIN 分支（AC4）
- [x] S3: show_index / show_create_table 系统目录分支（AC5/6/7/8）
- [x] 回归：AC10 四组目标测试与后端全量测试全绿；`git diff --check` 干净

## 改动面（文件级）

- `backend/src/tools/db_tools.py`（三个 Tool 增加真实分支，mock 分支原样保留）
- `backend/src/infrastructure/persistence/`（如 P4 只读引擎工厂已在此层，仅引用，不新建单例）
- `backend/tests/test_db_tools_real.py`（新增，mock 引擎 + 确定性假行，覆盖 AC1–AC9）
- 无数据库迁移、无接口契约变更

## 隔离提交清单

- P4.2 专属并完整暂存：`backend/src/tools/db_tools.py`、`backend/src/infrastructure/services/postgres_engine.py`、`backend/tests/test_db_tools_real.py`、本工作包 `plan.md`/`evidence.md`/`review.md`
- 混合文件仅暂存 P4.2 代码块：`backend/src/infrastructure/services/postgres_connector.py`、`backend/tests/test_postgres_connector.py`
- 明确不暂存：P4.3 的实例化服务配置、`load_service_dsn`、API/前端/模型设置、`.codex-tasks` 及其他 Agent 改动

## 验证方法

- 后端（backend/）：`..\.venv\Scripts\python.exe -m pytest tests -q`（全量）
- 回归子集：`..\.venv\Scripts\python.exe -m pytest tests/test_postgres_connector.py tests/test_p4_service_center.py tests/test_agent_gateway.py tests/test_tool_gateway.py -q`
- 门禁：`git diff --check`；确认凭据/DSN 未入日志、Trace、响应、截图

## 提交计划

- 按切片提交（每切片一个）：
  - `feat: P4.2 DBAgent 工具接入真实模式骨架与降级（AC1-AC3,AC9）`
  - `feat: P4.2 explain_sql 真实 EXPLAIN（AC4）`
  - `feat: P4.2 show_index/show_create_table 系统目录查询（AC5-AC8）`

## 试跑状态

- [x] plan.md 已交用户确认并进入 dev-execute
- [x] 用户确认后进入 dev-execute
