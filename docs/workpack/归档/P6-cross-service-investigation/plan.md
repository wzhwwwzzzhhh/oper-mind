# P6-cross-service-investigation · 工作包计划

> 关联 PRD：`docs/prd/session/P6-cross-service-investigation.md`（已确认，issue #27）
> 关联 Design：`docs/design/session/P6跨服务联合调查Design.md`（已确认）
> 分支：`feat/P6-cross-service-investigation` · worktree：`D:/market-handsome/oper-mind-worktrees/P6-cross-service-investigation` · 基线：`main`（8e1c4ac）

## 范围

### 只做

- AC2/AC5/AC6/AC8/AC10：新增 `session_services` 关联表与可回滚迁移；会话读写 `service_ids`，保留 `sessions.service_id` 和单服务快捷入口兼容；旧会话从单值列兜底服务集合。
- AC2：普通会话创建支持 `service_ids: string[]`；静态服务注册表校验未注册服务，拒绝重复服务；`service_id` 与 `service_ids` 同传时以数组为准。
- AC3/AC6/AC7：Run 请求支持显式单值 `service_id`，只允许属于会话服务集合；多服务会话未显式指定且需要数据库上下文时拒绝，单服务与无服务行为保持既有语义；每个 Run 独立执行和失败降级。
- AC1/AC3/AC4/AC8/AC9：欢迎页与服务中心改为多选服务；一个用户问题顺序创建每个服务各自的 Run；在同一对话轮次按服务分组呈现结论、Trace 与证据；会话页显示服务集合。
- AC11/AC12/AC13/AC14：补齐后端、迁移、前端交互与 mock 回归测试；重新生成 API 类型；不扩展真实外部访问、不泄露凭据、DSN、环境变量或原始输出。

### 明确不做

- 不将 `DiagnosisRunData`、DBAgent 或工具链的 `service_id` 改为多值；每个 Run 始终只绑定一个服务。
- 不实现跨服务证据归因、关联推理、权限/多租户、并发控制框架或会话中途编辑服务上下文。
- 不修改 `GET /services` 契约、`data/mock_db.py`、`data/scenarios.py` 或 S1-S4 评测路径。
- 不新增服务类型、Connector、凭据存储、外部连接或任何写操作。

## 已确认设计决策

- `session_services` 以 `(session_id, service_id)` 复合主键持久化关联；`sessions.service_id` 保留给旧路径和单服务快捷入口。迁移只建表，不迁移既有数据；降级在存在关联数据时拒绝。
- `SessionData.service_ids` 是有序、去重的服务集合。读取优先关联表，无关联时从遗留单值 `service_id` 兜底。
- `POST /sessions` 接受 `service_ids`；仅带旧 `service_id` 时仍写单值列和关联表；两者同传时数组优先。
- `POST /sessions/{id}/runs` 接受可选的单值 `service_id`。多服务会话由前端按既定顺序逐个提交 Run，每个 Run 使用独立幂等键。
- send-intent 升级为 v2，在一个 intent 内保存多个 Run 的受理和恢复状态，并兼容读取 v1 单 Run intent。
- 前端只根据服务端 messages 与 runs 重建多服务分组；连续且时间相邻的相同 query 用户消息可聚合为一个调查轮次，不伪造服务端事实。

## 切片拆分（3 个独立可验收切片）

- [ ] S1：会话多服务数据模型、迁移、仓储和 API 契约。覆盖关联表、合法性/重复校验、旧会话兜底、单服务兼容与迁移 upgrade/downgrade。
- [ ] S2：显式目标服务的单服务 Run 受理。覆盖会话服务集合校验、多服务未指定时的诚实拒绝、单服务回归和独立失败语义。
- [ ] S3：工作台和服务中心多选、多 Run 提交/恢复、按服务聚合展示与服务集合标识。覆盖 v2 send-intent/v1 兼容、未选/单选回归与前端交互。

## 改动面

### 后端

- `backend/migrations/versions/`：新增 `session_services` 迁移（upgrade/downgrade 数据守卫）。
- `backend/src/domain/records.py`：`SessionData.service_ids`。
- `backend/src/infrastructure/persistence/models.py`、`repositories.py`：关联记录与 Session 多服务读写。
- `backend/src/application/contracts.py`、`services.py`、`service_center.py`：创建会话与 Run 的多服务/显式目标服务语义。
- `backend/src/api/v1/schemas.py`、`resources.py`、`routes.py`：`service_ids`、Run `service_id` 与会话资源集合契约。
- `backend/tests/test_p6_cross_service.py`（新增）及 `test_p43_service_context.py`、`test_p4_service_center.py`、`test_p2_schema.py`、`test_p2_api_v1.py`、`test_postgres_connector.py`、`test_agent_gateway.py` 的针对性回归。

### 前端

- `frontend/src/api/v1/client.ts`、`queries.ts`：会话/Run 新字段；`generated.ts` 仅通过 `npm run generate:api` 更新。
- `frontend/src/features/shell/WelcomePanel.tsx`：checkbox 多选与交互测试。
- `frontend/src/features/workbench/WorkbenchPage.tsx`、`send-intent.ts`、`conversation-turns.ts`：多 Run 顺序提交、恢复、分组投影和服务集合展示；相应 Vitest 测试。
- `frontend/src/features/services/ServiceCenterPage.tsx`：多选与批量发起，保留单行快捷入口；相应交互测试和 MSW fixture。

## 验证方法

- 后端：从 `backend/` 运行 `..\.venv\Scripts\python.exe -m pytest tests/test_p6_cross_service.py tests/test_p43_service_context.py tests/test_p4_service_center.py tests/test_postgres_connector.py tests/test_agent_gateway.py tests/test_p2_schema.py tests/test_p2_api_v1.py -q`，随后运行 `..\.venv\Scripts\python.exe -m pytest tests -q`。
- 迁移：在独立应用数据库执行 `..\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head`、`downgrade -1`、再 `upgrade head`；验证历史 Session 读取兜底与关联数据存在时的安全降级拒绝。
- 前端：worktree 内安装依赖后运行 `npm run generate:api`、`npm run typecheck`、`npm run test`、`npm run build`。
- 门禁：`git diff --check`；审查变更和测试夹具，确认没有凭据、DSN、环境变量名、原始日志、原始异常或 `sk-` 字面量；只暂存工作包文件。

## 提交计划

- S1：`feat: P6 会话多服务关联与 API 契约`
- S2：`feat: P6 支持多服务会话的单服务 Run`
- S3：`feat: P6 工作台多服务联合调查聚合`
- 收尾：`docs: P6 跨服务联合调查工作包与验收证据`

## 停审阅点

计划已就绪，待用户确认范围、切片、API/迁移兼容策略和验证方法后进入 `dev-execute`。
