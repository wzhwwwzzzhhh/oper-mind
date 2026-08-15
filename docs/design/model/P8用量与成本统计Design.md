# P8 用量与成本统计 · Design

> 状态：已确认
> 更新：2026-08-13
> 关联：`docs/prd/model/P8-model-usage-stats.md`（已确认 PRD，issue #67）、
> `docs/prd/model/P8-model-params-config.md`（同批 P8，模型参数配置，app_settings 先例）、
> `docs/prd/model/P8-model-mode-switch.md`（同批 P8，运行时模式切换，app_settings 先例）、
> `docs/design/model/P6模型Provider与APIKey管理Design.md`（已确认，Provider/生效配置解析层）、
> `docs/design/model/P8模型参数配置Design.md`（已确认，注入模式与解析层先例）、
> `docs/产品定义.md`、`docs/路线图.md`、`docs/开发规范.md`、`docs/架构与开发路径.md`、
> `backend/src/core/llm.py`（LLMClient 采集点）、`backend/src/core/bootstrap.py`、
> `backend/src/api/v1/dependencies.py`（装配点）、`backend/src/domain/model_params.py`（AppSettingsStore 端口先例）、
> `backend/src/application/model_params.py`（解析层先例）、`backend/src/infrastructure/persistence/app_settings_repository.py`

## 1. 目标与范围

一句话目标：运维在模型设置页**查询模型调用的 token 用量与估算花费**（按时间窗 / 按模型）；真实调用的 usage **落库持久化**（跨进程可追溯），mock 恒 0 如实标注，花费为估算并明确标注。

### 做什么
- 用量采集：`LLMClient` 真实调用返回处把 usage（input/output/total tokens + 模型名 + 时间戳）**写入应用库**；mock 不采集。
- 统计接口：`GET /api/v1/model/usage`，支持可选时间窗（from/to）与模型过滤，返回按模型分组的 token 聚合与估算花费。
- 花费估算：按模型单价 × token 估算；单价**内置默认表 + app_settings 键值覆盖**（对齐 P8 既有键值先例）；响应标注"估算"。
- 前端适配：模型设置页新增"用量统计"区域，支持时间窗筛选，空态/失败态诚实展示。
- 涉及数据库迁移（新增用量记录表）与新增公开 API。

### 明确不做
- 不做精确账单/计价（PRD 排除；只做估算）。
- 不做按会话/Run 的用量明细下钻（首版只做聚合；表**预留 `run_id` 可空列**，首版不写入，便于后续下钻）。
- 不做用量告警/限额（PRD 排除，另行排期）。
- 不采集 mock 用量（mock 恒 0，如实标注）。
- 不暴露调用内容、prompt、响应、API Key 或凭据（只暴露聚合计数）。
- 不改变 `LLMClient` 的返回契约与既有调用语义（采集是副作用）。
- 不为单价新建表（复用既有 `app_settings` 键值，见 D3/D4；对齐 `model.runtime_mode` / `model.params` 先例）。

## 2. 设计决策

### D1 · 采集点与注入：LLMClient 真实调用返回处 + 显式 UsageRecorder port

- **采集点**：`backend/src/core/llm.py` 的 `LLMClient.chat()` 真实调用分支（`self.client.api_key != "mock"`），在响应返回前读取 `response.usage` 并调用注入的记录器；mock 分支（`_mock_chat`）不采集。这是全链路唯一真实 LLM 调用汇聚点（Coordinator / Debate / Reflection / Agent 全部经 `llm.chat()`），一次落点覆盖全部调用。
- **注入方式**：`LLMClient.__init__` 新增可选参数 `usage_recorder: UsageRecorder | None = None`（None=不采集，保持既有构造兼容）；`chat()` 不新增参数（采集是自动副作用，调用方无感知）。对齐 P8 参数配置的注入模式（`default_temperature`/`default_max_tokens` 实例字段）。
- **装配点**：`backend/src/core/bootstrap.py` 的 `build_llm_from_config(config, params=None, usage_recorder=None)` 透传；`backend/src/api/v1/dependencies.py` 的 `_resolved_coordinator_factory` 在构造 LLM 时注入 `SqlAlchemyUsageRecorder`（见 D2）。测试直接构造 `LLMClient` 时可不传 recorder。
- **失败降级**：采集包裹在独立 try/except 中，任何异常（应用库不可用、未迁移、写入失败）只记 WARNING 日志，**绝不阻断或改变调用返回**（AC8）。

### D2 · 采集记录器：domain 端口 + infrastructure 实现

- **domain 端口**：新增 `backend/src/domain/model_usage.py`，定义 `UsageRecorder` Protocol 与数据结构（对齐 `model_params.py` 的 `AppSettingsStore` 端口先例）：
  ```python
  class UsageRecorder(Protocol):
      def record(self, record: UsageRecord) -> None: ...
  class UsageRecord(TypedDict):
      model: str
      input_tokens: int
      output_tokens: int
      total_tokens: int
      occurred_at: datetime
  ```
- **infrastructure 实现**：`backend/src/infrastructure/persistence/model_usage_repository.py` 新增 `SqlAlchemyUsageRecorder`（经 `SessionFactory` 注入；单条 insert + commit，短生命周期 Session，模式对齐 `in_transaction`）与 `SqlAlchemyModelUsageRepository`（聚合查询，见 D5）。
- **数据流**：`LLMClient`（core）→ Protocol 调用 → `SqlAlchemyUsageRecorder`（infrastructure）→ `model_usage_records` 表。跨层数据为 TypedDict/Pydantic，无隐式字典协议。

### D3 · 数据模型（涉及迁移：仅一张新表）

**`model_usage_records`（用量记录，只增不改）**：
- `id` (UUID, PK)
- `model` (str, 索引) —— 采集自 `LLMClient.model`（生效模型名）
- `input_tokens` / `output_tokens` / `total_tokens` (int, ≥0 约束)
- `run_id` (UUID, **可空**) —— 预留字段，首版不写入（NULL），供后续按会话/Run 下钻，避免后续迁移
- `created_at` (datetime, timezone, 索引) —— 采集时间戳
- 索引：`(model, created_at)`、`created_at`（时间窗聚合）
- 无内容/prompt/响应/凭据字段（AC7）

**单价不建新表**：复用既有 `app_settings` 键值表（key=`model.prices`，值 JSON），对齐 `model.runtime_mode` / `model.params` 先例（见 D4）。

迁移：`backend/migrations/versions/` 新增一个 alembic revision（upgrade/downgrade 成对），`down_revision` 指向当前 head（`20260812_12_p8_run_rerun`），revision 建议 `20260813_13_p8_model_usage`。

### D4 · 花费估算：内置默认单价表 + app_settings 键值覆盖

- **内置默认表**（`backend/src/domain/model_usage.py` 代码常量 `DEFAULT_MODEL_PRICES`，单位 ¥/百万 token）：常见模型 input/output 单价（如 deepseek-chat / deepseek-reasoner / qwen 系列 / gpt-4o / gpt-4o-mini 等，含 input 与 output 两档）；未列出的模型回退通用默认单价（保守偏低，且响应标注"估算"与单价来源）。
- **覆盖机制**：`app_settings` 键 `model.prices`（JSON `{"<model>": {"input": 1.2, "output": 2.4}}`）按模型名覆盖默认值；查询时**模型名精确匹配**覆盖键，未命中用内置默认；两者皆无 → 花费按 0 估算并标注"未配置单价"（诚实空态）。JSON 解析失败/应用库不可用 → 诚实降级为内置默认（对齐 `decode_params` 降级纪律）。
- **计算公式**：`estimated_cost = input_tokens × input_price / 1e6 + output_tokens × output_price / 1e6`（total_tokens 仅展示，不参与计价，避免重复计费）。
- **标注**：响应携带 `estimate: true`、单价来源（`builtin` / `configured` / `unset`）与单价取值，前端明确展示"估算"字样（AC4）。

### D5 · 统计接口：GET /api/v1/model/usage

| 方法 | 路径 | 参数 | 行为 | 响应 |
|---|---|---|---|---|
| GET | `/api/v1/model/usage` | `from`（ISO datetime，可选，query 参数名用 `from_` + alias）、`to`（可选）、`model`（可选） | 按时间窗/模型过滤，按模型分组聚合 input/output/total tokens，按 D4 估算花费；无记录返回空态 | `ModelUsageResponse`：`{items: [{model, input_tokens, output_tokens, total_tokens, estimated_cost, price_source, price_per_million_input, price_per_million_output}], estimate: true, from, to, meta}` |

- **时间窗语义**：`from`/`to` 均为可选；缺省窗口 = 最近 30 天（诚实默认）；`from ≤ to` 校验失败 → 422；窗口跨度上限 366 天（防大表全扫，PRD"分页/限时"）。
- **聚合实现**：`SqlAlchemyModelUsageRepository.stats()` 的库内 `GROUP BY model` 聚合查询（SQLAlchemy `func.sum`），无分页（模型数有限，聚合结果天然小）；`model` 过滤为等值条件。
- **空态**：无记录（含 mock 模式恒 0）→ `items: []`，HTTP 200，不抛错（AC6）。
- **安全**：响应只含聚合计数与单价数值，**不含**调用内容/prompt/响应/API Key/`sk-`/凭据（AC7）；错误走既有 `ApiV1Error` 包络。
- **接口契约**：既有接口不变（AC10 兼容性）；前端 API 类型由 `npm run generate:api` 生成（`frontend/src/api/v1/generated.ts` 禁止手改）。

### D6 · 前端用量展示

- **位置**：`frontend/src/features/models/ModelSettingsPage.tsx` 新增"用量统计"section（独立于 Provider 区与参数区），复用既有 `model-*` CSS 模式。
- **交互**：时间窗筛选（预设按钮：近 7 天 / 近 30 天 / 近 90 天；可选 from/to 输入）；按模型分组表格：模型 / input tokens / output tokens / total tokens / 估算花费（含"估算"标注与单价来源）；无数据 → 诚实空态（"暂无用量记录；Mock 模式不采集用量"）；请求失败 → 错误态提示，不伪造。
- **数据获取**：`frontend/src/api/v1/queries.ts` 新增 `get_model_usage_query`；`client.ts` 新增请求函数（走既有 v1 client 模式）。

## 3. 文件改动面

### 后端（backend/）
- **新增** `backend/src/domain/model_usage.py` —— `UsageRecorder` Protocol、`UsageRecord` TypedDict、`DEFAULT_MODEL_PRICES` 默认单价表、单价编解码 helper（JSON 解析失败诚实降级）。
- **修改** `backend/src/core/llm.py` —— `LLMClient` 新增 `usage_recorder` 可选参数；`chat()` 真实调用返回处采集（try/except 降级，mock 不采集）。
- **修改** `backend/src/core/bootstrap.py` —— `build_llm_from_config` 透传 `usage_recorder`（默认 None）。
- **修改** `backend/src/api/v1/dependencies.py` —— `_resolved_coordinator_factory` 构造 LLM 时注入 `SqlAlchemyUsageRecorder`；`V1Services` 增加 `model_usage_service`。
- **修改** `backend/src/infrastructure/persistence/models.py` —— 新增 `ModelUsageRecord`。
- **新增** `backend/src/infrastructure/persistence/model_usage_repository.py` —— `SqlAlchemyUsageRecorder`（写入）+ `SqlAlchemyModelUsageRepository`（聚合查询、单价读取）。
- **新增** `backend/src/application/model_usage.py` —— 应用服务 `ModelUsageApplicationService`（stats 查询 + 单价解析 + 花费估算，对齐 `ModelParamsApplicationService` 风格）；跨层数据走 Pydantic。
- **新增** `backend/migrations/versions/20260813_13_p8_model_usage.py` —— 建 `model_usage_records` 表（upgrade/downgrade）。
- **修改** `backend/src/api/v1/routes.py` + `schemas.py` + `resources.py` —— 新增 `GET /model/usage` 与 `ModelUsageResponse`/`ModelUsageItemResource`。
- **新增** `backend/tests/test_model_usage_api.py`（接口/聚合/空态/时间窗/脱敏）、`backend/tests/test_usage_recording.py`（采集落库/mock 不采集/失败降级）；**修改** 既有 `test_api.py`/`test_model_provider_api.py`/`test_llm_client.py` 如有构造变更（预期无破坏，recorder 默认 None）。

### 前端（frontend/）
- **修改** `frontend/src/features/models/ModelSettingsPage.tsx` —— 新增"用量统计"section。
- **修改** `frontend/src/api/v1/client.ts`、`queries.ts` —— 新增 usage 查询；`generated.ts` 由 `npm run generate:api` 生成（禁止手改）。
- **新增/修改** 前端交互测试（`ModelSettingsPage.test.tsx` 扩展，MSW mock 用量接口）。

### 无功能改动部分
- Agent 调用策略、会话链路其他部分、Trace 展示逻辑、Provider 管理、模式切换、参数配置既有行为（本设计只读叠加，不改契约）。

## 4. 可独立验收的改动单元（指引，不写死）

> Design 只给改动单元的验收语义；正式切片拆解、验证命令与提交计划归 `dev-plan` 的 `plan.md`。

建议拆 **2 个独立可验收单元**：
- **U1 后端采集 + 统计接口**：迁移（usage 表）→ UsageRecorder 注入采集 → `GET /model/usage` 聚合/单价/空态/脱敏。验收语义：真实调用落库（AC1）、聚合与时间窗（AC2/AC3）、单价估算与标注（AC4）、mock 恒 0（AC5）、空态（AC6）、脱敏（AC7）、采集失败不阻断（AC8）、迁移 upgrade/downgrade 成功。门禁：数据库迁移 + 公开 API。
- **U2 前端用量展示**：模型设置页用量 section + 时间窗筛选 + 空态/失败态。验收语义：AC9；回归 AC10（既有后端/前端测试全绿）。

## 5. 风险、回滚与门禁

| 风险 | 缓解 |
|---|---|
| 采集拖慢真实调用 | 单条轻量 insert + 短生命周期 session；失败仅记日志不阻断（AC8）；不做网络/重试 |
| 应用库未迁移导致每次采集失败 | 采集降级静默（WARNING 日志），接口返回空态不崩（AC6/AC8）；DoD 要求迁移执行成功 |
| 单价估算误导 | 响应/页面明确"估算"标注 + 单价来源（builtin/configured/unset）（AC4） |
| 大时间窗拖慢聚合 | 窗口上限 366 天 + `(model, created_at)` 索引 + 库内聚合 |
| 隐私泄露 | 表无内容字段；响应只含聚合计数与单价（AC7）；不加新凭据路径 |
| 预留 run_id 无人写 | 首版显式不写入（NULL），文档注明后续下钻接线点，不误导为"已有明细" |
| 与并行 P8 切片迁移冲突 | 迁移 revision 唯一（13），down_revision 钉死当前 head；合前拉 main 解冲突 |

- **回滚**：移除 `/model/usage` 路由注册 + 回滚迁移（drop usage 表）；`LLMClient` 的 recorder 参数默认 None，移除注入即回到现状（无行为变化）。无既有接口契约破坏。
- **门禁项清单**：数据库迁移（新增 usage 表）、新增公开 API（`GET /model/usage`）。

## 6. 待用户确认的设计决策

1. **单价来源与默认值**：内置默认单价表（常见模型 input/output 每百万 token 单价）+ `app_settings` 键 `model.prices` 按模型覆盖；未配置用内置默认，未列出模型回退通用默认并标注来源。（PRD 开放问题 1 推荐方案；复用既有键值表，不建新表）
2. **run_id 预留**：`model_usage_records.run_id` 可空列，首版不写入（NULL），供后续按会话/Run 下钻免迁移。（PRD 开放问题 2 推荐方案）
3. **采集同步轻量写**：采集在调用返回处同步单条写入（应用库为本地 SQLite，毫秒级），失败降级不阻断；不引入异步队列（首版复杂度与收益不匹配）。（PRD 开放问题 3 推荐方案）
4. **默认时间窗**：`GET /model/usage` 未传 from/to 时默认最近 30 天；窗口跨度上限 366 天。
