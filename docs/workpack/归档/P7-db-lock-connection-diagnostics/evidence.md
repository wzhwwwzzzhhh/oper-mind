# P7-db-lock-connection-diagnostics · AC 证据

> PRD：`docs/prd/session/P7-db-lock-connection-diagnostics.md`
> Design：`docs/design/session/P7DB锁与连接池诊断Design.md`
> 切片：S1 两个只读工具真实分支与降级 / S2 mock 分支与审计摘要及注册（已合并为一个提交批次）

## 验证记录

- 聚焦：`pytest tests/test_db_lock_pool_tools.py -q` → 23 passed
- 回归子集：`pytest tests/test_db_tools_real.py tests/test_tool_gateway.py tests/test_agent_gateway.py tests/test_p2b_tool_trace.py -q` → 全绿
- 全量：`pytest tests -q` → 297 passed, 2 skipped
- `git diff --check`：干净
- 无前端改动（`typecheck`/`test`/`build` 不适用）

## AC 证据表

| AC | 证据 | PASS/FAIL |
|---|---|---|
| AC1 锁诊断返回结构化事实 / 无锁等待诚实 | `test_db_lock_pool_tools.py::test锁诊断识别阻塞链并脱敏`、`test锁诊断无锁等待返回诚实状态` | ✅ |
| AC2 阻塞链识别且不含用户名/IP/原始 SQL | `test锁诊断识别阻塞链并脱敏`（`pg_blocking_pids` 子查询，输出白名单字段） | ✅ |
| AC3 连接池统计与健康档位 | `test连接池统计与健康档位`、`test连接池已耗尽标注`、`test连接池正常档位` | ✅ |
| AC4 mock 模式行为不变、确定性 | `test_mock模式锁诊断返回无锁等待`、`test_mock模式连接池返回确定性占用`、`test_mock模式S4连接池已耗尽`；`data/scenarios.py`/`data/mock_db.py` 零改动 | ✅ |
| AC5 纯只读不执行 DML/DDL/不杀锁 | `test真实分支只发SELECT且无terminate`、`test连接池查询只读且全参数化`（`SET TRANSACTION READ ONLY`） | ✅ |
| AC6 脱敏兜底不含用户名/IP/SQL/DSN/凭据 | `test锁诊断连接失败返回不可用且不泄露异常`、`test网关白名单准入新工具`；`ToolGateway.desensitize()` 兜底 | ✅ |
| AC7 未配置/超时/失败诚实降级不抛异常 | `test锁诊断无DSN返回未配置`、`test连接池无DSN返回未配置`、`test锁诊断连接失败返回不可用且不泄露异常`、`test连接池连接失败返回不可用` | ✅ |
| AC8 网关白名单准入 + Trace 仅脱敏摘要 | `test网关白名单准入新工具`、`test网关拒绝未注册工具`、`test审计摘要为脱敏收敛摘要`（`audit_summary` 收敛） | ✅ |
| AC9 回归无新公开 API/迁移/凭据/配置 | 全量 `pytest tests -q` 297 passed/2 skipped；`git diff --check` 干净；前端零改动；未改 mock 数据源 | ✅ |

## 提交

- `feat: P7 锁与连接池只读诊断工具（含 mock 分支/审计摘要/注册）`
