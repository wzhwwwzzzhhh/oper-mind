# P0 Step1 — 规划与边界同步

> 日期：2026-07-25　|　状态：已完成　|　关联 commit：`docs: 同步P0产品化基线文档`

## Design

迁移提交 `f4478ab` 已将仓库拆分为 `backend/`、`frontend/`、`report/`，但入口规则仍描述根级 `src/` 和 `src/frontend/`，且 A-Plan 仍将 M7.5 作为下一步。这会让后续开发误把研发可观察性前端当作产品前端，并可能把历史 M8 与当前 V1 工作混在一起。

本 Step 用最小文档变更建立阶段二入口：阶段一 M0–M7 冻结，`report/` 保留其 M7 职责，`frontend/` 是主产品；P0–P7 接管当前主线。业务代码和未跟踪 `frontend/` 明确排除。

## Step

1. 按交接顺序核对分支、最近提交、规则、A-Plan、阶段二计划、HANDOFF 与未提交 diff。
2. 以 `backend/src/app.py`、`backend/src/main.py`、`backend/src/api/` 和 `report/package.json` 核对真实入口与启动方式。
3. 同步 A-Plan、AGENTS/CLAUDE、开发规范、前端路线图和历史文档提示。
4. 更新 P0 HANDOFF，补齐本设计和 Step 日志。
5. 审查 diff、搜索误导性入口、逐字比较镜像文件，并只暂存本 Step 文档与用户删除的 M7 HANDOFF。

## Code

- `AGENTS.md:1`、`CLAUDE.md:1`：改为真实 `backend/`、`frontend/`、`report/` 目录与启动方式；明确双文件逐字一致。
- `docs/开发/_A-Plan-总览.md:1`：将总览改为阶段一冻结、阶段二 P0–P7 当前主线，P0.1 为唯一下一步。
- `docs/开发规范.md:44`：将当前 API/SSE 契约位置改为 `backend/src/api/`，新增 `/api/v1` 演进与真实依赖共同确认约束。
- `docs/前端开发路线图.md:1`：将其定位为 M7/report 的历史可观察性路线，主产品入口转交 P 阶段文档。
- `docs/开发/P0-V1产品化基线/HANDOFF.md:1`：记录 P0.1 待 Review/提交与 P0.2 的切换条件。

## Test

- 文档类 Step，不运行后端或前端构建；不触碰 `backend/`、`frontend/`、`report/` 源码。
- 已核对当前 API/SSE 实现位置：`backend/src/api/schemas.py`、`backend/src/api/events.py`、`backend/src/app.py`。
- 已核对研发可观察性前端启动配置：`report/package.json`、`report/vite.config.ts`。

## Review

- 已完成独立文档 Review，详见 `docs/开发/P0-V1产品化基线/review.md`。
- 检查了阶段入口一致性、AGENTS/CLAUDE 逐字一致、旧入口误导性搜索、`git diff --check` 和暂存边界。
- 结论：通过；暂存后必须先询问用户是否允许提交。
