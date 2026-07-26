# P2.3 Step — Session/Run Application Service

> 日期：2026-07-26　|　状态：已完成，待用户授权提交　|　分支：`feat/p2-session-diagnosis`　|　实现基线：`5cf2c6b feat: 完成P2.2b Repository端口与SQLAlchemy实现`

## 目标与边界

在 P2.2b Repository 之上实现 Session/Run Application Service、诊断执行/结果组装端口和既有 Coordinator 的安全适配。严格不新增 `/api/v1`、SSE、前端、真实数据源或旧 API 变更。

## 实现结果

- 新增 `backend/src/application/`：命令、应用异常、执行/结果 ports 和 Service。Application Service 是唯一 `commit`/`rollback` 所有者；Repository 保持无事务控制。
- `SessionApplicationService` 支持创建与幂等逻辑归档；`RunApplicationService` 支持受理、同键重放、冲突、queued→running 条件认领、逐事件 sequence 预留、成功/失败终态写入。
- 受理在单短事务中写 input Message、queued Run、幂等记录和 `run_queued`。由于 mapper 为避免循环 DDL 未定义 Message/Run relationship，服务在同事务中显式 flush Message 后 flush Run，保证外键插入顺序。
- 执行器在 `run_started` 提交后的无事务区间运行；每个安全事件在独立短事务中持久化。重复执行只返回已 running/终态 Run，不重新调用执行器。
- 成功事务原子写 Result、助手 Message、Run succeeded 和 `run_succeeded`；失败事务只写安全错误、Run failed 和 `run_failed`。Result/助手消息写入异常会整体 rollback，再以安全失败终态收口。
- 新增 `backend/src/infrastructure/diagnosis/`：`CoordinatorDiagnosisExecutor` 丢弃 Trace detail/原始报告/任意执行 data；`ConservativeResultAssembler` 不从 Markdown 推断结构化事实，返回确定性低置信度安全结果。
- Repository 增加 Session 保存、Run 条件状态迁移和原子 sequence 预留；仍不调用 `commit`/`rollback`。

## 验证快照

- `backend/tests/test_p2_application_services.py`：覆盖 Session 归档、受理原子性、同键重放/冲突、已提交 running 后执行、成功/失败终态、安全事件、跨 Session input 防护、成功事务 rollback 和 UTC 事件时间。
- `backend/tests/test_p2_diagnosis_adapter.py`：覆盖 Coordinator Trace detail/Markdown 丢弃和阶段一 error 的安全映射。
- P2 定向回归（Application、adapter、Repository、schema、persistence）：32 passed。
- 完整后端测试：119 passed，保留 1 条既有 Starlette/httpx 弃用警告。
- `backend/scripts/smoke_pipeline.py`：direct、chain、parallel、debate 均通过。

## 已知边界

- 幂等唯一键竞争在 SQLite 下通过先查和唯一约束保护；P2.4/P7 的生产 PostgreSQL 并发门仍需覆盖竞争重读与锁/隔离级别。
- `/api/v1` 的 Pydantic 资源模型、HTTP 错误映射、不透明 cursor、SSE 重放和请求 ID 均留给 P2.4。
- 结构化 Result/Evidence 的正式资源级脱敏/校验仍须在 P2.4 API 边界完成；本 Step 的保守组装器只用于避免从 Markdown 伪造事实。

提交获授权后，唯一下一步为 **P2.4：`/api/v1` 与 SSE 恢复**。
