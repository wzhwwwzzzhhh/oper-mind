# M6 设计 — 后端服务化与流式契约

> 里程碑：M6　|　分支：待建
> 创建日期：2026-07-20
> 状态：⚪ 计划

## 1. 目标

为前端立一套**稳定的 API 契约 + SSE 流式诊断**。前端要实时展示 agent 编排进度，这是它的地基，必须先于 M7。当前 `src/app.py` 仅 84 行、无 streaming。

## 2. 关键决策

- **流式方案**：SSE（单向服务端推送，够用且实现简单）而非 WebSocket。
- **事件契约**：编排各阶段产出增量事件——路由决策 / Agent 起止 / 辩论轮次 / 反思 / 报告。前端据此点亮链路。
- **契约先行**：request/response 与事件用 Pydantic 定死，前端 TS 类型据此对齐（M7 step1）。

## 3. Step 分解

| Step | 内容 | 主要改动文件 |
|---|---|---|
| step1 | API 契约与响应模型 | 新增 `src/api/schemas.py`、重整 `src/app.py`、可能碰 `src/core/bootstrap.py` |
| step2 | SSE 流式诊断事件 | `src/app.py`、`src/core/coordinator.py`、`src/core/graph.py`、新增 `src/api/events.py` |

## 4. 验收

- 诊断接口有稳定 request/response 契约 + 统一错误处理。
- SSE 端点能逐条推送编排事件，本地 curl/浏览器可见增量。
- mock 与真实模式均可流式；`smoke_pipeline.py` 回归通过。
- **安全**：网络暴露接口若无鉴权须显式说明（demo 场景可接受，但要标注）。
