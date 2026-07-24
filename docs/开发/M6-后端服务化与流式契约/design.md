# M6 设计 — 后端服务化与流式契约

> 里程碑：M6　|　分支：`feat/m6-backend-sse`
> 创建日期：2026-07-20　|　完成日期：2026-07-24
> 状态：✅ 完成

## 1. 目标

为前端提供稳定的 HTTP API 契约与 SSE 流式诊断能力，使诊断链路可实时展示「路由决策 → Agent 执行 → 分歧检查 / 辩论 → 报告 → 反思」。

## 2. 关键决策

- **流式方案**：采用 SSE。诊断过程只需服务端单向推送，浏览器原生 `EventSource` 可直接消费，复杂度低于 WebSocket。
- **契约先行**：新增 `src/api/schemas.py`，以 Pydantic 固化同步请求、响应、错误体、健康检查与 trace 事件字段；前端可据此生成 TypeScript 类型。
- **不改同步编排语义**：同步 `CoordinatorAgent.route()` 继续使用 `graph.invoke()`；流式路径新增 `route_stream()`，消费 LangGraph `stream_mode="updates"` 的节点更新。
- **SSE 完成语义**：过程消息使用 `event: progress`；最后仅发送一个 `event: complete`（含终稿、策略、完整 trace），执行异常则发送 `event: error`，避免把内部异常暴露给前端。
- **安全边界**：当前为本地 demo 服务，**尚未接入鉴权、限流和跨域策略**，不得直接暴露在公网；健康检查仅返回 `mode` 与 `model`，不返回密钥。

## 3. Step 分解

| Step | 内容 | 状态 | 主要改动文件 |
|---|---|---|---|
| step1 | API 契约与响应模型 | ✅ | `src/api/schemas.py`、`src/app.py`、`tests/test_api.py` |
| step2 | SSE 流式诊断事件 | ✅ | `src/api/events.py`、`src/core/coordinator.py`、`src/app.py`、`tests/test_api.py` |

## 4. 验收

- [x] 诊断接口有稳定 request/response 契约与统一错误体。
- [x] `GET /diagnose/stream?query=...` 按节点产生 progress，并以 complete/error 结束。
- [x] mock 模式下 API 单测、全量 pytest 与 direct / chain / parallel 冒烟通过。
- [x] 健康检查不暴露密钥；无鉴权限制已在本设计中显式记录。

## 5. 对 M7 的交付

前端可以直接对接：

- `POST /diagnose`：同步结果，`show_thinking=true` 时附 trace。
- `GET /diagnose/stream?query=...`：SSE，监听 `progress`、`complete`、`error` 三类 event name；其中 progress 的 `data.type` 可为 `route_decided`、`agent_start`、`agent_done`、`conflict_checked`、`debate_round`、`report`、`reflection`。
- `GET /health`：顶部服务状态；仅展示 `status`、`mode`、`model`。
