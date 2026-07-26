# P2.2b Step — Repository 端口与 SQLAlchemy 实现

> 日期：2026-07-26　|　状态：已完成，待用户授权提交　|　分支：`feat/p2-session-diagnosis`　|　实现基线：`11634b4 feat: 完成P2.2a领域模型与首个业务迁移`

## 目标与边界

提供 P2.3 Application Service 可注入的 Repository ports、Pydantic 数据对象和 SQLAlchemy 实现，验证读取/分页/事务边界。严格不实现 Application Service、状态更新、幂等受理、Agent 适配、`/api/v1`、SSE、前端或真实数据源；旧 `/diagnose` 和 `/diagnose/stream` 不变。

## 实现结果

- `backend/src/domain/records.py`：六类持久化数据对象、四类已解码 cursor 和泛型页片段。对象采用 `extra="forbid"`，要求 UTC aware 时间；Result/Event/Run 的受控值和数值范围在进入 ORM 前校验。
- `backend/src/domain/repositories.py`：Session、Message、DiagnosisRun、RunEvent、DiagnosisResult、RunIdempotencyKey 六个 Protocol ports。端口不依赖 SQLAlchemy、不返回 ORM mapper、不处理 HTTP cursor 字符串。
- `backend/src/infrastructure/persistence/repositories.py`：六个 SQLAlchemy 实现。全部通过构造函数接收调用方的同步 `Session`，仅使用 `add`、`get`、`select`/固定排序查询；没有 `commit()`、`rollback()` 或 schema 创建。
- 读取分页：Session/Run 倒序复合 cursor，Message 升序复合 cursor，RunEvent sequence 升序；每页以 `limit + 1` 推导 `has_more` 和下一 cursor，Repository 拒绝 `limit < 1`。
- SQLite 读回的无时区时间由 mapper 转换层归一化为 UTC aware；Pydantic 数据对象和 ports 不泄露 ORM。

## 验证快照

- `backend/tests/test_p2_repositories.py`：验证六类对象 staged add/read、四种固定排序 cursor、`has_more`、调用方事务边界、UTC/受控值/分页参数校验。
- Repository + schema + 持久化定向回归：23 passed。
- 完整后端测试：109 passed，保留 1 条既有 Starlette/httpx 弃用警告。
- `backend/scripts/smoke_pipeline.py`：direct、chain、parallel 和 debate 分支均通过。
- `git diff --check` 通过；未修改 `frontend/`、`report/`、旧 API、`/api/v1` 或运行时 SQLite。

## 后续责任

P2.3 必须在 Application Service 中实现事务编排：Session 标题/归档、Run 受理与幂等、条件状态迁移、`next_event_sequence` 原子递增、Result/助手 Message 写入，以及 `messages.run_id` 同 Session 校验。Repository 仍不得自行提交或回滚。

提交获授权后，唯一下一步为 **P2.3：Session/Run Application Service**。
