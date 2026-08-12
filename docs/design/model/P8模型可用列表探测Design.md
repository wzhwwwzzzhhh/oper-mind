# P8 模型可用列表探测 · Design

> 状态：已确认
> 更新：2026-08-12
> 用户已确认（2026-08-12）：①模型列表现场拉取、不缓存；②响应契约保留 `unsupported` 状态预留（当前不产生）；③枚举无副作用，不写 `verify_status`。
> 关联：`docs/prd/model/P8-model-list-enumeration.md`（已确认 PRD，issue #63）、
> `docs/design/model/P6模型Provider与APIKey管理Design.md`（已确认，本文档在其落地代码上扩展）、
> `docs/prd/model/P6-model-provider-key-management.md`（加密 Key + verify 已落地）、
> `docs/接口清单.md`（第四大模块欠账表：`Provider 下可用模型列表`）、
> `docs/产品定义.md`、`docs/开发规范.md`（凭据纪律、诚实标注）、`docs/架构与开发路径.md`（横切边界）

## 1. 目标与范围

一句话目标：运维在模型设置页新建/编辑 Provider 时，可显式拉取该 Provider 的**可用模型名列表**并选择，减少手填错误；枚举为受控只读探测（限时、脱敏、失败诚实标注），不落库、不伪造。

### 做什么
- 新增枚举能力：对 Provider 已保存的 Base URL + API Key 发起受控只读 `GET /v1/models`（P6 verify 同一端点），解析并返回模型名列表。
- 新增公开接口：`GET /api/v1/model/providers/{provider_id}/models`（无状态只读探测）。
- 前端模型设置页：新建/编辑 Provider 表单提供"刷新模型列表"按钮 + 模型下拉选择；失败/未启用如实展示。
- 更新 `docs/接口清单.md`：补枚举接口行，欠账表 `Provider 下可用模型列表` 由 ❌ 改为 ✅。

### 明确不做（对齐 PRD）
- 不把模型列表缓存/持久化：每次点击现场拉取，不落库、无 TTL 缓存（决策 D3）。
- 不接入非 OpenAI-compatible 枚举协议（Ollama `/api/tags` 等）：首版只做 OpenAI-compatible `GET /v1/models`，类型分支后续加。
- 不改 P6 verify 语义与状态字段；枚举不写 `verify_status`、不产生副作用。
- 不暴露 API Key 明文、完整 Base URL、`sk-`、原始响应体或模型列表之外的字段。

## 2. 设计决策

### D1 · 枚举能力：扩展 P6 只读探测模块，新增 `fetch_provider_models()`

- 在 `backend/src/infrastructure/model_provider_verify.py`（P6 连接验证 Connector）内新增：
  - `fetch_provider_models(base_url: str, api_key: str, *, client=None, timeout_seconds=VERIFY_TIMEOUT_SECONDS) -> ProviderModelsOutcome`
  - **复用** P6 的 SSRF 主机校验（`_check_host_allowed`）、5s 超时、`Authorization: Bearer` 头、脱敏错误分类（TIMEOUT / CONNECTION_FAILED / HTTP_xxx / 地址校验码）。
  - 请求路径与 P6 verify 相同：`{base_url.rstrip('/')}/models`（P6 Base URL 语义已含 `/v1` 前缀，如 `https://api.deepseek.com/v1`，即 PRD 所述 `GET /v1/models`）。
- `ProviderModelsOutcome(status: VerifyStatus, models: list[str] | None, error_code: str | None)`——状态复用 `VerifyStatus`（`ok`/`failed`/`timeout`）。
- **成功解析（HTTP 200）**：按 OpenAI-compatible 标准取 `data[].id` 为模型名；**去重保序、限 100 条、单项超 200 字符丢弃**（受控限长）。响应体只在解析瞬间存在，不落日志/Trace/响应/数据库。
- **非 200**：`failed` + `HTTP_{status}`；超时 `timeout` + `TIMEOUT`；网络异常 `failed` + `CONNECTION_FAILED`。
- **HTTP 200 但解析失败**（响应结构非预期）：诚实 `failed` + `MODELS_PARSE_FAILED`——不伪造列表。
- 实现方式：与 verify 共享一个受控请求私有函数（`_request_provider_models`），verify 只消费状态、枚举消费解析结果；verify 对外语义与状态字段完全不变。

### D2 · 枚举接口契约：GET /api/v1/model/providers/{provider_id}/models

- 无状态只读 GET；权限=本地运维（同既有 Provider 接口）；无 `Idempotency-Key`；Provider 不存在 → 404（`ProviderNotFoundError`，与既有契约一致）。
- 响应（新增 `ModelProviderModelsResponse` schema）：

```json
{
  "provider_id": "<uuid>",
  "status": "ok" | "failed" | "timeout" | "unsupported",
  "models": ["deepseek-chat", "deepseek-reasoner"] | null,
  "error_code": "HTTP_401" | "NO_API_KEY" | ... | null,
  "meta": { "request_id": "..." }
}
```

- `status=ok` 时 `models` 为模型名数组；`failed`/`timeout` 时 `models=null`、`error_code` 为脱敏分类码（复用 P6 错误码集合 + `NO_API_KEY`/`SECRET_KEY_NOT_CONFIGURED`/`KEY_DECRYPT_FAILED` + 新增 `MODELS_PARSE_FAILED`）。
- **`unsupported` 为契约预留状态**：对应 PRD"该 Provider 不支持模型枚举 → 诚实标注不可用/未启用"；首版无 Provider 类型字段、所有 Provider 均尝试 OpenAI-compatible 枚举，**当前不会产生该值**，留给未来非兼容 Provider 类型分支。
- 应用服务新增 `list_models(provider_id) -> ModelProviderModelsData`（domain 层新增跨层模型 `ModelProviderModelsData`，Pydantic 含 status/models/error_code）：读取 Provider → 无 Key / 主密钥缺失 / 解密失败时与 P6 verify 相同诚实分类 → 调用 `fetch_provider_models`。
- **不落库**：枚举不写 `verify_status`/`last_verified_at`，无新增持久化、无迁移（PRD 数据影响声明一致）。

### D3 · 模型列表现场拉取、不缓存（PRD 开放问题 1 拍板）

- **选择**：每次点击现场拉取，无 TTL 缓存、无持久化。
- **理由**：
  1. 枚举由前端显式按钮触发，是运维配置 Provider 时的低频操作，非热路径；
  2. 诚实优先——现场拉取永远反映当下可用性，不出现陈旧列表；
  3. 避免为短时 TTL 引入进程级内存缓存设施（多 worker 不一致、陈旧态、测试复杂度），与 PRD"不把模型列表缓存/持久化"的默认语义一致。
- 前端表单关闭即丢弃枚举结果（临时 UI 状态，`useState`），不写 localStorage。

### D4 · 前端交互：表单内"刷新模型列表"按钮 + 模型下拉

- **新建态与编辑态语义不同**（枚举接口按已保存 `provider_id` 调、凭据取自已保存密文，新建时无 id 可调）：
  - **编辑态**：完整可用——"刷新模型列表"按钮 + 模型下拉 + 三态提示。
  - **新建态**：按钮**禁用**并诚实提示"保存 Provider 后可刷新模型列表"（新建时 Provider 未落库、凭据未加密保存，无法按 provider_id 枚举；PRD 功能需求 2 已同步补充该语义）。保存后进入编辑态即可使用枚举选择，首次值仍可手填。
- 编辑表单的"模型"输入区：输入框旁新增"刷新模型列表"按钮；点击后调用枚举接口，按三态渲染：
  - **ok**：展示模型下拉（≤100 条），选择后填充 `model` 字段；用户仍可手填（下拉为辅助，不强制）。
  - **failed/timeout**：展示脱敏中文原因（错误码映射，见 D5），保留手填。
  - **NO_API_KEY**：提示"未配置 API Key，保存 API Key 后再枚举"（诚实标注未启用）。
- 编辑态：当前 `model` 值若不在下拉列表中，额外提供"当前值（保留）"项，不强制替换。
- 枚举请求进行中按钮禁用并显示加载态；结果不持久化。

### D5 · 错误码 → 前端脱敏文案映射

| error_code | 前端文案 |
|---|---|
| TIMEOUT | 连接超时，请稍后重试 |
| CONNECTION_FAILED | 无法连接 Provider 服务 |
| HTTP_401 / HTTP_403 | 鉴权失败，请检查 API Key |
| HTTP_404 | 服务未返回模型列表，请检查 Base URL |
| 其他 HTTP_xxx | 服务返回 HTTP xxx |
| NO_API_KEY | 未配置 API Key |
| SECRET_KEY_NOT_CONFIGURED | 加密主密钥未配置 |
| KEY_DECRYPT_FAILED | 无法解密已保存的 API Key |
| MODELS_PARSE_FAILED | 服务返回了无法解析的响应 |
| INVALID_URL / DNS_RESOLUTION_FAILED / PRIVATE_ADDRESS_REJECTED | 地址校验失败 |
| 未知 | 枚举失败 |

### 安全与脱敏

- 只读最小请求：仅 `GET {base_url}/models` + Bearer 头；复用 P6 SSRF 主机校验（拒私有/保留段，非 localhost 强制 https 已在 P6 保存校验兜住）。
- 明文 API Key 只在应用服务解密瞬间存在，不落日志/Trace/响应/事件。
- 响应体仅解析模型名，原文不保存、不返回、不进日志；模型名非凭据，正常返回前端展示。
- 单个 Provider 枚举失败不影响其他 Provider（无共享状态）。

### 横切边界核对

| 边界 | 核对 |
|---|---|
| 一条主脊，能力即插件 | 模型枚举是 P6 Provider 管理的自然延伸，非新模式/新流程；确定性 Connector 实现，不经 Agent |
| 工具网关接缝 | 枚举不经 LLM/Agent，是 infrastructure 层受控 Connector，同 P6 verify 纪律 |
| 智能与权力分离 | 只读探测，无动作、无审批链路 |
| 能力即诚实锁 | 失败/超时/未配置如实标注（错误码 + 文案），不伪造模型列表 |
| 凭据纪律 | 明文只在解密瞬间；不进日志/Trace/响应/落库 |
| 跨层数据走 Pydantic | 新增 `ModelProviderModelsData` domain 模型 + schema |

## 3. 文件改动面

### 后端（backend/）
- **修改** `backend/src/infrastructure/model_provider_verify.py` —— 新增 `ProviderModelsOutcome` + `fetch_provider_models()`，与 verify 共享受控请求私有函数。
- **修改** `backend/src/domain/model_provider.py` —— 新增 `ModelProviderModelsData` 跨层模型。
- **修改** `backend/src/application/model_providers.py` —— 新增 `list_models(provider_id)` 应用服务方法（诚实分类 + 解密 + 调用枚举）。
- **修改** `backend/src/api/v1/schemas.py` —— 新增 `ModelProviderModelsResponse`（status/models/error_code）。
- **修改** `backend/src/api/v1/routes.py` —— 新增 `GET /model/providers/{provider_id}/models` 路由。
- **修改** `backend/tests/test_model_provider_api.py` —— 枚举接口用例（ok/failed/timeout/无 Key/404/解析失败）；`backend/tests/test_model_provider_verify.py` —— `fetch_provider_models` 单测（httpx MockTransport：解析/去重限长/非 200/超时）。

### 前端（frontend/）
- **修改** `frontend/src/features/models/ModelSettingsPage.tsx` —— 表单加"刷新模型列表"按钮 + 模型下拉 + 三态提示。
- **修改** `frontend/src/api/v1/queries.ts` —— 新增枚举 query；`generated.ts` 由 `npm run generate:api` 重新生成（禁手改）。
- **修改** `frontend/src/features/models/ModelSettingsPage.test.tsx` —— MSW mock 三态用例。

### 文档
- **修改** `docs/接口清单.md` —— Provider 表新增枚举接口行；欠账表 `Provider 下可用模型列表` 标 ✅。

### 无功能改动部分
- 会话链路、LLM 客户端、Trace、Agent 网关、迁移、凭据存储（`model_providers` 表结构不变）。

## 4. 切片与验证（指引，不写死）

> Design 只给改动单元的验收语义；正式切片拆解、验证命令与提交计划归 `dev-plan` 的 `plan.md`。

建议拆 **2 个独立可验收单元**：
- **U1 后端枚举接口**：`fetch_provider_models` + domain/应用服务 + 路由/schema + 后端测试。验收语义：可连通→模型名列表（去重限长）；失败/超时→脱敏状态码不暴露响应体；无 Key/主密钥缺失/解密失败→诚实分类；404；解析失败→诚实 failed（AC1/AC2/AC3/AC4/AC6/AC7）。门禁：真实连接（复用 P6 verify 已批准的同端点只读模式）。
- **U2 前端交互 + 文档**：按钮/下拉/三态 + MSW 测试 + 接口清单更新。验收语义：成功展示下拉可选、失败展示脱敏原因、未配置展示"未启用"（AC5）+ AC8 回归。

## 5. 风险、回滚与门禁

| 风险 | 缓解 |
|---|---|
| 模型响应格式非标准（`data[].id` 缺失） | 诚实 `failed` + `MODELS_PARSE_FAILED`，不伪造列表 |
| 响应体过大 | 列表限 100 条、单项限 200 字符、去重保序 |
| 枚举被滥用（SSRF） | 复用 P6 主机校验与超时，无新增网络面 |
| 枚举慢影响表单体验 | 按钮显式触发 + 加载态 + 5s 超时 |
| 手填习惯被打断 | 下拉为辅助不强制，手填始终可用；编辑态保留当前值 |

- **回滚**：移除枚举路由注册 + 新增 schema/domain 模型/应用服务方法/`fetch_provider_models`；无迁移、无既有接口契约破坏、无凭据变更。回滚即恢复现状（P6 行为不变）。
- **门禁项清单**：新增公开 API（`GET /model/providers/{provider_id}/models`）；真实连接（复用 P6 verify 已批准的同端点只读模式）。无迁移、无新凭据、无破坏性改动。

## 6. 待用户确认的设计决策

1. **模型列表现场拉取、不缓存**（PRD 开放问题 1 拍板为"现场拉取"而非"短时 TTL 缓存"）：理由——枚举由显式按钮触发属低频操作、诚实优先（列表永远反映当下）、避免为 TTL 引入缓存设施与陈旧态。
2. **响应契约含 `unsupported` 状态预留**（当前不产生，为未来非 OpenAI-compatible Provider 类型分支的诚实通道；同时落实 PRD 开放问题 2"首版只做 OpenAI-compatible"）。
3. **枚举不写 `verify_status`、无副作用**（PRD"不落库"语义下，枚举与 verify 状态解耦；verify 语义保持不变）。
