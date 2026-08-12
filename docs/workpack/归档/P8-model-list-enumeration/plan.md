# P8-model-list-enumeration · 工作包计划

> 关联 PRD：`docs/prd/model/P8-model-list-enumeration.md`（已确认，issue #63）
> 关联 Design：`docs/design/model/P8模型可用列表探测Design.md`（已确认，arch-review PASS + 用户确认 2026-08-12）
> 分支：`feat/model-list-enumeration`（基线 main）；worktree：`D:/market-handsome/oper-mind-worktrees/model-list-enumeration`

## 范围

### 只做
- 后端枚举能力：`fetch_provider_models()`（复用 P6 `model_provider_verify.py` 的主机校验/5s 超时/Bearer 头/脱敏错误码；解析 OpenAI-compatible `GET /v1/models` 响应的 `data[].id`；去重保序限 100 条、单项限 200 字符）——PRD 功能需求 1、AC1/AC6
- 应用服务 `list_models(provider_id)`：无 Key/主密钥缺失/解密失败诚实分类（`NO_API_KEY`/`SECRET_KEY_NOT_CONFIGURED`/`KEY_DECRYPT_FAILED`）；HTTP 200 解析失败 → `MODELS_PARSE_FAILED`；不落库、无副作用（不写 `verify_status`）——PRD 功能需求 1、AC2/AC3/AC4
- 接口 `GET /api/v1/model/providers/{provider_id}/models`：`status` 为 `ok`/`failed`/`timeout`/`unsupported`（预留，当前不产生）；Provider 不存在 → 404——PRD 功能需求 1、AC1–AC4
- 前端：编辑态表单"刷新模型列表"按钮 + 模型下拉 + 三态展示（成功/脱敏失败原因/未配置）；新建态按钮禁用 + 提示"保存 Provider 后可刷新模型列表"——PRD 功能需求 2、AC5
- `docs/接口清单.md`：Provider 表新增枚举接口行；欠账表 `Provider 下可用模型列表` 标 ✅

### 明确不做
- 不缓存/不持久化模型列表（现场拉取，Design D3，用户已确认）
- 不做非 OpenAI-compatible 枚举（Ollama `/api/tags` 等；PRD 排除，首版只做 OpenAI-compatible）
- 不改 P6 verify 语义与状态字段；枚举无副作用（Design D2/D3，用户已确认）
- 不暴露 API Key 明文、完整 Base URL、`sk-`、原始响应体（AC4）
- 不改 `model` 必填约束与既有 Provider 接口契约（兼容性：既有接口契约不变）

## 切片拆分（2 片，顺序执行）

- [ ] **S1 后端枚举接口**：`fetch_provider_models` + domain `ModelProviderModelsData` + 应用服务 `list_models` + 路由/schema + 后端测试。验收语义：可连通→模型名列表（去重限长）；失败/超时→脱敏状态码不暴露响应体；无 Key/主密钥缺失/解密失败→诚实分类；Provider 不存在→404；解析失败→诚实 `failed`（AC1/AC2/AC3/AC4/AC6/AC7）。
- [ ] **S2 前端交互 + 文档**：编辑态按钮/下拉/三态 + 新建态禁用提示 + MSW 测试 + `generated.ts` 重新生成 + 接口清单更新。验收语义：成功展示下拉可选、失败展示脱敏原因、未配置展示"未启用"（AC5）+ AC8 回归全绿。

## 改动面（文件级）

### 后端（backend/）
- **修改** `src/infrastructure/model_provider_verify.py` —— 新增 `ProviderModelsOutcome` + `fetch_provider_models()`，与 verify 共享受控请求私有函数（verify 对外语义不变）
- **修改** `src/domain/model_provider.py` —— 新增 `ModelProviderModelsData`（Pydantic 跨层模型）
- **修改** `src/application/model_providers.py` —— 新增 `list_models(provider_id)` 方法
- **修改** `src/api/v1/schemas.py` —— 新增 `ModelProviderModelsResponse`
- **修改** `src/api/v1/routes.py` —— 新增 `GET /model/providers/{provider_id}/models` 路由
- **修改** `tests/test_model_provider_api.py` —— 枚举接口用例（ok/failed/timeout/无 Key/404/解析失败）
- **修改** `tests/test_model_provider_verify.py` —— `fetch_provider_models` 单测（httpx MockTransport）

### 前端（frontend/）
- **修改** `src/features/models/ModelSettingsPage.tsx` —— 表单"刷新模型列表"按钮 + 模型下拉 + 三态
- **修改** `src/api/v1/queries.ts` —— 新增枚举 mutation；`generated.ts` 由 OpenAPI 重新生成（禁手改）
- **修改** `src/api/v1/client.ts` —— 新增 `list_model_provider_models` 方法与类型（实现必需接线，审查后补列）
- **修改** `src/features/models/ModelSettingsPage.test.tsx` —— MSW 三态用例
- **修改** `src/test/handlers.ts` —— MSW 枚举 handler（实现必需接线，审查后补列）
- **修改** `src/styles/model-settings.css` —— 表单横排与下拉样式（实现必需接线，审查后补列）

### 文档
- **修改** `docs/接口清单.md` —— 新增枚举接口行；欠账表该项标 ✅

无数据库迁移、无凭据变更、无既有接口契约破坏。

## 验证方法

- 后端（`backend/` 下执行）：
  - 本包：`..\.venv\Scripts\python.exe -m pytest tests/test_model_provider_api.py tests/test_model_provider_verify.py -q`
  - 回归（AC8）：`..\.venv\Scripts\python.exe -m pytest tests/test_model_config_api.py tests/test_agent_gateway.py tests/test_model_provider_resolver.py -q`
- 前端（`frontend/` 下执行）：
  - `npm run typecheck`、`npm run test`、`npm run build`
  - `npm run generate:api`（需后端 8000 提供 OpenAPI；端口不可用时按 dev-plan 已知坑：落盘 `openapi.json` 再 `npx openapi-typescript` 生成）
- 门禁：`git diff --check`；只暂存本工作包文件；提交信息 `<类型>: <中文描述>`

## 提交计划

- S1 完成并验证后提交：`feat: 模型可用列表探测——后端 Provider 模型枚举接口`
- S2 完成并验证后提交：`feat: 模型可用列表探测——前端刷新模型列表与模型选择`

## 验证前置说明

- S1 与 S2 顺序执行（S2 依赖 `generated.ts` 包含枚举接口类型）。
- 真实连接门禁：复用 P6 verify 已批准的同端点只读模式；本包测试全部走 mock（monkeypatch / MockTransport / MSW），不发起真实外部请求。
