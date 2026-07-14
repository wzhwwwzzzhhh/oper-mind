"""系统装配 — 统一构建 Coordinator 及其依赖

app.py（FastAPI 入口）与 main.py（CLI 入口）此前各自维护了一份逐字重复的
build_system()。为消除重复、保证两个入口的装配逻辑单一可信，将构建逻辑集中到此处。
"""

from src.core.llm import LLMClient
from src.core.coordinator import CoordinatorAgent
from src.agents.db_agent import DBAgent
from src.agents.server_agent import ServerAgent
from src.agents.log_agent import LogAgent
from src.agents.report_agent import ReportAgent
from src.core.debate import DebateArena
from src.core.reflection import ReflectionEngine
from src.config import load_config


def build_system() -> CoordinatorAgent:
    """构建整个系统，注入所有依赖，返回已接通质量保障链路的 Coordinator"""
    config = load_config()
    llm_config = config["llm"]

    llm = LLMClient(
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        model=llm_config.get("model", "qwen2.5:7b"),
    )

    # 领域 Agent
    db_agent = DBAgent(llm=llm)
    server_agent = ServerAgent(llm=llm)
    log_agent = LogAgent(llm=llm)

    # 质量保障组件
    debate = DebateArena(llm=llm)
    reflection = ReflectionEngine(llm=llm)
    report = ReportAgent()

    # Coordinator：持有编排图，注入领域 Agent 与质量保障组件
    coordinator = CoordinatorAgent(
        llm=llm, debate=debate, reflection=reflection, report=report
    )
    coordinator.register_agent("db", db_agent)
    coordinator.register_agent("server", server_agent)
    coordinator.register_agent("log", log_agent)

    return coordinator
