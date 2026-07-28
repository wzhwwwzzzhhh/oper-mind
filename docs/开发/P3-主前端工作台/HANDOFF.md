# P3 HANDOFF — 主前端工作台

> 更新时间：2026-07-28　|　状态：✅ P3.3c 代码、自动、独立代理与用户可视化验收及 Review 均已完成，等待提交授权
>
> 分支：`feat/p3-workbench`　|　最近提交基线：`e7b34a5 docs: 校正P3.3b提交状态并进入P3.3c`
>
> 恢复入口：`docs/开发/_A-Plan-总览.md`、本文件、`design.md`、`step3-run受理幂等与sse恢复.md`、`review.md`。

## 已完成

- P3 Design：`12bed37`；P3.1：`4862752`；P3.2 Design：`ec45ee2`；P3.2a：`75d6598`；P3.2b：`3170e6a`；P3.2c.1：`5491829`；P3.2c.2：`87c4f83`；P3.3 Design：`f038f09`；P3.3a：`dc122cc`；状态校正：`181e601`、`e7b34a5`；P3.3b：`e7858ce`。
- P3.3c 仅扩展 `frontend/scripts/mock_v1_api.py` 与 `frontend/scripts/test_mock_v1_api.py`：确定性进程内 POST Run 幂等、不同 key 独立 Run/trace/RunEvent ID、RunEvent REST cursor、有限持久化 SSE、Last-Event-ID/after_sequence、双游标 `400` 和终态关闭。
- `npm run test:mock-api` 为 10 passed（仅 TestClient/httpx 弃用警告）；`npm run typecheck`、`npm run test`（3 files / 22 passed）和 `npm run build` 均通过。build 仍只有既有单 chunk 大小非阻断提示。
- 本轮临时 8100 Mock 与 5175 Vite（`VITE_API_PROXY_TARGET=http://127.0.0.1:8100`）的真实 HTTP 代理验收通过；用户已完成独立可视化主流程验收并确认“开始诊断 → 事件到 succeeded → 刷新深链恢复”通过。临时进程均已关闭。
- 没有修改 `backend/`、`report/`、`data/`、`frontend/mockup.html`、P2 `/api/v1`，也没有连接真实数据库、数据源或用户的 8000 后端。

## 待提交文件与建议提交

仅暂存以下 P3.3c 文件与状态文档，禁止 `git add .`：

```text
frontend/scripts/mock_v1_api.py
frontend/scripts/test_mock_v1_api.py
AGENTS.md
CLAUDE.md
docs/开发/_A-Plan-总览.md
docs/开发/_B-V1产品化开发计划.md
docs/开发/P3-主前端工作台/design.md
docs/开发/P3-主前端工作台/step3-run受理幂等与sse恢复.md
docs/开发/P3-主前端工作台/review.md
docs/开发/P3-主前端工作台/HANDOFF.md
```

```text
feat: 完成P3.3c Mock FastAPI SSE契约验收
```

## 当前状态与提交后唯一下一步

**当前仅等待用户明确授权提交 P3.3c；不要自动进入 P3.4。**

提交后的唯一下一步为 **P3.4 Design：结构化结果、失败/空/归档收口与受控 Trace 入口**。真实数据库、数据源、P4/P5/P6 资源和旧 `/diagnose*` 均不进入该 Design 前的提交。

## 外部隔离改动

禁止读取、修改、暂存、提交或 reset：

```text
docs/00-项目方案说明书.md
```

`backend/src/domain/__init__.py` 与 `backend/src/infrastructure/persistence/__init__.py` 可能显示为修改；恢复时必须 `git diff -- <file>` 核对。当前无内容 diff 的行尾/元数据状态不纳入任何提交，也不 reset。
