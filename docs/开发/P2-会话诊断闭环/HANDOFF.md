# P2 HANDOFF — 会话诊断闭环

> 更新时间：2026-07-26
> 状态：P2.1 已完成并提交
> 分支：`feat/p2-session-diagnosis`　|　稳定基线：`6aa3302 feat: 建立P1应用持久化地基`
> 真实仓库：`D:\market-handsome\oper-mind`

## 当前已完成

- P1 已完成：根环境、集中路径/配置、持久化设计和 SQLAlchemy/Alembic/psycopg 基础设施均已提交。
- P2.1 已将 P0.3 契约落为可实施设计：Session、Message、DiagnosisRun、RunEvent、DiagnosisResult、Evidence 与幂等记录的关系、迁移、状态机、事务、Trace 映射和 API/SSE 切片已经固定。
- 现有 `/diagnose`、`/diagnose/stream`、`CoordinatorAgent.route_stream()` 已盘点为阶段一兼容输入；P2 只在应用层新增持久化和 `/api/v1`。

## P2.1 核心决策

```text
用户 Message -> Run.input_message_id（受理事务先写）
Run -> Event（sequence 单调、唯一、提交后 SSE）
Run -> Result（成功时最多一个）
助手 Message -> run_id（成功事务后写，避免循环外键）
Run idempotency -> session + endpoint + key + query fingerprint
Agent Core -> DiagnosisExecutor adapter（不写 DB、不持有事务）
```

首个业务 migration 只创建 `sessions`、`messages`、`diagnosis_runs`、`run_events`、`diagnosis_results`、`run_idempotency_keys`。每张表的 UUID、UTC、JSON 脱敏、约束和索引见 `design.md`。无 P4 数据源、P5 审批、RBAC 或前端表。

## 未完成与边界

- P2.1 已提交；后续工作区应从该稳定设计基线开始。
- P2.2 才创建 ORM mapper、第一份非空 Alembic revision、Repository 端口/实现和数据库测试；不接入 Agent、Application Service、HTTP 路由或 SSE。
- 不读取、修改、暂存或提交 `frontend/`、`report/`、`.venv/`、`config/config.local.yaml`、运行时 SQLite、运行时数据或实验产物。
- 阶段一 `/diagnose`、`/diagnose/stream` 必须保持兼容。

## 恢复顺序

```powershell
git status --short --branch
git log -5 --oneline
Get-Content -Raw -Encoding UTF8 AGENTS.md
Get-Content -Raw -Encoding UTF8 docs\开发\_A-Plan-总览.md
Get-Content -Raw -Encoding UTF8 docs\开发\_B-V1产品化开发计划.md
Get-Content -Raw -Encoding UTF8 docs\开发\P2-会话诊断闭环\HANDOFF.md
Get-Content -Raw -Encoding UTF8 docs\开发\P2-会话诊断闭环\design.md
Get-Content -Raw -Encoding UTF8 docs\开发\P2-会话诊断闭环\step1-领域迁移与闭环设计.md
Get-Content -Raw -Encoding UTF8 docs\开发\P2-会话诊断闭环\review.md
git diff --no-ext-diff
```

## 唯一下一步

**P2.2：领域模型、首个业务迁移与 Repository。**

仅实现 P2.1 已设计的 ORM mapper、第一份非空 Alembic revision、Repository ports/SQLAlchemy implementations 和 fresh-db/约束/查询测试。不得接入 Coordinator、Application Service、`/api/v1`、SSE、前端或真实数据源。

## P2.2 必跑验证

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
.\.venv\Scripts\python.exe -m pytest backend\tests -q
.\.venv\Scripts\python.exe -m pytest backend\tests\test_persistence_infrastructure.py -q
.\.venv\Scripts\python.exe backend\scripts\smoke_pipeline.py
```

P2.2 还必须覆盖 fresh DB 的首个业务 migration、外键/唯一/检查约束、RunEvent sequence、归档 Session 查询和 Repository 不自行 commit/rollback。

## 提交边界

- 当前待提交仅包括 P2.1 文档和必要的计划/入口同步文件。
- 禁止 `git add .`；提交前检查 `AGENTS.md` 与 `CLAUDE.md` 逐字一致。
- 建议提交信息：`docs: 完成P2会话诊断闭环设计`。
