# P7 数据库深度只读诊断——锁与连接池 Design

> 状态：已确认
> 更新：2026-08-08
> 关联：`docs/prd/session/P7-db-lock-connection-diagnostics.md`（已确认，issue #44）、
> `docs/prd/session/P4.2-db-agent-real.md`（双模式、只读引擎、DSN 来源、超时与降级，本 Design 沿用）、
> `docs/产品定义.md`（§2.2 证据摘要可审计、§5 安全边界）、`docs/开发规范.md`（§2/§3/§5/§6）、
> `docs/架构与开发路径.md`（一条主脊、工具网关接缝）、
> `backend/src/tools/db_tools.py`、`backend/src/agents/db_agent.py`、`backend/src/infrastructure/services/postgres_engine.py`、
> `backend/src/core/tool_gateway.py`、`backend/tests/test_db_tools_real.py`。

## 1. 目标与范围

在既有 P4.2 双模式只读工具（`explain_sql` / `show_index` / `show_create_table`）基础上，
为会话 DBAgent 新增**两个只读诊断工具**，补齐慢查询排障中两类现有工具看不到的维度：

1. **锁诊断**：查看当前锁与锁等待，识别阻塞链（阻塞源头、等待时长），输出结构化脱敏事实；
2. **连接池诊断**：统计连接总数/活跃/空闲/等待、最大连接数与利用率，输出结构化脱敏事实。

全程只读与脱敏：不杀锁、不 `terminate`、不修改连接；结果不含用户名、客户端 IP、原始 SQL、
application_name 与凭据；Trace 只展示收敛摘要。

### 做什么

- 新增 `check_lock_status` 工具（锁诊断，只读）：查当前锁与锁等待，识别阻塞链。
- 新增 `check_connection_pool` 工具（连接池诊断，只读）：统计连接占用与利用率。
- 双模式：mock 模式走确定性场景数据（沿用 `get_active_scenario()` 判定，S1–S4 评测路径不变）；
  真实模式走真实 PostgreSQL 只读系统目录。
- 复用 P4/P4.2 已验证资产：`load_service_dsn(service_id)` 连接来源、只读引擎、
  `SET TRANSACTION READ ONLY`、3s 超时、三态降级（成功/未配置/不可用）。
- 结构化输出：工具内部用 Pydantic 组装事实，格式化后返回给大脑；Trace 经 `audit_summary()`
  只展示脱敏摘要。
- 工具经 `DBAgent` 显式注册进 `ToolRegistry`，走既有 `ToolGateway` 白名单准入/参数校验/限时/脱敏。

### 明确不做

- 不做写操作：不杀锁、不 `terminate` 会话、不修改连接（写能力属受控动作，后续另行 Design）。
- 不做容量诊断（库/表大小、膨胀率）、索引效用分析——后续切片。
- 不做 MySQL/Redis 同型诊断（本 PRD 仅 PostgreSQL）。
- 不做 `EXPLAIN ANALYZE`。
- 不新增公开 REST API、不新增配置项、不新增凭据、不新增数据库迁移。
- 不改 `data/mock_db.py`、`data/scenarios.py`、S1–S4 评测路径。
- 不把 `pg_stat_activity` 明细行（用户名、客户端 IP、原始 SQL、application_name）暴露到
  Trace、事件、结果或前端。
- 不动前端（接口契约不变，Trace 展示不新增字段）。

## 2. 设计决策

### 2.1 模式判定（沿用 P4.2，零改动）

- `get_active_scenario()` 非 None ⇒ mock 模式，返回确定性场景事实。
- `get_active_scenario()` 为 None ⇒ 真实模式，走真实 PostgreSQL 只读分支。
- 两个新工具的 mock 分支只在本工具模块内定义确定性映射，**不改动** `data/mock_db.py`、
  `data/scenarios.py`；因 S1–S4 评测不调用这两个新工具，评测路径行为完全不变（AC4）。

### 2.2 连接来源与引擎（复用 P4.2，零新增配置）

- 复用 `db_tools._real_connection(service_id)`：`load_service_dsn(service_id)` → 无 DSN 返回 None；
  `create_read_only_postgres_engine(dsn)`（psycopg + `connect_timeout=3` + `statement_timeout=3000`）+ `SET TRANSACTION READ ONLY`。
- 每次调用现取 DSN、现建短生命周期连接，不跨 Run 持有引擎单例（与 P4.2 一致）。
- 无 DSN → 「数据库未配置，无法查询」（service_id 缺失 → 「数据库未选择目标服务」）；
  连接失败/超时 → 「数据库不可用」，均不抛异常、不泄露异常详情（AC7）。

### 2.3 锁诊断工具 `check_lock_status`

- **输入**：可选 `database`（数据库名过滤，默认按 Design 决策的范围），用标识符正则校验
  （沿用 `_IDENTIFIER_RE`），非法值拒绝不触库。
- **行为**：只读查询 `pg_locks` + `pg_stat_activity`，识别阻塞链：
  - 被阻塞会话 = `pg_locks` 中 `NOT granted` 且 `state='active'` 的会话；
  - 阻塞源头 = 通过 `pg_blocking_pids(blocked_pid)` 找到持有锁的会话；
  - 每条链输出：阻塞时长（被阻塞会话 `query_start` 起）、锁类型/模式、相关对象名
    （`pg_class.relname`，非 relation 锁取 `locktype`）、阻塞源头事务运行时长
    （`pg_stat_activity.xact_start` 起）。
  - **默认范围**：按「待用户确认 1」，默认限定**当前连接数据库**；真实分支通过
    `SELECT current_database()` 取当前库名作为默认 `:database` 绑定值（不需解析 DSN）。
- **查询（真实分支，全参数化）**：
  ```sql
  SELECT b.pid AS blocked_pid,
         EXTRACT(EPOCH FROM (now() - b.query_start))::int AS blocked_seconds,
         bl.locktype, bl.mode AS lock_mode,
         COALESCE(rel.relname, bl.locktype) AS object_name,
         (SELECT max(EXTRACT(EPOCH FROM (now() - a.xact_start))::int)
            FROM pg_stat_activity a
           WHERE a.pid = ANY(pg_blocking_pids(b.pid))) AS blocker_xact_seconds
    FROM pg_locks bl
    JOIN pg_stat_activity b ON b.pid = bl.pid
    LEFT JOIN pg_class rel ON rel.oid = bl.relation
   WHERE NOT bl.granted AND b.state = 'active'
     [AND b.datname = :database]
  ```
  另发一条聚合查询得到锁模式分布（`GROUP BY bl.mode`），供收敛摘要使用。
- **输出（结构化）**：`LockWaitStatus` Pydantic 模型：
  - `status: ok | not_configured | unavailable`
  - `message: str`（降级/无等待文案）
  - `chain_count: int`（等待链数量，无等待 = 0）
  - `chains: list[LockWaitChain]`：`{ blocked_seconds, blocker_xact_seconds, lock_type, lock_mode, object_name }`
  - `lock_mode_distribution: dict[str, int]`
- **诚实**：无锁等待时 `chain_count=0`，message 为「无锁等待」，不伪造（AC1）。
- **脱敏**：不选取 `usename`、`client_addr`、`query`、`application_name`；对象名只取表名
  （可展示的收敛信息），不展示 PID 明细到 Trace（AC2/AC6）。

### 2.4 连接池诊断工具 `check_connection_pool`

- **输入**：无（默认全库统计，对齐 PRD 功能需求 2）。
- **行为**：只读统计当前连接占用：
  - `total = count(*)`（`pg_stat_activity` 当前连接数）；
  - `active` = `state='active'` 计数；`idle` = `state='idle'` 计数；
  - `waiting` = `wait_event_type IS NOT NULL AND state <> 'idle'` 计数（PRD 开放问题的口径，见决策 2）；
  - `max_connections` = `pg_settings.setting`（`name='max_connections'`）；
  - `utilization = total / max_connections`（0–1 浮点）；
  - 健康档位：`utilization >= 1.0` → 已耗尽；`utilization >= 0.8` → 接近上限；否则 正常。
- **查询（真实分支，全参数化）**：
  ```sql
  SELECT count(*) AS total,
         count(*) FILTER (WHERE state = 'active') AS active,
         count(*) FILTER (WHERE state = 'idle') AS idle,
         count(*) FILTER (WHERE wait_event_type IS NOT NULL AND state <> 'idle') AS waiting
    FROM pg_stat_activity;
  SELECT setting::int AS max_connections FROM pg_settings WHERE name = 'max_connections';
  ```
- **输出（结构化）**：`ConnectionPoolStatus` Pydantic 模型：
  - `status: ok | not_configured | unavailable`
  - `message: str`
  - `total_connections / active / idle / waiting / max_connections: int`
  - `utilization: float`（0–1，如 0.95）
  - `health: 正常 | 接近上限 | 已耗尽`（由 `utilization` 档位映射，文案见 §2.4）
- **诚实**：利用率如实计算（`total/max_connections`），超限/接近如实标注（AC3）。

### 2.5 脱敏、审计与 Trace

- 工具返回格式化字符串给大脑（与既有工具一致）；格式化字符串**不含**用户名/IP/原始 SQL/DSN/凭据。
- 工具定义 `audit_summary()`，返回收敛摘要（如「锁等待链 2 条，最长阻塞 15 分钟」/
  「连接利用率 95%，接近上限」），供 `ToolGateway` 的 `detail` 使用；网关再经 `desensitize()` 兜底。
  前端 Trace 只展示该脱敏摘要，不展示明细行（AC8）。
- 凭据只走 `load_service_dsn()` 读取，不进日志/结果/Trace/响应（沿用 P4.2 已验证行为）。

### 2.6 注册与装配

- `DBAgent.__init__` 中新增：
  `tools.register(CheckLockStatusTool(service_id))`、`tools.register(CheckConnectionPoolTool(service_id))`。
- 不改 `build_coordinator` / `CoordinatorAgent` / `DBAgent` 构造签名；service_id 沿用现有传参。
- 不改 `ToolGateway`、`ToolRegistry`、`coordinator_executor._event_data`（审计摘要机制已有）。

### 2.7 接口契约

- **无，接口契约不变**：不新增公开 REST API；`GET /services`、会话/Run/Trace 契约均不变。
- 数据：无新增持久化、无数据库迁移。
- Trace：复用现有事件模型与 `audit_summary` 通道，不新增字段。

## 3. 文件改动面

### 后端

- `backend/src/tools/db_tools.py`（修改）：新增 `LockWaitStatus` / `ConnectionPoolStatus` /
  `LockWaitChain` Pydantic 模型；新增 `CheckLockStatusTool`、`CheckConnectionPoolTool`
  （含 mock 分支、真实查询分支、`audit_summary()`）；复用 `_real_connection`、`_is_identifier`。
- `backend/src/agents/db_agent.py`（修改）：注册两个新工具。
- `backend/src/scenarios/db_diagnosis.py`（修改，可选）：SYSTEM_PROMPT/TOOL_CALLING_EXAMPLE
  追加一行锁/连接池工具引导（仅提示、不改 mock 数据，不影响 S1–S4 确定性）。
- `backend/tests/test_db_lock_pool_tools.py`（新增）：见 §4。
- 回归：`backend/tests/test_db_tools_real.py`、`test_tool_gateway.py`、`test_agent_gateway.py`、
  `test_p2b_tool_trace.py`、`test_p2_api_v1.py` 等。

### 无功能改动

- 前端零改动（无公开 API、无 Trace 字段变化）。
- `data/mock_db.py`、`data/scenarios.py`、迁移、配置均不改。

## 4. 切片与验证（指引，不写死）

建议拆 **2 片**：

- **S1：两个只读工具 + 注册（后端）**。覆盖 AC1–AC3、AC5–AC7（真实分支查询/降级/只读、
  锁等待链识别、连接池统计与健康档位）。验证：`..\.venv\Scripts\python.exe -m pytest tests/test_db_lock_pool_tools.py -q`。
- **S2：mock 分支锁定 + 审计摘要 + 回归**。覆盖 AC4、AC8、AC9。验证：
  `..\.venv\Scripts\python.exe -m pytest tests -q`（全量回归）、`git diff --check`。

涉及门禁项：**新增 Tool（真实库只读查询）** ⇒ 必须先 Design → Review → 用户确认。

## 5. 风险、回滚与门禁

| 风险 | 缓解 |
|---|---|
| 真实库 `pg_stat_activity` 对普通角色的可见性有限（看不到其他会话） | 查询为空时如实返回（无等待/低占用），不伪造；文档标注需具备 `pg_read_all_stats` 或相当权限才能看到全量会话 |
| 阻塞链查询漏判/误判 | 以 `pg_locks` 未授权锁 + `pg_blocking_pids` 为准，聚合输出有限字段，有测试保护 |
| 对象名（表名）可能含敏感业务名 | 只取表名作收敛对象标识，不上用户/IP/SQL；仍过网关 `desensitize()` 兜底 |
| mock 分支伪造"实时"语义 | mock 分支返回确定性场景事实，且不标注为实时监控；S1–S4 评测不调用新工具 |
| 每 Run 现建连接开销 | 与 P4.2 相同，短生命周期、低频诊断场景可接受 |

- 回滚：删除两个新工具类与注册即回退（无迁移、无公开 API、无配置变更）。
- 门禁项清单：新增 Tool（真实库只读查询）⇒ Design → Review → 用户确认；未新增公开 API/迁移/凭据/配置。

## 6. 待用户确认的设计决策

1. **锁诊断默认范围**：默认**当前连接数据库**（DSN 指向的库，降低跨库对象名暴露），
   可选 `database` 参数过滤；不做按表过滤（后续切片）——是否确认？
2. **连接"等待"判定口径**：`wait_event_type IS NOT NULL AND state <> 'idle'` 计为等待——是否确认？
3. **健康档位阈值**：利用率 `>=100%` 已耗尽、`>=80%` 接近上限、否则正常——是否确认？
4. **工具命名**：`check_lock_status` / `check_connection_pool`（对齐既有 `explain_sql` 动词风格）——是否确认？
5. **mock 分支数据**：新工具 mock 分支在工具模块内定义确定性映射，**不改** `data/scenarios.py`/
   `data/mock_db.py`；锁诊断 mock 如实返回「无锁等待」，连接池按场景返回确定性占用——是否确认？
6. **服务中心服务详情页不同步展示**（PRD 开放问题：页面展示属后续切片）——是否确认？
