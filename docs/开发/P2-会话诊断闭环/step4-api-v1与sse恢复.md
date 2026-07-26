# P2 Step4 — /api/v1 与 SSE 恢复

> 日期：2026-07-26　|　状态：✅ 通过，待用户授权提交　|　关联 commit：待提交

## Design

- 新增 `src/api/v1/`，将 Pydantic 资源模型、请求/响应元数据、cursor、错误体、依赖、路由和 SSE 序列化与阶段一 `src/api/` 隔离；不得改变旧 `/diagnose`、`/diagnose/stream`、`/health`、`/memory/*` 的响应语义。
- v1 的写入仅调用 `SessionApplicationService` / `RunApplicationService`；Repository 仍只负责读取、暂存和条件更新，不在 API 层控制 commit/rollback。
- Run 创建在受理事务成功后返回 `202`，再以 FastAPI BackgroundTasks 调用执行用例；HTTP 层不传递 query 给执行用例，也不在 Executor 内推送 SSE。
- SSE 以已提交 `RunEvent.sequence` 为唯一 event id。连接先校验 Run 和 `Last-Event-ID` / `after_sequence`，再轮询读取已提交事件；发送终态事件后关闭。不会生成临时 complete/error 帧或读取未提交事件。
- 对外 datetime 用统一字段序列化为 UTC `Z`；请求 ID 由 v1 中间件生成或校验后回显；ApplicationError、验证错误和协议错误均转为 P0.3 安全错误体。
- 读取资源 JSON 时通过 Pydantic 资源模型校验；数据不符合安全资源结构时不返回原始 JSON，而是以安全内部错误收口。

## Step

1. 建立 v1 Pydantic 契约、cursor 和 SSE 帧工具。
2. 装配持久化 Runtime、Coordinator 执行适配及 Application Service，并提供测试可替换依赖。
3. 实现 Session、Message、Run、RunEvent 查询路由，Session 更新/归档和 Run 受理后台执行。
4. 实现持久化事件 SSE 重放、断线 cursor 校验、请求/trace 元数据与安全错误映射。
5. 用独立 Alembic 临时 SQLite 覆盖 API/SSE 与旧 API 回归，再做独立 Review 和文档回填。

## 非目标

- 不修改阶段一旧 API、`frontend/`、`report/`，不接入真实 PostgreSQL 或真实诊断数据源。
- 不新增 Environment、DataSource、Alert、Incident、Approval 等后续表和 API。
- 不通过 `Base.metadata.create_all()` 建库；测试只使用临时 SQLite 的 Alembic migration。
- Session 创建的可选幂等键没有相应持久化表，不伪造“同键复用”语义；P2.4 仅落实 schema 已支持的 Run 幂等。

## Code

- `backend/src/api/v1/schemas.py`、`resources.py`：P0.3 资源、响应 meta、错误体与结构化 Result 安全校验；统一 UTC `Z` 输出。
- `backend/src/api/v1/dependencies.py`、`routes.py`：持久化 Runtime/Service 装配及 Session、Message、Run、Event 路由；写入委派 Application Service，读取使用 Repository。
- `backend/src/api/v1/sse.py`：已提交 RunEvent 的 sequence SSE 帧、终态关闭与断线续传。
- `backend/src/app.py`：只为 `/api/v1` 增加 request ID 中间件、安全错误包络和路由装配；阶段一接口代码与契约保持不变。
- `backend/src/application/contracts.py`、`services.py`：补充受控 `UpdateSessionCommand` 与幂等 Session 更新；仍由 Application Service 独占事务。

## Test

- `backend/tests/test_p2_api_v1.py` 使用独立 Alembic 临时 SQLite：资源/UTC `Z`/cursor/request ID、Session 更新归档、Run 幂等与后台执行、Result/Message、RunEvent/SSE 重放、断线 cursor 和错误隔离。
- `python -m pytest backend/tests/test_p2_api_v1.py -q`：5 passed。
- `python -m pytest backend/tests/test_p2_application_services.py backend/tests/test_p2_api_v1.py backend/tests/test_api.py -q`：23 passed。
- `python -m pytest backend/tests -q`：124 passed，只有既有 TestClient 弃用警告。
- `python backend/scripts/smoke_pipeline.py`：direct / chain / parallel / debate 通过；未生成 `data/opermind.sqlite3`。

## Review

- 独立审查先发现执行错误可能透传、认领异常可能遗留 queued Run、测试导入默认数据库 URL 未显式固定；均已修复并复审通过。Repository 与诊断适配没有 commit/rollback；唯一事务所有者仍为 Application Service。
- `messages.run_id` 仍不设物理反向 FK，P2.3 的同 Session 校验责任未改变；P2.4 只读取公开资源。
- v1 SSE 不读取 executor 即时输出，只读取提交后的 RunEvent；错误事件只含固定公开 code；对抗性测试验证连接串、SQL 与 token 不会出现在 HTTP/SSE。旧 SSE 保持 `progress/complete/error`，两者已在规范中明确隔离。
- 未改动 `frontend/`、`report/`、Agent Core、阶段一旧 API、真实数据源或运行时数据库资产。
- 已知限制：SQLite 不能替代 PostgreSQL 并发竞争；P2.5 需要做更完整的刷新/失败恢复验收和 OpenAPI/长连接审查。
