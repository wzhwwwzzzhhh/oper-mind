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
from src.config import load_config
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
    """把 ShowIndexTool 包装成 LangChain 可调用的函数"""
    tool = ShowIndexTool()

    def show_index_wrapper(table: str) -> str:
        return tool.execute(table=table)

    return show_index_wrapper


def create_show_create_table_tool():
    """把 ShowCreateTableTool 包装成 LangChain 可调用的函数"""
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

_config = load_config()["llm"]
llm = ChatOpenAI(
    model=_config.get("model", "deepseek-chat"),
    api_key=_config["api_key"],
    base_url=_config["base_url"],
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
    final_answer = "Agent 未生成有效回答"
    for output in app.stream(initial_state):
        node_name = list(output.keys())[0]
        print(f"\n[节点: {node_name}]")
        if node_name == "llm":
            msg = output[node_name]["messages"][-1]
            if msg.content:
                final_answer = msg.content

    return final_answer


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
