# P7-monitoring-overview · AC 验收证据

> PRD：`docs/prd/monitor/P7-monitoring-overview-page.md`（issue #45，status 进行中）
> Design：`docs/design/monitor/P7服务监控概览页Design.md`（已确认）
> 分支：`feat/P7-monitoring-overview`

## AC 证据表

| AC | 结论 | 证据 |
|---|---|---|
| AC1 概览展示全部已注册服务，无遗漏、无未注册混入 | PASS | `MonitorOverviewApplicationService.get_overview()` 遍历 `registry.list_connectors()`；单测 `test_概览返回全部注册服务且按注册顺序`；API 测试 `test_概览接口返回全部服务与诚实状态` 断言 items 顺序 |
| AC2 最新快照标量（availability/p50/p95/慢查询/超时），数据来自只读快照/采样不伪造 | PASS | `latest_sample` 取窗口内原始最新样本，null 保持 null；单测 `test_概览展示最新样本标量`；应用服务仅调 `list_between()`，`_StubConnector.health_snapshot` 抛 AssertionError 锁定不触发目标连接 |
| AC3 有历史样本显示趋势摘要与异常计数；无样本显示"暂无历史采样" | PASS | `trend_summary`（sample_count/anomaly_sample_count）；not_sampled → latest_sample=None + availability=unavailable；单测 `test_无样本返回未采样诚实空态` |
| AC4 未配置/不可用如实；单服务失败不影响其他服务 | PASS | 状态判定（not_configured/unavailable）；`get_overview()` 逐服务异常隔离降级为 unavailable；单测 `test_未配置服务显示未配置`、`test_不可用服务显示不可用`、`test_单服务失败不影响其他服务`（真实模拟失败） |
| AC5 标注"定时采样 · 每 5 分钟 · 保留最近 24 小时 · 历史记录"，无"实时监控" | PASS | 前端诚实条读取响应 `sample_interval_seconds`/`retention_hours` 动态渲染；测试 `test_诚实标注数据来源且不含"实时监控"表述` |
| AC6 异常标记为"采样点异常"而非"正在告警" | PASS | 计数规则与 P5 一致（PG slow_query/timeout、Redis slowlog、availability 变化含恢复）；badge"采样点异常"；页面注明"不代表外部通知已触发"；测试 `test_异常采样点标记为"采样点异常"而非告警` |
| AC7 概览每行可进入 `/services/:id` | PASS | `navigate(\`/services/${encodeURIComponent(item.service_id)}\`)`；测试 `test_概览行可进入对应服务详情页` |
| AC8 只返回脱敏标量，不含 SQL/对象名/用户名/IP/凭据 | PASS | resource mapper 显式字段收敛；API 测试 `test_概览接口脱敏不泄露敏感字段`（password/DSN/sk-/sql=/SELECT/username 扫描） |
| AC9 概览接口请求失败页面显示失败空态并可重试 | PASS | `overview_query.isError` 渲染失败空态 + 重试按钮；测试 `test_概览接口失败时显示失败空态并可重试`（MSW 500） |
| AC10 回归——mock（S1–S4）不受影响、既有契约不变、测试全绿 | PASS | `data/mock_db.py`/`data/scenarios.py` 未改；`GET /services`、`GET /services/{id}/monitor/history` 契约未改；后端 287 passed；前端 typecheck/test/build 全绿 |

## 验证记录（2026-08-08）

- 后端：`..\.venv\Scripts\python.exe -m pytest tests -q` → **287 passed, 2 skipped**（合 main 后 **332 passed, 2 skipped**）
- 后端聚焦：`..\.venv\Scripts\python.exe -m pytest tests/test_monitor_overview.py tests/test_monitor_overview_api.py -q` → **12 passed**
- 前端：`npm run typecheck` ✓、`npm run test` → **79 passed**（合 main 后 **84 passed**）、`npm run build` ✓
- 门禁：`git diff --check` 干净（仅 LF/CRLF 警告）
- 覆盖超时路径：`test_概览接口读库超时返回内部错误`（`OVERVIEW_READ_TIMEOUT_SECONDS` 3s，测试注入 0.05s 验证 500）
- **合 main**：`git merge origin/main`（P7 #43/#44 已交付）在 resources.py / prd README / App.tsx /
  GlobalNav / ServiceContextNav 解冲突，合并后回归全绿。

## 交付时复核

- [ ] `git status` 只出现本 PRD/工作包允许的文件
- [ ] 未新增持久化/数据库迁移/凭据；未打印/记录 DSN
- [ ] 页面标注历史记录来源与保留窗口，无"实时监控"表述（有测试锁定）
