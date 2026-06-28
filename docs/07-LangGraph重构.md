# 07 LangGraph 重构

---

## 目标

用 LangGraph 重写 ReAct 循环，理解框架解决了什么问题。

---

## 前置依赖

- [ ] 03-手搓ReAct核心引擎完成（理解本质后再学框架，才不会变成调包侠）

---

## 知识点：为什么学 LangGraph？

你手搓的 ReAct 是硬编码的 `while` 循环：

```python
# 你自己的实现
for step in range(max_steps):
    response = llm.chat(messages)
    if tool_calls:
        execute_and_loop()
    else:
        return answer
```

LangGraph 把这个循环变成了**图**，好处是：

| 你手搓的版本               | LangGraph 版本 |
| -------------------- | ------------ |
| 循环是隐式的（代码里写死的 while） | 循环是显式的（图的边）  |
| 加条件分支要改代码            | 加条件分支是加一条边   |
| 状态管理要自己维护 messages   | 框架帮你管理 State |
| 只能顺序执行               | 可以并行节点、复杂路由  |

**但核心逻辑完全一样。** 你手搓的版本理解了本质，现在用 LangGraph 是"我知道它为什么这么设计"。

---

## 步骤

### 1. 概念理解：LangGraph 的核心概念

```
State（状态）
  ↓
Node（节点）→ 执行逻辑，返回更新后的 State
  ↓
Edge（边）→ 从一个节点到另一个节点
  ↓
Conditional Edge（条件边）→ 根据 State 决定下一个节点
```

你的 ReAct 循环对应成图：

```
                ┌──────────────┐
                │  call_llm    │  ← 节点1：调 LLM
                └──────┬───────┘
                       │
              ┌────────┴────────┐
              │                 │
        has_tool_call?     has_answer?
              │                 │
              ↓                 │
        ┌──────────────┐       │
        │ execute_tool  │       │  ← 节点2：执行工具
        └──────┬───────┘       │
               │               │
               └───────────────┘
                       ↓
                ┌──────────────┐
                │   返回结果     │
                └──────────────┘
```

### 2. 安装 LangGraph

确保已安装（在 `requirements.txt` 中已有）：

```bash
pip install langgraph langchain-openai
```

### 3. 用 LangGraph 重写 Agent

文件：`src/agent_langgraph.py`

```python
"""
LangGraph 版 Agent。
和手搓版跑同样的逻辑，但用图来表达。
"""

import json
from typing import Literal
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from src.core.tool_registry import ToolRegistry
from src.scenarios.db_diagnosis import SYSTEM_PROMPT
from src.tools.db_tools import ExplainTool, ShowIndexTool, ShowCreateTableTool
from data.mock_db import explain_sql, extract_table_name


# ===== 1. 定义 State =====

class AgentState(TypedDict):
    """Agent 的状态，在节点之间传递"""
    messages: list      # 对话历史
    next_step: str      # 下一步要做什么


# ===== 2. 初始化工具和 LLM =====

tools_registry = ToolRegistry()
tools_registry.register(ExplainTool())
tools_registry.register(ShowIndexTool())
tools_registry.register(ShowCreateTableTool())

# 把 Tool 转为 LangChain 格式
langchain_tools = []


def create_explain_tool():
    """把 ExplainTool 包装成 LangChain 可调用的函数"""
    tool = ExplainTool()

    def explain_sql_wrapper(sql: str) -> str:
        return tool.execute(sql=sql)

    return explain_sql_wrapper


def create_show_index_tool():
    tool = ShowIndexTool()

    def show_index_wrapper(table: str) -> str:
        return tool.execute(table=table)

    return show_index_wrapper


def create_show_create_table_tool():
    tool = ShowCreateTableTool()

    def show_create_table_wrapper(table: str) -> str:
        return tool.execute(table=table)

    return show_create_table_wrapper


# 注册到 LangChain
from langchain_core.tools import tool


@tool
def explain_sql_tool(sql: str) -> str:
    """执行 EXPLAIN 分析 SQL 的执行计划，返回访问类型、扫描行数、索引使用情况"""
    return ExplainTool().execute(sql=sql)


@tool
def show_index_tool(table: str) -> str:
    """查询指定表的索引信息"""
    return ShowIndexTool().execute(table=table)


@tool
def show_create_table_tool(table: str) -> str:
    """查看表的建表语句"""
    return ShowCreateTableTool().execute(table=table)


tools = [explain_sql_tool, show_index_tool, show_create_table_tool]

llm = ChatOpenAI(
    model="deepseek-chat",
    api_key="YOUR_API_KEY",  # 改成你的 key 或 "mock"
    base_url="https://api.deepseek.com/v1",
    temperature=0.1,
).bind_tools(tools)


# ===== 3. 定义节点函数 =====

def call_llm(state: AgentState) -> AgentState:
    """节点1：调用 LLM"""
    messages = state["messages"]
    response = llm.invoke(messages)
    messages.append(response)
    return {"messages": messages}


def execute_tool(state: AgentState) -> AgentState:
    """节点2：执行工具调用"""
    messages = state["messages"]
    last_message = messages[-1]

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_call_id = tool_call["id"]

        print(f"  → 调用工具: {tool_name}({json.dumps(tool_args, ensure_ascii=False)})")

        # 查找并执行工具
        result = ""
        for t in tools:
            if t.name == tool_name:
                result = t.invoke(tool_args)
                break

        print(f"  ← 结果: {str(result)[:100]}...")

        messages.append(ToolMessage(content=str(result), tool_call_id=tool_call_id))

    return {"messages": messages}


# ===== 4. 定义路由函数（条件边） =====

def should_continue(state: AgentState) -> Literal["tools", END]:
    """
    根据 LLM 的返回决定下一步。
    - 如果 LLM 调用了工具 → 去 tools 节点
    - 如果 LLM 直接回答了 → 结束
    """
    messages = state["messages"]
    last_message = messages[-1]

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"

    return END


# ===== 5. 构建图 =====

def build_langgraph_agent():
    """构建 LangGraph Agent"""

    # 创建图，指定 State 的类型
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("llm", call_llm)
    workflow.add_node("tools", execute_tool)

    # 设置入口节点
    workflow.set_entry_point("llm")

    # 添加条件边
    workflow.add_conditional_edges(
        "llm",
        should_continue,
        {
            "tools": "tools",  # 有工具调用 → 去 tools 节点
            END: END,          # 有答案 → 结束
        },
    )

    # tools 节点执行完后回到 llm
    workflow.add_edge("tools", "llm")

    # 编译图
    app = workflow.compile()
    return app


# ===== 6. 运行入口 =====

def run_langgraph_agent(user_input: str) -> str:
    """运行 LangGraph Agent"""

    app = build_langgraph_agent()

    # 初始化状态
    initial_state = {
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_input),
        ]
    }

    print(f"\n{'='*50}")
    print("LangGraph Agent 启动")
    print(f"{'='*50}\n")

    # 执行图
    for output in app.stream(initial_state):
        node_name = list(output.keys())[0]
        print(f"\n[节点: {node_name}]")
        if node_name == "llm":
            msg = output[node_name]["messages"][-1]
            if msg.content:
                # LLM 给出了最终回答
                return msg.content

    # 获取最终结果
    final_state = app.get_state(AgentState(messages=initial_state["messages"]))
    for msg in reversed(final_state.values.get("messages", [])):
        if hasattr(msg, "content") and msg.content:
            return msg.content

    return "Agent 未生成有效回答"


# ===== 7. CLI 入口 =====

if __name__ == "__main__":
    print("LangGraph 版数据库诊断 Agent")
    print("输入 SQL 进行分析，输入 'exit' 退出\n")

    while True:
        user_input = input("> ").strip()
        if user_input.lower() in ("exit", "quit", "q"):
            break

        result = run_langgraph_agent(user_input)
        print(f"\n{result}\n")
```

### 4. 运行比较

```bash
# 运行手搓版
python src/main.py
> SELECT * FROM orders WHERE status = 'PENDING'

# 运行 LangGraph 版
python src/agent_langgraph.py
> SELECT * FROM orders WHERE status = 'PENDING'
```

**看看两个版本的输出是不是一样？** 如果逻辑正确，诊断结果应该是一致的。

---

## 手搓 vs LangGraph 对比

| 维度   | 手搓版            | LangGraph 版 |
| ---- | -------------- | ----------- |
| 代码量  | ~60行核心逻辑       | ~120行       |
| 理解难度 | 容易，一个 while 循环 | 需要理解图概念     |
| 灵活度  | 改逻辑要改 while 体  | 加节点加边即可     |
| 调试难度 | 容易，print 就行    | 需要理解状态流转    |
| 生产适用 | 小场景够用          | 复杂场景推荐      |

**面试时怎么说：**

> "我一开始手写了 ReAct 循环，理解了本质后再用 LangGraph 重写。LangGraph 把显式的 while 循环变成了图的边和节点，优势在于复杂路由场景更容易扩展。但如果只是简单的 ReAct，手写反而更轻量可控。"

---

## 验收标准

- [ ] `python src/agent_langgraph.py` 能启动
- [ ] 输入慢 SQL，LLM 能正确调工具
- [ ] Agent 最终输出诊断结论
- [ ] 诊断逻辑和手搓版一致

---

## Git 提交

```bash
git add .
git commit -m "refactor: 用LangGraph重写ReAct引擎"
```

---

## 你会用到的知识点

| 概念               | 说明                       |
| ---------------- | ------------------------ |
| StateGraph       | LangGraph 的核心，定义状态和流转    |
| Node             | 一个执行单元（调 LLM / 执行工具）     |
| Edge             | 节点之间的连接                  |
| Conditional Edge | 根据状态决定走向哪个节点             |
| bind_tools       | LangChain 把工具绑定到 LLM 的方式 |
| ToolMessage      | 工具执行结果的消息类型              |

---

## 下阶段预告

下一阶段：用 FastAPI 包装 Agent，提供 HTTP API 接口。
