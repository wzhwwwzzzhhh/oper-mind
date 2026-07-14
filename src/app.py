"""FastAPI 入口 — 多智能体运维诊断 API"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.core.llm import LLMClient
from src.core.coordinator import CoordinatorAgent
from src.agents.db_agent import DBAgent
from src.agents.server_agent import ServerAgent
from src.agents.log_agent import LogAgent
from src.agents.report_agent import ReportAgent
from src.core.debate import DebateArena
from src.core.reflection import ReflectionEngine
from src.config import load_config

# ===== 1. FastAPI 实例 =====
app = FastAPI(
    title="OperMind — 多智能体运维诊断系统",
    description="输入运维问题，AI Agent 自动诊断并给出优化建议",
    version="1.0.0",
)

# ===== 2. 请求/响应模型 =====

class DiagnoseRequest(BaseModel):
    """诊断请求"""
    query: str
    show_thinking: bool = False

class DiagnoseResponse(BaseModel):
    """诊断响应"""
    result: str
    thinking: list[str] | None = None
    trace: list[dict] | None = None
    strategy: str = ""

# ===== 3. 初始化系统（单例） =====

def build_system():
    config = load_config()
    llm_config = config["llm"]

    llm = LLMClient(
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        model=llm_config.get("model", "qwen2.5:7b"),
    )

    db_agent = DBAgent(llm=llm)
    server_agent = ServerAgent(llm=llm)
    log_agent = LogAgent(llm=llm)

    debate = DebateArena(llm=llm)
    reflection = ReflectionEngine(llm=llm)
    report = ReportAgent()

    coordinator = CoordinatorAgent(
        llm=llm, debate=debate, reflection=reflection, report=report
    )
    coordinator.register_agent("db", db_agent)
    coordinator.register_agent("server", server_agent)
    coordinator.register_agent("log", log_agent)

    return coordinator

coordinator = build_system()

# ===== 4. API 接口 =====

@app.get("/")
def root():
    return {
        "name": "OperMind",
        "version": "1.0.0",
        "description": "多智能体运维诊断协作系统",
        "endpoints": {
            "POST /diagnose": "诊断问题",
            "GET /health": "健康检查",
            "GET /memory/stats": "记忆统计",
            "POST /memory/clear": "清空记忆",
        },
    }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/diagnose", response_model=DiagnoseResponse)
def diagnose(request: DiagnoseRequest):
    """诊断入口"""
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")

    result = coordinator.route(request.query)
    trace = coordinator.get_trace()
    thinking = coordinator.get_thinking() if request.show_thinking else None

    # 从链路事件里取出路由策略
    strategy = ""
    for e in trace:
        if e.get("node") == "route":
            strategy = e.get("detail", "")
            break

    return DiagnoseResponse(
        result=result,
        thinking=thinking,
        trace=trace if request.show_thinking else None,
        strategy=strategy,
    )

@app.get("/memory/stats")
def memory_stats():
    """记忆统计"""
    return {"message": "记忆系统功能待实现"}

@app.post("/memory/clear")
def clear_memory():
    return {"status": "ok", "message": "对话记忆已清空"}
