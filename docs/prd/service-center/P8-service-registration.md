---
title: 服务中心服务注册——动态接入、管理与连接测试
status: 完成
domain: service-center
phase: P8
issue: 53
updated: 2026-08-11
---

# 服务中心服务注册——动态接入、管理与连接测试 · PRD

## 背景

服务中心是正式产品模块（`docs/产品定义.md` §2.3），第一责任就是"接入和管理服务"。但当前服务注册表**完全硬编码**在 `backend/src/api/v1/dependencies.py:113-137`（3 个 PostgreSQL + 1 个 Redis），DSN 走环境变量 `OPERMIND_SERVICE_<INSTANCE_ID>_DSN`，**没有任何针对服务本身的写接口**——新增服务要改代码 + 加环境变量 + 重启，页面上的"服务接入能力将在后续工作包提供"是实话。

`docs/接口清单.md` 第二大模块把服务注册标为**最大欠账**："`POST /services` 注册服务接口完全不存在，`PUT /services/{id}` 改服务、`DELETE /services/{id}` 移除服务同样缺失；`POST /services/{id}/test-connection` 显式连通性测试也缺失（当前"刷新状态"只是重拉 `GET /services`，不是真探一次连接）"。

P4.4 多服务实例接入（`docs/prd/service-center/P4.4-service-instances.md`）已完成配置驱动多实例，当时明确排除"运行时动态增删实例的完整 CRUD（首版配置驱动，重启生效）"与"方案 B（加密落库）"，并注明"需单独批准放宽'不落库'硬规则"。本 PRD 是它的自然后续：把注册表从代码硬编码变为**运行时动态管理**。

凭据方案可照搬模型 Provider 的成熟落地（`docs/prd/model/P6-model-provider-key-management.md` + `docs/design/model/P6模型Provider与APIKey管理Design.md`）：AES-256-GCM 加密落应用库、主密钥 `OPERMIND_SECRET_KEY` 走环境变量、接口只回 `has_api_key` + 掩码尾号。服务 DSN 与 API Key 同属敏感凭据，应复用同一套加密与脱敏纪律。

关联：`docs/接口清单.md`（第二大模块缺表）、`docs/prd/service-center/P4.4-service-instances.md`（配置驱动多实例已交付）、`docs/prd/model/P6-model-provider-key-management.md`（凭据加密落库成熟方案）、`docs/产品定义.md` §2.3（服务中心责任）、`docs/开发规范.md`（凭据不得落明文）。

## 目标

1. 运维能在服务中心页**动态接入**新服务（PG/Redis，填实例 ID + 标题 + DSN），无需改代码或重启。
2. 已接入服务可**改标题、换 DSN、移除**，凭据安全持久化、绝不落明文。
3. 每个服务有**显式连通性测试**，与只读监控/调查链路一致地诚实降级。

## 用户故事

作为运维工程师，我接入了第二个数据库实例时，应在服务中心页直接"添加服务"，填实例 ID 和 DSN 保存，立刻看到连接状态，而不是改代码加环境变量再重启——以便快速接入新环境并确认连通。

## 范围

### 做什么
- 服务注册表从代码硬编码改为**应用库持久化**，支持运行时动态增删改。
- 凭据方案：DSN 加密落库（AES-256-GCM，主密钥 `OPERMIND_SECRET_KEY` 走 env），接口只回掩码尾号与 `has_dsn`，不回明文 DSN。
- 新增接口：`POST /services`（注册）、`PUT /services/{id}`（改）、`DELETE /services/{id}`（移除）、`POST /services/{id}/test-connection`（显式连通性测试）。
- 前端服务中心页新增"添加服务"表单、列表项编辑/移除、连接测试按钮。
- 已注册服务进入既有 `GET /services` 列表与只读监控/调查链路，与现有服务同等待遇。

### 不做什么（明确排除）
- 不做 MySQL 真实 Connector（`docs/产品定义.md` §7 未决，需先 Design）。
- 不做身份/权限/多用户（`docs/产品定义.md` §7 未决，第四阶段）。
- 不做告警通道配置（邮件/webhook，已决方案是页面内告警）。
- 不做运行时可编辑的监控阈值/关注项配置（接口清单欠账，另行排期）。
- **不做运行时可编辑的能力声明**：`supported_investigations` 由类型模板派生（postgres/redis 各自固定），PUT 仅改标题/DSN，不接受改能力声明（本 PRD 功能 2 输入含"能力声明"，按 Design 决策 7 收窄，需用户确认）。
- 不改变既有硬编码实例的读取方式（`OPERMIND_SERVICE_<ID>_DSN` 环境变量兼容保留，未落库实例仍可读取）。
- 不把 DSN 明文、完整 DSN、密码或 `sk-` 内容写入日志、Trace、事件、结果、截图或接口响应。

## 功能需求

### 1. 注册服务（POST /services）
- **输入**：服务类型（pg / redis）、实例 ID（唯一标识）、标题、DSN（凭据）。
- **行为**：
  - 校验实例 ID 唯一（与既有硬编码实例也不冲突）；类型必须是已有 Connector 的类型。
  - DSN 经 AES-256-GCM 加密落应用库专用表，明文不落库；主密钥未配置时拒绝创建（如实报错）。
  - 注册时是否立刻探连接见「开放问题」Q2——默认允许存为"未验证"态，页面诚实标注。
  - 已注册服务注册进运行时 `ServiceRegistry`，进入 `GET /services` 与只读监控/调查链路。
- **输出**：服务安全视图（id/type/title/连接状态/has_dsn/掩码尾号），不含 DSN 明文。

### 2. 修改服务（PUT /services/{id}）
- **输入**：服务 ID + 可改字段（标题、DSN；能力声明按 Design 决策 7 收窄为不可改，见"不做什么"）。
- **行为**：标题/DSN 更新；DSN 更新走同加密纪律；更新后连接状态重置为"未验证"并重新探测。
- **输出**：更新后的服务安全视图。

### 3. 移除服务（DELETE /services/{id}）
- **输入**：服务 ID。
- **行为**：从注册表移除服务与加密凭据；已有关联的会话/监控/活动留痕不删除（历史不可丢）。重复删除返回 204。
- **输出**：204；列表不再出现该服务。

### 4. 显式连通性测试（POST /services/{id}/test-connection）
- **输入**：服务 ID。
- **行为**：对目标服务发起**显式只读连接测试**（复用 P4 的 `health_snapshot()` 只读机制，3s 超时，不执行任意查询）；返回当前连接状态。
- **输出**：连接状态（healthy / unavailable / not_configured）与安全原因（不暴露 DSN、异常详情或凭据）。

### 5. 前端服务中心接入
- **输入**：服务中心列表页 / 详情页。
- **行为**：列表页提供"添加服务"入口与表单；每项支持编辑/移除/测试连接；新增服务即时出现在列表；未配置/未验证态诚实标注。
- **输出**：可管理的服务中心界面。

## 非功能需求
- **安全**：DSN 绝不落明文；掩码尾号展示；主密钥未配置时拒绝创建；无凭据进日志/Trace/结果/截图/响应；`has_dsn` 只表意不泄露。
- **可靠**：单服务连接失败不影响其他服务；注册/移除/测试均有明确成功/失败反馈。
- **诚实**：未验证/未配置/连接失败如实标注，不伪造连接成功。
- **性能**：连接测试限时（3s）；列表读取为本地库读取，ms 级。

## 数据与接口影响
- 数据：新增服务注册专用表（`service_registry`），存加密 DSN + 掩码尾号 + 类型/标题；涉及数据库迁移。**同时放宽 `sessions.service_id` / `session_services.service_id` 的既有 CHECK 白名单约束（原锁死 4 个硬编码 ID），否则动态注册服务无法创建会话、进入调查链路（按 Design 决策 8）。**
- 接口：新增 `POST /services`、`PUT /services/{id}`、`DELETE /services/{id}`、`POST /services/{id}/test-connection`；`GET /services` 结构与既有契约兼容（返回值随注册动态增加）。
- `POST /services` 以 instance_id 唯一作自然幂等（重复注册同 ID → 409，不单独要求 `Idempotency-Key`，按 Design 决策 9）。

## 验收标准
- [ ] AC1: 当运维通过 `POST /services` 注册一个 pg 服务（合法 ID + DSN）时，应返回服务安全视图（id/type/title/has_dsn/掩码尾号），且响应不含 DSN 明文。
- [ ] AC2: 当注册的服务 ID 与既有实例冲突时，应返回明确错误，不创建。
- [ ] AC3: 当主密钥未配置时注册新服务，应拒绝创建并如实报错，不落任何明文 DSN。
- [ ] AC4: 当已注册服务出现在 `GET /services` 时，应与其他服务同列，连接状态正确。
- [ ] AC5: 当 `PUT /services/{id}` 更新标题/DSN 时，应更新成功且连接状态重置为未验证。
- [ ] AC6: 当 `DELETE /services/{id}` 移除服务时，应返回 204 且列表不再出现；重复删除仍 204。
- [ ] AC7: 当 `POST /services/{id}/test-connection` 对可连通服务发起时，应返回 healthy；对不可达服务返回 unavailable 与安全原因，不暴露 DSN/异常。
- [ ] AC8: 应用库、日志、Trace、事件、结果、截图、接口响应中不得出现 DSN 明文、密码或 `sk-` 内容。
- [ ] AC9: 未验证/未配置的服务在前端应如实标注，不伪造连接成功。
- [ ] AC10: 移除服务后，其历史会话/监控/活动留痕应保留。
- [ ] AC11: 回归 —— 既有硬编码实例（环境变量 DSN）仍可读取；`test_p4_service_center.py`、`test_postgres_connector.py`、`test_redis_service_monitor.py` 相关全绿；前端 `typecheck`/`test`/`build` 通过。

## 边界与约束
- 安全边界：DSN 加密落库、主密钥走 env、接口只回掩码；纯只读调查，注册不引入写目标服务的路径。
- 降级策略：主密钥未配置 → 拒绝创建（不落明文）；未验证 → 诚实标注；连接失败 → unavailable；单服务故障不影响其他。
- 兼容性：环境变量 DSN 的硬编码实例兼容保留；既有 `GET /services` 契约兼容；mock 模式行为不变；MySQL 不新增。

## 完成定义（DoD）
- [ ] 全部 AC（AC1–AC11）通过
- [ ] 相关回归测试全绿
- [ ] `git status` 只出现本 PRD 允许的文件
- [ ] 服务注册表持久化迁移执行成功，凭据无明文落库/日志/截图/响应
- [ ] 连接测试只做只读探活，不执行任意查询
- [ ] 前端 `typecheck` / `test` / `build` 通过

## 开放问题
1. **DSN 存哪**：默认采用模型 Provider 成熟方案（AES-256-GCM 加密落库，主密钥 `OPERMIND_SECRET_KEY` 走 env）。备选：保持环境变量注入、UI 只声明服务 ID 与标题，凭据仍由运维注入。→ 推荐前者（与模型设置一致），需用户确认放宽"不落库"硬规则。
2. **注册时是否立刻探连接**：默认**不阻塞创建**——允许存为"未验证"态，页面诚实标注。备选：连接失败拒绝创建。→ 推荐前者（更实用），需用户确认。
3. **允许注册哪些类型**：默认 PG / Redis（有真实 Connector）；MySQL 出现但如实标注"未启用"。→ 需用户确认。
4. **注册表持久化的迁移**：新增服务注册表与迁移方式（对齐 alembic 既有显式迁移流程）。→ 执行期 Design 定。**（Design 决策 8：迁移同时放宽 `session_service_id_valid` / `session_services_service_id_valid` 两个 CHECK 约束，动态服务才能建会话/进调查链路。）**
5. **能力声明是否可编辑**：本 PRD 功能 2 输入含"能力声明"，Design 决策 7 收窄为不可改（类型模板派生）。→ 需用户确认。
6. **掩码尾号规则**：DSN 采用 `••••` + 末 4 位（与 P6 API Key 一致）；DSN 尾号是库名/端口片段而非密码，不构成可用凭据，但会暴露库名/端口片段。→ 需用户确认。

## GitHub Issue（已确认后回填）
- issue：#53（https://github.com/wzhwwwzzzhhh/oper-mind/issues/53）
- 状态同步：issue 状态与 PRD 状态一致（已确认=open，完成=closed）；中间过程留在 workpack。
