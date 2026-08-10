# P8 模型模式切换 · Design

> 状态：已确认
> 更新：2026-08-10
> 关联：`docs/prd/model/P8-model-mode-switch.md`（已确认 PRD，issue #55）、
> `docs/prd/model/P4.3-model-settings-real.md`（只读安全视图，本设计在其上扩展）、
> `docs/prd/model/P6-model-provider-key-management.md`（DB 激活 Provider 优先、加密 Key，已落地）、
> `docs/产品定义.md`、`docs/路线图.md`、`docs/开发规范.md`、`docs/架构与开发路径.md`

## 1. 目标与范围

一句话目标：运维在模型设置页**运行时切换 mock ↔ real**，模式选择**持久化到应用库并覆盖 env/YAML 决定**，切换后 `GET /model/config` 与会话链路**即时、一致、诚实**地反映新模式；real 但无可用 Provider/Key 时如实降级标注，不伪造切换已生效。

### 做什么
- 运行时模式持久化：应用库新增通用键值表 `app_settings`，key=`model.runtime_mode` 存 `mock` / `real`；未显式切换时该行不存在，回退 env/YAML 决定（env 只是"从未切过"的默认）。
- 生效解析：新增模式解析层，作用于**会话链路 LLM 构造点**（每 Run 解析）与 `GET /model/config` / `/health`，与既有 DB 激活 Provider 优先机制同层叠加、互相独立。
- 新模式写接口：`PUT /api/v1/model/mode`，体 `{"mode": "mock"|"real"}`；幂等、无需 Idempotency-Key；返回更新后的完整安全配置视图（无前后端漂移）。
- 诚实标注：`GET /model/config` 扩展 `mode_source`（runtime/env）、`mode_available`、`mode_unavailable_reason`；real 但无可用 Key 时页面如实提示，会话链路诚实降级。

### 明确不做
- 不做 Provider 下可用模型列表自动发现（PRD 排除，另行排期）。
- 不做模型参数（temperature / max_tokens）暴露（PRD 排除）。
- 不做用量 / 成本统计（PRD 排除）。
- 不做多模型路由策略（PRD 排除，`产品定义.md` §7 未决）。
- **不改 `load_config()` 内部实现**、不改 `OPERMIND_API_KEY` 等 env 读取机制本身（PRD 排除；模式是运行时覆盖层，env 仍是兜底事实）。
- 不把模式状态放前端 localStorage（PRD 排除，`完善清单.md` P1-7 已删假开关）。
- 不做"恢复为 env 默认"的显式 UI 操作（PRD 未要求；env 兜底仅在从未切换时生效）。

## 2. 设计决策

### D1 · 模式持久化：应用库通用键值表 `app_settings`

- **选择**：新增应用库键值表 `app_settings`（`key` PK、`value` 可空、`updated_at`），模式存 key=`model.runtime_mode`。
- **为什么**：PRD 开放问题 1 给两个选项——"应用库简单键值表，还是复用既有配置/Provider 表"。**不复用 `model_providers`**：模式是全局运行时态，不是单个 Provider 的属性，塞进 Provider 表语义错误；**不新建单用途表**：`app_settings` 通用键值表既满足本需求，也避免未来同类运行时设置再造表。
- **语义**：行不存在 = 从未显式切换（env/YAML 兜底）；行存在且 value=`mock`/`real` = 运行时覆盖。无"auto"中间态，避免三态歧义；如需回退 env，由运维在后续版本用显式重置能力处理（本版本不做）。
- **诚实降级**：应用库不可用 / 未迁移时，模式解析层回退到 env 决定（与 `resolve_model_config` 的 SQLAlchemyError 容错一致），**永不 raise**。此时若运维已显式切过模式，`mode_source` 报告 `env` 会混淆"从未切换"与"读取失败回退"——**降级路径下用 `mode_unavailable_reason="应用库不可用，回退环境变量决定"` 显式标注**，与"从未切换"区分开，保持诚实标注一致。

### D2 · 生效解析：模式覆盖层叠加在既有解析之上

- **不改 `resolve_model_config()`**（DB 激活 Provider 优先 → env/YAML 兜底，PRD 明确不做）。在其上新增独立解析层，返回结构化 `ModelRuntimeResolution`：
  ```python
  class ModelRuntimeResolution(TypedDict):
      mode: Literal["mock", "real"]          # 生效模式（运行时覆盖优先，未切换则 env 决定）
      mode_source: Literal["runtime", "env"]  # 诚实来源：runtime=显式切换，env=从未切换兜底
      mode_available: bool                    # real 是否有可用 Key；mock 恒 True
      mode_unavailable_reason: str | None     # real 不可用时的诚实原因（无可用 Provider/API Key）
      config: dict[str, dict[str, str]]       # 与 resolve_model_config 同构的 llm/judge_llm 生效配置
  ```
- **契约签名**：`resolve_runtime_mode(session_factory, secret_key) -> ModelRuntimeResolution`——**必须显式透传 `secret_key`**（与 `resolve_model_config(session_factory, secret_key)` 同构，`model_providers.py:286`）：DB 激活 Provider 场景解析 real 可用性需要解密 Key。三个调用方（`dependencies.py`、`routes.py`、`app.py`）已各自加载 `secret_key`，统一由路由/装配层注入，实现不各自发散。
- **会话链路生效点**：沿用 P6 的"每 Run 构造 LLM"机制（`dependencies.py::_resolved_coordinator_factory`）。构造 LLM 前先解析模式：
  - `mode=mock` → 强制 `config["llm"]["api_key"] = "mock"`，`build_llm_from_config` 走确定性 mock 场景（`set_active_scenario("S1")`）；
  - `mode=real` → 保留 `resolve_model_config` 原结果（DB 激活 Provider → env/YAML）；若生效 llm 无可用 Key（`api_key` 为空或 `"mock"`）→ `mode_available=false`，LLM 仍按 `build_llm_from_config` 的诚实兜底跑 mock（不伪造真实连接）。
  - **`judge_llm` 为展示-only**：会话链路仅经 `build_llm_from_config(config)`（`bootstrap.py:21-39`，只读 `config["llm"]`）构造单一 LLM，`judge_llm` 只被 `GET /model/config` 展示消费（`routes.py:277`）。mock 强制不重复作用于 judge（无裁判 LLM 构造路径），避免实现者误造。
- **展示生效点**：`routes.py::_model_config_resource` 与 `app.py::_service_mode`（`/health`）改用同一解析层，保证 `GET /model/config`、`/health` 与会话链路三处一致。
- **保存即生效、无需重启**：每次 Run / 每次 GET 都现场解析应用库，与 P6"Provider 激活后下一次 Run 即生效"一致。

> **契约语义变更点（有意演化，非回归）**：P4.3 AC2「env=`OPERMIND_API_KEY=mock` ⇒ `GET /model/config` 返回 `mode=mock`」仅在**从未显式切换**的基线下成立。运行时覆盖 real 而 env=mock 且无激活 Provider 时，本设计返回 `mode=real`、`mode_available=false`（页面如实提示不可用），会话链路诚实跑 mock——这是 PRD 驱动的模式选择语义，`mode_source`/`mode_available` 显式兜底诚实性。P4.3 相关既有用例（未切换基线）保持全绿，需在回归测试中显式区分。

### D3 · real 可用性判定：运行时事实，不复用历史探针

- PRD 开放问题 2 建议"复用 `has_api_key` + 验证状态"。**裁定：以运行时生效配置为唯一判定事实**——real 可用 ⟺ 解析后的 `config["llm"]["api_key"]` 是真实 Key（非空且非 `"mock"`）。
- **为什么不用 `verify_status`**：`verify_status` 是连接验证的**历史快照**（含 `timeout`/`failed`），会过期且不代表"此刻是否有 Key"；可用性判定应反映"现在切到 real 到底跑不跑得起来"，与 `resolve_model_config` 的诚实兜底语义同源。
- `verify_status` 仍保留在 Provider 列表视图（P6 已交付），但**不参与**模式可用性判定，避免两套事实打架。

### D4 · 接口契约（新增公开 API + 既有契约扩展）

| 方法 | 路径 | 行为 | 脱敏要求 |
|---|---|---|---|
| PUT | `/api/v1/model/mode` | 体 `{"mode": "mock"\|"real"}`；校验字面量（非法 → 422）；写入 `app_settings`；**幂等**（同值重复设置返回相同结果），无需 Idempotency-Key；持久化失败 → 返回错误、不产生半状态；返回 `ModelConfigResponse`（更新后的完整安全视图，前端一步到位、无漂移） | 无 Key/DSN/`sk-` 明文 |
| GET | `/api/v1/model/config` | 既有端点**向后兼容扩展**：`ModelConfigResource` 新增 `mode_source`、`mode_available`、`mode_unavailable_reason` 三个字段（加法，不破坏既有字段） | 沿用 P4.3 脱敏纪律 |

- `PUT /model/mode` 不要求 `Idempotency-Key`：模式是幂等标量设置（与 Provider 创建的"幂等防重放"语义不同），重复 PUT 同值结果一致。
- **错误映射**：持久化失败统一并入既有 `APPLICATION_ERROR_STATUS` 映射模式（`routes.py:134-152`）——新增 `MODEL_MODE_PERSISTENCE_FAILED` → 500（应用库写失败属服务端故障，不回 4xx）；校验失败走 FastAPI/Pydantic 既有 422（`mode` 非法字面量）。不存在 404/409 语义。
- 前端 API 类型经 `npm run generate:api` 重新生成（`frontend/src/api/v1/generated.ts`），禁止手改。
- **前端缓存策略（唯一口径）**：`PUT /model/mode` 返回完整 `ModelConfigResponse`，前端把响应直接写入 react-query 的 `model_config` 缓存（`setQueryData`）并置空查询重取，页面状态 = 后端返回值，**不二次推断**；§3 前端描述与此一致。

### 数据模型（涉及迁移）

新增 `app_settings` 表（应用库）：
- `key` (String, PK, ≤100)
- `value` (String, 可空, ≤200)
- `updated_at` (datetime)
- 迁移：`backend/migrations/` 新增 alembic revision（upgrade/downgrade）；downgrade 删除 `app_settings`。
- **无凭据落库**：value 只存 `mock`/`real`，与 Key/DSN 无涉。

## 3. 文件改动面

### 后端（backend/）
- **新增** `backend/src/domain/model_runtime_mode.py` —— 模式领域模型（`ModelRuntimeMode` 字面量常量、`ModelRuntimeResolution` TypedDict），拒绝隐式字典协议。
- **新增** `backend/src/application/model_mode.py` —— 模式应用服务 + 生效解析层：`resolve_runtime_mode(session_factory, secret_key) -> ModelRuntimeResolution`（读取 `app_settings`、叠加 `resolve_model_config`）；`set_runtime_mode(session_factory, mode)` 写库（事务助手与 `model_providers.py` 的 `_in_transaction` 同构——**提炼为共享事务助手**如 `src/application/transaction.py`，避免跨模块导入私有符号；本次随实现一并落地）。**不放 config.py**，避免层级倒挂与迁移 env.py 循环导入。
- **新增** `backend/src/infrastructure/persistence/models.py` 中 `AppSettingRecord`。
- **新增** `backend/src/infrastructure/persistence/app_settings_repository.py` —— `AppSettingRecord` 的读写仓库（`get(key)` / `set(key, value)`）。
- **新增** `backend/migrations/versions/20260810_10_p8_model_mode.py` —— 建 `app_settings` 表（upgrade/downgrade）。
- **修改** `backend/src/api/v1/dependencies.py` —— `_resolved_coordinator_factory` 构造 LLM 前应用模式覆盖（解析 `resolve_runtime_mode`，`mode=mock` 时强制 `api_key="mock"`）。
- **修改** `backend/src/api/v1/routes.py` —— 新增 `PUT /model/mode`；`_model_config_resource` 改用模式解析层（含 `mode_source`/`mode_available`/`mode_unavailable_reason`）。
- **修改** `backend/src/api/v1/schemas.py` —— `ModelConfigResource` 扩展三字段；新增 `UpdateModelModeRequest`（`mode: Literal["mock","real"]`）；`PUT /model/mode` 复用 `ModelConfigResponse`。
- **修改** `backend/src/app.py` —— `_service_mode` / `_effective_model_config` 改用模式解析层（`/health` 与 `GET /model/config` 一致）。
- **新增** `backend/tests/test_model_mode_api.py`、`backend/tests/test_model_mode_resolver.py`；**修改** `backend/tests/test_model_config_api.py`（期望响应补新字段）、`backend/tests/test_api.py`、`backend/tests/test_agent_gateway.py`（回归，模式解析层装配）。

### 前端（frontend/）
- **修改** `frontend/src/features/models/ModelSettingsPage.tsx` —— 运行模式卡片由"只读"改为 mock/real 切换控件（两态选择 + 保存）；保存后用 `PUT` 返回的 `ModelConfigResponse` 直接写入缓存，不二次推断；`mode_available=false` 时显示"real 模式已保存但当前不可用"，不伪造。
- **修改** `frontend/src/api/v1/queries.ts` —— 新增 `update_model_mode_mutation`；`generated.ts`/`client.ts` 由 `npm run generate:api` 生成。
- **新增/修改** 前端交互测试（`ModelSettingsPage.test.tsx`，MSW mock：切换 mock→real 保存、real 不可用提示）。

### 无功能改动部分
- Agent 调用策略本地偏好区、Provider CRUD、Trace 展示逻辑（本设计不含凭据展示路径）。

## 4. 切片与验证（指引，不写死）

> 本 Design 只给改动单元的验收语义；正式切片拆解、验证命令与提交计划归 dev-plan 的 `plan.md`。

建议拆 **2 个独立可验收单元**：
- **U1 模式持久化 + 生效解析层 + 会话链路生效**：`app_settings` 迁移 + 仓库 + 模式应用服务 + `resolve_runtime_mode` + coordinator factory 覆盖 + `/health` 一致性。验收语义：写模式后 `resolve_runtime_mode` 返回覆盖结果；未切换时回退 env；会话链路按模式构造 LLM（mock 强制走 mock 场景）；重启后模式保持（AC1/AC2/AC3/AC7 主战场）。门禁：数据库迁移。
- **U2 公开 API + 前端切换**：`PUT /model/mode` + `GET /model/config` 扩展 + 前端切换控件 + 诚实标注 + 回归。验收语义：切换后 `GET /model/config` 返回新模式且 `mode`/页面一致；real 无可用 Key 时保存成功但页面如实提示不可用；无 Key/`sk-` 明文（AC4/AC5/AC6/AC7）。门禁：新增公开 API。

## 5. 风险、回滚与门禁

| 风险 | 缓解 |
|---|---|
| 模式覆盖与 DB Provider 优先语义混淆 | 二者同层独立：Provider 决定"用什么 Key/URL"，模式决定"跑不跑真实调用"；解析层单一事实源 |
| `app_settings` 无值约束导致脏数据 | 仓库读写限定 `mock`/`real` 字面量；写接口 Pydantic Literal 校验（422） |
| 应用库不可用 / 未迁移 | 解析层 SQLAlchemyError 容错 → 回退 env，永不 raise（对齐 `resolve_model_config`） |
| 前端展示与后端漂移 | `PUT /model/mode` 返回完整 `ModelConfigResponse`，前端一步写入缓存，不二次推断 |
| 已有测试期望被新字段破坏 | 只做加法字段；`test_model_config_api.py` 期望 dict 同步补新字段 |
| 并发 real/mock Run 覆盖进程级 mock 场景态 | P6 遗留：`set_active_scenario("S1")` 是进程级全局态（`bootstrap.py:35-36`），并发 real/mock Run 互相覆盖；非本设计引入，随"每 Run 构造 LLM"沿用，风险表知悉，后续另行治理 |

- **回滚**：移除 `PUT /model/mode` 路由注册 + 回滚 `app_settings` 迁移；`GET /model/config` 三字段可留在响应（加法，前端未用到即忽略）；coordinator factory / `/health` 回退直接 `resolve_model_config` 现状。无既有接口契约破坏。
- **门禁项清单**：数据库迁移（`app_settings`）、新增公开 API（`PUT /model/mode`）。**无新增 Connector / 真实连接 / 凭据读写 / 审批执行能力。**

## 6. 待用户确认的设计决策

1. **模式持久化用应用库通用键值表 `app_settings`**（key=`model.runtime_mode`），涉及数据库迁移；不复用 `model_providers`（模式是全局态，非 Provider 属性）。→ 请确认迁移与键值表方案。
2. **real 可用性以运行时生效配置为唯一事实**（`config["llm"]["api_key"]` 非空且非 `"mock"` ⟺ 可用），不复用 Provider 的 `verify_status` 历史探针。→ 请确认判定口径。
3. **env 兜底语义**：运行时模式优先；env/YAML 只在"从未显式切换"时决定模式；本版本不做"恢复为 env 默认"的显式重置操作。→ 请确认。
4. **`GET /model/config` 契约扩展**：新增 `mode_source` / `mode_available` / `mode_unavailable_reason` 三个只加不减字段（向后兼容）。→ 请确认字段集。
5. **`PUT /model/mode` 幂等、无需 Idempotency-Key**（标量设置与 Provider 创建语义不同）；保存即生效、无需重启。→ 请确认。
