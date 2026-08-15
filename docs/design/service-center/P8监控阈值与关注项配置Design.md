# P8 监控阈值与关注项配置 Design

> 状态：已确认
> 更新：2026-08-15
> 关联：`docs/prd/service-center/P8-monitor-threshold-config.md`（issue #77，已确认）、
> `docs/design/monitor/P5监控历史趋势与页面告警Design.md`（采样/样本语义）、
> `docs/design/monitor/P7服务监控概览页Design.md`（概览聚合与异常计数）、
> `docs/产品定义.md` §5（监控诚实性）、`docs/开发规范.md` §5/§8（监控语义、并行冲突处理）、
> `docs/接口清单.md`（第二大模块"缺少"表：监控阈值欠账）、
> `backend/src/application/monitoring.py`（`_trend_summary` 硬编码判定）、
> `backend/src/api/v1/routes.py`、`frontend/src/features/services/ServiceDetailPage.tsx`。

## 1. 目标与范围

**一句话目标**：把"采样点异常"的判定规则从后端硬编码改为**按服务可配置**——运维能调关注指标、数量阈值、判定窗口与可用性变化开关，配置持久化到应用库（重启不丢），未配置时沿用内置默认（行为与现状完全一致），概览/历史/详情页异常计数与标记如实反映生效规则。

### 做什么

- 新增按服务维度的阈值配置读写接口：`GET /services/{id}/monitor/thresholds`（读）+ `PUT /services/{id}/monitor/thresholds`（写）。
- 配置项（指标白名单固定三项 + 窗口 + 开关）：
  - `slow_query_count_threshold` / `timeout_count_threshold` / `slowlog_count_threshold`：每项**数量下限**，`null` = 不关注该指标，数值 = 关注；
  - `window_minutes`：判定窗口（分钟），0 = 仅当前采样点自身；
  - `count_availability_change`：是否把"可用性状态变化"计为异常。
- 配置持久化到应用库（新增表 `service_monitor_thresholds`，涉及迁移），未配置不产生记录。
- 异常判定引擎改为**读配置**：`_trend_summary` 不再按服务类型硬编码，按服务配置计算异常采样点；
  概览 `anomaly_sample_count` 按配置计算；服务详情页趋势异常点标记按同一确定性规则复算。
- 前端服务中心详情页新增"监控阈值"配置区：只读回显当前生效规则（诚实标注"内置默认 / 已配置"）+ 可编辑保存，失败/校验错误诚实提示，空态/加载态正常。

### 明确不做

- 不做**全局/跨服务**阈值（按服务维度；全局默认由内置默认承担，不做全局覆盖）。
- 不做告警通道/通知（页面内告警已决，`docs/接口清单.md` 告警通道刻意不做）。
- 不改变采样本身（采样间隔、保留期、采样器不动）；配置只影响"异常判定"这一层。
- 不做复杂规则引擎（只做数值下限 + 窗口 + 关注指标开关 + 可用性变化开关，不做表达式/组合规则）。
- 不暴露凭据/DSN/原始异常详情；配置接口与判定结果不含敏感连接细节。
- 不改变既有 `GET /services`、`GET /services/{id}/monitor/history`、`GET /monitor/overview` 的**契约字段**（仅异常计数/标记的语义按配置计算）。
- 不改 mock 数据源（`data/mock_db.py`、`data/scenarios.py`）与 S1–S4 评测路径。

## 2. 设计决策

### 2.1 配置粒度与持久化（回答 PRD 开放问题 1）

按**服务维度**单行配置，不做"服务类型 + 服务"两级（PRD 推荐；当前静态注册表仅 4 个服务，两级只会引入继承/覆盖语义而无实际收益）。

新增应用库表 `service_monitor_thresholds`（与 `service_monitor_samples` 同库）：

| 列 | 类型 | 约束 |
|---|---|---|
| `service_id` | String(64) | 主键 |
| `slow_query_count_threshold` | Integer | nullable，`IS NULL OR >= 0` |
| `timeout_count_threshold` | Integer | nullable，`IS NULL OR >= 0` |
| `slowlog_count_threshold` | Integer | nullable，`IS NULL OR >= 0` |
| `window_minutes` | Integer | not null，`>= 0 AND <= 1440` |
| `count_availability_change` | Boolean | not null |
| `updated_at` | DateTime(timezone=True) | not null |

- `service_id` 不建到动态服务表的外键（当前服务来源是静态注册表，与 `service_monitor_samples` 一致）。
- **未配置不产生记录**（PRD：未配置不产生记录）；GET 未配置 → 返回内置默认 + `source=default`。
- 阈值上界（API 层校验 [0, 1000000]）只由 schema 执行，DB CheckConstraint 只保证非负下限——约束职责分层，避免双处漂移。
- 迁移必须提供 upgrade/downgrade；迁移链按 `docs/开发规范.md` §8.3 串行排队（合并 main 后把 `down_revision` 指向最新 head）。
- **downgrade 数据保护**（对齐 `20260812_12_p8_run_rerun` / `20260811_11_p8_service_registration` 惯例）：downgrade 前检查表中是否存在配置行，存在则拒绝回滚并抛出明确错误，避免静默丢弃用户配置。

### 2.2 内置默认（回答 PRD 开放问题 4，锁定 AC6）

内置默认常量 `DEFAULT_MONITOR_THRESHOLDS`（领域层定义，GET 未配置时完整暴露）：

| 项 | 默认值 | 与现状等价性 |
|---|---|---|
| `slow_query_count_threshold` | `1` | PG：自身计数 ≥ 1 ⇔ 现状 `slow_query_count > 0` |
| `timeout_count_threshold` | `1` | PG：自身计数 ≥ 1 ⇔ 现状 `timeout_count > 0` |
| `slowlog_count_threshold` | `1` | Redis：自身计数 ≥ 1 ⇔ 现状 `slowlog_count > 0`（PG 样本该标量恒为 null，不触发） |
| `window_minutes` | `0` | 0 = 仅当前采样点自身，等价现状"逐点判定" |
| `count_availability_change` | `true` | 与现状"可用性状态变化计异常"一致 |

未配置服务按此默认计算 ⇒ 与现状 `_trend_summary` 输出完全一致（AC6 由测试锁定）。

### 2.3 判定规则（回答 PRD 开放问题 2/3）

**窗口语义**："当前采样点往前 `window_minutes` 分钟内（含两端）目标指标计数之和 ≥ 阈值 → 该采样点计为异常"（PRD 推荐"时间窗内计数 ≥ 阈值"）。

确定性规则（单一实现，前后端按同一规则复算，无表达式执行）：

```
对窗口内样本序列（按 observed_at 升序，排除 not_configured 空标量样本）：
  逐点 p（时间 t）：
    anomalous = false
    对每个已关注指标 m（threshold T_m 非 null）：
      windowed_sum = Σ (样本 s 的 m 值 or 0)，其中 t - window_minutes*60 ≤ s.observed_at ≤ t
      if windowed_sum >= T_m: anomalous = true
    若 count_availability_change 且 p.availability ≠ 前一个样本的 availability: anomalous = true
    若 anomalous: anomaly_sample_count += 1
```

**边界语义（钉死，两端实现必须一致）**：首样本没有"前一个样本"，不判可用性异常；
"前一个样本"指序列中**相邻的既有样本**，不是按固定时间间隔取点——存在漏采样缺口时，
仍与相邻既有样本比较可用性。该规则是前端复算与后端计数共用的**唯一文字契约**：
两端各实现一份确定性逻辑，并用共享 fixture 的测试锁定同一语义（含首样本、缺口采样、窗口边界场景）。

- `window_minutes = 0` ⇒ 窗口只含 p 自身 ⇒ 等价现状"出现即异常"。
- `threshold = 0` 合法（PRD 校验只禁负值）：计数 ≥ 0 恒真，即该指标开启时所有采样点计异常——由用户自负，属合法配置。
- 全部指标 `null` 且 `count_availability_change=false` ⇒ 永不异常（合法配置，如实反映）。
- 复杂度：窗口内样本数上限约 288（24h / 5min），逐点窗口求和为内存计算，无额外采样放大。

**指标与服务类型的适用性**：PG 样本 `slowlog_count` 恒 null（和 0），Redis 样本 `slow_query_count/timeout_count` 恒 null；即使显式关注也不触发，无需按类型裁剪白名单，诚实且简单。

### 2.4 接口契约

```text
GET /api/v1/services/{service_id}/monitor/thresholds
PUT /api/v1/services/{service_id}/monitor/thresholds
```

GET 响应（PUT 响应同构，`source=configured`）：

```json
{
  "service_id": "postgres-production",
  "source": "default | configured",
  "config": {
    "slow_query_count_threshold": 1,
    "timeout_count_threshold": 1,
    "slowlog_count_threshold": null,
    "window_minutes": 0,
    "count_availability_change": true
  },
  "meta": { "request_id": "…", "trace_id": null }
}
```

PUT 请求体 = `config` 对象（不含 `service_id`/`source`，未知字段被 schema 拒绝）。

- `source`：`default`（未配置，值为内置默认）/ `configured`（已保存）——PRD "configured: bool 或等效标注"的等效实现，诚实标注来源。
- 服务不存在（静态注册表无此 id）→ 404 `SERVICE_NOT_FOUND`（复用既有安全错误语义，不探测外部资源）。
- 非法配置（阈值 < 0 / 窗口越界 / 未知字段 / 类型错误）→ 422 `VALIDATION_ERROR` 明确错误，**不落库**。
- PUT 幂等（PUT 语义），无需 Idempotency-Key；保存即生效（下一次概览/详情读取即按新配置计算）。
- 响应不含凭据、DSN、原始异常详情（配置接口只接受白名单标量，天然无敏感输入）。
- 既有 `GET /services`、`GET /services/{id}/monitor/history`、`GET /monitor/overview` 契约字段**不变**。

### 2.5 判定引擎改造

- `MonitorOverviewApplicationService._service_overview`：读窗口样本后，按服务读一次阈值配置（单行查询，未配置 → 内置默认），传入 `_trend_summary(samples, config)`；`_trend_summary` 去掉按 `kind` 分支，改为按配置计算。
- `MonitorHistoryApplicationService.get_history`：**契约不变**，不新增字段；服务详情页趋势异常点标记由前端按同一确定性规则复算（前端已持有 samples，加读一次阈值配置即可；规则见 §2.3，前后端各实现一份确定性逻辑并在测试中锁定同一语义）。
- 配置读取失败（防御性读取校验非法行）→ 回退内置默认并 `source=default`，日志记录中文安全摘要（PRD 可靠要求）。

### 2.6 前端配置区

`ServiceDetailPage` 新增"监控阈值"配置区（位于"运行趋势"卡片之后）：

- 加载态/失败态正常；读取成功展示当前生效规则：
  - 来源徽标：`内置默认` / `已配置`（诚实标注）；
  - 三项指标行：关注开关（阈值 null ⇔ 不关注）+ 数量阈值输入；
  - 判定窗口：下拉（0=仅当前采样点 / 5 / 10 / 15 / 30 分钟，默认 0）；
  - 可用性变化开关；
- 编辑后保存 → PUT；成功提示并刷新（`invalidateQueries`）；422/网络失败 → 诚实错误提示（展示后端错误消息），不静默；
- 不出现"实时监控/告警推送"等表述；页面标注"判定规则仅影响异常采样点标记，采样与保留策略不变"。
- 样式复用既有 `service-detail.css`，不引入新样式体系。

### 2.7 配置

不新增环境变量/YAML 配置项。内置默认值定义在领域层常量，属产品行为而非部署配置（运维如要全局调参，按 PRD 是"按服务配置"，不做全局覆盖）。

## 3. 文件改动面

### 后端

- `backend/src/domain/monitoring.py`：新增 `MonitorThresholdConfig`、`MonitorThresholdView`（含 `source`）、`MonitorThresholdSource` 枚举、`DEFAULT_MONITOR_THRESHOLDS` 常量（Pydantic frozen + extra=forbid）。
- `backend/src/infrastructure/persistence/models.py`：新增 `ServiceMonitorThresholdRecord` ORM（含 CheckConstraint 与 PK）。
- `backend/src/infrastructure/persistence/monitor_repositories.py`：新增 `SqlAlchemyMonitorThresholdRepository`（`get` / `upsert`，防御性读取校验）。
- `backend/src/application/monitoring.py`：新增 `MonitorThresholdApplicationService`（`get`/`save`，服务边界校验）；`_trend_summary` 改为按配置计算；`_service_overview` 注入配置读取。
- `backend/src/api/v1/schemas.py`：新增 `MonitorThresholdConfigResource`、`MonitorThresholdRequest`、`MonitorThresholdResponse`（`source` Literal、字段约束、extra=forbid）。
- `backend/src/api/v1/resources.py`：新增 `monitor_threshold_resource` mapper。
- `backend/src/api/v1/routes.py`：新增 `GET`/`PUT /api/v1/services/{service_id}/monitor/thresholds` 路由（错误走既有 `ApiV1Error`/`raise_application_error` 语义）。
- `backend/migrations/versions/20260815_13_p8_monitor_thresholds.py`（**新增**）：建表 + 索引 + 约束 + downgrade；`down_revision` 指向当前 head `20260812_12_p8_run_rerun`（合并时按 §8.3 重指最新 head）。
- `backend/tests/test_monitor_thresholds.py`（**新增**）：单元 + API 测试；`backend/tests/test_monitor_overview.py`：适配按配置计算。

### 前端

- `frontend/src/api/v1/client.ts`、`queries.ts`：新增 `get_service_monitor_thresholds`、`update_service_monitor_thresholds` 与查询/突变；`generated.ts` 仅通过 `npm run generate:api` 更新（禁止手工编辑，冲突时重新生成）。
- `frontend/src/features/services/ServiceDetailPage.tsx`：新增"监控阈值"配置区（读 + 编辑 + 保存 + 诚实状态）。
- `frontend/src/features/services/ServiceDetailPage.test.tsx`：新增配置区交互测试（回显、默认/已配置标注、编辑保存、422/失败提示、空态/加载态）。
- `frontend/src/test/handlers.ts`：新增阈值 GET/PUT MSW fixture。
- 样式复用 `service-detail.css`，一般无需新增样式文件。

### 文档（随工作包 PR 交付）

- `docs/design/service-center/P8监控阈值与关注项配置Design.md`（本文档，已确认后随 PR 提交）。
- `docs/prd/service-center/P8-monitor-threshold-config.md`、`docs/prd/README.md`、`docs/prd/service-center/README.md`（PRD 状态推进"进行中"）。
- `docs/workpack/README.md`（工作包登记）、`docs/workpack/P8-monitor-threshold-config/{plan,review,evidence}.md`。
- `docs/接口清单.md`：收尾时把"监控阈值 / 关注项配置 ❌ 欠账"行更新为已交付（现状记录随开发滚动更新）。

### 无功能改动部分

- 无新 Connector、无凭据/连接改动、无新配置项、无新服务类型。
- 采样器、采样间隔、保留期不动；`data/mock_db.py`、`data/scenarios.py`、S1–S4 评测路径不改。
- 既有三个监控接口契约字段不变。

## 4. 切片与验证（指引，不写死）

建议拆 3 片（切片拆解、验证命令、提交计划归 `dev-plan` 的 plan.md）：

- **S1 后端领域/持久化/判定引擎**：领域模型 + 默认常量 + ORM + 迁移 + 仓储 + `MonitorThresholdApplicationService` + `_trend_summary` 读配置。
  验收语义：默认配置下异常计数与现状一致（AC6）；配置后按配置计算（AC5）；读写往返一致（AC2）；非法配置拒绝不落库（AC3）；未配置无记录；持久化后重进读回一致（AC7）；迁移 upgrade/downgrade（downgrade 存在配置行时拒绝回滚）。
- **S2 阈值 API 契约与路由**：GET/PUT 路由 + schema + API 测试。
  验收语义：GET 未配置返回默认 + `source=default`（AC1）；PUT 保存后 GET 读回一致（AC2）；非法 422（AC3）；不存在服务 404（AC4）；响应无凭据/DSN（AC8）；既有监控接口回归。
- **S3 前端配置区**：详情页配置区 + client/queries/handlers + 交互测试。
  验收语义：回显生效规则与来源标注（AC1/AC9）；编辑保存与失败/校验诚实提示（AC9）；加载/空态；`typecheck`/`test`/`build`（AC10）。

涉及门禁项：**新增公开 API（GET/PUT）、数据库迁移（新表）、监控判定行为（监控语义）**——必须经本 Design → Review → 用户确认后进入 dev-plan。
> 说明：两个阈值配置端点是已确认 PRD（issue #77）明示授权的配置读写落地物——只读写应用库配置行，
> 不触发任何目标连接、不绕过工具网关，与「架构与开发路径.md」硬规则「禁止新端点/新独立页面」的意图不冲突
> （同 P7 概览端点先例）。

## 5. 风险、回滚与门禁

- **风险 1：判定语义漂移**。默认值若与现状不一致会违反 AC6 → 默认常量 + 等价性说明（§2.2）+ 单元测试锁定（默认配置下与旧 `_trend_summary` 输出一致）。
- **风险 2：前后端规则漂移**。详情页前端复算与后端概览计数可能不一致 → 规则以 §2.3 为唯一文字契约，两端各实现一份并用相同 fixture 的测试锁定同一语义。
- **风险 3：配置行损坏**。DB 约束防写入非法，防御性读取再校验一次，非法回退默认并 `source=default`，日志记录中文安全摘要。
- **风险 4：迁移链冲突**。多个 P8 issue 并行带迁移 → 按 `docs/开发规范.md` §8.3：合并 main 后把 `down_revision` 指向最新 head 再合。
- **回滚**：执行迁移 downgrade（drop 表；downgrade 前检查存在配置行则拒绝回滚，先手动备份/清空再降级）+ 移除两个路由注册 + 移除前端配置区即回滚；默认行为不变，无既有契约破坏，无采样/凭据影响。
- **门禁**：本 Design `arch-review` PASS + 用户确认 + 状态改为「已确认」后，才放行 dev-plan。

## 6. 待用户确认的设计决策

1. **配置粒度**：按服务维度单行表（`service_id` 主键），未配置不落库；不做"服务类型 + 服务"两级（PRD 开放问题 1 推荐按服务）。
2. **指标白名单**：固定三项 `slow_query_count` / `timeout_count` / `slowlog_count`，阈值 `null`=不关注、数值=关注；另加 `count_availability_change` 开关（PRD 开放问题 2 推荐与现有 `_trend_summary` 对齐）。
3. **窗口语义**："当前采样点往前 `window_minutes` 分钟内（含两端）目标指标计数之和 ≥ 阈值 → 该点异常"；`window_minutes=0` 表示仅当前采样点自身（PRD 开放问题 3 推荐"时间窗内计数 ≥ 阈值"）。
4. **默认值暴露**：GET 未配置时完整暴露内置默认并标注 `source=default`（PRD 开放问题 4 推荐）。
5. **内置默认值**：三项阈值均为 1（出现即异常）+ 窗口 0 + 可用性变化计异常——与现状行为完全一致（AC6 锁定）。
6. **判定引擎落点**：概览 `anomaly_sample_count` 由后端按配置计算；服务详情页趋势异常点标记由前端按同一确定性规则复算（历史接口契约不加字段，满足 PRD 兼容性要求）。
7. **校验范围**：阈值 ∈ [0, 1000000]（null=不关注）、窗口 ∈ [0, 1440] 分钟、未知字段/指标被 schema 拒绝 → 422 不落库；PUT 幂等无 Idempotency-Key。
8. **收尾动作**：随交付 PR 同步更新 `docs/接口清单.md` 欠账行（监控阈值 / 关注项配置 → 已交付）。
