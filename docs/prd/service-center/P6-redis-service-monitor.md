---
title: Redis 服务接入与只读监控
status: 完成
domain: service-center
phase: P6
updated: 2026-08-06
---

# Redis 服务接入与只读监控 · PRD

## 背景

服务中心目前只接入 PostgreSQL（P4.4 多实例 + P5 历史趋势），Redis 作为第二类服务类型仍是**框架预留**：
- `ServiceConnector` 协议（`definition()` + `health_snapshot()`）、`ServiceRegistry`、`load_service_dsn()` 环境变量命名空间解析器均已通用，不区分服务类型；
- 前端 `ServiceCenterPage` / `ServiceDetailPage` 已含 `kind="redis"` 的展示分支与 logo 样式；
- 但**没有 `redis` 类型的 Connector**，也没有 Redis 只读连接、监控或指标。

现状缺口：运维接入 Redis 实例（缓存/会话存储/消息队列）后，服务中心无法查看其连接状态、内存占用、连接数与慢日志，也无法纳入历史趋势——Redis 健康只能靠人工 `redis-cli` 或第三方监控，未进产品主链。

本 PRD 按 P4.4 Design 已确认的「MySQL/Redis 框架预留，后续按同一模式复制」方向，把 Redis 作为第二类服务类型接入，并纳入 P5 历史监控。

关联：
- `docs/design/service-center/P4.4服务中心接入与凭据Design.md`（凭据方案 A = 环境变量命名空间化、框架预留 Redis/MySQL、能力驱动）
- `docs/design/monitor/P5监控历史趋势与页面告警Design.md`（采样器/样本表/历史 API/前端趋势，已确认）
- `docs/prd/monitor/P5-monitor-trends.md`（P5 监控 PRD）
- `docs/开发规范.md` §3（服务与 Connector）、§4（凭据）、§5（监控诚实性）

## 已确认决策

| 决策点 | 结论 | 说明 |
|---|---|---|
| Redis 凭据方案 | 环境变量命名空间化（复用） | 复用 `load_service_dsn()`，`OPERMIND_SERVICE_<INSTANCE_ID>_DSN`，零落库，与 PG 同构 |
| Redis 只读监控指标 | 内存/连接/慢日志 | `PING` + `INFO memory`(used_memory) + `CLIENT LIST`(连接数) + `SLOWLOG LEN`(条数) |
| Redis 监控模式 | 复用 P5 历史监控 | 自动纳入 `MonitorSampler` 采样，写入 `service_monitor_samples`，趋势页自动展示 |
| 指标字段语义映射（方案 A） | 新增专用标量字段 | `memory_bytes` / `client_connections` / `slowlog_count` + 样本表迁移，PG 语义字段对 Redis 置 null |

## 目标

1. Redis 作为新服务类型接入服务中心，复用既有 `ServiceConnector` 协议、`ServiceRegistry`、`load_service_dsn()` 与前端展示。
2. Redis 只读快照提供连接状态 + 内存 / 连接数 / 慢日志收敛标量，纳入 P5 历史采样与趋势。
3. 凭据只走环境变量命名空间化，零落库，与 PG 完全同构；未配置实例诚实降级。

## 用户故事

作为运维工程师，我需要把 Redis 实例接入服务中心，查看它的连接状态、内存占用、连接数与慢日志，并像 PostgreSQL 一样看历史趋势——以便在缓存服务变慢或内存告急时，能从产品主链发现并调查，而不是人工 `redis-cli` 排查。

## 范围

### 做什么

- 新增 `redis` 类型的只读 Connector（`RedisServiceConnector`），实现 `ServiceConnector` 协议，返回 `ServiceDefinitionData`（kind="redis"）与 `ServiceSnapshotData`。
- 凭据：复用 `load_service_dsn(instance_id)` 环境变量命名空间化（`OPERMIND_SERVICE_<INSTANCE_ID>_DSN`），零落库。
- 只读监控指标：`PING` 存活探测、`INFO memory` → `used_memory`、`CLIENT LIST` → 连接数、`SLOWLOG LEN` → 慢日志计数。
- 快照映射：Redis 指标写入**新增专用标量字段**（`memory_bytes` / `client_connections` / `slowlog_count`），不复用 PG 延迟字段承载错误语义。
- 历史采样：Redis 实例自动纳入 P5 `MonitorSampler` 定时采样，Redis 专用标量写入 `service_monitor_samples`，历史趋势页面自动展示。
- 注册：在 `dependencies.py` 的实例声明中加入 Redis 实例（如 `redis-production`）。
- 前端：复用既有 `kind="redis"` 展示分支；若需要区分 Redis 指标语义，做最小展示标注。

### 不做什么（明确排除）

- 不新增 MySQL Connector（本阶段只做 Redis，MySQL 仍为框架预留）。
- 不做 Redis 写操作、flush、config set、KEY 修改或任何 DML/DDL（纯只读）。
- 不做 Redis 键空间扫描、热点 key、键前缀统计或数据内容读取（只读监控不读业务数据）。
- 不做运行时动态增删 Redis 实例的 CRUD（配置/元数据驱动，重启生效）。
- 不做凭据编辑表单/UI 保存（凭据只走环境变量）。
- 不新增历史采样或 API 之外的独立 Redis 专用接口/页面。
- 不改 mock 数据源、S1–S4 评测路径或既有 `GET /services`、`GET /services/{id}` 契约。

## 功能需求

### 1. Redis 服务类型接入

- **输入**：在实例声明中加入 `redis` 类型实例（如 `redis-production`），凭据来自对应 `OPERMIND_SERVICE_REDIS_PRODUCTION_DSN` env。
- **行为**：`RedisServiceConnector` 实现 `ServiceConnector` 协议；`definition()` 返回 kind="redis" 的静态服务身份与只读调查边界；实例 id 唯一性由 `ServiceRegistry` 校验。
- **输出**：Redis 实例注册进服务中心，`GET /services` 返回包含 Redis 实例的服务列表。

### 2. Redis 只读连接与凭据

- **输入**：`OPERMIND_SERVICE_<INSTANCE_ID>_DSN` 环境变量（redis:// 或 redis://:password@host:port）。
- **行为**：Connector 构造时解析对应实例的 DSN env；缺省 → `not_configured`；连接失败/超时 → `unavailable`；只读客户端，不做任何写命令。凭据绝不进入日志/Trace/结果/前端/应用库。
- **输出**：Redis 实例按各自 env 配置的只读连接；未配置实例诚实降级。

### 3. Redis 只读监控指标

- **输入**：对 Redis 实例发起只读健康检查。
- **行为**：依次执行 `PING`（存活）、`INFO memory`（`used_memory` 字节）、`CLIENT LIST`（连接数）、`SLOWLOG LEN`（慢日志条数）；任何命令失败/超时收敛为 `unavailable`，不抛异常。
- **输出**：`ServiceSnapshotData`（availability / server_metrics / database.signal），Redis 指标写入**新增专用标量字段**（方案 A，已确认）：
  - `used_memory` → `memory_bytes`
  - CLIENT LIST 连接数 → `client_connections`
  - 慢日志条数 → `slowlog_count`
  - PG 语义字段（p50_ms / p95_ms / timeout_count）对 Redis 实例置 null，不承载错误语义

### 4. 历史采样与趋势（复用 P5）

- **输入**：Redis 实例注册进采样器遍历的服务集合。
- **行为**：`MonitorSampler` 对 Redis 实例同样调用 `health_snapshot()`，写入 `service_monitor_samples`（含 availability 与 Redis 专用标量）；不可用/未配置保存状态、标量置 null。
- **输出**：Redis 实例的历史样本进入 `GET /api/v1/services/{id}/monitor/history`，服务详情页趋势自动展示。

### 5. 前端 Redis 展示

- **输入**：服务中心列表/详情页挂载。
- **行为**：复用既有 `kind="redis"` 展示分支（logo、类型标签已存在）；详情页展示 Redis 快照状态；历史趋势自动展示 Redis 指标（若字段语义需区分，做最小标注）。
- **输出**：Redis 实例在服务中心与历史趋势中可见，诚实标注指标语义与来源。

## 非功能需求

- **安全**：凭据只走环境变量；脱敏硬约束；无凭据/DSN/env 名进日志、Trace、结果、前端、应用库。
- **只读**：Redis 客户端只允许只读命令；禁止 FLUSHDB、CONFIG、EVAL、写 KEY 等。
- **可靠**：每实例独立降级，一个实例不可用不影响其他实例；连接超时（3s）+ 只读。
- **诚实**：未配置显示 not_configured；不可用显示 unavailable；Redis 指标使用专用标量字段（memory_bytes / client_connections / slowlog_count），不冒充 PostgreSQL 延迟语义。
- **性能**：快照复用 P5 限时机制，不阻塞 API 事件循环。

## 数据与接口影响

- 数据：`service_monitor_samples` 表**新增 Redis 专用标量字段**（`memory_bytes` / `client_connections` / `slowlog_count`，可空），需要一次数据库迁移（upgrade/downgrade）；既有 PG 样本不受影响，PG 语义字段对 Redis 样本置 null。Redis 实例 id 作为 service_id 采样。
- 接口：`GET /services`、`GET /services/{id}`、`/services/{id}/monitor/history` 结构不变；返回值随 Redis 实例增多。无新增公开接口。

## 验收标准

- [ ] AC1: 当声明 `redis-production` 实例且设置对应 `OPERMIND_SERVICE_REDIS_PRODUCTION_DSN` env 时，`GET /services` 应返回该 Redis 服务，`kind="redis"`，id 正确。
- [ ] AC2: 当 Redis 实例未设置对应 env 时，该实例应返回 `availability=not_configured`，不崩溃、不伪造。
- [ ] AC3: 当 Redis 连接失败/超时（模拟连接异常）时，该实例应返回 `availability=unavailable`，不把异常详情外泄。
- [ ] AC4: Redis 快照的 `server_metrics` 应含专用标量（memory_bytes / client_connections / slowlog_count）；不可用/未配置时标量为 null，不用 0 代替缺失。
- [ ] AC5: Redis 只读客户端不得发出任何写命令（FLUSHDB/CONFIG/EVAL/SET 等）；只允许只读命令。
- [ ] AC6: 快照/列表/详情/历史响应中不得出现 DSN 明文、`OPERMIND_SERVICE_` env 名、密码或 `sk-` 内容。
- [ ] AC7: Redis 实例应被 `MonitorSampler` 定时采样，样本进入 `service_monitor_samples`，`GET /services/{id}/monitor/history` 返回 Redis 历史样本。
- [ ] AC8: 前端服务中心应展示 Redis 实例（复用既有 `kind="redis"` 分支），状态正确；未配置实例显示"未配置"。
- [ ] AC9: Redis 指标使用专用标量字段，页面不把 Redis 内存/连接数展示为 PostgreSQL 延迟；PG 语义字段（p50_ms / p95_ms / timeout_count）对 Redis 样本应为 null。
- [ ] AC10: 回归 —— `test_p4_service_center.py`、`test_postgres_connector.py`、`test_monitoring.py`、`test_monitor_history_api.py`、`test_agent_gateway.py` 全绿。
- [ ] AC11: 前端 `typecheck` / `test` / `build` 通过（若涉及前端改动）。

## 边界与约束

- 安全边界：纯只读，无写路径；凭据只走环境变量；无凭据/env 名进日志、Trace、结果、前端、应用库。
- 降级策略：未配置 → not_configured；连接失败/超时 → unavailable；各实例独立，互不拖累。
- 兼容性：mock 模式行为不变；既有接口契约不变；MySQL 仍为框架预留，不实现 Connector。
- Redis 指标映射：方案 A（已确认）——新增 `memory_bytes` / `client_connections` / `slowlog_count` 专用标量字段，PG 语义字段（p50_ms / p95_ms / timeout_count）对 Redis 样本置 null，不做值承载。

## 完成定义（DoD）

- [ ] 全部 AC（AC1–AC11）通过
- [ ] 相关回归测试全绿
- [ ] `git status` 只出现本 PRD 允许的文件
- [ ] 未新增凭据落库/编辑/保存能力，未改后端配置机制
- [ ] `service_monitor_samples` 迁移 upgrade/downgrade 通过，既有 PG 样本不受影响
- [ ] 接口与页面均不含 DSN / env 名 / 凭据明文
- [ ] Redis 指标使用专用标量字段，不冒充数据库延迟

## 开放问题

1. **Redis 客户端实现**：引入 `redis-py` 库，还是用内置 socket 直连实现只读 PING/INFO/CLIENT/SLOWLOG？——决定依赖面与测试 mock 方式。建议用 `redis-py`（成熟、只读客户端易控、测试可注入假连接）。
2. **Redis 实例声明数**：首版注册几个 Redis 实例（如 `redis-production` 一个）？是否需 staging/target？——决定装配范围。
3. ~~指标字段语义映射~~ **已确认方案 A**（新增 Redis 专用标量字段 `memory_bytes` / `client_connections` / `slowlog_count` + 样本表迁移），不再作为开放问题。
