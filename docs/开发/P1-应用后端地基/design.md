# P1 设计 — 应用后端地基

> 日期：2026-07-26　|　状态：P1.1a、P1.1b、P1.1c 已提交；P1.1d 已完成并提交　|　稳定基线：`22b58b0 docs: 完成P1应用后端地基设计`

## 目标

P1 为 V1 产品建立可迁移、可审计、可恢复的应用持久化基础。P1.1d 只落地锁定依赖、应用数据库 Settings、同步 Engine/Session factory、Alembic 环境与测试底座；不创建业务表、ORM mapper、Repository、Application Service 或 `/api/v1` 路由。P2 才以 P0.3 契约实现第一个 Session/Run 纵向切片。

## 已完成基线

- P1.1a：根 `.venv`、锁定依赖与 mock 验证已提交 `1559266`。
- P1.1b：根 `config/`、`data/`、`experiments/` 与脚本/测试路径已收口，提交 `3d9d810`。
- P1.1c：应用数据库隔离、技术路线、迁移与事务纪律已提交 `22b58b0`。
- P0.3 是产品契约基线：UUID、UTC `Z` 时间、cursor 分页、`RunEvent.sequence` 对应 SSE `id`、最终 `DiagnosisResult` 结构化事实、Run 幂等和终态不可逆。

## P1.1 分解

| Step | 名称 | 状态 | 边界 |
|---|---|---|---|
| P1.1a | 环境基线恢复 | 已提交 `1559266` | 根 `.venv`、依赖与 mock 验证 |
| P1.1b | 配置/数据路径收口 | 已提交 `3d9d810` | 集中式路径、配置优先级与跨目录脚本/测试 |
| P1.1c | 应用后端地基设计 | 已提交 `22b58b0` | 持久化、迁移、事务、配置、安全与 P2 承接设计 |
| P1.1d | 最小应用层地基落地 | 已提交 | ORM/迁移依赖、独立 Settings、Engine/Session factory、Alembic 空业务骨架与测试 |

## 已落实的核心决策

### 1. 应用数据库与诊断数据源严格分离

应用数据库只保存后续 Session、Message、DiagnosisRun、RunEvent、DiagnosisResult、幂等记录和审计元数据；它不复用 P4 诊断数据源的连接、账号、连接池或工具权限。

- URL 优先级已实现为 `OPERMIND_APP_DATABASE_URL` > 被忽略的 `config/config.local.yaml` 中 `persistence.database_url` > 根 `data/opermind.sqlite3`。
- `api_key="mock"` 只决定外部诊断依赖的确定性 fallback；它不使 v1 持久化自动改为进程内内存。P2 的 v1 用例在存储不可用时必须安全失败，旧 `/diagnose`、`/diagnose/stream` 不受影响。
- SQLite 开发数据库属于运行时资产，`data/*.sqlite3` 已忽略；本 Step 产生的验证文件已删除，未纳入 Git。

### 2. 技术路线与配置

- 已锁定同步 `SQLAlchemy==2.0.51`、`alembic==1.18.5`、`psycopg[binary]==3.3.4`；现有 FastAPI/LangGraph 调用保持同步，不引入 async ORM 双栈。
- 本地开发和临时测试使用 SQLite；共享/生产应用元数据数据库使用 PostgreSQL。基础设施只接受 `sqlite` 与 `postgresql` URL，明确拒绝 MySQL 等未来诊断数据源 URL。
- `Base` 提供跨方言命名约束；P2 模型使用跨方言 UUID、JSON、UTC aware datetime 和显式命名约束，不使用 PostgreSQL native enum/JSONB 私有 DDL。

### 3. 已落实的目录与迁移边界

```text
backend/
├── alembic.ini
├── migrations/
│   ├── env.py              # 独立、跨目录可执行的迁移入口
│   ├── script.py.mako
│   ├── README.md
│   └── versions/.gitkeep   # P1.1d 不创建空业务 revision
└── src/infrastructure/persistence/
    └── database.py         # Base、Engine、Session factory
```

- 迁移唯一入口为 `python -m alembic -c backend/alembic.ini upgrade head`；应用启动不调用 `create_all()`、不自动建表、不自动升级。
- P1.1d 的 fresh-db `upgrade head` 只创建 Alembic 自身的 `alembic_version` 元数据；没有 P2 业务表。
- P2 的第一个非空 revision 才创建 Session、Message、DiagnosisRun、RunEvent、DiagnosisResult 和幂等记录的业务 schema。

### 4. 事务、并发与 SSE 持久化

- `PersistenceRuntime` 提供 Engine 与 `session_factory`，不在基础层创建事务、表或请求依赖。后续 HTTP 请求、后台 worker 与迁移命令各自使用独立 Session，Repository 不自行 commit/rollback。
- SQLite 每个连接显式启用 foreign keys；测试已覆盖 rollback 与外键约束。PostgreSQL 不连接真实服务，但已有 `psycopg` 方言构造与 DDL 编译覆盖。
- P2 将由 Application Service 管理短事务：Run 受理事务原子写入 Message、Run、幂等记录和 `run_queued`，提交后才调度；RunEvent 与终态结果提交后才可进入 SSE。

## P2 实施门

1. 先设计 P2 Step：领域模型、第一份非空 Alembic revision、Repository 端口、Application Service 事务和 `/api/v1` 端点对应关系。
2. 所有对外 ID、时间、cursor、错误体、SSE 语义严格以 P0.3 为准；旧接口保持兼容。
3. 至少验证 fresh DB migration、Run 状态机、同幂等键并发、sequence 单调递增、SSE 断线恢复、结构化 DiagnosisResult/Evidence 脱敏。
4. P2 不接入真实诊断数据源、前端或审批执行；这些留给 P3/P4/P5 的受控切片。

## 非目标

- P1.1d 不创建业务表、ORM mapper、业务 migration、Repository、Application Service、`/api/v1` 路由或持久化请求依赖。
- 不修改 Agent Core、阶段一 `/diagnose`、`/diagnose/stream`、`frontend/`、`report/`、`config/config.local.yaml`、运行时数据或实验产物。
- 不连接真实 PostgreSQL 或诊断数据源；真实连接仍须共同确认目标、最小权限、数据、契约、fallback 与验收场景。
