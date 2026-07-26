# P3 Step1 — 前端工程初始化与产品外壳

> 日期：2026-07-26　|　状态：✅ 已完成并提交　|　关联 commit：本 Step 提交
>
> 前置提交：`12bed37 docs: 完成P3主前端工作台设计`　|　工作分支：`feat/p3-workbench`

## Design

P3.1 只建立可构建、可测试的 V1 主产品外壳：React + TypeScript + Vite、React Router、TanStack Query、Zustand、Ant Design 的最小装配，以及 `/workbench` 路由与顶部/侧栏/中心占位结构。它不实现会话恢复、Run 创建、SSE 或结果卡片。

## Step

1. 在保留 `frontend/mockup.html` 的前提下初始化独立工程，锁定兼容 Node 22/npm 10 的 package/lockfile。
2. 建立 Providers、基础样式、Router、QueryClient、Zustand UI store 与 Ant Design product shell；不建立 P4/P5/P6 资源页面。
3. 配置 typecheck、Vitest/RTL、最小 MSW server 基础和 production build。
4. 空工作台仅显示“尚未接入会话数据”，不得请求旧 API 或塞入 fake Session/Run。
5. 完成 typecheck、测试、build 和本地视觉/导航验收；独立审查范围、原型保留与隔离状态。

## Code

- `frontend/package.json:1-33`、`frontend/package-lock.json`：建立独立 `opermind-workbench` 工程和 `dev/build/typecheck/test` 命令；锁定 React/Vite、Router、Query、Zustand、Ant Design 与 Vitest/RTL/MSW 依赖。
- `frontend/.gitignore:1-4`：只忽略 `node_modules/`、`dist/`、coverage 和本地日志；P0 `mockup.html` 未修改、仍保留。
- `frontend/vite.config.ts:1-19`：React Vite 插件、独立 5174 开发端口、`/api` 代理占位及 jsdom Vitest 环境；不接旧 `/diagnose`。
- `frontend/src/app/providers.tsx:1-32`：QueryClient 只配置通用 server-state 策略，Ant Design 主题集中装配；尚无 v1 query 或业务缓存。
- `frontend/src/stores/use-ui-store.ts:1-13`：Zustand 仅存侧栏折叠 UI 状态，未复制 Session/Run/Result 服务器事实。
- `frontend/src/app/App.tsx:1-96`：建立 `/ → /workbench`、`/workbench` 和兜底重定向，以及产品顶部、导航、中心工作区和右侧上下文栏。
- `frontend/src/features/workbench/WorkbenchPage.tsx:1-33`、`frontend/src/styles/global.css:1-158`：展示结果优先的真实空状态和 P4/P5/P6 诚实状态，未伪造会话、数据源、告警、审批或报告能力。
- `frontend/src/test/setup.ts:1-22`、`frontend/src/test/server.ts:1-4`、`frontend/src/app/App.test.tsx:1-18`：建立 MSW 基础、Ant Design 测试环境和产品外壳断言；P3.2 才加入 v1 handler。

## Test

```text
Node v22.23.1 / npm 10.9.8
npm run typecheck：通过
npm test：1 passed
npm run build：通过（Vite 7.3.6）
```

本地浏览器验收 `http://127.0.0.1:5174/workbench`：工作台标题和“尚未接入会话数据”空状态可见；收起/展开导航可用；右栏明确 `report/` 仅为研发界面，不嵌入或模拟 Trace。临时开发服务已停止，未保留日志、`dist/` 或 `node_modules/` 到 Git diff。

build 仅提示 Ant Design 初始 JavaScript chunk 为约 581 kB（gzip 约 191 kB），超过 Vite 500 kB 建议阈值；P3.1 页面很少，未为规避提示提前拆分或引入路由懒加载，后续根据 P3 实际页面增长再优化。

## Review

- 通过：工程仅位于 `frontend/`，`frontend/mockup.html` 未修改；`report/`、`backend/`、`data/`、旧 API 和真实配置均无本 Step diff。
- 通过：产品壳只包含 `/workbench` 和真实空状态；没有 Session/Run 伪数据、没有 v1 API 请求、没有 P4/P5/P6 假页面。
- 通过：TanStack Query、Zustand 和 MSW 仅完成边界装配；server-state 与 UI-state 未混用，后续 P3.2 可在此基础接入 v1 读模型。
- 通过：typecheck、测试、build 和人工导航验收均成功。无阻塞项。

## 提交边界与下一步

本 Step 只提交 `frontend/` 新工程文件、P3 日志/计划/规则状态更新；禁止 `git add .`，不得暂存隔离的 `docs/00-项目方案说明书.md`、两个初始化文件、`report/`、后端或运行时资产。

提交后，唯一下一步为 **P3.2：v1 API 客户端与会话恢复读模型的 Design**；不得混入 Run 受理、SSE 或结构化结果。