# 完善-壳层诚实化 · 工作包计划（issue #103）

> 类型：轻流程工作包（`docs/开发规范.md` §7.1，不新增公开 API / 迁移 / Connector / 能力承诺）。
> 工作地图：`docs/完善清单.md` P1-1、P1-6、P1-9、P1-12 剩余。
> 基线：`main`（2eb058c #99）；worktree：`D:/market-handsome/oper-mind-worktrees/shell-honesty`；
> 分支：`fix/issue103-shell-honesty`。

## 范围

### 只做
- **P1-1**：死入口/死按钮——`ServiceContextNav`“接入新服务”、`Composer`“安全策略”、TopBar 模型按钮
  已在 P7/P8 重构中删除；本次复扫其余壳层入口确认无静默死入口（`GlobalNav`/`ServiceContextNav`/`Sidebar`/
  `TopBar` 均指向真实路由或有“未开放”提示）。TopBar 增加**生效模型只读标识**：从 `get_model_config_query`
  读取真实生效诊断模型名 + mock/real 模式，加载中/失败如实显示，不写死模型名。
- **P1-6**：移除 `Composer` 写死的“默认只读调查” context-chip（服务上下文已由父级真实渲染：
  会话工具栏“调查目标服务”、欢迎页“默认只读调查”、回答“只读调查”徽标）；同步删除不再使用的 CSS
  （`.tool-group` / `.context-strip` / `.context-strip__icon`）。
- **P1-9**：`WelcomePanel` 服务数文案“在线”→**“已接入”**（注册数语义）；去掉硬编码默认 3（默认 0）；
  新增 `services_loading` / `services_error` 属性，加载中/失败如实显示“正在读取… / 服务列表暂不可读”，
  服务选择器同样补 loading/error 空态。`WorkbenchPage.ConversationHome` 把 `services_query` 的
  loading/error 传给 `WelcomePanel`（不再静默吞错显示 0）。
  `ServiceCenterPage`/`ServiceDetailPage` 现状已诚实（“已注册服务”、真实时间戳、加载/错误/空态齐全），仅清单回写。
- **P1-12 剩余**：Ctrl K 已真实实现（`Sidebar` 搜索 + document `Ctrl+K` 聚焦 + Esc 清空，`Sidebar.test.tsx` 覆盖）；
  硬编码“王志海/研发运维团队”已移除（`App.test.tsx` 断言不存在）；浏览器端到端复验按 issue #103 原文
  **并入阶段验收**，本次无代码改动，仅更新清单状态。

### 明确不做
- 不改后端（无接口 / 迁移 / Connector / 审批执行能力变化）。
- 不引入登录/用户体系，不编造用户信息（P1-12 用户占位仅删除，不新造）。
- 不做 P1-7 模型设置页“后端装配开关”（需 Design → Review → 用户确认，不在本 issue）。
- 不做“服务在线/健康”实时探测能力；现有快照语义不变，注册数 ≠ 在线数。
- 不新增后台轮询；不把注册数伪装成在线数。

## 切片拆分
- [x] S1：P1-1 + P1-6 —— TopBar 生效模型读真实配置 / Composer 移除写死 chip / 壳层死入口复扫确认。
- [x] S2：P1-9 + P1-12 回写 —— WelcomePanel / ConversationHome 服务数诚实化 + 加载/错误态；P1-12 无代码改动仅回写清单。

## 改动面（文件级）
- `frontend/src/features/shell/TopBar.tsx`（新增生效模型只读标识）
- `frontend/src/features/shell/Composer.tsx`（移除写死 context-chip）
- `frontend/src/styles/workbench.css`（删除 `.tool-group` / `.context-strip` / `.context-strip__icon`）
- `frontend/src/styles/app-shell.css`（新增 `.effective-model` 标识样式）
- `frontend/src/features/shell/WelcomePanel.tsx`（服务数文案 + 默认 0 + loading/error 态）
- `frontend/src/features/workbench/WorkbenchPage.tsx`（`ConversationHome` 传 loading/error）
- `frontend/src/features/shell/WelcomePanel.test.tsx`（诚实化用例：已接入 / loading / error / 默认 0）
- `frontend/src/app/App.test.tsx`（TopBar 生效模型断言、欢迎页“已接入”文案断言）
- `docs/完善清单.md`（P1-1 / P1-6 / P1-9 / P1-12 状态与验证方式回写）
- `docs/workpack/README.md`（活跃工作包登记）
- `docs/workpack/完善-shell-honesty/{plan,review,evidence}.md`（本工作包）

## 验证方法
- 前端（`frontend/` 下）：`npm run typecheck`、`npm run test`、`npm run build` 全绿。
- 门禁：`git diff --check` 干净；只暂存本工作包文件；无后端改动故不跑后端 pytest。

## 提交计划
- 切片 S1+S2 为同一诚实化工作包、改动紧耦合，按「代码 / 文档」分两次提交：
- `feat: 产品壳层诚实化——TopBar 生效模型、Composer chip 移除与服务数文案（issue #103）`（全部前端代码与测试）
- `docs: 完善清单回写壳层诚实化状态并登记工作包（issue #103）`（`完善清单.md` + 本工作包文档）
