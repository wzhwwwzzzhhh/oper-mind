# P1 HANDOFF — 应用后端地基

> 更新时间：2026-07-26
> 状态：P1.1a、P1.1b 已提交；P1.1c 已完成并提交
> 分支：`feat/p1-application-foundation`　|　稳定基线：`3d9d810 refactor: 收口P1配置与数据路径`
> 真实仓库：`D:\market-handsome\oper-mind`

## 当前已完成

- P0.3 API v1 契约仍是 P1/P2 的唯一实现边界：UUID、UTC `Z`、cursor、Run 幂等、RunEvent sequence/SSE id、终态不可逆和结构化 DiagnosisResult。
- P1.1a 已提交 `1559266`；根 `.venv`、锁定依赖、mock 健康检查、API smoke 与 pipeline 已验证。
- P1.1b 已提交 `3d9d810`；集中式 `project_paths.py`、根配置/数据/实验目录和跨目录脚本/测试已稳定。
- P1.1c 已完成设计：同步 SQLAlchemy 2.x + Alembic，SQLite 本地开发、PostgreSQL 生产兼容；应用数据库与诊断数据源隔离；Application Service 负责短事务；SSE 只发布已提交的 RunEvent；启动不自动迁移。

## 未完成与边界

- P1.1c 已提交；后续工作区应从该稳定设计基线开始。
- P1.1d 才新增锁定依赖、应用数据库 Settings、Engine/Session factory、Alembic 环境与迁移测试底座；不创建业务表、空业务 revision、Repository、Application Service 或 `/api/v1` 路由。
- 不读取、修改、暂存或提交 `frontend/`、`report/`、`.venv/`、`config/config.local.yaml`、运行时数据或实验产物。
- 阶段一 `/diagnose`、`/diagnose/stream` 必须保持兼容；P2 只新增 `/api/v1`。

## P1.1d 实施决策

```text
同步 SQLAlchemy 2.x + Alembic + psycopg
SQLite：本地开发与临时测试 URL
PostgreSQL：共享/生产应用元数据数据库
Application Service：事务、幂等、状态机、异常映射
Repository：聚合端口，禁止自行 commit/rollback
SSE：读取已提交 RunEvent；sequence == SSE id
迁移：显式 upgrade head；应用启动不 create_all/不自动升级
```

应用数据库 URL 优先级为 `OPERMIND_APP_DATABASE_URL` > 忽略的本地 `persistence.database_url` > P1.1d 的本地 SQLite 默认值。`api_key="mock"` 不是 v1 内存持久化 fallback；持久化不可用时新 v1 用例必须安全失败，旧 API 不受影响。

## 恢复顺序

```powershell
git status --short --branch
git log -5 --oneline
Get-Content -Raw -Encoding UTF8 AGENTS.md
Get-Content -Raw -Encoding UTF8 docs\开发\_A-Plan-总览.md
Get-Content -Raw -Encoding UTF8 docs\开发\_B-V1产品化开发计划.md
Get-Content -Raw -Encoding UTF8 docs\开发\P1-应用后端地基\HANDOFF.md
Get-Content -Raw -Encoding UTF8 docs\开发\P1-应用后端地基\design.md
Get-Content -Raw -Encoding UTF8 docs\开发\P1-应用后端地基\step3-应用后端地基设计.md
Get-Content -Raw -Encoding UTF8 docs\开发\P1-应用后端地基\review.md
git diff --no-ext-diff
```

## 唯一下一步

**P1.1d：最小应用层地基落地。**

严格按 P1.1c 设计只建立基础设施和验证底座。先确认并锁定依赖版本、数据库 URL 规则与本地临时 SQLite 测试策略；实现前不得跳过 Design/Step，也不得直接创建 P2 业务表或 API。

## P1.1d 必跑验证

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest backend\tests -q
.\.venv\Scripts\python.exe backend\scripts\smoke_pipeline.py
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
```

P1.1d 新增的 fresh-db migration、Session rollback、SQLite foreign-key 和 PostgreSQL 方言编译测试也必须真实通过。

## 提交边界

- 当前待提交仅包括 P1.1c 文档和必要的 A-Plan/B 计划/入口同步文件。
- 禁止 `git add .`；提交前检查 `AGENTS.md` 与 `CLAUDE.md` 逐字一致。
- 建议提交信息：`docs: 完成P1应用后端地基设计`。
