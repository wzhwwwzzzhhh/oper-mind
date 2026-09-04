# 服务中心域 PRD

> 服务接入/连接状态/监控入口/服务上下文。目标服务类型：PostgreSQL/MySQL/Redis。
> 现状：PostgreSQL 与 Redis 已支持动态注册、加密 DSN、连接测试和监控；PostgreSQL 的动态凭据尚未统一进入 Agent Tool，Redis 尚无 Agent 调查，MySQL 尚未接入。P12 PRD 已确认，拟通过 Issue #124 收口三类服务的最小真实只读调查链。

| PRD | 主题 | 状态 |
|---|---|---|
| [P4.4-service-instances.md](P4.4-service-instances.md) | 服务中心多服务实例接入 | 完成 |
| [P6-redis-service-monitor.md](P6-redis-service-monitor.md) | Redis 服务接入与只读监控 | 完成 |
| [P8-service-registration.md](P8-service-registration.md) | 服务中心服务注册——动态接入、管理与连接测试 | 完成 |
| [P8-monitor-threshold-config.md](P8-monitor-threshold-config.md) | 监控阈值与关注项配置——采样点异常判定规则可调 | 完成 |
| [P12-three-service-real-readonly-integration.md](P12-three-service-real-readonly-integration.md) | PostgreSQL、Redis 与 MySQL 真实只读接入 | 已确认（Issue #124） |
