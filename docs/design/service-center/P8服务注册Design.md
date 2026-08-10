# P8 服务注册 —— 动态接入、管理与连接测试 · Design

> 状态：已确认
> 更新：2026-08-10
> 用户已确认（2026-08-10）：§6 决策 1–9 全部拍板。
> 关联：`docs/prd/service-center/P8-service-registration.md`（已确认 PRD，issue #53）、
> `docs/prd/service-center/P4.4-service-instances.md`（配置驱动多实例，本设计是其运行时动态化后续）、
> `docs/design/service-center/P4.4服务中心接入与凭据Design.md`（凭据方案 A/B 边界，本设计启用其方案 B）、
> `docs/design/model/P6模型Provider与APIKey管理Design.md`（凭据 AES-256-GCM 加密落库成熟方案，本设计复用其纪律）、
> `docs/产品定义.md` §2.3（服务中心责任）、`docs/开发规范.md`（凭据不得落明文）、
> `docs/接口清单.md`（第二大模块欠账表）

## 1. 目标与范围

一句话目标：把服务注册表从 `backend/src/api/v1/dependencies.py:113-137` 的代码硬编码（3 PG + 1 Redis，DSN 走 `OPERMIND_SERVICE_<ID>_DSN` env）改为**运行时动态管理**——运维在服务中心页直接添加/编辑/移除服务，DSN 加密落库、绝不落明文，并提供显式只读连通性测试，新增服务进入既有 `GET /services` 与只读监控/调查链路。

### 做什么
- 服务注册表新增应用库专用表 `service_registry`，存加密 DSN + 掩码尾号 + 类型/标题，支持运行时增删改。
- 凭据方案：DSN AES-256-GCM 加密落库（主密钥 `OPERMIND_SECRET_KEY` 走 env，复用 `src/infrastructure/secrets.py`），接口只回 `has_dsn` + 掩码尾号，不回明文。
- 新增接口：`POST /services`（注册）、`PUT /services/{id}`（改标题/DSN）、`DELETE /services/{id}`（移除）、`POST /services/{id}/test-connection`（显式只读连通性测试）。
- `ServiceRegistry` 支持运行时注册/移除 Connector；已注册服务进入 `GET /services`、详情、活动、监控采样与调查链路。
- 前端服务中心页新增"添加服务"表单、列表项编辑/移除/连接测试；未验证/未配置态诚实标注。

### 明确不做（对齐 PRD）
- 不做 MySQL 真实 Connector（`docs/产品定义.md` §7 未决）。
- 不做身份/权限/多用户。
- 不做告警通道配置（邮件/webhook）。
- 不做运行时可编辑的监控阈值/关注项配置。
- **不改变**既有硬编码实例的读取方式（`OPERMIND_SERVICE_<ID>_DSN` env 兼容保留，未落库实例仍可读）。
- 不把 DSN 明文、完整 DSN、密码或 `sk-` 内容写入日志、Trace、事件、结果、截图或接口响应。

## 2. 设计决策

### D1 · 注册表持久化：DSN 加密落库（启用 P4.4 方案 B 边界）

- **选择**：新增应用库表 `service_registry`，DSN 用 AES-256-GCM 加密后存 `dsn_encrypted` + `dsn_nonce`（Base64）；主密钥来自环境变量 `OPERMIND_SECRET_KEY`，绝不落库/落代码/进日志。
- **为什么**：PRD 要求"运维在页面填 DSN 保存"，而纯环境变量（P4.4 方案 A）无法满足"前端输入"。唯一可行路径是**加密落库**——需用户批准把"凭据不落库"硬规则放宽为"**明文永不落库、密文可落专用表**"。这与 P6 模型 Provider 完全同构，用户 2026-08-06 已为 API Key 拍板，本次把同一放宽应用到服务 DSN。
- **加密纪律（复用 `src/infrastructure/secrets.py`）**：
  - 复用 `load_secret_key()`（`OPERMIND_SECRET_KEY` ≥32 字符，HKDF-SHA256 派生 32 字节）；每条记录独立随机 12 字节 nonce。
  - 主密钥未配置时**拒绝创建/更新 DSN**（返回 `SECRET_KEY_NOT_CONFIGURED` 409）；已落库密文在主密钥缺失时不可解 → 服务诚实降级为不可连接（见 D4 降级策略）。
  - DSN 输入设最小长度校验（≥8），避免极短 DSN 被掩码规则完整暴露。
  - 明文 DSN 只出现在应用服务的加密瞬间；不进入领域对象、日志、Trace、事件、响应、前端持久化。
- **回读**：接口/前端永不返回明文；仅返回 `has_dsn` 布尔与掩码尾号。掩码尾号规则与 P6 一致：`••••` + 末 4 位。**DSN 与 API Key 不同**：DSN 是结构化串，密码位于 userinfo（`@` 之前），末 4 位通常是库名/端口/路径片段（如 `redis://:pass@h:6379/0` 尾段是 db index），**不构成可复用凭据**，故沿用 P6 规则不升级为 P0/P1；但仍会泄露库名/端口片段，§6 决策 4 已向用户说明这一取舍。掩码仅出现在 dedicated 只读接口，绝不进日志/Trace/事件/前端持久化。

### D2 · 数据模型与迁移

新增 `service_registry` 表（应用库）：
- `id` (UUID, PK)、`instance_id` (str, 唯一)、`kind` (str: `postgres`/`redis`)、`title` (str)
- `dsn_encrypted` (str, 可空)、`dsn_nonce` (str, 可空) —— 密文 + nonce；`has_dsn = dsn_encrypted IS NOT NULL`；加 CHECK `(dsn_encrypted IS NULL) = (dsn_nonce IS NULL)` 成对约束（对齐 `model_providers` 同款纪律）
- `dsn_masked_tail` (str, 可空) —— 加密瞬间算好的掩码尾号，回读直接用（避免每次解密）
- `created_at` / `updated_at`
- 迁移：`backend/migrations/` 新增 alembic revision（upgrade/downgrade），对齐既有显式迁移流程。
- **downgrade 语义（P2 修复）**：放宽 CHECK 的迁移与建表同 revision；`downgrade` 在已存在动态 service_id 会话行时**显式拒绝回滚**（`op.get_bind()` 检查 `session_services` 中是否有不在硬编码集合内的 ID，有则 raise），对齐既有迁移"有数据则拒绝回滚"的纪律。
- **必须放宽既有 service_id CheckConstraint（P1 修复）**：`sessions.service_id` 的 `session_service_id_valid`（`20260806_04` 迁移：值域锁死 3 个 PG 硬编码 ID）与 `session_services.service_id` 的 `session_services_service_id_valid`（`20260808_09` 迁移：锁死 4 个硬编码 ID）是 **DB 级 CHECK 白名单**，动态注册的 service_id 写入会触发 `IntegrityError` → `POST /services/{id}/sessions` 与 `POST /sessions`（带动态 service_id）全失败。**本次迁移必须删除/放宽这两个 CHECK 约束**（service_id 本就是普通字符串列、无 FK，放行为无约束即可，与应用层 registry 校验并存）；`models.py` 中对应 CheckConstraint 定义同步移除，`REGISTERED_SERVICE_IDS` 不再作为建表约束来源。

### D3 · `ServiceRegistry` 运行时动态化 + 装配

- `src/domain/services.py` 的 `ServiceRegistry` 增加**可变方法**：
  - `register(connector)` —— 实例 ID 冲突时抛 `ValueError`（应用层转 409）；不冲突则插入并保持注册顺序。
  - `remove(service_id)` —— 从注册表移除；不存在返回 `False`（幂等，应用层转 204）。
  - `list_connectors()` / `get_connector()` / `service_ids()` 保持既有语义（读方取 tuple 快照）。
  - **并发契约**：`list_connectors()` 每次返回新 tuple 快照、写方单次 `dict` 替换，CPython GIL 下读不阻塞写；`MonitorSampler` 后台任务与请求线程共享同一 registry，采样轮次读到的是当时快照，允许新注册延迟一个采样周期。更新 `domain/services.py:194` 的注释不变式（原"只保存经过设计审查的静态 Connector，不提供运行时写入能力"需改为"静态硬编码 + 运行时经白名单类型注册的动态 Connector"）。
- **装配（loader 注入契约，P2 修复）**：`build_v1_services_for_runtime` **不得直接查应用库**——`test_p4_service_center.py:162` 的假 Runtime `session_factory` 一调即抛 `AssertionError`。改为显式注入 `registry_loader: Callable[[], Sequence[ServiceRegistryRecord]] | None` 参数（默认 `None` = 只装配硬编码实例，保持既有测试语义）；生产装配 `build_v1_services()` 传入真实 loader（读 `service_registry` 表，`SQLAlchemyError` → 空列表降级，对齐 `resolve_model_config()` 永不 raise 的既有模式）。
- **共享同一实例**：`V1Services` 中的 `service_center`、`monitor_sampler`、`session_service` 全部复用同一个 `registry` 实例，因此动态注册的服务立即进入列表、详情、活动、会话校验与监控采样链路（`monitoring.py` / `service_center.py` / `services.py` 均通过 `registry.list_connectors()` / `get_connector()` 读取，天然看到运行时变化）。
- `MonitorSampler` 在构造时 `connectors=registry.list_connectors()` 快照——需改为持 `registry` 引用、每轮采样读 `list_connectors()`，否则新注册服务不进入历史监控。**（注意：这是 sampler 的既有快照耦合，必须一并改）**。
- **事件 service_id 白名单（P1 修复）**：`application/services.py:539` 的 `_safe_event_data` 用静态 `REGISTERED_SERVICE_IDS` 白名单过滤事件 `service_id`，动态注册 ID 会被静默丢弃 → Run 事件/Trace 丢失动态服务的服务归属。改为**读运行时 registry 的 `service_ids()`**（若 registry 缺失则退回静态集合），或删除该过滤（`service_id` 已在上游 `_resolve_run_service_id` 校验）。本设计采用"读 registry.service_ids()"。

### D4 · 注册语义与诚实降级

- **注册时不立刻探连接**（PRD 开放问题 Q2，默认采纳"不阻塞创建"）：`POST /services` 保存成功即返回，连接状态由前端在下一次 `GET /services` 读取时探活，页面如实标注"未验证"。
- **诚实降级矩阵**：
  | 场景 | 行为 |
  |---|---|
  | 主密钥未配置 + 注册/更新 DSN | 409 `SECRET_KEY_NOT_CONFIGURED`，不落任何明文 |
  | 主密钥未配置 + 启动加载已落库服务 | 密文不可解 → 该服务以 `dsn=None` 注册，快照 `not_configured`，页面显示"凭据不可解" |
  | 连接失败/超时 | 快照 `unavailable`，不暴露异常详情 |
  | 未验证 | 页面标注"未验证"，不伪造 healthy |
- **实例 ID 唯一**：与既有硬编码实例 ID 也不冲突（注册时同时检查 registry 现有 ID + 硬编码 ID）。重复注册 → 409。
- **实例 ID 格式校验**：仅允许小写字母/数字/连字符/下划线，长度 1–64（对齐 `ServiceDefinitionData.id` 的 `min_length=1, max_length=64` 与 env 命名空间 `OPERMIND_SERVICE_<ID>_DSN` 的兼容形态）；非法格式 → 422。
- **PUT 重置语义**：DSN 更新后连接状态重置为"未验证"并重新探测（与 P4 `health_snapshot()` 一致，下次读取/测试即反映新 DSN）；能力声明 `supported_investigations` 由类型模板派生（postgres/redis 各自固定），**PUT 不接受改能力声明**（PRD 输入含"能力声明"，本设计明确排除，见 §6 决策 7）。

### D5 · 连接测试：显式只读探活

- `POST /services/{id}/test-connection` 复用 P4 的 `health_snapshot()` 只读机制（`SELECT 1` / Redis `PING`，3s 超时，只读事务，不执行任意查询）。
- 结果映射为连接状态 `healthy` / `unavailable` / `not_configured` 与安全原因（分类码如 `timeout` / `connection_refused` / `auth_failed` / `not_configured`，**不暴露 DSN、异常详情或凭据**）。
- 失败不影响其他服务；注册/移除/测试均有明确成功/失败反馈。

### 接口契约（新增公开 API，均走既有 v1 网关，错误码并入既有 `APPLICATION_ERROR_STATUS`）

| 方法 | 路径 | 行为 | 脱敏要求 |
|---|---|---|---|
| POST | `/api/v1/services` | 注册（kind/instance_id/title/dsn）；ID 冲突 → 409；主密钥未配置 → 409 | 入参 DSN 仅加密落库，不入响应/日志 |
| PUT | `/api/v1/services/{service_id}` | 改标题/DSN；dsn 不传=不改；能力声明不可改（类型模板派生）；更新后连接状态重置为未验证；不存在 → 404；主密钥未配置 → 409 | 同上 |
| DELETE | `/api/v1/services/{service_id}` | 移除；不存在仍 204（幂等）；已有关联会话/监控/活动留痕不删 | 无 |
| POST | `/api/v1/services/{service_id}/test-connection` | 显式只读连通性测试；不存在 → 404 | 结果脱敏分类码 |

- `GET /services` / `GET /services/{id}` 结构与既有契约兼容（返回值随注册动态增加）。
- 前端 API 类型由 `npm run generate:api` 生成（`frontend/src/api/v1/generated.ts`），禁止手改。

## 3. 文件改动面

### 后端（backend/）
- **修改** `src/domain/services.py` —— `ServiceRegistry` 增加 `register` / `remove`（可变 + 快照并发契约，更新不变式注释）；新增 `ServiceRegistrationData`（或复用 `ServiceDefinitionData` 扩展字段：`has_dsn` / `dsn_masked_tail`）。
- **修改** `src/infrastructure/persistence/models.py` —— 新增 `ServiceRegistryRecord`；**移除 `sessions.service_id` 与 `session_services.service_id` 的 CheckConstraint**（`REGISTERED_SERVICE_IDS` 不再作为建表约束来源）。
- **新增** `src/infrastructure/persistence/service_registry_repository.py` —— 读写 `service_registry`。
- **新增** `backend/migrations/versions/` revision —— 建 `service_registry` 表（upgrade/downgrade）**+ 放宽 `session_service_id_valid` / `session_services_service_id_valid` 两个 CHECK 约束**。
- **新增** `src/application/service_registration.py` —— 注册/改/删/测试连接应用服务（含 DSN 加密/掩码、实例 ID 唯一与格式校验、诚实降级）。
- **修改** `src/api/v1/routes.py` + `schemas.py` + `resources.py` —— 新增 4 接口 + 服务安全视图含 `has_dsn`/`dsn_masked_tail`。
- **修改** `src/api/v1/dependencies.py` —— 新增 `registry_loader` 注入参数（默认 `None`），`build_v1_services()` 传入真实 loader；`MonitorSampler` 改持 registry 引用。
- **修改** `src/infrastructure/monitoring/sampler.py` —— 每轮采样读 `registry.list_connectors()`。
- **修改** `src/application/services.py` —— `_safe_event_data` 的 service_id 白名单改读 registry `service_ids()`（registry 缺失时退回静态集合）。
- **修改** `src/infrastructure/secrets.py` —— 增加中性别名 `encrypt_dsn`/`decrypt_dsn` + 独立 key-info 派生（保持 `encrypt_api_key`/`decrypt_api_key` 兼容）。
- **修改** `config/config.example.yaml` —— 文档化 `OPERMIND_SECRET_KEY` 同时用于模型 API Key 与服务 DSN 加密（含最小长度与备份提示）。
- **新增** `backend/tests/test_service_registration_api.py`；**修改** `backend/tests/test_p4_service_center.py`（registry_loader 注入契约）、`backend/tests/test_monitoring.py`（sampler 构造签名变更，七处 `connectors=`）、`backend/tests/test_api.py` 等回归。

### 前端（frontend/）
- **修改** `src/features/services/ServiceCenterPage.tsx` —— 添加服务表单、列表项编辑/移除/连接测试按钮、未验证/未配置诚实标注。
- **修改** `src/api/v1/queries.ts`；`generated.ts` 由 `npm run generate:api` 生成。
- **新增/修改** 前端交互测试（`ServiceCenterPage.test.tsx`，MSW mock）。

### 无功能改动部分
- 会话工作台、多 Agent 内核、审批闭环、知识库、Trace 展示（本设计不含凭据展示路径）。

## 4. 可独立验收的改动单元（指引，不写死）

> Design 只给改动单元的验收语义；正式切片拆解、验证命令与提交计划归 `dev-plan` 的 `plan.md`。

建议拆 **3 个独立可验收单元**：
- **U1 加密持久化 + 注册/改/删 API + 约束放宽**：`service_registry` 表迁移 + **放宽 `session_service_id_valid` / `session_services_service_id_valid` 两个 CHECK 约束** + 仓储 + 加密落库 + 动态注册表 + CRUD 接口 + `GET /services` 兼容 + 前端添加/编辑/删除 + `_safe_event_data` 白名单改读 registry。验收语义：保存不落明文、回读无明文、ID 冲突 409、主密钥缺失 409、移除幂等 204、历史留痕保留、动态服务可建会话/进调查、事件 Trace 保留动态服务归属（AC1–AC6/AC8/AC10 主战场）。门禁：迁移（含约束放宽）+ 凭据 + 公开 API + 动态注册表。
- **U2 显式连接测试**：`test-connection` 接口，复用 `health_snapshot()` 只读机制、3s 限时、脱敏分类码。验收语义：可连通→healthy；不可达→unavailable + 安全原因；未配置→not_configured（AC7）。门禁：真实连接（对目标服务只读探活）。
- **U3 监控采样贯通 + 装配 + 回归**：`MonitorSampler` 动态读 registry + `registry_loader` 装配注入 + 前端诚实标注未验证 + 回归（AC9/AC11）。门禁：回归全绿。

## 5. 风险、回滚与门禁

| 风险 | 缓解 |
|---|---|
| 主密钥丢失 → 已存 DSN 不可解 | 诚实降级为 not_configured + "凭据不可解"提示，不崩；提供删除/重配路径 |
| 主密钥泄漏 → 全量可解 | 主密钥只走 `OPERMIND_SECRET_KEY` env（≥32 字符），日志/文档禁打；权限最小化 |
| 动态注册引入任意服务 | 类型白名单（postgres/redis，复用既有 Connector 类型）；实例 ID 唯一 + 格式校验；连接测试只读探活、不执行任意查询 |
| 移除服务后监控/会话引用残留 | 不删历史（service_id 为普通字符串列），列表不再出现即可；动态服务历史会话/监控/活动留痕保留（AC10） |
| 新注册服务不进历史监控 | MonitorSampler 改持 registry 引用、每轮读列表（D3 必须项） |
| 硬编码实例与动态实例 ID 冲突 | 注册时同时查 registry + 硬编码 ID，冲突 409 |
| 动态服务无法建会话/调查（既有 CHECK 白名单） | 迁移放宽 `session_service_id_valid` / `session_services_service_id_valid`（D2 必须项） |
| 动态服务事件/Trace 丢服务归属（既有静态白名单） | `_safe_event_data` 改读 registry `service_ids()`（D3 必须项） |
| 装配直连查库破坏既有测试 | `registry_loader` 显式注入，默认 `None`；`SQLAlchemyError` → 空列表降级（D3 必须项） |

- **回滚**：移除新增 routes 注册 + 回滚 `service_registry` 迁移（`downgrade` 在存在动态 service_id 历史行时拒绝回滚，需先清理或接受保留约束）；`dependencies.py` 回退为纯硬编码装配；`MonitorSampler` 回退快照构造；`_safe_event_data` 回退静态白名单。无既有接口契约破坏（新增均为追加）。
- **门禁项清单**：数据库迁移（`service_registry`）、新增公开 API（4 接口）、凭据（DSN 加密落库，需用户批准放宽"不落库"）、真实连接（test-connection 只读探活）、动态注册表（`ServiceRegistry` 可变）。

## 6. 待用户确认的设计决策

1. **批准服务 DSN 加密落库（放宽"凭据不落库"硬规则为"明文永不落库、密文可落专用表"）**，主密钥 `OPERMIND_SECRET_KEY` 走 env（≥32 字符）；明文仍绝对禁止。代价：主密钥泄漏=全量可解。**（PRD 开放问题 Q1）**
2. **注册时不立刻探连接，默认存为"未验证"态**，由下一次列表读取探活，页面诚实标注。备选：连接失败拒绝创建。**（PRD 开放问题 Q2，推荐前者）**
3. **允许注册类型仅 postgres / redis**（有真实 Connector）；MySQL 出现在前端提示但如实标注"未启用"。**（PRD 开放问题 Q3）**
4. **DSN 掩码尾号规则**：`••••` + 末 4 位（与 P6 API Key 一致）；DSN 输入最小长度 ≥8。已向用户说明：DSN 尾号是库名/端口片段而非密码（密码在 userinfo），不构成可用凭据，但会暴露库名/端口片段，接受此取舍。
5. **移除服务保留历史留痕**：删除仅移除注册表与加密凭据，不删除已有关联的会话/监控/活动记录（AC10）。删除接口幂等（重复删除 204）。
6. **`MonitorSampler` 由构造时快照改为持 registry 引用每轮读取**：这是让动态注册服务进入历史监控的必要改动，涉及既有 sampler 装配微调。
7. **PUT 不接受改"能力声明"**（`supported_investigations`）：能力声明由类型模板派生（postgres/redis 各自固定），PRD 功能 2 输入含"能力声明"但本设计明确排除；如需可改能力声明，须另行 Design。**（PRD 范围收窄，需双写回 PRD）**
8. **迁移放宽既有 `session_service_id_valid` / `session_services_service_id_valid` CHECK 约束**：动态服务才能建会话、进入调查链路（AC4/AC10 前提）。约束由"硬编码 ID 白名单"放宽为"无约束"（service_id 本就是普通字符串列，与应用层 registry 校验并存）。**（数据影响，需双写回 PRD）**
9. **`POST /services` 以 instance_id 唯一作自然幂等**：重复注册同 ID → 409，不再单独要求 `Idempotency-Key`（区别于 P6 Provider 的强制幂等键，因为服务 ID 是用户可见主键）。

> 用户确认后，将本文件顶部 `> 状态：草稿` 改为 `> 状态：已确认`，再放行到 dev-plan。

（2026-08-10 用户已确认全部 9 项决策，本文件已置为"已确认"，放行 dev-plan。）
