# P1 独立审查 — 应用后端地基

> 更新时间：2026-07-26　|　结论：P1.1a、P1.1b、P1.1c 已提交；P1.1d 已提交

## 已提交基线

- `1559266 chore: 恢复P1环境基线`：根 `.venv`、锁定依赖与 mock 验证。
- `3d9d810 refactor: 收口P1配置与数据路径`：集中式根路径、配置优先级、跨目录脚本与测试。
- `22b58b0 docs: 完成P1应用后端地基设计`：应用 DB 隔离、迁移与事务纪律。

## P1.1d 审查范围

审查锁定依赖、应用数据库 URL 优先级、SQLite/PostgreSQL 基础设施、Alembic 跨目录入口、迁移不建业务表、测试隔离、旧 API 回归和提交资产边界。

| 检查项 | 结论 | 依据 |
|---|---|---|
| 依赖锁定 | 通过 | `SQLAlchemy==2.0.51`、`alembic==1.18.5`、`psycopg[binary]==3.3.4` 已安装；`pip check` 通过 |
| 应用 DB 隔离 | 通过 | 独立 `OPERMIND_APP_DATABASE_URL` / `persistence.database_url`；基础设施拒绝 MySQL 诊断数据源 URL |
| 配置优先级与 fallback | 通过 | 环境变量覆盖、本地配置、根 SQLite 默认值及空 YAML 段回退均有测试 |
| SQLite 基础语义 | 通过 | 每连接外键启用、rollback 与外键约束有真实测试 |
| PostgreSQL 可移植性 | 通过 | `psycopg` 方言可构造，跨方言 DDL 编译测试通过；未伪称连接真实 PostgreSQL |
| Alembic 边界 | 通过 | 临时目录 fresh-db `upgrade head` 成功；仅创建 `alembic_version`，无业务 revision/业务表；启动未接入迁移 |
| 范围控制 | 通过 | 未创建 ORM mapper、Session/Run 表、Repository、Application Service、请求依赖或 `/api/v1` 路由 |
| 阶段一兼容 | 通过 | 完整后端测试 `98 passed`、API 测试 `11 passed`、mock `/health` 与跨目录 pipeline 均通过 |
| 运行时资产 | 通过 | `data/*.sqlite3` 已忽略；验证产生的根数据库已删除且不在 Git 状态 |

## 已知限制与 P2 风险

- PostgreSQL 尚未连接真实实例；P2 前至少保留当前方言编译门，具备可用 CI/容器条件时增加真实 PostgreSQL migration 集成验证。
- Alembic 的 `alembic_version` 是迁移自身元数据，不是业务 schema；第一个业务 revision 必须在 P2 随资源模型一起审查。
- 目前仅有 Session factory，不存在请求级依赖或事务封装；P2 必须由 Application Service 建立短事务，禁止 Repository 自行 commit。
- 目前没有 v1 端点，因此 `PERSISTENCE_UNAVAILABLE` 仍是 P2 的安全失败契约，不得据此修改旧 API。

## 结论

P1.1d 已达到最小应用层地基成功标准并完成独立提交。提交信息：`feat: 建立P1应用持久化地基`。提交后唯一下一步为 **P2：会话诊断闭环（第一个纵向切片）**。
