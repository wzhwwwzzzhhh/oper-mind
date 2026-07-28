# P3 HANDOFF — 主前端工作台

> 更新时间：2026-07-28　|　状态：✅ P3.3b 已提交 `e7858ce`；当前进入 P3.3c Design / 验收准备
>
> 分支：`feat/p3-workbench`　|　最近提交基线：`e7858ce feat: 完成P3.3b持久化事件与SSE恢复`
>
> 恢复入口：`docs/开发/_A-Plan-总览.md`、本文件、`design.md`、`step3-run受理幂等与sse恢复.md`、`review.md`。

## 已完成

- P3 Design：`12bed37`；P3.1：`4862752`；P3.2 Design：`ec45ee2`；P3.2a：`75d6598`；P3.2b：`3170e6a`；P3.2c.1：`5491829`；P3.2c.2：`87c4f83`；P3.3 Design：`f038f09`；P3.3a：`dc122cc`；状态校正：`181e601`；P3.3b：`e7858ce`。
- 用户已决定真实数据库只读验收延后到前后端大致开发完成后；C1–C8 保留为届时的必备清单，当前不连接真实 DB、数据源或用户启动的 8000 后端。
- P3.3b 已实现 RunEvent REST cursor、严格事件解析/合并、queued/running 原生 EventSource、断线 REST 重同步、终态关闭与 Run/Event/Session Runs/Messages 重读。
- 初连 SSE URL 固定不携带 `after_sequence`；浏览器负责 Last-Event-ID 自动重连。实现不设置 EventSource headers、不读取 response headers，避免 P2 双游标冲突。
- 验证已通过：`npm run typecheck`；`npm run test`（3 files / 22 passed）；`npm run build`。构建仅有非阻断的单 chunk 大小提示。
- 本次实现只修改 `frontend/src/`；未修改 `backend/`、`report/`、`data/`、`frontend/mockup.html` 或 P2 `/api/v1`。

## 当前状态与唯一下一步

P3.3b 已作为 `e7858ce feat: 完成P3.3b持久化事件与SSE恢复` 提交；该提交已逐文件暂存并通过暂存差异检查。当前不保留 P3.3b 待提交文件。

**当前唯一下一步为 P3.3c：Mock FastAPI SSE 契约验收。**该 Step 扩展独立 `frontend/scripts/` mock 与独立 Vite 人工验收，覆盖 POST 幂等、SSE `id/run_event`、Last-Event-ID 续传和终态关闭；不连接真实后端、数据库或数据源。

## 外部隔离改动

禁止读取、修改、暂存、提交或 reset：

```text
docs/00-项目方案说明书.md
```

`backend/src/domain/__init__.py` 与 `backend/src/infrastructure/persistence/__init__.py` 可能显示为修改；恢复时必须 `git diff -- <file>` 核对。当前无内容 diff 的行尾/元数据状态不纳入任何提交，也不 reset。
