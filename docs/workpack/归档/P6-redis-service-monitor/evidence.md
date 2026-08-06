# P6-redis-service-monitor · AC 证据表

> 切片：S1 Redis 只读 Connector / S2 历史采样迁移 / S3 前端展示
> 基线：`main`（74a021d）→ `feat/redis-service-monitor`
> 状态：已实现，独立审查 PASS

## AC 证据

| AC | 验收标准摘要 | 证据 | 结果 |
|---|---|---|---|
| AC1 | `GET /services` 返回 `kind="redis"` 服务，id 正确 | `dependencies.py` 注册 redis-production；`backend/tests/test_api.py`（id/kind/not_configured 直断）；`backend/tests/test_redis_connector.py::test_definition包含静态服务信息且调查未启用` | ✅ |
| AC2 | 未设 env → `availability=not_configured` | `redis_connector.py::health_snapshot` 缺 DSN 分支；`test_redis_connector.py::test_无凭据返回未配置快照` / `test_未配置时指标为null不伪装` | ✅ |
| AC3 | 连接失败/超时 → `unavailable`，异常不外泄 | `redis_connector.py` try/except → `_unavailable`；`test_redis_connector.py::test_连接失败/超时/非法dsn` | ✅ |
| AC4 | server_metrics 含 memory_bytes/client_connections/slowlog_count，不可用/未配置 null | `redis_connector.py::_read_healthy`；`services.py` 专用字段；`test_redis_connector.py::test_健康快照填充专用标量且pg字段置空` | ✅ |
| AC5 | 只读客户端只执行 PING/INFO/CLIENT/SLOWLOG | `redis_connector.py::_read_healthy` 仅四命令；`test_redis_connector.py::test_只读客户端仅执行只读命令`（命令序列精确断言） | ✅ |
| AC6 | 快照/列表/详情/历史无 DSN/env 名/密码/sk- | `resources.py` 仅收敛字段；`test_redis_connector.py::test_快照不包含凭据或env名`；`test_api.py` 负断言 | ✅ |
| AC7 | MonitorSampler 采样 Redis → service_monitor_samples → history API | `dependencies.py` 采样器含 redis；`test_monitoring.py::test_采样器持久化redis专用标量而pg语义字段为null`；`test_monitor_history_api.py::test_redis样本经历史查询返回专用标量且pg字段为null` | ✅ |
| AC8 | 前端展示 Redis 实例（kind=redis 分支），未配置显示「未配置」 | `ServiceCenterPage.tsx`/`ServiceDetailPage.tsx` 既有分支复用；`App.test.tsx` 新增 3 用例 | ✅ |
| AC9 | 专用标量字段，PG 语义字段对 Redis null；页面不冒充 PG 延迟 | `schemas.py`/`monitoring.py` 专用字段；`ServiceDetailPage.tsx` is_redis 分支；`App.test.tsx` 断言无 P50/P95 | ✅ |
| AC10 | 回归：`test_p4_service_center.py`/`test_postgres_connector.py`/`test_monitoring.py`/`test_monitor_history_api.py`/`test_agent_gateway.py` | 全量 `pytest tests -q` = 132 passed；指定 5 文件 26 passed | ✅ |
| AC11 | 前端 typecheck/test/build | `npm run typecheck` 通过；`npm run test` 58 passed；`npm run build` 通过 | ✅ |

## 验证记录

- 后端全量：`..\.venv\Scripts\python.exe -m pytest tests -q` → **132 passed**
- 迁移：`test_monitoring.py::test_p6_redis标量迁移升降级` 在干净 SQLite 库 upgrade→downgrade→upgrade 通过（三列 + 非负约束）
- 前端类型：`npm run typecheck` → 通过
- 前端测试：`npm run test` → **58 passed（9 文件）**
- 前端构建：`npm run build` → 通过
- 契约生成：`npm run generate:api`（后端 8000 OpenAPI）→ `generated.ts` 含三专用字段（禁止手工编辑）
- 门禁：`git diff --check` 干净；敏感字面量扫描无 DSN/密码/`sk-`/env 名泄露

## 已知边界（与计划一致，记录备查）

1. `POST /services/redis-production/sessions` 直接调用会因 `sessions.service_id` CHECK 约束 500；前端已禁用「发起调查」并标注「未启用」，与 plan 决议一致，不放开约束。
2. ServiceCenterPage 调查入口改为读取服务首个 `supported_investigations.id`，移除对全部服务的硬编码 `orders_slow_query.v1` 预填（对 PG 服务不再误填订单服务文案；WorkbenchPage 仍只识别 `orders_slow_query.v1`）。
