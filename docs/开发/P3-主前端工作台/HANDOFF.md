# P3 HANDOFF — 主前端工作台

> 更新时间：2026-07-28　|　状态：🟡 P3.3b 已授权开始；P3.3a 已提交
>
> 分支：`feat/p3-workbench`　|　最近提交基线：`dc122cc feat: 完成P3.3a Run受理与幂等重试`
>
> 恢复入口：`docs/开发/_A-Plan-总览.md`、本文件、`design.md`、`step3-run受理幂等与sse恢复.md`、`review.md`。

## 已完成

- P3 Design：`12bed37`；P3.1 工程与产品外壳：`4862752`；P3.2 Design：`ec45ee2`；P3.2a v1 GET client：`75d6598`；P3.2b 只读会话恢复：`3170e6a`；P3.2c.1 Mock FastAPI 验收：`5491829`；P3.2c.2 离线前置核对：`87c4f83`；P3.3 Design：`f038f09`。
- 用户已决定真实数据库只读验收延后到前后端大致开发完成后；C1–C8 保留为届时的必备清单，当前不连接真实 DB、数据源或用户启动的 8000 后端。
- P3.3a 已提交为 `dc122cc`：实现 v1 POST Run client、TanStack Query mutation、active Session 问题提交、同 key 的未知网络结果重试、202 深链、归档禁用与安全错误；未实现 Event/SSE、完整结果、Trace 跳转或独立 Mock FastAPI 扩展。
- 验证已通过：`npm run typecheck`；`npm run test`（2 files / 17 passed）；`npm run build`。构建仅有非阻断的单 chunk 大小提示。
- 本次实现只修改 `frontend/src/`；未修改 `backend/`、`report/`、`data/`、`frontend/mockup.html` 或 P2 `/api/v1`。

## 当前唯一下一步

**P3.3b：持久化事件与 SSE 恢复实现。**本轮只读取 P2 的 `GET /runs/{run_id}/events` 与 `GET /runs/{run_id}/stream`：添加 opaque cursor 读取、`(run_id, sequence)` 合并/去重、原生 EventSource 生命周期、断线 REST 重同步与终态重读。

不得修改后端、旧 API、`report/`、真实 DB/8000；不得进入 P3.3c 的独立 Mock FastAPI 验收、完整结果卡或 Trace 跳转。实现完成后执行 typecheck、Vitest、build 和独立 Review，再等待提交授权。

## 外部隔离改动

禁止读取、修改、暂存、提交或 reset：

```text
docs/00-项目方案说明书.md
```

`backend/src/domain/__init__.py` 与 `backend/src/infrastructure/persistence/__init__.py` 可能显示为修改；恢复时必须 `git diff -- <file>` 核对。当前无内容 diff 的行尾/元数据状态不纳入任何提交，也不 reset。
