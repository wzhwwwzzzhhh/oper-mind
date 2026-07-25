# M7 设计 — 前端可视化

> 里程碑：M7　|　分支：`feat/m7-frontend-visualization`
> 创建日期：2026-07-20　|　调整日期：2026-07-24
> 状态：🟡 进行中（M7.0–M7.4 已完成；M7.5 联调与视觉收口开发中）
> 关联：消费 M6 SSE 契约（`f6eb087`）；详细执行顺序以本文件为准。

## 1. 目标

把多 Agent 编排过程**可视化**，作为「全栈 + agent」岗位的正面证明。核心看点是一个**实时刷新的多 Agent 诊断链路 + 结构化报告 + M5 证据看板**。

M7 不追求复刻运维平台；优先完成答辩可稳定演示的单页控制台，账户、权限、复杂监控大盘不在本里程碑范围内。

## 2. 实施原则

- **薄切片，不大爆炸**：每个 Step 只解决一个可独立验收的用户价值，不把脚手架、SSE、图表和视觉收口塞进同一个提交。
- **同步先行，流式增强**：先让 `POST /diagnose` 的演示闭环稳定，再接入 SSE；SSE 断流时必须能回退同步诊断。
- **trace 是唯一过程真相**：前端不从 query 猜测 Debate / Reflection；只根据后端 trace 渲染是否发生。
- **契约优先**：`src/frontend/src/types/` 映射 M6 的 Pydantic 公开字段；后端契约变更先更新类型再改 UI。
- **诚实展示实验结论**：M5 看板同时展示多 Agent 的优势与边界，不只挑选提升数字。

## 3. 技术栈与目录

MVP 使用 Vite + React + TypeScript；M7.4 再引入 ECharts。首个版本不引入 AntD、Zustand、TanStack Query 或路由框架，等状态复杂度实际出现后再评估。

```text
src/frontend/
├── index.html  package.json  vite.config.ts  tsconfig*.json
└── src/
    ├── main.tsx  App.tsx
    ├── api/          # HTTP 与 SSE 请求封装
    ├── types/        # 与后端 Pydantic 契约对齐的 TS 类型
    ├── components/   # 从 M7.1 起按功能增量创建
    └── styles/
```

Vite 开发代理把 `/api/*` 转发给 `http://127.0.0.1:8000/*`；浏览器代码不保存 API Key，也不直接写真实后端地址。

## 4. 分步执行指引

| Step | 范围 | 交付与验收 | 当前状态 |
|---|---|---|---|
| **M7.0** | 工程地基 | Vite/React/TS、`/api` 代理、`GET /health`、最小页面壳；`typecheck + build` 通过 | ✅ 完成 |
| **M7.1** | 同步诊断闭环 | 输入问题 → `POST /diagnose` → loading / 报告 / 复制 / 错误态；不引入 SSE | ✅ 完成 |
| **M7.2** | Trace 回放与三路拓扑 | 用真实同步 trace + 固定 fixture 表现 direct / chain / parallel；不推断质量节点 | ✅ 完成 |
| **M7.3** | SSE 实时增量与降级 | 消费 `progress / complete / error`；逐步点亮；断流 / error / 取消回退同步 | ✅ 完成 |
| **M7.4** | M5 指标看板 | ECharts 展示全局与 case_group 对比，标明数据来源、样本与局限 | ✅ 完成 |
| **M7.5** | 联调与视觉收口 | mock API 演示、代理联调、1366×768 验收、截图 / 录屏、已知限制 | 🟡 开发中 |

### 每个 Step 的固定工作流

```text
Design → Code → Typecheck / Build / 对应测试 → 独立 Review → 修复复验 → Commit
```

- 每一步完成后先写对应 `stepN-*.md` 快照，再进入独立 Review。跨上下文或出现审查问题时，按 `HANDOFF.md` 记录可恢复交接点。
- 当前未提交代码只能属于一个 Step；后续 Step 的组件、依赖、文档不得提前混入。
- 若一次实现暴露多个 Step 的代码，优先收敛回当前 Step，而不是以“大提交”掩盖边界。

## 5. M7.0 当前边界

M7.0 **只**保留：

- 工程配置、依赖锁定、Vite 代理；
- `HealthResponse` TypeScript 类型与 `GET /health` 客户端；
- 后端连通状态和 M7 后续步骤说明页面；
- `npm run typecheck` 与 `npm run build` 验证。

M7.0 **明确不包含**：诊断表单、`POST /diagnose`、trace、SSE、报告组件、ECharts、场景接口或实验产物读取。

## 6. M7 完成验收

- M7.1–M7.5 分别有开发日志、测试结果、独立 Review 和中文 commit。
- mock 模式下可稳定演示 direct / chain / parallel 三条路径。
- 页面由真实后端 trace 和 SSE 渲染过程，不硬编码 Debate / Reflection 发生与否。
- SSE 不可用时，用户能看见明确提示并获得同步诊断 fallback。
- 前端不展示 API Key、本地配置、Judge 对照文件或长期记忆原始数据。
