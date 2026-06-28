"""FastAPI 包装：把 Agent 变成 HTTP API"""

import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.core.llm import LLMClient
from src.core.tool_registry import ToolRegistry
from src.core.agent import Agent
from src.tools.db_tools import ExplainTool, ShowIndexTool, ShowCreateTableTool
from src.scenarios.db_diagnosis import SYSTEM_PROMPT
from src.core.fallback import RuleEngine
from src.config import load_config

# ===== 1. 创建 FastAPI 实例 =====
app = FastAPI(
    title = "数据库诊断 Agent",
    description="输入SQL，Agent 自动诊断并给出优化建议",
    version="0.1.0",
)

# ===== 2. 定义请求/响应模型 =====
class ChatRequest(BaseModel):
    """请求体"""
    query: str
    use_llm: bool = True  # 允许调用方选择是否使用 LLM
    show_thinking: bool = False  # 是否显示思考过程

class ChatResponse(BaseModel):
    """响应体"""
    result: str
    thinking: list[str] | None = None  # 思考过程
    mode: str = "llm"  # "llm" 或 "fallback"

# ===== 3. 初始化 Agent（单例） =====

def create_agent():
    """创建 Agent 实例"""
    config = load_config()
    llm_config = config["llm"]

    llm = LLMClient(
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        model=llm_config.get("model", "deepseek-v4-flash"),
    )

    tools = ToolRegistry()
    tools.register(ExplainTool())
    tools.register(ShowIndexTool())
    tools.register(ShowCreateTableTool())

    return Agent(llm=llm, tools=tools, system_prompt=SYSTEM_PROMPT)

agent = create_agent()
rule_engine = RuleEngine()

# ===== 4. 定义 API 接口 =====

@app.get("/")
def root():
    """根路径，返回 API 信息"""
    return {
        "name": "数据库诊断 Agent",
        "version": "1.0.0",
        "endpoints": {
            "POST /chat": "诊断 SQL",
            "GET /health": "健康检查",
            "GET /memory/stats": "记忆统计",
        },
    }


@app.get("/health")
def health():
    """健康检查"""
    return {"status": "ok"}

@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """
    诊断 SQL。

    请求体：
    ```json
    {
        "query": "SELECT * FROM orders WHERE status = 'PENDING'",
        "use_llm": true,
        "show_thinking": true
    }
    ```
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")

    if not request.use_llm:
        # 降级模式：使用规则引擎
        result = rule_engine.diagnose(request.query)
        return ChatResponse(result=result, mode="fallback")

    # LLM 模式
    result = agent.run(request.query)

    thinking = agent.get_thinking() if request.show_thinking else None
    return ChatResponse(result=result, thinking=thinking, mode="llm")

@app.get("/memory/stats")
def memory_stats():
    """查看记忆系统统计"""
    stats = agent.get_memory_stats()
    history = agent.long_term.get_recent(5)
    return {
        "stats": stats,
        "recent_records": history,
    }


@app.post("/memory/clear")
def clear_memory():
    """清空当前对话记忆"""
    agent.short_term.clear()
    return {"status": "ok", "message": "对话记忆已清空"}