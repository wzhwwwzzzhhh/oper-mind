# P8-model-list-enumeration · AC 证据表

> 回写规则：随切片推进更新；验证记录以实际命令输出为准。

## 切片 S1：后端枚举接口（已完成）

验证记录：
- `pytest tests/test_model_provider_verify.py tests/test_model_provider_api.py -q` → **51 passed**
- 回归：`pytest tests/test_model_config_api.py tests/test_agent_gateway.py tests/test_model_provider_resolver.py -q` → **13 passed**
- 全量：`pytest tests -q` → 结果见 commit 时记录（64+ passed）

改动：
- `backend/src/infrastructure/model_provider_verify.py`：新增 `ProviderModelsOutcome`/`fetch_provider_models`/`_parse_model_names`，verify 与枚举共享受控请求 `_request_provider_models`；限长 100 条/200 字符/1MB。
- `backend/src/domain/model_provider.py`：新增 `ModelProviderModelsData`。
- `backend/src/application/model_providers.py`：新增 `list_models`/`_enumerate_against`/`_provider_plaintext_or_error`（verify 共享解密，行为不变）。
- `backend/src/api/v1/schemas.py`：新增 `ModelProviderModelsResponse`（status 含 unsupported 预留）。
- `backend/src/api/v1/routes.py`：新增 `GET /model/providers/{provider_id}/models`。

## 切片 S2：前端交互 + 文档（已完成）

验证记录：
- `npx vitest run src/features/models/ModelSettingsPage.test.tsx` → **11 passed**
- 全量 `npx vitest run` → **15 files / 116 passed**
- `npm run typecheck` → 通过；`npm run build` → 通过

改动：
- `frontend/src/api/v1/client.ts`：`ModelProviderModelsResponse` 类型 + `list_model_provider_models` 方法。
- `frontend/src/api/v1/queries.ts`：`list_provider_models_mutation`。
- `frontend/src/api/v1/generated.ts`：OpenAPI 重新生成。
- `frontend/src/features/models/ModelSettingsPage.tsx`：刷新按钮（新建态禁用+提示）、三态渲染、下拉选择填充、编辑态保留当前值。
- `frontend/src/test/handlers.ts` + `ModelSettingsPage.test.tsx`：MSW 三态用例。
- `frontend/src/styles/model-settings.css`：`.model-field-row` / `.model-models-select`。
- `docs/接口清单.md`：新增枚举接口行、欠账表该项 ✅、计数同步。

## AC 结论（独立审查 PASS 后）

AC1–AC8 全部 PASS（证据见 `review.md`）。
