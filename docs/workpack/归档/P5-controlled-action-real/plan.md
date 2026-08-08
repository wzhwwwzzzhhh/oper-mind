# P5-controlled-action-real · 工作包计划

## 基线与确认

- PRD：`docs/prd/approval/P5-controlled-action-real.md`
- Design：`docs/design/approval/P5受控动作联合索引Design.md`
- Design 状态：已获用户确认，2026-08-05
- 当前工作区已有 P4.3 服务上下文相关改动；本工作包不回退、不覆盖、不纳入这些既有改动。

## 范围

### 只做

- AC1、AC2、AC3：让 target 模式的诊断结构化结果在满足固定缺索引/seq scan 信号时生成一条绑定 Run 的固定联合索引重建提案；mock、无信号或证据不完整时不生成。
- AC4：固定提案、action digest、事件和 API/Trace 只使用脱敏结构化摘要，不暴露 SQL 原文、DSN、凭据或内部请求 ID。
- AC5、AC6、AC7、AC8、AC9：实现 `postgres-target` 专用白名单执行器，执行前服务端复核固定模板和目标前置条件，使用独立 autocommit 连接执行固定 `CREATE INDEX CONCURRENTLY`，随后用新的只读连接 Verify，并将失败安全收敛为 `blocked`/`failed`。
- AC10：复用既有 action API 和 `ActionProposalPanel`，补齐提案存在时的审批、二次确认执行、Verify 和“受控靶场 target 模式”展示交互测试。
- AC11：保持 action 状态机、P4.2 只读工具、服务接口和 mock S1–S4 路径回归通过。

### 明确不做

- 不连接或修改 `postgres-production`、`postgres-staging` 或任何真实用户生产/预发布资源。
- 不新增通用 SQL、Shell、DDL、DML、网络执行器，不接受客户端或模型提供 SQL、DSN、目标对象或动作参数。
- 不做自动批准、自动执行、执行回滚、重试写入、多用户/RBAC/多人审批。
- 不做 MySQL/Redis 受控动作、告警通知、历史监控、凭据编辑 UI 或运行时服务注册。
- 不修改 `data/mock_db.py`、`data/scenarios.py` 和 S1–S4 评测数据源。
- 不新增公开 API、数据库表或迁移；不改变既有 action API 契约。

## 切片拆分

- [x] S1：诊断缺索引结构化信号与固定提案生成，覆盖 AC1–AC4；补充 Result/Action Application 层单元测试与 API 脱敏测试。
- [x] S2：`postgres-target` 白名单执行器、前置复核、固定 DDL、独立 Verify 和安全失败映射，覆盖 AC5–AC9；使用确定性 mock 连接测试，不访问真实外部资源。
- [x] S3：前端审批闭环展示与全量回归，覆盖 AC10–AC11；补充前端交互测试，运行后端相关测试、前端 typecheck/test/build 和敏感信息门禁。

## 改动面（文件级）

### 后端拟修改/新增

- `backend/src/domain/records.py`：补充缺索引信号所需的结构化结果字段或严格模型，保持跨层类型约束。
- `backend/src/application/contracts.py`：扩展诊断完成结果端口，使缺索引信号以结构化事实传递，不从报告文本反推。
- `backend/src/application/action_services.py`：实现固定提案模板、target/mock 资格判断和服务端 digest 校验接入。
- `backend/src/application/action_execution.py`：必要时补充执行器安全失败/结果契约，不扩大通用执行能力。
- `backend/src/infrastructure/actions/postgres_target_executor.py`：新增仅面向 `postgres-target` 的固定索引执行与独立 Verify 实现。
- `backend/src/infrastructure/services/postgres_target.py` 或等价静态装配模块：提供受控靶场目标和 DSN 命名空间解析；具体路径以现有依赖注入结构为准。
- `backend/src/api/v1/dependencies.py`、`backend/src/core/bootstrap.py`：仅装配受控靶场执行器，明确 mock 不装配有效写执行器。
- `backend/src/config.py`：读取 `OPERMIND_SERVICE_POSTGRES_TARGET_DSN`，不返回 DSN。
- `backend/src/infrastructure/persistence/*`：仅在既有字段无法承载结构化 target 时评估；默认不修改表结构、不新增迁移。

### 后端测试拟修改/新增

- `backend/tests/test_action_services.py`：固定提案、无信号/mock 空态、digest 与状态机测试。
- `backend/tests/test_postgres_target_executor.py`：目标隔离、前置条件、autocommit 固定 DDL、连接释放、Verify 和失败映射测试。
- `backend/tests/test_api.py` 或现有 action API 测试文件：提案/事件/执行结果脱敏与契约回归。
- `backend/tests/test_p4_service_center.py`、`backend/tests/test_postgres_connector.py`：仅在装配回归需要时补充，保持既有服务只读语义。

### 前端拟修改/新增

- `frontend/src/features/actions/ActionProposalPanel.tsx`：仅在现有面板缺少 target 模式边界或状态展示时做最小修改。
- `frontend/src/features/workbench/WorkbenchPage.tsx`、`frontend/src/api/v1/queries.ts`：仅在提案关联/刷新闭环需要时接入既有 API，不新增后端接口。
- `frontend/src/features/actions/ActionProposalPanel.test.tsx` 或现有 `frontend/src/app/App.test.tsx`：审批、二次确认、Verify 和受控靶场文案交互测试。

### 工作包文档

- `docs/workpack/P5-controlled-action-real/plan.md`
- `docs/workpack/P5-controlled-action-real/review.md`：执行完成后由独立只读审查回写。
- `docs/workpack/P5-controlled-action-real/evidence.md`：执行完成后逐条回写 AC 证据。
- `docs/workpack/README.md`：登记活跃工作包。

## 验证方法

- 后端聚焦：从 `backend/` 执行 `..\.venv\Scripts\python.exe -m pytest tests/test_action_services.py tests/test_postgres_target_executor.py tests/test_api.py -q`；文件不存在时按现有测试布局调整为实际 action 测试文件。
- 后端回归：从 `backend/` 执行 `..\.venv\Scripts\python.exe -m pytest tests -q`。
- 前端类型：从 `frontend/` 执行 `npm run typecheck`。
- 前端测试：从 `frontend/` 执行 `npm run test`。
- 前端构建：从 `frontend/` 执行 `npm run build`。
- 生成契约：如后端 OpenAPI 未变化，不重新生成；若现有接口 schema 受影响，从 `frontend/` 执行 `npm run generate:api`，禁止手工编辑 generated 文件。
- 安全门禁：检查本工作包 diff 中无 DSN、密码、`sk-`、SQL 原文或原始异常；执行 `git diff --check`。
- 真实资源门禁：所有执行器测试使用确定性 mock，不连接任何生产、预发布或用户服务。

## 提交计划

- S1：`feat: 生成受控联合索引提案`
- S2：`feat: 实现靶场联合索引受控执行`
- S3：`test: 完善受控动作闭环回归`

提交前只暂存本工作包实际修改的文件，不使用 `git add .`；不提交当前工作区已有的 P4.3 改动。
