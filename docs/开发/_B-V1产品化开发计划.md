# B-Plan — OperMind DevOps Copilot MVP 开发计划

> 更新日期：2026-07-30　|　阶段范围与验收参考；项目当前唯一下一步以 `_A-Plan-总览.md` 为准。

## 1. MVP 目标

交付一个可演示、可审计、可验证的 DevOps Copilot 纵向闭环：用户报告订单接口异常后，系统协调 DB、Log、Server Agent 收集只读证据，形成结构化根因与受限修复提案；用户审批后，独立白名单执行器在隔离靶场执行固定修复，并显示前后验证结论。

MVP 的“可演示”不是为了做实验展示，而是为了证明产品可以在受控环境中稳定复现：真实证据来自固定靶场，审批和执行不会越过安全边界，Verify 不能伪造成功。

## 2. 约束与非目标

- 只承诺第一个故障：`orders(user_id, created_at)` 联合索引缺失导致慢 SQL。
- 靶场的真实目标固定为用户授权的本地隧道 `127.0.0.1:5433/opermind_demo`；只能操作 schema `opermind_demo` 内的预定义对象。
- 不读取、修改、列举或探测 `gongkar`；不接入生产资源、Kubernetes、云账号、真实认证或在线迁移。
- 不允许模型生成任意 SQL/Shell；执行仅通过固定 action ID、固定参数、人工审批和审计事实。
- 不以长会话、通用聊天、多租户、监控大盘或第二类故障替代首个闭环。

## 3. 工作包

| 工作包 | 范围 | 验收 | 状态 |
|---|---|---|---|
| P4.0 / Work 1 | 隔离 PostgreSQL 订单慢 SQL 靶场、本地订单服务、受控脚本、真实 smoke | 正常→删固定索引→可复核退化→重建固定索引→恢复验证→清理 | ✅ 完成 |
| P4.1 | DB/Log/Server 只读适配、证据模型、Coordinator 调度 | 真实靶场可得到结构化、可引用的调查证据 | 未授权 |
| P4.2 | 修复提案、审批、白名单执行、Verify 编排 | action 与审批、执行、验证事实可追溯且 fail-closed | 待设计 |
| P4.3 | 后端 API/SSE 与 `frontend/` 主流程 | 从异常报告到验证结论的一键演示 | 待设计 |
| P5+ | 第二故障、可靠性、安全、毕业设计评测 | 每个扩展独立设计、可回归 | 待开始 |

## 4. Work 1 成果与接口边界

Work 1 只提供靶场与脚本，不修改 OperMind 产品 Agent、API、前端、数据库迁移或 `/api/v1` 契约：

- `backend/scripts/demo_orders_env.py`：受限的 `start`、`probe`、`inject`、`repair`、`verify`、`clean`；
- `backend/scripts/smoke_demo_orders.py`：默认清理的端到端 smoke；
- `demo/orders-slow-query/order-service/`：仅本机 `127.0.0.1:18080` 的固定查询服务；
- `demo/orders-slow-query/postgres/schema.sql`：专用 schema 的显式结构参考；
- 单元测试验证配置拒绝、统计、计划解析、故障/恢复规则与清理边界。

P4.1 不能直接把 Work 1 管理脚本当成产品执行器；它必须先设计独立的只读适配器、证据契约、最小权限与 mock fallback。

## 5. 工作节奏

一个工作包可包含 1–3 个紧密相关切片。先确定目标、输入/输出、安全边界与验收，再连续实现和增量测试；完成时集中 Test → Review → Commit。涉及架构、公开契约、迁移、真实数据源、审批/执行安全或破坏性改动的内容，必须先独立 Design 与 Review，并取得用户授权。

P4.0 Work 1 已收口；等待用户是否授权 P4.1 Design。