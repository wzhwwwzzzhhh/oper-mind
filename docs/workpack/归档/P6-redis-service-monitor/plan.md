# P6-redis-service-monitor · 工作包计划

## 基线与确认

- PRD：`docs/prd/service-center/P6-redis-service-monitor.md`（状态：已确认）
- 前置 Design：
  - `docs/P4.4服务中心接入与凭据Design.md`（已确认：凭据方案 A = `OPERMIND_SERVICE_<INSTANCE_ID>_DSN` 环境变量命名空间化，Redis 框架预留、按同一模式复制）
  - `docs/P5监控历史趋势与页面告警Design.md`（已确认：MonitorSampler 采样 / service_monitor_samples 历史表 / history API）
- 指标字段语义映射 = 方案 A（PRD 已确认）：新增 `memory_bytes` / `client_connections` / `slowlog_count` 专用标量字段，PG 语义字段（p50_ms / p95_ms / timeout_count）对 Redis 置 null。
- 基线：`main`（commit `74a021d`）。

## 开放问题决议（来自 PRD 开放问题）

| 开放问题 | 决议 | 说明 |
|---|---|---|
| Redis 客户端实现 | 引入 `redis-py`，并加入 `backend/requirements.txt` | PRD 建议方向；成熟、只读命令易控、测试可注入假连接。将在 execute 阶段 pip 安装并钉版本（Python 3.11 兼容） |
| 实例声明数 | 首版注册 1 个：`redis-production` | 与 PRD「如 redis-production 一个」一致；不做 staging/target |
| Redis 调查能力 | `supported_investigations=()`（诚实未启用）+ 前端对无调查服务的「发起调查」诚实处理 | 内核无 Redis Agent/Tool，不伪造调查入口；因此**不放开** `sessions.service_id` 约束、不为此新增迁移（避免 500 与误导） |

## 范围

### 只做

- AC1：`redis-production` 实例注册进 `ServiceRegistry`；`GET /services` 返回 `kind="redis"` 服务，id 正确。
- AC2：实例未设置 `OPERMIND_SERVICE_REDIS_PRODUCTION_DSN` 时返回 `availability=not_configured`，不崩溃不伪造。
- AC3：Redis 连接失败/超时（模拟）返回 `availability=unavailable`，异常详情不外泄。
- AC4：Redis 快照 `server_metrics` 含专用标量 `memory_bytes` / `client_connections` / `slowlog_count`；不可用/未配置时标量为 null，不用 0 代替缺失。
- AC5：只读客户端仅执行 PING / INFO memory / CLIENT LIST / SLOWLOG LEN，不发任何写命令。
- AC6：列表/详情/快照/历史响应不含 DSN 明文、`OPERMIND_SERVICE_` env 名、密码或 `sk-` 内容。
- AC7：Redis 实例被 `MonitorSampler` 采样，样本写入 `service_monitor_samples`，`GET /services/{id}/monitor/history` 返回 Redis 历史样本。
- AC8：前端服务中心展示 Redis 实例（复用既有 `kind="redis"` 分支），未配置实例显示「未配置」。
- AC9：Redis 指标使用专用标量字段，PG 语义字段（p50_ms / p95_ms / timeout_count / slow_query_count）对 Redis 样本为 null；页面不把 Redis 内存/连接数展示为 PostgreSQL 延迟。
- AC10：`test_p4_service_center.py`、`test_postgres_connector.py`、`test_monitoring.py`、`test_monitor_history_api.py`、`test_agent_gateway.py` 及全量后端测试全绿。
- AC11：前端 `typecheck` / `test` / `build` 通过。

### 明确不做

- 不新增 MySQL Connector（本阶段只做 Redis，MySQL 仍为框架预留）。
- 不做 Redis 写操作、FLUSH、CONFIG、KEY 修改或任何 DML/DDL（纯只读）。
- 不做 Redis 键空间扫描、热点 key、键前缀统计或数据内容读取。
- 不做运行时动态增删 Redis 实例的 CRUD（配置/元数据驱动，重启生效）。
- 不做凭据编辑表单/UI 保存（凭据只走环境变量）。
- 不新增历史采样或 API 之外的独立 Redis 专用接口/页面；复用既有 history API 与页面。
- 不新增 Redis 调查 Agent/Tool；`supported_investigations=()` 诚实标注未启用。
- 不放开 `sessions.service_id` 约束、不为此新增迁移；Redis 不创建服务上下文会话（前端对无调查服务隐藏/禁用「发起调查」）。
- 不改 mock 数据源、S1–S4 评测路径或既有 `GET /services`、`GET /services/{id}`、`/services/{id}/monitor/history` 契约结构。

## 切片拆分

- [ ] S1：Redis 只读 Connector 与注册（后端）。覆盖 AC1–AC5、AC6（快照/列表/详情）、AC9（快照 server_metrics 部分）。新增 `RedisServiceConnector`、`ServiceServerMetricsData` 三个专用字段、redis 实例注册与资源映射；新增 `test_redis_connector.py`，更新受影响回归断言。
- [ ] S2：Redis 历史样本迁移与采样/查询（后端）。覆盖 AC7、AC6（历史）、AC9（样本部分）。`service_monitor_samples` 新增三列（迁移 upgrade/downgrade）、样本领域/ORM/仓储映射；扩展 `test_monitoring.py`、`test_monitor_history_api.py` 与迁移测试。
- [ ] S3：前端 Redis 展示（前端）。覆盖 AC8、AC9（页面部分）、AC11。详情页 Redis 指标卡片与趋势、服务中心诚实处理无调查服务；补充 MSW fixture 与前端交互测试。

## 改动面（文件级）

### S1 后端

- `backend/requirements.txt`：新增 redis-py 运行时依赖（execute 时安装并钉版本）。
- `backend/src/domain/services.py`：`ServiceServerMetricsData` 新增 `memory_bytes` / `client_connections` / `slowlog_count`（可空、非负），PG 语义字段不变。
- `backend/src/infrastructure/services/redis_connector.py`（新增）：`RedisServiceConnector` 实现 `ServiceConnector` 协议；`definition()` 返回 `kind="redis"` 静态身份、只读调查边界、`supported_investigations=()`、`session_title`；`health_snapshot()` 执行 PING/INFO memory/CLIENT LIST/SLOWLOG LEN（3s 超时、只读），DSN 解析用 `load_service_dsn("redis-production")`，失败/超时收敛 `unavailable`，缺省 `not_configured`，不打印/记录 DSN。支持注入假 client 供测试。
- `backend/src/api/v1/dependencies.py`：注册 `redis-production` 实例（读 `OPERMIND_SERVICE_REDIS_PRODUCTION_DSN`）。
- `backend/src/api/v1/schemas.py`：`ServiceServerMetricsResource` 新增三个可空字段。
- `backend/src/api/v1/resources.py`：`service_resource` 映射三个新字段。
- `backend/tests/test_redis_connector.py`（新增）：未配置 / 连接失败 / 超时 / 健康 / 只读命令断言 / 脱敏 / definition / 注册表唯一 / env 命名空间互不串扰。
- `backend/tests/test_api.py`：更新服务列表断言加入 `redis-production`。
- `backend/tests/test_p4_service_center.py`：更新默认装配 Connector 断言加入 `redis-production`。

### S2 后端

- `backend/migrations/versions/20260807_06_p6_redis_monitor_metrics.py`（新增）：`service_monitor_samples` 新增可空列 `memory_bytes` / `client_connections` / `slowlog_count` 及非负 CheckConstraint；downgrade 删除列；不改既有列与既有 PG 样本。
- `backend/src/domain/monitoring.py`：`ServiceMonitorSampleData` 新增三字段；`from_snapshot` 复制三个专用标量（PG 连接自然为 null）。
- `backend/src/infrastructure/persistence/models.py`：`ServiceMonitorSampleRecord` 新增三列与 CheckConstraint。
- `backend/src/infrastructure/persistence/monitor_repositories.py`：`add` / `_to_data` 映射三字段。
- `backend/src/api/v1/schemas.py`：`MonitorSampleResource` 新增三个可空字段。
- `backend/tests/test_monitoring.py`：Redis 样本写入与 PG 语义字段 null 断言。
- `backend/tests/test_monitor_history_api.py`：Redis 样本经历史接口返回与字段语义断言。
- 迁移测试：`backend/tests/test_p2_schema.py` 等既有迁移测试回归（upgrade/downgrade 不受影响，必要时补充新列断言）。

### S3 前端

- `frontend/src/features/services/ServiceDetailPage.tsx`：对 `kind="redis"` 展示 memory/connections/slowlog 专用指标卡片与历史趋势（不展示 p95 延迟冒充 PG）；异常判定对 Redis 使用 slowlog_count；缺失保持诚实空态。
- `frontend/src/features/services/ServiceCenterPage.tsx`：对无 `supported_investigations` 的服务诚实处理「发起调查」（隐藏或禁用），避免误导性 intent；Redis logo/标签分支已存在，保持复用。
- `frontend/src/api/v1/client.ts`：`MonitorSampleResource` 接口补充三个可空字段。
- `frontend/src/api/v1/generated.ts`：由 `npm run generate:api` 重新生成（后端在 8000 提供 OpenAPI 时）；若不可达则确认 `unknown` 契约无需改动，禁止手工编辑。
- `frontend/src/test/handlers.ts`：新增 `redis-production` 服务与 Redis 历史样本 MSW fixture。
- `frontend/src/features/services/ServiceCenterPage.test.tsx` 或 `ServiceDetailPage.test.tsx`（新增）：Redis 实例展示、未配置状态、专用指标语义、无调查服务诚实处理。

### 工作包文档

- `docs/workpack/P6-redis-service-monitor/plan.md`（本文件）
- `docs/workpack/P6-redis-service-monitor/review.md`：dev-execute 后由独立只读审查回写。
- `docs/workpack/P6-redis-service-monitor/evidence.md`：dev-execute 逐条回写 AC 证据。
- `docs/workpack/README.md`：登记活跃工作包。

## 验证方法

- 后端聚焦：从 `backend/` 执行 `..\.venv\Scripts\python.exe -m pytest tests/test_redis_connector.py tests/test_monitoring.py tests/test_monitor_history_api.py tests/test_p4_service_center.py tests/test_api.py -q`。
- 后端回归：从 `backend/` 执行 `..\.venv\Scripts\python.exe -m pytest tests -q`。
- 迁移：干净临时库执行 `..\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head` 与 `downgrade`，验证新列、约束与既有样本不受影响；既有迁移测试回归。
- 前端类型：从 `frontend/` 执行 `npm run typecheck`。
- 前端测试：从 `frontend/` 执行 `npm run test`。
- 前端构建：从 `frontend/` 执行 `npm run build`。
- 生成契约：从 `frontend/` 执行 `npm run generate:api`（后端可达时），禁止手工编辑 `generated.ts`。
- 门禁：仅检查本工作包文件范围的 `git diff --check` 与敏感字面量（DSN / 密码 / `sk-` / `OPERMIND_SERVICE_`）；确认 mock 路径与既有服务接口回归通过。

## 提交计划

- S1：`feat: 接入 Redis 只读服务 Connector`
- S2：`feat: Redis 历史采样与样本表迁移`
- S3：`feat: 服务中心展示 Redis 实例与指标`

提交前只暂存本工作包实际修改的文件，不使用 `git add .`。

## 分支与 Worktree（Phase 2，dev-execute 硬闸门）

- Worktree 路径：`D:/market-handsome/oper-mind-worktrees/redis-service-monitor`
- 分支名：`feat/redis-service-monitor`
- 基线：`main`（74a021d）
- 备注：worktree 为全新 checkout，需在 worktree 内重建后端依赖（含新增 redis-py）与前端 `npm install`；主仓库工作区只做分支与 worktree 管理。
