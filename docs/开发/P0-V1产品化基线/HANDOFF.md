# P0 HANDOFF — V1 产品化基线

> 更新时间：2026-07-25
> 状态：P0.2 已提交，P0.3 待接手
> 分支：`feat/p0-product-baseline`　|　基线提交：`f4478ab refactor: 重组项目结构 - backend/report/frontend 三目录分离`
> 唯一真实项目：`D:\market-handsome\oper-mind`

## 1. 本次恢复状态

- 已按恢复顺序核对分支、最近提交、`AGENTS.md`、A-Plan、阶段二计划、当前 HANDOFF 和未提交 diff。
- P0.1 仅同步文档：已更新 A-Plan、AGENTS/CLAUDE、开发规范、前端历史路线图及历史基线提示，并新增 `design.md`、`step1-规划与边界同步.md`。
- 用户手动删除 `docs/开发/M7-前端可视化/HANDOFF.md`；该删除是有效变更，必须保留并与 P0.1 文档一并显式暂存。
- `frontend/` 仍为用户未跟踪内容，本 Step 未读取、修改、暂存或提交；`report/` 未修改、暂存或删除。
- P0.1 已以 `docs: 同步P0产品化基线文档` 提交。用户删除的旧 M7 HANDOFF 已按要求纳入该提交。
- 当前工作区只剩用户未跟踪的 `frontend/`；它不属于 P0.1 提交，也未被读取、修改、暂存或提交。
- P0.2 已完成只读审计、架构基线与独立 Review，并已创建文档提交；未修改业务代码、`frontend/` 或 `report/`。

## 2. 产品方向与已确认决策

OperMind 从多 Agent 运维诊断 Demo 转向完整的“全栈 + Agent”产品。阶段二以产品化应用层、会话与持久化、主前端和真实业务闭环为主线；Agent Core 后续按专题渐进优化，不进行无业务收益的大重构。

- 阶段一 M0–M7 作为 Agent Core、实验与可观察性历史基线冻结保留。
- `frontend/` 是 V1 主产品，面向运维用户，结果优先；`report/` 是研发、实验与 Trace 可观察性前端。
- 主产品先做 React Web，未来确有本机能力需求时再用 Tauri。
- 使用纵向切片，第一条产品闭环是“持久化会话诊断”。
- P0 先收敛边界、现状、契约和原型；用户确认原型后才初始化正式 React 工程。
- 项目结构保持稳定，禁止随意新增顶层目录或一次性重排 `backend/src`。

完整长期计划见：`docs/开发/_B-V1产品化开发计划.md`；总进度和唯一下一步以 `docs/开发/_A-Plan-总览.md` 为准。

## 3. 当前仓库结构

```text
D:\market-handsome\oper-mind
├── backend/      # Python/FastAPI + Agent Core
├── frontend/     # V1 主产品前端，当前为用户未跟踪内容
├── report/       # 原 M7 React 研发/实验/Trace 可观察性前端
├── config/
├── data/
├── docs/
├── experiments/
├── AGENTS.md
├── CLAUDE.md
└── .git/
```

当前后端入口与契约分别为 `backend/src/main.py`、`backend/src/app.py`、`backend/src/api/`。`report/` 可用 `npm run dev` 启动；在 P0.4 原型确认并初始化前，不假定 `frontend/` 具有 Node 启动命令。

## 4. 后端现状与产品缺口

已有 `GET /`、`GET /health`、`POST /diagnose`、`GET /diagnose/stream`、`GET /memory/stats`、`POST /memory/clear` 等阶段一接口；SSE 使用 `progress / complete / error`，并输出 Trace。

缺少正式产品能力：Session / Message / DiagnosisRun 持久化、环境与数据源、告警与事件、审批记录和审计、知识库管理、报告持久化、结构化根因/证据/建议契约与正式 `/api/v1` 应用 API。

## 5. P0 拆分与状态

### P0.1 规划与边界同步 — 已完成，已提交

- 已统一总览、真实目录、启动方式、两个前端职责与阶段真相源。
- AGENTS/CLAUDE 已改为逐字一致的硬约束镜像。
- 已同步 P 阶段日志命名、阶段调整记录、真实数据源/前后端联调共同确认与 mock fallback 规则。

### P0.2 现状盘点与产品架构 — 已完成，已提交

- 审计 `backend/src`、现有 schema、SSE 与 Agent 输出。
- 输出 Application Service / Agent Core / Infrastructure 边界与渐进目录方案。
- 输出核心实体 ER 图及 Session、Run、Incident、Approval 状态机。

### P0.3 API v1 契约草案

- 统一 ID、时间、分页、错误体、request ID、SSE event ID。
- 定义 Session / Message / Run / RunEvent / DiagnosisResult。
- 设计“POST 创建 run + GET SSE”的恢复语义，结构化结果不再只返回 Markdown。

### P0.4 主前端产品原型

- 重做 `frontend/mockup.html`，展示会话、环境、问题、实时进度、根因、证据、影响、建议、风险与审批。
- Agent 协作只做摘要，完整 Trace 跳转 `report/`。
- 用户确认后才进入 React 工程。

## 6. 新会话恢复顺序

```powershell
git status --short --branch
git log -5 --oneline
Get-Content -Raw -Encoding UTF8 AGENTS.md
Get-Content -Raw -Encoding UTF8 docs\开发\_A-Plan-总览.md
Get-Content -Raw -Encoding UTF8 docs\开发\_B-V1产品化开发计划.md
Get-Content -Raw -Encoding UTF8 docs\开发\P0-V1产品化基线\HANDOFF.md
```

然后：

1. 确认 `frontend/` 仍未被误纳入 diff 或暂存区；不删除、不覆盖用户改动。
2. 阅读 `design.md`、`step1-规划与边界同步.md`、`review.md` 与本 HANDOFF，确认 P0.1 已收口。
3. 不读取、修改、暂存或提交用户未跟踪的 `frontend/`，除非后续 Step 获得明确授权。
4. 阅读 P0.2 架构盘点文档与本 HANDOFF，确认 P0.2 已收口；然后进入 P0.3 契约草案，不与 HTML 原型或业务代码混成一个提交。

## 7. 提交边界和禁止事项

- 本交接不授权自动提交。
- 不把未跟踪 `frontend/` 与规划文档无检查地一起 `git add .`。
- 不删除 `report/`，它有明确的长期职责。
- 不立刻引入数据库或大规模移动 `backend/src`；P0 先定契约。
- 不创建假的告警、审批、环境“完整平台”界面来掩盖后端缺口；未实现能力使用诚实空状态。
- 不将完整 Trace 再作为主前端视觉中心。
- 不把测试彻底取消；每个纵向切片保留最小质量门。

## 8. 唯一下一步

**P0.3：API v1 契约草案。**

定义 ID、UTC 时间、分页、错误体、request/trace ID、SSE event ID、Session/Run 契约和结构化 `DiagnosisResult`；不实现 ORM、数据库、迁移或新 API 路由。P1 前置风险已记录：配置/数据路径迁移未收口，且当前 `.venv` 解释器失效；P0.3 不得以此绕过或隐藏运行环境问题。
