# P5-controlled-action-real · AC 证据

## 验证命令

- 后端聚焦：`..\.venv\Scripts\python.exe -m pytest tests/test_p5_controlled_action.py tests/test_p2_diagnosis_adapter.py tests/test_p2_application_services.py tests/test_api.py tests/test_p4_service_center.py -q` → `24 passed, 1 warning`。
- 后端全量：`..\.venv\Scripts\python.exe -m pytest tests -q` → `115 passed, 1 warning`。
- 前端类型：`npm run typecheck` → 通过。
- P5 前端聚焦：`npm run test -- --run src/features/workbench/action-proposal-panel.test.tsx` → `3 passed`。
- 前端全量：`npm run test -- --run` → `9 files / 55 tests passed`。
- 前端构建：`npm run build` → 通过，仅有 Vite chunk size warning。
- P5 相关 `git diff --check` → 通过，仅有 LF/CRLF 转换警告。

## 范围与安全核对

- 固定 DDL 只存在于 `PostgresTargetActionExecutor`，不接受 API、模型或聊天文本参数。
- 执行目标固定为 `postgres-target`；production/staging 永远拒绝。
- 靶场 DSN 只读取环境变量，不进入提案、事件、结果、API 或前端。
- mock、无信号和未配置靶场均不产生可执行提案。
- 未新增公开 API、数据库迁移或表结构；未修改 mock 数据源。
- 仍建议后续补测：多 Engine/Connection 生命周期、取消/超时、invalid index、Verify 失败状态、前端 blocked/failed Verify 展示；当前均未连接真实外部资源。
