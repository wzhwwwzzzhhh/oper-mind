# P6-host-metrics · 独立审查

> 审查方式：只读子代理（Explore 类型，与开发视角分离），输入 plan.md / PRD / Design / 基线 / 工作区 diff。

## 结论

**PASS**（无 P0/P1）

## 审查发现与处理

### P2（已修复）

1. **时间预算契约未落实**：`_collect_target_unbounded` 初始 `within_budget()` 检查是死代码，`cpu_percent(interval=1)` 与 `net_connections()` 不受预算约束，超预算返回部分数据而非 Design 要求的 unavailable。
   → 已修复：CPU/内存块后、网络块后、磁盘循环、进程循环均做预算检查，超时抛 `TimeoutError` → 收敛为 unavailable 全空；补 `test_时间预算耗尽返回不可用`。
2. **缺 API 级回归断言**：`/api/v1/services` 与历史接口未断言 host_metrics / host_* 字段透出。
   → 已修复：`test_api.py` 断言服务响应恒携带 `host_metrics`（诚实状态）；`test_monitor_history_api.py` 新增 `test_历史样本携带主机标量`。

### P3（已修复）

3. `frontend/src/api/v1/client.ts` 本地 `MonitorSampleResource` 类型契约缺 4 个主机字段 → 已同步。
4. `_collect_processes` 把可调用参数标为 `object` → 改为 `Callable[[], bool]`。
5. 异步采样路径（`sample_once_async`/`_collect_host_async`，含 3s 超时）无单测 → 新增 `test_异步采样路径附加主机指标`（文件库 SQLite 避免跨线程内存库问题）。

### P3（按决策处理，交付时完成）

6. PRD AC7 引用不存在的 `test_server_agent.py` → 已新增 `test_server_tools.py` 锚定 AC5；**PRD AC7 文本更正在 dev-deliver 阶段随 PRD 状态推进一并完成**（用户确认决策 #6）。

## AC 证据

逐条 AC1–AC7 证据见 `evidence.md`（独立审查子代理逐条核验均为 PASS，含本工作包新增测试与完整套件 180 passed）。

## 遗留事项

- PRD AC7 测试引用更正 → dev-deliver 处理
- 完整套件中 `test_p2_recovery_closure` 偶发时序 flaky（单独运行 2 passed，非本工作包引入）
