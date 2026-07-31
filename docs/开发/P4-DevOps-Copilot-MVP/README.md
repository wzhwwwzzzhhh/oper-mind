# P4 — 单问题端到端 DevOps Copilot MVP

> 当前目标：把订单慢查询做成会话式 DevOps Copilot 的第一条完整用户路径。

| 文件 | 用途 |
|---|---|
| `work1-受控订单慢SQL靶场.md` | 已完成的 PostgreSQL 靶场实现与真实 smoke。 |
| `design.md` / `review.md` | P4.0 靶场与调查—修复—验证总边界。 |
| `p4.1-只读证据调查-design.md` / `p4.1-只读证据调查-review.md` | 已完成 target smoke 的会话触发只读调查设计及审查。 |
| P4.1-HANDOFF.md / p4.1-implementation.md | P4.1 target smoke、集中 Review/Commit 的恢复入口与实施记录。 |
| p4.2-固定修复审批执行验证-design.md / p4.2-固定修复审批执行验证-review.md / p4.2-implementation.md / p4.2-implementation-review.md | 已完成的固定索引修复提案、审批、白名单执行、独立 Verify、UI 与 target smoke。 |
| p4.3-服务中心监控调查入口-design.md / p4.3-服务中心监控调查入口-review.md / p4.3-implementation.md / p4.3-implementation-review.md / P4.3-HANDOFF.md | 已完成的已注册订单服务中心、有限快照、服务上下文调查入口与恢复记录；真实 target smoke 待当前进程靶场凭据后补验收。 |

P4.1 已完成“用户问订单慢查询 → DB/Log/Server 受控调查 → 结构化结论与可展开证据”。P4.2 已完成“固定 Proposal → local_operator 审批 → 二次确认执行 → 独立 Verify → 审计时间线”，并已通过 mock、API/UI 回归和 target smoke。P4.3 已完成“服务中心 → 有限当前快照 → 服务上下文会话 → 用户确认调查 → 服务页安全留痕”的代码、回归与实现审查；真实 target smoke 因当前进程没有靶场凭据而 fail-closed，待补验收。

靶场严格限于授权的 `opermind_demo`；任何非目标数据库、包括 `gongkar`，均不得探测或访问。
