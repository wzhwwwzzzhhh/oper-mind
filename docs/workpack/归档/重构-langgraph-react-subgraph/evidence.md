# 重构-langgraph-react-subgraph · 实施证据

> 日期：2026-09-11
> 状态：已完成并归档；全量 884 passed 零回归

## 交付内容

- 新增 `backend/src/core/react_graph.py`（141 行）：
  - LangGraph `StateGraph` ReAct 子图：`model` 节点（一次 LLM 调用）↔ `tools` 节点（ToolGateway 受控执行）+ 条件边终态收敛；
  - 行为契约文案常量（LLM_UNAVAILABLE_TEXT / TOOL_INVOCATION_LIMIT_TEXT / NO_RESPONSE_TEXT）与旧循环逐字一致；
  - 工具调用上限、步数耗尽、长期记忆写入、思考摘要格式、审计记录收集语义全部保持。
- 重写 `backend/src/core/agent.py` `BaseAgent.run`：
  - 删除手搓 for 循环（-61 行），改为 `build_react_graph` + `graph.invoke`；
  - 保留记忆 enrichment、工具菜单按查询裁剪（DBAgent 健康调查覆写）、按工具超时配置；
  - `max_steps<=0` 直接返回步数耗尽文案（旧 for 循环空转语义）；
  - `recursion_limit = max_steps*2+8`（模型↔工具每对消耗 2 个图步）。
- 更新 `backend/src/core/graph.py` 模块注释（"手搓 ReAct"→"ReAct 子图驱动"）。

## 验证证据

| 验证项 | 命令/方式 | 结果 |
|---|---|---|
| 迁移前基线 | `pytest tests -q`（主仓库 venv） | 884 passed, 4:53 |
| 迁移后全量 | 同上 | 884 passed, 4:53（零回归） |
| 聚焦契约 | test_agent_gateway + test_knowledge_agent + p11_tool_connector_safety | 35 passed |
| 内核编排/回归门禁 | runtime_evaluation + p12_postgres_e2e + p2_diagnosis_adapter + p2b_tool_trace + p43_service_context + run_rerun/cancel + regression_baseline | 102 passed |
| 类型检查 | `mypy`（全仓） | Success: no issues found in 120 source files |
| Lint | `ruff check src/core/agent.py src/core/react_graph.py` | All checks passed |
| whitespace | `git diff --check` | 干净 |

## 架构结果

从内核到编排全部运行于 LangGraph：
- `core/graph.py` 多 Agent 编排图（原有，未动）；
- `core/react_graph.py` 领域 Agent ReAct 子图（本次新增）；
- LLMClient（mock 确定性/用量采集/多角色装配）与 ToolGateway（六道关安全边界）刻意保留，理由见 plan.md。

## 未执行项（如实说明）

- LangGraph checkpointer 持久化未引入：Run 状态事实仍由 Run 主脊（RunEvent/RunStatus）承担，子图按 Run 现造即废弃，无跨 Run 状态需求；
- LangGraph `interrupt` 审批未引入：审批闭环已在 Action 主脊（提案→审批→白名单执行）实现，与执行循环解耦；
- 前端零改动。
