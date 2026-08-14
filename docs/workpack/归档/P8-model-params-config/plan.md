# P8-model-params-config · 工作包计划

## 范围

### 只做
- AC1：运维保存 `temperature=0.5` 后，会话链路 `LLMClient.chat()` 真传 0.5（主链路内容生成调用，非 localStorage）。
- AC2：未配置参数时用后端默认（temperature 0.0 / max_tokens 不传）并如实标注（`params_defaults`）。
- AC3：非法参数（temperature 超 [0,2]、max_tokens 非 [1,102400] 整数）拒绝保存，422 明确错误。
- AC4：参数持久化 `app_settings` 键 `model.params`（JSON），重启后保持；无新迁移。
- AC5：配置前后端一致（页面展示 = 后端 `GET /model/config` 返回的 params）。
- AC6：参数接口不含 API Key 明文 / DSN / `sk-`（参数与凭据无关，天然满足）。
- AC7：未进 `chat()` 的参数（top_p 等）不出现于配置界面（表单只有 temperature / max_tokens 两字段）。
- AC8：mock 路径 `_mock_chat` 不读参数，行为不变；前端标注「仅 real 生效」。
- AC9：回归——`test_model_config_api.py` / `test_model_provider_api.py` / `test_agent_gateway.py` 相关全绿；前端 `typecheck`/`test`/`build` 通过。

### 明确不做
- 不做 top_p / frequency_penalty 等未进 `chat()` 的参数（PRD 排除）。
- 不做按 Provider / 按 Agent 参数作用域（已确认全局，Design D2）。
- 不复活 localStorage 假开关（PRD 排除）。
- 不新增环境变量参数兜底（Design D2：参数唯一来源 app_settings）。
- 不改 `resolve_runtime_mode` / `resolve_model_config` 契约（Design D3：参数解析同层独立）。
- 不改 graph.py:158 / graph.py:269 / debate.py:77 三处显式 `temperature=0.0`（用户已确认保留）。

## 已确认设计决策（docs/design/model/P8模型参数配置Design.md，用户 2026-08-12 确认）
1. 参数范围：temperature + max_tokens 都进 `chat()`；`temperature: float|None = None`（None→实例默认）、`max_tokens: int|None = None`（None→不传 SDK）。
2. 作用域：全局，`app_settings` 单键 `model.params`（JSON），无新迁移（表已由 P8 模式切换迁移建好）。
3. 生效面：三处显式 0.0 保留（路由/分歧/辩论裁决）；Agent 分析、Reflection 质检、报告生成走配置默认。
4. mock：共用同一份配置、mock 路径不读参数、前端标注「仅 real 生效」。
- 沿用既有决策：`app_settings` 键值模式（`model.runtime_mode`，P8 模式切换 Design）；解析层永不 raise 的降级纪律（`resolve_runtime_mode`）；错误码并入 `APPLICATION_ERROR_STATUS` 映射；写接口幂等无需 Idempotency-Key（对齐 `PUT /model/mode` 先例）。

## 切片拆分（3 个独立可验收切片）
- [ ] S1: 参数持久化 + 解析层 + 读写 API——`domain/model_params.py`（校验/JSON 编解码）+ `application/model_params.py`（get/set + `resolve_model_params` 永不 raise）+ `PUT /model/params` 路由 + `GET /model/config` 契约兼容扩展（params / params_defaults）+ `test_model_params_api.py`。验收：保存/清除/校验 422/应用库降级/重启持久。
- [ ] S2: 生效链路——`LLMClient` 实例默认（default_temperature / default_max_tokens）+ `chat()` 参数扩展 + `build_llm_from_config(config, params=None)` + `_resolved_coordinator_factory` 注入 + `test_llm_client.py`。验收：配置后主链路传新值、未配置仍 0.0、显式传参处不变、mock 路径不变。
- [ ] S3: 前端参数表单——client/queries/generated + `ModelSettingsPage.tsx` 参数区（temperature/max_tokens 表单 + 保存 + 默认值标注 + mock 标注）+ MSW handler + 交互测试 + CSS。验收：页面展示 = 后端值、非法输入被拒、AC5/AC7/AC9。

## 改动面（文件级）
### S1 后端持久化与 API
- 新增 `backend/src/domain/model_params.py`（MODEL_PARAMS_KEY、ModelParams Pydantic、ModelParamsResolution TypedDict、JSON 编解码 helper）
- 新增 `backend/src/application/model_params.py`（ModelParamsApplicationService.get/set + resolve_model_params）
- 修改 `backend/src/api/v1/schemas.py`（ModelParamsResource、UpdateModelParamsRequest、ModelConfigResource 追加 params/params_defaults）
- 修改 `backend/src/api/v1/routes.py`（PUT /model/params、_model_config_resource 补 params）
- 新增 `backend/tests/test_model_params_api.py`

### S2 生效链路
- 修改 `backend/src/core/llm.py`（chat 签名扩展 + 实例默认字段；mock 路径不动）
- 修改 `backend/src/core/bootstrap.py`（build_llm_from_config 加 params 参数）
- 修改 `backend/src/api/v1/dependencies.py`（factory 解析 resolve_model_params 并注入）
- 新增 `backend/tests/test_llm_client.py`

### S3 前端
- 修改 `frontend/src/api/v1/client.ts`、`frontend/src/api/v1/queries.ts`；`generated.ts` 重新生成（`npm run generate:api`，后端 OpenAPI 落盘方式，不占端口）
- 修改 `frontend/src/features/models/ModelSettingsPage.tsx`（运行参数 section）
- 修改 `frontend/src/test/handlers.ts`（PUT /model/params handler）
- 修改 `frontend/src/features/models/ModelSettingsPage.test.tsx`
- 修改 `frontend/src/styles/model-settings.css`

### 收尾文档（纳入实现 PR）
- 新增 `docs/design/model/P8模型参数配置Design.md`（已写，尚未入 git）
- 新增 `docs/workpack/P8-model-params-config/plan.md`（本文件）
- 修改 `docs/prd/model/P8-model-params-config.md`（frontmatter 进行中→完成，收尾时）
- 修改 `docs/prd/README.md` + `docs/prd/model/README.md`（状态双写）
- 修改 `docs/接口清单.md`（欠账行「模型参数」标记）
- 修改 `docs/workpack/README.md`（活跃→归档）

### 无功能改动
- Provider CRUD/verify/activate/枚举、服务中心、Trace、会话其他链路（不动）。

## 验证方法
- 后端（backend/ 内）：`..\.venv\Scripts\python.exe -m pytest tests/test_model_params_api.py tests/test_llm_client.py tests/test_model_config_api.py tests/test_model_provider_api.py tests/test_agent_gateway.py -q`
- 后端全量回归：`..\.venv\Scripts\python.exe -m pytest tests -q`
- 前端（frontend/ 内）：`npm run typecheck`、`npm run test`、`npm run build`
- 门禁：`git diff --check`、CI（ruff + mypy + pytest + 前端 + Gitleaks）

## 提交计划
- S1 完成后：`feat: 模型参数持久化与读写 API（P8 模型参数配置 S1）`
- S2 完成后：`feat: 模型参数进入 LLM 调用链（P8 模型参数配置 S2）`
- S3 完成后：`feat: 模型设置页运行参数表单（P8 模型参数配置 S3）`
- 收尾：`docs: P8 模型参数配置收尾——PRD 完成、归档工作包`

## 分支与工作区
- worktree：`D:/market-handsome/oper-mind-worktrees/model-params-config`
- 分支：`feat/model-params-config`（基线 `main`）
- 环境：worktree 为全新 checkout，复制主仓库 `.venv` 到 worktree `backend/.venv`（已知坑：init 脚本在 PowerShell 5.1 GBK 失败、numpy==2.4.6 不在公开 PyPI）
