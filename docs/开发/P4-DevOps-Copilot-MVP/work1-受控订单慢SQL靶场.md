# Work 1 — 订单慢 SQL 受控靶场实施记录

> 日期：2026-07-30　|　分支：`feat/p4-devops-copilot`　|　状态：**✅ 真实 smoke 通过并已提交**　|　关联提交：`9560c15 feat: 建立订单慢SQL受控靶场`

## 交付内容

| 路径 | 内容 |
|---|---|
| `demo/orders-slow-query/.env.example` | 不含凭证的 PostgreSQL 靶场变量模板。 |
| `demo/orders-slow-query/order-service/` | 仅监听 `127.0.0.1:18080` 的固定订单查询服务。 |
| `demo/orders-slow-query/postgres/schema.sql` | 专用 schema 的显式结构参考。 |
| `backend/scripts/demo_orders_env.py` | 固定 target 的 `start`、`probe`、`inject`、`repair`、`verify`、`clean`。 |
| `backend/scripts/smoke_demo_orders.py` | 默认清理的完整 smoke。 |
| `backend/tests/scripts/` | 配置拒绝、计划解析、统计与清理边界测试。 |

## 真实验收

在用户授权的专用靶场执行 `backend/scripts/smoke_demo_orders.py --samples 10`：

| 阶段 | 事实 |
|---|---|
| baseline | `Index Scan`，P50 `53.809 ms`，P95 `60.539 ms`，无慢查询日志。 |
| degraded | 删除固定索引后 `Seq Scan`，P50 `78.558 ms`，比 baseline 高 `24.749 ms`、比例 `1.460`，10/10 慢查询日志。 |
| recovered | 重建索引后 `Index Scan`，P50 `53.985 ms`，P95 `61.451 ms`，慢日志归零。 |
| clean | 专用 schema 与靶场 `runtime/` 已清理，数据库保留为空库。 |

## 固定安全边界

- 仅可操作授权的 `127.0.0.1:5433/opermind_demo` 中 `opermind_demo.orders` 与 `idx_orders_user_created`。
- 不读取、写入、列举、探测或清理 `gongkar` 或其他目标。
- 连接参数仅来自当前进程环境；凭证未进入仓库、文档、日志或结果。
- Work 1 管理脚本只用于靶场准备/故障注入/清理，不是产品调查器或产品执行器。

## 后续关系

P4.1 将在此真实靶场上实现“会话问题 → 只读证据 → 结构化结论 → 展开详情”。只有用户明确授权后才可实施；修复提案、审批、执行与 Verify 仍属于 P4.2。
