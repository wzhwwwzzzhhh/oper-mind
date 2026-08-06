# P6 Redis 服务接入与只读监控 Design

> 状态：已确认
> 更新：2026-08-06
> 关联：`docs/prd/service-center/P6-redis-service-monitor.md`（已确认）、`docs/design/service-center/P4.4服务中心接入与凭据Design.md`（凭据方案 A）、`docs/design/monitor/P5监控历史趋势与页面告警Design.md`（采样/趋势）、`docs/产品定义.md` §2.1/§4、`docs/开发规范.md` §3/§4/§5、`docs/路线图.md`。

## 1. 目标与范围

在既有 Service Connector 体系上把 Redis 作为第二类服务类型接入，复用 `ServiceConnector` 协议、`ServiceRegistry`、`load_service_dsn()` 环境变量命名空间解析与前端 `kind="redis"` 展示分支，并提供只读监控指标，纳入 P5 历史采样与趋势。纯只读，凭据零落库。

### 做什么
- 新增 `redis` 类型只读 Connector（`RedisServiceConnector`），实现 `ServiceConnector` 协议，返回 `ServiceDefinitionData`（kind="redis"）与 `ServiceSnapshotData`。
- 凭据：复用 `load_service_dsn(instance_id)`，`OPERMIND_SERVICE_<INSTANCE_ID>_DSN`（redis:// 或 redis://:password@host:port），零落库。
- 只读监控指标：`PING` 存活 + `INFO memory`→`used_memory` + `CLIENT LIST`→连接数 + `SLOWLOG LEN`→慢日志条数。
- 快照映射（方案 A，已确认）：Redis 指标写入**新增专用标量字段** `memory_bytes` / `client_connections` / `slowlog_count`；PG 语义字段（p50_ms/p95_ms/timeout_count）对 Redis 样本置 null。
- 历史采样：Redis 实例自动纳入 `MonitorSampler`，写入 `service_monitor_samples`，趋势页自动展示。
- 注册：`dependencies.py` 实例声明加 Redis 实例（如 `redis-production`）。
- 前端：复用既有 `kind="redis"` 展示分支；指标语义需区分处做最小展示标注。

### 明确不做
- 不做 MySQL Connector（本阶段只做 Redis，MySQL 仍为框架预留）。
- 不做任何 Redis 写操作（FLUSHDB / CONFIG / EVAL / SET / DML/DDL），纯只读。
- 不做键空间扫描、热点 key、键前缀统计或业务数据内容读取。
- 不做运行时动态增删 Redis 实例的 CRUD（配置/元数据驱动，重启生效）。
- 不做凭据编辑表单/UI 保存。
- 不新增历史采样或 API 之外的独立 Redis 专用接口/页面。
- 不改 mock 数据源、S1–S4 评测路径或既有 `GET /services`、`GET /services/{id}` 契约。

## 2. 设计决策

### 2.1 凭据与连接
- 复用 `load_service_dsn(instance_id)` 环境变量命名空间化（`OPERMIND_SERVICE_<INSTANCE_ID>_DSN`），与 PG 完全同构，零落库。
- 缺省 → `not_configured`；连接失败/超时 → `unavailable`；只读客户端，禁止写命令。
- 凭据/env 名绝无进日志、Trace、结果、前端、应用库。

### 2.2 快照指标映射（方案 A，已确认）
| Redis 命令 | 指标 | 落库字段 |
|---|---|---|
| `INFO memory` | `used_memory` | `memory_bytes`（新增） |
| `CLIENT LIST` | 连接数 | `client_connections`（新增） |
| `SLOWLOG LEN` | 慢日志条数 | `slowlog_count`（新增） |
| — | PG 延迟语义 | p50_ms / p95_ms / timeout_count 对 Redis 样本置 null |

- 不复用 PG 延迟字段承载 Redis 语义（诚实标注，不冒充 PostgreSQL 延迟）。
- `service_monitor_samples` 新增三个可空标量字段，需一次迁移（upgrade/downgrade）；既有 PG 样本不受影响。

### 2.3 历史采样与趋势
- Redis 实例注册进采样器遍历的服务集合；`MonitorSampler` 对 Redis 同样调用 `health_snapshot()`，写入 `service_monitor_samples`。
- 不可用/未配置保存状态、标量置 null；样本进入 `GET /services/{id}/monitor/history`，趋势页自动展示。
- 每实例独立降级，一个实例不可用不影响其他；连接超时 3s + 只读。

### 2.4 诚实降级
| 场景 | 状态 |
|---|---|
| env 未配置 | `not_configured` |
| 连接失败/超时 | `unavailable`（不暴露异常详情） |
| 命令失败 | 收敛为 `unavailable`，不抛异常 |

## 3. 文件改动面
- `backend/src/infrastructure/services/redis_connector.py`（或既有服务目录）：新增 `RedisServiceConnector`（只读客户端；建议 `redis-py`，测试注入假连接）。
- `backend/src/config.py` / `dependencies.py`：实例声明加 `redis-production`。
- `service_monitor_samples` 表：迁移新增 `memory_bytes` / `client_connections` / `slowlog_count`（可空）。
- 前端：复用 `kind="redis"` 分支，最小指标语义标注。
- 测试：`test_redis_connector.py`（新增）、`test_monitoring.py`/`test_monitor_history_api.py`/`test_p4_service_center.py` 回归。
- 明确无：新增公开接口、前端直连接口、凭据落库。

## 4. 切片与验证（指引，不写死）
- 建议拆 2 片：S1 Redis Connector 与只读指标（含快照映射、降级、凭据脱敏）；S2 采样/趋势接入与前端标注 + 迁移（含回归）。每片独立可验收。
- 门禁项：新服务类型（Redis Connector）、真实连接、数据库迁移 → 需 Design → Review → 用户确认（本 Design 即满足）。
- 验证命令由 dev-plan 的 plan.md 落定（pytest / 前端 typecheck/build / git diff --check）。

## 5. 风险、回滚与门禁
- 风险集中在凭据泄漏与写命令误用：已由「环境变量零落库 + 只读客户端白名单 + 脱敏兜底 + 测试锁定」防护。
- 回滚：迁移 upgrade/downgrade 双向；移除 Redis 实例声明与 Connector 注册即回退，既有 PG 链路不受影响。
- 门禁：Redis Connector、真实连接、迁移均需 arch-review PASS + 用户确认后放行 dev-plan。

## 6. 待用户确认的设计决策
1. Redis 客户端实现：`redis-py`（建议，成熟/只读易控/测试可注入假连接）还是内置 socket 直连？
2. 首版 Redis 实例声明数：`redis-production` 一个（建议），是否需 staging/target？
3. 指标字段语义映射方案 A（新增专用标量字段 + 样本表迁移）已确认，不再开放。
