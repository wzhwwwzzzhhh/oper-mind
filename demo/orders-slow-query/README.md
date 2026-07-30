# Work 1：订单慢 SQL 受控靶场

该目录是 OperMind P4 的唯一真实演示目标环境。它不是产品后端、不会读取项目应用元数据，也不读取或修改用户已有的 `gongkar` 数据库。

## 真实边界

靶场只能通过用户授权的本地隧道访问以下固定目标：

| 项目 | 固定值 |
|---|---|
| 主机 | `127.0.0.1` |
| 端口 | `5433` |
| 数据库 | `opermind_demo` |
| schema | `opermind_demo` |
| 表 | `orders` |
| 索引 | `idx_orders_user_created (user_id, created_at)` |
| 订单服务 | `http://127.0.0.1:18080` |

控制脚本会 fail-closed 校验主机、端口、数据库、schema、表和索引。它不列举、不探测、不连接 `gongkar`，也不接受其他目标作为替代。

## 场景

- **正常**：专用 `opermind_demo.orders` 有预定义联合索引，固定查询走索引。
- **故障**：控制脚本只删除 `opermind_demo.idx_orders_user_created`；真实 PostgreSQL `EXPLAIN` 出现顺序扫描，订单服务产生真实延迟与 JSONL 慢查询日志。
- **恢复**：控制脚本只重建同一索引；验证脚本同时检查索引、执行计划、探测窗口和匹配日志。
- **清理**：默认删除整个 `opermind_demo` schema 与运行时进程/日志，但**不删除** `opermind_demo` 数据库，也不触及任何其他数据库。

没有 `pg_sleep`、伪造耗时、假指标或任意 SQL/Shell 入口。

## 前置条件

1. 用户已创建并授权专用数据库 `opermind_demo`；
2. 本地隧道在 `127.0.0.1:5433` 监听；
3. 通过环境变量提供该专用数据库的账号和密码；凭证绝不写入 `.env.example`、日志或 Git；
4. 本机 `18080` 端口可用，Python 虚拟环境已安装项目依赖。

复制 `.env.example` 的变量名到当前 PowerShell 环境后运行（不要提交真实 `.env`）：

```powershell
$env:OPERMIND_DEMO_PG_HOST = '127.0.0.1'
$env:OPERMIND_DEMO_PG_PORT = '5433'
$env:OPERMIND_DEMO_PG_DATABASE = 'opermind_demo'
$env:OPERMIND_DEMO_PG_USER = '<专用账号>'
$env:OPERMIND_DEMO_PG_PASSWORD = '<密码>'
```

## 操作

```powershell
# 初始化 schema、300,000 条确定性 demo 订单，并启动本地订单服务。
.\.venv\Scripts\python.exe backend\scripts\demo_orders_env.py start

# 正常探测；结果会写入 runtime/state。
.\.venv\Scripts\python.exe backend\scripts\demo_orders_env.py probe --phase baseline

# 只删除固定索引，注入慢 SQL 故障。
.\.venv\Scripts\python.exe backend\scripts\demo_orders_env.py inject

# 故障验证：索引不存在、顺序扫描、延迟升高且有慢查询日志才通过。
.\.venv\Scripts\python.exe backend\scripts\demo_orders_env.py verify --phase degraded

# 只重建固定索引，并验证恢复。
.\.venv\Scripts\python.exe backend\scripts\demo_orders_env.py repair
.\.venv\Scripts\python.exe backend\scripts\demo_orders_env.py verify --phase recovered

# 删除专用 schema、停止订单服务并删除 runtime。始终建议执行。
.\.venv\Scripts\python.exe backend\scripts\demo_orders_env.py clean
```

一次性完整验收（默认最终清理）：

```powershell
.\.venv\Scripts\python.exe backend\scripts\smoke_demo_orders.py --samples 10
```

`--keep` 仅用于排查；完成后仍必须显式运行 `clean`。

## 运行时产物

运行时文件只位于被 Git 忽略的 `runtime/`：服务 JSONL 日志、进程状态与基线/验证报告。日志路径被订单服务限制在 `runtime/logs/`，脚本只会终止自身记录并带有随机实例 ID 的本地订单服务进程。