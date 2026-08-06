# P6 模型 Provider 与 API Key 管理 · Design

> 状态：已确认
> 更新：2026-08-06
> 关联：`docs/prd/model/P6-model-provider-key-management.md`（已确认 PRD，issue #22）、
> `docs/prd/model/P4.3-model-settings-real.md`（只读展示，本设计在其上扩展）、
> `docs/design/service-center/P4.4服务中心接入与凭据Design.md`（凭据方案 A/B 边界，本文档启用其方案 B 边界）、
> `docs/产品定义.md`、`docs/路线图.md`（第四阶段）、`docs/开发规范.md`（凭据只走环境变量）、
> `docs/架构与开发路径.md`、`docs/正式产品架构设计-v1.md`
> 用户已确认（2026-08-06）：①批准 API Key 加密落库（放宽「凭据不落库」硬规则）；②DB 激活配置优先于 env/YAML；③Provider 范围任意 OpenAI-compatible；④API Key 掩码 = `••••` + 末 4 位。

## 1. 目标与范围

一句话目标：运维在模型设置页**配置/切换模型 Provider（Base URL / 模型 / API Key）**，API Key **加密后安全持久化**、绝不落明文/日志/Trace/响应，保存时可**受控验证连通**，配置变更后**会话链路即时使用生效配置**（诊断/裁判模型），mock/real 如实标注。

### 做什么
- 模型 Provider 配置的持久化与读写：新增/编辑/删除 Provider（名称 / Base URL / 模型），API Key 加密存储。
- Provider 激活为生效配置（诊断 / 裁判端点），会话链路使用生效配置（DB 激活优先，env/YAML 兜底）。
- 连接验证：保存时受控、限时验证 Provider 连通，失败诚实标注（不暴露响应体/凭据）。
- API Key 掩码展示、永不回显明文；只读安全视图保持 P4.3 契约兼容。
- 涉及数据库迁移（新增 `model_providers` 表）与新增公开 API。

### 明确不做
- 不做多租户 / 多用户的模型权限管理（PRD 排除）。
- 不做模型列表自动发现（Ollama 等 Provider 的模型枚举；PRD 排除）。
- 不做 Agent 调用策略开关的真实化（沿用 P4.3 结论，保留前端本地偏好或只读）。
- **不改 `load_config()` 内部实现**（env 优先 YAML 的既有逻辑）；模型端点**生效配置由 DB 激活的 Provider 承担**，未激活时 env/YAML 兜底（PRD 排除项已按本设计同步放宽，见 PRD 更新）。
- 不接外部密钥服务（Vault 等；PRD 排除）。

## 2. 设计决策

### D1 · API Key 持久化：加密落库（启用 P4.4 方案 B 边界）

- **选择**：API Key 用 **AES-256-GCM** 加密后写入应用库专用表 `model_providers` 的 `api_key_encrypted` 字段；**主密钥来自环境变量 `OPERMIND_SECRET_KEY`**，绝不落库/落代码/进日志。
- **为什么**：PRD 要求"前端输入 API Key 并安全持久化"，而外部密钥服务（Vault）被 PRD 排除、纯环境变量（P4.4 方案 A）无法满足"前端输入"。因此唯一可行路径是**加密落库**——这需要用户批准把"凭据不落库"硬规则放宽为"**明文永不落库、密文可落专用表**"（P4.4 已把该边界预留为方案 B，本次正式启用；用户 2026-08-06 已拍板，见 §6 决策 1）。
- **加密方案**：
  - 密钥派生：`OPERMIND_SECRET_KEY`（最小长度 32 字符，短于则启动时告警并禁止保存 Key）→ 32 字节密钥，经 HKDF-SHA256 派生（`cryptography` 库）。
  - 每条记录独立随机 12 字节 nonce；密文 + nonce 以 Base64 存入 `model_providers`。**API Key 输入设最小长度校验（≥8）**，避免极短 Key 被掩码规则完整暴露。
  - 新增依赖 `cryptography`（纯本地对称加密，无网络）。
  - 主密钥丢失即密文不可解：诚实降级为未配置，并提供备份/删除重配提示。
- **诚实降级**：`OPERMIND_SECRET_KEY` 未设置时，**禁止保存 API Key**（返回"加密主密钥未配置"），Provider 元数据（名称/Base URL/模型）仍可保存，API Key 置为未配置——不伪造、不落明文。
- **回读**：接口/前端**永不返回明文**；仅返回 `has_api_key` 布尔与掩码 `•••• + 末 4 位`（用户已确认，帮助运维识别是哪把 Key，不构成可用凭据）。掩码仅出现在 dedicated 只读接口，**绝不进日志/Trace/事件/前端持久化（localStorage 等）**。

### D2 · 配置生效：运行时解析覆盖层，保存即生效（无需重启）

- **不改 `load_config()` / env-over-YAML 机制**（PRD 明确不做，本设计只在其上层叠加）。新增**独立的生效配置解析层** `resolve_model_config()`：
  - 解析顺序：**DB 中已激活的 Provider（诊断/裁判端点）→ 若无激活配置，回退 `load_config()`（env/YAML 现状）**。
  - 即 **DB 激活配置优先于 env/YAML**（用户 2026-08-06 拍板）；仅当 DB 未激活该端点时才兜底现有机制。PRD 排除项已同步放宽并注明。
- **生效点**：LLM 客户端（`LLMClient`）构造处 `build_llm()` 改用 `resolve_model_config()`。为避免进程级共享单例的并发副作用，**每个 Run 构建 Coordinator 时解析并构造 LLM 客户端**（`app.py` 由 `_shared_llm` 单例改为每 Run 构造；LLM 客户端构造无网络副作用，成本低），与现有"每 Run `build_coordinator`"的并发隔离一致。配置保存/激活/删除后**下一次 Run 即生效，无需重启进程**。
- **mock/real 如实标注**：生效配置无 API Key（或 `OPERMIND_API_KEY=mock`）→ `mode=mock`，会话链路走确定性 mock 场景；有真实 Key → `mode=real`。`resolve_model_config()` 在 LLM 构造点**永不 raise**——未配置时返回诚实空态（mock），不抛错。`GET /api/v1/model/config` 语义不变，只读安全视图沿用 P4.3 结构。

### D3 · Provider 列表范围：任意 OpenAI-compatible Base URL，无硬编码白名单

- PRD 排除模型自动发现，且不要求白名单。**允许运维自由输入 Base URL + 模型名**（OpenAI-compatible /chat/completions 语义），保证灵活。
- **校验（防 SSRF）**：URL 必须 `http(s)`；**主机解析校验**——`localhost` / `127.0.0.1` 放行（本地 Provider，如 Ollama），其余主机**拒绝 loopback / 私有 / 链路本地 / 保留地址段**；非 localhost 强制 `https`；Base URL / 模型名非空；所有保存参数化校验，超时默认 5s。
- 常见 Provider（DeepSeek / OpenAI 等）仅作前端**快捷提示**，非强制白名单。

### D4 · 连接验证：受控最小只读请求

- 验证走**确定性受控 Connector**（不是任意 Tool/Agent），只发**最小验证请求**：OpenAI-compatible 的只读 `models.list`（或等价最小探测），不产生 token 消耗、不执行任意调用。
- **限时** 5s；失败/超时**诚实标注脱敏原因**（错误分类码 + 安全摘要），不暴露响应体、完整 URL、凭据。
- 验证结果落 `model_providers` 的脱敏状态字段（`verify_status` / `last_verified_at` / `verify_error_code`），前端展示诚实空态/失败态；一个 Provider 不可用不影响其他 Provider。

### 接口契约（新增公开 API，均走既有 v1 网关，权限=本地运维；错误码统一并入既有 `APPLICATION_ERROR_STATUS` 映射模式）

| 方法 | 路径 | 行为 | 脱敏要求 |
|---|---|---|---|
| GET | `/api/v1/model/providers` | 列 Provider 安全视图（含掩码/`has_api_key`/验证状态） | 无明文 Key |
| POST | `/api/v1/model/providers` | 新增 Provider（name/base_url/model/api_key）；**要求 `Idempotency-Key`**；SSRF/URL 校验失败 → 422 | 入参 Key 仅加密落库，不入响应/日志 |
| PUT | `/api/v1/model/providers/{id}` | 编辑 Provider（api_key 不传=不改，显式空串=清空该 Key）；不存在 → 404 | 同上 |
| POST | `/api/v1/model/providers/{id}/verify` | 触发连接验证；请求体 `{"endpoint"?: "diagnostic"\|"judge"}` 可选；不存在 → 404 | 结果脱敏 |
| POST | `/api/v1/model/providers/{id}/activate` | 激活为生效配置；请求体 **`{"endpoint": "diagnostic"\|"judge"}`**（单事务原子替换去旧置新）；不存在 → 404，并发冲突 → 409 | 无 |
| DELETE | `/api/v1/model/providers/{id}` | 删除 Provider（若为激活配置，删除后该端点回退 env/YAML 兜底，诚实空态）；不存在 → 404 | 无 |

- `GET /api/v1/model/config`（P4.3）**保持契约兼容**，改为读取 `resolve_model_config()` 解析后的生效配置。
- 前端 API 类型由 `npm run generate:api` 生成（`frontend/src/api/v1/generated.ts`），禁止手改。

### 数据模型（涉及迁移）

新增 `model_providers` 表（应用库）：
- `id` (UUID, PK)、`name` (str)、`base_url` (str)、`model` (str)
- `api_key_encrypted` (str, 可空)、`api_key_nonce` (str, 可空) —— 密文 + nonce，Base64；**无明文 Key 字段**
- `active_endpoint` (str, 可空：`diagnostic` / `judge` / `None`；唯一约束一端点一激活，切换由 activate 单事务原子替换保证）
- `verify_status` (str, 可空：`unknown`/`ok`/`failed`/`timeout`)、`last_verified_at` (datetime, 可空)、`verify_error_code` (str, 可空)
- `created_at` / `updated_at`
- 迁移：`backend/migrations/` 新增 alembic revision（upgrade/downgrade）。

## 3. 文件改动面

### 后端（backend/）
- **新增** `backend/src/infrastructure/secrets.py` —— AES-256-GCM 加密/解密封装，密钥派生自 `OPERMIND_SECRET_KEY`（含最小长度校验）；公开函数带类型标注，禁裸 `except`、禁打印。
- **新增** `backend/src/application/model_providers.py` —— Provider 读写/验证/激活的应用服务 + **`resolve_model_config()` 生效配置解析层**（显式注入"激活 Provider 读取器"port：repository / session_factory；**不放在 config.py**，避免层级倒挂与迁移 env.py 循环导入）。
- **新增** `backend/src/infrastructure/persistence/model_provider_repository.py` —— `ModelProviderRecord` 的 ORM 仓库（读写 + 激活原子替换）。
- **修改** `backend/src/infrastructure/persistence/models.py` —— 新增 `ModelProviderRecord`。
- **新增** `backend/migrations/` revision —— 建 `model_providers` 表（upgrade/downgrade）。
- **修改** `backend/src/config.py` —— 仅新增 `OPERMIND_SECRET_KEY` 读取与校验（含最小长度）；**不改 `load_config()` 既有逻辑**。
- **修改** `backend/src/core/bootstrap.py` / `app.py` —— `build_llm()` 改用 `resolve_model_config()`；`app.py` 由 `_shared_llm` 单例改为**每 Run 构造 LLM**（`_service_mode()`/`/health` 等对 `_shared_llm` 的既有引用一并改读 `resolve_model_config()` 或 env 兜底，装配经 `app.state.v1_services`/`get_v1_services` 注入，避免健康探针每查库/空指针；旧 `build_system()` 入口同样跟随生效配置，`resolve_model_config()` 永不 raise）。解析层经**显式 port 注入**（含 `build_llm → resolve_model_config` 的工厂在 `build_v1_services_for_runtime` 内构造，或注入 session_factory/repository）。
- **修改** `backend/src/api/v1/routes.py` + `schemas.py` —— 新增 Provider CRUD/verify/activate 接口；`GET /model/config` 改读解析层。
- **修改** `backend/requirements.txt` —— 新增 `cryptography`。
- **修改** `config/config.example.yaml` —— 文档化 `OPERMIND_SECRET_KEY`（含最小长度与备份提示）。
- **新增** `backend/tests/test_model_provider_api.py`、`backend/tests/test_secrets.py`；**修改** `backend/tests/test_model_config_api.py`（回归兼容）与 `backend/tests/test_api.py`（其中 `_shared_llm` fixture 改走 env/`resolve_model_config()` 兜底）。

### 前端（frontend/）
- **修改** `frontend/src/features/models/ModelSettingsPage.tsx` —— Provider 区替换为真实配置 CRUD（掩码展示、保存、验证、激活、删除）；"Agent 调用策略本地偏好"区保持不动。
- **修改** `frontend/src/api/v1/queries.ts`；`generated.ts` 由 `npm run generate:api` 生成。
- **新增/修改** 前端交互测试（`ModelSettingsPage.test.tsx`，MSW mock）。

### 无功能改动部分
- Agent 调用策略、会话链路其他部分、Trace 展示逻辑（本设计不含凭据展示路径）。

## 4. 可独立验收的改动单元（指引，不写死）

> Design 只给改动单元的验收语义；正式切片拆解、验证命令与提交计划归 `dev-plan` 的 `plan.md`。

建议拆 **3 个独立可验收单元**：
- **U1 加密持久化 + Provider 读写/激活 API**：加密模块 + `model_providers` 表迁移 + CRUD/activate 接口 + 脱敏/掩码。验收语义：保存不落明文、回读无明文、无 Key 时诚实空态（AC1/AC2/AC9 主战场）。门禁：迁移 + 凭据 + 公开 API。
- **U2 连接验证**：verify 接口，受控最小请求、限时、脱敏错误（含 SSRF 主机校验）。验收语义：可连通→成功；失败/超时→脱敏失败态（AC3/AC4）。门禁：真实连接（对外部服务发最小请求）。
- **U3 配置生效贯通 + 前端**：`resolve_model_config()` + `build_llm`/`app.py` 每 Run 构造 + `GET /model/config` 兼容 + 前端 CRUD/掩码展示 + 回归（AC5–AC8）。门禁：回归全绿。

## 5. 风险、回滚与门禁

| 风险 | 缓解 |
|---|---|
| 主密钥丢失 → 已存 Key 不可解 | 诚实提示运维备份/删除重配；密文不可解时 Provider 降级为未配置，不崩 |
| 主密钥泄漏 → 全量可解 | 主密钥只走 `OPERMIND_SECRET_KEY` 环境变量（≥32 字符），日志/文档禁打；权限最小化 |
| verify 被滥用（SSRF） | Base URL 主机解析校验（拒私有/保留段，非 localhost 强制 https）、只发最小只读请求、5s 超时、结果脱敏 |
| 引入加密依赖 | `cryptography` 纯本地、无网络、可审计；锁定版本 |
| DB 激活配置优先级改变运维习惯 | 用户 2026-08-06 已拍板；env/YAML 兜底不变；PRD 排除项已双写放宽 |
| 进程级 LLM 单例并发副作用 | 改为每 Run 构造 LLM，消除全局可变状态；mock 场景每 Run 按现有 `build_llm` 逻辑设置 |

- **回滚**：移除新增 routes 注册 + 回滚 `model_providers` 迁移；`GET /model/config` 回退 `load_config()` 现状；`build_llm`/`app.py` 回退直接 `load_config()` 与 `_shared_llm` 单例。无既有接口契约破坏。
- **门禁项清单**：数据库迁移（`model_providers`）、新增公开 API（Provider CRUD/verify/activate）、凭据（加密落库，用户已批准放宽"不落库"）、真实连接（verify 最小请求 + SSRF 校验）。

## 6. 设计决策（用户已确认，2026-08-06）

1. **批准「凭据不落库」硬规则放宽为「API Key AES-256-GCM 加密后落应用库专用表」**，主密钥 `OPERMIND_SECRET_KEY` 走环境变量（≥32 字符）；明文仍绝对禁止。代价：主密钥泄漏=全量可解，需运维妥善保管。**用户已确认**。（PRD 开放问题 1）
2. **DB 激活的 Provider 配置优先于 env/YAML**（仅 DB 未激活该端点时兜底），保存即生效、无需重启；mock/real 如实标注。**用户已确认**。（PRD 开放问题 2，PRD 排除项已同步放宽）
3. **Provider 范围接受任意 OpenAI-compatible Base URL**（自由输入 + http(s) 与主机解析校验，非 localhost 强制 https，拒私有/保留段），不做硬编码白名单；常见 Provider 仅 UI 提示。**用户已确认**。（PRD 开放问题 3）
4. **API Key 掩码展示规则**：界面仅显示 `•••• + 末 4 位`，接口永不返回明文，掩码不进日志/Trace/事件/前端持久化。**用户已确认**。（AC1/AC2 实现细节）
