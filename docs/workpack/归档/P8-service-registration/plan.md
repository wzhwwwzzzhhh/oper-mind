# P8-service-registration · 工作包计划

> 关联 PRD：`docs/prd/service-center/P8-service-registration.md`（已确认，issue #53）
> 关联 Design：`docs/design/service-center/P8服务注册Design.md`（已确认，§6 决策 1–9 用户已拍板）

## 范围

### 只做
- AC1：`POST /services` 注册服务（kind/instance_id/title/dsn），返回安全视图（id/type/title/has_dsn/掩码尾号），响应不含 DSN 明文。
- AC2：实例 ID 与既有硬编码实例冲突时返回明确错误（409），不创建。
- AC3：主密钥未配置时注册新服务拒绝创建（409），不落任何明文 DSN。
- AC4：已注册服务出现在 `GET /services`，与其他服务同列，连接状态正确。
- AC5：`PUT /services/{id}` 更新标题/DSN，更新后连接状态重置为未验证。
- AC6：`DELETE /services/{id}` 移除返回 204，重复删除仍 204；历史会话/监控/活动留痕保留（AC10）。
- AC7：`POST /services/{id}/test-connection` 可连通→healthy、不可达→unavailable + 安全原因、未配置→not_configured，不暴露 DSN/异常。
- AC8：应用库、日志、Trace、事件、结果、截图、接口响应中不得出现 DSN 明文、密码或 `sk-` 内容。
- AC9：未验证/未配置的服务在前端如实标注，不伪造连接成功。
- AC11：回归——既有硬编码实例（env DSN）仍可读取；`test_p4_service_center.py`、`test_postgres_connector.py`、`test_redis_service_monitor.py` 相关全绿；前端 `typecheck`/`test`/`build` 通过。
- Design 决策 6：`MonitorSampler` 改持 registry 引用每轮读取。
- Design 决策 8：迁移放宽 `session_service_id_valid` / `session_services_service_id_valid` CHECK 约束。

### 明确不做
- 不做 MySQL 真实 Connector（PRD 排除）。
- 不做身份/权限/多用户。
- 不做运行时可编辑的监控阈值/关注项。
- 不做运行时可编辑的能力声明（Design 决策 7，PUT 仅改标题/DSN）。
- 不改变既有硬编码实例读取方式（`OPERMIND_SERVICE_<ID>_DSN` env 兼容保留）。
- 不把 DSN 明文/完整 DSN/密码/`sk-` 写入日志、Trace、事件、结果、截图或接口响应。
- 不要求 `Idempotency-Key`（Design 决策 9，instance_id 唯一作自然幂等）。

## 切片拆分

- [ ] S1: **后端注册表持久化 + CRUD + 约束放宽** —— `service_registry` 表迁移（含 CHECK 放宽）、仓储、加密落库、`ServiceRegistry` 动态化、CRUD 接口、`GET /services` 兼容、`_safe_event_data` 白名单改读 registry。覆盖 AC1–AC6、AC8、AC10 主体。
- [ ] S2: **显式连接测试 + 前端接入** —— `test-connection` 接口（复用 `health_snapshot()` 只读探活、3s 限时、脱敏分类码）；前端添加/编辑/删除/测试连接 + 诚实标注。覆盖 AC7、AC9。
- [ ] S3: **装配贯通 + 回归** —— `registry_loader` 注入、`MonitorSampler` 动态读 registry、启动加载已落库服务、回归全绿。覆盖 AC11。

## 改动面（文件级）

### 后端（backend/）
- **修改** `src/domain/services.py` —— `ServiceRegistry` 增 `register`/`remove`（可变 + 快照并发契约，更新不变式注释）；`ServiceDefinitionData` 扩展 `has_dsn`/`dsn_masked_tail`（S1）。
- **修改** `src/infrastructure/persistence/models.py` —— 新增 `ServiceRegistryRecord`；移除 `sessions.service_id`、`session_services.service_id` 的 CheckConstraint（S1）。
- **新增** `src/infrastructure/persistence/service_registry_repository.py` —— 读写 `service_registry`（S1）。
- **新增** `backend/migrations/versions/` revision —— 建 `service_registry` 表（upgrade/downgrade）+ 放宽两个 CHECK 约束（S1，**数据库迁移**）。
- **新增** `src/application/service_registration.py` —— 注册/改/删/测试连接应用服务（含 DSN 加密/掩码、实例 ID 唯一与格式校验、诚实降级）（S1+S2）。
- **修改** `src/api/v1/routes.py` + `schemas.py` + `resources.py` —— 新增 4 接口 + 服务安全视图含 `has_dsn`/`dsn_masked_tail`（S1+S2，**公开 API**）。
- **修改** `src/api/v1/dependencies.py` —— `registry_loader` 注入参数（默认 None）+ `build_v1_services()` 传真实 loader + `MonitorSampler` 改持 registry 引用（S3）。
- **修改** `src/infrastructure/monitoring/sampler.py` —— 每轮采样读 `registry.list_connectors()`（S3）。
- **修改** `src/application/services.py` —— `_safe_event_data` service_id 白名单改读 registry `service_ids()`（S1）。
- **修改** `src/infrastructure/secrets.py` —— 增加中性别名 `encrypt_dsn`/`decrypt_dsn` + 独立 key-info 派生（S1）。
- **修改** `config/config.example.yaml` —— 文档化 `OPERMIND_SECRET_KEY` 同时用于模型 API Key 与服务 DSN 加密（S1）。
- **新增** `backend/tests/test_service_registration_api.py`；**修改** `backend/tests/test_p4_service_center.py`（registry_loader 注入）、`backend/tests/test_monitoring.py`（sampler 构造签名）、`backend/tests/test_api.py` 等回归（S1/S3）。

### 前端（frontend/）
- **修改** `src/features/services/ServiceCenterPage.tsx` —— 添加服务表单、编辑/移除/测试连接按钮、未验证/未配置诚实标注（S2）。
- **修改** `src/api/v1/queries.ts`（S2）；`generated.ts` 由 `npm run generate:api` 生成（S2）。
- **新增/修改** `src/features/services/ServiceCenterPage.test.tsx`（MSW mock）（S2）。

### 无功能改动部分
- 会话工作台、多 Agent 内核、审批闭环、知识库、Trace 展示（本工作包不含凭据展示路径）。

## 验证方法

- 后端：`..\.venv\Scripts\python.exe -m pytest tests/test_service_registration_api.py tests/test_p4_service_center.py tests/test_postgres_connector.py tests/test_redis_service_monitor.py tests/test_monitoring.py -q`（backend/ 下）。
- 全量回归：`..\.venv\Scripts\python.exe -m pytest tests -q`（backend/ 下）。
- 迁移：`..\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head` + `downgrade -1` + 再 `upgrade head`（验证 upgrade/downgrade 与约束语义）。
- 前端：`npm run typecheck`、`npm run test`、`npm run build`（frontend/ 下）。
- 门禁：`git diff --check`；检查暂存范围和敏感字面量（无 `sk-`/DSN 明文/密码）。

## 提交计划

- S1：`feat: 服务注册表持久化与动态注册/改/删 API（DSN 加密落库 + CHECK 约束放宽）`
- S2：`feat: 服务显式连接测试接口与服务中心前端接入`
- S3：`refactor: 装配 registry_loader 与 MonitorSampler 动态读 registry`

## 分支

- 分支名：`feat/p8-service-registration`
- 基线：`main`
- worktree 路径：`D:/market-handsome/oper-mind-worktrees/p8-service-registration`（已创建，2026-08-10）
