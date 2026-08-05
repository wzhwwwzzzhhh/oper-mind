# P4.3-service-context · 工作包计划

## 基线与确认

- PRD：`docs/prd/session/P4.3-service-context.md`，状态：已确认。
- 基线分支：`main`，基线 commit：`a650de5`。
- 工作分支：`feat/p4.3-service-context`。
- 开工前工作区：干净；没有需要隔离的其他未提交改动。
- 已确认工程闸门：本工作包允许修改既有 Session/Run 持久化契约、数据库迁移、服务 Connector 注入链路、v1 API 与会话工作台服务选择；不新增服务类型、凭据配置或写操作。

## 范围

### 只做

- AC2/AC3/AC5：从静态 `ServiceRegistry` 派生 Session 合法 `service_id`，支持 `postgres-production` 与 `postgres-staging`，拒绝未注册服务。
- AC6/AC9：将 Session 服务上下文复制到 Run，贯通执行器与 DBAgent；真实模式按绑定服务解析 Connector/DSN，mock 模式保持既有数据路径。
- AC7/AC8：无 DSN、连接失败、超时返回稳定的“未配置/不可用”结果，不外泄异常或凭据。
- AC4/AC11：普通会话创建支持可选 `service_id`；工作台发起 DB 调查前要求服务选择，Server/Log 路径不改变。
- AC12：Run 资源和会话工作台展示真实绑定服务；未绑定时不展示假服务。
- AC1/AC10：补齐 mock 回归、服务中心、Connector、Tool Gateway 与相关 API/前端交互测试。
- 数据库迁移：调整 Session 约束并为 `diagnosis_runs.service_id` 增加可空字段、索引和可回滚迁移。

### 明确不做

- 不贯通 Server / Log Agent 的服务连接语义。
- 不做跨服务联合调查、服务中途切换、服务上下文编辑、权限管理或多租户。
- 不修改 `data/mock_db.py`、`data/scenarios.py` 或 S1-S4 评测路径。
- 不新增 DSN、凭据保存、服务类型、Connector 或动态服务定义。
- 不新增写操作、任意 SQL、Shell、DDL、DML 或前端直连用户服务。

## 已确认设计决策

- Session 的 `service_id` 只能由静态注册表中的 Connector id 产生；领域校验与数据库约束保持同一已注册服务集合的当前实现边界。
- Run 创建时从持久化 Session 读取 `service_id`，复制到 Run；客户端不能覆盖或伪造 Run 服务上下文。
- Executor 通过显式上下文对象将 `service_id` 传给 Coordinator/Tool 装配；ToolGateway 继续负责准入、参数校验、3s 限时、脱敏和审计摘要。
- DB Tools 使用按服务实例注入的只读 Connector/连接工厂；未绑定服务的 DB 调查在执行前以稳定错误拒绝。mock 场景不创建真实连接。
- 服务未配置映射为“数据库未配置”，连接失败或超时映射为“数据库不可用”；不把底层异常写入事件、结果或 API。
- Run 资源只增加非敏感 `service_id`；前端展示服务 id/title，不展示 DSN、host、port 或凭据。

## 切片拆分

- [x] S1：Session/Run 数据模型、白名单、迁移、API 契约与后端持久化测试。
- [x] S2：服务上下文注入执行器与 DBAgent，补齐 mock/未配置/不可用/绑定实例测试。
- [x] S3：会话工作台服务选择、上下文展示与前端交互测试。

## 改动面

- 后端：`backend/src/domain/records.py`、`backend/src/domain/services.py`、`backend/src/application/contracts.py`、`backend/src/application/services.py`、`backend/src/infrastructure/persistence/models.py`、`backend/src/infrastructure/persistence/repositories.py`、`backend/src/infrastructure/diagnosis/coordinator_executor.py`、`backend/src/tools/db_tools.py`、`backend/src/api/v1/schemas.py`、`backend/src/api/v1/resources.py`、`backend/src/api/v1/routes.py` 及显式服务上下文测试。
- 迁移：`backend/migrations/versions/` 新增 P4.3 migration 与迁移测试。
- 前端：`frontend/src/api/v1/`、`frontend/src/features/workbench/`、服务选择组件及对应 Vitest 测试。
- 工作包证据：本目录 `review.md`、`evidence.md`。

## 验证方法

- 后端：从 `backend/` 执行 `..\.venv\Scripts\python.exe -m pytest tests/test_p4_service_center.py tests/test_postgres_connector.py tests/test_agent_gateway.py tests/test_tool_gateway.py -q`，再执行全量 `..\.venv\Scripts\python.exe -m pytest tests -q`。
- 前端：从 `frontend/` 执行 `npm run typecheck`、`npm run test`、`npm run build`。
- 迁移：验证 `upgrade` / `downgrade`，并检查 Session/Run 约束和历史数据兼容。
- 门禁：`git diff --check`、暂存范围检查、敏感字面量检查。

## 提交计划

- `feat: P4.3 打通会话服务上下文数据链路`
- `feat: P4.3 按服务上下文执行数据库调查`
- `feat: P4.3 增加工作台服务选择与上下文展示`
