# OperMind — 多 Agent DevOps Copilot

OperMind 是面向研发与运维人员的**会话式多 Agent DevOps Copilot**。它在受控、可复现、与应用元数据隔离的靶场中协调 DB、Log、Server 调查角色，完成证据化判断；危险修复必须经过提案、人工审批、白名单执行和验证闭环。多 Agent、SSE、Trace、记忆和评测都是产品能力或技术资产，不是脱离产品的独立目标。

## 当前产品与唯一主线

- 总进度和唯一下一步：`docs/开发/_A-Plan-总览.md`。
- 当前产品蓝图：`docs/开发/治理-DevOps-Copilot-MVP重定位/product-blueprint.md`。
- 秋招 MVP 只做一个问题：订单服务缺失 `orders(user_id, created_at)` 索引导致慢查询。先完成“会话提问 → 只读证据 → 根因 → 审批/执行/Verify → 服务页留痕”的骨架，再增加问题、服务或知识库复杂度。
- P4.0 Work 1、P4.1 与 P4.2 均已在用户授权靶场真实 smoke 通过。P4.3 的服务中心、有限快照、服务上下文会话和安全活动留痕已完成代码、回归与实现审查；其 target smoke 待当前进程提供授权靶场凭据后补跑，缺凭据必须 fail-closed，不能改用 mock 冒充。
- 已删除旧教程、旧阶段计划和过时产品路线，避免它们成为错误上下文。需要继承的历史代码/测试事实只读 `docs/开发/历史技术基线.md`、当前代码和测试；Git 历史只供追溯。

## 目录与职责

```text
backend/       FastAPI、应用服务、领域、持久化、Agent/Tool、测试和脚本
frontend/      主产品：会话、调查、证据、提案、审批、执行、验证、服务页
report/        研发、Trace 与评测控制台；保留，不是主产品前端
demo/          受控演示靶场
knowledge/     后续 P5.0 的受控 Markdown 知识目录（尚未实现前不得伪装可用）
config/ data/ experiments/  配置、确定性 mock、研发/毕业设计资产
```

## P4 靶场硬边界

- 唯一可操作目标：用户授权本地隧道 `127.0.0.1:5433` → `opermind_demo` → `opermind_demo.orders`，仅允许预定义索引 `idx_orders_user_created` 的受控动作。
- 绝不连接、读取、写入、列举或清理 `gongkar` 或任何其他数据库、schema、表、端口。
- 连接参数只来自当前进程环境；代码 fail-closed 校验目标。凭证不能写入仓库、文档、日志、事件、结果、截图或 Git。
- 应用元数据与诊断靶场隔离；`clean` 只能删除专用 schema 与项目运行时文件，不能删除数据库。

## 开发规则

> `AGENTS.md` 与 `CLAUDE.md` 必须逐字一致。完整规则：`docs/开发/开发规范.md`。

- 中文注释/文档/日志；公开函数有类型标注；跨层结构化数据用 Pydantic/TypedDict；禁止裸 `except` 和新增生产 `print`。
- LLM Agent 继承 `BaseAgent` 并复用 ReAct `run()`；Tool 继承 `Tool` 并实现 `execute`；确定性只读 Collector 必须经显式 Application port/Executor 注入并返回 Pydantic 事实，不能伪装为可自由调用的 Agent。Graph 使用显式 `DiagnosisState`。
- 每个外部依赖有确定性 mock fallback。诊断适配器默认只读、参数化、限时、脱敏；禁止模型任意 SQL/Shell/DDL/DML，禁止真实生产资源。
- 只有独立受控执行器才能在用户授权隔离靶场、人工审批、严格 action 白名单同时满足时执行预定义动作；不得扩展 P4.2 之外的写入动作。
- 过程 UI 只展示审计摘要、状态和结构化证据，不展示 CoT、Prompt、原始敏感数据、异常详情或凭证；未实现能力必须显式未启用。
- 知识库首版只能是允许目录内的 Markdown + 程序全文检索；模型不能调用任意 grep/Shell，文件上传、向量库、RAG、知识图谱、用户 API Key 都需独立工作包设计。
- 一个工作包可包含 1–3 个紧密切片，完成时集中 Test → Review → Commit。架构、公开契约、迁移、真实数据源、审批/执行安全、破坏性改动必须先 Design → Review → 用户授权。
- 不直推 `main`；commit 使用 `<类型>: <中文描述>`；只暂存指定文件，禁止无检查的 `git add .`；不得提交 `.env`、`*.local.yaml`、凭证或含 `sk-` 的文件。
