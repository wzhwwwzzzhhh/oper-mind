# 重构-langgraph-react-subgraph · 实施计划

> 日期：2026-09-11
> 模式：用户直给（无 issue/PRD）；用户明确要求跳过常规工作流，方案简述后直接实施。

## 背景与决策

用户判断自研 agent harness 维护成本过高，要求把执行内核换成开源框架 LangGraph。

侦察结论：项目编排层（`core/graph.py` 路由→领域Agent→Debate→Report→Reflection）
**已经是 LangGraph StateGraph**（requirements 已锁 langgraph==1.2.9）。真正的自研
部分只剩领域 Agent 内的手搓 ReAct 循环（`core/agent.py` BaseAgent.run 的 for 循环）。

因此本次迁移实质 = 把最后一块手搓循环替换为 LangGraph 子图。

## 方案（简版）

| 部分 | 处置 |
|---|---|
| `BaseAgent` 手搓 ReAct 循环 | 删除，换 LangGraph StateGraph ReAct 子图 |
| 编排图 `core/graph.py` | 已是 LangGraph，不动 |
| `LLMClient` | 保留（mock 确定性/用量落库/多角色装配锚点） |
| `ToolGateway` 六道关 | 保留（CLAUDE.md 安全边界 + 回归门禁锁定） |
| 事件落库/SSE/审批/rerun/cancel | 不动（Run 主脊，与循环解耦） |

行为契约逐字保留：终态文案（LLM 不可用/工具上限/步数耗尽/无响应）、
`Step N: 工具 X 状态=Y` 思考格式、工具审计收集、短期记忆裁剪语义、
`src.core.agent.ToolGateway` 可替换性（p11 monkeypatch 契约）、
`.execute` 直调门禁、`max_steps<=0` 语义、recursion_limit 放宽。

## 改动清单

- 新增 `backend/src/core/react_graph.py`：model↔tools 两节点 StateGraph 子图
- 重写 `backend/src/core/agent.py` run()：删除手搓循环，改为 build_react_graph + graph.invoke
- 更新 `backend/src/core/graph.py` 模块注释（过时描述）

## 验证计划

1. 迁移前基线：全量 pytest（884 passed 基准）
2. 迁移后全量 pytest 必须 884 passed 零回归
3. mypy 全量通过；ruff check 新改文件通过；`git diff --check` 干净
