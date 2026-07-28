# P3 HANDOFF — 主前端工作台

> 日期：2026-07-28　|　状态：✅ P3.4a 已完成代码、自动验证与独立 Review；等待 P3.4b 代码授权
>
> 工作分支：`feat/p3-workbench`　|　提交基线：`fb76b35 docs: 完成P3.4结构化结果设计`

## 已完成

- P3.1 工程与产品外壳：`4862752`；
- P3.2 Design：`ec45ee2`，P3.2a/b/c.1 分别为 `75d6598`、`3170e6a`、`5491829`；真实读模型验收继续按用户决定延后；
- P3.3a Run 受理/幂等：`dc122cc`，P3.3b 持久化 RunEvent/SSE：`e7858ce`，P3.3c Mock FastAPI SSE 契约与用户可视化验收：`ca899e0`；
- P3.4 Design：`fb76b35`；
- P3.4a 新增 `result-readers.ts`、`DiagnosisResultPanel.tsx` 和 `diagnosis-result.test.tsx`：完整 Result 运行时窄化、只读摘要/根因/证据、局部空状态和安全页内证据关联。已通过 `npm run typecheck`、Vitest 4 files / 32 passed、`npm run build`；未接入工作台，未改 Mock/后端/report/真实资源。

## 当前唯一下一步

**P3.4b：将结果面板接入 `SelectedRun`，并收口 failed/cancelled/queued/running、数组空状态、归档只读、404/跨 Session 与协议错误。**需要用户明确代码授权；不要把 P3.4c Mock 合同、Trace URL 或任何 P4–P6 能力混入该 Step。

## P3.4b 固定边界

- 只消费既有 `GET /api/v1/runs/{run_id}`；成功 Run 仅在 Result reader 合法时渲染 P3.4a 面板；
- `failed` 只显示服务端安全 `Run.error`；`cancelled` 不伪造原因；`queued/running` 不展示旧结果；
- Result/API/网络/非 JSON/协议读取失败必须区分；归档 Session 只读，不发送新 POST/PATCH/DELETE；
- 不修改 MSW/FastAPI Mock（P3.4c）、后端/旧接口/report，不实现 Trace、Markdown、审批、执行、报告或真实连接；
- 预计主要变更 `WorkbenchPage.tsx` 与组件/路由测试；若超过 4 个实现文件先更新 HANDOFF。

## 必跑验证（P3.4b 实现时）

```powershell
Set-Location frontend
npm run typecheck
npm run test
npm run build
```

必须覆盖成功面板、failed/cancelled/queued/running、无 Run、Result 局部空数组、归档、404/跨 Session 与 API/网络/协议错误。P3.4c 之前不运行/修改独立 Mock；真实接入确认之前不访问 8000、真实数据库或数据源。

## 严格隔离

- 不读取、修改、暂存、提交或 reset `docs/00-项目方案说明书.md`；
- `backend/src/domain/__init__.py`、`backend/src/infrastructure/persistence/__init__.py` 已核对无内容 diff；不得修改、暂存或 reset；
- 不改 `report/`、后端 `/api/v1`、Application Service、Repository、ORM、Alembic、旧 `/diagnose*` 或运行时资产；
- 禁止 `git add .`。提交时逐个指定本 Step 文件，并在提交前执行 `git diff --cached --check`。
