# P3 Step1 — 前端工程初始化与产品外壳

> 日期：2026-07-26　|　状态：待 P3 Design 提交后执行　|　关联 commit：待提交

## Design

P3.1 只建立可构建、可测试的 V1 主产品外壳：React + TypeScript + Vite、React Router、TanStack Query、Zustand、Ant Design 的最小装配，以及 `/workbench` 路由与顶部/侧栏/中心占位结构。它不实现会话恢复、Run 创建、SSE 或结果卡片。

## Step

1. 在不覆盖 `frontend/mockup.html` 前提下初始化工程，锁定兼容 Node 运行时、包管理器和 lockfile。
2. 建立 Providers、基础样式、Router、QueryClient、Zustand UI store 与 AntD shell；不建立 P4/P5/P6 资源页面。
3. 配置 typecheck、Vitest/RTL、最小 MSW 基础和 production build。
4. 空工作台只能显示“尚未接入会话数据”，不得请求旧 API 或塞入 fake Session/Run。
5. build/test 后独立审查是否误动原型、`report/`、后端、`data/` 或运行时资产。

## Code/Test/Review 边界

允许范围仅为 `frontend/` 新工程文件和 P3 日志；禁止改 `frontend/mockup.html`（除非单独授权）、`report/`、`backend/`、`data/`、真实配置及旧 API。Server state 不写入 Zustand。验证 typecheck、Vitest、production build、原型保留以及 Git diff 无 `report/`、`backend/`、`data/`/SQLite。

P3.1 必须独立提交；不得混入 Session 列表、Run 创建、SSE、结果卡片或 P4/P5/P6 空页面。实际完成时建议提交信息：`feat: 初始化P3主前端工程与产品外壳`。