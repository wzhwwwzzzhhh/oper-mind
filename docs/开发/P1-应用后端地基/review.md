# P1 独立审查 — 应用后端地基

> 更新时间：2026-07-26　|　结论：P1.1a、P1.1b 已提交；P1.1c 已提交

## P1.1a / P1.1b 基线

- `1559266 chore: 恢复P1环境基线`：根 `.venv`、锁定依赖与 mock 验证。
- `3d9d810 refactor: 收口P1配置与数据路径`：集中式根路径、配置优先级、跨目录脚本与测试。

## P1.1c 审查范围

审查持久化技术路线、应用数据库与诊断数据源隔离、SQLite/PostgreSQL 可移植性、迁移纪律、Session/事务边界、Run 事件提交顺序、P0.3 契约承接和 mock/失败语义。未审查不存在的 ORM 或 API 实现，因为本 Step 没有新增实现。

| 检查项 | 结论 | 设计结论 |
|---|---|---|
| 技术栈与同步边界 | 通过 | P1.1d 使用同步 SQLAlchemy 2.x、Alembic、`psycopg`；与现有同步 FastAPI/LangGraph 路径一致，不引入 async 双栈 |
| 应用 DB 隔离 | 通过 | 应用元数据数据库与 P4 诊断数据源分离，配置名使用 `OPERMIND_APP_DATABASE_URL` / `persistence.database_url`，不可复用诊断账号或连接 |
| SQLite/PostgreSQL 兼容 | 通过 | SQLite 用于本地/测试，PostgreSQL 用于共享/生产；跨方言 UUID、JSON、`DateTime(timezone=True)`、显式命名约束，避免 native enum/JSONB 私有 DDL |
| 迁移纪律 | 通过 | 仅 Alembic 显式迁移；启动不执行 `create_all()` 或自动升级；P1.1d 建环境与测试底座，P2 首个业务 revision 才建表 |
| 事务与事件 | 通过 | Service 持有短事务，Repository 不提交；长 Agent 执行不包事务；Run/Event/终态只在提交后进入 SSE，`sequence` 与 SSE `id` 一一对应 |
| 幂等与状态机 | 通过 | 受理事务原子保存 Message、Run、幂等记录和 `run_queued`；同键不同语义为 409，终态不可逆，失败只写安全错误 |
| mock 与存储失败 | 通过 | `api_key="mock"` 仅是外部依赖 mock，不能将 v1 持久化静默降级为内存；存储不可用必须安全失败，不影响旧接口 |
| P0.3 契约承接 | 通过 | UUID、UTC `Z`、cursor、结果结构、Evidence 脱敏和 SSE 恢复要求均被固定为 P1.1d/P2 实施门 |
| 范围控制 | 通过 | 未修改依赖、配置、数据库、迁移、Repository、Application Service、API、Agent Core、`frontend/`、`report/` 或运行时资产 |

## 已知风险与后续门槛

- SQLite 对类型、外键和并发的行为与 PostgreSQL 不完全相同。P1.1d 必须启用 SQLite foreign keys、使用 fresh-db migration 测试，并加入 PostgreSQL 方言编译或容器化集成门；不能以 SQLite 测试代替 PostgreSQL 验收。
- Event sequence 的并发追加需要由 P2 的单 Run worker/锁策略和数据库唯一约束共同保证；P1.1d 只提供基础设施，不提前伪造并发实现。
- cursor 签名密钥、应用数据库 URL 等敏感配置在 P1.1d 才增加，必须只来自环境变量或被忽略的本地配置，且不写入日志、响应或提交。
- 当前阶段一 `/diagnose` 与 `/diagnose/stream` 的即时语义保持不变；P2 只能新增 `/api/v1`，不可把新持久化约束倒灌到旧接口。

## 结论

P1.1c 设计达到可实施标准并已完成独立提交。提交信息：`docs: 完成P1应用后端地基设计`。提交后唯一下一步为 **P1.1d：最小应用层地基落地**。
