# P3 HANDOFF — 主前端工作台

> 更新时间：2026-07-28　|　状态：✅ P3.3 Design 已完成，未开始 P3.3a 代码
>
> 分支：`feat/p3-workbench`　|　最近提交基线：`87c4f83 docs: 完成P3.2c2离线前置核对`
>
> 恢复入口：`docs/开发/_A-Plan-总览.md`、本文件、`design.md`、`step3-run受理幂等与sse恢复.md`、`review.md`。

## 已完成

- P3 Design：`12bed37`；P3.1 工程与产品外壳：`4862752`；P3.2 Design：`ec45ee2`；P3.2a v1 GET client：`75d6598`；P3.2b 只读会话恢复：`3170e6a`；P3.2c.1 Mock FastAPI 验收：`5491829`；P3.2c.2 离线前置核对：`87c4f83`。
- 用户已决定真实数据库只读验收延后到前后端大致开发完成后；C1–C8 保留为届时的必备清单，当前不连接真实 DB、数据源或用户启动的 8000 后端。
- P3.3 Design 已完成：明确 POST Run 的幂等重试、202 导航、刷新顺序、事件 cursor、原生 EventSource 生命周期、终态重读和错误/空状态。
- 已修正 EventSource 双游标风险：原生 EventSource 初连不得带 `after_sequence`，否则自动重连附带更新的 Last-Event-ID 时会触发 P2 的 `INVALID_EVENT_CURSOR`；初连改为全量重放加 `(run_id, sequence)` 去重，自动重连只依赖浏览器 Last-Event-ID，REST Events 负责显式重同步。
- 本轮仅更新文档，未修改 `frontend/` 业务源码、`backend/`、`report/`、`data/` 或 Mock 行为。

## 当前唯一下一步

**P3.3a：Run 受理与幂等重试实现。**仅实现 v1 POST client/mutation、active Session 问题提交、稳定 Idempotency-Key 重试、安全错误与 202 深链；不进入 RunEvent/SSE、结构化结果、Mock FastAPI 扩展或真实后端联调。

开始前固定执行：

```powershell
git status --short --branch
git log -5 --oneline
git diff --check
git diff --name-only
git diff -- backend/src/domain/__init__.py
git diff -- backend/src/infrastructure/persistence/__init__.py
```

然后阅读 `_A-Plan-总览.md`、本 HANDOFF、`design.md`、`step3-run受理幂等与sse恢复.md`、`review.md`、P0 API contract 及现有 `frontend/src/api/v1/client.ts`/`queries.ts`/`WorkbenchPage.tsx`。若记录、工作区或 OpenAPI 与设计不一致，先停在核对结论。

## P3.3a 验证与提交边界

- 预期改动仅在 `frontend/src/api/v1/`、`frontend/src/features/workbench/` 及相应 MSW/测试文件；根据实际文件逐个暂存，禁止 `git add .`。
- 必跑：`npm run typecheck`、`npm run test`、`npm run build`；Review 覆盖 POST body/header、同 key retry、202 导航、刷新无 POST、归档与 409/422/503 安全错误。
- 不启动或指向真实 DB/8000；若需后续浏览器验证，优先独立 MSW/Mock FastAPI，且不得改变用户运行的 5174/8000 进程。
- P3.3a 完成 Review 后等待用户授权提交；不要自动跨入 P3.3b。

## 外部隔离改动

禁止读取、修改、暂存、提交或 reset：

```text
docs/00-项目方案说明书.md
```

`backend/src/domain/__init__.py` 与 `backend/src/infrastructure/persistence/__init__.py` 可能显示为修改；恢复时必须 `git diff -- <file>` 核对。当前已确认无内容 diff 的行尾/元数据状态，不纳入任何提交，也不 reset。