# P4 — DevOps Copilot MVP

> 建立日期：2026-07-29　|　Work 1 收口：2026-07-30　|　当前状态：**Work 1 已真实验收并收口；P4.1 未授权**

本目录记录 P4 工作包的实施快照，不替代总览或产品定位文档。

## Work 1 状态

- 已创建独立 `demo/orders-slow-query/` PostgreSQL 靶场与本地订单服务；
- 唯一目标为用户授权的本地隧道 `127.0.0.1:5433/opermind_demo`，运行时只在 schema `opermind_demo` 内创建数据；
- 只允许删除/重建 `idx_orders_user_created`，所有其他连接目标和对象均被拒绝；
- `start/probe/inject/repair/verify/clean` 与自动清理 smoke 已实现；
- 纯脚本测试、Python 编译和真实 `start → inject → verify → repair → verify → clean` smoke 已通过；
- 不读取、不修改、不探测 `gongkar`；凭证没有写入仓库或日志。

## 文档

| 文件 | 用途 |
|---|---|
| `design.md` | Work 1 安全边界、数据模型与验收设计。 |
| `work1-受控订单慢SQL靶场.md` | 交付清单、真实测量结果与运行命令。 |
| `review.md` | Work 1 代码/安全/验收复核。 |
| `HANDOFF.md` | 已关闭的交接记录与提交边界。 |

产品定位见 `../治理-DevOps-Copilot-MVP重定位/`；项目唯一下一步见 `../_A-Plan-总览.md`。