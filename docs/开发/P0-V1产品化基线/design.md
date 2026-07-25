# P0 设计 — V1 产品化基线

> 日期：2026-07-25　|　状态：P0.1–P0.4 已完成并提交　|　基线提交：`f4478ab`

## 目标

将项目的执行入口从阶段一 M5–M8 演示路线，统一调整为“全栈 + Agent 运维诊断产品”的阶段二 P0–P7 主线，同时保留阶段一 Agent Core、实验与可观察性产物的历史可追溯性。

## P0.1 已完成范围

- 同步总进度、阶段二详细计划的定位、真实目录与启动方式。
- 固化 `frontend/` 主产品前端与 `report/` 研发/实验/Trace 可观察性前端的职责边界。
- 同步日志、交接、真实数据源、mock fallback 和前后端联调规则。
- 为历史路线图和方案说明添加基线提示，不删除历史开发日志或 `docs/初始开发/`。

## P0.1 非目标

- 不修改 `backend/` 业务代码、API 实现或 Agent 编排。
- 不读取、修改、暂存或提交用户未跟踪的 `frontend/`。
- 不修改或删除 `report/`。
- 不初始化主产品 React 工程，不进入 API v1 契约草案或前端原型设计。

## 关键决策

1. `docs/开发/_A-Plan-总览.md` 是项目总进度、当前执行顺序和唯一下一步的真相源；`_B-V1产品化开发计划.md` 是阶段二的详细计划。
2. M0–M7 冻结为阶段一历史基线；M7 收口为 `report/` 的研发/实验/Trace 可观察性前端。原 M8 工作被 P6/P7 吸收。
3. P0–P7 是阶段二主线，当前 P0.1 完成后进入 P0.2，采用纵向切片而非一次性重构。
4. 当前 API/SSE 契约位于 `backend/src/api/`；产品 API 将在后续阶段统一向 `/api/v1` 演进。
5. 真实数据库、外部数据源和前后端联调必须在目标、权限、数据、契约、回退和验收场景上共同确认；确定性 mock fallback 始终保留。

## Step 分解

| Step | 名称 | 状态 | 验收 |
|---|---|---|---|
| P0.1 | 规划与边界同步 | 已完成 | 入口文档与真实目录、阶段边界和工作流互相一致 |
| P0.2 | 现状盘点与产品架构 | 已完成，已提交 | 现状到 V1 契约差距、分层边界、ER 图与状态机 |
| P0.3 | API v1 契约草案 | 已完成，已提交 | 统一 API、SSE、错误体和结构化结果契约 |
| P0.4 | 主前端产品原型 | 已完成，已提交 | 用户确认结果优先的 HTML 原型，再决定 React 初始化 |

## P0.2 目标与范围

- 审计 `backend/src` 的 API/SSE、编排图、Agent/Tool、记忆、审批、配置、目录迁移路径、评测边界与现有测试。
- 建立“当前能力 → V1 产品契约”的差距清单，明确可保留、需要适配和需要替换的职责。
- 定义 Application Service / Agent Core / Infrastructure 边界、渐进目录落点、实体关系和状态机。
- 只更新设计与交接文档，不引入 ORM、Migration、Repository 或新的产品 API。

P0.2 非目标：不修改 `backend/` 业务代码；不读取、修改、暂存或提交 `frontend/`；不修改或删除 `report/`；不完成 P0.3 的精确 OpenAPI 字段定义。

## P0.3 目标与范围

- 将 P0.2 已确认的实体、状态和迁移边界收敛为可实现的 `/api/v1` Pydantic / TypeScript 契约。
- 定义资源 ID、UTC 时间、分页、错误体、request/trace ID、SSE 事件信封、断线恢复和结构化 `DiagnosisResult`。
- 只输出契约与迁移说明；不引入 ORM、Migration、Repository 或新 API 路由。

P0.3 默认锁定：单租户 MVP、UUID、UTC ISO 8601、cursor 分页、`RunEvent.sequence` 映射 SSE `id`、`DiagnosisResult` 为最终结构化事实、旧 `/diagnose` 与 `/diagnose/stream` 保持兼容。

## P0.4 目标与范围

- 在获得用户授权后审计并重构未跟踪资产 `frontend/mockup.html`，保留其深色控制台以外的可复用信息密度，不继承 Trace 主导布局。
- 以 P0.3 契约呈现 Session、DiagnosisRun、RunEvent、DiagnosisResult、Evidence、`requires_approval` 与错误/空/恢复状态。
- 主屏优先展示结构化根因、证据、影响、建议与风险；Agent 协作仅作为摘要，完整 Trace 仅链接 `report/`。
- 使用静态交互切换成功、运行中、失败、空状态；所有数据标为原型/未接入，不调用 API。

P0.4 非目标：不初始化 React/Vite；不改 `backend/`、`report/`；不新增数据库、API 路由或伪造实现；用户确认前不推进 React 工程。

## 变更文件

- `AGENTS.md`、`CLAUDE.md`：真实目录、启动方式、真相源和硬约束镜像。
- `docs/开发/_A-Plan-总览.md`：阶段一冻结、阶段二 P0–P7、当前唯一下一步。
- `docs/开发规范.md`：目录、真相源、P 阶段日志、阶段调整和真实依赖共同确认规则。
- `docs/前端开发路线图.md`：M7/report 历史可观察性前端定位。
- `docs/开发路线图与规划.md`、`docs/00-项目方案说明书.md`：历史基线提示。
- `docs/开发/P0-V1产品化基线/HANDOFF.md`：P0.1 状态与 P0.2 交接。

## 验证与审查

- 比较 `AGENTS.md` 与 `CLAUDE.md`，必须逐字相同。
- 搜索当前入口文档中的旧 `src/`、`src/frontend`、把 M7.5 标为下一步的误导性说明。
- 复核暂存区仅含本 Step 文档和用户删除的 M7 HANDOFF；`frontend/`、`report/` 均不进入暂存。
- 独立 Review 通过后，先询问用户是否允许提交；不得自动提交。
