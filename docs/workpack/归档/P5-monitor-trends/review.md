# P5-monitor-trends · 独立审查

## 审查状态

**PASS**（2026-08-08，独立只读子代理审查通过；此前 tooling_blocked 状态由本次独立复审取代）

## 审查结论

- 未发现 P0 安全红线：样本、API、前端均无 SQL、对象名、DSN、凭据或 `sk-` 内容；采样只调用静态 Connector，纯只读。
- P1 已闭合：首次独立审查发现 AC2 契约破坏——`not_configured` 历史查询返回非空样本。开发方修复 `get_history`，未配置服务现在如实返回 `status=not_configured` + `samples=[]`，并连带修正混合状态无可用样本误标 available 的问题。复审确认修复正确、无回归。
- 前端空态（AC5）补齐真实交互断言："暂无历史采样"诚实空态 + 不绘制假趋势线。
- 既有服务快照接口契约未变，mock 评测（S1–S4）路径未改动。

## AC 证据

| AC | 证据 | 结论 |
|---|---|---|
| AC1 | `backend/tests/test_monitor_history_api.py`；`list_between` 按 `observed_at` 升序；`MonitorSampler.sample_once_async()` | PASS |
| AC2 | `monitoring.py` `get_history`（NOT_CONFIGURED → `samples=()`）；应用层 + HTTP 层测试断言空序列 + not_configured | PASS |
| AC3 | `sample_once_async()` 每服务 3 秒超时；异常收敛为 unavailable；`test_仅有不可用样本返回不可用状态` | PASS |
| AC4 | 按 service_id + 窗口查询；HTTP 层未注册 404、超大窗口 422；响应仅收敛标量 | PASS |
| AC5 | `ServiceDetailPage.tsx` 空态；`App.test.tsx` 断言"暂无历史采样"且无"采样点异常" | PASS |
| AC6 | `ServiceDetailPage.tsx` 异常点判定（慢查询/超时/可用性变化）；`App.test.tsx` 慢查询 3 断言 | PASS |
| AC7 | 页面标注"定时采样 · 每 5 分钟 · 保留最近 24 小时 · 历史记录"，无"实时监控"表述 | PASS |
| AC8 | 后端全量 270 passed、前端 68 passed；既有服务快照契约与 mock 路径不变 | PASS |
| AC9 | 领域模型、API schema 仅收敛标量；无 SQL/对象名/凭据字段 | PASS |

## 遗留观察（不阻塞）

- P3：历史仅含 unavailable 样本时，前端主图对 null 标量渲染最小高度条（tooltip 显示 `—`，不伪造数值）；该行为为预存，非本次修复引入。
- P3：前端趋势标注文案为默认值硬编码，未读取 API 返回的 `sample_interval_seconds`/`retention_hours`（默认配置下字面正确）。
