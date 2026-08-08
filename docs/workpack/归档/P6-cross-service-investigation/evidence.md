# P6-cross-service-investigation · AC 证据表

> 关联 PRD：`docs/prd/session/P6-cross-service-investigation.md`（issue #27）。独立审查见 `review.md`。

## 验证命令

- 后端聚焦：`backend/.venv/Scripts/python.exe -m pytest tests/test_p6_cross_service.py tests/test_p43_service_context.py tests/test_p4_service_center.py tests/test_postgres_connector.py tests/test_agent_gateway.py tests/test_p2_schema.py tests/test_p2_api_v1.py -q` → `41 passed`。
- 后端全量：`backend/.venv/Scripts/python.exe -m pytest tests -q` → `267 passed, 2 skipped`。
- 迁移：`alembic upgrade head` → `downgrade -1` → `upgrade head` 通过；`test_迁移在存在关联数据时拒绝降级` 验证数据守卫。
- 前端：`npm run generate:api`、`npm run typecheck`、`npm run test`、`npm run build` → 类型生成成功、`72 passed`、构建成功。
- 门禁：`git diff --check` 通过；本工作包代码与生成类型未包含凭据、DSN、原始日志或 CoT 展示路径。

## 逐条 AC 证据

- [x] AC1 欢迎页多选服务：`WelcomePanel.tsx` checkbox 与 `WelcomePanel.test.tsx`。
- [x] AC2 多服务关联、未注册/重复拒绝：`test_p6_cross_service.py`，会话创建契约/API 测试。
- [x] AC3 每服务单独 Run：`send-intent.test.ts` 多 Run 顺序提交，`test_p6_cross_service.py` 显式服务绑定。
- [x] AC4 对话按服务展示：`conversation-turns.ts`、`WorkbenchPage.tsx` 服务结果区及投影测试。
- [x] AC5 未选择服务保持空上下文：创建 intent 的空服务集合和既有无上下文 Run 回归。
- [x] AC6 单服务兼容：`test_p43_service_context.py`、前端 `App.test.tsx` 回归。
- [x] AC7 单服务失败独立降级：`submit_unaccepted_session_runs` 测试和工作台逐服务错误提示。
- [x] AC8 会话展示服务集合：`SessionWorkspace`、`App.test.tsx`。
- [x] AC9 服务中心多选发起：`ServiceCenterPage.tsx`、`App.test.tsx` 多服务创建断言。
- [x] AC10 迁移正反向与既有会话兜底：迁移命令和 `test_p6_cross_service.py`。
- [x] AC11 后端回归：聚焦 41 项与完整 267 项通过。
- [x] AC12 前端类型检查、测试、构建：`typecheck`、72 项 Vitest、`build` 通过。
- [x] AC13 安全展示：Run 仍使用既有脱敏边界；新增服务集合只含服务 ID/title/type。
- [x] AC14 mock S1-S4 回归：后端全量 267 项通过。
