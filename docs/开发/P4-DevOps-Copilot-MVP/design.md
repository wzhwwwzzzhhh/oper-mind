# Work 1 Design — 订单慢 SQL 受控靶场

> 日期：2026-07-29，修订：2026-07-30　|　授权：用户已明确授权 Work 1　|　状态：**实现与真实验收完成**

## 1. 工作包目标

为 P4 首个产品闭环建立可重复、可清理、可审计的真实故障靶场：固定订单查询在缺失联合索引后退化，由后续多 Agent 调查、人工审批、白名单执行和 Verify 复用。

Work 1 不改 OperMind 后端产品代码、Agent、API、前端、迁移或 `/api/v1` 契约。

## 2. 设计边界

| 维度 | 决策 |
|---|---|
| 数据库 | 用户授权新建的 `opermind_demo`；通过 `127.0.0.1:5433` 本地隧道访问。 |
| 数据隔离 | 仅创建/删除 `opermind_demo` schema，不删除数据库，不访问其他库。 |
| 禁止目标 | `gongkar` 和任何未写死的数据库、schema、表、端口。 |
| 服务 | 仅本机 `127.0.0.1:18080` 的 FastAPI 订单服务。 |
| 数据 | 300,000 条确定性 demo 订单；不读取项目 `data/`、应用元数据或用户业务表。 |
| 故障 | 仅删除 `opermind_demo.idx_orders_user_created`。 |
| 修复 | 仅重建同名且定义固定的联合索引。 |
| 证据 | PostgreSQL `EXPLAIN (FORMAT JSON)`、订单服务真实耗时、JSONL 日志。 |
| 清理 | 仅停止实例 ID 匹配的本地服务，删除靶场 schema 与 `runtime/`。 |

## 3. 操作协议

1. 从环境变量读取连接参数；代码验证 `host=127.0.0.1`、`port=5433`、`database=opermind_demo`，否则失败；
2. `start` 建立 schema、表、固定索引和 demo 数据，启动服务并采集 baseline；
3. `inject` 删除目标索引；
4. `verify --phase degraded` 要求无索引、`Seq Scan`、明显退化及慢查询日志均成立；
5. `repair` 重建目标索引；
6. `verify --phase recovered` 要求索引/索引计划恢复、延迟恢复和慢日志归零；
7. `clean` 默认由 smoke 触发并删除靶场数据与运行时文件。

## 4. 失败策略

- 配置、数据库名、当前连接数据库、schema/table/index 不符合设计：立即失败；
- 启动、健康检查、探测或验证失败：返回非零，smoke 的 finally 仍执行 clean；
- 实际隧道性能不足以形成退化：判定 smoke 失败，调整靶场数据/判定后重新验证，绝不伪造；
- 不存在“改连 `gongkar`”或任何其他资源的回退路径。

## 5. 预留而未实施的内容

P4.1 才设计 DB/Log/Server 只读 adapter、mock fallback、证据契约和 Agent 接入；P4.2 才设计审批、action、审计和 Verify application service。Work 1 管理脚本不得被直接当作生产执行器。