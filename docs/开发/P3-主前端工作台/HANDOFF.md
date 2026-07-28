# P3 HANDOFF — 主前端工作台

> 更新时间：2026-07-28　|　状态：✅ P3.3a 已完成 Review，等待用户提交授权
>
> 分支：`feat/p3-workbench`　|　最近提交基线：`f038f09 docs: 完成P3.3 Run受理与SSE恢复设计`
>
> 恢复入口：`docs/开发/_A-Plan-总览.md`、本文件、`design.md`、`step3-run受理幂等与sse恢复.md`、`review.md`。

## 已完成

- P3 Design：`12bed37`；P3.1 工程与产品外壳：`4862752`；P3.2 Design：`ec45ee2`；P3.2a v1 GET client：`75d6598`；P3.2b 只读会话恢复：`3170e6a`；P3.2c.1 Mock FastAPI 验收：`5491829`；P3.2c.2 离线前置核对：`87c4f83`；P3.3 Design：`f038f09`。
- 用户已决定真实数据库只读验收延后到前后端大致开发完成后；C1–C8 保留为届时的必备清单，当前不连接真实 DB、数据源或用户启动的 8000 后端。
- P3.3a 已实现 v1 POST Run client、TanStack Query mutation、active Session 问题提交、同 key 的未知网络结果重试、202 深链、归档禁用与安全错误；未实现 Event/SSE、完整结果、Trace 跳转或独立 Mock FastAPI 扩展。
- 验证已通过：`npm run typecheck`；`npm run test`（2 files / 17 passed）；`npm run build`。构建仅有非阻断的单 chunk 大小提示。
- 本次实现只修改 `frontend/src/`；未修改 `backend/`、`report/`、`data/`、`frontend/mockup.html` 或 P2 `/api/v1`。

## 待提交文件与建议提交

仅暂存以下 P3.3a 文件，禁止 `git add .`：

```text
frontend/src/api/v1/client.ts
frontend/src/api/v1/queries.ts
frontend/src/features/workbench/WorkbenchPage.tsx
frontend/src/api/v1/client.test.ts
frontend/src/app/App.test.tsx
frontend/src/test/handlers.ts
frontend/src/test/setup.ts
docs/开发/P3-主前端工作台/design.md
docs/开发/P3-主前端工作台/step3-run受理幂等与sse恢复.md
docs/开发/P3-主前端工作台/review.md
docs/开发/P3-主前端工作台/HANDOFF.md
docs/开发/_A-Plan-总览.md
docs/开发/_B-V1产品化开发计划.md
AGENTS.md
CLAUDE.md
```

建议提交信息：

```text
feat: 完成P3.3a Run受理与幂等重试
```

## 当前状态与提交后唯一下一步

**当前仅等待用户明确授权提交 P3.3a；不要自动进入 P3.3b。**

提交后的唯一下一步为 **P3.3b：持久化事件与 SSE 恢复实现**。恢复时先执行固定 Git 核对，阅读本 HANDOFF、`design.md`、`step3-run受理幂等与sse恢复.md`、`review.md` 和 P0 v1 contract。P3.3b 只读取 P2 的 `GET /runs/{run_id}/events` / `GET /runs/{run_id}/stream`，不改后端，不连接真实 DB/8000。

## 外部隔离改动

禁止读取、修改、暂存、提交或 reset：

```text
docs/00-项目方案说明书.md
```

`backend/src/domain/__init__.py` 与 `backend/src/infrastructure/persistence/__init__.py` 可能显示为修改；恢复时必须 `git diff -- <file>` 核对。当前无内容 diff 的行尾/元数据状态不纳入任何提交，也不 reset。
