# 服务中心域 PRD

> 服务接入/连接状态/监控入口/服务上下文。目标服务类型：PostgreSQL/MySQL/Redis。
> 现状：P4 已接入 PostgreSQL 只读服务，P4.4 支持多实例（production/staging）配置驱动接入。连接测试、凭据保存、权限模型、监控指标尚未定稿，须先设计。

| PRD | 主题 | 状态 |
|---|---|---|
| [P4.4-service-instances.md](P4.4-service-instances.md) | 服务中心多服务实例接入 | 完成 |
| [P6-redis-service-monitor.md](P6-redis-service-monitor.md) | Redis 服务接入与只读监控 | 完成 |
| [P8-service-registration.md](P8-service-registration.md) | 服务中心服务注册——动态接入、管理与连接测试 | 已确认 |
| [P8-monitor-threshold-config.md](P8-monitor-threshold-config.md) | 监控阈值与关注项配置——采样点异常判定规则可调 | 已确认 |
