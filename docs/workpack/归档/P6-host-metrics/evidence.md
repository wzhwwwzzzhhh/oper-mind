# P6-host-metrics · AC 证据表

> 按切片回写；每个断言必须附测试输出 / 命令结果支撑。审查结论见 `review.md`。

## S1：领域模型 + HostMetricsCollector

验证命令（worktree `backend/`）：
`../.venv/Scripts/python.exe -m pytest tests/test_host_metrics.py tests/test_server_tools.py -q`

结果：`10 passed in 0.12s`（test_host_metrics）、`7 passed`（test_server_tools，随完整套件）

## S2：快照 / API / 迁移 / 采样器

验证命令：
`../.venv/Scripts/python.exe -m pytest tests/test_monitoring.py tests/test_p4_service_center.py tests/test_monitor_history_api.py tests/test_api.py tests/test_p2_api_v1.py tests/test_p43_service_context.py -q`

结果：`31 passed`（S1+S2 组合）、`24 passed`（API 回归）、完整套件 `180 passed, 1 skipped`

迁移验证：`test_p6_主机指标迁移升降级` —— upgrade 增加 host_cpu_percent/host_memory_percent/host_memory_bytes/host_disk_used_percent 四列与 CheckConstraint，downgrade 移除，均通过。

## S3：前端

验证命令（worktree `frontend/`）：
`npm run typecheck` → 通过
`npm run test` → `63 passed`
`npm run build` → 通过
`npx openapi-typescript http://127.0.0.1:8011/openapi.json -o src/api/v1/generated.ts` → generated.ts 含 host_metrics / host_cpu_percent（禁止手工编辑，重新生成）

## 门禁

- `git diff --check` → 干净（仅 generated.ts LF→CRLF 提示，既有行为）
- 未改动工作包外文件（见 `git status`）

## 既有测试修复（非本工作包引入）

- `test_monitoring.py` 的 `_snapshot()` 及 redis 专用测试使用固定时间 `2026-08-05 12:00 UTC`，随真实时钟越过 24h 保留窗口被采样清理逻辑删除 → 时间炸弹。已改为 `datetime.now(timezone.utc)`。此为既有缺陷，非本工作包引入，修复后完整套件 180 passed。

## 逐条 AC 证据

- [ ] AC1 服务详情展示主机当前状态与异常进程 → 见 test_host_metrics（mock 解析）+ ServiceDetailPage.test.tsx `挂载时展示主机当前状态与异常进程` → PASS
- [ ] AC2 psutil 不可用→不可用降级不伪造 → test_host_metrics `test_psutil_import_failure_returns_unavailable` → PASS
- [ ] AC3 采样入历史、趋势可见 → test_monitoring `test_采样器附加主机标量到每个样本` + ServiceDetailPage.test.tsx `历史采样包含主机走势轨道` → PASS
- [ ] AC4 不可用标量 null 不用 0 → test_host_metrics `test_unavailable_never_uses_zero` → PASS
- [ ] AC5 mock 模式返回原 mock 结果 → test_server_tools（7 条 S1–S3 断言）→ PASS
- [ ] AC6 网关脱敏无凭据 → 异常进程仅 name/pid/占用率（HostProcessData 无 cmdline），采样日志仅中文安全摘要 → PASS
- [x] AC7 回归全绿 + 前端三件套 → 完整套件 180 passed + typecheck/test/build → PASS；PRD AC7 文本已更正（`test_server_agent.py` → `test_host_metrics.py` + `test_server_tools.py`，随交付提交）

## 待办

- [x] 独立审查 PASS 后逐切片提交（S1/S2/S3/docs 四提交已入 `feat/P6-host-metrics`）
- [x] 交付时更正 PRD AC7 测试引用
