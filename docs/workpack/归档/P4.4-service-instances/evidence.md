# P4.4-service-instances · AC 证据

## 验证结果

- 后端聚焦：`..\.venv\Scripts\python.exe -m pytest tests/test_db_tools_real.py tests/test_p4_service_center.py tests/test_postgres_connector.py tests/test_api.py -q` → `34 passed`。
- 后端全量：`..\.venv\Scripts\python.exe -m pytest tests -q` → `101 passed`，1 条既有 Starlette/httpx 弃用警告。
- 前端类型：`npm run typecheck` → 通过。
- 前端测试：`npm run test` → `8 files / 51 tests passed`。
- 前端构建：`npm run build` → 通过；仅有 Vite bundle 大小提示。
- API 类型：`npm run generate:api` → 通过；P4.4 未新增接口契约。
- 差异门禁：P4.4 相关文件 `git diff --check` → 通过。工作区无关的 `docs/产品定义.md` 尾随空格未修改。
- 独立只读审查：PASS；未发现 P0/P1。

## AC 证据表

| AC | 证据 | 结果 |
|---|---|---|
| AC1 | `dependencies.py` 注册 production/staging；`test_api.py` 验证 `/api/v1/services` 返回两个实例 ID。 | PASS |
| AC2 | `load_service_dsn()` 缺省返回 `None`；Connector 与服务中心测试验证 `not_configured`。 | PASS |
| AC3 | Connector 将连接异常/超时收敛为 `unavailable`；PostgreSQL 与 DB Tool 测试覆盖。 | PASS |
| AC4 | 实例 DSN 由各自 `OPERMIND_SERVICE_<INSTANCE_ID>_DSN` 读取；装配测试验证 production/staging 不串扰；DB Tool 使用 production 命名空间。 | PASS |
| AC5 | `ServiceRegistry` 保留重复 ID 拒绝；单元测试覆盖。 | PASS |
| AC6 | 服务 API 测试断言响应不含 DSN、环境变量名和密码；快照测试不含连接串、SQL 原文。 | PASS |
| AC7 | 服务中心列表展示多个实例及“未配置”；前端 App 交互测试覆盖。 | PASS |
| AC8 | 列表/详情继续调用 `health_snapshot()`，无新增连接测试接口。 | PASS |
| AC9 | 后端全量 `101 passed`，包含服务中心、PostgreSQL、Agent/Tool 网关回归。 | PASS |
| AC10 | 前端 typecheck、test、build 全部通过。 | PASS |

## 范围说明

工作区包含其他已存在的 P4.3 模型设置和 API 类型改动；本工作包未回退或覆盖这些改动。P4.4 自身未新增公开接口、数据库迁移、凭据落库或 MySQL/Redis Connector。
