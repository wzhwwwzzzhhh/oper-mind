# P6-log-source-real · 独立审查

> 审查者：独立只读子代理（Explore，写审分离）；被审对象：`git diff 0f532ab..HEAD`（ceefbee / 21f9b0e / f1cec9a）

## 总体：PASS

无 P0/P1。安全红线逐条核验通过：凭据仅环境变量零落库；Connector 纯只读（仅 `open("r")`）；路径逃逸拦截（`resolve().relative_to(root)` 根前缀校验，对齐 `knowledge_tools.py:138-143`）；检索词不拼接入任意路径；无裸 except、无新增生产 print；Tool 均继承 `Tool` 且经网关受控 execute；mock 数据源零改动、真实分支绝不返回 mock 内容。

真实模式判定 `get_active_scenario() is not None` 与 `db_tools.py:132/173/232` 同构自洽；mock 分支与基线逐字一致（S1–S4 确定性不受影响）。

## 发现（P0–P3）

- [P2] `_MAX_FILE_CHARS` 为死代码：`_scan_lines` 只按累计行数截断，单行超长日志会被整行读入内存。→ **已修复**：改为 `_MAX_LINE_CHARS = 8192`，`_scan_lines` 超长行截断，文档与实现一致。
- [P2] mock 分支不更新 `_last_summary`，mock 模式 Trace 的 audit_summary 恒为「日志分析未执行」。→ **已修复**：三个 `_mock_*` 分支回写脱敏摘要（仅 Trace 元数据，不改工具输出文案）。
- [P3] 时间范围用本地 naive `datetime.now()` 与日志行 naive 时间戳比较，跨时区有偏差。→ 保留为已确认设计行为（行级文本检索 + 相对时间窗口），在证据中注明限制。
- [P3] evidence.md S2 状态「待提交」已过时；workpack README 登记状态与 plan 确认不符。→ **已修复**：evidence 回填提交号；README 状态更新。
- [P3] mock 回归仅精确锁定 S1（search_logs 精确串）。→ 保留：mock 分支代码与基线逐字一致（仅引号风格与 `[:10]`→`[:10]` 等价改写），S2–S4 风险低。

## AC 证据（审查者独立核对）

| AC | 结论 |
|---|---|
| AC1 真实日志源只读检索结果 | PASS（`TestRealModeSearch` / `TestSearch` + 真实分支） |
| AC2 未配置降级 | PASS（`TestRealModeDegradation::test_not_configured` 等） |
| AC3 不可用降级、不泄露异常 | PASS（`test_unavailable_*` + `_resolve_root` 收敛） |
| AC4 mock 行为不变 | PASS（`test_search_logs_s1_exact` 精确串 + mock 分支逐字一致） |
| AC5 无凭据/DSN/sk-/原始异常 | PASS（`TestExclusionAndEscape` + 网关 `desensitize` 兜底） |
| AC6 网关限时/脱敏兜底、Trace 脱敏摘要 | PASS（`TestAuditSummary` + `audit_summary()` + 事件 detail 截 280） |
| AC7 回归三件套全绿 | PASS（evidence 自报 28 passed；回归测试不引用本工作包模块） |

## 附注

- 审查为只读，未独立复跑 pytest；AC7 为 evidence.md 自报。主 agent 已在修复后复跑：`test_log_source` + `test_log_tools_real` + `test_log_event_service_id` → **37 passed, 1 skipped**；AC7 回归（agent_gateway/diagnosis/tool_gateway/api/knowledge_agent）→ **28 passed**。
- `tests/test_monitoring.py` 3 个失败经 stash 到基线 `main`（0f532ab）复跑确认为既有失败，与本工作包无关。
