# P4.3-model-settings-real · 工作包计划

> PRD：`docs/prd/model/P4.3-model-settings-real.md`（已确认）
> 当前门禁：新增公开只读 API 的响应路径与结构属于 PRD 开放问题，需本计划经用户确认后才能进入实现。

## 范围

### 只做
- AC1–AC4：新增 `GET /api/v1/model/config`，读取 `load_config()` 当前生效配置并返回安全视图；只返回诊断模型、可选裁判模型、Provider、URL 主机、模型名和 `mock/real` 模式，不返回 API Key、完整含凭据 URL、密码或 DSN。
- AC3：裁判模型未配置时返回 `null`（前端显示“未配置”）；不从诊断模型复制或推断裁判模型。
- AC5–AC6：模型设置页挂载时读取接口，移除 Provider/模型静态示例作为真实配置来源；接口错误显示错误状态，不回退静态假数据。
- AC7：添加模型服务、测试连接、刷新模型列表等未实现能力继续保持禁用或诚实提示。
- AC8：补充后端 API 测试、前端客户端/页面交互测试，并完成前端契约生成与回归验证。

### 明确不做
- 不新增 API Key 输入、保存、编辑、落库或前端状态持久化。
- 不新增 Provider 编辑、删除、连接测试、模型自动发现或外部网络调用。
- 不将 Coordinator/DB/Server/Log 等 Agent 策略开关真实化；继续作为本地 UI 偏好。
- 不修改 `load_config()` 的加载、校验和环境变量覆盖逻辑。
- 不做数据库迁移，不改 Connector、服务接入、权限、审批或执行能力。
- 不修改与本工作包无关的既有用户/其他 Agent 改动。

## 安全响应契约

- 路径：`GET /api/v1/model/config`。
- 响应：v1 既有资源响应风格的顶层 `meta` 加 `config` 资源，资源字段为 `mode`、`diagnostic_model`、`judge_model`。
- 模型资源字段：`provider`、`base_url_host`、`model`、`status`；`judge_model` 未配置时为 `null`。
- `base_url_host` 只保留 URL 主机名，不返回完整 URL、路径、查询参数或凭据；该字段仅为本次用户确认的模型设置安全视图展示字段，不构成其他接口的通用连接细节展示规则；`api_key` 永不进入响应模型。
- `status` 只表示 `configured` / `not_configured`，不冒充真实连接测试结果。

## 切片拆分

- [x] S1：安全配置视图、v1 响应契约和后端 API 测试，覆盖 AC1–AC4。
- [x] S2：前端 API client/query、OpenAPI 生成类型和模型设置页真实配置/错误态，覆盖 AC5–AC7。
- [x] S3：后端全量、前端 `typecheck`/`test`/`build` 与敏感信息和 diff 门禁，覆盖 AC8。

## 改动面（文件级）

- `backend/src/api/v1/schemas.py`：新增模型配置安全响应模型。
- `backend/src/api/v1/routes.py`：新增只读模型配置路由及安全映射函数。
- `backend/tests/test_model_config_api.py`：新增 mock/env 配置场景和凭据泄露断言。
- `frontend/src/api/v1/client.ts`：增加模型配置类型和 GET client 方法。
- `frontend/src/api/v1/queries.ts`：增加模型配置 query。
- `frontend/src/features/models/ModelSettingsPage.tsx`：读取真实配置、未配置态和错误态，保留本地偏好与未接入能力提示。
- `frontend/src/features/models/ModelSettingsPage.test.tsx`：新增挂载成功、未配置、接口失败和禁用能力交互测试。
- `frontend/src/api/v1/generated.ts`：仅通过 `npm run generate:api` 更新，禁止手工编辑。
- 无数据库迁移、无配置机制改动、无凭据方案改动。

## 验证方法

- 后端：从 `backend/` 执行 `..\.venv\Scripts\python.exe -m pytest tests/test_model_config_api.py -q`，再执行 `..\.venv\Scripts\python.exe -m pytest tests -q`。
- 前端：从 `frontend/` 执行 `npm run generate:api`、`npm run typecheck`、`npm run test`、`npm run build`。
- 门禁：`git diff --check`；检查响应、日志、测试输出和改动文件不含 API Key、`sk-`、密码或 DSN。

## 提交计划

- `feat: P4.3 暴露模型真实生效配置安全视图`
- `feat: P4.3 模型设置页读取真实配置并显示错误态`
- `test: P4.3 补齐模型设置回归验证`
