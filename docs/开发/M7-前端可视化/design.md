# M7 设计 — 前端可视化

> 里程碑：M7　|　分支：待建
> 创建日期：2026-07-20
> 状态：🟡 下一个（M6 已完成，待创建 M7 分支后启动）
> 关联：吸收并取代 `docs/前端开发路线图.md` 的规划；后端依赖 M6 已在 `f6eb087` 完成。

## 1. 目标

把多 Agent 编排过程**可视化**，作为「全栈 + agent」岗位的正面证明。核心看点：一个**实时刷新的多 Agent 诊断链路 + ECharts 指标看板**。消费 M6 的 SSE 契约。

## 2. 技术栈与目录

Vite + React + TypeScript + ECharts（AntD 可选）。源码目录：

```
src/frontend/
├── index.html  package.json  vite.config.ts  tsconfig.json
└── src/
    ├── main.tsx  App.tsx
    ├── api/          # SSE 客户端 + 请求封装
    ├── types/        # 与后端 Pydantic 契约对齐的 TS 类型
    ├── components/
    │   ├── trace/    # 诊断链路实时视图
    │   └── charts/   # ECharts 看板组件
    ├── pages/
    └── styles/
```

## 3. 关键决策

- **可视化什么**：路由决策（direct/chain/parallel 的视觉差异是核心看点）→ 各 Agent 起止 → 辩论轮次 → 反思 → 报告；旁边 ECharts 展 M5 的对比曲线 / token / 延迟。
- **实时性**：消费 SSE 事件逐步点亮链路，而非一次性返回。
- **契约对齐**：`src/frontend/src/types/` 直接映射 M6 `src/api/schemas.py` 与事件定义。

## 4. Step 分解

| Step | 内容 | 主要改动 |
|---|---|---|
| step1 | 前端脚手架与 SSE 客户端 | `src/frontend/` 整套骨架 + `src/frontend/src/api/` |
| step2 | 诊断链路实时视图 | `src/frontend/src/components/trace/*` |
| step3 | 指标看板 ECharts | `src/frontend/src/components/charts/*` |

## 5. 验收

- `npm run dev` 起得来，vite proxy 通到 uvicorn。
- 输入查询后，诊断链路随 SSE 实时点亮，三种路由策略视觉可辨。
- 看板正确渲染 M5 对比数据。
- 有降级兜底（SSE 断线 → 退非流式或提示）。
