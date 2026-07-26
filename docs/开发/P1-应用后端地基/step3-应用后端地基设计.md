# P1.1c Step3 — 应用后端地基设计

> 日期：2026-07-26　|　状态：已完成并提交，独立 Review 通过　|　分支：`feat/p1-application-foundation`　|　基线：`3d9d810`

## Design

P0.3 已定义 V1 Session、Run、Event、Result、UUID、UTC、cursor、幂等与 SSE 恢复契约，但仓库当前没有 ORM、Alembic、应用数据库 URL、迁移目录或 Application Service。本 Step 不以“先建表再补边界”的方式推进，而是先固定应用数据库与未来诊断数据源的职责分离、SQLite/PostgreSQL 可移植策略、事务所有权、事件提交顺序和迁移纪律。

## Step

1. 从 `3d9d810` 恢复干净工作区，阅读 P1 交接、P0.3 契约、当前依赖、配置和阶段二计划。
2. 审计确认 `backend/requirements.txt` 未启用 SQLAlchemy/Alembic/驱动，`backend/src/config.py` 仅处理 LLM 配置，现有 API 仍为阶段一兼容接口。
3. 形成 P1.1d 的最小落地边界：同步 SQLAlchemy、Alembic、明确 Session 生命周期、迁移命令、SQLite 本地/ PostgreSQL 生产兼容与测试策略。
4. 形成 P2 承接规则：Run 受理、事件追加、终态结果、幂等键、SSE 重放和安全失败的事务顺序均由持久化契约约束。

## Code

无代码、依赖、配置、数据库、迁移、Repository、Application Service 或 API 路由改动。本 Step 只更新 P1 设计、步骤、审查、交接与进度入口。

## Test

| 检查 | 结果 |
|---|---|
| Git 基线 | 工作区干净；当前 `3d9d810 refactor: 收口P1配置与数据路径` |
| 依赖盘点 | `backend/requirements.txt` 没有 SQLAlchemy、Alembic 或 PostgreSQL 驱动；P1.1d 才新增锁定依赖 |
| 契约对齐 | P0.3 的 UUID、UTC、Run 状态机、`sequence`/SSE `id`、幂等和失败语义均被纳入设计 |
| 边界检查 | 明确 P1.1c 不创建表、不改旧 API、不改 `frontend/`、`report/` 或运行时资产 |
| 文档检查 | 提交前执行 `git diff --check`、A-Plan/B 计划下一步一致性、`AGENTS.md`/`CLAUDE.md` 逐字一致性检查 |

## Review

独立审查见 `review.md`。结论：同步 ORM 路线与显式迁移可承接现有同步 FastAPI/LangGraph 调用；不共享 SQLAlchemy Session、短事务持久化事件后再 SSE、禁止 v1 内存降级和应用 DB/诊断数据源隔离共同消除了 P2 的主要基础风险。

## 下一步

唯一下一步为 **P1.1d：最小应用层地基落地**。只新增已批准的依赖、Settings、Engine/Session factory、Alembic 环境与迁移测试底座；仍不创建 Session/Run 业务表、不实现 Repository 或 `/api/v1` 路由。
