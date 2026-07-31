# OperMind — 会话式多 Agent DevOps Copilot

OperMind 是面向研发与运维人员的正式 Web 产品：用户在类似 DeepSeek 的会话系统中提问、追问和下达受控指令；系统结合已接入服务、监控事实、受控 Tool 和多 Agent 协作完成调查、提案、人工审批、白名单执行与验证。

## 当前产品事实源

- 产品定义：`docs/产品定义.md`
- 当前路线图：`docs/路线图.md`
- 开发规则：`docs/开发规范.md`
- 这三份文档是唯一当前文档来源。旧工作包、靶场、验收、Review、Handoff 和历史路线已从工作区删除，不得从 Git 历史恢复为当前需求或规则。
- 现有代码是技术资产，不自动决定正式产品边界。当前已有 PostgreSQL 慢查询闭环只是第一个技术切片，不是产品只能支持的服务或故障范围。

## 产品方向

- 会话工作台是主入口；服务中心负责服务接入、服务状态、监控和调查入口。
- 产品目标支持 PostgreSQL、MySQL、Redis 等服务，但新增服务类型、连接方式、监控、凭据、权限和动作都必须先完成独立 Design → Review → 用户确认。
- 多 Agent、Trace、记忆、MCP、RAG 和评测都是服务产品能力的技术手段，不是脱离产品的独立目标。
- Trace UI 只展示简要审计事实、状态和结构化证据摘要；禁止展示 CoT、Prompt、原始敏感数据、异常详情或凭据。

## 安全硬规则

- 模型不得直接拥有任意 SQL、Shell、DDL、DML 或网络访问能力；只允许显式注册、受控、参数校验、限时和脱敏的 Tool / Connector。
- 前端不得直连任何用户服务。外部服务访问只能由后端 Connector / Tool 在授权服务边界内执行。
- 凭据只能来自当前进程环境或经过 Design 批准的安全密钥引用；不得进入仓库、文档、日志、Trace、事件、结果、截图或 Git。
- 默认调查只读。高风险动作必须经过服务器提案、人工审批、严格白名单执行和独立 Verify；禁止自动批准、通用执行器和聊天文本直接执行。
- 未经用户明确授权，不连接、探测、读取、写入或清理任何真实外部资源。

## 工程规则

> `AGENTS.md` 与 `CLAUDE.md` 必须逐字一致。

- 中文注释、文档和用户可见日志；公开函数有类型标注；跨层数据用 Pydantic/TypedDict；禁止裸 `except` 和新增生产 `print`。
- LLM Agent 继承 `BaseAgent` 并遵守约定运行接口；Tool 继承 `Tool` 并实现受控 `execute`；确定性 Connector/Collector 必须通过显式 Application port/Executor 注入并返回结构化事实。
- 架构、公开 API、迁移、Connector、真实连接、凭据、监控、权限、审批/执行安全和破坏性改动必须先 Design → Review → 用户确认。
- 一个工作包可包含 1–3 个紧密切片，完成时集中 Test → Review → Commit。
- 不直推 `main`；commit 使用 `<类型>: <中文描述>`；只暂存指定文件，禁止无检查的 `git add .`；不得提交 `.env`、`*.local.yaml`、凭据或含 `sk-` 的文件。
