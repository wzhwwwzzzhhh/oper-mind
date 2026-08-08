# P6-model-provider-key-management · 工作包计划

> 关联 PRD：`docs/prd/model/P6-model-provider-key-management.md`（已确认，issue #22）
> 关联 Design：`docs/design/model/P6模型Provider与APIKey管理Design.md`（已确认，arch-review PASS，用户 2026-08-06 确认 4 项决策）
> 分支：`feat/p6-model-provider-key-management` · worktree：`D:/market-handsome/oper-mind-worktrees/p6-model-provider-key-management` · 基线：`main`（0f532ab）

## 范围

### 只做

- AC1/AC2/AC9：Provider 配置（名称 / Base URL / 模型 / API Key）新增/编辑/删除/列表，API Key AES-256-GCM 加密落库、掩码展示、永不落明文/日志/Trace/响应。
- AC3/AC4：连接验证接口，受控最小只读请求、5s 限时、失败/超时脱敏原因（含 SSRF 主机校验）。
- AC5/AC6/AC7：`resolve_model_config()` 生效配置解析（DB 激活优先、env/YAML 兜底），`build_llm`/`app.py` 每 Run 构造，保存即生效、无需重启；未配置诚实降级（mock/未配置）；mock/real 如实标注。
- AC8：回归 —— `test_model_config_api` 相关、`test_agent_gateway.py` 全绿；前端 `typecheck`/`test`/`build` 通过。
- 前端模型设置页 Provider 区替换为真实配置 CRUD（掩码展示、保存、验证、激活、删除）；Agent 调用策略本地偏好区保持不动。
- 新增 `OPERMIND_SECRET_KEY`（≥32 字符）读取与校验；`config.example.yaml` 文档化。

### 明确不做

- 多租户 / 多用户模型权限管理、模型列表自动发现、Agent 调用策略真实化（沿用 P4.3 结论）。
- 不改 `load_config()` 内部实现（env 优先 YAML 既有逻辑）；仅在其上层叠加 DB 激活配置解析。
- 不接外部密钥服务（Vault 等）。
- 不修改本工作包外的既有接口契约（`GET /api/v1/model/config` 保持兼容，其余服务/会话/审批接口不动）。

## 切片拆分（1–3 个独立可验收切片）

- [x] S1：**加密持久化 + Provider 读写/激活 API** —— `secrets.py` 加密模块、`model_providers` 表迁移、Repository、应用服务、CRUD/activate 接口、脱敏/掩码；覆盖 AC1、AC2、AC9 主体。
- [x] S2：**连接验证** —— verify 接口，受控最小请求、限时、脱敏错误、SSRF 主机校验；覆盖 AC3、AC4。
- [x] S3：**配置生效贯通 + 前端** —— `resolve_model_config()`、`build_llm`/`app.py` 每 Run 构造、`GET /model/config` 兼容、前端 CRUD/掩码/验证/激活 + 交互测试；覆盖 AC5–AC8。

## 改动面

### 后端（backend/）

- `backend/requirements.txt`：新增 `cryptography`（S1）。
- `backend/src/infrastructure/secrets.py`（新增）：AES-256-GCM 加密/解密封装，密钥 HKDF 派生自 `OPERMIND_SECRET_KEY`（含最小长度校验）；公开函数带类型标注，禁裸 `except`、禁打印（S1）。
- `backend/src/infrastructure/persistence/models.py`：新增 `ModelProviderRecord`（含 `api_key_encrypted`/`api_key_nonce` 密文字段、`active_endpoint` 唯一约束、verify 状态字段；无明文字段）（S1）。
- `backend/migrations/versions/<timestamp>_p6_model_provider.py`（新增）：建 `model_providers` 表，upgrade/downgrade（S1）。
- `backend/src/infrastructure/persistence/model_provider_repository.py`（新增）：Provider 读写 + 激活原子替换（去旧置新，单事务）（S1）。
- `backend/src/application/model_providers.py`（新增）：Provider 读写/验证/激活应用服务 + `resolve_model_config()` 生效配置解析层（显式注入"激活 Provider 读取器"port，不读 config.py 内的 DB，避免层级倒挂与迁移 env.py 循环导入）（S1 部分 / S3 解析）。
- `backend/src/config.py`：仅新增 `OPERMIND_SECRET_KEY` 读取与校验（≥32 字符）；**不改 `load_config()` 既有逻辑**（S1）。
- `backend/src/core/bootstrap.py` / `app.py`：`build_llm()` 改用 `resolve_model_config()`；`app.py` 由 `_shared_llm` 单例改为每 Run 构造（`_service_mode()`/`/health` 对 `_shared_llm` 的引用一并改读解析层或 env 兜底，装配经 `app.state.v1_services`/`get_v1_services` 注入）；`resolve_model_config()` 在 LLM 构造点永不 raise（诚实空态）（S3）。
- `backend/src/api/v1/schemas.py`、`routes.py`：新增 Provider CRUD/verify/activate 接口契约与路由（POST create 要求 `Idempotency-Key`；activate 请求体 `{"endpoint": "diagnostic"|"judge"}`；错误码 404/422/409 并入既有 `APPLICATION_ERROR_STATUS` 映射）；`GET /model/config` 改读 `resolve_model_config()`（S1/S2/S3）。
- `backend/src/api/v1/dependencies.py`：`build_v1_services_for_runtime` 内装配含 `build_llm → resolve_model_config` 的工厂（S3）。
- `config/config.example.yaml`：文档化 `OPERMIND_SECRET_KEY`（最小长度与备份提示）（S1）。
- 测试：`backend/tests/test_secrets.py`（新增，S1）、`backend/tests/test_model_provider_api.py`（新增，S1/S2）、`backend/tests/test_model_config_api.py`（回归兼容，S3）、`backend/tests/test_api.py`（`_shared_llm` fixture 改走 env/`resolve_model_config()` 兜底，S3）、迁移测试（S1）。

### 前端（frontend/）

- `frontend/src/api/v1/queries.ts`：新增 Provider 查询/变更（S3）。
- `frontend/src/api/v1/generated.ts`：由 `npm run generate:api` 重新生成，**禁止手改**（S3）。
- `frontend/src/features/models/ModelSettingsPage.tsx`：Provider 区替换为真实配置 CRUD（掩码展示、保存、验证、激活、删除）；Agent 调用策略本地偏好区保持不动（S3）。
- `frontend/src/features/models/ModelSettingsPage.test.tsx`：交互测试（MSW mock）（S3）。
- `frontend/src/test/handlers.ts`：Provider MSW fixture（S3）。

### 无功能改动部分

- 会话链路其他部分、Trace 展示逻辑、服务中心/审批接口（本工作包不含凭据展示路径）。

## 验证方法

- 后端迁移：`..\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head`（在 worktree 内重建 venv）；验证表/索引/约束；`downgrade` 测试。
- 后端测试：`..\.venv\Scripts\python.exe -m pytest tests/test_secrets.py tests/test_model_provider_api.py tests/test_model_config_api.py tests/test_agent_gateway.py tests/test_api.py -q`；随后跑 `..\.venv\Scripts\python.exe -m pytest tests -q` 全量回归。
- 前端：`npm install`（worktree 内），`npm run typecheck`、`npm run test`、`npm run build`。
- 门禁：`git diff --check`；敏感字面量扫描（无 `sk-`、无 API Key 明文、无 `config.local.yaml`）；只暂存本工作包文件。

## 提交计划

- S1：`feat: 模型 Provider 加密持久化与读写/激活 API（P6）`
- S2：`feat: 模型 Provider 连接验证接口（P6）`
- S3：`feat: 模型 Provider 配置生效贯通与前端管理（P6）`
- 文档（Design + PRD 双写 + workpack）随本工作包交付纳入同一 PR，另计 `docs: P6 模型 Provider 与 API Key 管理 Design 与 PRD 同步（issue #22）`。

## 停审阅点

计划已就绪，交用户确认：范围、切片、改动面、验证方法、提交计划。
