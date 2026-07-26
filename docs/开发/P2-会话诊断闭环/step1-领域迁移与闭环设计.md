# P2.1 Step1 — 领域、迁移与闭环设计

> 日期：2026-07-26　|　状态：已完成并提交，独立 Review 通过　|　分支：`feat/p2-session-diagnosis`　|　基线：`6aa3302`

## Design

P1 已提供应用数据库、同步 Session factory 与 Alembic 空业务骨架，但尚无业务表和 `/api/v1`。P2.1 先把 P0.3 契约转换为可迁移的数据关系、事务时序和 API 切片，避免在 P2.2 直接创建表时把 Agent 编排、HTTP/SSE 和数据库耦合起来。

## Step

1. 从 P1 稳定基线恢复，创建 `feat/p2-session-diagnosis`，确认工作区干净。
2. 审计现有 `/diagnose`、`/diagnose/stream`、`CoordinatorAgent.route_stream()` 和 TraceRecord，确认它们仍是即时兼容接口而非持久化来源。
3. 固定 Session、Message、DiagnosisRun、RunEvent、DiagnosisResult、幂等记录的表关系、约束、索引和 JSON 安全边界。
4. 固定 Run 状态机、RunEvent sequence 事务、创建 Run 的幂等受理事务、终态结果/失败事务与阶段一 Trace 映射。
5. 拆分 P2.2–P2.5 的实现顺序，明确每一步不可跨越的边界和验收。

## Code

无业务代码、依赖、迁移、ORM mapper、Repository、Application Service 或 `/api/v1` 路由改动。本 Step 只创建 P2 设计、步骤、审查、交接和计划/入口同步文档。

## Test

| 检查 | 结果 |
|---|---|
| Git 基线 | 工作区干净；从 `6aa3302 feat: 建立P1应用持久化地基` 创建 `feat/p2-session-diagnosis` |
| P1 持久化底座 | SQLAlchemy/Alembic/psycopg、应用 DB Settings、Session factory、跨目录 Alembic 已存在；无业务 revision |
| 阶段一兼容映射 | `/diagnose`、`/diagnose/stream` 与 `CoordinatorAgent.route_stream()` 已盘点为 P2 的诊断适配输入，不改其现有行为 |
| P0.3 对齐 | UUID、UTC、cursor、Run 状态、sequence/SSE id、幂等、终态和结构化 Result/Evidence 均进入设计 |
| 范围检查 | 未修改 `frontend/`、`report/`、运行时资产、旧 API 或 P2 业务实现 |

## Review

独立审查见 `review.md`。核心审查结论：用户输入 Message 与 DiagnosisRun 的单向外键避免循环依赖；RunEvent 序列与 Run 状态由短事务保护；SSE 只读已提交事件；ResultAssembler 不允许用 Markdown 正则伪造结构化事实。

## 下一步

唯一下一步为 **P2.2：领域模型、首个业务迁移与 Repository**。只创建已设计的 ORM mapper、第一份非空 Alembic revision 和 Repository 端口/实现与数据库测试；不接入 Agent、HTTP 路由或 SSE。
