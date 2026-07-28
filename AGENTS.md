# OperMind — 全栈 Agent 运维诊断产品

OperMind 是面向运维工程师、SRE 与系统管理员的全栈 Agent 运维诊断产品。现有 LangGraph 多 Agent 核心支持 direct / chain / parallel 路由，并提供 Debate、Reflection、审批门、SSE 与 Trace 能力；阶段二将在此基础上完成会话、持久化、环境与数据源、告警事件、审批、知识记忆和报告闭环。

## 技术栈

Python 3.10+、LangGraph、OpenAI SDK、FastAPI、React + TypeScript

## 真实目录与职责

```text
oper-mind/
├── backend/                 # FastAPI、Agent Core、应用服务、持久化、测试和脚本
│   ├── src/
│   │   ├── api/             # 当前 HTTP/SSE 契约、事件与路由边界
│   │   ├── application/     # P2 产品用例、短事务、幂等与执行/结果端口
│   │   ├── domain/          # P2 状态、值对象与 Repository ports
│   │   ├── infrastructure/  # ORM、Repository 与 Coordinator 诊断适配
│   │   ├── agents/          # Server / DB / Log / Report Agent
│   │   ├── core/            # 编排、LLM、Debate、Reflection、Approval
│   │   ├── tools/           # 诊断工具
│   │   ├── memory/          # Agent 记忆
│   │   ├── app.py           # FastAPI 入口
│   │   └── main.py          # CLI 入口
│   ├── tests/
│   └── requirements.txt
├── frontend/                # V1 主产品前端；P0 原型确认后再初始化正式 React 工程
├── report/                  # 阶段一 M7 的研发/实验/Trace 可观察性 React 前端
├── config/                  # 配置模板
├── data/                    # 本地数据与确定性 mock
├── docs/                    # 规划、架构、产品与开发日志
├── experiments/             # 评测与实验产物
├── backend/scripts/         # 后端 smoke、评测与文档脚本
├── AGENTS.md
└── CLAUDE.md
```

## 计划与真相源

- **总进度唯一真相源**：`docs/开发/_A-Plan-总览.md`。阶段一 M0–M7 已完成并冻结为历史基线；阶段二 P0–P7 是当前主线。
- **阶段二详细计划**：`docs/开发/_B-V1产品化开发计划.md`。它展开 P0–P7 的产品范围与顺序，但不替代总览中的进度状态。
- `docs/开发路线图与规划.md`、`docs/初始开发/` 与 M 阶段日志均为历史材料，保留但不作为当前执行入口。
- 当前唯一下一步以 A-Plan 为准：**P3.3c Mock FastAPI SSE 契约已提交为 `ca899e0`；当前进入 P3.4 Design：结构化结果、失败/空/归档收口与受控 Trace 入口。**真实数据库只读验收仍按用户决策延后至前后端大致开发完成后；在后续真实接入前仍不得连接真实 DB 或数据源、运行在线 Alembic 或修改 8000 后端；真实失败不得降级为 mock/假数据。P3.3b 已提交为 `e7858ce`，P3.3a 已提交为 `dc122cc`，P3.2c.1 已提交为 `5491829`，P3.2b 已提交为 `3170e6a`，P3.2a 已提交为 `75d6598`，P3.2 Design 已提交为 `ec45ee2`，P3.1 已提交为 `4862752 feat: 初始化P3主前端工程与产品外壳`，P2.5 已提交为 `54f02e5 feat: 完成P2.5刷新恢复与闭环验收`。

## 常用命令

```powershell
.\.venv\Scripts\Activate.ps1                    # 激活根目录虚拟环境（PowerShell）
$env:PYTHONPATH = "$PWD\backend;$PWD"           # 迁移期同时解析 backend/src 与根 data/config
$env:OPERMIND_API_KEY = "mock"                   # 迁移期显式配置 mock，绕过尚未收口的配置路径
$env:OPERMIND_BASE_URL = "http://mock"
$env:OPERMIND_MODEL = "mock"
python -m src.main                               # 运行后端 CLI
python -m uvicorn src.app:app --reload           # 启动 FastAPI，默认 http://127.0.0.1:8000

Set-Location report
npm run dev                                     # 启动研发/实验/Trace 可观察性前端
```

`frontend/` 是 V1 主产品前端。P0.4 原型经用户确认并完成 React 工程初始化前，不假定其具有 `npm run dev` 启动命令；不得把 `report/` 当作主产品前端，也不得删除它。`backend/src/project_paths.py` 是根 `config/`、`data/` 与 `experiments/` 的唯一资源路径来源；配置依次读取根 `config.local.yaml`、根 `config.example.yaml`，再由 `OPERMIND_*` 环境变量覆盖。应用元数据数据库 URL 的优先级为 `OPERMIND_APP_DATABASE_URL`、本地 `persistence.database_url`、根 `data/opermind.sqlite3`；仅用显式 Alembic 迁移，运行时 SQLite 文件不得提交。脚本和测试不得依赖当前工作目录或把 `backend/` 当资源根；迁移期遗留 `PYTHONPATH` 即使存在也不得改变资源路径解析。

## 开发规则

> `AGENTS.md` 与 `CLAUDE.md` 是**同一份精简硬约束的镜像**；两者内容必须逐字一致。
> 完整规则的唯一真相源是 `docs/开发规范.md`；总进度的唯一真相源是 `docs/开发/_A-Plan-总览.md`。

- **代码规范**：注释用中文；类名大驼峰，函数/变量小写下划线，常量全大写；公开函数必须带类型标注；跨层结构化数据用 Pydantic / TypedDict，不裸传 dict；禁止裸 `except` 和新增生产 `print`。
- **架构边界**：Tool 继承 `backend/src/core/tool_registry.py` 的 `Tool` 并实现 `execute`；Agent 继承 `BaseAgent` 并复用 ReAct `run()`；当前 HTTP API、SSE 事件和公开契约位于 `backend/src/api/`，`backend/src/app.py` 只负责入口与装配。阶段二产品 API 统一向 `/api/v1` 演进，业务用例、持久化与权限不得直接塞入 Agent 节点；Graph 状态走显式 `DiagnosisState`。
- **Mock、真实数据与安全**：`api_key="mock"` 是一等公民；每个外部依赖必须有确定性 mock fallback。应用元数据数据库与诊断数据源必须隔离，`/api/v1` 不得在持久化不可用时静默降级为内存；应用 schema 只经显式 Alembic 迁移，启动不得 `create_all()` 或自动升级。接入真实数据库、数据源或前后端联调前，必须共同确认连接目标、最小权限、可用数据、接口契约、回退路径和验收场景；密钥只读环境变量，真实 DB 仅只读账号和参数化查询，诊断工具禁 DDL/DML，高危操作必须经过审批门。
- **测试与复现**：测试默认 mock；direct / chain / parallel 均需冒烟覆盖。修改 graph / debate / reflection / approval 必跑 `backend/scripts/smoke_pipeline.py`。评测必须关闭长期记忆读写，实验固定种子并以 config hash 落盘。产品切片至少保留启动检查、Migration、核心 API smoke、SSE 联调、前端构建和主流程人工验收。
- **重要改动工作流**：架构、接口契约、安全、里程碑产出和非平凡 bug 均按 **Design → Step → Code → Test → Review → Commit** 执行。每个 step 收尾即做 Review；架构、删文件、非平凡改动须独立 code review 通过后才能提交；测试、审查、Git 不可后置。
- **开发日志**：重要里程碑日志放 `docs/开发/M<N>-<名称>/` 或 `docs/开发/P<N>-<名称>/`，包含 `design.md`、一个或多个 `stepN-*.md`、`review.md`。跨阶段规则/流程治理日志放 `docs/开发/治理-<名称>/`。日志是带日期与 commit 的快照，记录关键片段和 `文件路径:行号` 锚点，不贴整文件。`docs/初始开发/` 是历史归档，不再新增日志。
- **上下文交接与恢复**：一个 step 必须在可控范围内完成 **Design → Code → Test → Review → Commit**；预计跨上下文、实现超过 3–5 个文件、出现 P1/P2 审查问题或上下文接近上限时，先在对应 `docs/开发/M<N>-<名称>/HANDOFF.md` 或 `docs/开发/P<N>-<名称>/HANDOFF.md` 写清状态、基线提交、已完成项、未完成/阻塞项、唯一下一步、必跑验证和提交边界。恢复固定执行 `git status --short`、查看最近提交、阅读 A-Plan 与当前 `HANDOFF.md` / `design.md`、核对未提交 diff；记录与 diff 不一致时先核对，禁止猜测或提交。step 提交后必须回填最终状态或移除临时 HANDOFF。
- **文档同步**：目录、节点流、Agent/Tool 关系、API/SSE 契约、真实数据源接入或工作流变更时，必须同步更新 `AGENTS.md`、`CLAUDE.md`、`docs/开发规范.md`；影响阶段状态时同时更新 `_A-Plan-总览.md`，影响阶段二范围时同步 `_B-V1产品化开发计划.md`。
- **Git**：阶段一历史分支沿用 `feat/mN-*`；阶段二里程碑使用 `feat/pN-*`。commit 使用 `<类型>: <中文描述>`；不直推 `main`；不提交 `.env`、`*.local.yaml`、凭证或含 `sk-` 的文件；暂存必须指定文件，禁止无检查的 `git add .`。
