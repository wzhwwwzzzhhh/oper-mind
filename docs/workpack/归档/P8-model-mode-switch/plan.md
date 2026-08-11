# P8-model-mode-switch · 工作包计划

> 关联 PRD：`docs/prd/model/P8-model-mode-switch.md`（已确认，issue #55）
> 关联 Design：`docs/design/model/P8模型模式切换Design.md`（已确认，arch-review PASS，用户 2026-08-10 确认 5 项决策）
> 分支：`feat/p8-model-mode-switch` · worktree：`D:/market-handsome/oper-mind-worktrees/p8-model-mode-switch` · 基线：`main`（88673f7）

## 范围

### 只做

- AC1/AC2/AC3：运行时模式切换 mock↔real 并**持久化**（应用库通用键值表 `app_settings`，key=`model.runtime_mode`），切换后 `GET /model/config` 返回新模式、会话链路按新模式运行、重启后保持。
- AC4：real 模式但未配置可用 Provider/API Key 时，保存成功但页面如实提示"real 模式已保存但当前不可用"；会话链路诚实降级（跑 mock），不伪造切换已生效。
- AC5：`GET /model/config` 的 `mode` 与页面展示始终一致（`mode_source`/`mode_available`/`mode_unavailable_reason` 三字段诚实标注），无前后端漂移。
- AC6：模式切换接口与响应不含 API Key 明文、完整 DSN 或 `sk-` 内容。
- AC7：回归 —— `test_model_config_api.py`、`test_model_provider_api.py`、`test_agent_gateway.py` 相关全绿；前端 `typecheck`/`test`/`build` 通过。
- 新增 `PUT /api/v1/model/mode` 写接口（幂等、无需 Idempotency-Key，返回完整 `ModelConfigResponse`）；`GET /model/config` 加法扩展三字段。
- 会话链路生效：`dependencies.py::_resolved_coordinator_factory` 构造 LLM 前应用模式覆盖；`/health` 的 `_service_mode`/`_effective_model_config` 改用同一解析层。

### 明确不做

- Provider 下可用模型列表自动发现、模型参数（temperature/max_tokens）暴露、用量/成本统计、多模型路由策略（PRD 排除，另行排期）。
- 不改 `load_config()` 内部实现、不改 `OPERMIND_API_KEY` 等 env 读取机制本身（PRD 排除；env 仍是"从未切过"时的兜底事实）。
- 不把模式状态放前端 localStorage（PRD 排除）。
- 不做"恢复为 env 默认"的显式 UI 重置操作（PRD 未要求）。
- 不修改 `model_providers` 表的语义（模式是全局态，非 Provider 属性；D1 裁定不复用）。
- 不修改本工作包外的既有接口契约（其余服务/会话/审批接口不动）。

## 切片拆分（1–3 个独立可验收切片）

- [ ] S1：**模式持久化 + 生效解析层 + 会话链路生效** —— `app_settings` 表迁移、AppSetting 仓库、`resolve_runtime_mode` 解析层（含 `secret_key` 透传、`_in_transaction` 提炼为共享事务助手）、coordinator factory 模式覆盖、`/health` 一致性、模式解析单测；覆盖 AC1/AC2/AC3 主体与 AC7 后端部分。
- [ ] S2：**公开 API + 前端切换** —— `PUT /model/mode` + `GET /model/config` 三字段扩展 + `ModelSettingsPage` 切换控件 + 诚实标注 + 前端/API 交互测试；覆盖 AC4/AC5/AC6/AC7。

## 改动面

### 后端（backend/）

- `backend/src/domain/model_runtime_mode.py`（新增）：`ModelRuntimeMode` 字面量常量、`ModelRuntimeResolution` TypedDict（S1）。
- `backend/src/application/model_mode.py`（新增）：`resolve_runtime_mode(session_factory, secret_key) -> ModelRuntimeResolution`、`set_runtime_mode(session_factory, mode)` 写库（S1）。
- `backend/src/application/transaction.py`（新增，S1）：把 `model_providers.py::_in_transaction` 提炼为共享事务助手，`model_providers.py` 同步改用（避免跨模块导入私有符号）。
- `backend/src/infrastructure/persistence/models.py`：新增 `AppSettingRecord`（S1）。
- `backend/src/infrastructure/persistence/app_settings_repository.py`（新增）：`get(key)` / `set(key, value)`（S1）。
- `backend/migrations/versions/20260810_10_p8_model_mode.py`（新增）：建 `app_settings` 表，upgrade/downgrade（S1）。
- `backend/src/api/v1/dependencies.py`：`_resolved_coordinator_factory` 构造 LLM 前应用模式覆盖（S1）。
- `backend/src/app.py`：`_service_mode` / `_effective_model_config` 改用 `resolve_runtime_mode`（S1）。
- `backend/src/api/v1/schemas.py`：`ModelConfigResource` 扩展 `mode_source`/`mode_available`/`mode_unavailable_reason`；新增 `UpdateModelModeRequest`（S2）。
- `backend/src/api/v1/routes.py`：新增 `PUT /model/mode`；`_model_config_resource` 改用模式解析层；`MODEL_MODE_PERSISTENCE_FAILED` → 500 并入 `APPLICATION_ERROR_STATUS`（S2）。
- `backend/src/application/model_providers.py`：`_in_transaction` 迁移到 `transaction.py` 并改引用（S1）。
- 测试：`backend/tests/test_model_mode_resolver.py`（新增，S1）、`backend/tests/test_model_mode_api.py`（新增，S2）、`backend/tests/test_model_config_api.py`（期望响应补新字段，S2）、`backend/tests/test_api.py`、`backend/tests/test_agent_gateway.py`（回归，模式解析层装配，S1/S2）、迁移测试（S1）。

### 前端（frontend/）

- `frontend/src/api/v1/queries.ts`：新增 `update_model_mode_mutation`（S2）。
- `frontend/src/api/v1/generated.ts` / `client.ts`：由 `npm run generate:api` 重新生成，**禁止手改**（S2）。
- `frontend/src/features/models/ModelSettingsPage.tsx`：运行模式卡片由只读改为 mock/real 切换控件（两态选择 + 保存），保存后把 `PUT` 返回的 `ModelConfigResponse` 直接写入 `model_config` 缓存；`mode_available=false` 时显示"real 模式已保存但当前不可用"（S2）。
- `frontend/src/features/models/ModelSettingsPage.test.tsx`：交互测试（切换 mock→real 保存、real 不可用提示）（S2）。
- `frontend/src/test/handlers.ts`：`GET /model/config` fixture 补三字段；`PUT /model/mode` MSW handler（S2）。

### 无功能改动部分

- Agent 调用策略本地偏好区、Provider CRUD、Trace 展示逻辑（本工作包不含凭据展示路径）。

## 验证方法

- 后端迁移：`..\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head`（在 worktree 内重建 venv）；验证 `app_settings` 表/约束；`downgrade` 测试。
- 后端测试：`..\.venv\Scripts\python.exe -m pytest tests/test_model_mode_resolver.py tests/test_model_mode_api.py tests/test_model_config_api.py tests/test_model_provider_api.py tests/test_agent_gateway.py tests/test_api.py -q`；随后跑 `..\.venv\Scripts\python.exe -m pytest tests -q` 全量回归。
- 前端：`npm install`（worktree 内），`npm run typecheck`、`npm run test`、`npm run build`。
- 门禁：`git diff --check`；敏感字面量扫描（无 `sk-`、无 API Key 明文、无 `config.local.yaml`）；只暂存本工作包文件。

## 提交计划

- S1：`feat: 模型模式运行时持久化与生效解析层（P8，issue #55）`
- S2：`feat: 模型模式切换接口与前端控件（P8，issue #55）`
- 文档（Design + PRD 状态双写 + workpack）随本工作包交付纳入同一 PR，另计 `docs: P8 模型模式切换 Design 与 PRD 状态同步（issue #55）`。

## 停审阅点

计划已就绪，交用户确认：范围、切片、改动面、验证方法、提交计划。确认后进入 dev-execute。
