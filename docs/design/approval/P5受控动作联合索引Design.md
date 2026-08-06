# P5 受控动作联合索引 Design

> 状态：已确认
>
> 关联 PRD：`docs/prd/approval/P5-controlled-action-real.md`
>
> 本文只确认 P5 第一个受控写动作的技术边界，不扩大为通用 SQL 执行能力。

## 1. 设计结论

P5 只实现一个代码内固定动作：对受控靶场 PostgreSQL 的固定业务对象创建固定联合索引，并通过独立只读 Verify 确认索引存在。执行目标使用独立的静态 `postgres-target` 服务标识，不能从 `postgres-production`、`postgres-staging` 或用户请求中选择。

动作链路为：

```text
结构化缺索引信号
→ 服务器生成不可编辑提案
→ local_operator 审批
→ 二次确认执行
→ 执行器重查前置条件
→ 固定 DDL 写入受控靶场
→ 独立只读 Verify
```

没有结构化信号、没有受控靶场配置、目标不是静态靶场或前置条件不满足时，不执行任何变更。

## 2. 固定动作定义

### 2.1 动作身份

- `action_id`：`postgres.orders_compound_index_rebuild.v1`
- `target_service_id`：`postgres-target`
- `target_schema`：`public`
- `target_table`：`orders`
- `target_columns`：`(customer_id, created_at)`，顺序固定
- `target_index_name`：`idx_orders_customer_created_at`
- `verification_plan`：固定为“确认目标表存在”“确认固定索引存在”“只读执行计划确认索引可用”三项摘要

这些值由服务端代码常量提供。提案的 `target` 只保存脱敏后的结构化字段：服务标识、schema、表、列组合和索引名，不保存 DSN、SQL 原文、查询原文或连接细节。前端不能编辑 `target`、`action_id` 或 `verification_plan`。

### 2.2 触发资格

只有当 `DiagnosisResultData` 中存在经过 DBAgent 只读工具收敛的缺索引/seq scan 信号，并且该信号的结构化目标与上述固定对象完全匹配时，才生成提案。仅有自然语言报告、用户输入中出现“建索引”、慢查询文本或无法验证的对象名，不得触发提案。

提案必须绑定来源 Run，并使用该结果中已有的合法 root cause/evidence 标识；缺少结构化证据时返回 `None`。同一 Run 只允许一个提案，依赖既有唯一约束和事务内创建逻辑。

mock 模式始终不生成提案；target 模式只有固定对象信号满足时才生成提案。

## 3. 受控靶场与凭据边界

### 3.1 静态目标

- 受控靶场服务 ID 固定为 `postgres-target`。
- 靶场服务必须由后端静态注册表显式装配。
- `postgres-production` 和 `postgres-staging` 是只读服务实例，永远不是动作执行目标。
- 执行器不接受请求传入的 service ID、DSN、URL、schema、表名、列名、索引名或 SQL。
- 执行器收到任何非 `postgres-target` 提案时抛出 `ActionPreconditionBlockedError`，不建立写连接、不发送变更。

### 3.2 凭据

- 靶场 DSN 仅从 `OPERMIND_SERVICE_POSTGRES_TARGET_DSN` 读取。
- DSN 不进入领域对象、提案、数据库普通字段、事件、日志、Trace、API 响应或前端状态。
- 未配置 DSN 时执行安全终止为 `blocked`；不回退到生产/预发布 DSN。
- 执行器每次动作/Verify 新建短生命周期连接或 Engine，完成后释放，不持有跨 Run 的连接单例。

## 4. 执行器行为

### 4.1 前置复核

执行器在真正动作前重新计算固定动作摘要，并校验提案的 `action_id`、`mode`、`target`、`verification_plan`、`source_run_id` 和 `action_digest` 与服务端固定模板一致。前端提交的提案快照、任何客户端字段或仅凭前端不可编辑约束都不能作为执行授权。

随后通过独立短生命周期连接读取固定对象状态。PostgreSQL 标识符不使用普通绑定参数；实现只允许代码内常量对应的固定系统目录查询：

1. `public.orders` 是否存在。
2. `public.idx_orders_customer_created_at` 是否已存在。

只有“表存在且索引不存在”同时成立，才允许进入固定 DDL。其他结果均抛出 `ActionPreconditionBlockedError`，持久化为 `blocked`，并保证不会发送 DDL。

标识符不能由外部字符串直接拼接。执行器只使用代码内常量映射到固定 SQL 模板；不提供标识符格式化器或通用 SQL 参数。前置检查连接在进入 DDL 连接前关闭。

### 4.2 白名单写动作

动作只允许执行代码内固定的 PostgreSQL 语句：

```sql
CREATE INDEX CONCURRENTLY idx_orders_customer_created_at
ON public.orders (customer_id, created_at)
```

该语句不从 API、模型、提案字段或聊天文本读取。执行连接使用 3 秒连接超时和 3 秒 statement timeout，并显式启用 autocommit，确保语句不在显式事务块中执行。执行器不执行其他 DDL、DML、事务控制语句或网络命令。`CREATE INDEX CONCURRENTLY` 的 PostgreSQL 事务限制由执行器使用独立连接处理，不与应用数据库事务复用。执行成功、失败、超时或取消后都必须关闭连接并释放 Engine；不会自动重试写入。

成功返回固定脱敏摘要，例如“受控靶场固定联合索引动作已提交”，不返回驱动消息或 SQL。

### 4.3 独立 Verify

Verify 必须使用新的短生命周期只读连接，不能复用执行连接或执行结果作为证明。验证内容为：

- 固定索引存在；
- 固定索引处于有效状态；
- 固定目标的只读 EXPLAIN 结果表明计划可使用该索引，或在测试/靶场限制下以索引存在且有效作为等价可验证事实。

Verify 只返回布尔/枚举事实和脱敏摘要。通过则返回 `verified`；失败则返回 `ActionVerificationFailedError` 对应的 `failed`，不自动回滚。

若 DDL 超时或失败后发现固定索引存在但状态为无效，执行记录进入 `failed`，Verify 事实标记为未通过；系统不自动删除、重建或回滚该索引，只在安全摘要中提示需要人工处置。有效索引已存在属于执行前置条件不满足，进入 `blocked` 且不发送 DDL。

## 5. 失败与安全映射

| 情况 | 结果 | 是否发送变更 |
|---|---|---|
| mock 模式 | 不生成提案 | 否 |
| 无缺索引结构化信号 | 不生成提案 | 否 |
| 非 `postgres-target` 目标 | `blocked` | 否 |
| 靶场 DSN 未配置 | `blocked` | 否 |
| 表不存在 | `blocked` | 否 |
| 索引已存在 | `blocked` | 否 |
| 连接失败/超时 | `blocked` 或 `failed`，按执行阶段映射 | 否或无法确认，均不重试写入 |
| 固定 DDL 执行失败 | `failed` | 可能已由数据库处理，页面只显示安全摘要 |
| Verify 不通过 | `failed` | 不自动回滚 |

所有持久化 error code/message、事件摘要、Trace 和 API 输出均使用固定安全文案，不包含 DSN、主机、端口、密码、原始 SQL、原始异常或内部请求 ID。

## 6. 装配与接口影响

- 复用 `ControlledActionExecutor`、`ActionApplicationService` 和既有 action API。
- 新增具体 PostgreSQL 受控执行器，通过依赖注入装配；不改变通用审批状态机的公开接口。
- 执行器的服务端固定模板校验必须在每次 `execute` 和 `verify` 前执行；提案摘要不匹配时按 `blocked` 处理。
- 受控靶场可以作为静态 Connector/目标端口装配，但其执行能力只能通过具体执行器暴露，不能复用只读 Service Connector 作为写接口。
- 不新增 action 表、不新增迁移、不新增公开 API。
- mock 模式下不装配有效执行器，且 `maybe_create_proposal_in_transaction` 不产生提案。

## 7. 测试门禁

必须提供确定性 mock Engine/连接端口测试，不连接真实生产、预发布或用户服务。至少覆盖：

- 固定信号生成提案、无信号不生成、mock 不生成；
- 提案目标和 action digest 固定且不可编辑；
- 服务端篡改 `action_id`、目标、Verify 计划或摘要时拒绝执行，且拒绝前不建立写连接；
- 生产/预发布目标拒绝，拒绝前不执行 SQL；
- 靶场未配置、表不存在、索引已存在均为 `blocked`；
- 固定动作成功后独立 Verify 为 `verified`；Verify 失败为 `failed` 且不回滚；
- `CREATE INDEX CONCURRENTLY` 在 autocommit 独立连接执行，成功/失败/超时/取消后连接均释放；
- DDL 失败留下无效索引时不自动清理，进入 `failed` 并返回脱敏人工处置提示；
- 连接失败/超时安全收敛；
- DSN、SQL 原文、原始异常不进入 API、事件、Trace 或持久化字段；
- 既有 action 状态机、P4.2 只读工具、mock S1–S4 回归全绿；
- 前端审批 → 二次确认执行 → Verify 全流程交互测试。

## 8. Review 记录

- PRD：`docs/prd/approval/P5-controlled-action-real.md`
- 本 Design：`docs/design/approval/P5受控动作联合索引Design.md`
- 当前状态：待用户确认后创建 workpack 并实施。
