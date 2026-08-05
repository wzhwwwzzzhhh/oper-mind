# P4.3-service-context · AC 证据

状态：实现完成，待独立 readonly 审查回写最终结论。

| PRD 条目 | 代码/接口/测试证据 | 结果 | 备注 |
|---|---|---|---|
| AC1 | `backend/tests/test_db_tools_real.py`；后端全量测试 | PASS | mock 场景未改动 |
| AC2 | `ServiceCenterApplicationService.create_service_session`；`test_p4_service_center.py` | PASS | 已注册 PostgreSQL 实例可创建会话 |
| AC3 | `SessionData` 白名单与 `SessionApplicationService` 注册表校验；`test_p43_service_context.py` | PASS | `order-service` 和未知 id 被拒绝 |
| AC4 | `WelcomePanel` 服务选择；`WelcomePanel.test.tsx`；`create_session_mutation` | PASS | 首页选择服务后创建请求携带 service_id |
| AC5 | 既有 `POST /services/{service_id}/sessions` 与服务中心回归测试 | PASS | 服务中心入口保留 |
| AC6 | `DiagnosisRunData.service_id`、`RunApplicationService` 复制 Session 上下文、Run 资源 | PASS | 服务端从 Session 读取，客户端不能覆盖 |
| AC7 | `db_tools.py` 按实例 DSN 缺省返回“数据库未配置” | PASS | 无 DSN 不抛异常 |
| AC8 | `db_tools.py` 连接/超时异常统一返回“数据库不可用” | PASS | 不暴露底层异常 |
| AC9 | `CoordinatorDiagnosisExecutor` 将 service_id 传给新建 Coordinator；安全工具事件携带绑定服务 | PASS | 不再固定订单演示内容 |
| AC10 | 后端 `101 passed`；前端 `52 passed`、typecheck、build | PASS | 回归全绿 |
| AC11 | `ShowIndexTool(service_id=None)` 返回“数据库未选择目标服务” | PASS | 未绑定 DB 调查不连接固定生产库 |
| AC12 | `SessionWorkspace` 展示 Session 的真实 service_id/title；未绑定不展示 | PASS | 未使用假服务回填 |
