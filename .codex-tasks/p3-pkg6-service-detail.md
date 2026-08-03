# 任务 P3-包6：单服务详情页（按设计稿）

## 背景（只读）
按 `frontend/参考原型/mysql-service-detail.html`（设计稿）实现单服务详情页。
已有壳：窄图标导航 + 双模式共用壳（`/workbench` 会话模式，`/services` 运维模式）。
`/services` 已实现服务中心目录（包5）。本任务实现 `/services/:service_id` 详情页。

## 只允许修改/创建这些文件
1. 新建 `frontend/src/features/services/ServiceDetailPage.tsx`
2. 新建 `frontend/src/styles/service-detail.css`
3. 改 `frontend/src/features/services/ServiceCenterPage.tsx`（"查看详情"按钮已跳 `/services/:id`，确认路由）
4. 改 `frontend/src/app/App.tsx`（`/services/:service_id` 路由指向 ServiceDetailPage）
5. 改 `frontend/src/main.tsx`（import 新 css）
6. 改 `frontend/src/app/App.test.tsx`（如有必要）

**严禁触碰其他文件**（不改后端、不改已有壳组件、不改 P2 链路）。

## 设计稿结构 → 组件映射
设计稿页面自上而下：
- 面包屑「服务中心 / 订单 MySQL」
- Hero 区：服务 logo + 名称 + 状态徽章 + 「重新检查 / 发起调查」按钮
- 元信息条：服务状态 / 最近检查 / 数据来源 / 权限边界 / 数据新鲜度
- 状态 notice（运行正常 + 查看检查记录）
- 当前健康概览：4 个指标卡（可用性 / 连接延迟 / 当前连接 / 慢查询）
- 运行趋势 + 当前关注（两栏卡片）
- 服务能力（能力卡网格）
- 最近活动（时间线）
- 服务信息（信息卡网格）

## 数据来源（接真实 API，空则空态）
- `get_service(service_id)` → `ServiceResource`：
  - `title`、`kind`、`supported_investigations`、`action_boundary`、`snapshot`
  - `snapshot`: `observed_at`、`mode`、`availability`、`performance_signal`、`server_metrics`、`database`
- `list_service_activities(service_id)` → 活动列表
- `create_service_session(service_id, {})` → 发起调查（跳会话页）

**真实 API 当前可能返回空/无 snapshot**：页面要如实显示空态/缺省值，
**不得伪造示例指标**（如"99.98% 可用性"）。可用"—"或"暂无数据"占位。

## 必须实现的能力
1. **发起调查**：按钮调 `create_service_session(service_id, {})`，成功跳 `/workbench/sessions/:id?intent=...`
2. **健康概览**：从 snapshot 读 availability/performance_signal/server_metrics（p50_ms/p95_ms/slow_query_count/timeout_count），缺失显示 "—"
3. **能力区**：从 `supported_investigations`/`action_boundary` 渲染能力卡（有→启用，无→未启用），只读展示
4. **面包屑返回**：点「服务中心」回 `/services`

## 设计稿的"假数据"部分（如运行趋势图、慢查询 3 条等示例指标）
**不实现**。真实 API 无此数据时显示空态/缺省，不硬编码示例数值。

## 验收
- `npm run typecheck` 绿
- `npm run test` 全绿
- `npm run build` 绿
- 手动：`/services` 点「查看详情」进入详情页，面包屑返回可用；后端无服务时显示诚实空态
- `git status` 只出现上面允许的文件

## 完成后
**不要 commit。** 停下告诉我"包6完成"，我审 diff + 跑测试后自己提交。
