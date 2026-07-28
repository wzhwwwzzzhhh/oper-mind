# P3 HANDOFF — 主前端工作台

> 日期：2026-07-28　|　状态：✅ P3.4b 已完成代码、自动验证与独立 Review；等待 P3.4c 代码授权
>
> 工作分支：`feat/p3-workbench`　|　提交基线：`bc1b4aa feat: 完成P3.4a结构化结果读取与摘要面板`

## 已完成

- P3.1 工程与产品外壳：`4862752`；
- P3.2 Design：`ec45ee2`，P3.2a/b/c.1 分别为 `75d6598`、`3170e6a`、`5491829`；真实读模型验收继续按用户决定延后；
- P3.3a Run 受理/幂等：`dc122cc`，P3.3b 持久化 RunEvent/SSE：`e7858ce`，P3.3c Mock FastAPI SSE 契约与用户可视化验收：`ca899e0`；
- P3.4 Design：`fb76b35`，P3.4a：`bc1b4aa`；
- P3.4b 修改 `WorkbenchPage.tsx` 将结果面板接入 `SelectedRun`：成功 Result 必须完整合法；failed/cancelled/queued/running/未知或矛盾载荷都有诚实展示；归档历史 Result 只读可看，提交区继续禁用。更新 `App.test.tsx` 后已通过 `npm run typecheck`、Vitest 4 files / 37 passed、`npm run build`；未改 MSW/Mock/后端/report/真实资源。

## 当前唯一下一步

**P3.4c：补齐完整结构化 Result 的 MSW/独立 Mock FastAPI 契约，并完成独立 8100→5175 代理与人工验收。**需要用户明确代码授权；不要接入真实 8000/数据库，或混入 Trace/Markdown/审批/报告/P4–P6 能力。

## P3.4c 固定边界

- MSW 与 `frontend/scripts/mock_v1_api.py` 必须提供全部 P2 `DiagnosisResult` 字段，尤其 `created_at`，并包含完整成功、局部空数组、failed/cancelled/queued/running、归档历史和协议/安全错误场景；
- 不改 P2 后端、OpenAPI、既有 `/api/v1` 契约、旧 `/diagnose*`、`report/`、真实数据库或数据源；Mock 仍只做进程内确定性验收，不成为队列/持久化替代；
- 自动验证至少包括 `npm run test:mock-api`、`npm run typecheck`、`npm run test`、`npm run build`；独立验收只用临时 Mock `8100` 与 Vite `5175`，显式 `VITE_API_PROXY_TARGET=http://127.0.0.1:8100`，完成后关闭临时实例；
- 人工验收覆盖成功结果、空数组、failed/cancelled、归档历史、刷新深链、Result 协议错误、无 Trace 入口和代理非 JSON 安全错误；
- 若 Mock 或 P2 契约字段有分歧，先停在契约差异，不在前端猜字段或用真实 8000 替代。

## 严格隔离

- 不读取、修改、暂存、提交或 reset `docs/00-项目方案说明书.md`；
- `backend/src/domain/__init__.py`、`backend/src/infrastructure/persistence/__init__.py` 已核对无内容 diff；不得修改、暂存或 reset；
- 不改 `report/`、后端 `/api/v1`、Application Service、Repository、ORM、Alembic、旧 `/diagnose*` 或运行时资产；
- 禁止 `git add .`。提交时逐个指定本 Step 文件，并在提交前执行 `git diff --cached --check`。
