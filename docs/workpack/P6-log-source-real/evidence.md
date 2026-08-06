# P6-log-source-real · AC 证据表

> 基线：`main`（`0f532ab`）→ `feat/P6-log-source-real`（worktree `D:/market-handsome/oper-mind-worktrees/P6-log-source-real`）
> 关联 PRD：`docs/prd/session/P6-log-source-real.md`（进行中）；Design：`docs/design/session/P6日志真实源接入Design.md`（已确认）

## 验收标准（AC1–AC7）

| AC | 验收标准 | 证据（测试/验证记录） | 状态 |
|---|---|---|---|
| AC1 | 真实模式 `search_logs` 等返回真实日志源只读检索结果 | `test_log_tools_real.py::TestRealModeSearch::test_returns_real_results`、`test_no_match`、`test_time_range_filter_applied`；`test_log_source.py::TestSearch` | ✅ |
| AC2 | 日志源未配置 → 「未配置」降级 | `test_log_tools_real.py::TestRealModeDegradation::test_not_configured`、`test_all_three_tools_degrade_consistently`；`test_log_source.py::TestLogSourceDegradation::test_not_configured_when_dir_none` | ✅ |
| AC3 | 连接失败/超时 → 「不可用」，不泄露异常详情 | `test_log_tools_real.py::test_unavailable_when_dir_missing`；`test_log_source.py::test_unavailable_when_dir_missing`、`test_unavailable_when_dir_is_file` | ✅ |
| AC4 | mock 模式（S1）行为与改动前一致 | `test_log_tools_real.py::TestMockRegression::test_search_logs_s1_exact`（精确串）、`test_aggregate_errors_s1`、`test_slow_query_s1` | ✅ |
| AC5 | 结果无凭据/DSN/sk-/原始异常；日志行脱敏后进入上下文 | 凭据/隐藏/越界文件排除：`test_log_source.py::TestExclusionAndEscape`（含动态构造 sk- 的 `.env` 排除）；网关 `desensitize` 兜底沿用 `tool_gateway.py`；`test_log_tools_real.py::TestRealModeSearch::test_returns_real_results`（真实分支不含 mock/凭据内容） | ✅ |
| AC6 | 网关限时（3s）与脱敏兜底；Trace 只展示工具名/状态/耗时/脱敏摘要 | 网关限时+脱敏沿用 `tool_gateway.py`（六道关）；工具 `audit_summary()` 供 Trace：`test_log_tools_real.py::TestAuditSummary`；事件 detail 截 280 字符沿用 `coordinator_executor.py` | ✅ |
| AC7 | 回归 `test_agent_gateway.py`、`test_diagnosis.py`、`test_tool_gateway.py` 全绿 | `pytest tests/test_agent_gateway.py tests/test_diagnosis.py tests/test_tool_gateway.py tests/test_api.py tests/test_knowledge_agent.py -q` → **28 passed** | ✅ |

## 切片提交记录

| 切片 | 提交 | 验证 |
|---|---|---|
| S1 | `21f9b0e` feat: 增加日志真实源只读 Connector 与配置 | `pytest tests/test_log_source.py -q` → **16 passed, 1 skipped**（符号链接用例因 Windows 无权限跳过） |
| S2 | 待提交 | `pytest tests/test_log_tools_real.py -q` → **15 passed**；AC7 回归 **28 passed** |

## 验证记录

- 全量后端：`pytest tests -q` → **183 passed, 2 skipped, 3 failed**；其中 3 个失败均在 `tests/test_monitoring.py`（监控采样持久化），**经 stash 到基线 `main`（0f532ab）复跑确认是既有失败，与本工作包无关**（`test_monitoring.py` 不引用任何本工作包改动模块）。
- `git diff --check` 干净；敏感字面量扫描无 `sk-`/凭据/DSN 实际值。
- 前端无改动（无 typecheck/build 门禁；PRD「不新增前端页面」）。
