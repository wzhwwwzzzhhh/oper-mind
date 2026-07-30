# B-Plan — OperMind 单问题端到端 MVP 开发计划

> 更新：2026-07-30　|　阶段范围与验收参考；项目唯一下一步以 `_A-Plan-总览.md` 为准。

## 1. MVP 目标

交付一个可实际演示和操作的 DevOps Copilot 工作台，而不是 Agent 实验页：用户在会话中报告订单服务变慢，系统展示可信的 DB/Log/Server 调查过程与结构化结论；后续用户审批固定修复动作，系统执行并验证恢复。

“完整”指一条用户路径有真实输入、真实受控证据、清晰安全边界、持久化记录和可回收验证，不指首版支持所有运维问题。

## 2. 约束与非目标

- 首个且唯一故障：缺失 `orders(user_id, created_at)` 索引导致订单慢查询。
- 首个且唯一真实 Connector：授权靶场中的 PostgreSQL 订单服务；MySQL、Redis 等只预留扩展边界。
- 不接入生产、云账号、Kubernetes、任意 MCP 或模型自由 SQL/Shell。
- 不在 P4.1 做 DDL/DML、审批、执行、文件上传、向量库、RAG、知识图谱或用户 API Key 存储。
- 知识库先采用仓库受控 Markdown + 程序全文检索；复杂方案以可评测需求为前提。

## 3. 工作包

| 工作包 | 范围 | 验收 |
|---|---|---|
| P4.0 / Work 1（完成） | 隔离 PostgreSQL 靶场、本地订单服务、受控脚本、真实 smoke | 正常→删固定索引→可复核退化→重建→恢复→清理。 |
| P4.1 | 只读 Collector、证据模型、产品执行器、现有 Workbench 的会话接入 | 用户输入慢查询问题后，可得到三源或明确失败的结构化事实；简要过程可见、详情可展开、无 CoT 泄露。 |
| P4.2 | 固定修复提案、审批、白名单执行、Verify | action ID、审批、执行、前后证据可追溯；默认 fail-closed。 |
| P4.3 | 已注册靶场服务的服务中心/监控页 | 一个服务有真实有限健康/性能事实、调查入口和历史记录。 |
| P5.0 | Markdown 知识目录与受控全文检索 | 命中片段、文件来源、行号可引用；未命中不编造。 |
| P5.1 | Provider 设置与第二 Connector | 先完成安全设计、mock 和验收，再接 MySQL 或 Redis 之一。 |
| P6+ | 第二故障、评测、毕设、回归、部署增强 | 每项独立设计并可回归。 |

## 4. 复用与架构边界

- 重用 P2 的 Session/Message/Run/Result/RunEvent/SSE 与前端 Workbench；若需要改公开 API 或迁移，必须另行审查。
- P4.1 的 DB/Log/Server 是确定性 Collector，不是可自由调用 Tool 的模型 Agent；对用户仍以调查角色呈现。
- 现有 ReAct/LangGraph、Debate/Reflection、Trace、评测和记忆能力可以作为技术资产逐步纳入，但不能突破 Collector 和白名单执行器的安全边界。
- `ServiceConnector` 和 `MarkdownKnowledgeSearcher` 是先搭边界、后增能力的扩展点；没有真实实现的能力不在产品中伪装为可用。

## 5. 工作节奏

一个工作包可包含 1–3 个紧密切片。先确定用户路径、输入/输出、安全边界、失败语义和验收，再连续实现；完成时集中 Test → Review → Commit。真实数据源、公开契约、迁移、审批/执行和破坏性改动必须先独立 Design → Review，并获得用户授权。
