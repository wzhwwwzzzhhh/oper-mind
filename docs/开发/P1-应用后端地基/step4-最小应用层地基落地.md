# P1.1d Step4 — 最小应用层地基落地

> 日期：2026-07-26　|　状态：已完成并提交，独立 Review 通过　|　分支：`feat/p1-application-foundation`　|　基线：`22b58b0`

## Design

严格执行 P1.1c：只建立同步 SQLAlchemy、Alembic、应用数据库 Settings、Engine/Session factory 与验证底座。应用元数据数据库独立于未来 P4 诊断数据源；应用启动不建表、不迁移；P2 才创建 Session、Message、DiagnosisRun、RunEvent、DiagnosisResult 等业务 schema 和 `/api/v1` 用例。

## Step

1. 锁定并在根 `.venv` 安装 `SQLAlchemy==2.0.51`、`alembic==1.18.5`、`psycopg[binary]==3.3.4`。
2. 在根配置模板与 `src.config` 增加独立的应用数据库 URL：`OPERMIND_APP_DATABASE_URL` > 本地 `persistence.database_url` > 根 `data/opermind.sqlite3`。
3. 新增 `src.infrastructure.persistence`：跨方言命名约束、同步 Engine、Session factory、SQLite foreign-key pragma；不声明 ORM 模型、不调用 `create_all()`。
4. 新增 `backend/alembic.ini`、`backend/migrations/env.py`、模板与说明。迁移入口支持从非仓库目录执行，仅创建 Alembic 迁移版本元数据，不创建业务表。
5. 新增基础设施测试并执行完整后端回归、旧 API、健康检查与 smoke pipeline。

## Code

- `backend/requirements.txt`：固定 ORM、迁移和 PostgreSQL 驱动版本。
- `config/config.example.yaml`、`backend/src/config.py`：应用数据库 Settings 与环境变量覆盖；不暴露实际连接串。
- `backend/src/infrastructure/persistence/database.py`：`Base` 命名约束、`create_app_engine()`、`PersistenceRuntime` 与 `session_factory`。仅接受 SQLite/PostgreSQL URL；SQLite 连接启用外键。
- `backend/migrations/`、`backend/alembic.ini`：显式 Alembic 环境与跨目录启动桥接。无业务 revision。
- `backend/tests/test_persistence_infrastructure.py`：配置优先级、默认 SQLite、rollback、foreign key、PostgreSQL 方言编译、非目标数据库拒绝和非根目录 fresh-db `upgrade head`。
- `.gitignore`：忽略本地 `data/*.sqlite3`；验证产生的运行时数据库已删除，未进入 Git 状态。

## Test

| 验证 | 实际结果 |
|---|---|
| 安装/完整性 | `pip install -r backend/requirements.txt` 成功；`pip check` 返回 `No broken requirements found.` |
| 定向基础设施 | `python -m pytest backend/tests/test_persistence_infrastructure.py backend/tests/test_project_paths.py backend/tests/test_eval_config.py -q`：`19 passed` |
| Alembic 跨目录 | 临时目录执行 `python -m alembic -c D:\market-handsome\oper-mind\backend\alembic.ini upgrade head` 成功；fresh SQLite 只生成 `alembic_version`，没有业务表 |
| 完整后端回归 | `python -m pytest backend/tests -q`：`98 passed`；仅既有 Starlette/httpx 弃用警告 |
| 旧 API | `python -m pytest backend/tests/test_api.py -q`：`11 passed`；同一既有弃用警告 |
| mock 健康检查 | 从 `backend/` 使用根 `.venv`：`GET /health` 返回 `200`、`mode=mock` |
| pipeline 跨目录 | 临时目录执行 `backend/scripts/smoke_pipeline.py`：direct / chain / parallel / debate 全部通过 |

## Review

独立审查见 `review.md`。确认没有业务表、ORM mapper、Repository、Application Service、`/api/v1` 路由、`create_all()`、自动迁移或 v1 内存降级；应用数据库与诊断数据源继续隔离。

## 下一步

唯一下一步为 **P2：会话诊断闭环（第一个纵向切片）**。先为 Session、Message、DiagnosisRun、RunEvent、DiagnosisResult 设计第一个非空业务 migration 与应用用例；旧 `/diagnose`、`/diagnose/stream` 必须保持兼容。
