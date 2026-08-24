# 完善-壳层诚实化 · AC 证据表（issue #103）

> 工作包：`docs/workpack/完善-shell-honesty/`　分支：`fix/issue103-shell-honesty`
> 基线：`main`（2eb058c #99）　轻流程依据：`docs/开发规范.md` §7.1

## 切片 S1：P1-1 + P1-6

| AC（完善清单条目） | 代码/接口/测试证据 | 状态 |
|---|---|---|
| P1-1 死入口/死按钮清理（"接入新服务"、"安全策略"、TopBar 模型按钮） | 三个按钮在 main 已随 P7/P8 重构删除；本次复扫 `GlobalNav`/`ServiceContextNav`/`Sidebar`/`TopBar` 无静默死入口（分享按钮有"接入权限系统后启用"提示）。证据：`App.test.tsx`「全球图标轨只放正式模块」「顶栏生效模型读后端真实配置」（断言 `OperMind-Reasoner` 不存在） | PASS |
| P1-1 TopBar 模型名读真实生效配置 | `TopBar.tsx` 新增 `EffectiveModelLabel`，从 `get_model_config_query`（`/api/v1/model/config`）读生效诊断模型名 + mock/real 模式；loading→"生效模型读取中…"、error→"生效模型暂不可读"、未配置→"未配置"；real 已保存但 `mode_available=false` 时如实标注"（暂不可用）"（后端此时回退确定性调用）。证据：`App.test.tsx`「顶栏生效模型读后端真实配置，不再写死模型名」（MSW 返回 diagnostic-model · mock）、「顶栏在 real 不可用时如实标注暂不可用，不冒充真实调用」 | PASS |
| P1-6 Composer 写死 context-chips 移除 | `Composer.tsx` 删除"默认只读调查" chip；`workbench.css` 删除 `.tool-group`/`.context-strip`/`.context-strip__icon` 无用样式，`.composer-tools` 改 `flex-end`；服务上下文由父级真实渲染（会话工具栏「调查目标服务」、欢迎页服务选择器、回答「只读调查」徽标） | PASS |

## 切片 S2：P1-9 + P1-12 回写

| AC（完善清单条目） | 代码/接口/测试证据 | 状态 |
|---|---|---|
| P1-9 注册数=在线数文案修正（"在线"→"已接入"） | `WelcomePanel.tsx` 状态条改 `{n} 个服务已接入 · 默认只读调查`；`WorkbenchPage.ConversationHome` 传 `service_count`（真实 `services_query` 数据长度）。证据：`WelcomePanel.test.tsx`「服务数如实展示已接入」「没有传入服务数时默认 0，不写死 3」、`App.test.tsx`「欢迎页服务数如实展示已接入口径，不再写在线」 | PASS |
| P1-9 硬编码默认值移除 | `WelcomePanel` 默认 `service_count = 3` → `0`（无数据时不再声称 3 个服务） | PASS |
| P1-9 加载/错误态补齐（不冒充 0 个服务） | `WelcomePanel` 新增 `services_loading`/`services_error`：「正在读取已接入服务… / 服务列表暂不可读」+ 选择器空态；`WorkbenchPage.ConversationHome` 传 `services_query.isPending/isError`。证据：`WelcomePanel.test.tsx`「服务列表加载中/失败时如实展示，不冒充 0 个服务」 | PASS |
| P1-9 服务中心"最近同步/刚刚"诚实化 | 现状已是真实 `dataUpdatedAt` 时间戳（`ServiceCenterPage.tsx` `sync_text`：0 → "尚未读取"），统计口径"已注册服务 / N 个已配置快照"；本工作包复核无改动 | PASS |
| P1-12 用户信息占位移除 | "王志海/研发运维团队"在 main 已移除（无登录体系不编造用户），`App.test.tsx`「服务中心列表展示真实服务目录，不伪装成实时监控」断言不存在；Ctrl K 已由 P8 #64 实现（`Sidebar.test.tsx` 交互用例）；浏览器端到端复验按 issue #103 **并入阶段验收**，本次无代码改动 | PASS |

## 验证记录（实测）

| 检查 | 命令（`frontend/` 下） | 结果 |
|---|---|---|
| 类型 | `npm run typecheck` | 通过（无输出错误） |
| 测试 | `npm run test` | **203 passed / 20 files** |
| 构建 | `npm run build` | 成功（132 modules → dist） |
| 门禁 | `git diff --check`（worktree 根） | 干净 |

## 范围核对

- `git status --short` 仅含本工作包文件：`frontend/src/features/shell/{TopBar,Composer,WelcomePanel}.tsx`、
  `frontend/src/features/workbench/WorkbenchPage.tsx`、`frontend/src/styles/{app-shell,workbench}.css`、
  `frontend/src/app/App.test.tsx`、`frontend/src/features/shell/WelcomePanel.test.tsx`、`docs/完善清单.md`、本工作包目录。
- 无后端改动、无迁移、无接口变更、无凭据/敏感内容、无 mock 冒充真实。