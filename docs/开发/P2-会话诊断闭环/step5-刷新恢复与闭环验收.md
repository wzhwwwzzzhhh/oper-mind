# P2 Step5 — 刷新恢复与闭环验收

> 日期：2026-07-26　|　状态：已完成验证与独立审查，待用户授权提交　|　关联 commit：待提交

## Design

- 页面刷新后的产品恢复必须只读取持久化资源：先读取 Session，再按固定 cursor 读取该 Session 的 Run、消息；针对选定 Run 读取 Result、RunEvent，并仅在非终态时由客户端自行重连 SSE。读取端点绝不重新调用 executor、创建 Run 或变更状态。
- Repository 已有 `DiagnosisRunRepository.list_by_session()`，但 v1 未公开此读模型；P2.5 新增 `GET /api/v1/sessions/{session_id}/runs`，固定排序为 `created_at desc, id desc`，复用不透明 cursor、ResponseMeta、Run 资源和既有安全 Result 映射。
- 将 P0.3 API 契约补齐该恢复必需的读取端点及 `DiagnosisRunListResponse`。这不是新领域能力或表，而是公开已有持久化读模型。
- 验收以独立 Alembic 临时 SQLite 生成数据，并以新的 TestClient 模拟刷新后的新请求上下文：成功 Run 与失败 Run 都必须能恢复；终态 SSE 在已收到最终 sequence 时立即关闭且不再输出临时事件；`trace_id` 必须在 Run、Event、SSE meta 一致。
- OpenAPI 是 Pydantic 契约的可执行投影：验证 v1 路径、响应模型和旧接口路径同时存在，避免新路由或异常分流破坏阶段一兼容接口。

## Step

1. 同步 P0.3 契约、v1 Pydantic 列表模型与 Session→Run 读取路由。
2. 新建独立 P2.5 闭环测试，模拟跨请求/刷新恢复成功、失败、消息、Result、Event、终态 SSE、trace 和 cursor。
3. 进行 OpenAPI、旧 API、迁移临时库与无运行时资产验收。
4. 独立审查恢复只读性、状态机/事务不变量、SSE 终态语义和范围控制，回填文档与唯一下一步。

## 非目标

- 不在 GET/SSE 路由中隐式恢复或重启 queued/running Run；进程崩溃后的 worker 接管、超时和重试策略仍属 P2.5 记录风险及 P7 的生产加固，不伪造持久化任务队列。
- 不修改旧 `/diagnose`、`/diagnose/stream`，不改 `frontend/`、`report/`，不接入真实 PostgreSQL、真实数据源、P4/P5 表或接口。
- 不以 `Base.metadata.create_all()` 替代 Alembic；测试只使用临时 SQLite 数据库。

## Code

- `backend/src/api/v1/routes.py` 新增 `GET /api/v1/sessions/{session_id}/runs`：先以既有 Session 服务确认资源存在，再以独立短生命周期 SQLAlchemy Session 调用 `SqlAlchemyDiagnosisRunRepository.list_by_session()` 和 Result Repository。固定排序为 `created_at desc, id desc`，复用不透明 cursor、UTC 序列化、`ResponseMeta` 与 Result 安全资源映射；路由不调用 executor、不排队、不提交或回滚。
- `backend/src/api/v1/schemas.py` 新增 `DiagnosisRunListResponse`。P0.3 契约同步同名 Pydantic 与 TypeScript 形状和最小端点表。
- `backend/tests/test_p2_recovery_closure.py` 只通过 Alembic 创建临时 SQLite。两个新 TestClient 模拟刷新后的新请求上下文，覆盖成功 Run 的分页/消息/Result/Event/SSE/trace/OpenAPI 以及失败 Run 的安全错误、终态事件与 SSE 脱敏。

## Test

```text
P2 定向（schema/application/API/P2.5）：20 passed
完整 backend/tests：126 passed
backend/scripts/smoke_pipeline.py：direct / chain / parallel / debate 通过
```

全量测试仅报告既有 Starlette TestClient 弃用警告。验证期间未使用默认应用数据库，未产生 `data/opermind.sqlite3`。

## Review

- 恢复列表以 `session_id` 过滤且先验证 Session，cursor 使用领域 `DiagnosisRunCursor`，不会把其他 Session 的 Run 混入页面；列表只读，不触发 BackgroundTask 或 executor。
- 成功与失败资源均只恢复已提交数据。终态 SSE 在客户端已确认最终 sequence 时返回 `200` 空流并关闭；trace_id 在 Run、Event 和 SSE envelope 中一致。
- 失败测试故意提供连接串、令牌和 SQL，断言它们不会进入 Run、Event 或 SSE；公开错误固定为 `DIAGNOSIS_FAILED` 与通用中文文案。
- 不改旧 `/diagnose`、`/diagnose/stream`，OpenAPI 回归同时验证新旧路径；不改 `frontend/`、`report/`，不接入真实 PostgreSQL/数据源。

## Known risks

- `BackgroundTasks` 没有崩溃恢复、重试或多进程 worker 语义；P7 需要补充持久化任务接管方案。
- SSE 的短连接轮询适合当前持久化重放，不等价于高吞吐推送；P7 需要慢客户端、取消和资源上限验证。
- SQLite 验收不代替 PostgreSQL 并发幂等/sequence 验证；本 Step 按范围不连接真实 PostgreSQL。

## 下一步

待用户授权提交 P2.5 后，唯一下一步为 **P3：主前端工作台** 的 Design。