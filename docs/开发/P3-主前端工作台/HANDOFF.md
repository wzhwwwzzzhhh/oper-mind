# P3 HANDOFF — 主前端工作台

> 日期：2026-07-28　|　状态：✅ P3.4 Design 已完成并独立审查通过；等待 P3.4a 代码授权
>
> 工作分支：`feat/p3-workbench`　|　提交基线：`306724d docs: 校正P3.3c提交状态并进入P3.4`

## 已完成

- P3.1 工程与产品外壳：`4862752`；
- P3.2 Design：`ec45ee2`，P3.2a/b/c.1 分别为 `75d6598`、`3170e6a`、`5491829`；真实读模型验收继续按用户决定延后；
- P3.3a Run 受理/幂等：`dc122cc`，P3.3b 持久化 RunEvent/SSE：`e7858ce`，P3.3c Mock FastAPI SSE 契约与用户可视化验收：`ca899e0`；
- P3.4 Design 已完成：`design.md` 第 10 节、`step4-结构化结果与终态收口.md` 与本轮独立 Review 定义 Result、终态、空/归档、Mock 与 Trace/report 边界；本轮没有代码、Mock 或真实资源改动。

## 当前唯一下一步

**P3.4a：结构化结果读取模型与摘要面板实现。**需要用户明确代码授权；不要把 P3.4b/c、真实 API/数据库联调或任何 P4–P6 能力混入该 Step。

## P3.4a 固定边界

- 只以 `GET /api/v1/runs/{run_id}` 的 `DiagnosisRun.result` 为事实，校验 `result.run_id`、必填字段、枚举、置信度与 UTC `Z`；
- 只实现只读摘要、severity/confidence、根因、证据及合法空数组的局部空状态；
- 预计文件：`frontend/src/features/workbench/result-readers.ts`、`DiagnosisResultPanel.tsx`、其测试和必要样式；超过 4 个源码/测试文件先更新 HANDOFF；
- 不接入 failed/cancelled/归档全量收口、Mock FastAPI、Trace URL、Markdown 渲染、审批/执行/报告能力；
- P3.3c Mock 的成功 Result 缺 `created_at`，不能作为 P3.4a 端到端事实；P3.4a 使用完整静态夹具，P3.4c 再单独补齐 MSW/Mock。

## 必跑验证（P3.4a 实现时）

```powershell
Set-Location frontend
npm run typecheck
npm run test
npm run build
```

并覆盖完整 Result、空数组、run_id 错配、缺失字段、未知枚举与非 UTC `Z`。没有 P3.4c 授权前不运行/修改独立 Mock；没有真实接入确认前不访问 8000、真实数据库或数据源。

## 严格隔离

- 不读取、修改、暂存、提交或 reset `docs/00-项目方案说明书.md`；
- `backend/src/domain/__init__.py`、`backend/src/infrastructure/persistence/__init__.py` 已核对无内容 diff；不得修改、暂存或 reset；
- 不改 `report/`、后端 `/api/v1`、Application Service、Repository、ORM、Alembic、旧 `/diagnose*` 或运行时资产；
- 禁止 `git add .`。提交时逐个指定本 Step 文件，并在提交前执行 `git diff --cached --check`。
