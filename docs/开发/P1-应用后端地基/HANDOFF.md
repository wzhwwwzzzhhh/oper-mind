# P1 HANDOFF — 应用后端地基

> 更新时间：2026-07-26
> 状态：P1.1a、P1.1b、P1.1c 已提交；P1.1d 已完成并提交
> 分支：`feat/p1-application-foundation`　|　稳定基线：`22b58b0 docs: 完成P1应用后端地基设计`
> 真实仓库：`D:\market-handsome\oper-mind`

## 当前已完成

- P0.3 是 P2 的 API/数据契约基线：UUID、UTC `Z`、cursor、Run 幂等、RunEvent sequence/SSE id、终态不可逆和结构化 DiagnosisResult。
- P1.1a `1559266`、P1.1b `3d9d810`、P1.1c `22b58b0` 已提交。
- P1.1d 已实现并验证：同步 SQLAlchemy 2.x、Alembic、psycopg、独立应用 DB Settings、SQLite/PostgreSQL Engine、Session factory、SQLite foreign keys 与跨目录迁移入口。
- 未创建业务表或业务 revision；fresh-db `upgrade head` 只产生 `alembic_version`。
- 真实验证：`pip check`、定向持久化/配置测试 `19 passed`、完整后端测试 `98 passed`、API `11 passed`、mock `/health`、跨目录 Alembic 和 pipeline 均通过；仅既有 Starlette/httpx 弃用警告。

## 稳定命令

从仓库根执行：

```powershell
.\.venv\Scripts\Activate.ps1
$env:OPERMIND_API_KEY = "mock"
$env:OPERMIND_BASE_URL = "http://mock"
$env:OPERMIND_MODEL = "mock"

python -m uvicorn --app-dir backend src.app:app --reload
python -m alembic -c backend\alembic.ini upgrade head
python -m pytest backend\tests\test_persistence_infrastructure.py -q
python -m pytest backend\tests -q
python backend\scripts\smoke_pipeline.py
```

应用数据库 URL：`OPERMIND_APP_DATABASE_URL` > 被忽略的本地 `persistence.database_url` > 根 `data/opermind.sqlite3`。`data/*.sqlite3` 是运行时资产，禁止提交。应用启动不会自动迁移或建表。

## 未完成与边界

- P1.1d 已提交；后续工作区应从该稳定持久化基线开始。
- 不读取、修改、暂存或提交 `frontend/`、`report/`、`.venv/`、`config/config.local.yaml`、运行时数据或实验产物。
- 未创建 P2 业务表、ORM mapper、Repository、Application Service 或 `/api/v1` 路由；阶段一 `/diagnose`、`/diagnose/stream` 必须保持兼容。

## 恢复顺序

```powershell
git status --short --branch
git log -5 --oneline
Get-Content -Raw -Encoding UTF8 AGENTS.md
Get-Content -Raw -Encoding UTF8 docs\开发\_A-Plan-总览.md
Get-Content -Raw -Encoding UTF8 docs\开发\_B-V1产品化开发计划.md
Get-Content -Raw -Encoding UTF8 docs\开发\P1-应用后端地基\HANDOFF.md
Get-Content -Raw -Encoding UTF8 docs\开发\P1-应用后端地基\design.md
Get-Content -Raw -Encoding UTF8 docs\开发\P1-应用后端地基\step4-最小应用层地基落地.md
Get-Content -Raw -Encoding UTF8 docs\开发\P1-应用后端地基\review.md
git diff --no-ext-diff
```

## 唯一下一步

**P2：会话诊断闭环（第一个纵向切片）。**

先完成 P2.1 的 Design：Session、Message、DiagnosisRun、RunEvent、DiagnosisResult、Evidence、幂等记录的最小数据库模型、第一份非空 Alembic revision、Repository 端口、Application Service 事务与 `/api/v1` 契约映射；再按纵向切片实现。不得把 P2 状态、事务或持久化逻辑塞进 Agent 节点。

## P2 必跑验证

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
.\.venv\Scripts\python.exe -m pytest backend\tests -q
.\.venv\Scripts\python.exe -m pytest backend\tests\test_api.py -q
.\.venv\Scripts\python.exe backend\scripts\smoke_pipeline.py
```

P2 还必须新增 fresh-db 业务迁移、状态机、幂等、sequence/SSE 重放、失败安全和结构化结果验证。

## 提交边界

- 仅暂存 P1.1d 的已审查代码、测试、迁移/配置文件和必要文档/入口同步。
- 禁止 `git add .`；提交前检查 `AGENTS.md` 与 `CLAUDE.md` 逐字一致。
- 建议提交信息：`feat: 建立P1应用持久化地基`。
