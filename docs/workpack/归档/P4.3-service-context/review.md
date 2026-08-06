# P4.3-service-context · 独立审查

结论：PASS

审查范围：P4.3 PRD、P4.3 工作包、P4.3 两个提交及其测试；未纳入其他工作包文件。

审查结论：

- Session 合法服务由已装配静态 `ServiceRegistry` 校验，ORM CHECK 与迁移约束允许 `postgres-production` / `postgres-staging`，旧 `order-service` 被拒绝。
- Session 的 `service_id` 在 Run 受理时复制并由 Repository 持久化，执行器按持久化 Run 上下文构造隔离 Coordinator 与 DBAgent Tool。
- 未绑定服务的明确数据库调查在 Run 受理阶段以 `SERVICE_CONTEXT_REQUIRED` 拒绝；Tool 默认不绑定生产实例。
- mock、未配置、连接失败和超时路径保持诚实降级，不写入 DSN 或原始异常。
- 前端服务选择请求携带 `service_id`，会话页只展示真实服务上下文；未绑定会话不回填假服务。

剩余风险：DB 调查类型识别使用受控关键词守卫，后续若扩展自然语言路由应将 DB 能力判定下沉为显式路由结果；本 PRD 不扩大 Server/Log 服务上下文。

复审补充：

- DB 调查关键词守卫覆盖查询、表、连接池和 schema 等常见只读 DB 意图。
- Tool Gateway 默认超时为 3 秒。
- 只有 role=db 的工具事件携带 service_id，Server/Log 事件不伪装服务连接。
- OpenAPI 生成文件已从干净后端重新生成，不含 P5 monitor history 契约。
