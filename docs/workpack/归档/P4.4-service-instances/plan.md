# P4.4-service-instances · 工作包计划

> PRD：`docs/prd/service-center/P4.4-service-instances.md`（已确认）
> Design：`docs/P4.4服务中心接入与凭据Design.md`（方案 A，已确认）
> 当前门禁：仅实现已确认的 PostgreSQL 多实例只读接入；不新增公开接口、不做数据库迁移。

## 范围

### 只做
- AC1、AC4、AC5：将服务中心注册从单个硬编码 Connector 改为 PostgreSQL 实例声明驱动；默认声明 `postgres-production` 与 `postgres-staging`，实例 ID 在注册表内保持唯一，各实例只读取自身命名空间化 DSN。
- AC2、AC3、AC8：扩展服务配置读取与 PostgreSQL Connector，使缺少 `OPERMIND_SERVICE_<INSTANCE_ID>_DSN` 返回 `not_configured`，连接失败/超时返回 `unavailable`，健康检查继续复用 `health_snapshot()` 的只读机制。
- AC6：保持服务定义、快照、API 资源和日志的安全边界，不返回 DSN、环境变量名、密码、原始异常或 `sk-` 内容。
- AC7：复用现有 `/services` 列表和详情接口与页面，展示后端返回的多个实例，并把未配置状态显示为“未配置”；不引入新的前端接口契约。
- AC9–AC10：补充多实例后端单元/API 测试与前端交互测试，并完成既有服务中心、PostgreSQL、Agent/Tool 网关和前端质量门禁回归。

### 明确不做
- 不新增 MySQL / Redis Connector 或其他真实服务类型。
- 不做运行时动态增删实例、配置管理 CRUD、凭据编辑表单或凭据保存。
- 不修改凭据存储方案；DSN 只从当前进程环境读取，不落库、不进入日志、Trace、结果或前端状态。
- 不做历史监控趋势、告警、轮询监控或新增连接测试接口。
- 不引入 DML、DDL、写操作、任意 SQL、权限模型、审批/执行能力或数据库迁移。
- 不修改与 P4.4 无关的既有用户或其他 Agent 改动。

## 切片拆分

- [x] S1：实例元数据/凭据命名空间装配与 Connector 定义扩展，覆盖 AC1–AC5、AC8，并补充后端单元/API 测试。
- [x] S2：服务中心列表/详情的多实例与“未配置”状态展示，覆盖 AC6–AC7，并补充前端交互测试；OpenAPI 结构保持不变。
- [x] S3：后端与前端回归、敏感信息扫描、`git diff --check`，覆盖 AC9–AC10。

## 改动面（文件级）

- `backend/src/config.py`：将服务 DSN 配置从单值扩展为按实例读取的环境变量命名空间；不改变敏感值落点。
- `backend/src/api/v1/dependencies.py`：按固定 PostgreSQL 实例声明构造 `ServiceRegistry`，移除单实例硬编码装配。
- `backend/src/infrastructure/services/postgres_connector.py`：支持实例 ID、标题和对应 DSN 的实例化，同时保持现有只读快照和错误映射。
- `backend/src/domain/services.py`：仅在注册表/服务协议需要时调整静态实例唯一性相关实现，不改变现有 API 数据结构。
- `backend/src/tools/db_tools.py`：如服务配置模型变更影响现有生产 PostgreSQL 工具，改为读取明确的 production 实例 DSN，保持 P4.2 行为。
- `backend/tests/test_p4_service_center.py`：扩展多实例、独立 env、重复 ID、未配置、连接失败和脱敏测试。
- `backend/tests/test_postgres_connector.py`：更新/补充实例化后的 Connector 回归测试。
- `backend/tests/test_api.py` 或对应服务 API 测试文件：补充 `/services` 多实例响应与安全字段断言（以现有测试布局为准）。
- `frontend/src/features/services/ServiceCenterPage.tsx`：复用现有服务列表，修正未配置文案与实例状态展示，不添加凭据相关 UI。
- `frontend/src/features/services/ServiceDetailPage.tsx`：确认并补齐多实例未配置详情态，保持现有接口调用和只读能力展示。
- `frontend/src/features/services/ServiceCenterPage.test.tsx`、`frontend/src/features/services/ServiceDetailPage.test.tsx` 或现有服务中心测试文件：覆盖多实例和未配置状态交互。
- `frontend/src/api/v1/generated.ts`：不应发生契约变更；若生成命令产生无关变化则不纳入本工作包。
- `docs/workpack/README.md`：登记本活跃工作包。
- 无数据库迁移、无新增公开 API、无凭据落库。

## 验证方法

- 后端聚焦：从 `backend/` 执行 `..\.venv\Scripts\python.exe -m pytest tests/test_p4_service_center.py tests/test_postgres_connector.py -q`，并运行新增/受影响 API 测试。
- 后端回归：从 `backend/` 执行 `..\.venv\Scripts\python.exe -m pytest tests -q`，重点确认 `test_agent_gateway.py`、`test_tool_gateway.py` 全绿。
- 前端：从 `frontend/` 执行 `npm run typecheck`、`npm run test`、`npm run build`；本 PRD 不要求 API 类型生成，除非接口契约意外变化。
- 门禁：执行 `git diff --check`，检查差异和测试输出不含 DSN、`OPERMIND_SERVICE_`、密码、API Key 或 `sk-` 内容；确认无迁移和未授权真实外部连接。

## 提交计划

- `feat: P4.4 支持 PostgreSQL 多服务实例注册`
- `feat: P4.4 展示服务实例未配置状态`
- `test: P4.4 补齐多实例服务中心回归验证`
