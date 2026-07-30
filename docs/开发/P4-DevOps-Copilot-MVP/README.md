# P4 — 单问题端到端 DevOps Copilot MVP

> 当前目标：把订单慢查询做成会话式 DevOps Copilot 的第一条完整用户路径。

| 文件 | 用途 |
|---|---|
| `work1-受控订单慢SQL靶场.md` | 已完成的 PostgreSQL 靶场实现与真实 smoke。 |
| `design.md` / `review.md` | P4.0 靶场与调查—修复—验证总边界。 |
| `p4.1-只读证据调查-design.md` / `p4.1-只读证据调查-review.md` | 已完成 target smoke 的会话触发只读调查设计及审查。 |
| P4.1-HANDOFF.md / p4.1-implementation.md | P4.1 target smoke、集中 Review/Commit 的恢复入口与实施记录。 |
| p4.2-固定修复审批执行验证-design.md / p4.2-固定修复审批执行验证-review.md | 已完成设计审查、等待实施确认的固定索引修复提案、审批、白名单执行与 Verify 方案。 |

P4.1 已完成“用户问订单慢查询 → DB/Log/Server 受控调查 → 结构化结论与可展开证据”。P4.2 的修复提案、审批、执行和 Verify 已完成独立 Design/Review；当前只等待用户对该设计的实施确认。

靶场严格限于授权的 `opermind_demo`；任何非目标数据库、包括 `gongkar`，均不得探测或访问。
