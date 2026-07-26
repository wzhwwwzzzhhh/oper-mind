# P2 HANDOFF — 会话诊断闭环

> 更新时间：2026-07-26
> 状态：P2.4 已完成实现、验证与独立审查，**等待用户授权暂存/提交**
> 分支：`feat/p2-session-diagnosis`　|　稳定基线：`ae2f978 feat: 完成P2.3会话诊断应用服务`
> 真实仓库：`D:\market-handsome\oper-mind`

## 已完成

- P2.1：关系、状态机、事务、Trace 映射与 API/SSE 切片设计，提交 `8f27717`。
- P2.2a：六张业务表、ORM、migration 和 schema 验证，提交 `11634b4`。
- P2.2b：Repository ports/SQLAlchemy 实现、cursor 查询与事务边界，提交 `5cf2c6b`。
- P2.3：Session/Run Application Service、幂等受理、短事务、状态迁移、事件、结果、Coordinator 安全适配，提交 `ae2f978`。
- P2.4：新增隔离 `src/api/v1/` 的 Pydantic 资源/错误/meta/cursor 契约，Session/Message/Run/RunEvent 路由，Run 受理后的 BackgroundTasks 执行，结构化 Result 读取，`X-Request-Id`/`X-Trace-Id`，以及只重放已提交 RunEvent 的 sequence SSE；执行异常和历史错误资源均收敛为固定公开错误。
- v1 写入只委派 Application Service；Repository 与诊断适配不 commit/rollback。v1 SSE 固定为 `event: run_event`，阶段一旧 SSE 保持 `progress/complete/error`。
- 已验证：P2.4 定向 5 passed；P2 应用/API/旧 API 联合 23 passed；完整后端 124 passed（1 条既有弃用警告）；pipeline direct/chain/parallel/debate smoke 通过；未生成 `data/opermind.sqlite3`。

## 外部/不可提交改动

以下外部改动继续隔离，禁止读取、修改、暂存或提交：

```text
docs/00-项目方案说明书.md
```

`backend/src/domain/__init__.py` 与 `backend/src/infrastructure/persistence/__init__.py` 可能显示为修改，但与 HEAD 内容 hash 相同且 `git diff` 为空；不纳入提交，不执行 reset。

## P2.4 精确提交边界

授权后只暂存以下 P2.4 文件，禁止 `git add .`：

```text
AGENTS.md
CLAUDE.md
backend/src/app.py
backend/src/api/v1/__init__.py
backend/src/api/v1/cursors.py
backend/src/api/v1/dependencies.py
backend/src/api/v1/errors.py
backend/src/api/v1/resources.py
backend/src/api/v1/routes.py
backend/src/api/v1/schemas.py
backend/src/api/v1/sse.py
backend/src/application/contracts.py
backend/src/application/services.py
backend/tests/test_p2_api_v1.py
docs/开发规范.md
docs/开发/_A-Plan-总览.md
docs/开发/_B-V1产品化开发计划.md
docs/开发/P2-会话诊断闭环/design.md
docs/开发/P2-会话诊断闭环/step4-api-v1与sse恢复.md
docs/开发/P2-会话诊断闭环/review.md
docs/开发/P2-会话诊断闭环/HANDOFF.md
```

不要暂存 `docs/00-项目方案说明书.md`、两个显示异常但无 diff 的初始化文件、`frontend/`、`report/`、`.venv/`、`config/config.local.yaml`、运行时 SQLite、数据或实验产物；不要修改阶段一 `/diagnose`、`/diagnose/stream`。

## 唯一下一步

用户授权并提交 P2.4 后，唯一下一步为 **P2.5：刷新恢复与闭环验收**。验证跨刷新读取顺序、失败 Run/安全错误、Run 幂等重试、终态 SSE 关闭、结构化 Result 安全边界、OpenAPI 与受控 Trace 链路；不得直接进入前端、真实数据源或 P4/P5 数据表。

## P2.5 必跑验证

```powershell
$env:PYTHONPATH = "$PWD\backend;$PWD"
$env:OPERMIND_API_KEY = "mock"
$env:OPERMIND_BASE_URL = "http://mock"
$env:OPERMIND_MODEL = "mock"
.\.venv\Scripts\python.exe -m pytest backend\tests\test_p2_api_v1.py -q
.\.venv\Scripts\python.exe -m pytest backend\tests -q
.\.venv\Scripts\python.exe backend\scripts\smoke_pipeline.py
```
