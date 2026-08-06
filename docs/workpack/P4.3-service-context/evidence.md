# P4.3-service-context · AC 证据

状态：实现完成，两次独立 readonly 审查修复后 PASS。

| PRD 条目 | 代码/接口/测试证据 | 结果 | 备注 |
|---|---|---|---|
| AC1 | `backend/tests/test_db_tools_real.py`；后端全量 `115 passed` | PASS | mock 场景未改动 |
| AC2 | `ServiceCenterApplicationService.create_service_session`；`test_p4_service_center.py` | PASS | 已注册 PostgreSQL 实例可创建会话 |
| AC3 | `SessionApplicationService` 按静态注册表校验；`test_p43_service_context.py:22` | PASS | 未注册 id（含 `order-service`）被拒绝 |
| AC4 | `WelcomePanel` 服务选择回填 `service_id`；`WelcomePanel.test.tsx`、`App.test.tsx` | PASS | 首页选择服务后创建请求携带 service_id |
| AC5 | 既有 `POST /services/{service_id}/sessions` 与 `App.test.tsx` 服务中心回归 | PASS | 服务中心入口保留，fixture 已改真实服务 |
| AC6 | `DiagnosisRunData.service_id` 持久化；Run 资源返回 service_id；`test_p2_application_services.py` | PASS | 服务端从 Session 读取并复制，客户端不能覆盖 |
| AC7 | `db_tools.py` 无 DSN 返回“数据库未配置”；`test_db_tools_real.py` | PASS | 无 DSN 不抛异常 |
| AC8 | `db_tools.py` 连接/超时统一返回“数据库不可用” | PASS | 不暴露底层异常 |
| AC9 | 执行器把 service_id 传入 Coordinator；DB 工具事件携带绑定服务；`test_p43_service_context.py` 断言 Trace 无 `order-service` | PASS | 不再固定订单演示内容 |
| AC10 | 后端全量 `115 passed`；前端 `56 passed`、`typecheck`、`build`；`git diff --check` 干净 | PASS | 相关回归全绿 |
| AC11 | `SERVICE_CONTEXT_REQUIRED` 受理守卫；`ShowIndexTool(service_id=None)` 返回“数据库未选择目标服务”；日志/服务器语义不误判 | PASS | 未绑定 DB 调查不创建 Run；日志交叉用例已补 |
| AC12 | `SessionWorkspace` 展示服务器返回的真实 service_id/title；未绑定不展示；`App.test.tsx` 集成断言 | PASS | fixture 使用 `postgres-production` 真实服务 |
