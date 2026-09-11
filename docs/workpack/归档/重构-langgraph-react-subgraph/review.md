# 重构-langgraph-react-subgraph · 审查证据

> 日期：2026-09-11
> 审查方式：契约清单核对 + 全量回归（用户直给模式，以零回归为审查主闸）

## 契约保持核对（迁移前逐一确认，迁移后全量验证）

| 契约 | 锚定测试 | 结果 |
|---|---|---|
| 终态文案逐字一致（LLM 不可用/工具上限/步数耗尽/无响应） | test_p12_postgres_end_to_end.py::test_postgres_health_query_executes_at_most_one_tool_call 等 | PASS |
| 工具调用全部经 ToolGateway（禁止 .execute 直调） | test_harness_regression_baseline.py AST 门禁 | PASS |
| `src.core.agent.ToolGateway` 可 monkeypatch 替换 | test_harness_p11_tool_connector_safety.py::test_迟到Tool结果不进入Agent记忆结果或公开Trace | PASS |
| 迟到工具结果不进入记忆/结果/Trace | 同上（含 release 前后快照一致断言） | PASS |
| 脱敏输出喂给 LLM | test_agent_gateway.py::test_agent_feeds_desensitized_tool_result_to_llm | PASS |
| 工具审计记录按 run 重置收集 | test_agent_gateway.py（连续 run 断言） | PASS |
| thinking 格式 `Step N: 工具 X 状态=Y` | 评测矩阵（test_agent_runtime_evaluation.py） | PASS |
| mock 确定性路由/证据/辩论/反思链路 | test_agent_runtime_evaluation.py 全套 | PASS |
| 工具上限只接纳一次调用（重复 tool_calls 场景） | test_p12_postgres_end_to_end.py（_RepeatHealthCallsDriver） | PASS |
| recursion_limit 放宽支持任意 max_steps | new：agent.run 内 max_steps*2+8 | PASS（全量内验证） |

## 验证结果

| 项目 | 迁移前基线 | 迁移后 | 结果 |
|---|---|---|---|
| 全量 pytest | 884 passed (4:53) | 884 passed (4:53) | 零回归 PASS |
| mypy（120 文件） | Success | Success: no issues | PASS |
| ruff check（新改文件） | — | All checks passed | PASS |
| git diff --check | — | 干净 | PASS |

## 审查结论

**PASS** —— 行为契约零漂移，安全边界（ToolGateway 六道关）未动，全量测试与静态检查全绿。
