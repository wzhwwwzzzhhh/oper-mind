# P2.2a Step — 领域模型、首个业务迁移与 schema 验证

> 日期：2026-07-26　|　状态：已完成，待用户授权提交　|　分支：`feat/p2-session-diagnosis`　|　设计基线：`8f27717 docs: 完成P2会话诊断闭环设计`

## 目标与严格边界

实现 P2.1 已固定的领域状态/事件常量、六张核心业务表 ORM mapper、首份非空 Alembic revision 与可复现 schema 验证。此 Step 不实现 Repository、Application Service、Coordinator/Agent 适配、`/api/v1`、SSE 或前端；不修改旧 `/diagnose`、`/diagnose/stream`，不触碰 `frontend/` 或 `report/`，不连接真实 PostgreSQL 或真实数据源。

## 实现结果

- 新增 `backend/src/domain/diagnosis.py`：`SessionStatus`、`MessageRole`、`RunStatus`、`RunEventType` 与 `RUN_TERMINAL_STATUSES`。枚举采用兼容 Python 3.10+ 的 `str, Enum`。
- 新增 `backend/src/infrastructure/persistence/models.py`：`SessionRecord`、`MessageRecord`、`DiagnosisRunRecord`、`RunEventRecord`、`DiagnosisResultRecord`、`RunIdempotencyKeyRecord`；默认 UUID v4 与 UTC aware 时间。
- 新增 `backend/migrations/versions/20260726_01_p2_session_diagnosis.py`：revision `20260726_01_p2`，只创建 `sessions`、`messages`、`diagnosis_runs`、`run_events`、`diagnosis_results`、`run_idempotency_keys`。
- 更新 `backend/migrations/env.py` 与 `backend/src/infrastructure/persistence/__init__.py`，确保 Alembic 加载 ORM metadata。
- `messages.run_id` 保持可空、带索引、无物理外键。该选择避免 `diagnosis_runs.input_message_id -> messages.id` 与助手消息关联之间的循环 DDL；P2.3 Service 必须校验 Run 和 Message 同属一个 Session。
- 新增 `backend/tests/test_p2_schema.py`，并将 P1 遗留 fresh-db 断言更新为首个业务 migration 的实际预期。

## 验证快照

- 根 `.venv`：`python -m compileall -q backend\src backend\migrations backend\tests` 通过。
- 在 `PYTHONPATH=$PWD\backend;$PWD` 下导入 mapper：`Base.metadata.tables` 正好为六张业务表。
- 独立系统临时 SQLite：`upgrade head` 后仅有 `alembic_version` 与六张业务表；检查外键、唯一键、检查约束、索引；`downgrade base` 后仅保留 `alembic_version`，随后可再次 `upgrade head`。
- `backend/tests/test_p2_schema.py` 与 `backend/tests/test_persistence_infrastructure.py`：17 passed。
- 完整后端测试：104 passed，保留 1 条既有 Starlette/httpx 弃用警告。
- PostgreSQL：不建立真实连接；ORM metadata 和 `alembic upgrade head --sql` 均以 `postgresql+psycopg` 方言离线编译。

## 审查结论与下一步

ORM 与 migration 字段、约束、命名一致；未产生循环外键或额外业务表；不存在 Repository、Service、HTTP/SSE、旧 API、`frontend/`、`report/` 越界改动，也未生成/跟踪运行时 SQLite 资产。唯一残留的设计风险是 `messages.run_id` 的同 Session 一致性不能由当前物理 schema 强制，已明确下放为 P2.3 Application Service 的必做校验。

提交获授权后，唯一下一步为 **P2.2b：Repository 端口与 SQLAlchemy 实现**。
