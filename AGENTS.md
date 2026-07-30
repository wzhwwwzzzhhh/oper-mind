# OperMind — 多 Agent DevOps Copilot

OperMind 是面向研发与运维人员的多 Agent DevOps Copilot。它在**受控、可复现、与应用元数据隔离**的运维靶场中协调数据库、日志和服务器 Agent，完成故障调查、证据化判断、修复提案、人工审批、白名单执行与验证闭环。多 Agent、SSE、Trace 与评测是产品能力和技术验证，不是脱离产品的独立目标。

## 技术栈

Python 3.10+、LangGraph、OpenAI SDK、FastAPI、React + TypeScript、PostgreSQL（P4 受控靶场经本地隧道接入）

## 真实目录与职责

```text
oper-mind/
├── backend/                 # FastAPI、Agent Core、应用服务、持久化、测试和脚本
│   ├── src/
│   │   ├── api/             # HTTP/SSE 契约、事件与路由边界
│   │   ├── application/     # 用例、短事务、幂等、审批/执行/验证编排
│   │   ├── domain/          # 状态、值对象与 Repository ports
│   │   ├── infrastructure/  # ORM、Repository 与诊断/靶场适配器
│   │   ├── agents/          # Server / DB / Log / Report Agent
│   │   ├── core/            # 编排、LLM、Debate、Reflection、Approval
│   │   ├── tools/           # 只读诊断工具与受控执行工具
│   │   ├── memory/          # Agent 记忆
│   │   ├── app.py           # FastAPI 入口
│   │   └── main.py          # CLI 入口
│   ├── tests/
│   └── requirements.txt
├── frontend/                # 主产品：调查、证据、提案、审批、执行与验证
├── report/                  # 研发/Trace/评测控制台，不是主产品前端
├── demo/                    # 与产品元数据隔离的受控演示靶场
├── config/                  # 配置模板
├── data/                    # 本地数据与确定性 mock
├── docs/                    # 规划、架构、产品与开发日志
├── experiments/             # 毕设评测与实验产物
├── backend/scripts/         # smoke、评测与文档脚本
├── AGENTS.md
└── CLAUDE.md
```

## 计划与真相源

- **总进度与唯一下一步**：`docs/开发/_A-Plan-总览.md`。
- **阶段范围与 MVP 路线**：`docs/开发/_B-V1产品化开发计划.md`；它不维护第二个“当前唯一下一步”。
- **当前产品定位与 P4.0 入口**：`docs/开发/治理-DevOps-Copilot-MVP重定位/`。用户于 **2026-07-30** 授权 Work 1 使用其本地隧道中的隔离数据库 `opermind_demo`；真实 smoke 已通过，且最终清理已删除 `opermind_demo` schema。未经新的 Design → Review → 用户授权，不得进入 Work 2 的 Agent、API、前端或真实数据源实现。
- P4 Work 1 的唯一可操作目标：`127.0.0.1:5433` → `opermind_demo` → `opermind_demo.orders`。它通过用户提供的本地隧道到达其服务器；**绝不连接、读取、写入或清理 `gongkar`**，也不访问任意其他数据库、schema、表或端口。
- `治理-个人AI运维助手产品重定位/`、P3.5/P3.6 的长期会话、发送幂等和 SSE 恢复设计，以及 `P3-主前端工作台/` 均已**封存为历史技术成果**；可按未来工作包选择性复用，但不得再作为当前需求或下一步。
- M0–M7、`report/`、评测和 `docs/初始开发/` 是研发/毕设/历史材料，不是当前产品执行入口；不得删除 `report/`。
- 已发布 `/api/v1` 契约、P2 持久化模型与 P3 测试事实必须继承；历史体验文案不等于当前产品需求。

## 常用命令

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "$PWD\backend;$PWD"
$env:OPERMIND_API_KEY = "mock"
$env:OPERMIND_BASE_URL = "http://mock"
$env:OPERMIND_MODEL = "mock"
python -m src.main
python -m uvicorn --app-dir backend src.app:app --reload

Set-Location frontend
npm run dev

Set-Location report
npm run dev
```

`backend/src/project_paths.py` 是根 `config/`、`data/`、`experiments/` 的唯一资源路径来源。配置依次读取根 `config.local.yaml`、根 `config.example.yaml`，再由 `OPERMIND_*` 环境变量覆盖。应用元数据数据库 URL 的优先级为 `OPERMIND_APP_DATABASE_URL`、本地 `persistence.database_url`、根 `data/opermind.sqlite3`；schema 只经显式 Alembic 迁移，运行时 SQLite 文件不得提交。脚本和测试不得依赖当前工作目录或把 `backend/` 当资源根。

## 开发规则

> `AGENTS.md` 与 `CLAUDE.md` 是同一份精简硬约束的镜像，内容必须逐字一致。完整规则以 `docs/开发规范.md` 为准。

- **代码与边界**：中文注释；公开函数带类型标注；跨层结构化数据使用 Pydantic / TypedDict；禁止裸 `except` 和新增生产 `print`。Tool 继承 `Tool` 并实现 `execute`；Agent 继承 `BaseAgent` 并复用 ReAct `run()`；Graph 状态使用显式 `DiagnosisState`。HTTP/SSE 契约位于 `backend/src/api/`，`app.py` 只做入口与装配。
- **安全与真实数据**：每个外部依赖必须有确定性 mock fallback。诊断适配器默认只读、参数化、限时；应用元数据与诊断数据源隔离。仅独立的受控执行器可在**用户授权的隔离靶场**经人工审批执行严格白名单动作；禁止模型任意 SQL、Shell、DDL/DML，禁止连接真实生产资源。真实连接必须先确认目标、最小权限、数据边界、契约、回退和验收。
- **P4 目标硬边界**：连接参数只能来自环境变量；代码必须 fail-closed 地校验 `127.0.0.1:5433/opermind_demo`，所有 DDL 仅限 `opermind_demo` schema 中预定义的 `orders` 表和 `idx_orders_user_created` 索引。不得记录凭证，不得使用或探测 `gongkar`。
- **工作包节奏**：以可验收的纵向工作包为单位（通常包含 1–3 个紧密相关切片），而不是每个微步骤都 Design/Review/Commit。工作包先确定目标、边界和验收，再连续实现与增量测试；完成时集中 Test → Review → Commit。架构、公开契约、迁移、真实数据源、审批/执行安全和破坏性改动必须在实现前设计并独立审查。
- **测试与文档**：测试默认 mock；改 graph / debate / reflection / approval 必跑 `backend/scripts/smoke_pipeline.py`。P4 靶场工作包还须有启动、故障注入、修复、验证 smoke；默认清理数据与进程。重要工作包记录设计、关键取舍、测试和 Review；小改动只需测试与 commit message。跨上下文或工作包未收口时写 `HANDOFF.md`，提交后关闭或更新。
- **Git**：阶段二功能分支沿用 `feat/pN-*`；commit 使用 `<类型>: <中文描述>`；不直推 `main`；不提交 `.env`、`*.local.yaml`、凭证或含 `sk-` 的文件；暂存必须指定文件，禁止无检查的 `git add .`。