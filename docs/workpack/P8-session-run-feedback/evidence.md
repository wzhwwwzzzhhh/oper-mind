# Issue #102 会话回答与运行反馈 · 验收证据

> 更新：2026-08-27
> 当前结论：实现、自动化与浏览器复验全部 PASS。

## 验收项

| 验收项 | 结果 | 证据 |
|---|---|---|
| 发送即回显且不冒充已保存 | PASS | `App.test.tsx`：普通消息与调查请求在响应前显示“用户问题（待确认）”；权威 user message id 出现后临时卡片消失且内容只出现一次 |
| 发送按钮 loading 与防重复 | PASS | mutation pending 时按钮切换为可访问名称“正在发送”、spinner 可见、textarea 与按钮禁用 |
| queued/running 阶段气泡 | PASS | 参数化测试分别断言“请求已受理，正在准备调查 / 尚未产生调查结论”和“正在执行只读调查 / Trace 中更新” |
| 创建会话 spinner 与防重复 | PASS | 延迟 POST 测试确认创建进度、快捷卡、Composer 与服务选择同步禁用 |
| 前端 typecheck/test/build | PASS | 21 files / 217 tests；`tsc --noEmit` PASS；Vite build PASS，仅既有 chunk-size warning |
| 浏览器交互与视觉复验 | PASS | 原生 Python Playwright + Chromium headless；mock API 8122、Vite 5192；创建 spinner、pending 卡片、发送 loading、queued 气泡断言通过；JS console error/pageerror 为 0 |

## 浏览器限制与目检

- 仓库 mock API 不提供创建会话 POST，也不会把新受理 Run 的 user message加入消息列表，因此浏览器脚本只在延迟窗口验证创建 spinner；Run 受理后临时卡片诚实保持“已受理，待恢复”。
- 3 个 mock 辅助资源 404 单独记为 `mock_resource_errors`，未当作产品 JavaScript 错误；生产契约形态由 MSW 交互测试覆盖。
- 1440×1100 全页及元素局部截图目检：spinner、虚线临时态、queued 进度卡无重叠、截断或横向溢出；临时文件已清理。
