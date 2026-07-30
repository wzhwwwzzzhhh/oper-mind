# OperMind DevOps Copilot MVP 重定位

> 生效：2026-07-29　|　产品总设计更新：2026-07-30
>
> **当前定位：会话式、多 Agent、受控执行的 DevOps Copilot 产品；不是独立的多 Agent 实验系统。**

## 当前要做什么

先完成一个真实问题的端到端产品闭环：订单服务因缺失 `orders(user_id, created_at)` 联合索引而慢查询。用户从会话提问开始，依次得到只读调查、证据与根因、固定修复提案、人工审批、白名单执行和 Verify 结论。

完整界面和能力分层见：

- `product-blueprint.md`：会话工作台、过程展示、服务接入、知识库、Provider、MCP 与路线；
- `product-blueprint-review.md`：范围、安全和产品可信度审查；
- `design.md` / `review.md`：P4.0 靶场设计及 Work 1 的真实验收事实；
- `HANDOFF.md`：当前 P4 交接与恢复入口。

## 当前范围

- 先只做 PostgreSQL 订单慢查询；不因为有 Connector 设计就伪称已支持 MySQL/Redis。
- 知识库先是受控 Markdown + 程序全文检索；不先做 RAG/向量库/知识图谱。
- 模型 Key 设置、文件上传、生产服务接入、MCP 外接和第二问题都延后到独立工作包。
- 用户能看过程摘要和证据，不能看 CoT 或敏感原始数据。

历史路线文档已经从工作树清理。需确认可复用事实请读 `../历史技术基线.md`、代码和测试，而不是旧阶段计划。
