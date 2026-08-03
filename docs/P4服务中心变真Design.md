# P4 服务中心变真 · Design（接真实 PostgreSQL 只读服务）

> 状态：**草案，待 Review 与用户确认后实施。**
> 更新：2026-08-03
> 关联：路线图 P3.5（服务中心变真，因前端重构让位延后，现启动）

## 1. 目标与范围

把服务中心从「空 ServiceRegistry + 空态前端」变成「第一个真实服务可摸」。
本阶段只接 **1 个 PostgreSQL 只读服务**，跑通「服务注册 → 只读快照 → 前端展示」全链路，
验证连接/凭据/脱敏/只读的安全边界。MySQL、Redis 后续按同一模式复制。

### 范围（做什么）
- 实现 `PostgresServiceConnector`（实现现有 `ServiceConnector` 协议）
- 装配进 `ServiceRegistry`，替换当前的 `ServiceRegistry(())`
- `health_snapshot()` 从真实 PostgreSQL 读取有限只读快照：
  - 连接状态（availability）
  - 基础性能标量（p50/p95/慢查询计数/超时计数）
  - 数据库高层信号（是否慢查询 / 缺索引）
- 前端服务中心/详情页从「空态」变为「真态」（接口契约不变，无需改前端）

### 不做什么（明确排除）
- 不接 MySQL / Redis（后续按同模式复制）
- 不做完整历史监控趋势（缺接口，P5 才做）
- 不做服务注册/编辑/停用的动态接口（静态注册）
- 不做凭据落库 / 落代码 / 落文档
- 不引入 DDL/DML/写操作（纯只读）

## 2. 凭据方案（安全硬规则）

- PostgreSQL 连接凭据**只从当前进程环境变量读取**，如：
  ```
  OPERMIND_PG_DSN=postgresql://user:pass@host:5432/dbname
  ```
  或拆分：
  ```
  OPERMIND_PG_HOST / OPERMIND_PG_PORT / OPERMIND_PG_DB / OPERMIND_PG_USER / OPERMIND_PG_PASSWORD
  ```
- 凭据**绝不进入**：仓库、文档、日志、Trace、事件、结果、截图、Git、前端响应。
- 配置读取走现有 `src/config.py` 的 `_apply_env_overrides` 机制，不新增明文配置。
- 无环境变量时：Connector 报告 `availability=not_configured`，**不崩溃、不伪造**（前端显示"未配置"）。

## 3. Connector 结构（工程规则）

```python
# backend/src/infrastructure/services/postgres_connector.py
class PostgresServiceConnector:
    """静态注册的 PostgreSQL 只读 Connector，实现 domain.services.ServiceConnector。"""

    def __init__(self, settings: PostgresSettings) -> None: ...
    def definition(self) -> ServiceDefinitionData: ...      # 静态身份
    def health_snapshot(self) -> ServiceSnapshotData: ...    # 读真 PG 有限快照
```

- **只读**：连接用 `SET TRANSACTION READ ONLY` / 或 `autocommit=False` + 只发 SELECT；绝不执行写。
- **限时**：每次快照读取有超时（如 3s），超时 → `availability=unavailable`，不阻塞。
- **脱敏**：快照字段只含收敛标量（p50/p95/计数），不含 SQL、对象名、凭据、原始日志。
- **确定性装配**：经 `dependencies.py` 显式构造，不通过 LLM/Agent 隐式调用。
- **失败诚实**：连接失败/超时/无凭据 → 对应状态（unavailable/not_configured），不抛异常炸页面。

## 4. 快照读取内容（有限、脱敏）

`health_snapshot()` 返回 `ServiceSnapshotData`：

| 字段 | 来源（只读查询） | 脱敏 |
|---|---|---|
| availability | 连接测试 `SELECT 1` + 指标读取是否成功 | — |
| p50_ms / p95_ms | `pg_stat_statements` 或 `pg_stat_database` 的调用延迟（有限窗口） | 仅数值 |
| slow_query_count | 慢查询统计（如 `pg_stat_activity` 或系统表计数） | 仅计数 |
| timeout_count | 超时计数（如可用） | 仅计数 |
| database.signal | 从慢查询/缺索引信号收敛的高层状态 | 不含 SQL/对象名 |

**不读取**：具体慢 SQL 原文、表结构、索引明细、用户数据、系统目录原始内容。
（深度的 explain/索引分析仍由会话里的 DBAgent + 网关工具承担，不走服务快照。）

## 5. 装配与前端影响

### 后端装配
```python
# src/api/v1/dependencies.py
ServiceRegistry((
    PostgresServiceConnector(postgres_settings),
    # 后续: MySqlServiceConnector(...), RedisServiceConnector(...)
))
```

### 前端影响
- 接口契约**完全不变**（`GET /services`、`GET /services/{id}` 结构照旧）
- 前端无需改动：服务中心/详情页从空态自动变真态（因为有数据了）
- 若未配置凭据：前端显示"未配置"空态（诚实，不伪造）

## 6. 测试策略

- **单元测试**（不连真库）：用假连接/注入，验证 Connector 各分支：
  - 无凭据 → not_configured
  - 连接失败 → unavailable
  - 超时 → unavailable
  - 正常 → healthy + 各指标填充
  - 脱敏：快照不含 SQL/对象名/凭据
- **现有回归**：P2/P3 测试全绿（服务接口契约不变）
- **不做**：连真实 PG 的集成测试（本地手动验证）

## 7. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 凭据泄露 | 只环境变量；测试注入假值；快照脱敏 |
| 慢查询阻塞 | 每次快照 3s 超时 + 只读事务 |
| 真实服务被误写 | Connector 严格只读（无 DML/DDL 代码路径） |
| 无凭据环境炸 | 缺凭据 → not_configured 空态，不崩 |
| 装配复杂化 | 复用现有 ServiceRegistry/ServiceConnector 协议，不新造轮子 |

回滚：移除 Connector 装配，回到 `ServiceRegistry(())` 空态，接口不变。

## 8. 已确认决策

1. ✅ 接 PostgreSQL 只读诊断作为第一个真实服务
2. ✅ 凭据用单一环境变量 `OPERMIND_PG_DSN`
3. ✅ 指标深度：SELECT 1 连通性 + pg_stat_database 基础行；扩展可用才读 p50/p95/慢查询，读不到留 None
4. ✅ 本阶段只做「服务快照变真」，DBAgent 工具连真库放到 P4.2 单独 Design

## 9. 实施中发现的既有设计缺陷（P4 需一并修复）

> 2026-08-03 复核发现，这两处是 P2 演示遗留，会阻塞服务中心 API 全链路。

1. **`schemas.py` 写死 P2 演示字面量**：
   `ServiceInvestigationResource.id: Literal["orders_slow_query.v1"]`、
   `ServiceResource.id: Literal["order-service"]`、`kind: Literal["postgres_orders_demo"]`
   → 改为通用字符串字段（id/kind 用 `str` + 长度约束）。
2. **`DatabaseSignal` 缺健康结论值**：
   `DatabaseSignal` 没有 `NO_SLOW_QUERY_DETECTED`（健康分支需要的诚实结论）
   → 补该枚举值，并在 schemas 的 `signal` Literal 同步补 `"no_slow_query_detected"`。

这两处是「正式产品去 P2 演示硬编码」的一部分，不属于新增功能，故纳入 P4 实施范围。
