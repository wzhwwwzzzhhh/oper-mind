# P1.1d 持久化迁移说明

此目录只承载应用元数据数据库的 Alembic 迁移，不承载 P4 诊断数据源或 Agent 工具连接。

- 迁移命令：`python -m alembic -c backend/alembic.ini upgrade head`
- 数据库 URL：`OPERMIND_APP_DATABASE_URL` > 本地 `persistence.database_url` > 根 `data/opermind.sqlite3`
- 服务启动不执行 `create_all()` 或自动迁移。
- P1.1d 没有业务 revision；P2 的第一个 revision 才创建 Session、Message、DiagnosisRun、RunEvent、DiagnosisResult 等表。