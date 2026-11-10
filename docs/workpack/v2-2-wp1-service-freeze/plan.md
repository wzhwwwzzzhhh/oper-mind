# V2-2-WP1-service-freeze · 工作包计划

> 状态：计划已确认（2026-10-29，用户确认）；实现中
> 关联：PRD `docs/prd/agent-runtime/V2-2-execution-capabilities.md`（Issue #142，已确认；本片是「阶段拆分」里的 WP1）；Design `docs/design/agent-runtime/V2-2-WP1服务冻结Design.md`（已确认，arch-review 两轮后 P1=0）。
> 分支：`feat/v2-2-wp1-service-freeze`；worktree：`D:/market-handsome/oper-mind-worktrees/v2-2-wp1-service-freeze`；基线：`main` 561580f（2026-10-29 建）。

## 范围

### 只做

- **AC9（部分）**：服务引用在受理时冻结。`service_id` 由用户选择，受理期校验并写入 `MainInputSnapshotV1.service`；`run.service_id` 落同一值，**含重跑路径**（带 `None` 守卫）。
- **受理校验两级**：格式错误 → 422 `VALIDATION_ERROR`；未注册／类型不符／无凭据 → 409 `MAIN_AGENT_SERVICE_UNAVAILABLE`。只查内存注册表，不建立连接。
- **AC10（部分）**：V1 默认入口、V1 调查链、V2-0／V2-1 既有行为不变；无迁移、无新端点、无新事件类型、无新依赖。
- **AC8（部分）**：界面能选服务并如实显示三态（加载中／读取失败／确实为空）与「本片未启用」的未来时文案。

### 明确不做

- 不新增任何能力；不改 `CapabilityDefinition`；不改 `core/` 全部（含 `main_agent_react.py`、`capability_tools.py`、`tool_gateway.py`）。
- 不改交付：`MainDeliveryV1` 仍是 `answer | needs_input | comparison`；不碰 `run_deliveries`、不碰迁移。
- 不做会话范围收紧（PRD 该条仍是开放问题）。
- 不探测服务连通性（受理期不建连接）。
- 不实现健康摘要／日志扫描（属 WP2／WP3）；不提前设计它们的契约字段。
- 不手工编辑 `frontend/src/api/v1/generated.ts`。

## 切片拆分

- [ ] S1 后端管道：领域字段 + 条件序列化 + 受理校验 + 指纹 + 公开资源投影。
- [ ] S2 前端选择器：`MainAgentComposer` 自持 query、三态、未来时文案、错误提示。

## 阶段位置

- 本片在整体路径中的位置：第 1 片 / 共 3 片（WP1 服务冻结 → WP2 健康摘要 + structured → WP3 日志扫描插件证明）。
- 下一片是什么（一句话）：WP2 在冻结服务上跑 `service.health_summary@1`，并引入通用 `structured` 交付与一次 `run_deliveries.kind` CHECK 迁移。
- 本片交付后，下一片能多知道哪些事实：服务冻结链路真实可用、`run.service_id` 在受理/重跑/公开资源三处一致、条件序列化不破坏旧行；WP2 才能据此决定「能力输入契约」到底要加哪些字段。

## 改动面（文件级）

后端修改：

- `backend/src/domain/main_agent.py`：`MainInputV1.service_id`、`MainInputSnapshotV1.service`、`MainServiceBindingV1`（唯一定义处）
- `backend/src/infrastructure/persistence/repositories.py`：`SqlAlchemyRunInputRepository.add` 条件序列化（`service is None` 时 `payload.pop("service")`）
- `backend/src/application/run_execution.py`：`build_main_input_snapshot` / `rebuild_main_input_snapshot` 带 `service`；两个指纹**仅在 `service_id` 非空时**追加键
- `backend/src/application/services.py`：受理期服务校验（幂等重放判定之后，仅对 `CreateMainAgentRunCommand`）、`run.service_id`（含重跑分支 `None` 守卫）
- `backend/src/application/errors.py`：`MainAgentServiceUnavailableError`（409）
- `backend/src/api/v1/schemas.py`：`CreateMainAgentRunRequest.service_id`、`MainServiceBindingResource`、`MainInputSnapshotResource.service`
- `backend/src/api/v1/routes.py`：`_run_command` 透传、`APPLICATION_ERROR_STATUS` 加 409
- `backend/src/api/v1/resources.py`：`main_input_snapshot_resource` 投影 `service`

后端测试：

- `backend/tests/test_main_agent_runs_api.py`：改写既有 422 断言；新增 service_id 受理/校验/重跑/幂等用例
- `backend/tests/test_main_agent_runtime.py`：条件序列化与指纹不变用例（如该文件承载更合适）

前端修改：

- `frontend/src/features/workbench/MainAgentComposer.tsx`：服务选择器（自持 `useQuery`，三态，未来时文案）
- `frontend/src/api/v1/queries.ts`：mutation 变量加 `service_id`
- `frontend/src/api/v1/generated.ts`：**只允许** `npm run generate:api` 重新生成
- `frontend/src/test/handlers.ts`：加法 mock（一个 `kind:'postgres'` + `has_dsn:true` 的服务）

**数据库变更**：无。**公开端点**：无新增。**事件类型**：无。**依赖**：无新增。

## 验证方法

后端（`backend/` 下）：

- 聚焦：`..\.venv\Scripts\python.exe -m pytest tests/test_main_agent_runs_api.py -q`
- 聚焦：`..\.venv\Scripts\python.exe -m pytest tests/test_main_agent_runtime.py -q`
- 全量：`..\.venv\Scripts\python.exe -m pytest tests -q`

前端（`frontend/` 下）：

- `npm run typecheck` / `npm run test` / `npm run build`

门禁：

- `git diff --check` 干净
- 敏感字面量扫描无命中
- **专项断言**：无服务快照写入后 `payload` 不含 `service` 键；无服务请求的创建/重跑指纹与改动前逐字节相同

## 提交计划

- `feat: 受理期冻结服务引用`（S1 后端管道）
- `feat: 主 Agent 录入区支持选择服务`（S2 前端选择器）
