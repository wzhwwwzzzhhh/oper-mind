# P8 模型调用参数暴露 · Design

> 状态：已确认
> 更新：2026-08-12
> 用户已确认（2026-08-12）：①temperature + max_tokens；②全局作用域；③graph.py/debate.py 三处显式 0.0 保留；④mock 展示并标注仅 real 生效。
> 关联：`docs/prd/model/P8-model-params-config.md`（已确认 PRD，issue #66）、
> `docs/prd/model/P8-model-mode-switch.md`（同批 P8，运行时模式切换，app_settings 先例）、
> `docs/design/model/P6模型Provider与APIKey管理Design.md`（已确认，Provider/生效配置解析层）、
> `docs/产品定义.md`、`docs/路线图.md`、`docs/开发规范.md`、
> `backend/src/core/llm.py`、`backend/src/core/graph.py`、`backend/src/core/debate.py`、
> `backend/src/api/v1/dependencies.py`、`backend/src/application/model_mode.py`

## 1. 目标与范围

一句话目标：运维在模型设置页配置 **temperature / max_tokens**，持久化到应用库，会话链路构造 LLM 时读取并**真实进入调用链**（非 localStorage 假状态），未配置时用后端默认值。

### 做什么
- 参数持久化：应用库 `app_settings` 键值（对齐 `model.runtime_mode` 既有先例），**无新迁移**（`app_settings` 表已在 P8 模式切换迁移中建好）。
- 生效链路：LLM 构造点解析参数并注入 `LLMClient` 实例默认，`chat()` 的 `temperature` 默认值从写死 0.0 改为「实例默认」，未配置仍为 0.0；新增 `max_tokens` 支持，未配置不传。
- 读写接口：`GET /model/config` 契约兼容扩展（追加 params 字段）；新增 `PUT /model/params` 写接口。
- 诚实标注：未配置显示默认值并标注；mock 模式正常展示配置但标注「仅 real 调用生效」。

### 明确不做
- 不做未进 `chat()` 的参数暴露（`top_p` / `frequency_penalty` 等，PRD 排除）。
- 不做按 Provider / 按 Agent 的参数作用域（首版全局，PRD 排除作用域矩阵）。
- 不复活 localStorage 假开关（PRD 排除，`完善清单.md` P1-7 已删）。
- 不新增环境变量兜底（参数唯一来源 app_settings；env/YAML 无参数键，未配置即默认值）。
- 不改 mock 路径行为（`_mock_chat` 不读参数，天然满足 AC8）。
- 不改 `resolve_runtime_mode` / `resolve_model_config` 既有契约（参数解析为**同层独立**解析层）。

## 2. 设计决策

### D1 · 参数范围：temperature + max_tokens（都进 `chat()`）

- `temperature` ∈ **[0, 2]**（float），未配置 → 默认 **0.0**（保持现状，实验可复现语义不变）。
- `max_tokens` ∈ **[1, 102400]**（int，OpenAI 公开文档上限），未配置 → **不传 SDK**（`None`，用模型自身默认）。
- `chat()` 签名扩展：`temperature: float | None = None`（None → 实例默认）、`max_tokens: int | None = None`（None → 不传）。既有显式传参调用点全部兼容。
- 校验失败 → 422（并入既有 `APPLICATION_ERROR_STATUS` 映射模式），不产生半状态。

### D2 · 作用域：全局（app_settings 单键），非按 Provider

- 键 `model.params`，值 JSON 字符串 `{"temperature": 0.5, "max_tokens": 4096}`（字段缺省即未配置）。
- 读取：应用库不可用 / JSON 解析失败 → **诚实降级为未配置**（返回默认值），永不 raise（对齐 `resolve_runtime_mode` 的降级纪律）。
- 写入：`in_transaction` 单键 upsert（对齐 `SqlAlchemyAppSettingsRepository.set`），一次写入两项原子生效；持久化失败 → 返回错误不产生半状态。
- 为什么全局：PRD 推荐全局（简单），按 Provider 需要扩展 `model_providers` 表 + 激活 Provider 关联参数，首版不做；且用户故事是「调整**诊断模型**的 temperature」——诊断模型即生效配置的诊断端点，全局参数覆盖它。

### D3 · 生效链路：LLM 构造点注入实例默认，显式传参处保持不动

- **注入点**：`dependencies.py` 的 `_resolved_coordinator_factory`（v1 主链路，每 Run 解析）中解析参数，经 `build_llm_from_config(config, params=...)` 传入；`LLMClient` 新增 `default_temperature: float = 0.0` / `default_max_tokens: int | None = None` 实例字段。
- **解析层**：新增 `resolve_model_params(session_factory) -> ModelParamsResolution`（应用层，复用 `SqlAlchemyAppSettingsRepository`），与 `resolve_runtime_mode` 同层独立；永不 raise，返回已配置值 + 默认值（诚实标注用）。
- **显式传参处保持不动**（PRD 功能需求 2 交 Design 定）：`graph.py:158`（路由决策）、`graph.py:269`（分歧检测）、`debate.py:77`（辩论裁决）继续显式传 `temperature=0.0`。理由：这三个节点是**结构化决策**（路由策略 / 分歧判断 / 裁决），0.0 确定性是诊断质量骨架的**特性**而非缺陷——降低随机性诉求针对的是**内容生成**。
- **参数生效面（走实例默认、会被配置覆盖的调用）**：各领域 Agent 的诊断分析（agent.py）、Reflection 质检反馈（reflection.py）、报告初稿与修订（graph.py 报告节点）；**保持显式 0.0 的调用**仅路由决策 / 分歧检测 / 辩论裁决三处。前端文案按此精确标注。
- **旧入口**：`build_llm()` / `build_system()`（旧 /diagnose 入口）不注入参数，保持现状（默认 0.0）；产品主入口是 v1 会话链路，参数在其上生效。
- **装配方向**：bootstrap 的 `build_llm_from_config` 只收结构化 params（普通数据，无基础设施依赖），应用层解析 app_settings 后传入——依赖方向不变（core 不依赖基础设施）。

### D4 · 接口契约（新增公开 API，走既有 v1 网关，权限=本地运维；错误码并入既有映射模式）

| 方法 | 路径 | 行为 | 脱敏要求 |
|---|---|---|---|
| PUT | `/api/v1/model/params` | 全量替换参数：`{"temperature": 0.5 \| null, "max_tokens": 4096 \| null}`；**null=清除该项**（恢复默认），两项皆 null=清空；幂等（同值重复写结果相同，无需 Idempotency-Key，对齐 `PUT /model/mode` 先例）；校验失败 → 422；响应返回更新后的完整 `ModelConfigResponse`（对齐 `PUT /model/mode` 行为） | 无凭据 |
| GET | `/api/v1/model/config`（既有） | **契约兼容扩展**：`ModelConfigResource` 追加 `params`（已配置值，未配置为 null）与 `params_defaults`（后端默认值）字段；旧前端忽略新字段，兼容 | 无凭据 |

- 参数响应不含任何凭据字段（参数与 API Key / DSN 无关，AC6 天然满足）。
- 前端 API 类型由 `npm run generate:api` 生成（`frontend/src/api/v1/generated.ts`），禁止手改。

### D5 · mock 模式：正常展示配置并标注「仅 real 生效」

- 参数持久化与展示**不区分模式**（mock 与 real 同一份配置，切换模式参数保留）。
- `_mock_chat` 路径不读参数（AC8：mock 行为不变）。
- 前端参数区标注「mock 模式下参数不生效，仅 real 调用按此参数执行」——不隐藏配置（用户可先配好再切 real），如实标注（PRD 开放问题 3 按推荐方案定）。

### 数据模型（无迁移）

`app_settings` 表（已存在）新增键 `model.params`，值 JSON 字符串；无需新迁移、无新表。

### 配置契约

- 参数**不引入新环境变量**：`OPERMIND_*` 只覆盖 api_key/base_url/model（现状不变）；参数唯一来源是 app_settings，未配置 → 后端默认（temperature 0.0 / max_tokens 不传）。诚实标注来源：`params` 已配置值 + `params_defaults` 默认值，前端区分展示。

## 3. 文件改动面

### 后端（backend/）
- **新增** `backend/src/domain/model_params.py` —— `MODEL_PARAMS_KEY` 常量、`ModelParams` Pydantic（temperature/max_tokens 校验：∈[0,2]、∈[1,102400]）、`ModelParamsResolution` TypedDict（已配置值 + 默认值）、JSON 编解码 helper（解析失败诚实降级）。
- **新增** `backend/src/application/model_params.py` —— `ModelParamsApplicationService`（get / set，set 用 `in_transaction` upsert；持久化失败抛既有错误类型）+ `resolve_model_params(session_factory)`（永不 raise，应用库不可用 → 未配置默认）。
- **修改** `backend/src/core/llm.py` —— `chat()` 加 `temperature: float | None = None`（None → 实例默认）与 `max_tokens: int | None = None`（None → 不传 SDK）；`LLMClient.__init__` 加 `default_temperature` / `default_max_tokens` 实例字段；mock 路径不动。
- **修改** `backend/src/core/bootstrap.py` —— `build_llm_from_config(config, params=None)` 透传实例默认。
- **修改** `backend/src/api/v1/dependencies.py` —— `_resolved_coordinator_factory` 中解析 `resolve_model_params` 并传入构造。
- **修改** `backend/src/api/v1/schemas.py` —— 新增 `ModelParamsResource`、`UpdateModelParamsRequest`；`ModelConfigResource` 追加 `params` / `params_defaults`。
- **修改** `backend/src/api/v1/routes.py` —— 新增 `PUT /model/params`；`_model_config_resource` 补 params 字段。
- **新增** `backend/tests/test_model_params_api.py`；**新增** `backend/tests/test_llm_client.py`（LLMClient 默认参数单测）；**修改** `backend/tests/test_model_config_api.py`（回归兼容）。

### 前端（frontend/）
- **修改** `frontend/src/features/models/ModelSettingsPage.tsx` —— 「运行模式」下方新增「运行参数」section：temperature（数字输入 0–2）、max_tokens（数字输入 ≥1 可空）表单 + 保存按钮；展示已配置值 / 默认值标注；mock 模式标注「仅 real 生效」。
- **修改** `frontend/src/api/v1/client.ts`、`frontend/src/api/v1/queries.ts`；`generated.ts` 由 `npm run generate:api` 重新生成。
- **修改** `frontend/src/features/models/ModelSettingsPage.test.tsx`（MSW 参数接口 handler + 交互测试）、对应 CSS。

### 无功能改动部分
- 会话链路其他部分、Trace 展示、Provider CRUD/verify/activate/枚举接口、服务中心（本设计不含这些路径）。

## 4. 切片与验证（指引，不写死）

> Design 只给改动单元的验收语义；正式切片拆解、验证命令与提交计划归 `dev-plan` 的 `plan.md`。

建议拆 **3 个独立可验收单元**：
- **U1 参数持久化 + 解析层 + 读写 API**：domain 校验 + app_settings 键值读写 + `resolve_model_params` 降级 + `PUT /model/params` + `GET /model/config` 扩展。验收语义：保存/清除/校验失败/应用库不可用诚实降级（AC3/AC4/AC5/AC6）。
- **U2 生效链路**：`LLMClient` 实例默认 + `chat()` 参数扩展 + factory 注入。验收语义：配置后主链路调用传新值、未配置仍 0.0、显式传参处（graph/debate）不变、mock 路径不变（AC1/AC2/AC8）。
- **U3 前端参数表单**：表单 + 保存 + 诚实标注 + mock 标注 + 回归。验收语义：页面展示 = 后端值，未配置显示默认（AC5/AC7/AC9）。

## 5. 风险、回滚与门禁

| 风险 | 缓解 |
|---|---|
| max_tokens 超具体模型上限被 SDK 拒 | 仅校验公开文档上限（≤102400）与 ≥1；具体模型更低上限由 SDK 拒绝时如实报错，不伪造成功 |
| 配置只覆盖部分调用，运维误以为全链路生效 | 前端文案如实标注生效面：内容生成（Agent 分析 / Reflection 质检 / 报告）按此参数，路由 / 分歧 / 辩论裁决保持确定性 0.0 |
| JSON 解析/应用库异常影响链路 | 解析层永不 raise，诚实降级为默认值（对齐 runtime_mode 纪律） |
| 参数写入并发覆盖 | 单键单事务原子写入，全量替换语义无部分状态 |

- **回滚**：移除 `PUT /model/params` 路由注册 + `chat()` 参数扩展还原 + 前端表单移除 + app_settings 键删除；**无迁移、无新表**，回滚即移除新增注册，无既有契约破坏（`GET /model/config` 扩展字段为追加，回滚删字段旧前端不受影响）。
- **门禁项清单**：新增公开 API（`PUT /model/params`；`GET /model/config` 扩展字段）；无迁移、无新凭据、无新真实连接、无 mock 行为变化。

## 6. 待用户确认的设计决策

1. **参数范围**：首版 temperature + max_tokens 都进 `chat()`（max_tokens 未配置不传 SDK，用模型默认）。→ 对齐 PRD 开放问题 1 推荐。
2. **作用域**：全局生效（app_settings 单键 `model.params`），非按 Provider；无新迁移。→ 对齐 PRD 开放问题 2 推荐。
3. **显式传参处保持不动**：`graph.py` 两处 + `debate.py` 一处继续显式 `temperature=0.0`，配置仅覆盖诊断内容生成调用（各 Agent 分析与报告）；前端如实标注。→ PRD 功能需求 2 交 Design 定的点。
4. **mock 标注**：mock/real 共用同一份参数配置（切换模式参数保留），mock 路径不读参数，前端标注「仅 real 生效」。→ 对齐 PRD 开放问题 3 推荐。
