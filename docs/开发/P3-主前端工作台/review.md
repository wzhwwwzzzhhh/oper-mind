# P3 独立审查 — 主前端工作台

> 日期：2026-07-28　|　结论：✅ P3.2c.2 离线前置核对已完成；真实数据库只读验收按用户决策延后；当前进入 P3.3 Design
>
> 已提交基线：`12bed37 docs: 完成P3主前端工作台设计`、`4862752 feat: 初始化P3主前端工程与产品外壳`、`ec45ee2 docs: 完成P3.2接口与恢复读模型设计`、`75d6598 feat: 完成P3.2a v1 API客户端与MSW契约`、`3170e6a feat: 完成P3.2b会话工作台只读恢复`、`5491829 feat: 完成P3.2c1 mock FastAPI联调验收`

## 1. 审查范围

本次审查 P3.2c.2 的离线真实读模型前置核对及用户作出的延后决策：记录迁移、URL 优先级、启动装配、权限/数据/契约/回退门槛；不建立真实连接、查询、迁移、写入或读取本地密钥/运行时 SQLite 内容。

## 2. 审查依据

- 配置与装配：`backend/src/config.py:14-22,84-101`、`backend/src/api/v1/dependencies.py:25-42`、`backend/src/infrastructure/persistence/database.py:37-74`；
- 迁移：`backend/migrations/env.py:27-69`、`backend/migrations/versions/20260726_01_p2_session_diagnosis.py`；
- 离线验证：`alembic heads` 为 `20260726_01_p2`，PostgreSQL `alembic upgrade head --sql` 编译通过；
- 决策记录：`step2c2-真实读模型前置条件核对.md`、`HANDOFF.md`、A/B Plan 与规则镜像。

## 3. 独立审查结果

| 检查项 | 结论 | 审查结果 |
|---|---|---|
| 连接隔离 | 通过 | 未读取本地配置、未读取环境变量值、未连接真实 DB/数据源；只检查 URL 环境变量是否存在 |
| URL 与装配 | 通过 | 优先级为环境变量 > 本地配置 > 根 SQLite；v1 服务装配 persistence runtime，不自动迁移或建表 |
| 迁移可用性 | 通过（离线） | head 为 `20260726_01_p2`；PostgreSQL `psycopg` 方言离线 SQL 编译通过；不等价于目标实例已迁移 |
| 默认回退风险 | 通过记录 | 根 SQLite 为 0 字节且未读取，不能假定为已迁移/有数据；真实失败不得改用它或 mock 伪造成功 |
| 真实接入门槛 | 通过固化 | C1–C8 保留为后期强制条件：目标、受控 URL、只读权限、revision、安全数据、实例、契约与回退 |
| 用户决策 | 通过 | 用户选择暂不接入真实数据库，待前后端大致开发完成后再启动真实只读验收；该决策解除当前 P3.3 的阻塞，不降低 C1–C8 要求 |
| 范围与资产 | 通过 | 未改 `backend/`、`report/`、`data/`、`frontend/mockup.html`；未创建或访问 SQLite，未提前进入 P3.3/P3.4/P4/P5/P6 |
| 文档与下一步 | 通过 | A/B Plan、P3 文档和规则镜像已同步为 P3.2 完成 mock/离线验证，唯一下一步为 P3.3 Design |

## 4. 结论与唯一下一步

P3.2c.2 以离线前置核对完成收口。真实数据库只读验收明确延后，届时必须重新执行 C1–C8 核对；当前不把它作为前端功能开发的阻塞。

**当前唯一下一步：P3.3 Design：Run 受理、幂等与 SSE 恢复。**在 P3.3 Design 中仍不连接真实 DB 或数据源、不运行在线 Alembic，也不提前实现完整结果卡、Trace 跳转或 P4/P5/P6。
