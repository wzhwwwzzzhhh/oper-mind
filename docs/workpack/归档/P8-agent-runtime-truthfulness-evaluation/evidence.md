# P8-agent-runtime-truthfulness-evaluation · 验证证据

> 状态：实现、全量验证与第三轮独立代码终审完成（PASS，无 P0–P3），随 PR #99 交付归档

## AC 证据

| AC | 状态 | 可追溯证据 |
|---|---|---|
| AC1 | PASS | DB allowlist、显式 DB facts 与任一畸形 schema 整体 fail closed 均有评测覆盖。 |
| AC2 | PASS | Server/Log/Knowledge 角色菜单互斥；Knowledge 使用临时受管目录正向命中并保留安全标题。 |
| AC3 | PASS | 结论绑定角色、工具、场景和输出类别，统一标注“模拟场景证据来源”；跨角色证据可区分。 |
| AC4 | PASS | S2 无 DB 事实返回“未提供”；无适用 direct 不发 `agent_start/tool_invoked`；混合菜单失败关闭。 |
| AC5 | PASS | actual Debate 的 DB/Server Agent 先经真实 ToolGateway 生成审计记录，再按本轮冲突证据确定性执行。 |
| AC6 | PASS | direct/chain、证据不足、无证据 Reflection 均为 skipped；修订上限 failed；Knowledge 未配置为 unavailable。 |
| AC7 | PASS | Server 依赖缺失和采集异常单测均返回结构化 `unavailable`，固定 CPU 等回退已删除。 |
| AC8 | PASS | 四 direct、chain、parallel、无匹配、rejected/unavailable、actual Debate 及 S1–S4 双跑快照均机器判定。 |
| AC9 | PASS | 负向门禁自动识别跨角色、未标注 mock、false success、敏感泄漏及 `check_cpu`→磁盘错配（含混合声明）。 |
| AC10 | PASS | query、SQL、Windows/Unix/root/引号路径、DSN、Key、traceback、规范 JSON 工具实参均被安全投影拦截。 |
| AC11 | PASS | 后端 605 passed；Ruff/Mypy、前端 197 passed/typecheck/build 全部通过。 |
| AC12 | PASS | `docs/完善清单.md` P0-3/P1-2/P2-1 与 `docs/跑通验证.md` C3 已在第三轮终审 PASS 后按实收口。 |
| AC13 | PASS | `git diff` 确认无公开 API/OpenAPI、迁移、Connector、服务类型或高风险动作改动；仅本地 loopback mock UI 验证。 |

## 自动化结果

- 后端行为评测：首轮整改后 **27 passed**；第二轮整改后 `pytest tests/test_agent_runtime_evaluation.py -q` → **29 passed**。
- Server/Gateway：`pytest tests/test_server_tools.py tests/test_tool_gateway.py -q` → **20 passed**。
- 事件投影：`pytest tests/test_p2b_tool_trace.py tests/test_p2_diagnosis_adapter.py -q` → **8 passed**。
- 后端全量：第二轮整改后 `pytest tests -q` → **605 passed, 2 warnings**（2026-08-23，230.59s）。
- 静态检查：`ruff check ...` → **All checks passed**；`mypy src` → **Success: no issues found in 113 source files**。
- 前端：TraceCard 聚焦 **8 passed**；`npm run typecheck` PASS；`npm run test` → **197 passed / 20 files**；`npm run build` PASS。
- `git diff --check` PASS（Windows LF→CRLF 提示不构成错误）。

## 浏览器全链

- 先侦察到常驻 5174/8000 服务污染，最终使用隔离端口：后端 `8020`、Vite `5194`，显式注入 mock 模式。
- 仅在本地应用库登记 `127.0.0.1:1` 测试服务，未访问真实外部资源；执行“全面体检数据库并定位故障”。
- Playwright/Edge headless 断言通过：TraceCard 显示 9 个事件、3 个工具调用、1 个阶段未执行；报告明确显示“模拟场景证据来源”；辩论未执行且未误报“工具调用全部通过”；无 page error。
- 截图（本地忽略资产）：`.tmp/issue98-tracecard.png`。

## 范围核对

- 未修改 `frontend/src/api/v1/generated.ts`，无需 OpenAPI 生成。
- 未新增迁移、ORM 字段、公开端点、Connector、Agent、真实资源访问、配置项或高风险动作。
- `.venv/`、`frontend/node_modules/`、`data/opermind.sqlite3` 与浏览器脚本/截图均为 worktree 内 Git 忽略的本地验证资产，不进入提交。
