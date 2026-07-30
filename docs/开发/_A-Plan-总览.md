# A-Plan 总览 — OperMind 多 Agent DevOps Copilot

> 创建：2026-07-20　|　产品重置：2026-07-29　|　单问题端到端蓝图确认：2026-07-30
>
> **本文件是项目总进度、执行顺序与唯一下一步的唯一真相源。**

## 1. 当前产品方向

OperMind 是面向研发与运维人员的**会话式多 Agent DevOps Copilot**。用户在会话中提出运维问题，系统基于受控证据进行调查；危险操作只能通过提案、人工审批、白名单执行和验证闭环完成。

它不是通用聊天机器人，也不是独立多 Agent 实验系统。秋招 MVP 只解决一个真实、可复现的问题：订单服务因缺失 `orders(user_id, created_at)` 联合索引而慢查询。先把以下产品骨架做通，再增加故障类型、服务和知识库复杂度：

```text
会话提问 → 受控调查 → 证据/根因/不确定性 → 修复提案
→ 人工审批 → 白名单执行 → Verify 前后事实 → 服务页留痕
```

用户可看见简要进度和可展开的证据依据；不可看见模型 CoT、原始敏感数据或凭证。完整定位见 `治理-DevOps-Copilot-MVP重定位/product-blueprint.md`。

## 2. 保留的技术基础

- `backend/src/api/v1/`、应用层、领域模型、持久化、前端 Workbench 已提供 Session、Message、Run、Result、RunEvent 和 SSE 的技术底座。
- `backend/src/agents/`、`core/`、`tools/`、`memory/`、`report/`、`experiments/` 保留 Agent、Trace、评测和毕业设计资产，但不自行定义产品需求。
- P4.0 Work 1 已在用户授权的专用 PostgreSQL 靶场真实完成 `start → inject → verify → repair → verify → clean` smoke。
- 历史阶段日志、旧产品重定位、教程和过时对外叙事已从工作树删除；需追溯时查 Git 历史。必须继承的事实集中在 `历史技术基线.md`。

## 3. 当前主线与工作包

| 工作包 | 状态 | 目标 |
|---|---|---|
| **P4.0 / Work 1** | ✅ 完成 | 隔离 PostgreSQL 订单慢查询靶场、受控脚本与真实 smoke。 |
| **P4.1** | ✅ 完成 | 会话触发的 DB/Log/Server 只读调查、结构化证据结果、简要过程与可展开详情；mock/API/UI 回归与 target smoke 已通过。 |
| **P4.2** | ✅ 完成 | 固定修复提案、local_operator 人工审批、白名单执行、独立 Verify、轮询审计与 target smoke 已通过。 |
| **P4.3** | ✅ Design/Review 完成，待授权实现 | 一个已注册靶场服务的服务中心/有限监控快照/调查入口；尚未授权实现。 |
| **P5.0** | 待设计 | Markdown 知识目录、受控全文检索（grep 等价实现）和引用展示。 |
| **P5.1** | 待设计 | 模型 Provider 设置、第二类 Connector 的安全设计与实现。 |
| **P6+** | 待开始 | 第二故障、MySQL/Redis、评测、毕业设计材料、安全与部署增强。 |

## 4. 当前唯一下一步

**P4.3 Design/Review 已于 2026-07-30 完成；当前唯一下一步是等待用户明确授权实施 P4.3（已注册靶场服务的服务中心、有限监控快照与调查入口）。**

P4.2 已交付固定 `postgres.orders.rebuild_missing_user_created_index.v1`：只有 P4.1 的 `high / 0.95` 三源确认事实才能生成不可编辑 Proposal；本地操作者以 `local_operator` 批准或拒绝；批准后第二次确认才异步进入白名单执行器；Verify 重新确认索引、固定计划、恰好 3 次固定探测与匹配日志。执行结果与脱敏审计事件在 Workbench 展示，P4.2 没有通用 SQL、Shell、重试、自动回滚或第二套 SSE。

P4.3 Design/Review 见 `P4-DevOps-Copilot-MVP/p4.3-服务中心监控调查入口-design.md` 与 `p4.3-服务中心监控调查入口-review.md`。在用户明确授权前，不得实现服务中心、监控页、调查入口、迁移、公开契约或新的真实读取。仍不得扩展第二种故障、Redis/MySQL/Kubernetes、RAG/知识库、文件上传、用户 API Key 存储或任何新真实连接。

## 5. P4 靶场硬边界

- 唯一可操作目标是用户授权的本地隧道 `127.0.0.1:5433` 上专用数据库 `opermind_demo`，仅限 schema `opermind_demo` 的 `orders` 表和 `idx_orders_user_created` 索引。
- 绝不探测、读取、写入或清理 `gongkar`，也不访问其他数据库、schema、表或端口。
- 凭证只在当前进程环境中使用，不进入仓库、文档、日志、截图、结果或事件。
- 产品元数据数据库必须与诊断靶场隔离；`clean` 只删除专用 schema 与项目运行时文件，不删除专用数据库。

## 6. Work 1 真实验收事实

2026-07-30 的首次完整 smoke（300,000 条确定性 demo 订单、10 次样本）结果：

| 阶段 | 核心事实 |
|---|---|
| baseline | `Index Scan` 使用固定索引；P50 `53.809 ms`、P95 `60.539 ms`；无慢查询日志。 |
| degraded | 删除固定索引后为 `Seq Scan`；P50 `78.558 ms`，比 baseline 高 `24.749 ms`、比例 `1.460`；10/10 匹配慢查询日志。 |
| recovered | 重建固定索引后回到 `Index Scan`；P50 `53.985 ms`、P95 `61.451 ms`；无慢查询日志。 |
| clean | `opermind_demo` schema 与靶场运行时文件已清理；专用数据库保留为空库。 |

上述数据只证明该隔离隧道靶场可复现，不是生产 SLA。

P4.1 于 2026-07-30 在同一隔离靶场完成 `start → inject → API/SSE 调查 → repair → clean`：三类证据、缺失索引根因、可重放终态事件均通过；回收后靶场 schema 与运行时文件已清理。

P4.2 于 2026-07-30 在同一隔离靶场完成 `start → inject → P4.1 调查 → Proposal → approve → execute → Verify → clean`：受控执行器仅创建固定索引；Verify 确认目标索引、固定计划、3 次固定探测与匹配日志均正常；`clean` 已完成。

## 7. 执行原则

- 先完成一个纵向产品切片，再扩展故障数和平台能力。
- 真实数据源默认只读、参数化、限时、可 mock；LLM 不直接拥有 SQL/Shell/DDL/DML 权限。
- “过程可见”只展示审计事实和脱敏结构化证据，不能伪装 CoT 或实时监控。
- 工作包内可连续实现 1–3 个紧密切片，完成时集中 Test → Review → Commit；架构、公开契约、迁移、真实连接、审批/执行和破坏性改动仍先独立设计审查。
- 每次切换上下文先读本文件；只有本文件可以声明“当前唯一下一步”。
