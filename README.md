# OperMind

OperMind 是一个面向研发与运维人员的**会话式多 Agent DevOps Copilot**。

产品主界面是类似 DeepSeek 的对话系统：用户创建会话、提出运维问题或下达受控指令；系统根据会话上下文、已接入服务、监控事实和受控工具完成调查，并在需要时发起人工审批、执行与验证。

## 核心产品能力

- **会话工作台**：创建、切换和持续使用运维会话；会话是用户的主入口。
- **多 Agent 协作**：由协调角色分派调查，数据库、缓存、服务与日志等角色提供受控事实，最终形成可读结论。
- **简要 Trace**：展示角色、阶段、工具类别、状态、耗时和证据摘要；可展开查看结构化依据，但绝不展示模型 CoT、Prompt、原始敏感数据或凭据。
- **服务中心**：用户可以接入并管理 PostgreSQL、MySQL、Redis 等服务；每个服务有状态、监控和从服务进入调查会话的入口。
- **受控行动闭环**：只读调查默认执行；高风险动作必须经过提案、人工审批、白名单执行和执行后验证。

## 当前原则

这是一个正式的前后端产品，不是多 Agent、RAG、Trace 或评测的实验集合。它会逐步支持多种中间件和数据库，但每种新 Connector、凭据处理方式、监控读取与可执行动作都必须经过独立的产品和安全设计。

## 当前状态

产品骨架与横向能力已由 P0–P7 铺完（会话与多 Agent 内核、工具网关、服务中心、监控快照与趋势、
知识检索、模型 Provider 管理、受控动作闭环、跨服务联合调查）。当前处于**体验驱动完善阶段**：
不新增能力，只修跑不通的链路和误导用户的占位。

已实现不等于已启用——未接通的能力在 UI 中如实标注"未启用"，Agent 侧也不存在对应工具。

## 仓库结构

```text
backend/    正式后端；API 主线 src.app:app 的 /api/v1
frontend/   正式前端；入口 src/app/App.tsx
demo/       专用演示靶场，不是产品入口
docs/       文档；索引见 docs/README.md
```

## 文档入口

从 `docs/README.md` 开始，它按「事实源 / 工作地图 / 执行产物」三层组织：

- 事实源：`docs/产品定义.md`、`docs/路线图.md`、`docs/开发规范.md`、`docs/架构与开发路径.md`
- 工作地图：`docs/完善清单.md`（当前主线）、`docs/backlog.md`、`docs/跑通验证.md`
- 执行产物：`docs/prd/`、`docs/design/`、`docs/workpack/`

`docs/归档/` 内是已被取代的历史文档（旧架构草案、P3 重构计划、历史接口清单），只作历史参考，
**不作为当前需求来源**。

## 本地开发

后端从 `backend/` 执行，用仓库根 `.venv`：

```bash
..\.venv\Scripts\python.exe -m pytest tests -q
..\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head   # 迁移需显式执行
..\.venv\Scripts\python.exe -m uvicorn src.app:app --reload --port 8000
```

前端从 `frontend/` 执行，开发服务固定 `5174`，`/api` 默认代理到 `http://127.0.0.1:8000`：

```bash
npm install && npm run dev
npm run typecheck && npm run test && npm run build
```

敏感配置走环境变量（`OPERMIND_API_KEY`、`OPERMIND_BASE_URL`、`OPERMIND_MODEL`、
`OPERMIND_APP_DATABASE_URL`、`OPERMIND_SERVICE_<ID>_DSN`）；`config/config.local.yaml` 被 Git 忽略。
凭据不得进入仓库、日志、Trace、结果或接口响应。
