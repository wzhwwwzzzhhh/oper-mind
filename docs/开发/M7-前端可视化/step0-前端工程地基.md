# M7 Step0 — 前端工程地基

> 日期：2026-07-24　|　状态：✅ 通过　|　分支：`feat/m7-frontend-visualization`

## Design

M7 的第一步只建立一个可构建、可通过代理访问 FastAPI 健康检查的前端地基。此前的一次性原型包含诊断、SSE、链路图和 ECharts，已主动收敛，不提前把后续风险带入本 Step。

## Step

1. 建立 Vite + React + TypeScript 工程和锁文件。
2. 配置 `/api` 到 FastAPI 的本地开发代理。
3. 映射 `HealthResponse` 类型并实现 `GET /health` 客户端。
4. 用最小页面展示连通状态和 M7.1–M7.5 执行指引。
5. 忽略 node_modules、dist 和本地开发日志。

## Code

- `src/frontend/package.json:1-21`：仅保留 React、Vite、TypeScript；ECharts 延后到 M7.4。
- `src/frontend/vite.config.ts:1-16`：开发代理。
- `src/frontend/src/types/api.ts:1-5`、`src/frontend/src/api/health.ts:1-11`：健康检查类型与客户端。
- `src/frontend/src/App.tsx:1-89`：健康检查和后续实施步骤页面。
- `src/frontend/src/styles/global.css:1-58`：M7.0 最小桌面页面样式。
- `.gitignore`：忽略前端依赖、构建产物和本地日志。

## Test

```text
npm run typecheck  → 通过
npm run build      → 通过
```

生产构建主 JS gzip 约 62 kB；相比收敛前的 ECharts 原型显著降低，符合地基阶段不提前引依赖的边界。

## Review

- 审查人：Herschel（独立 code-review agent），审查日期：2026-07-24。
- 审查结论：无 P0/P1 阻塞项；确认 `/api` 代理、M7.0 依赖边界、加载/成功/失败状态和忽略规则正确。
- 审查建议与处置：
  1. 健康检查响应增加轻量运行时字段校验，避免后端契约漂移导致渲染异常；已在 `src/frontend/src/api/health.ts:5-17` 修复。
  2. 路线图明确“当前完成 M7.0，下一步进入 F0/M7.1”，避免误以为诊断闭环已完成；已更新 `docs/前端开发路线图.md`。
  3. 保留原有 step1–3 计划快照，不将粒度收敛误做成历史文档删除。
- 复验：`npm run typecheck`、`npm run build`、M7.0 范围检查均通过。
- 结论：**通过**。
