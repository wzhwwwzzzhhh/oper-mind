# P5 监控历史趋势与页面告警 Design

> 状态：已确认
> 更新：2026-08-05
> 关联：`docs/prd/monitor/P5-monitor-trends.md`、`docs/产品定义.md` §5.5/§6、`docs/开发规范.md` §5。

## 1. 目标与范围

本阶段在现有静态 `ServiceRegistry` 和只读 `health_snapshot()` 能力之上增加历史采样、趋势查询和服务详情页内异常采样点展示。
采样数据属于应用元数据，不复用目标 PostgreSQL 连接；目标服务访问仍只能通过已注册 Connector。

### 做什么

- 后端单进程定时采样已注册 Connector，默认每 5 分钟执行一次。
- 将快照中的脱敏标量和状态写入 `service_monitor_samples` 历史表。
- 默认查询和保留窗口为最近 24 小时；采样间隔与保留窗口通过环境变量配置。
- 新增按 `service_id` 和时间窗口查询历史样本的只读 v1 API。
- 服务详情页展示 p50/p95、慢查询、超时和可用性历史，并标注异常采样点。
- 明确展示“定时采样 · 每 5 分钟 · 保留最近 24 小时 · 历史记录”。

### 明确不做

- 不做邮件、Slack、Webhook、企业微信、短信或其他外部通知。
- 不做秒级轮询、SSE/WebSocket 推送、跨进程协调、采样器高可用或补采样。
- 不做跨服务对比、报表、导出、历史搜索或可配置告警规则。
- 不新增服务类型、Connector、凭据管理、连接测试或动态服务注册。
- 不写 SQL、对象名、原始日志、DSN、API Key 或其他凭据到样本、接口、日志或前端状态。
- 不修改 `data/mock_db.py`、`data/scenarios.py` 或 S1–S4 评测路径。

## 2. 设计决策

### 2.1 采样调度

- 在 FastAPI 应用 lifespan 中启动一个单进程后台任务；关闭应用时取消任务并等待退出。
- 首次采样默认在应用启动后执行一次，之后按固定间隔执行。首次采样失败不阻止应用启动。
- 每轮按 `ServiceRegistry.list_connectors()` 顺序逐个采样，单个 Connector 的异常转换为 `unavailable` 样本并继续其他服务。
- 现有 Connector 为同步接口。采样器使用 `asyncio.to_thread()` 执行 `health_snapshot()`，避免阻塞 API 事件循环；每个服务使用 3 秒超时。
- 采样器和 API 查询共用应用数据库的 `SessionFactory`，每次写入使用独立短事务。
- 同一轮采样不并发访问同一服务；采样轮次通过任务内部串行控制，避免重复采样。

### 2.2 配置

新增配置字段，环境变量优先于 YAML：

| 配置 | 默认值 | 约束 |
|---|---:|---|
| `OPERMIND_MONITOR_SAMPLE_INTERVAL_SECONDS` | `300` | 30–86400 秒 |
| `OPERMIND_MONITOR_RETENTION_HOURS` | `24` | 1–168 小时 |
| `OPERMIND_MONITOR_QUERY_MAX_HOURS` | `24` | 1–168 小时，不能超过保留窗口 |

配置值非法时应用启动失败并返回明确配置错误；不接受负值、零值或任意字符串执行。

### 2.3 样本领域模型

跨层使用显式 Pydantic 模型，不使用隐式字典协议。

`ServiceMonitorSampleData` 字段：

| 字段 | 类型 | 语义 |
|---|---|---|
| `id` | UUID | 样本标识 |
| `service_id` | string | 静态注册服务键 |
| `observed_at` | UTC datetime | 快照观测时间 |
| `availability` | enum | `healthy/unhealthy/unavailable/not_configured` |
| `p50_ms` / `p95_ms` | number or null | 脱敏延迟标量 |
| `slow_query_count` / `timeout_count` | integer or null | 脱敏计数 |
| `performance_signal` | enum | 高层性能信号 |
| `source_status` | enum | `available/unavailable/not_configured` |

`not_configured` 和 `unavailable` 样本仍保存状态，但所有无法诚实提供的指标保存为 null。不得使用 0 代替缺失值。

### 2.4 持久化与清理

新增 ORM 表 `service_monitor_samples`：

- `id` UUID 主键；`service_id`、`observed_at`、状态和收敛标量列均为显式字段。
- `service_id` 不建立到动态服务表的外键，因为当前服务来源是静态注册表。
- 建立 `(service_id, observed_at)` 索引，查询按服务和时间升序读取。
- 建立 `observed_at` 索引，供保留清理使用。
- 数据库 CheckConstraint 限制枚举值、计数非负和延迟非负。
- 每轮采样结束后执行一次轻量清理：删除 `observed_at < now - retention_hours` 的样本。清理失败记录安全日志，不影响本轮样本和 API。
- 迁移必须提供 upgrade/downgrade；不修改既有表和既有服务接口字段。

为避免 SQLite 与 PostgreSQL 时间行为差异，应用内部统一使用 UTC aware datetime；数据库列沿用现有 `DateTime(timezone=True)` 约定，查询边界由后端规范化。

### 2.5 历史查询 API

新增接口：

```text
GET /api/v1/services/{service_id}/monitor/history
```

查询参数：

- `from`: 可选 ISO 8601 UTC 起始时间。
- `to`: 可选 ISO 8601 UTC 结束时间。
- `hours`: 可选整数窗口，默认 `24`，与 `from/to` 互斥。

约束：

- `service_id` 必须存在于静态注册表；不存在返回既有安全的服务不存在错误，不探测外部资源。
- 未配置服务返回 HTTP 200，`status=not_configured`、`samples=[]`。
- 已注册但没有历史样本返回 HTTP 200，`status=not_sampled`、`samples=[]`。
- 仅有不可用样本时返回 HTTP 200，`status=unavailable`，样本保留状态但不返回异常详情。
- 有样本时返回 `status=available` 和按 `observed_at` 升序排列的样本序列。
- 时间窗口不得超过 `query_max_hours`；非法时间范围返回 422。
- 返回只包含上述样本领域模型字段，不复用当前快照响应，不返回 SQL、对象名、原始异常、DSN 或凭据。

响应契约：

```json
{
  "service_id": "postgres-production",
  "status": "available | not_sampled | not_configured | unavailable",
  "source": "scheduled_sampling",
  "sample_interval_seconds": 300,
  "retention_hours": 24,
  "from": "2026-08-05T00:00:00Z",
  "to": "2026-08-05T12:00:00Z",
  "samples": []
}
```

### 2.6 前端趋势与异常点

- `ServiceDetailPage` 使用 React Query 请求历史接口，查询窗口固定为后端默认最近 24 小时。
- 成功且有样本时，运行趋势卡片展示三组可扫描的历史视图：延迟（p50/p95）、慢查询/超时计数、可用性状态。
- 为避免引入不必要的图表依赖，首版使用现有 CSS/HTML 绘制稳定尺寸的时间序列轨道和点位；每个点保留观测时间、值和异常标记。
- 异常判定为纯确定性前端展示逻辑：
  - `slow_query_count > 0`；
  - `timeout_count > 0`；
  - 当前点与前一个点的 `availability` 不同。
- 异常点显示“采样点异常”，并在卡片摘要列出最近最多 5 个异常点及触发指标。
- 不显示“告警中”“正在推送”“实时监控”等表述。
- 无样本、未配置和不可用分别展示诚实状态；无有效标量时不绘制数值趋势线。
- 历史接口加载失败展示安全错误状态，不回退静态示例数据；当前快照和活动区块行为保持不变。

## 3. 文件改动面

### 后端

- `backend/src/config.py`：新增采样/保留/查询窗口配置加载与校验。
- `backend/src/domain/monitoring.py`：新增样本、查询结果和状态的显式领域模型。
- `backend/src/infrastructure/persistence/models.py`：新增历史样本 ORM 模型。
- `backend/src/infrastructure/persistence/monitor_repositories.py`：新增样本写入、窗口查询和清理仓储。
- `backend/src/application/monitoring.py`：新增采样用例和历史查询用例。
- `backend/src/infrastructure/monitoring/sampler.py`：新增单进程后台采样任务。
- `backend/src/api/v1/schemas.py`：新增历史趋势响应 schema。
- `backend/src/api/v1/routes.py`：新增历史查询路由。
- `backend/src/api/v1/dependencies.py` 与 `backend/src/app.py`：装配采样器和历史查询服务，管理 lifespan 生命周期。
- `backend/migrations/versions/<timestamp>_p5_monitor_samples.py`：新增表、索引、约束及 downgrade。
- `backend/tests/test_monitoring.py`、`backend/tests/test_monitor_history_api.py`、迁移测试：覆盖采样、降级、脱敏、窗口和迁移。

### 前端

- `frontend/src/api/v1/client.ts`、`queries.ts`、`generated.ts`：新增历史接口契约和 query。
- `frontend/src/features/services/ServiceDetailPage.tsx`：接入历史数据、趋势视图和异常摘要。
- `frontend/src/features/services/ServiceDetailPage.test.tsx` 或现有服务页面测试：覆盖成功、空态、异常点、接口失败和诚实标注。
- `frontend/src/test/handlers.ts`：新增确定性 MSW 历史样本 fixture。

## 4. 切片与验证

### S1：历史样本模型、迁移、采样器

- 覆盖 PRD AC1–AC3、AC8、AC9。
- 验证已配置、未配置、失败、超时和单服务失败隔离；验证样本仅有脱敏标量。
- 执行迁移 upgrade/downgrade 和后端监控单元测试。

### S2：历史查询 API

- 覆盖 PRD AC1–AC4。
- 验证服务键边界、默认窗口、最大窗口、时间排序、空态状态和响应脱敏。
- 执行 API 测试及既有服务中心回归测试。

### S3：服务详情趋势与页面内异常高亮

- 覆盖 PRD AC5–AC7。
- 验证历史成功态、无数据态、未配置/不可用态、异常点判定、最多 5 条摘要和无实时表述。
- 执行前端 `typecheck`、`test`、`build`。

## 5. 风险、回滚与门禁

- 采样器异常不得传播到 FastAPI 请求；后台任务捕获已知运行异常并使用中文安全摘要记录。
- 不在应用启动时自动运行 Alembic；部署/测试显式执行 `alembic upgrade head`。
- 若后台采样器引入启动或资源风险，可通过配置禁用采样任务，但历史查询仍返回 `not_sampled`，不伪造数据。
- 回滚顺序为停止采样任务、执行迁移 downgrade、移除 API/前端入口；不删除既有服务快照数据或会话数据。
- Review 必须确认调度生命周期、数据库表契约、状态语义、异常脱敏和 mock 回归后，才能进入 workpack 实现。

## 6. 待用户确认的设计决策

1. 是否确认本设计采用“应用单进程 lifespan 任务 + `asyncio.to_thread` 隔离同步快照”的调度方式。
2. 是否确认历史样本表使用应用元数据库，并按 `(service_id, observed_at)` 查询，不复用目标 PostgreSQL。
3. 是否确认 API 的未配置/未采样/不可用状态均返回 HTTP 200 空序列或状态样本，而不是把业务降级当作 5xx。
4. 是否确认前端首版使用 CSS/HTML 时间序列轨道，不引入图表库。
5. 是否确认本设计 Review 通过后，将 P5 PRD 状态从“草稿”更新为“已确认”，再创建 `docs/workpack/P5-monitor-trends/plan.md` 进入实现。
