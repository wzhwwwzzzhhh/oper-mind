# P5-monitor-trends · AC 证据

## 交付说明

- 功能代码经 PR #13 已合并到 main；本工作包在 `docs/p5-monitor-trends-deliver` 分支补做流程收尾：独立审查发现并修复 AC2 契约问题，补齐前后端测试后复审 PASS，随后完成 PRD 状态推进与工作包归档。

## 测试证据

- 后端全量：`270 passed, 2 skipped`。
- P5 后端聚焦：`test_monitoring.py` + `test_monitor_history_api.py` 共 `18 passed`（含新增未配置/未采样/不可用/混合状态、HTTP 层 200/404/422）。
- 干净 SQLite migration：`upgrade head`、`downgrade 20260802_04_p2_tool_invoked`、再次 `upgrade head` 全部通过。
- 前端 `npm run typecheck`：通过。
- 前端全量测试：`10 files / 68 passed`（含新增"暂无历史采样"诚实空态断言）。
- 前端构建：通过；仅有既有约 913 kB bundle size warning。
- 提交前 `git diff --check`：干净。

## AC 状态

| AC | 状态 | 证据 |
|---|---|---|
| AC1 | PASS | 定时采样、样本表、升序历史查询测试 |
| AC2 | PASS | `get_history` 对未配置返回空序列 + not_configured（P1 修复）；应用层与 HTTP 层测试 |
| AC3 | PASS | 失败隔离、3 秒异步超时、unavailable 状态样本测试 |
| AC4 | PASS | 窗口查询、脱敏 schema、HTTP 404/422 契约测试 |
| AC5 | PASS | 前端"暂无历史采样"诚实空态交互测试 |
| AC6 | PASS | 异常点高亮与摘要前端测试 |
| AC7 | PASS | 历史来源/频率/保留窗口文案 |
| AC8 | PASS | 后端全量回归和前端既有测试 |
| AC9 | PASS | 领域模型与响应字段白名单 |

## 独立审查

- 首轮独立只读子代理审查（2026-08-08）：FAIL——AC2 未配置服务历史查询返回非空样本（P1）。
- 修复 + 补测后复审（2026-08-08）：PASS。结论见 `review.md`。
