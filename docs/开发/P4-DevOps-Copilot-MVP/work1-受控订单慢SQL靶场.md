# Work 1 — 订单慢 SQL 受控靶场实施记录

> 日期：2026-07-30　|　分支：`feat/p4-devops-copilot`　|　状态：**✅ 真实 smoke 已通过，等待提交**

## 交付内容

| 路径 | 内容 |
|---|---|
| `demo/orders-slow-query/.env.example` | 不含凭证的 PostgreSQL 靶场变量模板。 |
| `demo/orders-slow-query/postgres/schema.sql` | `opermind_demo` schema 和 `orders` 表的显式结构参考。 |
| `demo/orders-slow-query/order-service/app/main.py` | 固定订单查询、健康检查、窗口指标和 JSONL 查询日志；只接受固定目标。 |
| `backend/scripts/demo_orders_env.py` | `start`、`probe`、`inject`、`repair`、`verify`、`clean` 六个受限命令。 |
| `backend/scripts/smoke_demo_orders.py` | 正常→注入→故障验证→恢复→恢复验证→清理的端到端 smoke。 |
| `backend/tests/scripts/test_demo_orders_env.py` | 不需要网络/数据库的纯 Python 单元测试。 |

## 实施后的运行流程

```powershell
$env:OPERMIND_DEMO_PG_HOST = '127.0.0.1'
$env:OPERMIND_DEMO_PG_PORT = '5433'
$env:OPERMIND_DEMO_PG_DATABASE = 'opermind_demo'
$env:OPERMIND_DEMO_PG_USER = '<专用账号>'
$env:OPERMIND_DEMO_PG_PASSWORD = '<密码>'
.\.venv\Scripts\python.exe backend\scripts\smoke_demo_orders.py --samples 10
```

预期顺序：

1. `start` 验证当前连接数据库为 `opermind_demo`，创建专用 schema、300,000 条数据和正常索引，启动本地订单服务；
2. `inject` 只执行目标索引的 `DROP INDEX`；
3. `verify --phase degraded` 要求索引缺失、顺序扫描、以 P50 比例/增量判定延迟退化，并同时要求慢日志成立；
4. `repair` 只重建目标索引；
5. `verify --phase recovered` 要求索引计划、延迟和日志同时恢复；
6. 默认 `clean`；只有 `--keep` 保留现场。

## 本机真实验证事实

| 项目 | 结果 | 说明 |
|---|---|---|
| 纯脚本单测 | ✅ 11 passed | 覆盖配置拒绝、百分位、计划遍历、P50 抗隧道抖动规则、故障/恢复规则、日志过滤、路径/清理边界，以及服务配置/日志路径边界。 |
| Python 编译 | ✅ 通过 | 覆盖控制脚本、smoke 与订单服务。 |
| 完整 smoke | ✅ 通过 | 2026-07-30，`--samples 10`，默认最终 clean。 |
| baseline | ✅ | `Index Scan` 使用目标索引；P95 `60.539 ms`；无慢查询日志。 |
| degraded | ✅ | `Seq Scan`；P95 `84.127 ms`，P50 比 baseline 高 `24.749 ms`（`1.460x`）；10 条慢查询日志。 |
| recovered | ✅ | 恢复 `Index Scan`；P95 `61.451 ms`、P50 `53.985 ms`；慢查询日志为 0。 |
| 清理检查 | ✅ | `opermind_demo` schema 不存在，`runtime/` 已删除；数据库保留。 |

## 安全复核事实

- 在连接前，脚本只检查用户授权的回环地址与专用数据库；没有列举或检查 `gongkar`；
- 所有 DDL 都指定 `opermind_demo` schema 和固定索引名；
- 密码仅放在运行命令的进程环境，未写入文件、日志、测试输出或 Git；
- 订单服务日志路径限制到靶场 `runtime/logs/`；进程停止仅接受状态文件中脚本启动的随机实例 ID；
- 因 `clean` 已执行，当前专用数据库为空，不遗留 Work 1 demo schema 或数据。

## 后续边界

Work 1 通过不等于 Agent/API/前端已完成。下一步必须先提交本工作包，之后等待用户是否授权 P4.1 Design。