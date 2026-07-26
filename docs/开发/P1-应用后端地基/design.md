# P1 设计 — 应用后端地基

> 日期：2026-07-26　|　状态：P1.1a、P1.1b 已提交；P1.1c 已完成并提交　|　稳定基线：`3d9d810 refactor: 收口P1配置与数据路径`

## 目标

P1 为 V1 产品建立可迁移、可审计、可恢复的应用持久化基础。P1.1c 只做设计决策，不引入 SQLAlchemy、Alembic、数据库驱动、表、迁移、Repository、Application Service 或 `/api/v1` 路由；P1.1d 才依此设计落地最小基础设施。

## 已完成基线

- P1.1a：根 `.venv`、锁定依赖与 mock 验证已提交 `1559266`。
- P1.1b：根 `config/`、`data/`、`experiments/` 与脚本/测试路径已收口，提交 `3d9d810`。
- P0.3 是产品契约基线：UUID、UTC `Z` 时间、cursor 分页、`RunEvent.sequence` 对应 SSE `id`、最终 `DiagnosisResult` 结构化事实、Run 幂等和终态不可逆。

## P1.1 分解

| Step | 名称 | 状态 | 边界 |
|---|---|---|---|
| P1.1a | 环境基线恢复 | 已提交 `1559266` | 根 `.venv`、依赖与 mock 验证 |
| P1.1b | 配置/数据路径收口 | 已提交 `3d9d810` | 集中式路径、配置优先级与跨目录脚本/测试 |
| P1.1c | 应用后端地基设计 | Review 通过，待本次提交 | 持久化、迁移、事务、配置、安全与 P2 承接设计；不写实现 |
| P1.1d | 最小应用层地基落地 | 下一步 | 仅落地依赖、Settings、DB Session、Alembic 环境与测试底座；不实现 P2 资源 API |

## 核心决策

### 1. 应用数据库与诊断数据源严格分离

应用数据库只保存 Session、Message、DiagnosisRun、RunEvent、DiagnosisResult、幂等记录、后续审批/审计元数据；它不是 DB Agent 未来要诊断的业务数据库，也不会复用其连接、账号或工具权限。

- 应用数据库配置名预留为 `OPERMIND_APP_DATABASE_URL` / `persistence.database_url`，避免与 P4 的 `DataSource` 和诊断工具连接混淆。
- 真实诊断数据源仍遵守只读、参数化查询、连接超时与审批规则；其接入在 P4 共同确认后进行。
- `/api/v1` 一旦依赖持久化，不允许因为应用数据库不可用而静默降级到进程内内存；应返回安全的 `503 PERSISTENCE_UNAVAILABLE`，旧 `/diagnose`、`/diagnose/stream` 不受影响。

### 2. 技术路线与配置优先级

- P1.1d 引入同步 SQLAlchemy 2.x ORM、Alembic 与 PostgreSQL `psycopg` 驱动；现有 FastAPI 与 LangGraph 路径为同步调用，避免在基础层同时引入 async ORM 双栈。
- 本地开发使用 SQLite；生产/共享环境使用 PostgreSQL。模型只使用 SQLAlchemy 的跨方言类型与显式命名约束，不使用 PostgreSQL 专属 `JSONB`、原生 enum 或 SQLite 私有 DDL。
- 数据库 URL 优先级：`OPERMIND_APP_DATABASE_URL` 环境变量 > 被忽略的 `config/config.local.yaml` 中 `persistence.database_url` > P1.1d 定义的本地 SQLite 开发默认值。模板不得包含真实连接串或凭据。
- `api_key="mock"` 继续仅表示外部诊断依赖可确定性 mock；它不允许 v1 持久化改为无审计的内存实现。P1.1d 的测试通过显式注入临时 SQLite URL 隔离。

### 3. 目录与迁移边界

P1.1d 计划新增但本 Step 不创建：

```text
backend/
├── alembic.ini
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
└── src/
    ├── domain/           # 领域实体、状态机与端口，不依赖 FastAPI/SQLAlchemy
    ├── application/      # 用例、事务边界、异常映射
    └── infrastructure/
        └── persistence/  # Engine、Session factory、ORM mapper、Repository 实现
```

- 迁移唯一入口为 `python -m alembic -c backend/alembic.ini upgrade head`；应用启动不得调用 `create_all()`、自动建表或自动升级。
- P1.1d 创建 Alembic 环境和迁移测试底座，但不制造空的业务 schema revision；P2 的第一个非空 revision 才创建 Session/Run 核心表。
- CI/部署必须对新建数据库执行 `upgrade head`；回滚策略在每个 revision 审查，破坏性变更默认 expand/contract 两阶段，不以自动 downgrade 代替数据恢复方案。

### 4. 事务、并发与 SSE 持久化

- SQLAlchemy `Session` 是单事务、不可跨线程/协程共享的可变对象。HTTP 请求、后台诊断 worker 和迁移命令各自获取并关闭自己的 Session；Repository 不创建、不提交、不回滚事务。
- Application Service 是事务边界：创建 Session、创建 Run、状态迁移、写最终结果和写幂等记录在明确的短事务中完成；长时间 Agent 执行绝不包在数据库事务内。
- 创建 Run 的受理事务必须原子写入输入 Message、DiagnosisRun、Idempotency 记录与 `run_queued` RunEvent，提交成功后才返回 `202` 并调度编排。
- 运行事件采用独立短事务追加。每个 Run 持有单调递增的 `next_event_sequence`，追加时与 Run 状态变更一起提交；`(run_id, sequence)` 唯一。SSE 只读取已提交事件，`sequence` 十进制字符串一一映射 `id`。
- 成功事务原子写入 `DiagnosisResult`、其已校验的结构化 Evidence、Run 终态和 `run_succeeded`；失败同理写安全错误与 `run_failed`。终态不可回退，提交前不得向客户端发送终态事件。

### 5. 模型、类型与可移植性

P2 的第一个资源迁移至少覆盖：`sessions`、`messages`、`diagnosis_runs`、`run_events`、`diagnosis_results`、`run_idempotency_keys`；Evidence 作为受 Pydantic 校验、版本化的结果子结构持久化，后续若需独立检索再以无损迁移拆表。

- 主键、`trace_id`、幂等键使用 Python 生成 UUID v4，数据库使用 SQLAlchemy 跨方言 UUID 映射；对外统一序列化为 RFC 4122 字符串。
- 时间由应用层写入 UTC aware datetime，ORM 使用 `DateTime(timezone=True)`；API 序列化统一输出 `Z`，不依赖 SQLite/PostgreSQL 的默认时间文本。
- 状态值使用 `String` 加显式命名 `CHECK` 约束，避免 PostgreSQL native enum 的升级耦合；外键、唯一键和索引均命名，便于 Alembic 跨方言管理。
- `RunEvent.data` 与结果嵌套结构使用标准 JSON 类型，写入前由 Pydantic 校验、读取时再次验证并带 `schema_version`；禁止把未清洗的原始日志、SQL、连接信息或 Trace 任意写入 JSON。
- cursor 由服务端生成不透明、带版本和签名的排序锚点；P2 使用固定端点排序与 `id` 打破并列，客户端不得构造 cursor。签名密钥必须来自环境变量或被忽略的本地配置。

### 6. Repository、Application Service 与异常边界

- 不做通用 CRUD Repository。每个聚合拥有面向用例的端口，例如 `SessionRepository`、`RunRepository`、`RunEventRepository` 与 `IdempotencyRepository`；接口属于 domain/application，SQLAlchemy 实现在 infrastructure。
- Application Service 将 Pydantic 请求转换为领域命令，控制事务、调用编排端口、映射 `not_found` / `conflict` / `persistence_unavailable` 等应用异常；FastAPI 只负责 HTTP 协议与依赖注入。
- 约束冲突不能被裸异常吞掉：幂等键同语义返回原 Run，不同语义映射 `409 IDEMPOTENCY_KEY_REUSED`；资源不存在映射 `404`；存储不可用映射安全 `503`；内部细节只进入服务端日志并以 request/trace ID 关联。

## P1.1d 验收门

1. 新依赖固定版本并通过 `pip check`；不引入业务表或 `/api/v1` 路由。
2. Settings 只从环境变量/忽略本地配置取得应用数据库 URL，且固定解析根本地 SQLite 路径。
3. Alembic 环境可对空数据库执行 `upgrade head`，应用启动不自动建表/迁移。
4. Session 生命周期、事务 rollback、SQLite 外键启用、迁移 fresh-db 测试与 PostgreSQL 方言编译覆盖真实通过。
5. 保持 mock `/health`、旧 API 测试和 pipeline 回归；持久化不可用时的 v1 行为有明确安全失败，而非内存降级。

## 非目标

- 不在 P1.1c 创建 ORM mapper、数据库表、迁移 revision、Repository、Application Service、配置字段、依赖或 FastAPI 路由。
- 不修改 Agent Core、阶段一 `/diagnose`、`/diagnose/stream`、`frontend/`、`report/`、运行时数据或实验产物。
- 不接入真实 PostgreSQL、诊断数据源或前后端联调；这些都须在后续共同确认连接目标、最小权限、可用数据、契约、fallback 与验收场景后执行。
