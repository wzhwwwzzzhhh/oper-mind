# P8-model-usage-stats · 工作包计划

## 范围

### 只做
- AC1：真实 LLM 调用完成时把 usage（input/output/total tokens + 模型名 + 时间戳）落库（`LLMClient.chat()` 真实分支返回处采集，mock 不采集）。
- AC2：`GET /model/usage` 按时间窗/模型返回 token 用量聚合统计（按模型分组）。
- AC3：时间窗过滤只返回窗口内用量（`from ≤ to` 校验，缺省近 30 天，窗口上限 366 天）。
- AC4：花费标注"估算"；未配置单价用内置默认，`app_settings` 键 `model.prices` 配置后按配置估算（单价来源 builtin/configured/unset）。
- AC5：mock 调用不采集用量（mock 恒 0，统计中无 mock 记录，前端如实标注）。
- AC6：无用量记录时返回空态（`items: []`，HTTP 200），不抛错。
- AC7：用量统计响应不含调用内容/prompt/响应/API Key/`sk-`/凭据（表无内容字段）。
- AC8：单次用量采集失败不影响 LLM 调用本身（采集 try/except 降级只记日志）。
- AC9：前端用量区域展示统计，支持时间窗筛选，空态/失败态诚实。
- AC10：回归——`test_agent_gateway.py` / `test_model_provider_api.py` 相关全绿；前端 `typecheck`/`test`/`build` 通过。
- DoD：用量记录表迁移 upgrade/downgrade 执行成功；`git status` 只出现本工作包文件。

### 明确不做
- 不做精确账单/计价（PRD 排除，只做估算）。
- 不做按会话/Run 的用量明细下钻（`run_id` 预留可空列，首版不写入）。
- 不做用量告警/限额（PRD 排除，另行排期）。
- 不采集 mock 用量（mock 恒 0）。
- 不暴露调用内容/prompt/响应/API Key/凭据。
- 不为单价新建表（复用 `app_settings` 键值 `model.prices`，对齐 `model.params` 先例）。
- 不改变 `LLMClient` 返回契约与既有调用语义（recorder 参数默认 None，采集是副作用）。
- 不改 Provider/模式切换/参数配置既有行为与契约。

## 已确认设计决策（docs/design/model/P8用量与成本统计Design.md，用户 2026-08-13 确认）
1. 单价来源：内置默认单价表（`DEFAULT_MODEL_PRICES`）+ `app_settings` 键 `model.prices` 按模型覆盖；未配置用内置默认，未列出模型回退通用默认并标注来源（用户确认复用 app_settings，不建新表）。
2. `run_id` 预留：`model_usage_records.run_id` 可空列，首版不写入（NULL），供后续下钻免迁移。
3. 采集同步轻量写：调用返回处单条写入，失败降级不阻断；不引入异步队列。
4. 默认时间窗：未传 from/to 默认近 30 天；窗口跨度上限 366 天。
- 沿用既有决策：`UsageRecorder` Protocol 注入（对齐 `AppSettingsStore` 端口先例）；解析层永不 raise 的降级纪律（`resolve_model_params`）；错误码并入 `APPLICATION_ERROR_STATUS` 映射；`from` query 参数用 `from_` + alias；OpenAI usage 字段映射 `prompt_tokens`→input、`completion_tokens`→output。

## 切片拆分（2 个独立可验收切片）
- [ ] S1: 后端采集 + 统计接口——迁移（`model_usage_records` 表）+ `domain/model_usage.py`（UsageRecorder/UsageRecord/DEFAULT_MODEL_PRICES/单价编解码）+ `infrastructure/persistence/model_usage_repository.py`（SqlAlchemyUsageRecorder 写入 + 聚合查询）+ `application/model_usage.py`（stats 查询 + 单价解析 + 花费估算）+ `LLMClient` recorder 注入 + `GET /model/usage` 路由 + 测试。验收：真实调用落库（AC1）、聚合与时间窗（AC2/AC3）、单价估算与标注（AC4）、mock 恒 0（AC5）、空态（AC6）、脱敏（AC7）、采集失败不阻断（AC8）、迁移成功。
- [ ] S2: 前端用量展示——client/queries 新增 usage 查询 + `ModelSettingsPage.tsx` 用量统计 section（时间窗筛选 + 按模型表格 + 估算标注 + 空态/失败态）+ 交互测试 + CSS。验收：AC9；回归 AC10（typecheck/test/build 通过）。

## 改动面（文件级）

### S1 后端采集与统计接口
- 新增 `backend/src/domain/model_usage.py`（UsageRecorder Protocol、UsageRecord TypedDict、DEFAULT_MODEL_PRICES、单价 JSON 编解码 helper）
- 新增 `backend/src/infrastructure/persistence/model_usage_repository.py`（SqlAlchemyUsageRecorder + SqlAlchemyModelUsageRepository 聚合查询）
- 修改 `backend/src/infrastructure/persistence/models.py`（新增 ModelUsageRecord）
- 新增 `backend/migrations/versions/20260813_13_p8_model_usage.py`（建 model_usage_records 表，upgrade/downgrade）
- 新增 `backend/src/application/model_usage.py`（ModelUsageApplicationService）
- 修改 `backend/src/core/llm.py`（LLMClient 新增 usage_recorder 可选参数；chat 真实分支采集）
- 修改 `backend/src/core/bootstrap.py`（build_llm_from_config 透传 usage_recorder）
- 修改 `backend/src/api/v1/dependencies.py`（_resolved_coordinator_factory 注入 SqlAlchemyUsageRecorder；V1Services 增加 model_usage_service）
- 修改 `backend/src/api/v1/schemas.py` + `resources.py` + `routes.py`（ModelUsageResponse/ModelUsageItemResource、GET /model/usage）
- 新增 `backend/tests/test_usage_recording.py`、`backend/tests/test_model_usage_api.py`

### S2 前端用量展示
- 修改 `frontend/src/api/v1/client.ts`、`frontend/src/api/v1/queries.ts`；`generated.ts` 由 `npm run generate:api` 生成（后端 OpenAPI 落盘方式，禁止手改）
- 修改 `frontend/src/features/models/ModelSettingsPage.tsx`（用量统计 section）
- 修改 `frontend/src/test/handlers.ts`（GET /model/usage handler）
- 修改 `frontend/src/features/models/ModelSettingsPage.test.tsx`
- 修改 `frontend/src/styles/model-settings.css`

### 收尾文档（纳入实现 PR）
- 新增 `docs/design/model/P8用量与成本统计Design.md`（已写，已确认，尚未入 git）
- 新增 `docs/workpack/P8-model-usage-stats/plan.md`（本文件）+ 后续 `review.md` / `evidence.md`
- 修改 `docs/prd/model/P8-model-usage-stats.md`（frontmatter 已确认→进行中，S1 开工后；收尾时→完成）
- 修改 `docs/prd/README.md` + `docs/prd/model/README.md`（状态双写）
- 修改 `docs/接口清单.md`（第四大模块欠账行「用量 / 成本统计」标记）
- 修改 `docs/workpack/README.md`（登记活跃 → 收尾归档）

### 无功能改动
- Provider CRUD/verify/activate/枚举、模式切换、参数配置、服务中心、Trace、会话其他链路（不动）。

## 验证方法
- 后端（backend/ 内）：`..\.venv\Scripts\python.exe -m pytest tests/test_usage_recording.py tests/test_model_usage_api.py tests/test_model_provider_api.py tests/test_model_config_api.py tests/test_agent_gateway.py -q`
- 后端全量回归：`..\.venv\Scripts\python.exe -m pytest tests -q`
- 迁移验证：`..\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head` 与 `downgrade -1` + `upgrade head`
- 前端（frontend/ 内）：`npm run typecheck`、`npm run test`、`npm run build`
- 门禁：`git diff --check`、CI（ruff + mypy + pytest + 前端 + Gitleaks）

## 提交计划
- S1 完成后：`feat: 用量采集落库与统计接口（P8 用量统计 S1）`
- S2 完成后：`feat: 模型设置页用量统计区域（P8 用量统计 S2）`
- 收尾：`docs: P8 用量统计收尾——PRD 完成、归档工作包`

## 分支与工作区
- worktree：`D:/market-handsome/oper-mind-worktrees/P8-model-usage-stats`
- 分支：`feat/P8-model-usage-stats`（基线 `main` = 8a644f3，已建）
- 环境：worktree 为全新 checkout，从主仓库复制 `.venv` 到 worktree 根（参照 P8-model-params-config 经验：init 脚本 PowerShell 5.1 GBK 坑、numpy 版本坑）；前端需 `npm install`
